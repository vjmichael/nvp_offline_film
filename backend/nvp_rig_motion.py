"""NVP-PROD-06A — creator-approved reusable BVH skeletal motion for Blender proxy rigs.

Deliberately narrow: humanoid preview armature, explicit joint mapping and local
Euler rotations; approved PROD-05 root blocking remains authoritative. Root
translation from BVH is never applied. No unknown Blender Python is executed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender

from backend.nvp_studio import Studio
from backend.nvp_production_scene import compact, digest
from backend.nvp_shot_sequence import ShotSequence, FPS
from backend.nvp_blender_acceptance import blender_available

ROLES = ('hips','spine','head','arm_left','arm_right','leg_left','leg_right')
RIG_VERSION = 'humanoid_preview_v1'
MAX_BVH_BYTES = 1_000_000
MAX_FRAMES = 2400
MAX_JOINTS = 64
MAX_ACTORS = 16
MAX_SEGMENTS = 64
LICENSE = re.compile(r'[A-Za-z0-9_.:/+ -]{1,100}\Z')
SOURCE = re.compile(r'[A-Za-z0-9_ .()\-]{1,120}\Z')
TOKEN = re.compile(r'[{}]|[^\s{}]+')


def checked_int(v,name,minimum=1,maximum=14400):
    if isinstance(v,bool) or not isinstance(v,int) or not minimum<=v<=maximum:
        raise ValueError(f'{name} must be an integer in [{minimum},{maximum}]')
    return v


def checked_text(v,name,pattern):
    if not isinstance(v,str) or not pattern.fullmatch(v):
        raise ValueError(f'Invalid {name}')
    return v


def finite_float(v,label,limit=1e6):
    try:value=float(v)
    except (TypeError,ValueError,OverflowError):raise ValueError(f'Invalid {label}') from None
    if not math.isfinite(value) or abs(value)>limit:raise ValueError(f'Out-of-range {label}')
    return value


def parse_bvh(source: str, mapping:dict[str,str]):
    """Read BVH hierarchy and rotations without silently guessing actor bone names.

    Input mapping {target_role: BVH_joint_name} is mandatory; no inferred
    mapping/rig-height conversion. BVH translation channels are ignored by
    design; approved scene blocking owns actor root movement.
    """
    if not isinstance(source,str) or not source or len(source.encode('utf-8'))>MAX_BVH_BYTES:
        raise ValueError('BVH source must be nonempty and at most 1 MiB')
    if not isinstance(mapping,dict) or not mapping or any(k not in ROLES for k in mapping):
        raise ValueError('Explicit BVH target mapping required')
    if len(set(mapping.values()))!=len(mapping) or any(not isinstance(v,str) for v in mapping.values()):
        raise ValueError('BVH source bones must be distinct')
    tokens=TOKEN.findall(source)
    if len(tokens)>320000:raise ValueError('BVH token budget exceeded')
    p=0
    channels=[]; names=set(); translations=False
    def take(expected=None):
        nonlocal p
        if p>=len(tokens):raise ValueError('Truncated BVH')
        value=tokens[p];p+=1
        if expected is not None and value!=expected:raise ValueError(f'Expected BVH token {expected}')
        return value
    def node(root=False,depth=0):
        nonlocal translations
        if depth>32 or len(names)>=MAX_JOINTS:raise ValueError('Too many BVH joints or hierarchy levels')
        take('ROOT' if root else 'JOINT')
        name=take()
        if name in names:raise ValueError('Duplicate BVH joint names')
        names.add(name);take('{');take('OFFSET')
        for _ in range(3):finite_float(take(),'BVH offset',1000)
        take('CHANNELS');count=checked_int(int(take()),'Channel count',1,6)
        entries=[take() for _ in range(count)]
        rotations=[x for x in entries if x.endswith('rotation')]
        positions=[x for x in entries if x.endswith('position')]
        if set(rotations)!={'Xrotation','Yrotation','Zrotation'} or len(rotations)!=3:
            raise ValueError('BVH requires each rotation axis once per joint')
        if positions and (not root or set(positions)!={'Xposition','Yposition','Zposition'} or len(positions)!=3):
            raise ValueError('Only BVH ROOT may have XYZ translation channels')
        if len(entries)!=len(rotations)+len(positions):raise ValueError('Unknown BVH channel')
        translations=translations or bool(positions)
        channels.append((name,entries))
        while p<len(tokens) and tokens[p] in ('JOINT','End'):
            if tokens[p]=='End':
                take('End');take('Site');take('{');take('OFFSET')
                for _ in range(3):finite_float(take(),'End offset',1000)
                take('}')
            else:node(False,depth+1)
        take('}')
    take('HIERARCHY');node(True);take('MOTION');take('Frames:')
    count=checked_int(int(take()),'BVH frames',2,MAX_FRAMES)
    take('Frame');take('Time:')
    frame_time=finite_float(take(),'BVH frame time',1)
    if not 1/120<=frame_time<=1/10:raise ValueError('BVH frame time must represent 10–120 fps')
    required=count*sum(len(c) for _,c in channels)
    if len(tokens)-p!=required:raise ValueError('BVH motion channel count mismatch')
    indices={name:(start,cols) for start,(name,cols) in
             zip([sum(len(c) for _,c in channels[:i]) for i in range(len(channels))],channels)}
    if any(source_joint not in indices for source_joint in mapping.values()):
        raise ValueError('Mapped BVH bone absent in hierarchy')
    frames=[];stride=sum(len(c) for _,c in channels)
    for fi in range(count):
        raw=[finite_float(v,'BVH frame channel',720) for v in tokens[p+fi*stride:p+(fi+1)*stride]]
        rotations={}
        for role,name in mapping.items():
            offset,cols=indices[name]
            vals={col:raw[offset+j] for j,col in enumerate(cols)}
            order=''.join(col[0] for col in cols if col.endswith('rotation'))
            rotations[role]={'euler_deg':[vals['Xrotation'],vals['Yrotation'],vals['Zrotation']], 'order':order}
        frames.append({'frame':fi,'joints':rotations})
    return {'format':'nvp.motion.clip.v1','rig':RIG_VERSION,'fps':1/frame_time,
            'frames':frames,'source_joint_mapping':mapping,
            'root_translation_ignored':translations,
            'limitations':['Joint orientation and rest-pose calibration must be reviewed manually',
                           'Source root translation is not used; blocking owns movement']}


def parse_authored(frames:list, fps:int=24):
    checked_int(fps,'Motion FPS',10,120)
    if not isinstance(frames,list) or not 2<=len(frames)<=MAX_FRAMES:
        raise ValueError('At least two bounded authored motion frames required')
    out=[];previous=-1
    for row in frames:
        if not isinstance(row,dict) or not isinstance(row.get('joints'),dict):
            raise ValueError('Motion frame must include explicit joint rotations')
        i=checked_int(row.get('frame'),'Motion frame',0,MAX_FRAMES)
        if i<=previous:raise ValueError('Motion samples must have increasing frames')
        previous=i
        angles={}
        for role,rotation in row['joints'].items():
            if role not in ROLES or not isinstance(rotation,list) or len(rotation)!=3:
                raise ValueError('Unknown role or malformed Euler rotation')
            angles[role]={'euler_deg':[finite_float(v,'joint angle',720) for v in rotation], 'order':'XYZ'}
        if not angles:raise ValueError('Motion frame cannot be empty')
        out.append({'frame':i,'joints':angles})
    if out[0]['frame']!=0:raise ValueError('Authored motion must start at frame zero')
    return {'format':'nvp.motion.clip.v1','rig':RIG_VERSION,'fps':fps,'frames':out,
            'source_joint_mapping':{},'root_translation_ignored':False,
            'limitations':['Procedural preview rig proportions are not calibrated to a performer']}


class RigMotion:
    def __init__(self, studio:Studio):
        self.studio=studio;self.seq=ShotSequence(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_motion_clips (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL, license TEXT NOT NULL, source_sha TEXT NOT NULL,
                source_kind TEXT NOT NULL, clip_json TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_motion_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL,
                take_sha TEXT NOT NULL, plan_json TEXT NOT NULL, approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_motion_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, action TEXT NOT NULL,
                plan_sha TEXT NOT NULL, PRIMARY KEY(project_id,scene_id,revision))''')

    def register(self,project_id,name,license_id,*,frames=None,bvh=None,mapping=None,fps=24):
        self.studio.get_project(project_id)
        checked_text(name,'clip name',SOURCE);checked_text(license_id,'license',LICENSE)
        if (frames is None)==(bvh is None):raise ValueError('Specify authored frames OR BVH, not both')
        clip=parse_authored(frames,fps) if frames is not None else parse_bvh(bvh,mapping)
        source_kind='authored_euler' if frames is not None else 'bvh_explicit_map'
        original=compact(frames if frames is not None else bvh)
        source_sha=hashlib.sha256(original.encode('utf8')).hexdigest()
        clip_id='MC_'+digest([project_id,name,license_id,source_sha,clip])[:24]
        with self.studio._connection() as db:
            db.execute('INSERT OR IGNORE INTO prod_motion_clips VALUES (?,?,?,?,?,?,?)',
                       (clip_id,project_id,name,license_id,source_sha,source_kind,compact(clip)))
        return {'clip_id':clip_id,'name':name,'license':license_id,'source_kind':source_kind,
                'fps':clip['fps'],'sample_count':len(clip['frames']),
                'root_translation_ignored':clip['root_translation_ignored'],'source_sha256':source_sha}

    def clips(self,project_id):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute(
                'SELECT id,name,license,source_sha,source_kind FROM prod_motion_clips WHERE project_id=? ORDER BY name,id',(project_id,))]

    def _clip(self,db,project_id,clip_id):
        row=db.execute('SELECT * FROM prod_motion_clips WHERE project_id=? AND id=?',(project_id,clip_id)).fetchone()
        if not row:raise KeyError('Project-scoped motion clip not found')
        return json.loads(row['clip_json'])

    def _context(self,project_id,scene_id):
        pkg=self.seq.export(project_id,scene_id)
        return pkg,digest(pkg['take'])

    def create(self,project_id,scene_id):
        pkg,sha=self._context(project_id,scene_id)
        actors=[{'instance_id':x['instance_id'],'rig':RIG_VERSION,'segments':[]}
                for x in pkg['take']['actors']]
        if not actors:raise ValueError('No registered characters available for rigging')
        if len(actors)>MAX_ACTORS:raise ValueError('Too many characters for preview rigging')
        plan={'format':'nvp.motion.performance.v1','actors':actors}
        with self.studio._connection() as db:
            if db.execute('SELECT 1 FROM prod_motion_sessions WHERE project_id=? AND scene_id=?',(project_id,scene_id)).fetchone():
                raise RuntimeError('Motion session already exists')
            db.execute('INSERT INTO prod_motion_sessions VALUES (?,?,?,?,?,?,?)',
                       (project_id,scene_id,0,'draft',sha,compact(plan),None))
            db.execute('INSERT INTO prod_motion_history VALUES (?,?,?,?,?)',
                       (project_id,scene_id,0,'create',digest(plan)))
        return self.read(project_id,scene_id)

    def _stored(self,db,pid,sid):
        row=db.execute('SELECT * FROM prod_motion_sessions WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone()
        if not row:raise KeyError('Motion session does not exist')
        return dict(row)

    def read(self,project_id,scene_id):
        pkg,sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:row=self._stored(db,project_id,scene_id)
        plan=json.loads(row['plan_json'])
        return {'project_id':project_id,'scene_id':scene_id,'revision':row['revision'],
                'status':row['status'],'stale':row['take_sha']!=sha,
                'actors':plan['actors'],'approval_sha':row['approval_sha'],
                'take_sha':row['take_sha'],'current_take_sha':sha,
                'end_frame':pkg['take']['shots'][-1]['stop_frame']-1}

    def _mutate(self,pid,sid,expected_revision,action,mutator):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            row=self._stored(db,pid,sid)
            if row['revision']!=expected_revision:raise RuntimeError('Stale motion revision')
            if row['status']!='draft' or row['take_sha']!=sha:
                raise RuntimeError('Motion plan is approved or underlying shot take changed')
            plan=json.loads(row['plan_json'])
            mutator(db,plan,pkg)
            nextrev=row['revision']+1
            db.execute('UPDATE prod_motion_sessions SET revision=?, plan_json=? WHERE project_id=? AND scene_id=?',
                       (nextrev,compact(plan),pid,sid))
            db.execute('INSERT INTO prod_motion_history VALUES (?,?,?,?,?)',
                       (pid,sid,nextrev,action,digest(plan)))
        return self.read(pid,sid)

    def attach(self,pid,sid,actor_id,clip_id,start_frame,expected_revision):
        checked_int(start_frame,'Motion start frame')
        def mutator(db,plan,pkg):
            actor=next((a for a in plan['actors'] if a['instance_id']==actor_id),None)
            if actor is None:raise KeyError('Actor not present in approved shot take')
            clip=self._clip(db,pid,clip_id)
            duration=math.ceil((clip['frames'][-1]['frame']/clip['fps'])*FPS)
            end=start_frame+duration
            if end>pkg['take']['shots'][-1]['stop_frame']:
                raise ValueError('Motion clip exceeds approved take')
            if any(not (end<=x['start_frame'] or start_frame>=x['stop_frame']) for x in actor['segments']):
                raise ValueError('Motion clips overlap for actor')
            if sum(len(a['segments']) for a in plan['actors'])>=MAX_SEGMENTS:raise ValueError('Motion segment budget exceeded')
            actor['segments'].append({'clip_id':clip_id,'start_frame':start_frame,'stop_frame':end})
            actor['segments'].sort(key=lambda x:x['start_frame'])
        return self._mutate(pid,sid,expected_revision,'attach',mutator)

    def clear(self,pid,sid,actor_id,expected_revision):
        def mutator(db,plan,pkg):
            actor=next((a for a in plan['actors'] if a['instance_id']==actor_id),None)
            if actor is None:raise KeyError('Actor missing')
            actor['segments']=[]
        return self._mutate(pid,sid,expected_revision,'clear_actor',mutator)

    def approve(self,pid,sid,expected_revision):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            row=self._stored(db,pid,sid)
            if row['revision']!=expected_revision or row['take_sha']!=sha or row['status']!='draft':
                raise RuntimeError('Motion approval rejected: changed or stale')
            plan=json.loads(row['plan_json'])
            if not any(a['segments'] for a in plan['actors']):raise ValueError('No motion segments to approve')
            for actor in plan['actors']:
                for seg in actor['segments']:self._clip(db,pid,seg['clip_id'])
            receipt=digest([plan,sha])
            db.execute('UPDATE prod_motion_sessions SET status=?, approval_sha=? WHERE project_id=? AND scene_id=?',
                       ('approved',receipt,pid,sid))
            db.execute('INSERT INTO prod_motion_history VALUES (?,?,?,?,?)',
                       (pid,sid,row['revision']+1,'approve',receipt))
        return self.read(pid,sid)

    def history(self,pid,sid):
        self.studio.get_project(pid)
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute(
                'SELECT * FROM prod_motion_history WHERE project_id=? AND scene_id=? ORDER BY revision',(pid,sid))]

    def export(self,pid,sid):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            row=self._stored(db,pid,sid)
            if row['status']!='approved' or row['take_sha']!=sha:raise RuntimeError('Motion is not approved/current')
            plan=json.loads(row['plan_json']);clips={}
            for actor in plan['actors']:
                for seg in actor['segments']:
                    clip=self._clip(db,pid,seg['clip_id']);clips[seg['clip_id']]=clip
        if row['approval_sha']!=digest([plan,sha]):raise RuntimeError('Motion approval mismatch')
        return {'manifest':pkg['manifest'],'take':pkg['take'],
                'motion':{'format':'nvp.production.rig_motion.v1',
                    'rig':RIG_VERSION,'plan':plan,'clips':clips,
                    'approval_sha':row['approval_sha'],'take_sha':sha}}

    def blender_script(self,pid,sid):
        from backend.nvp_shot_sequence import animated_blender_script
        pkg=self.export(pid,sid)
        return inject_rig_script(animated_blender_script(pkg['manifest'],pkg['take']),pkg['motion'],pkg['take'])


# Blender procedural rig uses a real ARMATURE with pose-bone quaternion keys.
# It does NOT infer source translations or claim retarget calibration.
RIG_SCRIPT=r'''# NVP-PROD-06A: safe, bounded humanoid skeleton with audited joint motion.
from mathutils import Euler
motion=json.loads(MOTION_PAYLOAD)
assert motion['format']=='nvp.production.rig_motion.v1'
for binding in motion['plan']['actors']:
    if not binding['segments']:continue
    actor_id=binding['instance_id']
    parent=bpy.data.objects['NVP_'+actor_id]
    height=float(next(x['height_m'] for x in take['actors'] if x['instance_id']==actor_id))
    arm=bpy.data.armatures.new('NVP_HUMANOID_'+actor_id)
    rig=bpy.data.objects.new('NVP_RIG_'+actor_id,arm)
    bpy.context.collection.objects.link(rig)
    rig.parent=parent
    rig.location=(0,0,-height/2)
    rig['nvp_rig_kind']='humanoid_preview_v1'
    rig['nvp_actor_id']=actor_id
    bpy.context.view_layer.objects.active=rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    specs={
        'hips':((0,0,.45),(0,0,.55),None),
        'spine':((0,0,.55),(0,0,.80),'hips'),
        'head':((0,0,.80),(0,0,.96),'spine'),
        'arm_left':((0,0,.77),(.33,0,.57),'spine'),
        'arm_right':((0,0,.77),(-.33,0,.57),'spine'),
        'leg_left':((.09,0,.46),(.09,0,.05),'hips'),
        'leg_right':((-.09,0,.46),(-.09,0,.05),'hips'),
    }
    for name,(start,end,par) in specs.items():
        bone=arm.edit_bones.new(name)
        bone.head=[float(v)*height for v in start]
        bone.tail=[float(v)*height for v in end]
        if par:bone.parent=arm.edit_bones[par]
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.select_set(False)
    for segment in binding['segments']:
        clip=motion['clips'][segment['clip_id']]
        for sample in clip['frames']:
            frame=segment['start_frame']+sample['frame']*take['fps']/clip['fps']
            for role,datum in sample['joints'].items():
                pose=rig.pose.bones[role]
                pose.rotation_mode='QUATERNION'
                xyz=[math.radians(float(v)) for v in datum['euler_deg']]
                pose.rotation_quaternion=Euler(xyz,datum['order']).to_quaternion()
                pose.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=role)
        rig['nvp_clip_'+segment['clip_id']]=segment['start_frame']
sc['nvp_motion_approval_sha']=motion['approval_sha']
'''


def inject_rig_script(base,motion,take):
    anchor='args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []'
    if base.count(anchor)!=1:raise RuntimeError('Unexpected base Blender generator')
    src='MOTION_PAYLOAD='+repr(compact(motion))+'\n'+RIG_SCRIPT
    return base.replace(anchor,src+'\n'+anchor)


MOTION_AUDIT_SCRIPT=r'''import bpy, json, math, sys
from mathutils import Euler
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(args[::2],args[1::2]))
payload=json.loads(Path(opts['--motion']).read_text('utf8'))
sc=bpy.context.scene
checks=[]
def check(name,ok,detail):checks.append({'check':name,'passed':bool(ok),'evidence':detail})
check('fps24',sc.render.fps==24,sc.render.fps)
check('camera_cut_markers',len([m for m in sc.timeline_markers if m.name.startswith('CUT_')])>0,'camera timeline')
check('approval_digest',sc.get('nvp_motion_approval_sha')==payload['approval_sha'],'approval')
for binding in payload['plan']['actors']:
    if not binding['segments']:continue
    rid=binding['instance_id']; rig=bpy.data.objects.get('NVP_RIG_'+rid)
    check('armature:'+rid,rig is not None and rig.type=='ARMATURE',rid)
    if rig is None:continue
    check('rig_identity:'+rid,rig.get('nvp_actor_id')==rid and rig.parent.name=='NVP_'+rid,rid)
    check('bone_count:'+rid,len(rig.pose.bones)==7,len(rig.pose.bones))
    for segment in binding['segments']:
        clip=payload['clips'][segment['clip_id']]
        for sample in (clip['frames'][0],clip['frames'][-1]):
            frame=segment['start_frame']+sample['frame']*24/clip['fps']
            sc.frame_set(int(frame),subframe=frame-int(frame))
            for role,datum in sample['joints'].items():
                actual=rig.pose.bones[role].rotation_quaternion
                expected=Euler([math.radians(float(v)) for v in datum['euler_deg']],datum['order']).to_quaternion()
                error=abs(abs(actual.dot(expected))-1.)
                check('pose:'+rid+':'+role+':'+str(frame),error<.0005,{'quaternion_error':error})
report={'format':'nvp.motion.blender.audit.v1','passed':all(x['passed'] for x in checks),
        'checks':checks,'blender':bpy.app.version_string}
Path(opts['--audit']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
if not report['passed']:raise RuntimeError('Motion rig native audit failed')
if opts.get('--skip-render')!='1':
    sc.frame_set(max(1,int(sc.frame_end/2)))
    sc.render.engine='BLENDER_WORKBENCH'
    sc.render.filepath=opts['--preview']
    sc.render.image_settings.file_format='PNG'
    sc.render.resolution_x=640;sc.render.resolution_y=360;sc.render.resolution_percentage=100
    bpy.ops.render.render(write_still=True)
'''


def run_motion_acceptance(service,pid,sid,directory,*,executable='blender',render_preview=True,timeout=180):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    pkg=service.export(pid,sid)
    paths={'script':root/'build_motion.py','motion':root/'motion.json',
           'audit_script':root/'audit_motion.py','blend':root/'motion.blend',
           'audit':root/'motion_audit.json','preview':root/'motion_preview.png'}
    paths['script'].write_text(service.blender_script(pid,sid),'utf8')
    paths['motion'].write_text(compact(pkg['motion']),'utf8')
    paths['audit_script'].write_text(MOTION_AUDIT_SCRIPT,'utf8')
    probe=blender_available(executable)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason'],'script':str(paths['script'])}
    cmds=[
        [probe['path'],'-b','--factory-startup','-t','2','--python',str(paths['script']),'--','--output',str(paths['blend'])],
        [probe['path'],'-b',str(paths['blend']),'-t','2','--python',str(paths['audit_script']),'--',
         '--motion',str(paths['motion']),'--audit',str(paths['audit']),'--preview',str(paths['preview'])]
    ]
    if not render_preview:cmds[1].extend(['--skip-render','1'])
    logs=[]
    for cmd in cmds:
        try:p=run_trusted_blender(cmd,capture_output=True,text=True,cwd=root,timeout=timeout)
        except subprocess.TimeoutExpired:return {'status':'failed','reason':'Blender timed out','step':len(logs)+1}
        logs.append({'exit_code':p.returncode,'stdout_tail':p.stdout[-1500:],'stderr_tail':p.stderr[-2000:]})
        if p.returncode:return {'status':'failed','reason':'Native Blender build/audit failed','steps':logs}
    if not paths['blend'].is_file() or not paths['audit'].is_file() or (render_preview and not paths['preview'].is_file()):
        return {'status':'failed','reason':'Native Blender output missing','steps':logs}
    report=json.loads(paths['audit'].read_text('utf8'))
    if not report['passed']:return {'status':'failed','reason':'Rig/bone audit disagreed','report':report}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'checks':len(report['checks']),'blend':str(paths['blend']),
            'preview':str(paths['preview']) if render_preview else None,'audit':str(paths['audit']),
            'version':probe['version']}
