"""DATA-AV-01: actual packaged NVP.exe standalone source AV acceptance.

This is a CLI SMOKE ENTRY for the packaged desktop executable, not part of
the human editing workflow. Native OpenUSD scene, temporal events and recorded
PCM are rebuilt in a disposable project. FFmpeg and BWF are NOT available or
required. It proves the binary contains the authoring/reader code but does
not substitute for audible GUI-device acceptance on physical Windows.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import math
import os
import struct
import tempfile

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


def _native_stage(stage):
    """Fsynced CI-only receipt to locate fatal native DLL crashes without source data."""
    target = os.environ.get("NVP_SMOKE_DIAGNOSTIC_PATH")
    if not target:
        return
    path = Path(target)
    if path.is_symlink():
        raise RuntimeError("Refusing symlink diagnostic target")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("NVP_SMOKE_STAGE native_" + stage + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class _Window:
    def __init__(self):
        self.prompts=0
    def get_current_url(self):
        return "http://127.0.0.1:7777/"
    def create_confirmation_dialog(self,title,message):
        self.prompts+=1
        if "FFmpeg" not in message or "Original" not in message:
            raise RuntimeError("Installed creator consent missing native source scope")
        return True


def run_installed_data_av_smoke():
    T=TICKS_PER_SECOND
    _native_stage("enter")
    with tempfile.TemporaryDirectory(prefix="nvp-installed-data-av-") as root:
        _native_stage("before_studio")
        studio=Studio(Path(root)/"native_sound.sqlite3")
        project=studio.create_project("Native frozen 3D sound","No FFmpeg runtime")
        pid=project["id"]
        index=FilmIndex(studio)
        sources=RecordedSoundSources(index)
        sample=struct.pack("<"+"h"*24000,*(
            int(12000*math.sin(2*math.pi*440*i/48000))
            for i in range(24000)))
        sound=sources.publish(pid,"captured_dialogue",[sample[:24000],sample[24000:]])
        original=sha256(sample).hexdigest()
        _native_stage("before_scene_bridge")
        scene=OpenUSDSceneBridge(index)
        _native_stage("before_scene_publish")
        scene.publish(pid,"native_scene",prims=[
            {"path":"/World/Speaker","role":"actor","position":[3,0,0]},
            {"path":"/World/CameraA","role":"camera","position":[0,0,0]},
            {"path":"/World/CameraB","role":"camera","position":[7,0,0]},
        ],curves=[],native_schemas=True)
        _native_stage("after_scene_publish")
        timeline=TemporalLedger(index)
        timeline.publish(pid,"native_sound_events",[{
            "event_id":"speech","event_kind":"dialogue",
            "subject_id":"Speaker","start_tick":0,"end_tick":T,
            "source_id":"captured_dialogue","source_revision":1,
            "payload":{"usd_prim_path":"/World/Speaker","gain":1.0},
        }],duration_tick=2*T)
        _native_stage("after_timeline_publish")
        freezes=OpenUSDTakeCapture(
            index,verify_creator_action=lambda event,scope:
            event=="approved" and scope["operation"]==
            "nvp.freeze.usd_temporal_take.v1")
        take=freezes.freeze(pid,"immutable_scene_take",
            scene_id="native_scene",scene_revision=1,
            timeline_id="native_sound_events",timeline_revision=1,
            sample_ticks=[0,T],creator_event="approved")
        original_take_sha=take["document_sha256"]
        _native_stage("after_take_freeze")
        bridge=TrustedDesktopCameraBridge(
            index,origin="http://127.0.0.1:7777")
        window=_Window()
        bridge._attach_window(window)
        try:
            _native_stage("before_catalog")
            catalog=bridge.data_av_catalog(pid)
            if (catalog["ffmpeg_runtime_required"] is not False or
                len(catalog["takes"])!=1):
                raise RuntimeError("Installed native Digital Take catalog invalid")
            mixes=[]
            for listener in ("/World/CameraA","/World/CameraB"):
                _native_stage("before_begin")
                response=bridge.data_av_begin({
                    "project_id":pid,"take_id":"immutable_scene_take",
                    "take_document_sha256":original_take_sha,
                    "listener_path":listener,"first_sample":0,
                    "direction":"forward",
                })
                if response["status"]!="READY":
                    raise RuntimeError("Installed source-local native review denied")
                session=response["session_id"]
                _native_stage("before_audio_window")
                item=bridge.data_av_audio_window(session,0,2048)
                if (item["status"]!="READY" or
                    item["sample_count"]!=2048 or
                    item["source_modified"] is not False or
                    item["film_master_approved"] is not False):
                    raise RuntimeError("Installed source PCM output invalid")
                _native_stage("before_scene_at")
                scene=bridge.data_av_scene_at(session,0)
                if (scene["spatial_audio"]["bindings"][0][
                    "usd_schema"]!="UsdMediaSpatialAudio"):
                    raise RuntimeError("Installed OpenUSD spatial source missing")
                mixes.append(item["audio_sha256"])
                if bridge.data_av_stop(session)["status"]!="STOPPED":
                    raise RuntimeError("Installed native stop failed")
            _native_stage("after_two_listeners")
            if (mixes[0]==mixes[1] or window.prompts!=2 or
                sha256(sources.read(
                    pid,"captured_dialogue",1,0,2048)).hexdigest()!=
                sha256(sample[:4096]).hexdigest() or
                index.read_revision(
                    pid,"immutable_scene_take",1)["document_sha256"]!=
                    original_take_sha or
                sha256(b"".join(sources.read(
                    pid,"captured_dialogue",1,p,min(2048,24000-p))
                    for p in range(0,24000,2048))).hexdigest()!=original):
                raise RuntimeError("Installed take/sound mutated or listeners identical")
            if __import__("sys").stdout is not None:
                print("DATA_AV01_INSTALLED_NATIVE_SOURCE_PASS",
                      original_take_sha,mixes[0],mixes[1])
            return 0
        finally:
            bridge._close()
