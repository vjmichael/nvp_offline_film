"""Cross-platform native Blender fixture: export source GLB, import, remap, re-open/audit.

Source model is a Blender-exported stylized skinned character, not a purchased
human asset. Genuine external licensing and artistic quality remain separate.
"""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_skinning import SkinnedPerformance, run_skin_acceptance
from backend.nvp_character_assets import CharacterAssets,run_character_acceptance
from tests.test_skinning import make_fixture
from backend.nvp_rig_motion import ROLES

EXPORT_CHARACTER_GLTF = r'''# NVP-PROD-06C real Blender skinned GLB source fixture.
import bpy,sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
output=Path(args[args.index('--out')+1]).resolve()
rig=next(x for x in bpy.data.objects if x.name.startswith('NVP_RIG_') and x.type=='ARMATURE')
actor_id=rig.name.split('NVP_RIG_',1)[1]
mesh=bpy.data.objects['NVP_SKIN_'+actor_id]
bpy.context.scene.frame_set(1)
for bone in rig.pose.bones:
    bone.rotation_mode='QUATERNION'
    bone.rotation_quaternion=(1,0,0,0)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True);mesh.select_set(True)
bpy.context.view_layer.objects.active=mesh
bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',
                          use_selection=True,export_animations=False,
                          export_skins=True,export_yup=True)
if not output.is_file() or output.stat().st_size<128:
    raise RuntimeError('Blender did not export a real skinned GLB')
'''


def build_fixture(out:Path,*,render_preview=True, blender='blender'):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    studio,pid,sid,actor=make_fixture(out)
    skin=SkinnedPerformance(studio)
    s=skin.create(pid,sid)
    s=skin.calibrate(pid,sid,actor,'arm_left',[10,0,0],[0,0,0],s['revision'])
    skin.approve(pid,sid,s['revision'])
    check=blender_available(blender)
    if not check['available']:
        return {'status':'blocked_no_blender','reason':check['reason']}
    baseline=run_skin_acceptance(skin,pid,sid,out/'source_skin',executable=blender,render_preview=False)
    if baseline['status']!='passed_blender_audit_only':
        return {'status':'failed','step':'source_skin','evidence':baseline}
    export=out/'export_character.py';export.write_text(EXPORT_CHARACTER_GLTF,'utf8')
    avatar=out/'importable_humanoid.glb'
    cmd=[check['path'],'-b',baseline['blend'],'-t','2','--python',str(export),'--','--out',str(avatar)]
    try: p=subprocess.run(cmd,capture_output=True,text=True,timeout=180,cwd=out)
    except subprocess.TimeoutExpired:
        return {'status':'failed','step':'export_glb','reason':'Blender timed out'}
    if p.returncode or not avatar.is_file():
        return {'status':'failed','step':'export_glb','stdout':p.stdout[-1800:],'stderr':p.stderr[-2500:]}
    characters=CharacterAssets(studio)
    try:
        imported=characters.register(pid,avatar.read_bytes(),'creator_owned',source='NVP CI fixture / director-authored geometry')
        session=characters.create(pid,sid)
        session=characters.bind(pid,sid,actor,imported['asset_id'],
                                {role:role for role in ROLES},session['revision'])
        characters.approve(pid,sid,session['revision'])
        result=run_character_acceptance(characters,pid,sid,out/'native_character',
                                        executable=blender,render_preview=render_preview)
    except Exception as e:
        return {'status':'failed','step':'register_or_bind','reason':f'{type(e).__name__}: {e}'}
    return {'import':imported,'native':result,'status':result['status']}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args(argv)
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    result=build_fixture(out,render_preview=not args.audit_only)
    (out/'result.json').write_text(json.dumps(result,indent=2),'utf8')
    print(json.dumps(result,indent=2))
    return 0 if result['status']==('passed_blender_audit_only' if args.audit_only else 'passed_blender') else 1

if __name__=='__main__':raise SystemExit(main())
