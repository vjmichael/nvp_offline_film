"""PROD-06E2C1: read-only candidate sole geometry audit on a real skinned human.

Bone-weighted vertices are *candidate regions*, not medically/anatomically
certified shoe soles. This rejects absent/ambiguous bilateral region weights,
tracks evaluated mesh geometry across contact frames, and quantifies ground
clearance without changing the approved IK animation or floor.
"""
from __future__ import annotations

import json
import math
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_foot_contact import FootLockPlan
from backend.nvp_production_scene import compact, digest

MAX_FRAMES = 2400
MAX_REGIONS = 16
MAX_VERTICES = 250000

SOLE_REGION_SCRIPT = r'''import bpy,sys,json,math
from pathlib import Path
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts['--package']).read_text('utf8'))
sc=bpy.context.scene
identity=pkg['leg_identity']; lock=pkg['foot_lock']
if lock['leg_identity_approval_sha']!=identity['approval_sha']:
    raise RuntimeError('Stale anatomical approval for sole region survey')
if sc.get('nvp_footlock_approval_sha')!=lock['approval_sha']:
    raise RuntimeError('Opening unapproved foot-lock scene')
if sc.get('nvp_leg_identity_approval_sha')!=identity['approval_sha']:
    raise RuntimeError('Opening incorrect anatomical rig identity')
result={'format':'nvp.sole_region.native_observation.v1',
        'foot_lock_sha':lock['approval_sha'],
        'leg_identity_sha':identity['approval_sha'],
        'blender_version':bpy.app.version_string,
        'actors':{}}
for author in lock['actors']:
    rid=author['instance_id']
    rig=bpy.data.objects.get('NVP_CHARACTER_RIG_'+rid)
    approved=next(a for a in identity['actors'] if a['instance_id']==rid)
    if rig is None or rig.get('nvp_character_sha')!=approved['asset_sha256']:
        raise RuntimeError('Foot source asset mismatch')
    meshes=[o for o in bpy.data.objects if o.type=='MESH' and o.get('nvp_character_actor')==rid
            and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    if not meshes or len(meshes)>16:raise RuntimeError('Missing or oversized approved skinned mesh set')
    members={side:[] for side in ('left','right')}
    for obj in meshes:
        if len(obj.data.vertices)>250000:raise RuntimeError('Unsafe geometry for sole survey')
        for side in ('left','right'):
            names={approved['mapping'][side]['ankle'],approved['mapping'][side]['toe']}
            groups={v.index for v in obj.vertex_groups if v.name in names}
            if len(groups)!=2:
                raise RuntimeError('Need both explicit ankle and toe deform groups for '+side)
            indices=[]
            for vertex in obj.data.vertices:
                total=sum(group.weight for group in vertex.groups if group.group in groups)
                if total>=.25:indices.append(vertex.index)
            if indices:members[side].append((obj,indices))
    if not members['left'] or not members['right']:
        raise RuntimeError('Missing separately weighted sole-region candidates')
    frames=sorted(set(n for side in ('left','right')
                for start,end in author['config'][side]['contact_windows']
                for n in range(start,end+1)))
    if len(frames)>2400 or not frames:raise RuntimeError('Unbounded or missing contact windows')
    observations=[]
    for frame in frames:
        sc.frame_set(frame);bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        state={'frame':frame,'regions':{}}
        for side in ('left','right'):
            count=0;minimum=1e100;maxz=-1e100;point=None
            for obj,indices in members[side]:
                ev=obj.evaluated_get(deps);mesh=ev.to_mesh()
                try:
                    if len(mesh.vertices)!=len(obj.data.vertices):
                        raise RuntimeError('Evaluated skinned topology changed')
                    for index in indices:
                        pos=ev.matrix_world@mesh.vertices[index].co
                        count+=1
                        if pos.z<minimum:
                            minimum=float(pos.z);point=[float(x) for x in pos]
                        maxz=max(maxz,float(pos.z))
                finally:ev.to_mesh_clear()
            if count<3 or not math.isfinite(minimum) or not all(math.isfinite(x) for x in point):
                raise RuntimeError('Invalid or too sparse '+side+' candidate vertices')
            state['regions'][side]={'candidate_vertices':count,
                                    'minimum_z_m':minimum,'maximum_z_m':maxz,
                                    'minimum_world_m':point}
        observations.append(state)
    result['actors'][rid]={
        'asset_sha256':approved['asset_sha256'],
        'contact_frames':frames,'observations':observations,
        'note':'Bone-weight candidates, not an approved plantar sole mask'}
Path(opts['--output']).write_text(json.dumps(result,sort_keys=True,indent=2),'utf8')
'''


def analyze_region_observation(report, package, *, ground_z_m=0.0):
    """Independent host validation and contact-frame residual summaries."""
    if type(ground_z_m) not in (int,float) or not math.isfinite(ground_z_m):
        raise ValueError('Ground Z must be numeric/finite')
    if type(report) is not dict or report.get('format')!='nvp.sole_region.native_observation.v1':
        raise ValueError('Native sole observation format mismatch')
    if report.get('foot_lock_sha')!=package['foot_lock']['approval_sha'] or report.get('leg_identity_sha')!=package['leg_identity']['approval_sha']:
        raise ValueError('Sole region report approval mismatch')
    approved={a['instance_id']:a for a in package['leg_identity']['actors']}
    authors={a['instance_id']:a for a in package['foot_lock']['actors']}
    observed=report.get('actors')
    if type(observed) is not dict or set(observed)!=set(approved) or set(observed)!=set(authors):
        raise ValueError('Sole region actor mismatch')
    summary={}
    for rid,r in observed.items():
        if type(r) is not dict or r.get('asset_sha256')!=approved[rid]['asset_sha256']:
            raise ValueError('Sole-region character identity mismatch')
        expected=sorted(set(n for s in ('left','right')
                 for a,b in authors[rid]['config'][s]['contact_windows']
                 for n in range(a,b+1)))
        frames=r.get('contact_frames'); samples=r.get('observations')
        if frames!=expected or not isinstance(samples,list) or len(samples)!=len(frames):
            raise ValueError('Sole survey frame set does not match approved contact windows')
        side_results={}
        for side in ('left','right'):
            in_contact={n for a,b in authors[rid]['config'][side]['contact_windows'] for n in range(a,b+1)}
            lows=[];xy=[]
            for item,frame in zip(samples,frames):
                if type(item) is not dict or item.get('frame')!=frame:
                    raise ValueError('Sole observations not frame aligned')
                regions=item.get('regions')
                if type(regions) is not dict or set(regions)!= {'left','right'}:
                    raise ValueError('Sole observations must include both feet')
                candidate=regions[side]
                n=candidate.get('candidate_vertices')
                if type(n) is not int or not 3<=n<=MAX_VERTICES:
                    raise ValueError('Bad semantic foot candidate population')
                pos=candidate.get('minimum_world_m')
                if not isinstance(pos,list) or len(pos)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in pos):
                    raise ValueError('Invalid real evaluated sole point')
                low=candidate.get('minimum_z_m')
                high=candidate.get('maximum_z_m')
                if type(low) not in (int,float) or type(high) not in (int,float) or not math.isfinite(low) or not math.isfinite(high) or high<low or abs(pos[2]-low)>1e-5:
                    raise ValueError('Measured foot minimum inconsistent')
                if frame in in_contact:
                    lows.append(low-ground_z_m)
                    xy.append(pos[:2])
            if not lows:raise ValueError('Missing side-specific contact observations')
            # Important: these are observed residuals, not 'passed' contact.
            slide=max(math.dist(xy[i],xy[0]) for i in range(len(xy)))
            side_results[side]={'contact_frames':len(lows),
                                'min_clearance_m':min(lows),
                                'max_clearance_m':max(lows),
                                'max_candidate_minimum_xy_shift_m':slide,
                                'sole_physically_verified':False}
        summary[rid]=side_results
    return {'format':'nvp.sole_region.candidate_report.v1',
            'report_sha':digest(report),'actors':summary,
            'foot_lock_sha':package['foot_lock']['approval_sha'],
            'ground_z_m':ground_z_m,'physical_sole_contact_verified':False,
            'limitations':'Evaluated ankle+toe-weighted skinned vertices are candidate foot region only; no artist-approved plantar mask/ground collision model'}


def run_native_sole_region(service:FootLockPlan,pid,sid,approved_blend,directory,
                           *,blender='blender',ground_z_m=0.0,timeout=240):
    package=service.export(pid,sid)
    probe=blender_available(blender)
    if not probe['available']:return {'status':'blocked_no_blender','reason':probe['reason']}
    approved_blend=Path(approved_blend).resolve()
    if not approved_blend.is_file() or approved_blend.suffix.lower()!='.blend':
        raise ValueError('A completed approved ankle-lock .blend is required')
    out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
    script=out/'survey_sole_region.py';script.write_text(SOLE_REGION_SCRIPT,'utf8')
    manifest=out/'sole_package.json';manifest.write_text(compact(package),'utf8')
    observation=out/'sole_region_observation.json';observation.unlink(missing_ok=True)
    command=[probe['path'],'-b',str(approved_blend),'-t','2','--python-exit-code','30',
             '--python',str(script),'--','--package',str(manifest),'--output',str(observation)]
    try:run=run_owned_subprocess(command,cwd=out,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:return {'status':'failed','reason':'Native sole-region survey timed out'}
    if run.returncode or not observation.is_file():
        return {'status':'failed','reason':'Native sole-region survey refused',
                'exit_code':run.returncode,'stderr':run.stderr[-2800:],
                'stdout':run.stdout[-1800:]}
    raw=json.loads(observation.read_text('utf8'))
    report=analyze_region_observation(raw,package,ground_z_m=ground_z_m)
    (out/'sole_region_report.json').write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
    return {'status':'passed_candidate_region_survey_only',
            'report':report,'directory':str(out),'physical_sole_contact_verified':False}
