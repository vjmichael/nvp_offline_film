"""Real kernel-contained NVP original-USD source render acceptance witness.

This produces one verified original geometry-derived PNG through a separate
Python subprocess in Windows Job Object or Linux delegated cgroup-v2.
The fixture's in-memory approval callbacks are NOT creator consent evidence.
No BWF/video, FFmpeg, Hydra photoreal or cinema master is claimed.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile

from PIL import Image
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue
from backend.nvp_plan03_original_render_host import NativeOriginalSceneRender

T=7056000000
FORMAT="nvp.plan03.real_os_source_render_witness.v1"


def run(report):
    report=Path(report)
    if (not report.is_absolute() or report.is_symlink() or report.exists()):
        raise ValueError("A fresh absolute native acceptance report is required")
    if sys.platform=="linux":
        from backend.nvp_worker_linux_cgroup import current_delegated_parent
        current_delegated_parent() # actual kernel delegation, not mock
    elif os.name!="nt":
        raise RuntimeError("Unsupported real OS source-render witness host")
    with tempfile.TemporaryDirectory(prefix="nvp-plan03-original-source-") as tmp,(
         tempfile.TemporaryDirectory(prefix="nvp-plan03-render-output-")) as work:
        db=Path(tmp)/"studio.sqlite3"
        studio=Studio(db)
        pid=studio.create_project("Original source render witness","One original 3D sphere")["id"]
        index=FilmIndex(studio)
        asset=OpenUSDAssetRegistry(index).publish(
            pid,"OriginalSphere",shape="sphere",size_m=1.5)
        scene=OpenUSDSceneBridge(index).publish(
            pid,"OriginalWorld",
            prims=[
                {"path":"/World/Camera","role":"camera","position":[0,0,0]},
                {"path":"/World/Sphere","role":"prop","position":[0,0,-3]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{
                "path":"/World/Sphere",
                "asset_id":"OriginalSphere",
                "asset_revision":asset["revision"],
            }])
        cuts=ExactTimeShotSequence(index).publish(
            pid,"OriginalCuts",scene_id="OriginalWorld",scene_revision=1,
            duration_tick=str(T),shots=[{
                "shot_id":"RealSourceMoment","camera_path":"/World/Camera",
                "start_tick":"0","end_tick":str(T),"pattern":"continuous"}])
        frozen=OpenUSDTakeCapture(
            index,verify_creator_action=lambda event,scope:
                event=="fixture_only_native_freeze").freeze(
                pid,"OriginalFrozenTake",scene_id="OriginalWorld",
                scene_revision=1,timeline_id="OriginalCuts",
                timeline_revision=1,sample_ticks=[0,T//2],
                creator_event="fixture_only_native_freeze")
        request={
            "take_id":"OriginalFrozenTake",
            "take_document_sha256":frozen["document_sha256"],
            "camera_timeline_id":"OriginalCuts","camera_timeline_revision":1,
            "camera_timeline_sha256":cuts["document_sha256"],
            "first_tick":0,"last_tick_exclusive":T,
            "camera_mode":"original","rail_id":None,"rail_revision":None,
            "rail_document_sha256":None,
        }
        source_review=[]
        queue=DurableRenderIntentionQueue(
            index,ask_native=lambda scope:source_review.append(scope) or True)
        queued=queue.enqueue(pid,"Plan03RealKernelPicture",request)
        approved=queue.review(pid,"Plan03RealKernelPicture",queued["revision"])
        render_review=[]
        host=NativeOriginalSceneRender(
            index,queue,workspace=Path(work),
            ask_native=lambda scope:render_review.append(scope) or True)
        result=host.render_once(
            pid,"Plan03RealKernelPicture",approved["revision"],
            approved["selection_sha256"],T//2)
        if len(source_review)!=1 or len(render_review)!=1:
            raise RuntimeError("Exactly two separated fixture reviews required")
        if result["cinema_master_published"] or not result["worker_process_tree_custody_verified"]:
            raise RuntimeError("OS source renderer not independently verified")
        if result["source_tick"]!=T//2 or result["take_document_sha256"]!=frozen[
                "document_sha256"]:
            raise RuntimeError("Native rendering lost exact original Film Time/source identity")
        with Image.open(result["derived_image_path"]) as image:
            if image.format!="PNG" or image.size!=(640,360) or not image.getbbox():
                raise RuntimeError("No real authored 3D sphere in derived PNG")
        # Reopen original in a fully independent Studio/FilmIndex instance.
        reopened=FilmIndex(Studio(db))
        if reopened.read_revision(pid,"OriginalFrozenTake",1)[
                "document_sha256"]!=frozen["document_sha256"]:
            raise RuntimeError("Original Digital Take changed during native OS renderer")
        if reopened.read_revision(pid,"OriginalWorld",1)[
                "document_sha256"]!=scene["document_sha256"]:
            raise RuntimeError("Original USD scene changed during native OS renderer")
        evidence={
            "format":FORMAT,
            "status":"ACTUAL_NATIVE_SOURCE_RENDER_OS_CUSTODY_PASS",
            "platform":sys.platform,
            "kernel_custody":result["custody_mode"],
            "source_sha256":scene["document_sha256"],
            "take_sha256":frozen["document_sha256"],
            "source_tick":T//2,
            "derived_png_sha256":result["png_sha256"],
            "derived_png_bytes":result["png_bytes"],
            "original_scene_and_take_unchanged_after_reopen":True,
            "human_native_consent_physically_witnessed":False,
            "source_review_fixture_only":True,
            "separate_render_review_fixture_only":True,
            "ffmpeg_used":False,
            "cinema_master_published":False,
        }
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(evidence,indent=2,sort_keys=True),encoding="utf8")
        print("NVP_PLAN03_ACTUAL_SOURCE_RENDER_OS_CUSTODY_PASS",flush=True)
        return evidence


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--report",required=True)
    args=p.parse_args(argv)
    run(args.report)


if __name__=="__main__":
    main()
