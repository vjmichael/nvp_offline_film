"""PLAN-02-D5: actual installed NVP.exe OpenUSD camera/queue/raster smoke.

Creates genuine frozen source and native procedural geometry inside the
installed executable, exercises the exact trusted-window IPC methods with a
test-only native dialog stand-in, independently reopens output and SQLite.
This is not physical creator approval or cinematic screening.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_plan02d_render_queue import (
    DurableRenderIntentionQueue, RECOVERY)
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


class _InstalledReviewStandIn:
    """CI-only approval signal; NEVER report this as physical human input."""
    def __init__(self):
        self.allow=True
        self.prompts=[]
        self.url="http://127.0.0.1:7777/"
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self,title,message):
        self.prompts.append((title,message))
        if "SHA" not in message or "Film Time" not in message:
            raise RuntimeError("Installed source review is not correctly scoped")
        return self.allow


def run_installed_plan02d_smoke():
    with tempfile.TemporaryDirectory(prefix="nvp-plan02d-installed-") as t:
        database=Path(t)/"studio.sqlite3"
        studio=Studio(database)
        pid=studio.create_project("Installed PLAN-02-D native source",
                                  "No derived media as source")["id"]
        index=FilmIndex(studio)
        asset=OpenUSDAssetRegistry(index).publish(
            pid,"InstalledRasterSphere",shape="sphere",size_m=1.5)
        scene=OpenUSDSceneBridge(index).publish(
            pid,"InstalledRasterWorld",prims=[
                {"path":"/World/Camera","role":"camera","position":[0,0,0]},
                {"path":"/World/Geometry","role":"prop","position":[0,3,0]},
            ],curves=[],native_schemas=True,asset_bindings=[
                {"path":"/World/Geometry","asset_id":"InstalledRasterSphere",
                 "asset_revision":asset["revision"]}])
        timeline=ExactTimeShotSequence(index).publish(
            pid,"InstalledCuts",scene_id="InstalledRasterWorld",
            scene_revision=1,duration_tick=str(2*T),shots=[{
                "shot_id":"InstalledShot","camera_path":"/World/Camera",
                "start_tick":"0","end_tick":str(2*T),
                "pattern":"continuous"}])
        taken=OpenUSDTakeCapture(
            index,verify_creator_action=lambda ev,scope:
                ev=="installed_temporary_test").freeze(
            pid,"InstalledTake",scene_id="InstalledRasterWorld",
            scene_revision=1,timeline_id="InstalledCuts",
            timeline_revision=1,sample_ticks=[0,T],
            creator_event="installed_temporary_test")
        sha=taken["document_sha256"]
        request={
            "take_id":"InstalledTake","take_document_sha256":sha,
            "camera_timeline_id":"InstalledCuts",
            "camera_timeline_revision":1,
            "camera_timeline_sha256":timeline["document_sha256"],
            "first_tick":0,"last_tick_exclusive":T,
            "camera_mode":"original","rail_id":None,
            "rail_revision":None,"rail_document_sha256":None,
        }
        bridge=TrustedDesktopCameraBridge(
            index,origin="http://127.0.0.1:7777")
        window=_InstalledReviewStandIn()
        bridge._attach_window(window)
        try:
            scope=bridge.plan02d_preview({
                "project_id":pid,"selection":request})
            if (scope["renderer_worker_authorized"] is not False or
                    scope["take_document_sha256"]!=sha):
                raise RuntimeError("Installed renderer preview granted authority")
            sampled=bridge.plan02d_raster_preview({
                "project_id":pid,"selection":request,
                "selection_sha256":scope["selection_sha256"],
                "tick":T//3})
            if (sampled["status"]!="DERIVED_MEMORY_PREVIEW_NOT_PUBLISHED" or
                    sampled["source_modified"] is not False or
                    sampled["ffmpeg_used"] is not False):
                raise RuntimeError("Installed OpenUSD native picture invalid")
            saved=bridge.plan02d_raster_publish({
                "project_id":pid,"presentation_id":"InstalledNativePNG",
                "selection":request,
                "selection_sha256":scope["selection_sha256"],
                "tick":T//3,"expected_png_sha256":sampled["png_sha256"]})
            if saved["status"]!="VERIFIED_DERIVED_OPENUSD_PNG":
                raise RuntimeError("Installed native PNG did not publish")
            queued=bridge.plan02d_enqueue({
                "project_id":pid,"job_id":"InstalledWorkerIntent",
                "selection":request})
            reviewed=bridge.plan02d_review({
                "project_id":pid,"job_id":"InstalledWorkerIntent",
                "expected_revision":queued["revision"]})
            if (reviewed["status"]!="SOURCE_SCOPE_APPROVED_NO_WORKER" or
                    reviewed["renderer_worker_authorized"] is not False or
                    len(window.prompts)!=2):
                raise RuntimeError("Installed native source review not separated")
        finally:
            bridge._close()
        # Truly reopen SQLite through a different host object.
        reopened=FilmIndex(Studio(database))
        if (reopened.read_revision(
                pid,"InstalledTake",1)["document_sha256"]!=sha or
                reopened.read_revision(
                pid,"InstalledNativePNG",1)["data"]["png_sha256"]!=
                sampled["png_sha256"]):
            raise RuntimeError("Installed source or derived SHA changed on restart")
        recovery=DurableRenderIntentionQueue(
            reopened,ask_native=lambda _:False).reconcile_restart(
                pid,"InstalledWorkerIntent")
        if (recovery["status"]!=RECOVERY or
                recovery["renderer_worker_authorized"] is not False):
            raise RuntimeError("Installed prior OS review replayed after restart")
        if __import__("sys").stdout is not None:
            print("NVP_PLAN02D_INSTALLED_SOURCE_RASTER_RESTART_PASS="+sha,flush=True)
        return 0
