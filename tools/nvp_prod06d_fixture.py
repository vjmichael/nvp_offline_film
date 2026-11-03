"""PROD-06D external human acceptance. No bundled third-party model.

The caller supplies the upstream Cesium Man GLB from Khronos sample assets.
Original animation is discarded in a *trusted* Blender normalization step so
production uses only a director-approved NVP motion clip. The source stays
unchanged and is separately attributed; the derived GLB is a test artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_skinning import SkinnedPerformance
from backend.nvp_character_assets import CharacterAssets
from backend.nvp_retarget import RetargetCalibration,run_retarget_acceptance
from tests.test_skinning import make_fixture

# Pin to official Khronos glTF-Sample-Assets commit and specific Git blob SHA1.
UPSTREAM_COMMIT = '8f492390ddc7a2ae221a1369ef560589cf8c70fb'
UPSTREAM_GIT_BLOB = '8586c4e6a59bf8ef585c2a685c50a80d28503216'
UPSTREAM_URL = ('https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/'
                + UPSTREAM_COMMIT + '/Models/CesiumMan/glTF-Binary/CesiumMan.glb')
UPSTREAM_LICENSE = 'CC-BY-4.0'
UPSTREAM_CREDIT = 'Cesium (2017), Cesium Man; CC BY 4.0; source contains a Cesium logo/trademark'


def verify_upstream(data: bytes):
    if not isinstance(data,bytes) or len(data)>32*1024*1024:
        raise ValueError('External test source must be a bounded downloaded binary')
    sha=hashlib.sha1(b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()
    if sha!=UPSTREAM_GIT_BLOB:
        raise ValueError('Downloaded external model differs from pinned official git blob')
    return {'source_git_blob_sha1':sha,'source_sha256':hashlib.sha256(data).hexdigest(),
            'license':UPSTREAM_LICENSE,'attribution':UPSTREAM_CREDIT,'upstream':UPSTREAM_URL,
            'notice':'For engineering acceptance only. Do not distribute the trademark/logo as NVP branding.'}


NORMALIZE_GLTF = r'''# Trusted Blender-only normalization of pre-existing sample data.
import bpy,sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
source=Path(args[args.index('--source')+1]).resolve()
output=Path(args[args.index('--output')+1]).resolve()
bpy.ops.import_scene.gltf(filepath=str(source))
rigs=[o for o in bpy.data.objects if o.type=='ARMATURE']
if len(rigs)!=1:raise RuntimeError('Expected exactly one imported Cesium Man armature')
rig=rigs[0]
meshes=[o for o in bpy.data.objects if o.type=='MESH' and
    any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
if not meshes:raise RuntimeError('Reference GLB lacks skinned character mesh')
# Do not grant upstream animation authority. Export only neutral geometry/rig.
for obj in bpy.data.objects:
    obj.animation_data_clear()
for action in list(bpy.data.actions):bpy.data.actions.remove(action)
for pb in rig.pose.bones:
    pb.rotation_mode='QUATERNION';pb.rotation_quaternion=(1,0,0,0)
bpy.context.scene.frame_set(1)
bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
for mesh in meshes:mesh.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',
                          use_selection=True,export_animations=False,
                          export_skins=True,export_yup=True)
if not output.is_file() or output.stat().st_size<128:
    raise RuntimeError('Missing normalized real skinned GLB')
'''

# This mapping is specific to Cesium's named external skeleton. No fuzzy
# inference, no live application auto-map and no silent fallback are allowed.
CESIUM_ROLE_MAP = {
    'hips':'Skeleton_torso_joint_1',
    'spine':'Skeleton_torso_joint_2',
    'head':'Skeleton_neck_joint_2',
    'arm_left':'Skeleton_arm_joint_L__4_',
    'arm_right':'Skeleton_arm_joint_R',
    'leg_left':'leg_joint_L_1',
    'leg_right':'leg_joint_R_1',
}


def build_external_fixture(output:Path,glb_path:Path,*,render_preview=True,blender='blender'):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    glb_path=Path(glb_path).resolve()
    if not glb_path.is_file():
        return {'status':'blocked_external_asset_missing','expected':str(glb_path)}
    source=glb_path.read_bytes()
    provenance=verify_upstream(source)
    (output/'external_source_provenance.json').write_text(json.dumps(provenance,indent=2),'utf8')
    probe=blender_available(blender)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason']}
    norm=output/'normalize.py';norm.write_text(NORMALIZE_GLTF,'utf8')
    asset=output/'cesiumman_skeleton_only.glb'
    command=[probe['path'],'-b','--factory-startup','-t','2','--python',str(norm),
             '--','--source',str(glb_path),'--output',str(asset)]
    try:proc=subprocess.run(command,cwd=output,capture_output=True,text=True,timeout=180)
    except subprocess.TimeoutExpired:return {'status':'failed','step':'normalize','reason':'Blender timeout'}
    if proc.returncode or not asset.is_file():
        return {'status':'failed','step':'normalize','stdout':proc.stdout[-2200:],
                'stderr':proc.stderr[-2200:]}
    studio,pid,sid,actor=make_fixture(output/'project')
    skin=SkinnedPerformance(studio)
    s=skin.create(pid,sid);skin.approve(pid,sid,s['revision'])
    characters=CharacterAssets(studio)
    imported=characters.register(pid,asset.read_bytes(),UPSTREAM_LICENSE,
                                 attribution=UPSTREAM_CREDIT,source=UPSTREAM_URL)
    missing={role:name for role,name in CESIUM_ROLE_MAP.items() if name not in imported['joint_names']}
    if missing:
        return {'status':'failed','step':'manual_role_map','missing':missing,
                'available_joint_names':imported['joint_names']}
    c=characters.create(pid,sid)
    c=characters.bind(pid,sid,actor,imported['asset_id'],CESIUM_ROLE_MAP,c['revision'])
    characters.approve(pid,sid,c['revision'])
    retarget=RetargetCalibration(studio)
    cal=retarget.create(pid,sid)
    limits={role:175.0 for role in CESIUM_ROLE_MAP}
    cal=retarget.configure(pid,sid,actor,cal['revision'],joint_limits_deg=limits,
                           contact_frames=[1],contact_tolerance_m=.12,
                           max_ground_penetration_m=.20)
    retarget.approve(pid,sid,cal['revision'])
    native=run_retarget_acceptance(retarget,pid,sid,output/'native',
                                   executable=blender,render_preview=render_preview)
    return {'status':native['status'],'native':native,'external':provenance,
            'normalized_sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
            'character_asset_id':imported['asset_id'],'joint_count':imported['joint_count'],
            'skinned_vertices':imported['skinned_vertices']}


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    p.add_argument('--external-glb',required=True);p.add_argument('--audit-only',action='store_true')
    args=p.parse_args(argv)
    result=build_external_fixture(Path(args.out),Path(args.external_glb),render_preview=not args.audit_only)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,indent=2),'utf8')
    print(json.dumps(result,indent=2))
    return 0 if result['status']==('passed_blender_audit_only' if args.audit_only else 'passed_blender') else 1

if __name__=='__main__':raise SystemExit(main())
