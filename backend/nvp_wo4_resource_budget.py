"""WO4 LF05 deterministic long-form resource admission and reel planning.

Plans 2–3 hour films as metadata, not frames in RAM. Figures are conservative
scratch envelopes, not benchmarks or duration guarantees. Caller owns the
host-selected local disk and must re-check its free space before each stage.
"""
from __future__ import annotations

from math import ceil
from pathlib import Path
import shutil

from backend.nvp_wo3_j2k_audit import PROFILES,MAX_CODESTREAM
from backend.nvp_production_journal import TICKS_PER_SECOND

FORMAT="nvp.wo4.production_resource_plan.v1"
MAX_REEL_FRAMES=7200
MAX_TOTAL_FRAMES=24*60*60*12 # twelve hours, not a tested duration
MAX_REELS=288
MIN_HEADROOM=2*1024**3
COPY_BLOCK=1024*1024

def plan_feature(*,frames,profile,channels=2,max_reel_frames=7200):
    if (type(frames) is not int or not 3<=frames<=MAX_TOTAL_FRAMES
            or profile not in PROFILES or
            channels not in (2,6,8) or type(channels) is not int or
            type(max_reel_frames) is not int or
            not 3<=max_reel_frames<=MAX_REEL_FRAMES):
        raise ValueError("Exact bounded feature frames/profile/channels required")
    width,height,_=PROFILES[profile]
    raw_frame_bytes=width*height*6
    reels=[]
    begin=0
    while begin<frames:
        end=min(frames,begin+max_reel_frames)
        if end-begin<3:
            if not reels or end-reels[-1]["first_frame"]>MAX_REEL_FRAMES:
                raise ValueError("Cannot form valid minimum-frame final reel")
            reels[-1]["end_frame"]=end
            reels[-1]["frame_count"]=end-reels[-1]["first_frame"]
            reels[-1]["end_tick"]=end*(TICKS_PER_SECOND//24)
            break
        reels.append({
            "reel_number":len(reels)+1,
            "first_frame":begin,
            "end_frame":end,
            "frame_count":end-begin,
            "start_tick":begin*(TICKS_PER_SECOND//24),
            "end_tick":end*(TICKS_PER_SECOND//24),
        })
        begin=end
    if len(reels)>MAX_REELS:
        raise ValueError("Too many production reels")
    # Conservative capacity planning; lossless OpenJPEG may approach raw.
    # Not all reels coexist in a worker's active memory, but final DCP
    # retains its own copies of picture and sound MXF.
    picture_bound=max(MAX_CODESTREAM,raw_frame_bytes)
    sound_pcm_bytes=frames*2000*channels*3
    full_picture_bound=frames*picture_bound
    full_audio_bound=sound_pcm_bytes+4096*len(reels)
    # Intermediate + final picture/sound spool and 25% margin, plus
    # a separate 2GiB OS/user working-space reserve.
    scratch_peak=(2*(full_picture_bound+full_audio_bound)*5+3)//4+MIN_HEADROOM
    return {
        "format":FORMAT,"status":"CAPACITY_ESTIMATE_ONLY",
        "profile":profile,"channels":channels,
        "frames":frames,"reel_count":len(reels),
        "start_tick":0,"end_tick":frames*(TICKS_PER_SECOND//24),
        "reels":reels,
        "xyz12_frame_bytes":raw_frame_bytes,
        "single_frame_resident_bytes_upper_bound":raw_frame_bytes+COPY_BLOCK*4,
        "max_input_buffer_bytes":COPY_BLOCK,
        "estimated_pcm_bytes":sound_pcm_bytes,
        "worst_case_j2k_or_raw_frame_bytes":picture_bound,
        "estimated_upper_scratch_bytes":scratch_peak,
        "estimated_headroom_bytes":MIN_HEADROOM,
        "all_frames_loaded_into_ram":False,
        "throughput_benchmarked":False,
        "production_release_accepted":False,
    }

def admit_disk(plan,output_root,*,available_bytes=None,reserve_bytes=MIN_HEADROOM):
    if (type(plan) is not dict or plan.get("format")!=FORMAT
            or type(reserve_bytes) is not int or reserve_bytes<MIN_HEADROOM):
        raise PermissionError("Trusted production resource plan required")
    root=Path(output_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Host-selected native scratch root required")
    if available_bytes is None:
        available_bytes=shutil.disk_usage(root).free
    if type(available_bytes) is not int or available_bytes<0:
        raise ValueError("Trusted actual free disk count required")
    required=plan["estimated_upper_scratch_bytes"]
    # The estimate includes MIN_HEADROOM. A caller may set a higher
    # minimum operating-system reserve, not silently lower it.
    required+=reserve_bytes-MIN_HEADROOM
    return {
        "format":"nvp.wo4.native_disk_admission.v1",
        "status":("ADMITTED" if available_bytes>=required else "INSUFFICIENT_DISK"),
        "required_bytes":required,
        "available_bytes":available_bytes,
        "headroom_bytes":reserve_bytes,
        "native_disk_checked":True,
        "started_encoding":False,
    }
