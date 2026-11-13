"""PROD-06E2B: approved ankle-contact animation on a real Blender skeleton.

Development-only external Blender execution. Uses the *approved* eight-joint
identity and director-specified knee pole/stance windows. The native program
bakes thigh/shin rotations without touching actor-root or shot-camera keys.
An independent, separate native Blender process reopens and measures output.
"""
from __future__ import annotations

import json
import math
import subprocess
from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_foot_contact import FootLockPlan
from backend.nvp_production_scene import compact
from backend.nvp_retarget import run_retarget_acceptance

FOOTLOCK_BUILD = r'''import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector,Matrix
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts['--package']).read_text('utf8'))
planned=pkg['foot_lock']
identity=pkg['leg_identity']
sc=bpy.context.scene
if planned['format']!='nvp.footlock.approved.v1':
    raise RuntimeError('Not an approved foot-lock plan')
if planned['leg_identity_approval_sha']!=identity['approval_sha']:
    raise RuntimeError('Changed anatomical approval dependency')
if sc.get('nvp_retarget_approval_sha')!=pkg['retarget']['approval_sha']:
    raise RuntimeError('Changed approved base retarget scene')
maxframe=max(int(shot['stop_frame'])-1 for shot in pkg['take']['shots'])
if maxframe>2400:raise RuntimeError('Foot-lock frame count exceeded 2400')
def world(rig,p):return rig.matrix_world @ p
def vec(v):return Vector(v)
def finite_vec(v):
    return len(v)==3 and all(math.isfinite(float(c)) for c in v)
def solve(hip,ankle,pole,a,b):
    axis=ankle-hip
    d=axis.length
    if d<1e-7 or d>=a+b-1e-7 or d<=abs(a-b)+1e-7:
        raise RuntimeError('Refusing unreachable or straight leg contact')
    axis.normalize()
    projection=(a*a-b*b+d*d)/(2*d)
    radius=a*a-projection*projection
    if radius<=1e-14:raise RuntimeError('Cannot establish bending knee')
    perpendicular=(pole-hip)-axis*((pole-hip).dot(axis))
    if perpendicular.length<1e-7:raise RuntimeError('Knee pole is collinear')
    return hip+axis*projection+perpendicular.normalized()*math.sqrt(radius)
def align_parent(pbone,child,target):
    bpy.context.view_layer.update()
    head=pbone.head.copy()
    old=child.head.copy()-head
    desired=target-head
    if old.length<1e-6 or desired.length<1e-6:
        raise RuntimeError('Degenerate imported pose joint vector')
    if abs(old.length-desired.length)>.002:
        raise RuntimeError('Bone chain changed length before applying IK')
    turn=old.rotation_difference(desired)
    before=pbone.matrix.copy()
    pbone.matrix=Matrix.Translation(head) @ turn.to_matrix().to_4x4() @ Matrix.Translation(-head) @ before
    bpy.context.view_layer.update()
result={'format':'nvp.footlock.bake_evidence.v1',
        'approval_sha':planned['approval_sha'],
        'identity_sha':identity['approval_sha'],
        'ik_applied':True,'frames':maxframe,'actors':{}}
# The entire baseline animation is sampled before any thigh or shin keys are
# introduced; repeated scene.frame_set alone would otherwise blend new keys.
stored={}
for authored in planned['actors']:
    rid=authored['instance_id']
    rig=bpy.data.objects.get('NVP_CHARACTER_RIG_'+rid)
    actor=bpy.data.objects.get('NVP_'+rid)
    original=next(x for x in identity['actors'] if x['instance_id']==rid)
    if rig is None or rig.type!='ARMATURE' or rig.parent!=actor:
        raise RuntimeError('Approved actor armature/parent is missing')
    if rig.get('nvp_character_sha')!=original['asset_sha256']:
        raise RuntimeError('Character asset identity changed in staged Blender')
    if rig.get('nvp_retarget_approval_sha')!=pkg['retarget']['approval_sha']:
        raise RuntimeError('Actor retarget receipt missing in Blender')
    if any(name not in rig.pose.bones for side in ('left','right')
           for name in original['mapping'][side].values()):
        raise RuntimeError('Mapped anatomical bone missing from staged armature')
    entries={}
    for frame in range(1,maxframe+1):
        sc.frame_set(frame);bpy.context.view_layer.update()
        sample={}
        for side in ('left','right'):
            m=original['mapping'][side]
            bones={part:rig.pose.bones[m[part]] for part in ('hip','knee','ankle','toe')}
            if any(bones[a].parent!=bones[b] for a,b in
                   (('knee','hip'),('ankle','knee'),('toe','ankle'))):
                raise RuntimeError('Staged imported anatomy parent hierarchy differs')
            sample[side]={
                'hip':list(world(rig,bones['hip'].head)),
                'knee':list(world(rig,bones['knee'].head)),
                'ankle':list(world(rig,bones['ankle'].head)),
                'hip_quat':list(bones['hip'].rotation_quaternion),
                'knee_quat':list(bones['knee'].rotation_quaternion),
                'hip_m':float((bones['knee'].head-bones['hip'].head).length),
                'shin_m':float((bones['ankle'].head-bones['knee'].head).length)}
        entries[frame]=sample
    stored[rid]=entries
for authored in planned['actors']:
    rid=authored['instance_id'];config=authored['config']
    rig=bpy.data.objects['NVP_CHARACTER_RIG_'+rid]
    actor=bpy.data.objects['NVP_'+rid]
    m=next(x['mapping'] for x in identity['actors'] if x['instance_id']==rid)
    anchors={};lookup={}
    for side in ('left','right'):
        s=config[side]
        anchors[side]=[];lookup[side]={}
        for start,end in s['contact_windows']:
            base=stored[rid][start][side]
            ankle=vec(base['ankle']);hip=vec(base['hip']);knee=vec(base['knee'])
            if (hip-ankle).length<.001:raise RuntimeError('Degenerate native baseline leg')
            # Explicit positive pull bends a nearly-straight sample rig without
            # changing the approved root trajectory or inventing a ground height.
            target=ankle+(hip-ankle).normalized()*float(s['anchor_pull_to_hip_m'])
            pole=knee+actor.matrix_world.to_quaternion()@vec(s['pole_offset_actor_m'])
            if not finite_vec(target) or not finite_vec(pole):
                raise RuntimeError('Nonfinite actor/world target geometry')
            entry={'start':start,'end':end,'ankle_target_world_m':list(target),
                   'pole_world_m':list(pole),'source_ankle_world_m':list(ankle)}
            anchors[side].append(entry)
            for frame in range(start,end+1):
                if frame in lookup[side]:raise RuntimeError('Duplicate stance frame')
                lookup[side][frame]=entry
    # Authoring app cannot move the approved scene actor root or shot cameras.
    for frame in range(1,maxframe+1):
        sc.frame_set(frame);bpy.context.view_layer.update()
        for side in ('left','right'):
            bones={part:rig.pose.bones[m[side][part]] for part in ('hip','knee','ankle','toe')}
            saved=stored[rid][frame][side]
            bones['hip'].rotation_mode='QUATERNION'
            bones['knee'].rotation_mode='QUATERNION'
            bones['hip'].rotation_quaternion=vec(saved['hip_quat']) if False else tuple(saved['hip_quat'])
            bones['knee'].rotation_quaternion=tuple(saved['knee_quat'])
        bpy.context.view_layer.update()
        for side in ('left','right'):
            anchor=lookup[side].get(frame)
            if anchor is None:continue
            chain={part:rig.pose.bones[m[side][part]] for part in ('hip','knee','ankle')}
            hip=chain['hip'].head.copy()
            local_target=rig.matrix_world.inverted() @ vec(anchor['ankle_target_world_m'])
            local_pole=rig.matrix_world.inverted() @ vec(anchor['pole_world_m'])
            saved=stored[rid][frame][side]
            if (vec(saved['ankle'])-vec(anchor['ankle_target_world_m'])).length>config['max_ankle_correction_m']+1e-6:
                raise RuntimeError('Actor ankle correction exceeds director-approved limit')
            # Re-evaluate armature-local lengths *after* original source
            # animation and any actor/rig world scaling have been applied.
            thigh=(chain['knee'].head-chain['hip'].head).length
            shin=(chain['ankle'].head-chain['knee'].head).length
            if abs(thigh-saved['hip_m'])>.002 or abs(shin-saved['shin_m'])>.002:
                raise RuntimeError('Staged anatomical rest length changed')
            goal_knee=solve(hip,local_target,local_pole,thigh,shin)
            align_parent(chain['hip'],chain['knee'],goal_knee)
            if (chain['knee'].head-goal_knee).length>.004:
                raise RuntimeError('Upper-leg solver failed to place native knee')
            align_parent(chain['knee'],chain['ankle'],local_target)
            if (chain['ankle'].head-local_target).length>.008:
                raise RuntimeError('Lower-leg solver failed to pin native ankle')
        # Bake dense keys for contact and *noncontact* frames. Noncontact
        # frames are restored from pre-IK original quaternions above.
        for side in ('left','right'):
            for role in ('hip','knee'):
                bone=rig.pose.bones[m[side][role]]
                bone.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=bone.name)
    rig['nvp_footlock_approval_sha']=planned['approval_sha']
    rig['nvp_leg_identity_approval_sha']=identity['approval_sha']
    result['actors'][rid]={'anchors':anchors,'bone_mapping':m,
                            'config':config,'frame_count':maxframe}
sc['nvp_footlock_approval_sha']=planned['approval_sha']
sc['nvp_leg_identity_approval_sha']=identity['approval_sha']
bpy.ops.wm.save_as_mainfile(filepath=str(Path(opts['--output']).resolve()))
Path(opts['--report']).write_text(json.dumps(result,indent=2,sort_keys=True),'utf8')
'''

FOOTLOCK_AUDIT = r'''import bpy,json,sys,math,hashlib
from pathlib import Path
from mathutils import Vector
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts['--package']).read_text('utf8'))
identity=pkg['leg_identity'];planned=pkg['foot_lock']
after=opts['--mode']=='output'
bake=json.loads(Path(opts['--bake']).read_text('utf8')) if after else None
sc=bpy.context.scene
checks=[]
def check(label,passed,detail=None):
    checks.append({'check':label,'passed':bool(passed),'detail':detail})
def xyz(v):return [float(v[0]),float(v[1]),float(v[2])]
def finite(v):return all(math.isfinite(float(x)) for x in v)
def snapshot(obj):
    matrix=obj.matrix_world
    return [float(x) for row in matrix for x in row]
if after:
    check('approval_on_scene',sc.get('nvp_footlock_approval_sha')==planned['approval_sha'])
    check('anatomy_approval_on_scene',sc.get('nvp_leg_identity_approval_sha')==identity['approval_sha'])
else:
    check('approved_retarget_original',sc.get('nvp_retarget_approval_sha')==pkg['retarget']['approval_sha'])
maxframe=max(int(shot['stop_frame'])-1 for shot in pkg['take']['shots'])
result={'format':'nvp.footlock.native_audit.v1','mode':'output' if after else 'baseline',
        'blender':bpy.app.version_string,'checks':checks,
        'cut_markers':[(x.frame,x.camera.name if x.camera else None)
                       for x in sc.timeline_markers],
        'frames':{},'metrics':{}}
for n in range(1,maxframe+1):
    sc.frame_set(n);bpy.context.view_layer.update()
    result['frames'][str(n)]={'root':{},'camera':{},'legs':{}}
    for actor in planned['actors']:
        rid=actor['instance_id'];rig=bpy.data.objects['NVP_CHARACTER_RIG_'+rid]
        scene_actor=bpy.data.objects['NVP_'+rid]
        if after:
            check('foot_receipt:'+rid,rig.get('nvp_footlock_approval_sha')==planned['approval_sha'])
        check('asset:'+rid,rig.get('nvp_character_sha')==next(
              x['asset_sha256'] for x in identity['actors'] if x['instance_id']==rid))
        result['frames'][str(n)]['root'][rid]=snapshot(scene_actor)
        mapping=next(x['mapping'] for x in identity['actors'] if x['instance_id']==rid)
        legs={}
        for side in ('left','right'):
            bones={part:rig.pose.bones[mapping[side][part]] for part in ('hip','knee','ankle','toe')}
            if bones['knee'].parent!=bones['hip'] or bones['ankle'].parent!=bones['knee']:
                raise RuntimeError('Native leg chain unexpectedly changed')
            local=[bones[part].head.copy() for part in ('hip','knee','ankle','toe')]
            coords={part:xyz(rig.matrix_world@bones[part].head)
                    for part in ('hip','knee','ankle','toe')}
            coords['segment_lengths_local_m']=[(local[1]-local[0]).length,
                                                (local[2]-local[1]).length]
            coords['rotations']={part:[float(z) for z in bones[part].rotation_quaternion]
                                 for part in ('hip','knee')}
            if not all(finite(v) for v in coords.values() if isinstance(v,list)):
                raise RuntimeError('Native foot frame has nonfinite geometry')
            legs[side]=coords
        result['frames'][str(n)]['legs'][rid]=legs
    for camera in sorted((x for x in bpy.data.objects if x.type=='CAMERA'),key=lambda x:x.name):
        result['frames'][str(n)]['camera'][camera.name]={'matrix':snapshot(camera),
                    'lens_mm':float(camera.data.lens)}
    if after and bake:
        for actor in planned['actors']:
            rid=actor['instance_id'];settings=actor['config']
            for side in ('left','right'):
                for anchor in bake['actors'][rid]['anchors'][side]:
                    if anchor['start']<=n<=anchor['end']:
                        got=Vector(result['frames'][str(n)]['legs'][rid][side]['ankle'])
                        err=(got-Vector(anchor['ankle_target_world_m'])).length
                        check('ankle_pin:'+rid+':'+side+':'+str(n),
                              err<=settings['max_ankle_slide_m']+.00001,round(err,9))
result['passed']=all(x['passed'] for x in checks)
Path(opts['--audit']).write_text(json.dumps(result,indent=2,sort_keys=True),'utf8')
if not result['passed']:raise RuntimeError('Independent foot lock Blender audit rejected')
'''


def _mat_error(a,b):
    if len(a)!=len(b):return math.inf
    return max((abs(x-y) for x,y in zip(a,b)),default=0)


def independently_compare(baseline,after,bake,package):
    """Compare independent native observations on original and baked .blend."""
    if not baseline.get('passed') or not after.get('passed'):
        raise ValueError('One or more native Blender observation checks failed')
    if baseline['mode']!='baseline' or after['mode']!='output':
        raise ValueError('Wrong independent Blender observation modes')
    if baseline['cut_markers']!=after['cut_markers']:
        raise ValueError('Foot IK changed camera cuts')
    if set(baseline['frames'])!=set(after['frames']):
        raise ValueError('Frame coverage mismatch')
    peak_slide=0.0
    peak_limb_error=0.0
    changed=0.0
    for frame,ref in baseline['frames'].items():
        made=after['frames'][frame]
        if ref['camera'].keys()!=made['camera'].keys() or ref['root'].keys()!=made['root'].keys():
            raise ValueError('Foot IK changed actor or camera roster')
        for actor,mat in ref['root'].items():
            if _mat_error(mat,made['root'][actor])>1e-6:
                raise ValueError('Actor root was moved during foot IK')
        for name,camera in ref['camera'].items():
            target=made['camera'][name]
            if abs(camera['lens_mm']-target['lens_mm'])>1e-8 or _mat_error(camera['matrix'],target['matrix'])>1e-6:
                raise ValueError('Approved camera optics or pose changed')
        for actor,legs in ref['legs'].items():
            for side,measure in legs.items():
                observed=made['legs'][actor][side]
                errors=[abs(a-b) for a,b in zip(measure['segment_lengths_local_m'],
                                                observed['segment_lengths_local_m'])]
                peak_limb_error=max(peak_limb_error,*errors)
                if any(e>.001 for e in errors):
                    raise ValueError('Actual native leg bone lengths changed')
                for part in ('hip','knee'):
                    changed=max(changed,_mat_error(measure['rotations'][part],observed['rotations'][part]))
                config=next(x['config'] for x in package['foot_lock']['actors']
                            if x['instance_id']==actor)
                anchors=bake['actors'][actor]['anchors'][side]
                active=next((item for item in anchors if item['start']<=int(frame)<=item['end']),None)
                if active:
                    got=observed['ankle'];expected=active['ankle_target_world_m']
                    error=math.sqrt(sum((x-y)**2 for x,y in zip(got,expected)))
                    peak_slide=max(peak_slide,error)
                    if error>config['max_ankle_slide_m']+1e-5:
                        raise ValueError('Independently measured foot sliding exceeds approval')
                    first=baseline['frames'][str(active['start'])]['legs'][actor][side]
                    source=first['ankle'];hip=first['hip']
                    v=[h-a for h,a in zip(hip,source)]
                    norm=math.sqrt(sum(x*x for x in v))
                    pull=next(x['config'][side]['anchor_pull_to_hip_m']
                              for x in package['foot_lock']['actors'] if x['instance_id']==actor)
                    predicted=[a+(d/norm)*pull for a,d in zip(source,v)]
                    if _mat_error(predicted,expected)>1e-6:
                        raise ValueError('Foot anchor was not derived from the pristine approved scene')
                else:
                    # Outside explicit contact windows, restore original pose
                    # rather than silently contaminating other frames.
                    for part in ('hip','knee'):
                        if _mat_error(measure['rotations'][part],observed['rotations'][part])>.001:
                            raise ValueError('Non-contact animation changed without permission')
    if changed<1e-4:
        raise ValueError('No native thigh/shin pose change was actually demonstrated')
    return {'status':'passed_native_ankle_lock_only','max_ankle_slide_m':peak_slide,
            'max_segment_length_error_m':peak_limb_error,
            'max_native_quaternion_component_change':changed,
            'frame_count':len(baseline['frames']),'ik_applied':True,
            'limitations':'Ankle-marker pinning is not sole contact or realistic gait'}


def run_footlock_acceptance(service:FootLockPlan,pid,sid,directory,*,
                            executable='blender',render_preview=False,
                            baseline_blend=None,timeout=240):
    """Run actual Blender build, independent reopen audits, compare snapshots.

    base can be supplied by a verified native 06D fixture to avoid rebuilding.
    This is a developer runner, NOT the future Lu-contained production worker.
    """
    pkg=service.export(pid,sid)
    out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
    probe=blender_available(executable)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason']}
    if baseline_blend is None:
        native=run_retarget_acceptance(service.identities.retarget,pid,sid,
                                       out/'baseline',executable=executable,
                                       render_preview=render_preview,timeout=timeout)
        if not native['status'].startswith('passed_blender'):
            return {'status':'failed','stage':'baseline_retarget','details':native}
        source=Path(native['blend'])
    else:
        source=Path(baseline_blend).resolve()
    if not source.is_file():raise FileNotFoundError('Approved real source Blender scene not found')
    (out/'foot_package.json').write_text(compact(pkg),'utf8')
    (out/'apply_ankle_lock.py').write_text(FOOTLOCK_BUILD,'utf8')
    (out/'audit_ankle_lock.py').write_text(FOOTLOCK_AUDIT,'utf8')
    output=out/'ankle_locked.blend'
    artifact=out/'ankle_lock_build.json'
    before_report=out/'pristine_native_audit.json'
    after_report=out/'modified_native_audit.json'
    commands=[
        [probe['path'],'-b',str(source),'-t','2','--python-exit-code','30',
         '--python',str(out/'audit_ankle_lock.py'),'--','--mode','baseline',
         '--package',str(out/'foot_package.json'),'--audit',str(before_report)],
        [probe['path'],'-b',str(source),'-t','2','--python-exit-code','30',
         '--python',str(out/'apply_ankle_lock.py'),'--',
         '--package',str(out/'foot_package.json'),'--report',str(artifact),'--output',str(output)],
        [probe['path'],'-b',str(output),'-t','2','--python-exit-code','30',
         '--python',str(out/'audit_ankle_lock.py'),'--','--mode','output',
         '--package',str(out/'foot_package.json'),'--bake',str(artifact),
         '--audit',str(after_report)]
    ]
    logs=[]
    for number,cmd in enumerate(commands,1):
        try:p=run_trusted_blender(cmd,cwd=out,capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:
            return {'status':'failed','step':number,'reason':'Blender foot lock timed out'}
        logs.append({'step':number,'exit_code':p.returncode,'stdout':p.stdout[-2500:],
                     'stderr':p.stderr[-2600:]})
        if p.returncode:
            return {'status':'failed','step':number,'reason':'Real Blender foot IK/audit rejected',
                    'attempts':logs}
    baseline=json.loads(before_report.read_text('utf8'))
    after=json.loads(after_report.read_text('utf8'))
    bake=json.loads(artifact.read_text('utf8'))
    result=independently_compare(baseline,after,bake,pkg)
    result.update({'blender_version':probe['version'],'approved_foot_lock_sha':pkg['foot_lock']['approval_sha'],
                   'approved_leg_identity_sha':pkg['leg_identity']['approval_sha'],
                   'output_blend':str(output),'native_audit':str(after_report),
                   'pristine_audit':str(before_report),'bake':str(artifact)})
    (out/'foot_lock_result.json').write_text(json.dumps(result,indent=2,sort_keys=True),'utf8')
    return result
