"""STACK-02C3B2 real approved immutable Blender spec and native resource acceptance.

This fixture calls the existing Blender worker and approved static bpy script.
It does not create a new renderer. Tests actual OS memory preflight, queue
without spawn, durable promotion and independently audited Blender output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_resource_guard import ResourceSnapshot,collect_resources
from backend.nvp_resource_ledger import TaskLedger
from tools.nvp_stack02a_worker_fixture import FIXTURE_SCRIPT


def fixture(out,blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    exe=Path(shutil.which(blender) or blender).resolve()
    if not exe.is_file():raise RuntimeError("Actual Blender binary not installed")
    version=subprocess.run([str(exe),"-b","--version"],
        capture_output=True,text=True,timeout=18,check=True).stdout.splitlines()[0].strip()
    ledger=TaskLedger(root/"shared_activity")
    worker=BlenderWorkerSupervisor(root/"worker",blender_executable=exe,
        blender_sha256=sha_file(exe),blender_version=version,activity_ledger=ledger)
    job=worker.root/"real_approved_blender"
    job.mkdir()
    source={"format":"nvp.test.worker.frozen.v1","source_sha256":sha_file(exe),
            "frames":[1],"output_kind":"native_blender_workbench_cpu"}
    (job/"source.json").write_text(json.dumps(source,sort_keys=True),"utf8")
    (job/"trusted.py").write_text(FIXTURE_SCRIPT,"utf8")
    op=BlenderOperation(job_id=job.name,script="trusted.py",
        script_sha256=sha_file(job/"trusted.py"),
        inputs={"source.json":sha_file(job/"source.json")},
        outputs={"real_scene.blend":"blend","real_frame.png":"png","real_audit.json":"json_audit"},
        arguments={"--manifest":"source.json","--output":"real_scene.blend",
                   "--render":"real_frame.png","--audit":"real_audit.json"},
        timeout_seconds=145,memory_limit_mb=2048)
    # First prevent launching during a fake critical RAM shortage. Then use
    # real OS memory telemetry to promote the same authorized job.
    real_sampler=ledger.sampler
    ledger.sampler=lambda:ResourceSnapshot(1,16384,1024,0,())
    # Authorizer simulates the trusted production-domain creator approval.
    # Unlike an owner ID, this checks exact frozen source evidence. Real NVP
    # integration must consult creator-approved scene/take revision records.
    def approval_check(approval_id,digest,document):
        return (approval_id=="creator_approved_b2" and
                document.get("operation",{}).get("inputs",{}).get("source.json")==
                sha_file(job/"source.json"))
    dispatcher=ApprovedBlenderDispatcher(worker,ledger,approval_check=approval_check)
    ticket=dispatcher.enqueue(op,approval_id="creator_approved_b2",lane="interactive")
    blocked=dispatcher.run_next()
    if blocked["state"]!="QUEUED" or (job/"real_frame.png").exists():
        raise RuntimeError("Memory-short NVP Blender task did not queue without execution")
    ledger.sampler=real_sampler
    admitted=dispatcher.run_next()
    if admitted and admitted.get("state")=="SUCCEEDED":
        admitted["resource_activity_id"]=worker._activity_id(op.job_id)
    if admitted["state"]!="SUCCEEDED":
        raise RuntimeError("Real governed Blender task did not finish: "+str(admitted))
    activity=TaskLedger(ledger.root)
    row=activity.get_task(admitted["resource_activity_id"])
    if row["state"]!="SUCCEEDED" or activity.snapshot()["reservations"]["ram_mb"]!=0:
        raise RuntimeError("Verified worker did not release its reserved memory")
    reopened=worker.verify_completed(op.job_id)
    if reopened["state"]!="SUCCEEDED":
        raise RuntimeError("Original Blender source and outputs failed independent readback")
    events=activity.events(admitted["resource_activity_id"])
    if not any(e["state"]=="QUEUED" for e in events) or not any(e["phase"]=="building_scene" for e in events):
        raise RuntimeError("Measured operation phases not recorded")
    audit=json.loads((job/"real_audit.json").read_text("utf8"))
    if audit["passed"] is not True:
        raise RuntimeError("Real Blender audit failed")
    report={
        "format":"nvp.stack02c3b2.approved.native.blender.v1",
        "engine":version,"blender_sha256":sha_file(exe),
        "real_blender_ran":True,"queued_without_start_under_low_ram":True,
        "admitted_after_real_memory_measurement":True,
        "rendered_png_sha256":sha_file(job/"real_frame.png"),
        "saved_blend_sha256":sha_file(job/"real_scene.blend"),
        "independent_output_reopen":True,
        "progress_from_measured_worker_states":True,
        "fabricated_percent":False,
        "final_ram_reservation_mb":0,
        "gpu_memory_used":False,
        "model_loading_or_offloading_controlled":False,
        "creator_approved_spec_sha256":ticket["spec_sha256"],
        "approved_native_dispatcher":True,
    }
    (root/"stack02c3b2_approved_native_acceptance.json").write_text(json.dumps(report,indent=2,sort_keys=True),"utf8")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--blender",default="blender")
    a=p.parse_args()
    print(json.dumps(fixture(a.out,a.blender),indent=2,sort_keys=True))
