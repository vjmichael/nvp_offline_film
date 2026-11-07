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
import struct
import tempfile

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


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
    # This is NOT a physical two-input sync claim. It verifies that the
    # installed binary includes the actual PortAudio adapter and its DLL,
    # rather than passing from a Python environment without native inputs.
    import sounddevice as sd
    if not callable(getattr(sd,"RawInputStream",None)):
        raise RuntimeError("Installed native independent microphone adapter missing")
    sd.query_hostapis()
    T=TICKS_PER_SECOND
    with tempfile.TemporaryDirectory(prefix="nvp-installed-data-av-") as root:
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
        scene=OpenUSDSceneBridge(index)
        scene.publish(pid,"native_scene",prims=[
            {"path":"/World/Speaker","role":"actor","position":[3,0,0]},
            {"path":"/World/CameraA","role":"camera","position":[0,0,0]},
            {"path":"/World/CameraB","role":"camera","position":[7,0,0]},
        ],curves=[],native_schemas=True)
        timeline=TemporalLedger(index)
        timeline.publish(pid,"native_sound_events",[{
            "event_id":"speech","event_kind":"dialogue",
            "subject_id":"Speaker","start_tick":0,"end_tick":T,
            "source_id":"captured_dialogue","source_revision":1,
            "payload":{"usd_prim_path":"/World/Speaker","gain":1.0},
        }],duration_tick=2*T)
        freezes=OpenUSDTakeCapture(
            index,verify_creator_action=lambda event,scope:
            event=="approved" and scope["operation"]==
            "nvp.freeze.usd_temporal_take.v1")
        take=freezes.freeze(pid,"immutable_scene_take",
            scene_id="native_scene",scene_revision=1,
            timeline_id="native_sound_events",timeline_revision=1,
            sample_ticks=[0,T],creator_event="approved")
        original_take_sha=take["document_sha256"]
        bridge=TrustedDesktopCameraBridge(
            index,origin="http://127.0.0.1:7777")
        window=_Window()
        bridge._attach_window(window)
        try:
            catalog=bridge.data_av_catalog(pid)
            if (catalog["ffmpeg_runtime_required"] is not False or
                len(catalog["takes"])!=1):
                raise RuntimeError("Installed native Digital Take catalog invalid")
            mixes=[]
            for listener in ("/World/CameraA","/World/CameraB"):
                response=bridge.data_av_begin({
                    "project_id":pid,"take_id":"immutable_scene_take",
                    "take_document_sha256":original_take_sha,
                    "listener_path":listener,"first_sample":0,
                    "direction":"forward",
                })
                if response["status"]!="READY":
                    raise RuntimeError("Installed source-local native review denied")
                session=response["session_id"]
                item=bridge.data_av_audio_window(session,0,2048)
                if (item["status"]!="READY" or
                    item["sample_count"]!=2048 or
                    item["source_modified"] is not False or
                    item["film_master_approved"] is not False):
                    raise RuntimeError("Installed source PCM output invalid")
                scene=bridge.data_av_scene_at(session,0)
                if (scene["spatial_audio"]["bindings"][0][
                    "usd_schema"]!="UsdMediaSpatialAudio"):
                    raise RuntimeError("Installed OpenUSD spatial source missing")
                mixes.append(item["audio_sha256"])
                if bridge.data_av_stop(session)["status"]!="STOPPED":
                    raise RuntimeError("Installed native stop failed")
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
            # Batch 3: independently prove the INSTALLED executable can
            # create real composed source USD surface geometry, evaluate
            # native ACES2 SDR PNG16 and persist a real full-float ACEScg
            # OpenEXR frame. This does not need actual display hardware.
            from backend.nvp_openusd_assets import OpenUSDAssetRegistry
            from backend.nvp_exact_time_shots import ExactTimeShotSequence
            from backend.nvp_native_color_decisions import NativeColorDecisions
            from backend.nvp_native_aces_color import NativeACESColor,policy
            from backend.nvp_native_scene_linear_exr import NativeSceneLinearEXR
            geometry=OpenUSDAssetRegistry(index).publish(
                pid,"smoke_source_material",shape="cube",size_m=2.,
                preview_material={
                    "base_color_rgb":[.25,.5,.75],
                    "roughness":.35,"metallic":.3})
            color_scene=OpenUSDSceneBridge(index)
            color_scene.publish(pid,"smoke_color_world",prims=[
                {"path":"/World/ColorActor","role":"actor",
                 "position":[0,0,0]},
                {"path":"/World/ColorCamera","role":"camera",
                 "position":[0,0,5]},
                {"path":"/World/ColorLight","role":"light",
                 "position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/ColorActor","asset_id":"smoke_source_material",
                "asset_revision":1}])
            ExactTimeShotSequence(index).publish(
                pid,"smoke_color_shots",scene_id="smoke_color_world",
                scene_revision=1,duration_tick=str(T),shots=[{
                    "shot_id":"ColorShot",
                    "camera_path":"/World/ColorCamera",
                    "start_tick":"0","end_tick":str(T),
                    "pattern":"continuous"}])
            color_take=freezes.freeze(
                pid,"smoke_color_take",
                scene_id="smoke_color_world",scene_revision=1,
                timeline_id="smoke_color_shots",timeline_revision=1,
                sample_ticks=[0],creator_event="approved")
            grade=NativeColorDecisions(index).publish(
                pid,"smoke_color_grade",take_id="smoke_color_take",
                take_sha256=color_take["document_sha256"],parameters={
                    "exposure_stops":0.1,"contrast":1.,
                    "saturation":1.,"temperature_kelvin":6500.,
                    "tint_magenta_green":0.})
            info,_=policy()
            png,aces=NativeACESColor(index).process_verified_usd_scene(
                pid,"smoke_color_take",color_take["document_sha256"],
                "smoke_color_grade",1,grade["document_sha256"],
                tick=0,camera_path="/World/ColorCamera",
                expected_config_sha256=info["configuration_sha256"])
            if (png[24:26]!=bytes((16,2)) or
                aces["cinema_master_approved"] is not False or
                aces["ffmpeg_used"] is not False):
                raise RuntimeError("Installed native source ACES2 PNG16 failed")
            exr=NativeSceneLinearEXR(index).write(
                pid,"smoke_color_take",color_take["document_sha256"],
                "smoke_color_grade",1,grade["document_sha256"],
                tick=0,camera_path="/World/ColorCamera",
                expected_config_sha256=info["configuration_sha256"],
                output_file=Path(root)/"installed_color_source.exr")
            if (exr["working_space"]!="ACEScg" or
                exr["float_bits_per_component"]!=32 or
                exr["original_modified"] is not False or
                index.read_revision(pid,"smoke_color_take",1)[
                    "document_sha256"]!=color_take["document_sha256"]):
                raise RuntimeError("Installed source ACEScg EXR32 failed")
            if __import__("sys").stdout is not None:
                print("DATA_AV01_INSTALLED_NATIVE_SOURCE_AND_ACES_PASS",
                      original_take_sha,mixes[0],mixes[1],
                      aces["png16_sha256"],exr["output_exr_sha256"])
            return 0
        finally:
            bridge._close()
