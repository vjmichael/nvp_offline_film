"""B7 real NVP film scene -> approved Blender build -> independent Blender reopen.

The native creator action is SIMULATED by an isolated fixture callback, not a
shipped desktop UI. The Blender processes, OS containment, source hashes,
resource admission, .blend output, geometry readback and PNG are REAL.
No Lu/DLC connection and no artificial pre-rendered image can satisfy this.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_native_proxy_render import NativeApprovedProxyRender
from backend.nvp_native_proxy_audit import NativeProxySceneAuditor
from backend.nvp_production_scene import ProductionScene
from backend.nvp_render_preflight import preflight_scene
from backend.nvp_render_source_stage import stage_proxy_render_source
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


def fixture(out, blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    exe=Path(shutil.which(blender) or blender).resolve()
    if not exe.is_file():
        raise RuntimeError("Real native Blender is required; never simulate success")
    version=subprocess.run([str(exe),"-b","--version"],
               capture_output=True,text=True,timeout=18,check=True).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("Real pinned Blender did not report version")
    studio=Studio(root/"project.sqlite3")
    project=studio.create_project("Actual B7 proxy shot","Director-approved static staging")
    pid=project["id"]
    sid=studio.save_screenplay(pid,"INT. OBSERVATION STUDIO - DAY\n\nMARA\nI'm ready.\n",0)["scenes"][0]["id"]
    prod=ProductionScene(studio)
    prod.create_asset(pid,{"name":"MARA","category":"character","dimensions":[.4,.4,1.7]})
    plan=prod.stage_scene(pid,sid,[8,6,3])
    plan=prod.solve_scene(pid,sid,plan["plan_revision"])
    prod.approve_scene(pid,sid,plan["plan_revision"])
    world=WorldState(studio).read(pid,sid)
    actor=world["manifest"]["instances"][0]["instance_id"]
    WorldState(studio).set_human(pid,sid,actor,"visible",False,world["revision"])
    proof=preflight_scene(studio,pid,sid)

    ledger=TaskLedger(root/"resource_activity")
    supervisor=BlenderWorkerSupervisor(root/"approved_worker",
          blender_executable=exe,blender_sha256=sha_file(exe),
          blender_version=version,activity_ledger=ledger)
    staged=stage_proxy_render_source(studio,supervisor,proof,ram_mb=2048)
    event=object()
    events=[]
    def trusted_fixture_creator_action(incoming,scope):
        events.append(scope)
        return (incoming is event and scope["project_id"]==pid and
                scope["scene_id"]==sid and
                scope["world_sha256"]==proof["world_sha256"] and
                scope["output_contract"]=="blend_build_and_independent_reopen_audit_preview")
    approved=NativeApprovedProxyRender(studio,supervisor,ledger,
                                      verify_creator_action=trusted_fixture_creator_action)
    consent=approved.consent_from_trusted_native_action(staged,proof,event,duration_s=1800)
    ticket=approved.enqueue_approved(staged,proof,consent["approval_id"],lane="interactive")
    if ticket["state"]!="QUEUED":
        raise RuntimeError("NVP build must queue before creator-authorized memory admission")
    real_sampler=ledger.sampler
    ledger.sampler=lambda:ResourceSnapshot(1,16384,1024,0,())
    blocked=approved.run_next()
    if blocked["state"]!="QUEUED" or (staged["stage_dir"]/"approved_scene.blend").exists():
        raise RuntimeError("Unsafe RAM admission allowed Blender to run")
    ledger.sampler=real_sampler
    built=approved.run_next()
    if built["state"]!="SUCCEEDED":
        raise RuntimeError("Real contained native Blender build failed: "+str(built))
    if ledger.get_task(ticket["task_id"])["state"]!="SUCCEEDED":
        raise RuntimeError("Creator-authorized Blender worker did not record success")

    auditor=NativeProxySceneAuditor(approved)
    result=auditor.reopen_and_verify(consent["approval_id"],ram_mb=2048)
    if result.get("state")!="VERIFIED" or not result.get("verified_real_blender_reopen"):
        raise RuntimeError("Independent real Blender reopen did not pass: "+str(result))
    repeat=auditor.reopen_and_verify(consent["approval_id"],ram_mb=2048)
    if repeat!=result:
        raise RuntimeError("Restart-safe audit verification changed without new outputs")
    if ledger.snapshot()["reservations"]["ram_mb"]!=0:
        raise RuntimeError("Verified Blender workers leaked RAM reservation")
    report={
        "format":"nvp.stack02c3b7.real_native_build_and_reopen.v1",
        "actual_blender_version":version,
        "real_blender_binary_sha256":sha_file(exe),
        "real_blender_build_executed":True,
        "independent_blender_reopen_executed":True,
        "native_creator_action":"fixture_simulated_not_desktop_ui",
        "lu_ipc_used":False,
        "queued_without_start_on_low_ram":True,
        "native_output_checks":result["audit_checks"],
        "director_hidden_visibility_verified":True,
        "source_world_sha256":proof["world_sha256"],
        "approved_build_script_sha256":proof["blender_script_sha256"],
        "original_blend_sha256":result["build_blend_sha256"],
        "verified_audit_sha256":result["audit_json_sha256"],
        "verified_png_sha256":result["preview_png_sha256"],
        "resource_reservation_released":True,
        "frozen_digital_take_completed":False,
        "professional_graded_exr_completed":False,
        "native_host_ui_integrated":False,
    }
    (root/"nvp_stack02c3b7_real_native_acceptance.json").write_text(
        json.dumps(report,indent=2,sort_keys=True),"utf8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--blender",default="blender")
    args=parser.parse_args()
    print(json.dumps(fixture(args.out,args.blender),indent=2,sort_keys=True))
