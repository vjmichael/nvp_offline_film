"""INDEX-TIME-01: source-video PTS -> authored film timeline, loss-aware.

An imported video frame is an observation at an exact source presentation
timestamp, not an authoritative NVP event. This bridge positions source
frame timestamps on NVP's integer-tick Film Time axis without assuming CFR
and without cumulative floating-point drift.

It does NOT publish authored events, grant creator approval, render frames,
or verify original bytes during interactive preview. FilmIndex ingest and
final-conform custody remain independent.
"""
from __future__ import annotations

from math import gcd
from pathlib import Path

from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, MAX_TICK, _int

FORMAT = "nvp.imported_source_pts_film_time.v1"
ROUNDING = frozenset(("exact", "floor", "ceil", "nearest"))
MAX_MAPPED_FRAMES = 96
MAX_DENOMINATOR = 2**63 - 1


def _rational(numerator, denominator):
    if denominator <= 0:
        raise ValueError("Invalid exact rational denominator")
    d = gcd(abs(numerator), denominator)
    return {"numerator": numerator // d, "denominator": denominator // d}


def pts_to_film_tick(*, source_pts, source_in_pts, time_base_num,
                     time_base_den, film_in_tick, rounding="exact"):
    """Map source PTS to film ticks with explicit, auditable quantization.

    The source-in PTS maps to *film_in_tick*. All calculations use Python
    integers; never round per-frame deltas and add the rounded results.
    The signed quantization_error is tick-selected minus rational exact time,
    expressed in integer NVP ticks. The source's original PTS is preserved.
    """
    for value, label in ((source_pts,"source PTS"),
                         (source_in_pts,"source inpoint PTS")):
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise ValueError("Invalid 64-bit " + label)
    _int(time_base_num, "source time base numerator", minimum=1,
         maximum=MAX_DENOMINATOR)
    _int(time_base_den, "source time base denominator", minimum=1,
         maximum=MAX_DENOMINATOR)
    _int(film_in_tick,"film clip inpoint tick")
    if rounding not in ROUNDING:
        raise ValueError("Explicit imported-video timestamp rounding is required")
    offset = source_pts - source_in_pts
    if offset < 0:
        raise ValueError("Frame precedes the declared source inpoint")
    # Use the original absolute PTS delta; do not infer timestamps from
    # frame ordinals or the project's export frame rate.
    total_num = offset * time_base_num * TICKS_PER_SECOND
    q, rem = divmod(total_num, time_base_den)
    if rounding == "exact" and rem:
        raise ValueError("Source timestamp is not exactly representable in NVP ticks")
    if rounding == "ceil":
        delta_tick = q + bool(rem)
    elif rounding == "nearest":
        delta_tick = q + (2 * rem >= time_base_den)
    else:
        delta_tick = q
    result_tick = film_in_tick + delta_tick
    if result_tick > MAX_TICK:
        raise ValueError("Imported frame timestamp exceeds NVP film-time range")
    # Both terms are expressed with denominator time_base_den.
    error_num = delta_tick*time_base_den - total_num
    return {
        "time_tick":result_tick,
        "source_pts":source_pts,
        "source_in_pts":source_in_pts,
        "source_time_base_num":time_base_num,
        "source_time_base_den":time_base_den,
        "source_elapsed_seconds":_rational(offset*time_base_num,time_base_den),
        "rounding_policy":rounding,
        "exactly_representable":error_num == 0,
        "quantization_error_ticks":_rational(error_num,time_base_den),
    }


class IndexedSourceFilmTime:
    """Bind an indexed imported-video window to a specific film clip inpoint.

    Only a previously indexed, source-stamp-checked NVP frame index is read.
    The caller supplies the user's timeline placement (film_in_tick) and the
    source clip's inpoint ordinal (source_in_frame_zero). No source file hash
    is claimed to have been verified in this operation.
    """
    def __init__(self, index: NVPFrameIndex):
        if not isinstance(index,NVPFrameIndex):
            raise TypeError("Trusted NVP-owned frame index required")
        self.index=index

    def map_window(self, project, asset, source_sha, source, *,
                   source_in_frame_zero, film_in_tick, first_zero,
                   count, rounding="exact"):
        _int(source_in_frame_zero,"source inpoint ordinal")
        _int(first_zero,"source window ordinal")
        _int(film_in_tick,"film clip inpoint tick")
        _int(count,"bounded mapped frame count",
             minimum=1,maximum=MAX_MAPPED_FRAMES)
        if first_zero < source_in_frame_zero:
            raise ValueError("Imported frame is before the selected clip inpoint")
        if rounding not in ROUNDING:
            raise ValueError("Unknown source-to-film quantization policy")
        src=Path(source)
        anchor=self.index.window(project,asset,source_sha,src,
                                  first_zero=source_in_frame_zero,count=1)
        window=self.index.window(project,asset,source_sha,src,
                                  first_zero=first_zero,count=count)
        for field in ("index_path","source_stamp","time_base_num","time_base_den"):
            if anchor[field]!=window[field]:
                raise RuntimeError("Source/index changed between inpoint and window")
        if (anchor["index_status"] not in (
                "CREATED_SOURCE_STAMP_UNVERIFIED",
                "REUSED_SOURCE_STAMP_UNVERIFIED") or
            window["index_status"] not in (
                "CREATED_SOURCE_STAMP_UNVERIFIED",
                "REUSED_SOURCE_STAMP_UNVERIFIED")):
            raise RuntimeError("Unrecognized source custody state")
        origin=anchor["frames"][0]
        if origin["ordinal"]!=source_in_frame_zero:
            raise RuntimeError("Indexed inpoint ordinal changed")
        mapped=[]
        previous_pts=None
        previous_tick=None
        for i,row in enumerate(window["frames"]):
            if row["ordinal"]!=first_zero+i:
                raise RuntimeError("Imported source frame ordinal changed")
            if previous_pts is not None and row["pts"]<=previous_pts:
                raise RuntimeError("Video source PTS order is not increasing")
            previous_pts=row["pts"]
            result=pts_to_film_tick(
                source_pts=row["pts"],source_in_pts=origin["pts"],
                time_base_num=window["time_base_num"],
                time_base_den=window["time_base_den"],
                film_in_tick=film_in_tick,rounding=rounding)
            if previous_tick is not None and result["time_tick"]<=previous_tick:
                raise RuntimeError("Film tick quantization collapsed two frames")
            previous_tick=result["time_tick"]
            mapped.append({"source_frame_zero":row["ordinal"],
                           "source_keyframe":row["keyframe"],
                           "source_packet_pos":row["packet_pos"],**result})
        # No interpolation/picture duration is inferred for the last
        # frame; this maps presentation *instants*, not source-frame spans.
        return {
            "format":FORMAT,"project_id":project,"source_id":asset,
            "source_sha256_at_original_ingest":source_sha,
            "source_sha_verified_this_operation":False,
            "source_integrity":"SOURCE_STAMP_UNVERIFIED",
            "index_status":window["index_status"],
            "source_stamp":window["source_stamp"],
            "source_in_frame_zero":source_in_frame_zero,
            "source_in_pts":origin["pts"],
            "film_in_tick":film_in_tick,
            "first_source_frame_zero":first_zero,
            "frame_count":count,
            "frames":mapped,
            "film_time_is_authoritative_for_native_events":True,
            "imported_media_is_observation_only":True,
            "rendered_frames":False,
        }
