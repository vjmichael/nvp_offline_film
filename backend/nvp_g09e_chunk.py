"""G09-E real bounded 10-second 24fps MJPEG/48k stereo native film reels.

Film Time is GLOBAL. Each independently decodable AVI segment has a strictly
specified global [frame_start,frame_end) and exact 2000 PCM samples/frame.
A single original G06 Take/ActorID remains authoritative, regardless of
how many reels/worker restarts derive new output from it. One project can
have up to three hours of 24fps edit decisions without a 32-bit RIFF overrun.

The output is a segmented WORKING film with a separately verified playlist.
It is NOT advertised as one gapless professional codec, DCP or protected
feature-length playback. Ordinary original PCM above 64 MiB is admitted
through bounded SHA-verified SQLite pages. The native live-capture duration
and protected long-film worker remain independently limited.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path

from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_g08_native_avi import (
    SourceWorld,render_picture,_audio_frame,
    MjpegPcmAvi,verify_movie,TICKS_FRAME,TICKS_SAMPLE,
    AUDIO_HZ,AUDIO_BLOCK,FPS,MAX_OUTPUT_BYTES)
from backend.nvp_g09e_audio import finish_window

FRAMES_PER_CHUNK=240 # 10s: genuinely replayable AVI, no >4GiB RIFF
MAX_FRAMES=3*3600*FPS
MAX_CHUNKS=(MAX_FRAMES+FRAMES_PER_CHUNK-1)//FRAMES_PER_CHUNK
MAX_CHUNK_BYTES=80*1024*1024
MAX_TAKES_PER_WINDOW=24
FORMAT="nvp.g09e.native_reels.v1"
REQUIRED_DIGESTS=("edit_document_sha256","production_looks_sha256",
    "actor_performances_sha256","acoustic_looks_sha256","finishing_sha256")

def chunk_bounds(total_frames,index):
    if (type(total_frames) is not int or not 1<=total_frames<=MAX_FRAMES or
        type(index) is not int or not 0<=index<math.ceil(total_frames/FRAMES_PER_CHUNK)):
        raise ValueError("The proposed reel is outside the film")
    start=index*FRAMES_PER_CHUNK
    return start,min(total_frames,start+FRAMES_PER_CHUNK)

def check_assembly(assembly,total_frames,start,end,digests):
    if assembly.get("format")!="nvp.g07.non_destructive_edit.v1":
        raise RuntimeError("Original Film Time assembly cannot be opened")
    if assembly.get("source_media_modified") is not False:
        raise RuntimeError("Original Digital Takes changed")
    if (assembly["duration_tick"]!=total_frames*TICKS_FRAME or
        assembly.get("window")!=[start*TICKS_FRAME,end*TICKS_FRAME] or
        not 0<=start<end<=total_frames or
        end-start>FRAMES_PER_CHUNK):
        raise RuntimeError("A reel was not loaded from its exact film source time")
    if not 1<=len(assembly["original_takes"])<=MAX_TAKES_PER_WINDOW:
        raise ValueError("Too many original scenes participate in this reel")
    if (assembly.get("source_payload_budget_bytes",0)>256*1024*1024):
        raise ValueError("A film reel exceeds its original source memory budget")
    if (type(digests) is not dict or set(digests)!=set(REQUIRED_DIGESTS) or
        any(assembly[k]!=v for k,v in digests.items())):
        raise RuntimeError("Film source or director-approved decisions changed")
    from backend.nvp_int01c_source_contract import verify_render_assembly
    verify_render_assembly(assembly)
    return True

def source_digests(assembly):
    return {key:assembly[key] for key in REQUIRED_DIGESTS}

def _worlds(assembly,*,actors=False):
    worlds={tid:SourceWorld(take)
            for tid,take in assembly["original_takes"].items()}
    if actors:
        from backend.nvp_g09_actor_rig import ActorFrameEvaluator
        for tid,approved in assembly.get("actor_performances",{}).items():
            if tid not in worlds:continue
            if approved["performance"]["actors"]:
                # Visual skin/jaw positions are EXACT source-time evaluations,
                # but G09-B's short Take UsdSkel exporter is not falsely
                # described as full-length USD layer production here.
                worlds[tid].actor_frame_evaluator=ActorFrameEvaluator(
                    assembly["original_takes"][tid],approved)
    return worlds

def _pcm_mixer(assembly,worlds):
    if assembly.get("acoustic_looks"):
        from backend.nvp_g09c_native_audio import SpatialFilmMixer
        return SpatialFilmMixer(assembly,worlds)
    return None

def source_audio_window(assembly,worlds,start_sample,count,*,mixer=None):
    if (type(start_sample) is not int or type(count) is not int or
        start_sample<0 or not 1<=count<=48000):
        raise ValueError("Native source read is bounded to one second")
    end=(start_sample+count)*TICKS_SAMPLE
    if end>assembly["duration_tick"]:
        raise RuntimeError("Sound read would leave the original film")
    return (mixer.window(start_sample,count)[0] if mixer
            else _audio_frame(assembly,assembly["original_takes"],
                              start_sample,count))

def iter_source_pcm(assembly,start_frame,end_frame):
    """Yield full film source clock in max 1-second memory chunks."""
    if (type(start_frame) is not int or type(end_frame) is not int or
        not 0<=start_frame<end_frame<=MAX_FRAMES or
        end_frame-start_frame>FRAMES_PER_CHUNK):
        raise ValueError("Invalid source PCM reel")
    worlds=_worlds(assembly)
    mixer=_pcm_mixer(assembly,worlds)
    start=start_frame*2000;end=end_frame*2000
    for sample in range(start,end,48000):
        count=min(48000,end-sample)
        yield sample,source_audio_window(
            assembly,worlds,sample,count,mixer=mixer)

def render_reel(assembly,start_frame,end_frame,plan,output,*,progress=None,
                cancel=None):
    if (not hasattr(output,"write") or
        type(start_frame) is not int or type(end_frame) is not int or
        not 0<=start_frame<end_frame<=MAX_FRAMES or
        end_frame-start_frame>FRAMES_PER_CHUNK):
        raise ValueError("A native reel requires a bounded original film window")
    if not assembly.get("window")==[
        start_frame*TICKS_FRAME,end_frame*TICKS_FRAME]:
        raise RuntimeError("The reel is not source-bound to this Film Time")
    from backend.nvp_g09d_master import finish_picture
    from backend.nvp_g09_render import render_production_picture
    from backend.nvp_int01c_source_contract import verify_render_assembly
    verify_render_assembly(assembly)
    worlds=_worlds(assembly,actors=True)
    mixer=_pcm_mixer(assembly,worlds)
    decision=(assembly.get("approved_finishing") or {}).get("finishing")
    if decision and plan["target_integrated_lufs"]!=decision["audio"]["target_lufs"]:
        raise RuntimeError("The sound mastering revision is no longer approved")
    frames=end_frame-start_frame
    writer=MjpegPcmAvi(output,frames)
    for offset in range(frames):
        if cancel and cancel():raise InterruptedError("The director stopped the film export")
        index=start_frame+offset
        tick=index*TICKS_FRAME
        frame=(render_production_picture(assembly,worlds,tick) if
               assembly.get("production_looks") or
               assembly.get("actor_performances")
               else render_picture(assembly,worlds,tick))
        if decision:
            frame,_=finish_picture(frame,decision["color"])
        raw=source_audio_window(
            assembly,worlds,index*2000,2000,mixer=mixer)
        finished=finish_window(raw,plan,
            start_sample=index*2000,
            total_samples=assembly["duration_tick"]//TICKS_SAMPLE)
        writer.frame(frame,finished)
        if progress and (offset%12==0 or offset+1==frames):
            progress(offset+1,frames)
    receipt=writer.finish()
    receipt.update({
        "format":FORMAT,
        "start_frame":start_frame,"end_frame":end_frame,
        "start_tick":start_frame*TICKS_FRAME,
        "end_tick":end_frame*TICKS_FRAME,
        "audio_start_sample":start_frame*2000,
        "audio_end_sample":end_frame*2000,
        "sound_plan_sha256":sha256(_canonical(plan)).hexdigest(),
        "source_digests":source_digests(assembly),
        "original_film_untouched":True,
        "reel_size_bytes":receipt["output_bytes"],
        "working_deliverable_not_dcp":True})
    if receipt["output_bytes"]>MAX_CHUNK_BYTES:
        raise ValueError("Native film reel exceeds its output-size budget")
    return receipt

def _canonical(value):
    import json
    return json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=False,allow_nan=False).encode("utf8")

def inspect_reel(path,frames,*,expected_sha):
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise RuntimeError("The candidate film reel is missing or unsafe")
    if not 0<p.stat().st_size<=MAX_CHUNK_BYTES:
        raise RuntimeError("The original film reel exceeds its budget")
    result=verify_movie(p.read_bytes(),frames,expected_sha=expected_sha)
    if not result["verified"] or result["audio_samples_per_channel"]!=frames*2000:
        raise RuntimeError("The actual reel lost its sample/frame integrity")
    return result
