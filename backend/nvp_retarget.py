"""NVP-PROD-06D: director-owned rest-frame motion calibration.

The existing PROD-06C binding is the authority for asset and bone identity.
This layer contains approved joint limits, contact frames, a dependable source
fingerprint, and Blender-evaluated rest-frame transformation. It does not infer
licenses, create actors, or claim quality on arbitrary rigs.
"""
from __future__ import annotations

import json
import math
import subprocess
from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender
from pathlib import Path

from backend.nvp_character_assets import CharacterAssets
from backend.nvp_rig_motion import ROLES
from backend.nvp_production_scene import compact, digest
from backend.nvp_blender_acceptance import blender_available

DEFAULT_LIMITS = {
    'hips': 90.0, 'spine': 85.0, 'head': 80.0,
    'arm_left': 160.0, 'arm_right': 160.0,
    'leg_left': 150.0, 'leg_right': 150.0,
}


def finite_number(value, label, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{label} must be finite in [{lo},{hi}]')
    return float(value)


def valid_quat(q):
    if not isinstance(q, (list, tuple)) or len(q) != 4 or not all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in q
    ):
        raise ValueError('Quaternion must contain four finite numbers')
    n = math.sqrt(sum(x*x for x in q))
    if n < 1e-8:
        raise ValueError('Quaternion length is zero')
    return tuple(x/n for x in q)


def qmul(a, b):
    w, x, y, z = a; W, X, Y, Z = b
    return (w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y,
            w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W)


def qinv(q):
    w, x, y, z = valid_quat(q)
    return (w, -x, -y, -z)


def change_rest_frame(source_delta, source_rest, target_rest):
    """Conjugate a local rotation into a differently oriented target rest basis.

    Both rest quaternions represent orientations in the same global coordinate
    frame. The result intentionally changes orientation, not translation or scale.
    """
    source_delta=valid_quat(source_delta)
    source_rest=valid_quat(source_rest)
    target_rest=valid_quat(target_rest)
    align=qmul(qinv(target_rest),source_rest)
    return valid_quat(qmul(qmul(align,source_delta),qinv(align)))


class RetargetCalibration:
    def __init__(self, studio):
        self.studio=studio
        self.characters=CharacterAssets(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_retarget_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, character_sha TEXT NOT NULL,
                plan_json TEXT NOT NULL, approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_retarget_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _context(self,pid,sid):
        package=self.characters.export(pid,sid)
        return package,digest(package['character'])

    def _record(self,db,pid,sid):
        row=db.execute('SELECT * FROM prod_retarget_sessions WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone()
        if not row:raise KeyError('Retarget calibration does not exist')
        return dict(row)

    def create(self,pid,sid):
        pkg,sha=self._context(pid,sid)
        plan={'format':'nvp.retarget.calibration.v1','actors':[
            {'instance_id':x['instance_id'], 'joint_limits_deg':dict(DEFAULT_LIMITS),
             'contact_frames':[1], 'contact_tolerance_m':0.08,
             'max_ground_penetration_m':0.04, 'author':'director',
             'provenance':'authored'} for x in pkg['character']['bindings']]}
        if not plan['actors']:raise ValueError('No approved external character')
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM prod_retarget_sessions WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone():
                raise RuntimeError('Retarget session already exists')
            db.execute('INSERT INTO prod_retarget_sessions VALUES (?,?,?,?,?,?,?)',
                       (pid,sid,0,'draft',sha,compact(plan),None))
            db.execute('INSERT INTO prod_retarget_history VALUES (?,?,?,?,?)',
                       (pid,sid,0,'create',compact(plan)))
        return self.read(pid,sid)

    def read(self,pid,sid):
        _,sha=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        return {'project_id':pid,'scene_id':sid,'revision':row['revision'],
                'status':row['status'], 'stale':row['character_sha']!=sha,
                'actors':json.loads(row['plan_json'])['actors'],
                'approval_sha':row['approval_sha']}

    def configure(self,pid,sid,actor_id,expected_revision,*,joint_limits_deg,
                  contact_frames,contact_tolerance_m,max_ground_penetration_m):
        if not isinstance(joint_limits_deg,dict) or set(joint_limits_deg)!=set(ROLES):
            raise ValueError('All seven joint limits must be declared')
        limits={r:finite_number(joint_limits_deg[r],r+' limit',1.0,180.0) for r in ROLES}
        if not isinstance(contact_frames,list) or len(contact_frames)>32 or not contact_frames or (
            any(type(x) is not int or x<1 or x>100000 for x in contact_frames) or
            contact_frames!=sorted(set(contact_frames))):
            raise ValueError('Contact frames must be sorted, unique positive frame indices')
        tolerance=finite_number(contact_tolerance_m,'contact tolerance',0,0.5)
        penetration=finite_number(max_ground_penetration_m,'ground penetration',0,0.25)
        pkg,sha=self._context(pid,sid)
        frame_end=max(x['stop_frame']-1 for x in pkg['take']['shots'])
        if any(x>frame_end for x in contact_frames):raise ValueError('Contact frame is outside take')
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._record(db,pid,sid)
            if row['status']!='draft' or row['character_sha']!=sha or type(expected_revision) is not int or row['revision']!=expected_revision:
                raise RuntimeError('Retarget configuration was changed or approved')
            plan=json.loads(row['plan_json'])
            found=next((a for a in plan['actors'] if a['instance_id']==actor_id),None)
            if found is None:raise KeyError('Actor not present in approved character binding')
            found.update(joint_limits_deg=limits,contact_frames=contact_frames,
                         contact_tolerance_m=tolerance,max_ground_penetration_m=penetration)
            revision=row['revision']+1
            db.execute('UPDATE prod_retarget_sessions SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(plan),pid,sid))
            db.execute('INSERT INTO prod_retarget_history VALUES(?,?,?,?,?)',
                       (pid,sid,revision,'configure',compact(plan)))
        return self.read(pid,sid)

    def approve(self,pid,sid,expected_revision):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._record(db,pid,sid)
            if row['status']!='draft' or row['character_sha']!=sha or type(expected_revision) is not int or row['revision']!=expected_revision:
                raise RuntimeError('Only a fresh director-edited retarget plan may be approved')
            plan=json.loads(row['plan_json'])
            if {a['instance_id'] for a in plan['actors']} != {x['instance_id'] for x in pkg['character']['bindings']}:
                raise RuntimeError('Approved character roster changed')
            approval=digest([sha,plan]);revision=row['revision']+1
            db.execute('UPDATE prod_retarget_sessions SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?',
                       (revision,'approved',approval,pid,sid))
            db.execute('INSERT INTO prod_retarget_history VALUES(?,?,?,?,?)',
                       (pid,sid,revision,'approve',compact(plan)))
        return self.read(pid,sid)

    def history(self,pid,sid):
        self.studio.get_project(pid)
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute('SELECT revision,action,snapshot_json FROM prod_retarget_history WHERE project_id=? AND scene_id=? ORDER BY revision',(pid,sid))]

    def export(self,pid,sid):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        plan=json.loads(row['plan_json'])
        if row['status']!='approved' or row['character_sha']!=sha or row['approval_sha']!=digest([sha,plan]):
            raise RuntimeError('Only an approved current retarget calibration may be exported')
        return {**pkg,'retarget':{'format':'nvp.retarget.approved.v1',
                                'character_sha':sha,'approval_sha':row['approval_sha'],
                                'actors':plan['actors'],
                                'limitations':'Explicit 7-role mapping, rigid rest-basis correction, no adaptive IK or muscle simulation'}}

    def export_bundle(self,pid,sid,path):
        pkg=self.export(pid,sid)
        out=Path(path).resolve()
        self.characters.export_bundle(pid,sid,out)
        original=(out/'build_characters.py').read_text('utf8')
        (out/'build_retargeted.py').write_text(inject_retarget_script(original,pkg),'utf8')
        (out/'retarget.json').write_text(compact(pkg),'utf8')
        (out/'audit_retarget.py').write_text(RETARGET_AUDIT_SCRIPT,'utf8')
        return {'path':str(out),'status':'staged','actor_count':len(pkg['retarget']['actors'])}


# Rest orientations are taken from REAL imported Blender bones, not assumed to be
# identical to the preview rig. This post-process overrides PROD-06C's naive
# quaternion copy, but NEVER changes approved actor root paths or camera cuts.
RETARGET_SCRIPT = r'''# NVP-PROD-06D: approved rest-frame correction with explicit joint ceilings
from mathutils import Vector
retarget=json.loads(RETARGET_PAYLOAD)
assert retarget['format']=='nvp.retarget.approved.v1'
for rb in retarget['actors']:
    rid=rb['instance_id']
    src=bpy.data.objects['NVP_RIG_'+rid]
    dest=bpy.data.objects['NVP_CHARACTER_RIG_'+rid]
    actor_binding=next(x for x in character['bindings'] if x['instance_id']==rid)
    motion_actor=next(x for x in motion['plan']['actors'] if x['instance_id']==rid)
    mapping=actor_binding['role_map']
    # The imported file's own animation is not NVP authorization.
    dest.animation_data_clear()
    for name in mapping.values():
        dest.pose.bones[name].rotation_mode='QUATERNION'
        dest.pose.bones[name].rotation_quaternion=(1,0,0,0)
    rest_data=[]
    for role,name in mapping.items():
        sb=src.pose.bones[role].bone;tb=dest.pose.bones[name].bone
        if sb.length<0.0001 or tb.length<0.0001:
            raise RuntimeError('Zero-length source or imported character bone')
        # Basis change in actor/world coordinates. Local rotation is conjugated;
        # copying raw quaternion components works only for identical rest bases.
        qsrc=(src.matrix_world.to_quaternion() @ sb.matrix_local.to_quaternion()).normalized()
        qdst=(dest.matrix_world.to_quaternion() @ tb.matrix_local.to_quaternion()).normalized()
        align=qdst.inverted() @ qsrc
        rest_data.append({'role':role,'target_bone':name,
                          'source_length_m':round(sb.length,6),'target_length_m':round(tb.length,6),
                          'source_rest_quat':[round(v,8) for v in qsrc],
                          'target_rest_quat':[round(v,8) for v in qdst],
                          'alignment_quat':[round(v,8) for v in align]})
    dest['nvp_retarget_rest_report']=json.dumps(rest_data,sort_keys=True)
    for segment in motion_actor['segments']:
        clip=motion['clips'][segment['clip_id']]
        for sample in clip['frames']:
            frame=segment['start_frame']+sample['frame']*take['fps']/clip['fps']
            sc.frame_set(int(frame),subframe=frame-int(frame))
            for role,name in mapping.items():
                if role not in sample['joints']:continue
                sb=src.pose.bones[role].bone;tb=dest.pose.bones[name].bone
                src_q=(src.matrix_world.to_quaternion() @ sb.matrix_local.to_quaternion()).normalized()
                dst_q=(dest.matrix_world.to_quaternion() @ tb.matrix_local.to_quaternion()).normalized()
                align=dst_q.inverted() @ src_q
                corrected=(align @ src.pose.bones[role].rotation_quaternion @ align.inverted()).normalized()
                angle=math.degrees(corrected.angle)
                if angle>rb['joint_limits_deg'][role]+0.0001:
                    raise RuntimeError('Joint limit exceeded: '+role+' at frame '+str(frame))
                b=dest.pose.bones[name]
                b.rotation_quaternion=corrected
                b.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=name)
    # Mesh-only proportion correction. The approved actor and its root motion
    # remain at their author-provided transforms, while this imported model is
    # scaled to the configured actor height and initially grounded.
    target_height=float(next(x['height_m'] for x in take['actors'] if x['instance_id']==rid))
    meshes=[obj for obj in bpy.data.objects if obj.get('nvp_character_actor')==rid and obj.type=='MESH']
    if not meshes:raise RuntimeError('No imported character mesh for retarget calibration')
    base_frame=rb['contact_frames'][0]
    sc.frame_set(base_frame)
    bpy.context.view_layer.update()
    def mesh_bounds():
        deps=bpy.context.evaluated_depsgraph_get();pts=[]
        for mesh in meshes:
            eval_obj=mesh.evaluated_get(deps);geom=eval_obj.to_mesh()
            try:pts.extend([eval_obj.matrix_world@v.co for v in geom.vertices])
            finally:eval_obj.to_mesh_clear()
        if not pts:raise RuntimeError('Imported character mesh has no vertices')
        return min(p.z for p in pts),max(p.z for p in pts)
    low,high=mesh_bounds();height=high-low
    if height<=.001:raise RuntimeError('Imported character has zero visible height')
    scale=target_height/height
    if not .1<=scale<=10:raise RuntimeError('Character height adaptation exceeds allowable ratio')
    dest.scale=[float(v)*scale for v in dest.scale]
    bpy.context.view_layer.update()
    # Position is relative to NVP's actor root, which is commonly non-uniformly
    # scaled. Convert world-space clearance into the parent's local-Z units.
    for _ in range(4):
        low,_=mesh_bounds()
        if abs(low)<.001:break
        parent_z=abs(dest.parent.matrix_world.to_scale().z)
        if parent_z<.00001:raise RuntimeError('Invalid actor parent scale')
        dest.location.z-=low/parent_z
        bpy.context.view_layer.update()
    low,_=mesh_bounds()
    if abs(low)>.03:
        raise RuntimeError('Retargeted character could not be grounded in parent coordinates')
    dest['nvp_retarget_target_height_m']=target_height
    dest['nvp_retarget_scale_factor']=scale
    dest['nvp_retarget_approval_sha']=retarget['approval_sha']
    dest['nvp_retarget_ground_tolerance_m']=rb['contact_tolerance_m']
sc['nvp_retarget_approval_sha']=retarget['approval_sha']
'''


def inject_retarget_script(original,pkg):
    anchor='args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []'
    if original.count(anchor)!=1:raise RuntimeError('Unexpected Blender script anchor')
    return original.replace(anchor,'RETARGET_PAYLOAD='+repr(compact(pkg['retarget']))+'\n'+RETARGET_SCRIPT+'\n'+anchor)


RETARGET_AUDIT_SCRIPT = r'''import bpy,sys,json,math
from pathlib import Path
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
payload=json.loads(Path(opts['--package']).read_text('utf8'))
sc=bpy.context.scene
checks=[]
def check(name,okay,detail):checks.append({'name':name,'passed':bool(okay),'detail':detail})
check('director_approval',sc.get('nvp_retarget_approval_sha')==payload['retarget']['approval_sha'],'immutable receipt')
for rb in payload['retarget']['actors']:
    rid=rb['instance_id'];src=bpy.data.objects.get('NVP_RIG_'+rid)
    dest=bpy.data.objects.get('NVP_CHARACTER_RIG_'+rid)
    check('rig:'+rid,src is not None and dest is not None,rid)
    if src is None or dest is None:continue
    check('approval:'+rid,dest.get('nvp_retarget_approval_sha')==payload['retarget']['approval_sha'],rid)
    binding=next(x for x in payload['character']['bindings'] if x['instance_id']==rid)
    mapping=binding['role_map'];rest=json.loads(dest.get('nvp_retarget_rest_report','[]'))
    check('rest_data:'+rid,len(rest)==len(mapping),rest)
    meshes=[o for o in bpy.data.objects if o.type=='MESH' and o.get('nvp_character_actor')==rid]
    check('real_skinned_mesh:'+rid,bool(meshes) and any(
        m.type=='ARMATURE' and m.object==dest for mesh in meshes for m in mesh.modifiers),len(meshes))
    if not meshes:continue
    ma=next(x for x in payload['motion']['plan']['actors'] if x['instance_id']==rid)
    samples=[]
    for seg in ma['segments']:
        clip=payload['motion']['clips'][seg['clip_id']]
        for sample in clip['frames']:
            samples.append((seg['start_frame']+sample['frame']*payload['take']['fps']/clip['fps'],sample))
    motion_values=[];poses=[]
    for frame,sample in samples:
        sc.frame_set(int(frame),subframe=frame-int(frame))
        for role,other in mapping.items():
            if role not in sample['joints']:continue
            sb=src.pose.bones[role].bone;db=dest.pose.bones[other].bone
            qa=(src.matrix_world.to_quaternion()@sb.matrix_local.to_quaternion()).normalized()
            qb=(dest.matrix_world.to_quaternion()@db.matrix_local.to_quaternion()).normalized()
            align=qb.inverted()@qa
            expected=align@src.pose.bones[role].rotation_quaternion@align.inverted()
            found=dest.pose.bones[other].rotation_quaternion
            dot=abs(expected.dot(found))
            check('rest_rotation:'+rid+':'+role+':'+str(frame),dot>.999,
                  {'dot':dot,'frame':frame})
            angle=math.degrees(found.angle)
            check('joint_ceiling:'+rid+':'+role+':'+str(frame),angle<=rb['joint_limits_deg'][role]+.1,angle)
        deps=bpy.context.evaluated_depsgraph_get()
        obj=meshes[0].evaluated_get(deps);data=obj.to_mesh()
        try:
            coords=[obj.matrix_world@v.co for v in data.vertices]
            if coords:
                minimum=min(p.z for p in coords)
                poses.append((frame,minimum,[obj.matrix_world@v.co for v in data.vertices],src.parent.matrix_world.translation.copy()))
        finally:obj.to_mesh_clear()
    check('mesh_present:'+rid,len(poses)>=2,len(poses))
    if poses:
        # Test world height after proportional calibration, independently on reopen.
        base=poses[0][2]
        found_height=max(v.z for v in base)-min(v.z for v in base)
        expected_height=dest.get('nvp_retarget_target_height_m',0)
        check('proportion_height:'+rid,abs(found_height-expected_height)<.035,
              {'measured':found_height,'expected':expected_height})
        # World-space floor at scene origin: only the imported visual mesh can shift.
        bottom=min(x[1] for x in poses)
        check('floor_penetration:'+rid,bottom>=-rb['max_ground_penetration_m']-.005,bottom)
        for frame in rb['contact_frames']:
            nearest=min(poses,key=lambda x:abs(x[0]-frame))
            if abs(nearest[0]-frame)<.51:
                error=abs(nearest[1])
                check('contact:'+rid+':'+str(frame),error<=rb['contact_tolerance_m']+.005,error)
        if len(poses)>=2 and all(len(poses[0][2])==len(p[2]) for p in poses[1:]):
            # A cycle can start and end at the SAME pose. Compare all samples,
            # especially intermediate movements, minus any approved root travel.
            reference=poses[0]
            deformation=max((((v-u)-(p[3]-reference[3])).length)
                 for p in poses[1:] for u,v in zip(reference[2],p[2]))
            check('skin_deformation:'+rid,deformation>.005,deformation)
report={'format':'nvp.retarget.audit.v1','blender':bpy.app.version_string,
        'passed':all(x['passed'] for x in checks),'checks':checks}
Path(opts['--audit']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
if not report['passed']:raise RuntimeError('NVP rest-frame calibration audit failed')
if opts.get('--skip-render')!='1':
    sc.frame_set(max(1,int(sc.frame_end//2)))
    sc.render.engine='BLENDER_WORKBENCH';sc.render.filepath=opts['--render']
    sc.render.image_settings.file_format='PNG'
    sc.render.resolution_x=960;sc.render.resolution_y=540
    bpy.ops.render.render(write_still=True)
'''


def run_retarget_acceptance(service,pid,sid,directory,*,executable='blender',render_preview=True,timeout=240):
    out=Path(directory).resolve();service.export_bundle(pid,sid,out)
    blend=out/'retarget.blend';audit=out/'retarget_audit.json';preview=out/'retarget_preview.png'
    probe=blender_available(executable)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason'],'path':str(out)}
    cmds=[
        [probe['path'],'-b','--factory-startup','-t','2','--python-exit-code','30','--python',str(out/'build_retargeted.py'),'--','--output',str(blend)],
        [probe['path'],'-b',str(blend),'-t','2','--python-exit-code','30','--python',str(out/'audit_retarget.py'),
         '--','--package',str(out/'retarget.json'),'--audit',str(audit),'--render',str(preview)]
    ]
    if not render_preview:cmds[1].extend(['--skip-render','1'])
    attempts=[]
    for i,command in enumerate(cmds,1):
        try:p=run_trusted_blender(command,capture_output=True,text=True,cwd=out,timeout=timeout)
        except subprocess.TimeoutExpired:return {'status':'failed','step':i,'reason':'Blender timed out'}
        attempts.append({'step':i,'exit_code':p.returncode,'stdout':p.stdout[-1800:],'stderr':p.stderr[-2200:]})
        if p.returncode:
            failure={'status':'failed','step':i,'reason':'Native Blender retarget failed','attempts':attempts}
            if audit.is_file():
                try:failure['audit']=json.loads(audit.read_text('utf8'))
                except (OSError,ValueError):pass
            return failure
    if not blend.is_file() or not audit.is_file() or (render_preview and not preview.is_file()):
        failure={'status':'failed','reason':'Required Blender output missing','attempts':attempts}
        if audit.is_file():
            try:failure['audit']=json.loads(audit.read_text('utf8'))
            except (OSError,ValueError):pass
        return failure
    report=json.loads(audit.read_text('utf8'))
    if not report['passed']:return {'status':'failed','reason':'Calibration checks failed','audit':report}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'blend':str(blend),'audit':str(audit),'preview':str(preview) if render_preview else None,
            'checks':len(report['checks']),'version':probe['version']}
