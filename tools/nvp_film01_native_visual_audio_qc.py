"""Independent quality-control observations for a genuine 30s NVP export.

Technical validation of all original frame/source hashes, original
audio alignment and cue; creative diagnostics across real sampled
pixel images and PCM levels. Technical acceptance != artistic approval,
a passed preview != a physically installed AVI player or a DCI DCP.
This tool never supplies replacement pixels or modifies sources.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import math
import wave
from zipfile import ZipFile
import numpy as np
from PIL import Image

FORMAT="nvp.film01.native_original_visual_sound_qc.v1"
FPS=24
SAMPLE_RATE=48000
SAMPLES_PER_FRAME=2000
TOTAL_FRAMES=720
SAMPLE_FRAMES=(0,12,24,60,120,180,228,239,240,252,300,360,
               420,468,479,480,492,540,600,623,624,636,660,708,719)
CUT_FRAMES=(240,480)
CUE_START=624
CUE_END=636
BASELINE_EVENT="BeaconSignalRestored"


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def inspect_original_nvp_film(source_zip,report_json,*,require_complete=True):
    """Observe exactly the real source-authored visual and audio derivative.

    A partial six-frame smoke cannot pass as the original full film.
    No heuristic visual threshold automatically rejects intentional
    abstraction/darkness; metrics guide a human review.
    """
    source=Path(source_zip)
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError("Genuine NVP source render archive missing")
    if type(require_complete) is not bool or not require_complete:
        raise PermissionError("Original FILM01 QC requires full 720-frame source")
    with ZipFile(source) as z:
        receipt=json.loads(z.read("original_30s_preview_receipt.json"))
        rows=receipt.get("frame_receipts")
        if (receipt.get("frames_rendered_from_usd")!=TOTAL_FRAMES or
                receipt.get("all_720_frames_really_rendered") is not True or
                receipt.get("exact_pcm_samples")!=SAMPLE_RATE*30 or
                receipt.get("dci_master_or_dcp_created") is not False or
                type(rows) is not list or len(rows)!=TOTAL_FRAMES):
            raise PermissionError("30-second picture/PCM is incomplete")
        names={name for name in z.namelist()}
        if len(names)!=TOTAL_FRAMES+3:
            raise PermissionError("Unexpected or duplicate original source ZIP entries")
        expected={f"preview_frames/frame_{i:04d}.png"
                  for i in range(TOTAL_FRAMES)}
        expected.update({"audio/original_source_review_48k_mono.wav",
                         "original_30s_preview_receipt.json","README.txt"})
        if names!=expected:
            raise PermissionError("Source archive does not cover all exact output frames")
        counts={}
        take_per_shot={}
        hash_per_shot={}
        for i,row in enumerate(rows):
            if (type(row) is not dict or row.get("frame_zero")!=i or
                    not isinstance(row.get("frame_png_sha256"),str) or
                    len(row["frame_png_sha256"])!=64 or
                    not isinstance(row.get("original_source_take_sha256"),str)):
                raise PermissionError("Source frame order/hash is incomplete")
            shot=i//240
            sid=row.get("source_segment_id")
            if sid!=f"Relay30Cut{shot}":
                raise PermissionError("Actual original source film cut identity changed")
            take=take_per_shot.setdefault(shot,row["original_source_take_sha256"])
            if row["original_source_take_sha256"]!=take:
                raise PermissionError("Source Take unexpectedly changed inside locked shot")
            ids=row.get("source_audio_event_ids")
            if type(ids) is not list:
                raise PermissionError("Exact original native audio event custody missing")
            if ((BASELINE_EVENT in ids)!=(CUE_START<=i<CUE_END)):
                raise PermissionError("The source-linked signal event is not precisely at output 26s")
            counts[shot]=counts.get(shot,0)+1
            hash_per_shot.setdefault(shot,set()).add(row["frame_png_sha256"])
        if len(set(take_per_shot.values()))!=3 or counts!={0:240,1:240,2:240}:
            raise PermissionError("Original film lacks three distinct immutable source Takes")
        wav=z.read("audio/original_source_review_48k_mono.wav")
        if _digest(wav)!=receipt["audio_wav_sha256"]:
            raise PermissionError("Source WAV SHA changed")
        with wave.open(BytesIO(wav),"rb") as w:
            if (w.getnchannels()!=1 or w.getsampwidth()!=2 or
                    w.getframerate()!=SAMPLE_RATE or
                    w.getnframes()!=TOTAL_FRAMES*SAMPLES_PER_FRAME):
                raise PermissionError("Audible source not exactly native 30s/24fps/48k PCM")
            pcm=w.readframes(w.getnframes())
        if len(pcm)!=TOTAL_FRAMES*SAMPLES_PER_FRAME*2:
            raise PermissionError("Original source PCM was truncated")
        samples=np.frombuffer(pcm,dtype="<i2").astype(np.float64)
        peak=int(np.max(np.abs(samples)))
        clipped=int(np.count_nonzero(np.abs(samples)>=32767))
        rms=float(np.sqrt(np.mean(samples*samples)))
        def sound_span(start_second,end_second):
            block=samples[int(start_second*SAMPLE_RATE):int(end_second*SAMPLE_RATE)]
            diffs=np.diff(block)
            return {
                "peak_abs_pcm16":int(np.max(np.abs(block))) if len(block) else 0,
                "rms_pcm16":round(float(np.sqrt(np.mean(block*block))),2)
                    if len(block) else 0,
                "mean_adjacent_sample_delta":round(
                    float(np.mean(np.abs(diffs))),2) if len(diffs) else 0,
                "fraction_near_silence":round(float(np.mean(np.abs(block)<16)),5)
                    if len(block) else 1,
            }
        audio_blocks=[
            {"shot":i+1,"start_second":i*10,
             **sound_span(i*10,(i+1)*10)} for i in range(3)]
        cue_before=sound_span(25.5,26.0)
        cue_during=sound_span(26.0,26.5)
        cue_after=sound_span(26.5,27.0)
        measures=[]
        for frame in SAMPLE_FRAMES:
            row=rows[frame]
            png=z.read(f"preview_frames/frame_{frame:04d}.png")
            if _digest(png)!=row["frame_png_sha256"]:
                raise PermissionError("Sampled original visual source pixels changed")
            with Image.open(BytesIO(png)) as im:
                im.load()
                if im.format!="PNG" or im.mode!="RGB" or im.size!=(640,360):
                    raise PermissionError("Actual source image is not genuine expected RGB PNG")
                pix=np.asarray(im,dtype=np.uint8).astype(np.float32)/255.
            luminosity=(.2126*pix[:,:,0]+.7152*pix[:,:,1]+.0722*pix[:,:,2])
            measures.append({
                "frame_zero":frame,
                "source_segment_id":row["source_segment_id"],
                "source_take_sha256":row["original_source_take_sha256"],
                "png_sha256":row["frame_png_sha256"],
                "virtual_fx_shader_used":row.get("virtual_light_shader_used") is True,
                "RGB_mean_8bit":[round(float(x),2) for x in
                                  np.mean(pix,axis=(0,1))*255],
                "luminance_p10_p50_p90":[round(float(x),5) for x in
                                         np.percentile(luminosity,[10,50,90])],
                "fraction_nearly_black":round(float(
                    np.mean(luminosity<.01)),5),
                "fraction_nearly_white":round(float(
                    np.mean(luminosity>.98)),5),
                "fraction_non_black":round(float(
                    np.mean(luminosity>.01)),5),
                "sampled_RGB_pixel_data":pix,
            })
        comparisons=[]
        pairs=[(0,24),(24,120),(120,239),(239,240),(240,360),
               (360,479),(479,480),(480,600),(600,719)]
        indexed={r["frame_zero"]:r for r in measures}
        for a,b in pairs:
            if a not in indexed or b not in indexed:
                continue
            x=indexed[a]["sampled_RGB_pixel_data"]
            y=indexed[b]["sampled_RGB_pixel_data"]
            comparisons.append({
                "frame_pair":[a,b],
                "is_hard_cut_boundary":b in CUT_FRAMES,
                "mean_absolute_RGB_8bit_change":round(
                    float(np.mean(np.abs(x-y))*255),4),
                "fraction_pixels_changed_gt_8bit":round(
                    float(np.mean(np.any(
                        np.abs(x-y)>8/255,axis=2))),6),
            })
        for m in measures:del m["sampled_RGB_pixel_data"]
        warnings=[]
        if any(len(x)<=1 for x in hash_per_shot.values()):
            warnings.append("STATIC_SHOT_OR_FROZEN_ANIMATION_INSPECT_SOURCE_TIME")
        if any(x["fraction_non_black"]<.01 for x in measures):
            warnings.append("VERY_SPARSE_RENDERED_PIXEL_COVERAGE_CHECK_CAMERA_AND_GEOMETRY")
        if any(x["fraction_nearly_white"]>.30 for x in measures):
            warnings.append("BRIGHT_PIXEL_CLIPPING_CHECK_EXPOSURE_AND_VIRTUAL_LIGHT_GAIN")
        if clipped>0:
            warnings.append("SOURCE_PCM_PEAK_CLIPPING")
        if peak<16 or rms<5:
            warnings.append("SOURCE_PCM_NEAR_SILENCE")
        if cue_during["mean_adjacent_sample_delta"]<=cue_before["mean_adjacent_sample_delta"]:
            warnings.append("SIGNAL_CHIRP_AUDIBLE_SPECTRAL_DISTINCTION_NOT_OBVIOUS")
        if receipt.get("source_geometry_asset_profiles") and any(
            item.get("geometry_is_abstract_proxy")
            for item in receipt["source_geometry_asset_profiles"]):
            warnings.append("INTENTIONALLY_ABSTRACT_CUBE_SPHERE_GEOMETRY_NOT_HUMAN_CHARACTER_ACCEPTED")
        observed={
            "format":FORMAT,"source_archive_sha256":_digest(source.read_bytes()),
            "technical_native_source_frame_count":TOTAL_FRAMES,
            "original_30s_duration_verified":True,
            "exact_three_take_cut_ids_verified":True,
            "cut_frames":list(CUT_FRAMES),
            "source_film_at_24fps":True,
            "source_PNG_all_frame_receipts_present":True,
            "sampled_picture_frames":measures,
            "unique_source_image_hashes_by_shot":{
                str(i+1):len(hash_per_shot[i]) for i in range(3)},
            "visual_motion_and_cut_differences":comparisons,
            "audio":{
                "source_sample_rate":SAMPLE_RATE,
                "source_channels":1,"bit_depth":16,
                "total_original_pcm_samples":len(samples),
                "whole_film_peak_abs_pcm16":peak,
                "whole_film_rms_pcm16":round(rms,2),
                "clipped_sample_count":clipped,
                "per_shot":audio_blocks,
                "cue_source_event_start_frame":CUE_START,
                "cue_source_event_end_frame_exclusive":CUE_END,
                "cue_before":cue_before,"cue_during":cue_during,
                "cue_after":cue_after,
                "signal_event_at_26s_proven_by_actual_native_receipts":True,
            },
            "source_geometry_asset_profiles":receipt.get("source_geometry_asset_profiles"),
            "virtual_fx_enabled":bool(receipt.get("virtual_gold_and_sun_fx_applied_to_render")),
            "observed_warnings_not_automatic_artistic_rejection":warnings,
            "human_visual_judgment_required":True,
            "actual_external_player_watched":False,
            "movie_or_DCI_certified":False,
            "photorealistic_actors_present":False,
            "native_installed_screen_speaker_verified":False,
        }
    dest=Path(report_json)
    if not dest.is_absolute() or dest.exists() or dest.is_symlink():
        raise PermissionError("Native QC must write one fresh absolute report")
    dest.write_text(json.dumps(observed,indent=2,sort_keys=True,allow_nan=False)+"\n")
    return observed
