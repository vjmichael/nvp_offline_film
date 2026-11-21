"""USD-FILM-01P: original director EDL *source-time validation only*.

Retains historical 01P 1..96-camera, 720-frame semantics without importing
its removed FFmpeg/subprocess codec, media masters or unsafe worker launcher.
"""
from __future__ import annotations

FRAMES=720
FPS=24
CUT_MAX=96


def even_camera_coverage_edl(camera_ids):
    """Default 9-camera example: 9 cuts × 80 frames = 30sec film."""
    if (type(camera_ids) is not list or
        not 1<=len(camera_ids)<=CUT_MAX or
        any(type(x) is not str or not x for x in camera_ids) or
        len(set(camera_ids))!=len(camera_ids)):
        raise ValueError("Choose 1–96 distinct original director camera IDs")
    base,rem=divmod(FRAMES,len(camera_ids))
    index=0
    cuts=[]
    for i,camera_id in enumerate(camera_ids):
        length=base+(1 if i<rem else 0)
        cuts.append({"camera_id":camera_id,
                     "source_in_frame":index,
                     "source_out_frame":index+length,
                     "edit_in_frame":index,
                     "edit_out_frame":index+length})
        index+=length
    return cuts


def _validate_edl(edl,source_camera_ids):
    if (type(edl) is not list or not 1<=len(edl)<=CUT_MAX or
        any(type(x) is not dict or set(x)!={
            "camera_id","source_in_frame","source_out_frame",
            "edit_in_frame","edit_out_frame"} for x in edl)):
        raise ValueError("Director EDL must contain bounded typed camera cuts")
    available=set(source_camera_ids)
    current=0
    for cut in edl:
        indices=[cut[x] for x in (
            "source_in_frame","source_out_frame",
            "edit_in_frame","edit_out_frame")]
        if (cut["camera_id"] not in available or
            any(type(x) is not int for x in indices) or
            not 0<=indices[0]<indices[1]<=FRAMES or
            indices[0]!=indices[2] or indices[1]!=indices[3] or
            indices[2]!=current):
            raise PermissionError(
                "Camera cuts must cover one unchanged original actor timeline")
        current=indices[3]
    if current!=FRAMES:
        raise RuntimeError("Exactly 720 continuous original film frames required")
    return edl
