"""PROD-06E2B1: read-only staged-pose measurements after 06D calibration.

This survey opens an *actual retargeted .blend* and measures pose bone heads
in WORLD SPACE, including actor parenting/height adaptation and animation.
No IK / contacts are applied. The independent result validator refuses source
mismatches, degenerate lengths, hierarchy drift and out-of-take frames.
"""
from __future__ import annotations
import json
import math
import subprocess
from pathlib import Path
from backend.nvp_blender_acceptance import blender_available
from backend.nvp_leg_chains import LegChainIdentity, LEGS, PARTS, _vec, _dist, MAX_BONES
from backend.nvp_production_scene import compact, digest


STAGED_POSE_SURVEY_SCRIPT = r'''import bpy,json,sys,math
from pathlib import Path
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
payload=json.loads(Path(opts['--manifest']).read_text('utf8'))
sc=bpy.context.scene
if payload['leg_identity']['format']!='nvp.legchain.approved_identity.v1':
    raise RuntimeError('Missing approved imported bone identity')
if sc.get('nvp_retarget_approval_sha')!=payload['retarget']['approval_sha']:
    raise RuntimeError('Opened rig does not belong to approved retarget')
frames=payload['survey_frames']
if not frames or len(frames)>2400:
    raise RuntimeError('Invalid frame survey')
report={'format':'nvp.staged_pose.observation.v1',
        'leg_approval_sha':payload['leg_identity']['approval_sha'],
        'retarget_approval_sha':payload['retarget']['approval_sha'],
        'blender_version':bpy.app.version_string,
        'frames':frames,'actors':{}}
for record in payload['leg_identity']['actors']:
    rid=record['instance_id']
    rig=bpy.data.objects.get('NVP_CHARACTER_RIG_'+rid)
    if rig is None or rig.type!='ARMATURE' or rig.get('nvp_character_sha')!=record['asset_sha256']:
        raise RuntimeError('Staged character rig identity mismatch')
    if rig.get('nvp_retarget_approval_sha')!=payload['retarget']['approval_sha']:
        raise RuntimeError('Staged rig retarget approval mismatch')
    series=[]
    for frame in frames:
        sc.frame_set(frame);bpy.context.view_layer.update()
        legs={}
        for side,chain in record['mapping'].items():
            joints={}
            for part,name in chain.items():
                bone=rig.pose.bones.get(name)
                if bone is None:raise RuntimeError('Approved bone missing in staged rig')
                position=rig.matrix_world@bone.head
                joints[part]=[float(c) for c in position]
            legs[side]=joints
        series.append({'frame':frame,'legs':legs,
                       'actor_root_world_m':[float(c) for c in rig.parent.matrix_world.translation],
                       'rig_world_scale':[float(c) for c in rig.matrix_world.to_scale()]})
    report['actors'][rid]={'asset_sha256':record['asset_sha256'],'samples':series}
Path(opts['--output']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
'''


def analyze_staged_pose(report,package):
    if (type(report) is not dict or report.get('format')!='nvp.staged_pose.observation.v1'
        or report.get('leg_approval_sha')!=package['leg_identity']['approval_sha']
        or report.get('retarget_approval_sha')!=package['retarget']['approval_sha']):
        raise ValueError('Staged observation does not match approved identity and retarget')
    first=min(x['start_frame'] for x in package['take']['shots'])
    last=max(x['stop_frame']-1 for x in package['take']['shots'])
    frames=report.get('frames')
    if type(frames) is not list or not 1<=len(frames)<=2400 or any(type(n) is not int for n in frames):
        raise ValueError('Staged frame list invalid')
    if frames!=sorted(set(frames)) or any(not first<=n<=last for n in frames):
        raise ValueError('Staged frames outside approved take or unsorted')
    actors=report.get('actors')
    approved=package['leg_identity']['actors']
    if type(actors) is not dict or set(actors)!={a['instance_id'] for a in approved}:
        raise ValueError('Staged actor roster mismatch')
    results={}
    for a in approved:
        rid=a['instance_id'];raw=actors[rid]
        if type(raw) is not dict or raw.get('asset_sha256')!=a['asset_sha256']:
            raise ValueError('Staged actor asset identity changed')
        samples=raw.get('samples')
        if not isinstance(samples,list) or len(samples)!=len(frames):
            raise ValueError('Missing staged frame samples')
        measurements=[]
        for sample,frame in zip(samples,frames):
            if type(sample) is not dict or sample.get('frame')!=frame:
                raise ValueError('Staged samples not aligned to approved frames')
            _vec(sample.get('actor_root_world_m'),'root')
            scale=_vec(sample.get('rig_world_scale'),'scale')
            if any(v<.001 or v>100 for v in scale):
                raise ValueError('Staged rig scale invalid')
            legs=sample.get('legs')
            if type(legs) is not dict or set(legs)!=set(LEGS):
                raise ValueError('Staged observations missing one side')
            limbs={}
            for side in LEGS:
                bones=legs[side]
                if type(bones) is not dict or set(bones)!=set(PARTS):
                    raise ValueError('Staged bone positions incomplete')
                pts={k:_vec(v,'bone head') for k,v in bones.items()}
                upper=_dist(pts['hip'],pts['knee'])
                lower=_dist(pts['knee'],pts['ankle'])
                foot=_dist(pts['ankle'],pts['toe'])
                if not (.01<=upper<=5 and .01<=lower<=5 and .005<=foot<=3):
                    raise ValueError('Staged limb geometry degenerate')
                limbs[side]={'upper_m':upper,'lower_m':lower,'ankle_to_toe_m':foot,
                             'hip_world_m':list(pts['hip']),
                             'knee_world_m':list(pts['knee']),
                             'ankle_world_m':list(pts['ankle']),
                             'toe_world_m':list(pts['toe'])}
            measurements.append({'frame':frame,'legs':limbs,
                                 'actor_root_world_m':sample['actor_root_world_m'],
                                 'rig_world_scale':sample['rig_world_scale']})
        results[rid]=measurements
    return {'format':'nvp.staged_pose.validated.v1','source_sha':digest(report),
            'leg_approval_sha':package['leg_identity']['approval_sha'],
            'retarget_approval_sha':package['retarget']['approval_sha'],
            'blender_version':report.get('blender_version','unreported'),
            'actors':results,'ik_applied':False,
            'limitations':'Staged 3D world-space rest/motion observations only; contacts not enforced'}


def survey_native_staged_pose(service:LegChainIdentity,pid,sid,blend,directory,
                              *,frames=None,blender='blender',timeout=180):
    package=service.export(pid,sid)
    first=min(x['start_frame'] for x in package['take']['shots'])
    last=max(x['stop_frame']-1 for x in package['take']['shots'])
    if frames is None:
        frames=sorted({first,(first+last)//2,last})
    if (not isinstance(frames,list) or not frames or len(frames)>2400 or
        any(type(f) is not int for f in frames) or frames!=sorted(set(frames)) or
        any(not first<=f<=last for f in frames)):
        raise ValueError('Native pose survey frames invalid')
    probe=blender_available(blender)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason']}
    blend=Path(blend).resolve()
    if not blend.is_file() or blend.suffix.lower()!='.blend':
        raise ValueError('Expected actual saved retargeted Blender stage')
    out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
    script=out/'survey_staged_pose.py';script.write_text(STAGED_POSE_SURVEY_SCRIPT,'utf8')
    manifest=out/'survey_source.json'
    manifest.write_text(compact({**package,'survey_frames':frames}),'utf8')
    report=out/'staged_pose_observation.json';report.unlink(missing_ok=True)
    cmd=[probe['path'],'-b',str(blend),'-t','2','--python-exit-code','30',
         '--python',str(script),'--','--manifest',str(manifest),'--output',str(report)]
    try:result=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'status':'failed','reason':'Blender staged pose observation timed out'}
    if result.returncode or not report.is_file():
        return {'status':'failed','reason':'Staged Blender pose observation failed',
                'returncode':result.returncode,'stderr':result.stderr[-2000:],
                'stdout':result.stdout[-1500:]}
    reviewed=analyze_staged_pose(json.loads(report.read_text('utf8')),package)
    (out/'staged_pose_validated.json').write_text(json.dumps(reviewed,indent=2,sort_keys=True),'utf8')
    return {'status':'passed_staged_pose_observation_only','result':reviewed,
            'report_path':str(out),'ik_applied':False}
