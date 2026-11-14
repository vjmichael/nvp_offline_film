"""NVP-PROD-06B: approved procedural weighted skin and explicit neutral-pose calibration.

No raw user Blender code, no external asset fetching, no magical rig compatibility.
The geometry is a recognizable seven-part preview silhouette, not a production
character. It has a genuine ARMATURE modifier and blended vertex groups.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess

from backend.nvp_studio import Studio
from backend.nvp_production_scene import compact, digest
from backend.nvp_rig_motion import RigMotion, ROLES
from backend.nvp_blender_acceptance import blender_available

SKIN_VERSION = 'nvp.procedural_skin.v1'
MAX_SKIN_ACTORS = 16


def _degrees(values, name):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError(f'{name} must be an explicit XYZ Euler vector')
    out = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 180:
            raise ValueError(f'{name} must contain finite degrees in [-180,180]')
        out.append(float(value))
    return out


class SkinnedPerformance:
    """Production-scoped approval overlay on the current immutable motion package."""

    def __init__(self, studio: Studio):
        self.studio = studio
        self.rig = RigMotion(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_skin_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                motion_sha TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_skin_events (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                action TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _context(self, project_id, scene_id):
        package = self.rig.export(project_id, scene_id)
        return package, digest(package['motion'])

    def _read_db(self, db, project_id, scene_id):
        row = db.execute('SELECT * FROM prod_skin_sessions WHERE project_id=? AND scene_id=?',
                         (project_id, scene_id)).fetchone()
        if row is None:
            raise KeyError('Skinning session does not exist')
        return dict(row)

    def create(self, project_id, scene_id):
        package, motion_sha = self._context(project_id, scene_id)
        actors = [{'instance_id':a['instance_id'], 'style':'segmented_weighted_preview_v1',
                   'calibrations':{}}
                  for a in package['motion']['plan']['actors'] if a['segments']]
        if not actors or len(actors) > MAX_SKIN_ACTORS:
            raise ValueError('A bounded approved motion actor is required for skinning')
        plan = {'format':'nvp.skin.proposal.v1', 'actors':actors}
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM prod_skin_sessions WHERE project_id=? AND scene_id=?',
                          (project_id,scene_id)).fetchone():
                raise RuntimeError('Skinning session already exists')
            db.execute('INSERT INTO prod_skin_sessions VALUES(?,?,?,?,?,?,?)',
                       (project_id,scene_id,0,'draft',motion_sha,compact(plan),None))
            db.execute('INSERT INTO prod_skin_events VALUES(?,?,?,?,?)',
                       (project_id,scene_id,0,'create',compact(plan)))
        return self.read(project_id,scene_id)

    def read(self, project_id, scene_id):
        _, motion_sha = self._context(project_id,scene_id)
        with self.studio._connection() as db:
            row = self._read_db(db,project_id,scene_id)
        return {'project_id':project_id,'scene_id':scene_id,'revision':row['revision'],
                'status':row['status'], 'stale':row['motion_sha']!=motion_sha,
                'actors':json.loads(row['plan_json'])['actors'],
                'motion_sha':row['motion_sha'],'approval_sha':row['approval_sha']}

    def calibrate(self, project_id,scene_id,actor_id,role,source_neutral_deg,target_neutral_deg,expected_revision):
        if role not in ROLES:
            raise ValueError('Unknown preview bone role')
        source = _degrees(source_neutral_deg,'Source neutral')
        target = _degrees(target_neutral_deg,'Target neutral')
        _, motion_sha = self._context(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._read_db(db,project_id,scene_id)
            if (isinstance(expected_revision,bool) or row['revision']!=expected_revision
                    or row['status']!='draft' or row['motion_sha']!=motion_sha):
                raise RuntimeError('Skinning revision, approval, or motion dependency changed')
            plan=json.loads(row['plan_json'])
            actor=next((x for x in plan['actors'] if x['instance_id']==actor_id),None)
            if actor is None:
                raise KeyError('Actor not present in approved motion package')
            actor['calibrations'][role]={'source_neutral_deg':source,'target_neutral_deg':target,
                                         'author':'director','provenance':'authored'}
            revision=row['revision']+1
            db.execute('UPDATE prod_skin_sessions SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(plan),project_id,scene_id))
            db.execute('INSERT INTO prod_skin_events VALUES(?,?,?,?,?)',
                       (project_id,scene_id,revision,'calibrate:'+role,compact(plan)))
        return self.read(project_id,scene_id)

    def approve(self,project_id,scene_id,expected_revision):
        package,motion_sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._read_db(db,project_id,scene_id)
            if (isinstance(expected_revision,bool) or row['revision']!=expected_revision
                    or row['status']!='draft' or row['motion_sha']!=motion_sha):
                raise RuntimeError('Skin approval requires a current, editable plan')
            plan=json.loads(row['plan_json'])
            existing={x['instance_id'] for x in package['motion']['plan']['actors'] if x['segments']}
            if {x['instance_id'] for x in plan['actors']}!=existing:
                raise RuntimeError('Skin actor roster changed')
            receipt=digest([motion_sha,plan])
            revision=row['revision']+1
            db.execute('UPDATE prod_skin_sessions SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?',
                       (revision,'approved',receipt,project_id,scene_id))
            db.execute('INSERT INTO prod_skin_events VALUES(?,?,?,?,?)',
                       (project_id,scene_id,revision,'director_approve',compact(plan)))
        return self.read(project_id,scene_id)

    def history(self,project_id,scene_id):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute('SELECT revision,action,snapshot_json FROM prod_skin_events '
                       'WHERE project_id=? AND scene_id=? ORDER BY revision',(project_id,scene_id))]

    def export(self,project_id,scene_id):
        package,motion_sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:row=self._read_db(db,project_id,scene_id)
        plan=json.loads(row['plan_json'])
        if (row['status']!='approved' or row['motion_sha']!=motion_sha
                or row['approval_sha']!=digest([motion_sha,plan])):
            raise RuntimeError('Only current director-approved weighted skinning can be exported')
        roster={a['instance_id'] for a in package['motion']['plan']['actors'] if a['segments']}
        if {a['instance_id'] for a in plan['actors']}!=roster:
            raise RuntimeError('Approved skin roster is no longer valid')
        return {**package,'skin':{'format':'nvp.production.skin.v1','style':SKIN_VERSION,
                 'actors':plan['actors'],'approval_sha':row['approval_sha'],
                 'motion_sha':motion_sha}}

    def blender_script(self,project_id,scene_id):
        package=self.export(project_id,scene_id)
        return inject_skin_script(self.rig.blender_script(project_id,scene_id),package['skin'])


# Each of the 7 named bones owns a tube segment inside ONE weighted mesh.
# The first ring of child segments blends 35% of its weights to the parent bone,
# producing real Blender ARMATURE deformation rather than attached rigid props.
# This is a deliberately stylized preview, not automatic production-quality skinning.
SKIN_SCRIPT = r'''# NVP-PROD-06B: creator-approved weighted humanoid previs.
from mathutils import Vector, Euler
skin_data=json.loads(SKIN_PAYLOAD)
assert skin_data['format']=='nvp.production.skin.v1'
assert skin_data['style']=='nvp.procedural_skin.v1'
for skin_binding in skin_data['actors']:
    actor_id=skin_binding['instance_id']
    rig=bpy.data.objects['NVP_RIG_'+actor_id]
    actor=bpy.data.objects['NVP_'+actor_id]
    assert rig.parent==actor and rig.type=='ARMATURE'
    calibration=skin_binding['calibrations']
    motion_actor=next(x for x in motion['plan']['actors'] if x['instance_id']==actor_id)
    # Calibration is a quaternion delta: q_target_neutral * inverse(q_source_neutral) * q_motion.
    # Direct subtraction of Euler angles would be incorrect for multi-axis motion.
    for segment in motion_actor['segments']:
        clip=motion['clips'][segment['clip_id']]
        for sample in clip['frames']:
            frame=segment['start_frame']+sample['frame']*take['fps']/clip['fps']
            for role,neutral in calibration.items():
                datum=sample['joints'].get(role)
                if datum is None:continue
                src=Euler([math.radians(x) for x in neutral['source_neutral_deg']],datum['order']).to_quaternion()
                target=Euler([math.radians(x) for x in neutral['target_neutral_deg']],'XYZ').to_quaternion()
                animated=Euler([math.radians(x) for x in datum['euler_deg']],datum['order']).to_quaternion()
                bone=rig.pose.bones[role]
                bone.rotation_mode='QUATERNION'
                bone.rotation_quaternion=target @ (src.inverted() @ animated)
                bone.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=role)
    verts=[]; faces=[];weights={role:[] for role in rig.pose.bones.keys()}
    radius_scale={'hips':.10,'spine':.12,'head':.10,'arm_left':.045,
                  'arm_right':.045,'leg_left':.06,'leg_right':.06}
    for role in ('hips','spine','head','arm_left','arm_right','leg_left','leg_right'):
        rest=rig.data.bones[role]
        head=rest.head_local.copy();tail=rest.tail_local.copy()
        direction=(tail-head).normalized()
        tangent=direction.cross(Vector((0,0,1)))
        if tangent.length<.001:tangent=direction.cross(Vector((1,0,0)))
        tangent.normalize();bitangent=direction.cross(tangent).normalized()
        radius=radius_scale[role]*float(next(x['height_m'] for x in take['actors'] if x['instance_id']==actor_id))
        index0=len(verts)
        for ri,t in enumerate((0.,.5,1.)):
            center=head.lerp(tail,t)
            for k in range(8):
                angle=2*math.pi*k/8
                verts.append(tuple(center+radius*(math.cos(angle)*tangent+math.sin(angle)*bitangent)))
                index=len(verts)-1
                par=rest.parent.name if rest.parent is not None else None
                if ri==0 and par is not None:
                    weights[role].append((index,.65)); weights[par].append((index,.35))
                else:weights[role].append((index,1.))
        for ri in (0,1):
            for k in range(8):
                a=index0+ri*8+k;b=index0+ri*8+(k+1)%8
                faces.append((a,b,b+8,a+8))
        faces.append(tuple(index0+k for k in reversed(range(8))))
        faces.append(tuple(index0+16+k for k in range(8)))
    data=bpy.data.meshes.new('NVP_WEIGHTED_GEOMETRY_'+actor_id)
    data.from_pydata(verts,[],faces);data.update()
    skin=bpy.data.objects.new('NVP_SKIN_'+actor_id,data)
    bpy.context.collection.objects.link(skin)
    skin.parent=rig
    skin['nvp_skin_kind']='segmented_weighted_preview_v1'
    skin['nvp_actor_id']=actor_id
    skin['nvp_skin_approval_sha']=skin_data['approval_sha']
    for role,entries in weights.items():
        group=skin.vertex_groups.new(name=role)
        for idx,weight in entries:group.add([idx],weight,'REPLACE')
    mod=skin.modifiers.new('NVP_ARMATURE_DEFORM','ARMATURE')
    mod.object=rig;mod.use_vertex_groups=True
    rig.show_in_front=True
    # Keep original root animation and ID intact; render only the weighted silhouette.
    actor.hide_render=True
    actor['nvp_skin_proxy_hidden']=True
sc['nvp_skin_approval_sha']=skin_data['approval_sha']
'''


def inject_skin_script(base: str, skin: dict):
    anchor='args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []'
    if base.count(anchor)!=1:
        raise RuntimeError('Unexpected rigged motion generator insertion point')
    return base.replace(anchor,'SKIN_PAYLOAD='+repr(compact(skin))+'\n'+SKIN_SCRIPT+'\n'+anchor)


SKIN_AUDIT_SCRIPT=r'''import bpy,json,math,sys
from pathlib import Path
from mathutils import Euler
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
payload=json.loads(Path(opts['--payload']).read_text('utf8'))
sc=bpy.context.scene
checks=[]
def check(name,ok,value):checks.append({'check':name,'passed':bool(ok),'evidence':value})
check('skin_approval',sc.get('nvp_skin_approval_sha')==payload['skin']['approval_sha'],'approved manifest')
check('motion_approval',sc.get('nvp_motion_approval_sha')==payload['motion']['approval_sha'],'approved rig motion')
for binding in payload['skin']['actors']:
    rid=binding['instance_id']
    rig=bpy.data.objects.get('NVP_RIG_'+rid)
    skin=bpy.data.objects.get('NVP_SKIN_'+rid)
    actor=bpy.data.objects.get('NVP_'+rid)
    check('rig:'+rid,rig is not None and rig.type=='ARMATURE',rid)
    check('skin:'+rid,skin is not None and skin.type=='MESH',rid)
    if rig is None or skin is None or actor is None:continue
    check('parent:'+rid,skin.parent==rig and rig.parent==actor, 'actor blocking preserved')
    check('proxy_hidden:'+rid,actor.hide_render and actor.get('nvp_skin_proxy_hidden')==True,'proxy hidden')
    check('skin_identity:'+rid,skin.get('nvp_actor_id')==rid and skin.get('nvp_skin_approval_sha')==payload['skin']['approval_sha'],rid)
    mods=[m for m in skin.modifiers if m.type=='ARMATURE' and m.object==rig and m.use_vertex_groups]
    check('armature_modifier:'+rid,len(mods)==1,len(mods))
    check('vertex_count:'+rid,len(skin.data.vertices)==168,len(skin.data.vertices))
    check('face_count:'+rid,len(skin.data.polygons)==126,len(skin.data.polygons))
    groups={g.name for g in skin.vertex_groups}
    check('weighted_roles:'+rid,groups=={'hips','spine','head','arm_left','arm_right','leg_left','leg_right'},sorted(groups))
    weights_ok=all(len(v.groups)>0 and abs(sum(g.weight for g in v.groups)-1.)<1e-5 for v in skin.data.vertices)
    blended=sum(1 for v in skin.data.vertices if len(v.groups)>1)
    check('normalized_weights:'+rid,weights_ok, 'sum=1')
    check('joint_blending:'+rid,blended>=20,blended)
    motion_actor=next(x for x in payload['motion']['plan']['actors'] if x['instance_id']==rid)
    for seg in motion_actor['segments']:
        clip=payload['motion']['clips'][seg['clip_id']]
        for sample in (clip['frames'][0], clip['frames'][len(clip['frames'])//2]):
            frame=seg['start_frame']+sample['frame']*payload['take']['fps']/clip['fps']
            sc.frame_set(int(frame),subframe=frame-int(frame))
            for role,neutral in binding['calibrations'].items():
                if role not in sample['joints']:continue
                datum=sample['joints'][role]
                src=Euler([math.radians(x) for x in neutral['source_neutral_deg']],datum['order']).to_quaternion()
                target=Euler([math.radians(x) for x in neutral['target_neutral_deg']],'XYZ').to_quaternion()
                animated=Euler([math.radians(x) for x in datum['euler_deg']],datum['order']).to_quaternion()
                expected=target @ (src.inverted() @ animated)
                q=rig.pose.bones[role].rotation_quaternion
                err=abs(abs(q.dot(expected))-1.)
                check('calibrated_pose:'+rid+':'+role+':'+str(frame),err<.0005,err)
    # Independent evaluated modifier check: an arm's vertices actually MOVE.
    dynamic=None
    for seg in motion_actor['segments']:
        clip=payload['motion']['clips'][seg['clip_id']]
        first=clip['frames'][0]
        for sample in clip['frames'][1:]:
            for role in ('arm_left','arm_right','leg_left','leg_right','head','spine'):
                if role in first['joints'] and role in sample['joints']:
                    before=first['joints'][role]['euler_deg'];after=sample['joints'][role]['euler_deg']
                    if max(abs(a-b) for a,b in zip(before,after))>10:
                        dynamic=(seg,clip,first,sample,role);break
            if dynamic:break
        if dynamic:break
    if dynamic:
        seg,clip,first,middle,role=dynamic
        # Role tube begins at index role_index*24; tip ring is +16.
        role_index=('hips','spine','head','arm_left','arm_right','leg_left','leg_right').index(role)
        idx=role_index*24+16
        locations=[]
        for sample in (first,middle):
            frame=seg['start_frame']+sample['frame']*payload['take']['fps']/clip['fps']
            sc.frame_set(int(frame),subframe=frame-int(frame))
            deps=bpy.context.evaluated_depsgraph_get()
            obj=skin.evaluated_get(deps)
            mesh=obj.to_mesh()
            locations.append(tuple(obj.matrix_world@mesh.vertices[idx].co))
            obj.to_mesh_clear()
        displacement=math.dist(locations[0],locations[1])
        check('real_skin_deformation:'+rid,displacement>.02,{'vertex':idx,'metres':displacement,'role':role})
    else:
        check('non_dynamic_clip:'+rid,True,'no source frame with >10 degrees change')
report={'format':'nvp.skin.blender.audit.v1','blender':bpy.app.version_string,
        'passed':all(x['passed'] for x in checks),'checks':checks}
Path(opts['--audit']).write_text(json.dumps(report,sort_keys=True,indent=2),'utf8')
if not report['passed']:raise RuntimeError('Weighted skinning audit failed')
if opts.get('--skip-render')!='1':
    sc.frame_set(max(1,int(sc.frame_end//2)))
    sc.render.engine='BLENDER_WORKBENCH'
    sc.render.filepath=opts['--preview']
    sc.render.image_settings.file_format='PNG'
    sc.render.resolution_x=960;sc.render.resolution_y=540;sc.render.resolution_percentage=100
    bpy.ops.render.render(write_still=True)
'''


def run_skin_acceptance(service:SkinnedPerformance,project_id:str,scene_id:str,directory,
                        *,executable='blender',render_preview=True,timeout=180):
    root=Path(directory).resolve()
    root.mkdir(parents=True,exist_ok=True)
    package=service.export(project_id,scene_id)
    paths={'script':root/'build_skin.py','payload':root/'skin.json','audit_script':root/'audit_skin.py',
           'blend':root/'skin.blend','audit':root/'skin_audit.json','preview':root/'skin_preview.png'}
    paths['script'].write_text(service.blender_script(project_id,scene_id),'utf8')
    paths['payload'].write_text(compact({'skin':package['skin'],'motion':package['motion'],'take':package['take']}),'utf8')
    paths['audit_script'].write_text(SKIN_AUDIT_SCRIPT,'utf8')
    probe=blender_available(executable)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason'],'script':str(paths['script'])}
    cmds=[
        [probe['path'],'-b','--factory-startup','-t','2','--python',str(paths['script']),
         '--','--output',str(paths['blend'])],
        [probe['path'],'-b',str(paths['blend']),'-t','2','--python',str(paths['audit_script']),
         '--','--payload',str(paths['payload']),'--audit',str(paths['audit']),
         '--preview',str(paths['preview'])]
    ]
    if not render_preview:cmds[1].extend(['--skip-render','1'])
    runs=[]
    for i,cmd in enumerate(cmds,1):
        try:p=run_owned_subprocess(cmd,capture_output=True,text=True,cwd=root,timeout=timeout)
        except subprocess.TimeoutExpired:return {'status':'failed','step':i,'reason':'Blender timed out'}
        runs.append({'step':i,'exit_code':p.returncode,'stdout_tail':p.stdout[-1800:],
                     'stderr_tail':p.stderr[-2100:]})
        if p.returncode:
            return {'status':'failed','step':i,'reason':'Native Blender build or audit failed','runs':runs}
    if (not paths['blend'].is_file() or not paths['audit'].is_file()
            or (render_preview and not paths['preview'].is_file())):
        return {'status':'failed','reason':'Native acceptance outputs absent','runs':runs}
    report=json.loads(paths['audit'].read_text('utf8'))
    if not report.get('passed'):
        return {'status':'failed','reason':'Weighted mesh or retarget audit failed','report':report}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'checks':len(report['checks']),'blend':str(paths['blend']),'audit':str(paths['audit']),
            'preview':str(paths['preview']) if render_preview else None,
            'version':probe['version']}
