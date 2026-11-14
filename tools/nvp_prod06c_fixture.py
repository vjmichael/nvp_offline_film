"""Cross-platform native Blender fixture: export source GLB, import, remap, re-open/audit.

Source model is a Blender-exported stylized skinned character, not a purchased
human asset. Genuine external licensing and artistic quality remain separate.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor, sha_file
from backend.nvp_skinning import SkinnedPerformance, SKIN_AUDIT_SCRIPT
from backend.nvp_character_assets import CharacterAssets, CHARACTER_AUDIT_SCRIPT
from backend.nvp_production_scene import compact
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


def _checked_copy(source:Path, destination:Path):
    """Stage only a hash-checked reviewed source into one bounded worker job."""
    source=Path(source).resolve()
    if not source.is_file() or destination.exists():
        raise RuntimeError("Missing original worker source or attempted derivative overwrite")
    digest=sha_file(source)
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination)
    if sha_file(destination)!=digest:
        raise RuntimeError("Source bytes changed while staging a supervised worker")
    return digest


def _dispatch(supervisor, job_id, script_name, script, *, inputs, outputs,
              arguments, scene=None, strict_linux=False):
    """One finite source-owned Blender invocation, never a direct subprocess.

    The script is a reviewed first-party template/approved compiler output.
    Every imported artifact is SHA-pinned, and every output is journaled.
    """
    job=supervisor.root/job_id
    if job.exists():
        raise RuntimeError("Original Blender worker job cannot be reused")
    job.mkdir()
    script_path=job/script_name
    script_path.write_text(script,encoding="utf8")
    hashes={}
    for relative, original in inputs.items():
        hashes[relative]=_checked_copy(Path(original),job/relative)
    op=BlenderOperation(
        job_id=job_id,script=script_name,script_sha256=sha_file(script_path),
        inputs=hashes,outputs=outputs,arguments=arguments,scene=scene,
        timeout_seconds=300,memory_limit_mb=8192,
        require_linux_cgroup_v2=strict_linux,
        # Original public synthetic CI is NOT privately approved content.
        # Windows native Job custody is required, but AppContainer/WFP/EFS
        # remains a separate, independently authorized production gate.
        require_private_isolation=False)
    result=supervisor.run(op)
    if result["state"]!="SUCCEEDED":
        error_path=job/"worker_stderr.log"
        stderr=(error_path.read_text("utf8",errors="replace")[-1500:]
                if error_path.is_file() else "")
        raise RuntimeError("Original protected Blender job "+job_id+
                           " refused: "+str(result.get("error"))+" "+stderr)
    receipt=supervisor.verify_completed(job_id)
    if receipt["state"]!="SUCCEEDED":
        raise RuntimeError("Original supervised Blender receipt not accepted")
    return job, receipt


def build_fixture(out:Path,*,render_preview=True, blender='blender'):
    """Original 06C generated GLB and casting under five supervised jobs.

    This is real public test geometry, never a licensed private character or
    independent creator film-master approval. No direct Blender launcher.
    """
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    studio,pid,sid,actor=make_fixture(out)
    skin=SkinnedPerformance(studio)
    revision=skin.create(pid,sid)
    revision=skin.calibrate(pid,sid,actor,'arm_left',[10,0,0],[0,0,0],
                            revision['revision'])
    skin.approve(pid,sid,revision['revision'])

    candidate=Path(blender)
    located=str(candidate.resolve()) if candidate.is_file() else shutil.which(blender)
    if not located:
        return {"status":"blocked_no_blender","reason":"No original Blender binary found"}
    binary=Path(located).resolve()
    # Pinned by the provisioned public CI environment. Wrong version must
    # fail closed, never silently run an unreviewed executable.
    version=os.environ.get("NVP_TEST_BLENDER_VERSION","Blender 5.3.0")
    binary_sha=sha_file(binary)
    worker_root=out/"protected_blender_jobs"
    supervisor=BlenderWorkerSupervisor(
        worker_root,blender_executable=binary,
        blender_sha256=binary_sha,blender_version=version)
    strict_linux=sys.platform=="linux"
    supervisor.probe(strict_linux_cgroup=strict_linux)
    receipts={}

    source,receipt=_dispatch(
        supervisor,"Prod06CSkinBuild","build_skin.py",
        skin.blender_script(pid,sid),inputs={},
        outputs={"skin.blend":"blend"},
        arguments={"--output":"skin.blend"},strict_linux=strict_linux)
    receipts["skin_build"]=receipt

    approved=skin.export(pid,sid)
    payload=out/"original_skin_review.json"
    payload.write_text(compact({
        "skin":approved["skin"],"motion":approved["motion"],
        "take":approved["take"]}),encoding="utf8")
    audit,receipt=_dispatch(
        supervisor,"Prod06CSkinAudit","audit_skin.py",SKIN_AUDIT_SCRIPT,
        inputs={"skin.blend":source/"skin.blend","skin.json":payload},
        outputs={"skin_audit.json":"json_audit"},
        arguments={"--payload":"skin.json","--audit":"skin_audit.json",
                   "--skip-render":"1"},scene="skin.blend",strict_linux=strict_linux)
    receipts["skin_audit"]=receipt
    source_report=json.loads((audit/"skin_audit.json").read_text("utf8"))
    if (source_report.get("passed") is not True or
            len(source_report.get("checks",[]))<10):
        raise RuntimeError("Original source skin audit is incomplete")

    glb_job,receipt=_dispatch(
        supervisor,"Prod06CGLBExport","export_glb.py",
        EXPORT_CHARACTER_GLTF,
        inputs={"skin.blend":source/"skin.blend"},
        outputs={"importable_humanoid.glb":"glb"},
        arguments={"--out":"importable_humanoid.glb"},
        scene="skin.blend",strict_linux=strict_linux)
    receipts["glb_export"]=receipt
    original=glb_job/"importable_humanoid.glb"
    _checked_copy(original,out/"importable_humanoid.glb")

    characters=CharacterAssets(studio)
    imported=characters.register(
        pid,original.read_bytes(),"creator_owned",
        source="NVP CI fixture / director-authored geometry")
    session=characters.create(pid,sid)
    session=characters.bind(
        pid,sid,actor,imported["asset_id"],
        {role:role for role in ROLES},session["revision"])
    characters.approve(pid,sid,session["revision"])
    bundle_root=out/"source_review_bundle"
    characters.export_bundle(pid,sid,bundle_root)
    package=characters.export(pid,sid)
    original_inputs={"character.json":bundle_root/"character.json"}
    for binding in package["character"]["bindings"]:
        relative=binding["file"]
        if relative!="assets/"+binding["sha256"]+".glb":
            raise RuntimeError("Source GLB asset path is not the approved digest")
        original_inputs[relative]=bundle_root/relative

    character_build,receipt=_dispatch(
        supervisor,"Prod06CCharacterBuild","build_characters.py",
        (bundle_root/"build_characters.py").read_text("utf8"),
        inputs=original_inputs,outputs={"characters.blend":"blend"},
        arguments={"--output":"characters.blend"},strict_linux=strict_linux)
    receipts["character_build"]=receipt

    audit_outputs={"character_audit.json":"json_audit"}
    audit_args={"--package":"character.json",
                "--audit":"character_audit.json"}
    if render_preview:
        audit_outputs["character_preview.png"]="png"
        audit_args["--preview"]="character_preview.png"
    else:
        audit_args["--skip-render"]="1"
    character_audit,receipt=_dispatch(
        supervisor,"Prod06CCharacterAudit","audit_characters.py",
        CHARACTER_AUDIT_SCRIPT,
        inputs={"characters.blend":character_build/"characters.blend",
                "character.json":bundle_root/"character.json"},
        outputs=audit_outputs,arguments=audit_args,
        scene="characters.blend",strict_linux=strict_linux)
    receipts["character_audit"]=receipt

    report=json.loads((character_audit/"character_audit.json").read_text("utf8"))
    if report.get("passed") is not True or len(report.get("checks",[]))<=10:
        raise RuntimeError("Original imported-character audit is incomplete")

    # A separate host instance must independently reopen the five durable
    # specifications and output/source hashes after all Blender jobs exit.
    reopened=BlenderWorkerSupervisor(
        worker_root,blender_executable=binary,
        blender_sha256=binary_sha,blender_version=version)
    for job_id in ("Prod06CSkinBuild","Prod06CSkinAudit",
                   "Prod06CGLBExport","Prod06CCharacterBuild",
                   "Prod06CCharacterAudit"):
        reopened.verify_completed(job_id)
    if sha_file(original)!=sha_file(out/"importable_humanoid.glb"):
        raise RuntimeError("Public original skinned GLB changed after journal reopen")

    native={"status":"passed_blender" if render_preview
            else "passed_blender_audit_only",
            "checks":len(report["checks"]),
            "audit":str(character_audit/"character_audit.json"),
            "blend":str(character_build/"characters.blend"),
            "version":version,
            "independent_blender_journal_reopen":True}
    return {"status":native["status"],"import":imported,"native":native,
            "source_worker_ids":[receipt["id"] for receipt in receipts.values()],
            "source_worker_receipts_verified":True,
            "public_fixture_only":True,
            "private_worker_authorized":False,
            "original_filmmaster_approved":False}


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
