"""WO6-07F: real pixel-rendered OpenUSD editorial windows with exact PCM at 24fps.

This is a bounded *preview* using NVP's existing scene-linear CPU rasterizer,
not Hydra photometric parity, a DCP, a finished master or a claimed continuous
24fps installed acceptance. Multiple finite windows can be scheduled by the
desktop's audio-driven clock; an underrun stops, never fakes playback.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO
import json
import math
import time
import wave

from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly,FORMAT as EDIT_FORMAT
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_wo6_07e_source_review import (
    sample_editorial_source,SAMPLES_PER_FRAME,SAMPLE_RATE,MAX_OUTPUT_FRAME)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.wo6_07f.actual_rendered_frame_pcm_window.v1"
FPS=24
TICKS_PER_FRAME=TICKS_PER_SECOND//FPS
MAX_FRAMES=6
MAX_PNG_BYTES=750000
MAX_WINDOW_WIRE_BYTES=6*1024*1024
MAX_AV_RENDER_WALL_SECONDS=90


def _encode_real_raster(rgba,proof):
    """Display-only sRGB PNG from authentic finite NVP source-linear pixels."""
    import numpy as np
    from PIL import Image
    if (getattr(rgba,"dtype",None)!=np.dtype("float32") or
            getattr(rgba,"ndim",None)!=3 or rgba.shape!=(360,640,4) or
            not np.isfinite(rgba).all() or
            not np.allclose(rgba[:,:,3],1.,rtol=0,atol=1e-6) or
            proof["source_geometry_triangles"]<1 or
            proof["rasterized_triangles"]<1 or
            proof.get("unclipped_linear_float_output") is not True or
            proof.get("source_modified") is not False):
        raise RuntimeError("No genuine, bounded, visibly rasterized 3D source pixels")
    # No hidden grading or color-management claim: a preview-only standard
    # transfer is applied to the already rendered working-space RGB.
    rgb=np.clip(rgba[:,:,:3],0.,1.)
    srgb=np.where(rgb<=.0031308,rgb*12.92,
                  1.055*np.power(rgb,1./2.4)-.055)
    pixels=np.ascontiguousarray(
        np.rint(np.clip(srgb,0.,1.)*255),dtype=np.uint8)
    out=BytesIO()
    Image.fromarray(pixels,"RGB").save(out,format="PNG",optimize=False)
    png=out.getvalue()
    if not 100<len(png)<=MAX_PNG_BYTES:
        raise RuntimeError("Rendered source PNG violates review limit")
    with Image.open(BytesIO(png)) as check:
        check.load()
        if check.format!="PNG" or check.size!=(640,360) or check.mode!="RGB":
            raise RuntimeError("Rendered original picture failed PNG readback")
        if check.tobytes()!=pixels.tobytes():
            raise RuntimeError("Pixel renderer image differs after serialization")
    return {
        "frame_png_sha256":sha256(png).hexdigest(),
        "source_linear_float_sha256":proof["scene_linear_rgba_sha256"],
        "pixel_width":640,"pixel_height":360,
        "renderer":"NVP native first-party OpenUSD CPU scene-linear raster",
        "hydra_pixels_verified":False,
        "photometric_lighting_calibrated":False,
        "renderer_gpu_offload_used":False,
        "color_display_transform":"approximate uncalibrated linear Rec709 to sRGB",
        "real_source_mesh_triangles":proof["source_geometry_triangles"],
        "actual_rasterized_triangles":proof["rasterized_triangles"],
        "frame_image_data_url":"data:image/png;base64,"+
                               base64.b64encode(png).decode("ascii"),
    }


def rendered_source_window(index,project_id,edit_id,edit_revision,edit_sha,
                           first_frame,count,*,camera_path=None,
                           sound_timeline_id=None,sound_timeline_revision=None,
                           sound_timeline_sha256=None):
    if not isinstance(index,FilmIndex):
        raise TypeError("A real first-party NVP source index is required")
    _require_pid(project_id)
    _id(edit_id,"immutable original source edit")
    _sha(edit_sha)
    if (type(edit_revision) is not int or edit_revision<1 or
            type(first_frame) is not int or not 0<=first_frame<MAX_OUTPUT_FRAME or
            type(count) is not int or not 1<=count<=MAX_FRAMES or
            (camera_path is not None and
             (type(camera_path) is not str or
              not camera_path.startswith("/World/") or len(camera_path)>240))):
        raise ValueError("Exact bounded original rendered picture/audio window required")
    if (sound_timeline_id is None)!=(sound_timeline_revision is None) or (
            (sound_timeline_id is None)!=(sound_timeline_sha256 is None)):
        raise ValueError("Sound source must supply an exact ID, revision and SHA together")
    reader=SlateSequenceAssembly(
        DigitalSlateBranches(index,verify_editor_action=lambda *_:False),
        verify_editor_action=lambda *_:False)
    cut=reader.open_edit(project_id,edit_id,edit_revision)
    if (cut["kind"]!="edit" or cut["data"].get("format")!=EDIT_FORMAT or
            cut["document_sha256"]!=edit_sha):
        raise PermissionError("Original rendered editorial source revision changed")
    duration=cut["data"]["duration_tick"]
    # Continuous 24fps is undefined for sub-frame hard cuts; we must not
    # round/move an original edit boundary in the name of playback.
    if duration%TICKS_PER_FRAME or any(
            seg[key]%TICKS_PER_FRAME for seg in cut["data"]["segments"]
            for key in ("timeline_start_tick","timeline_end_tick",
                        "source_in_tick","source_out_tick")):
        raise PermissionError("Editorial cut requires actual 24fps frame-aligned source intervals")
    if (first_frame+count)*TICKS_PER_FRAME>duration:
        raise ValueError("Rendered window exceeds actual committed editorial length")
    rendered=[]
    combined_samples=bytearray()
    begins=time.monotonic()
    rasterizer=NativeSceneLinearRaster(index)
    for frame in range(first_frame,first_frame+count):
        # This source-level window explicitly restricts audio to ONE frame.
        # Each original Take is independently reselected across hard cuts.
        sample=sample_editorial_source(
            index,project_id,edit_id,edit_revision,edit_sha,frame,
            sound_timeline_id=sound_timeline_id,
            sound_timeline_revision=sound_timeline_revision,
            sound_timeline_sha256=sound_timeline_sha256,
            audio_window_frames=1)
        if (int(sample["output_film_time_tick"])!=frame*TICKS_PER_FRAME or
                sample["output_frame_zero"]!=frame or
                sample["source_take_sha256"]!=
                    sample["source_projection"]["source_take_sha256"] or
                sample["original_source_modified"] is not False):
            raise PermissionError("Original scene/source/audio frame projection changed")
        if sample["source_projection"].get("source_shot_id") is not None:
            # The first-party source raster reads a frozen Take. A native
            # shot-local override is a stronger authored presentation;
            # silently displaying unmodified Take pixels as that shot
            # would be counterfeit editorial playback.
            raise RuntimeError(
                "Native shot-local OpenUSD overrides require their own composed raster path")
        cameras=sorted(p["prim_path"] for p in sample["scene_poses"]
                       if p["role"]=="camera")
        active_camera=camera_path or (cameras[0] if len(cameras)==1 else None)
        if active_camera not in cameras:
            raise PermissionError("Exactly one source-authorized camera path is required")
        first=time.monotonic()
        color,proof=rasterizer.render(
            project_id,sample["source_take_id"],
            sample["source_take_sha256"],
            tick=int(sample["source_film_time_tick"]),
            camera_path=active_camera)
        image=_encode_real_raster(color,proof)
        original_take=index.read_revision(
            project_id,sample["source_take_id"],1)
        if (original_take["document_sha256"]!=sample["source_take_sha256"] or
                proof["original_take_sha256"]!=sample["source_take_sha256"] or
                proof["time_tick"]!=sample["source_film_time_tick"] or
                proof["scene_document_sha256"]!=
                    original_take["data"]["scene_document_sha256"]):
            # OpenUSD visual pose records intentionally omit the source
            # scene SHA; reopen the authentic frozen Take instead of
            # guessing an absent field from UI-only pose metadata.
            raise PermissionError("Rendered original pixels and source Film Time diverge")
        if sample["audio_data_url"]:
            _,base64data=sample["audio_data_url"].split(",",1)
            audio_bytes=base64.b64decode(base64data,validate=True)
            if sha256(audio_bytes).hexdigest()!=sample["source_pcm_wav_sha256"]:
                raise PermissionError("Original PCM WAV bytes differ from native source receipt")
            with wave.open(BytesIO(audio_bytes),"rb") as src:
                if (src.getnchannels()!=1 or src.getsampwidth()!=2 or
                        src.getframerate()!=SAMPLE_RATE or
                        src.getnframes()!=SAMPLES_PER_FRAME):
                    raise RuntimeError("An exact source audio frame was not available")
                frame_samples=src.readframes(SAMPLES_PER_FRAME)
        else:
            if (not sample["zero_audio_when_no_source"] or
                    sample["source_pcm_tracks"]):
                raise PermissionError("Unverified silence would hide actual original audio")
            frame_samples=bytes(SAMPLES_PER_FRAME*2)
        if len(frame_samples)!=SAMPLES_PER_FRAME*2 or (
                sample["frame_spans_edit_boundary"]):
            raise RuntimeError("Original audio boundaries not 24fps source-aligned")
        combined_samples.extend(frame_samples)
        rendered.append({
            "output_frame_zero":frame,
            "output_film_time_tick":str(frame*TICKS_PER_FRAME),
            "original_source_tick":sample["source_film_time_tick"],
            "source_segment_id":sample["source_projection"]["segment_id"],
            "source_take_id":sample["source_take_id"],
            "source_take_sha256":sample["source_take_sha256"],
            "original_camera_path":active_camera,
            "source_review_sha256":sample["source_review_sha256"],
            "recorded_pcm_source_tracks":sample["source_pcm_tracks"],
            "actual_render_wall_ms":round((time.monotonic()-first)*1000,1),
            **image,
        })
        if time.monotonic()-begins>MAX_AV_RENDER_WALL_SECONDS:
            raise RuntimeError("Native source rendering exceeded bounded preview wall time")
    wav_bytes=BytesIO()
    with wave.open(wav_bytes,"wb") as out:
        out.setframerate(SAMPLE_RATE)
        out.setnchannels(1)
        out.setsampwidth(2)
        out.writeframes(bytes(combined_samples))
    audio=wav_bytes.getvalue()
    if len(combined_samples)!=count*SAMPLES_PER_FRAME*2:
        raise RuntimeError("Rendered picture count and source audio samples differ")
    result={
        "format":FORMAT,"project_id":project_id,
        "edit_id":edit_id,"edit_revision":edit_revision,
        "edit_sha256":edit_sha,
        "first_frame_zero":first_frame,
        "count":count,"fps_num":FPS,"fps_den":1,
        "audio_samples_per_frame":SAMPLES_PER_FRAME,
        "source_audio_rate":SAMPLE_RATE,
        "actual_audio_sample_count":count*SAMPLES_PER_FRAME,
        "actual_recorded_sound_not_mastered":True,
        "source_audio_wav_sha256":sha256(audio).hexdigest(),
        "source_audio_wav_data_url":"data:audio/wav;base64,"+
            base64.b64encode(audio).decode("ascii"),
        "images":rendered,
        "real_original_usd_pixels_rendered":True,
        "source_rasterizer_only_not_hydra":True,
        "color_management_not_reference_approved":True,
        "audio_clock_verified_by_installed_browser":False,
        "continuous_24fps_installed_acceptance":False,
        "rendered_window_count":count,
        "render_wall_seconds":round(time.monotonic()-begins,3),
        "source_modified":False,"film_delivered":False,
        "native_worker_authorized":False,"FFmpeg_used":False,
    }
    result["window_receipt_sha256"]=sha256(json.dumps({
        k:(v if k!="images" else [
            {ik:iv for ik,iv in image.items() if ik!="frame_image_data_url"}
            for image in v])
        for k,v in result.items()
        if k!="source_audio_wav_data_url"
    },sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    if len(json.dumps(result))>MAX_WINDOW_WIRE_BYTES:
        raise RuntimeError("Rendered picture/audio window exceeds trusted desktop IPC bound")
    if index.read_revision(project_id,edit_id,edit_revision)[
            "document_sha256"]!=edit_sha:
        raise PermissionError("Source edit mutated during native rendering")
    return result
