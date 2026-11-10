"""Actual Blender Cycles whole-scene production and independent reopen witness.

Run with real trusted native Blender inside Windows Job Object or a Linux
systemd-delegated cgroup v2. Uses two NVP-authored OpenUSD primitive assets,
a frozen FilmIndex Take and real Blender/Cycles renderer. Fixture review
callbacks are NOT physical creator consent. No FFmpeg, video or PCM bounces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue
from backend.nvp_plan04_original_cycles import OriginalCyclesProduction
from backend.nvp_resource_ledger import TaskLedger

T=7056000000


def run(out,blender="blender"):
    report=Path(out)
    if not report.is_absolute() or report.exists() or report.is_symlink():
        raise ValueError("Fresh absolute acceptance report path required")
    if sys.platform=="linux":
        from backend.nvp_worker_linux_cgroup import current_delegated_parent
        current_delegated_parent()
    elif os.name!="nt":
        raise RuntimeError("Only real Windows Job / Linux cgroup renderer acceptance")
    executable=Path(shutil.which(blender) or blender).resolve(strict=True)
    version=subprocess.run([str(executable),"-b","--version"],
             capture_output=True,text=True,timeout=20,check=True).stdout.splitlines()[0]
    if not version.startswith("Blender "):
        raise RuntimeError("Native Blender version unavailable")
    with tempfile.TemporaryDirectory(prefix="nvp-plan04-cycles-source-") as tmp,(
         tempfile.TemporaryDirectory(prefix="nvp-plan04-cycles-jobs-")) as jobs:
        db=Path(tmp)/"film.sqlite3"
        studio=Studio(db)
        pid=studio.create_project(
            "Two verified original USD objects","Cycles Blender original scene")["id"]
        index=FilmIndex(studio)
        assets=OpenUSDAssetRegistry(index)
        sphere=assets.publish(pid,"Sphere",shape="sphere",size_m=1.8)
        cube=assets.publish(pid,"Cube",shape="cube",size_m=1.4)
        scene=OpenUSDSceneBridge(index).publish(
            pid,"CyclesWorld",
            prims=[
                {"path":"/World/Camera","role":"camera","position":[0,-7,2.5]},
                {"path":"/World/Sphere","role":"prop","position":[-1,0,0]},
                {"path":"/World/Cube","role":"prop","position":[1,0,0]},
            ],curves=[
                {"path":"/World/Sphere","samples":[
                    {"tick":0,"position":[-1,0,0]},
                    {"tick":T-1,"position":[-0.6,0,0]},
                ]},
            ],native_schemas=True,asset_bindings=[
                {"path":"/World/Sphere","asset_id":"Sphere",
                 "asset_revision":sphere["revision"]},
                {"path":"/World/Cube","asset_id":"Cube",
                 "asset_revision":cube["revision"]},
            ])
        cuts=ExactTimeShotSequence(index).publish(
            pid,"CyclesCamera",scene_id="CyclesWorld",scene_revision=1,
            duration_tick=str(T),shots=[{
                "shot_id":"ActualCyclesPicture",
                "camera_path":"/World/Camera","start_tick":"0",
                "end_tick":str(T),"pattern":"continuous",
            }])
        frozen=OpenUSDTakeCapture(
            index,verify_creator_action=lambda event,scope:
                event=="test-only-freeze-consent").freeze(
            pid,"OriginalCyclesTake",scene_id="CyclesWorld",scene_revision=1,
            timeline_id="CyclesCamera",timeline_revision=1,
            sample_ticks=[0,T//2],creator_event="test-only-freeze-consent")
        request={
            "take_id":"OriginalCyclesTake",
            "take_document_sha256":frozen["document_sha256"],
            "camera_timeline_id":"CyclesCamera",
            "camera_timeline_revision":1,
            "camera_timeline_sha256":cuts["document_sha256"],
            "first_tick":0,"last_tick_exclusive":T,
            "camera_mode":"original",
            "rail_id":None,"rail_revision":None,
            "rail_document_sha256":None,
        }
        source_reviews=[]
        queue=DurableRenderIntentionQueue(
            index,ask_native=lambda scope:source_reviews.append(scope) or True)
        queued=queue.enqueue(pid,"CyclesProductionIntent",request)
        approved=queue.review(
            pid,"CyclesProductionIntent",queued["revision"])
        ledger=TaskLedger(Path(jobs)/"resources")
        supervisor=BlenderWorkerSupervisor(
            Path(jobs)/"blender",blender_executable=executable,
            blender_sha256=sha_file(executable),blender_version=version,
            activity_ledger=ledger)
        launch_reviews=[]
        producer=OriginalCyclesProduction(
            index,queue,supervisor,
            ask_native=lambda scope:launch_reviews.append(scope) or True)
        result=producer.render_once(
            pid,"CyclesProductionIntent",approved["revision"],
            approved["selection_sha256"],T//2)
        if (result["status"]!="REAL_BLENDER_CYCLES_AND_INDEPENDENT_REOPEN_VERIFIED"
                or len(source_reviews)!=1 or len(launch_reviews)!=1 or
                result["actual_geometry_count"]!=2 or
                result["scene_sha256"]!=scene["document_sha256"] or
                result["take_sha256"]!=frozen["document_sha256"]):
            raise RuntimeError("Real original Cycles source/custody requirements failed")
        render=supervisor.root/result["build_job_id"]/"derived_cycles.png"
        with Image.open(render) as image:
            image.load()
            if image.format!="PNG" or image.size!=(400,240):
                raise RuntimeError("Native Cycles derived image is not real")
            if image.getbbox() is None:
                raise RuntimeError("Real Cycles image is blank")
        after=BlenderWorkerSupervisor(
            supervisor.root,blender_executable=executable,
            blender_sha256=sha_file(executable),blender_version=version,
            activity_ledger=TaskLedger(ledger.root))
        for job in (result["build_job_id"],result["audit_job_id"]):
            confirmed=after.verify_completed(job)
            if confirmed["state"]!="SUCCEEDED":
                raise RuntimeError("Restart-reopened Blender job output not verified")
        if after.recover_interrupted():
            raise RuntimeError("Completed native jobs should never replay after restart")
        if ledger.snapshot()["reservations"]["ram_mb"]!=0:
            raise RuntimeError("Blender resource reservations leaked")
        independently_reopened=FilmIndex(Studio(db))
        if (independently_reopened.read_revision(pid,"OriginalCyclesTake",1)[
                "document_sha256"]!=frozen["document_sha256"] or
                independently_reopened.read_revision(pid,"CyclesWorld",1)[
                "document_sha256"]!=scene["document_sha256"]):
            raise RuntimeError("Original FilmIndex/USD modified by Blender")
        evidence={
            "format":"nvp.plan04.actual_blender_cycles_frozen_openusd.v1",
            "status":"REAL_CYCLES_BUILD_SECOND_BLENDER_REOPEN_SOURCE_INTACT",
            "actual_native_blender_version":version.strip(),
            "blender_binary_sha256":sha_file(executable),
            "actual_native_blender_executions":2,
            "engine":"CYCLES_CPU",
            "source_take_sha256":frozen["document_sha256"],
            "source_scene_sha256":scene["document_sha256"],
            "original_objects":2,
            "exact_source_tick":T//2,
            "original_source_immutable_after_reopen":True,
            "build_blend_sha256":result["blend_sha256"],
            "rendered_cycles_png_sha256":result["derived_png_sha256"],
            "independent_reopen_cycles_png_sha256":result[
                "independently_reopened_png_sha256"],
            "kernel_tree_custody_required":True,
            "future_restart_replay":False,
            "source_review_fixture_only":True,
            "creator_os_approval_physically_witnessed":False,
            "ffmpeg_used":False,
            "final_film_delivered":False,
            "original_pcm_source_included_in_this_scene":False,
            "materialx_or_skinned_character_completed":False,
        }
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(evidence,sort_keys=True,indent=2),
                          encoding="utf8")
        print("NVP_PLAN04_REAL_BLENDER_CYCLES_PRODUCTION_PASS",flush=True)
        return evidence


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--report",required=True)
    parser.add_argument("--blender",default="blender")
    args=parser.parse_args()
    run(args.report,args.blender)
