"""STACK-02A: genuine Blender child-process acceptance, no simulated rendering.

Uses one SHA-verified Blender executable, a pinned independently distributed
worker script, a frozen source manifest, durable SQLite job events, supervised
render, independent Blender file reopen, exact output rehash and cancellation.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time

from backend.nvp_blender_worker import (
    BlenderOperation, BlenderWorkerSupervisor, sha_file,
)

# Production operations will reuse scene scripts from nvp_blender_acceptance.
# This simple fixture intentionally tests the worker boundary, not image quality.
FIXTURE_SCRIPT = r'''import bpy, json, sys
from pathlib import Path
args=sys.argv[sys.argv.index("--")+1:]
options=dict(zip(args[::2],args[1::2]))
source=json.loads(Path(options["--manifest"]).read_text("utf8"))
if source["format"]!="nvp.test.worker.frozen.v1":
    raise RuntimeError("Untrusted immutable worker source manifest")
scene=bpy.context.scene
# Windows headless CI has no WGL/Workbench OpenGL device.
# Reuse Blender's established CPU Cycles renderer rather than software
# graphics emulation or an uncontained application-specific fallback.
if sys.platform == "win32":
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=1
else:
    scene.render.engine="BLENDER_WORKBENCH"
scene.render.resolution_x=128
scene.render.resolution_y=72
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.render.filepath=options["--render"]
scene["nvp_source_hash"]=source["source_sha256"]
bpy.ops.wm.save_as_mainfile(filepath=options["--output"])
bpy.ops.render.render(write_still=True)
report={
    "passed":True,"format":"nvp.stack02a.real_blender.audit.v1",
    "source_sha256":source["source_sha256"],
    "blender_version":bpy.app.version_string,
    "render_width":128,"render_height":72,
    "blend_exists":Path(options["--output"]).is_file(),
    "png_exists":Path(options["--render"]).is_file(),
}
if not report["blend_exists"] or not report["png_exists"]:
    raise RuntimeError("Required genuine Blender outputs missing")
Path(options["--audit"]).write_text(json.dumps(report,sort_keys=True),"utf8")
'''

BAD_SCRIPT = r'''import bpy
raise RuntimeError("deliberate Blender child failure for durable worker refusal")
'''

SLOW_SCRIPT = r'''import bpy,time
time.sleep(30)
raise RuntimeError("cancelled worker somehow continued")
'''


def fixture(out, blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    binary=Path(shutil.which(blender) or blender).resolve()
    if not binary.is_file():
        raise RuntimeError("No real Blender executable; native acceptance blocked")
    # Version is obtained from the independent Blender probe, NOT invented.
    import subprocess
    version=subprocess.run([str(binary),"-b","--version"],capture_output=True,
                           text=True,timeout=20,check=True).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("Selected executable is not Blender")
    exe_sha=sha_file(binary)
    worker=BlenderWorkerSupervisor(root/"worker",
        blender_executable=binary,blender_sha256=exe_sha,blender_version=version)
    # Native CI opts into the strict delegated cgroup profile explicitly.
    strict_linux_tree=(os.getenv("NVP_REQUIRE_REAL_CGROUP")=="1" and os.name=="posix")

    jobdir=worker.root/"real_render_001"
    jobdir.mkdir()
    source={
        "format":"nvp.test.worker.frozen.v1",
        "source_sha256":hashlib.sha256(b"frozen-nvp-source-and-take").hexdigest(),
        "frames":[1],"output_kind":"Workbench PNG",
    }
    (jobdir/"source_manifest.json").write_text(json.dumps(source,sort_keys=True),"utf8")
    (jobdir/"trusted_script.py").write_text(FIXTURE_SCRIPT,"utf8")
    op=BlenderOperation(
        job_id=jobdir.name,script="trusted_script.py",
        script_sha256=sha_file(jobdir/"trusted_script.py"),
        inputs={"source_manifest.json":sha_file(jobdir/"source_manifest.json")},
        outputs={"real_scene.blend":"blend","real_frame.png":"png",
                 "blender_audit.json":"json_audit"},
        arguments={"--manifest":"source_manifest.json","--output":"real_scene.blend",
                   "--render":"real_frame.png","--audit":"blender_audit.json"},
        timeout_seconds=180,
        require_linux_cgroup_v2=strict_linux_tree)
    result=worker.run(op)
    if result["state"]!="SUCCEEDED":
        raise RuntimeError("Real external Blender rendering worker failed: "+str(result["error"]))
    reopened=BlenderWorkerSupervisor(worker.root,
        blender_executable=binary,blender_sha256=exe_sha,blender_version=version)
    audited=reopened.verify_completed(op.job_id)
    if audited["outputs"]!=result["outputs"]:
        raise RuntimeError("Blender receipt changed after fresh process/restart")
    evidence=json.loads((jobdir/"blender_audit.json").read_text("utf8"))
    if evidence["source_sha256"]!=source["source_sha256"] or evidence["blender_version"] not in version:
        raise RuntimeError("Real Blender audit changed frozen source/version")
    from backend.nvp_presentation_pipeline import _png_info
    width,height=_png_info((jobdir/"real_frame.png").read_bytes())
    if (width,height)!=(128,72):
        raise RuntimeError("Real Blender PNG raster changed")
    # A successful journal record is not authority when the media is altered.
    png=jobdir/"real_frame.png"
    real=png.read_bytes()
    try:
        png.write_bytes(real+b"tampered")
        try:
            reopened.verify_completed(op.job_id)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Tampered successful result was trusted")
    finally:
        png.write_bytes(real)
    reopened.verify_completed(op.job_id)

    # Native child failure must never report SUCCEEDED.
    bad_dir=worker.root/"bad_script_002"
    bad_dir.mkdir()
    (bad_dir/"bad.py").write_text(BAD_SCRIPT,"utf8")
    bad=BlenderOperation(job_id=bad_dir.name,script="bad.py",
        script_sha256=sha_file(bad_dir/"bad.py"),inputs={},
        outputs={"will_not_exist.json":"json_audit"},arguments={},
        timeout_seconds=40,
        require_linux_cgroup_v2=strict_linux_tree)
    bad_result=worker.run(bad)
    if bad_result["state"]!="FAILED" or bad_result["outputs"] is not None:
        raise RuntimeError("Deliberate native Blender failure was not refused")

    # Test cancellation of an actually running Blender process and its session.
    slow_dir=worker.root/"slow_script_003"
    slow_dir.mkdir()
    (slow_dir/"slow.py").write_text(SLOW_SCRIPT,"utf8")
    slow=BlenderOperation(job_id=slow_dir.name,script="slow.py",
        script_sha256=sha_file(slow_dir/"slow.py"),inputs={},
        outputs={"never.json":"json_audit"},arguments={},
        timeout_seconds=70,
        require_linux_cgroup_v2=strict_linux_tree)
    response={}
    thread=threading.Thread(target=lambda:response.update(worker=worker.run(slow)))
    thread.start()
    ready=False
    for _ in range(300):
        try:
            ready=worker.inspect(slow.job_id)["state"]=="RUNNING"
        except KeyError:
            ready=False
        if ready:break
        time.sleep(.05)
    if not ready:
        thread.join(timeout=90)
        raise RuntimeError("Real Blender cancellation target never entered RUNNING")
    if not worker.cancel(slow.job_id):
        raise RuntimeError("Real cancellation request was rejected")
    thread.join(timeout=90)
    if thread.is_alive() or response.get("worker",{}).get("state")!="CANCELLED":
        raise RuntimeError("Actual Blender process was not cancelled and reaped")

    # Reuse the existing NVP ProductionScene builder and existing independent
    # Blender geometry audit through the SAME pinned external worker manager.
    from backend.nvp_studio import Studio
    from backend.nvp_production_scene import ProductionScene
    from backend.nvp_supervised_production import run_supervised_scene
    studio=Studio(root/"approved_source_film.sqlite3")
    proj=studio.create_project("STACK02A supervised source","frozen approved stage")
    project_id=proj["id"]
    scene=studio.save_screenplay(project_id,
        "INT. SET - DAY\\n\\nA chair rests by the window.\\n",0)
    scene_id=scene["scenes"][0]["id"]
    production=ProductionScene(studio)
    chair=production.create_asset(project_id,{
        "name":"Chair","category":"furniture","dimensions":[.5,.5,.9],
        "anchors":{"seat":[0,0,.5]},
    })
    plan=production.stage_scene(project_id,scene_id,[8,6,3])
    plan=production.add_instance(project_id,scene_id,chair["asset_id"],
        "chair_1",plan["plan_revision"])
    plan=production.solve_scene(project_id,scene_id,plan["plan_revision"])
    production.approve_scene(project_id,scene_id,plan["plan_revision"])
    staged=run_supervised_scene(production,project_id,scene_id,worker,
        require_linux_cgroup_v2=strict_linux_tree)
    if staged["status"]!="passed_blender_supervised" or staged["audit_checks"]<4:
        raise RuntimeError("Approved original production stage did not survive supervised external Blender/audit: "+str(staged))

    # Simulate the durable state present immediately before a host crash:
    # recovery must mark it INTERRUPTED, NEVER synthesize acceptance.
    worker._transition(bad.job_id,"RUNNING",worker_pid=999999)
    interrupted=reopened.recover_interrupted()
    if interrupted!=[bad.job_id] or reopened.inspect(bad.job_id)["state"]!="INTERRUPTED":
        raise RuntimeError("Interrupted worker journal did not refuse a result")
    report={
        "format":"nvp.stack02a.native.worker.acceptance.v1",
        "status":"real_pinned_external_blender_and_durable_refusal_verified",
        "blender_version":version,"executable_sha256":exe_sha,
        "frozen_manifest_sha256":op.inputs["source_manifest.json"],
        "script_sha256":op.script_sha256,
        "rendered_blend_sha256":result["outputs"]["real_scene.blend"]["sha256"],
        "rendered_png_sha256":result["outputs"]["real_frame.png"]["sha256"],
        "independently_reopened_after_restart":True,
        "actual_blender_scene_and_128x72_png":True,
        "approved_nvp_scene_build_and_independent_supervised_audit":staged,
        "output_corruption_refused":True,
        "nonzero_blender_failure_refused":True,
        "running_process_cancelled_and_reaped":True,
        "interrupted_worker_accepted":False,
        "orphan_cleanup_after_real_host_crash_proven":False,
        "strict_linux_cgroup_tree_mode":strict_linux_tree,
        "standalone_redistributable_blender_installer_proven":False,
        "commercial_redistribution_license_cleared":False,
        "events":{key:worker.events(key) for key in (op.job_id,bad.job_id,slow.job_id)},
    }
    (root/"stack02a_native_report.json").write_text(json.dumps(report,indent=2,sort_keys=True),"utf8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--blender",default="blender")
    args=parser.parse_args()
    print(json.dumps(fixture(args.out,args.blender),sort_keys=True,indent=2))
