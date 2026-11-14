"""STACK-02A supervised adapter for an existing creator-approved NVP scene.

Uses current ProductionScene export, original Blender build and original
independent AUDIT_SCRIPT from nvp_blender_acceptance. No second renderer,
custom geometry operations, or new blender-side math. Blender stays external.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil

from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor, sha_file
from backend.nvp_blender_acceptance import AUDIT_SCRIPT
from backend.nvp_production_scene import ProductionScene, compact


def run_supervised_scene(
    production: ProductionScene, project_id: str, scene_id: str,
    supervisor: BlenderWorkerSupervisor, *, require_linux_cgroup_v2: bool=False,
):
    """Build -> fresh independent Blender reopen/audit -> output SHA validation.

    Every edit to the source manifest between build and final validation
    invalidates the result. No approval or data-source mutation is performed.
    """
    original=compact(production.export_manifest(project_id,scene_id))
    script=production.export_blender_script(project_id,scene_id)
    build=supervisor.root/"approved_build_001"
    build.mkdir(exist_ok=False)
    (build/"approved_manifest.json").write_text(original,"utf8")
    (build/"trusted_scene_build.py").write_text(script,"utf8")
    build_job=BlenderOperation(
        job_id=build.name,script="trusted_scene_build.py",
        script_sha256=sha_file(build/"trusted_scene_build.py"),
        inputs={"approved_manifest.json":sha_file(build/"approved_manifest.json")},
        outputs={"approved_scene.blend":"blend"},
        arguments={"--output":"approved_scene.blend"},
        timeout_seconds=240,
        require_linux_cgroup_v2=require_linux_cgroup_v2,
    )
    built=supervisor.run(build_job)
    if built["state"]!="SUCCEEDED":
        return {"status":"failed","step":"build","receipt":built}

    audit=supervisor.root/"independent_audit_002"
    audit.mkdir(exist_ok=False)
    shutil.copyfile(build/"approved_scene.blend",audit/"approved_scene.blend")
    shutil.copyfile(build/"approved_manifest.json",audit/"approved_manifest.json")
    (audit/"trusted_audit.py").write_text(AUDIT_SCRIPT,"utf8")
    audit_job=BlenderOperation(
        job_id=audit.name,script="trusted_audit.py",
        script_sha256=sha_file(audit/"trusted_audit.py"),
        scene="approved_scene.blend",
        inputs={
            "approved_scene.blend":sha_file(audit/"approved_scene.blend"),
            "approved_manifest.json":sha_file(audit/"approved_manifest.json"),
        },
        outputs={"checked_scene.png":"png","verified_scene.json":"json_audit"},
        arguments={
            "--manifest":"approved_manifest.json",
            "--audit":"verified_scene.json",
            "--render":"checked_scene.png",
        },
        timeout_seconds=240,
        require_linux_cgroup_v2=require_linux_cgroup_v2,
    )
    audited=supervisor.run(audit_job)
    if audited["state"]!="SUCCEEDED":
        return {"status":"failed","step":"audit","build":built,"receipt":audited}
    result=json.loads((audit/"verified_scene.json").read_text("utf8"))
    if result.get("passed") is not True or not result.get("checks"):
        raise RuntimeError("Independent native Blender geometry audit lacks checks")
    if compact(production.export_manifest(project_id,scene_id))!=original:
        raise RuntimeError("Creator-approved source manifest changed during worker run")
    # Independent reopen must not trust a stale journal row alone.
    supervisor.verify_completed(build_job.job_id)
    supervisor.verify_completed(audit_job.job_id)
    return {
        "status":"passed_blender_supervised",
        "build_job":built["id"],"audit_job":audited["id"],
        "original_source_sha256":sha_file(build/"approved_manifest.json"),
        "blender_version":supervisor.blender_version,
        "build_sha256":built["outputs"]["approved_scene.blend"]["sha256"],
        "preview_sha256":audited["outputs"]["checked_scene.png"]["sha256"],
        "audit_sha256":audited["outputs"]["verified_scene.json"]["sha256"],
        "audit_checks":len(result["checks"]),
        "approval":"technical_only_not_a_director_approved_presentation",
    }
