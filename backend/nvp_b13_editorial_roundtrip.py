"""NVP B13 — verified edited OpenTimelineIO reimport with immutable FilmIndex edits.

An edit does not mutate original Digital Takes, FLOAT32 OpenEXR images, SDR
reviews or the B12 portable delivery. Untrusted OTIO may reorder/trim/split/
repeat shots within the original indexed media. No arbitrary media paths,
gap, transition, soundtrack, time warp, nested track or compositing is silently
accepted. Unsupported NLE operations are explicit failure until a dedicated
production feature is implemented.

This module is for the admitted, OS-contained native worker. The trusted
native host supplies exact creator authorization and owns the worker lifecycle.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.nvp_b12_editorial_delivery import (
    _otio,verify_editorial_handoff,RATE,OTIO_VERSION)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id

FORMAT="nvp.edit.b13.reimported_otio.v1"
MAX_OTIO_BYTES=4*1024*1024
MAX_EDIT_FRAMES=480
MAX_CLIPS=128


def _sha(raw:bytes):
    return hashlib.sha256(raw).hexdigest()


def _frame_integer(time,what):
    if (time is None or float(time.rate)!=RATE or
        not float(time.value).is_integer() or not 0<=time.value<=MAX_EDIT_FRAMES):
        raise RuntimeError("Edited OTIO "+what+" must be a finite integer 24fps frame")
    return int(time.value)


def _reject_effects(item):
    if list(getattr(item,"effects",[])) or list(getattr(item,"markers",[])):
        raise RuntimeError("Effects/markers need explicit supported NVP workflow, not silent omission")


def parse_edited_otio(raw:bytes,original:dict):
    """Only allow exact original indexed image media, with changed edit decisions.

    Return normalized source-frame mapping and clip edits, independent of any
    untrusted OTIO metadata claiming approval or ownership.
    """
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OTIO_BYTES:
        raise ValueError("Edited OTIO bytes missing or over native input limit")
    if original.get("format")!="nvp.presentation.b12.editorial_delivery.v1":
        raise RuntimeError("No authoritative B12 indexed source for editorial import")
    otio=_otio()
    try:
        timeline=otio.adapters.read_from_string(raw.decode("utf8"),adapter_name="otio_json")
    except (UnicodeError,ValueError,TypeError,RuntimeError) as exc:
        raise RuntimeError("Real OpenTimelineIO schema did not parse") from exc
    if not isinstance(timeline,otio.schema.Timeline):
        raise RuntimeError("Import must be a real OTIO Timeline")
    _reject_effects(timeline)
    if len(list(timeline.tracks))!=1:
        raise RuntimeError("NVP supports only one explicit picture track; audio not imported yet")
    track=timeline.tracks[0]
    if not isinstance(track,otio.schema.Track) or track.kind!=otio.schema.TrackKind.Video:
        raise RuntimeError("Imported edit must contain one video track only")
    _reject_effects(track)
    if (getattr(track,"enabled",True) is not True or
        getattr(track,"source_range",None) is not None or
        getattr(timeline.tracks,"source_range",None) is not None):
        raise RuntimeError("Disabled or parent-trimmed picture tracks cannot be silently flattened")
    clips=list(track)
    if not 1<=len(clips)<=MAX_CLIPS:
        raise RuntimeError("Edited track must contain bounded picture clips")
    source_frames=original["media_frames"]
    original_total=original["frame_count"]
    if len(source_frames)!=original_total or [i["frame"] for i in source_frames]!=list(range(1,original_total+1)):
        raise RuntimeError("B12 indexed media source is incomplete")
    cuts={str(c["shot_id"]):c for c in original["camera_cutlist"]}
    if len(cuts)!=len(original["camera_cutlist"]):
        raise RuntimeError("Original frozen camera shot IDs are ambiguous")
    # Native OTIO metadata is AnyDictionary, NOT Python 'dict'.
    # Never bypass source validation because the serialization library uses a
    # typed mapping: NLE-controlled origin claims are untrusted even when
    # their structural representation differs from a plain Python dict.
    native_meta=timeline.metadata
    if not hasattr(native_meta,"get"):
        raise RuntimeError("Edited timeline origin metadata is missing")
    metadata=native_meta.get("nvp")
    if metadata is None or not hasattr(metadata,"get"):
        raise RuntimeError("Edited timeline original-film origin is missing")
    for label,original_key in (("project_id","project_id"),
                               ("source_take_id","source_take_id"),
                               ("review_id","source_review_id")):
        if metadata.get(label)!=original[original_key]:
            raise RuntimeError("Edited timeline origin metadata conflicts with indexed source")
    if (metadata.get("soundtrack_present") is not False or
        metadata.get("fps")!=RATE or
        metadata.get("frames")!=original_total):
        raise RuntimeError("Edited timeline origin FPS/audio/frame record changed")
    out=[]
    segments=[]
    for clip in clips:
        if not isinstance(clip,otio.schema.Clip):
            raise RuntimeError("Unsupported timeline gap, transition or nested compositing")
        _reject_effects(clip)
        if getattr(clip,"enabled",True) is not True:
            raise RuntimeError("Disabled editorial clip would silently lose source picture")
        if clip.name not in cuts:
            raise RuntimeError("Editor referenced a shot outside the frozen Digital Take")
        cut=cuts[clip.name]
        start=cut["start_frame"]
        end=cut["stop_frame_exclusive"]
        length=end-start
        ref=clip.media_reference
        if (not isinstance(ref,otio.schema.ImageSequenceReference) or
            ref.target_url_base!="media/" or
            ref.name_prefix!="review_" or ref.name_suffix!=".png" or
            ref.frame_zero_padding!=6 or ref.start_frame!=start or
            ref.frame_step!=1 or ref.rate!=RATE or
            ref.missing_frame_policy!=otio.schema.ImageSequenceReference.MissingFramePolicy.error):
            raise RuntimeError("Edited media reference is not the original bounded B12 image sequence")
        _reject_effects(ref)
        avail=ref.available_range
        source=clip.source_range
        if source is None or avail is None:
            raise RuntimeError("Edited shot requires original media availability/source ranges")
        if (_frame_integer(avail.start_time,"available start")!=0 or
            _frame_integer(avail.duration,"available duration")!=length):
            raise RuntimeError("Edited image reference was substituted or extended")
        offset=_frame_integer(source.start_time,"trim start")
        count=_frame_integer(source.duration,"trim duration")
        if count<1 or offset+count>length:
            raise RuntimeError("Edit trim exceeded its original verified camera shot")
        if ref.target_url_for_image_number(offset)!="media/review_%06d.png"%(start+offset):
            raise RuntimeError("NLE image URL origin unexpectedly changed")
        if ref.target_url_for_image_number(offset+count-1)!="media/review_%06d.png"%(start+offset+count-1):
            raise RuntimeError("NLE image URL end unexpectedly changed")
        next_start=len(out)+1
        if len(out)+count>MAX_EDIT_FRAMES:
            raise RuntimeError("Edited timeline exceeds bounded working frame count")
        for frame in range(start+offset,start+offset+count):
            src=source_frames[frame-1]
            if src["frame"]!=frame or src["shot_id"]!=clip.name:
                raise RuntimeError("OTIO frame is not a real indexed shot asset")
            out.append({
                "edit_frame":len(out)+1,
                "source_frame":frame,
                "shot_id":clip.name,
                "original_png16_sha256":src["png16_sha256"],
                "original_rgb48_sha256":src["rgb48_sha256"],
                "original_float32_sha256":src["source_exr_sha256"],
            })
        segments.append({
            "shot_id":clip.name,"edit_start_frame":next_start,
            "edit_stop_frame_exclusive":len(out)+1,
            "source_start_frame":start+offset,
            "source_stop_frame_exclusive":start+offset+count,
            "trim_start_from_frozen_shot":offset,
        })
    if not out:
        raise RuntimeError("Edited film contains no verified picture frames")
    if (_frame_integer(timeline.duration(),"duration")!=len(out) or
        len(out)>MAX_EDIT_FRAMES):
        raise RuntimeError("Edited timebase/duration differs from exact source-frame map")
    return {
        "format":"nvp.b13.official_otio_edit_map.v1",
        "otio_version":OTIO_VERSION,"fps":RATE,"frame_count":len(out),
        "duration_seconds":len(out)/RATE,"clip_count":len(segments),
        "segments":segments,"frame_map":out,
        "reorder_or_trim_supported":True,"audio_unsupported":True,
        "transitions_and_speed_effects_unsupported":True,
    }


def import_edited_otio(capture:DigitalCapture,project_id:str,
                       delivery_id:str,package:Path,edit_id:str,raw:bytes,*,
                       expected_edit_revision:int=0):
    """Worker-side import of a new *edit revision*, never a frozen take update."""
    _id(edit_id,"persistent editor revision identity")
    if type(expected_edit_revision) is not int or expected_edit_revision<0:
        raise ValueError("Edit expected revision needs a nonnegative integer")
    handoff=verify_editorial_handoff(
        capture,project_id,delivery_id,Path(package),check_decode=False)
    if handoff["status"]!="VERIFIED_PORTABLE_EDITORIAL_HANDOFF":
        raise RuntimeError("B12 handoff not independently source-verified")
    original=capture.index.read_revision(project_id,delivery_id)
    data=original["data"]
    planned=parse_edited_otio(raw,data)
    if expected_edit_revision:
        prior=capture.index.read_revision(project_id,edit_id,expected_edit_revision)
        if (prior["kind"]!="edit" or prior["revision"]!=expected_edit_revision or
            prior["data"].get("format")!=FORMAT or
            prior["data"]["source_delivery_id"]!=delivery_id or
            prior["data"]["source_delivery_sha256"]!=original["document_sha256"]):
            raise RuntimeError("Cannot change an editorial edit to another film/source")
    otio_sha=capture.index.put_blob(
        project_id,raw,"application/vnd.opentimelineio+json")
    if otio_sha!=_sha(raw):
        raise RuntimeError("FilmIndex edited OTIO blob differs from native parsed bytes")
    doc={
        "format":FORMAT,"status":"unapproved_editorial_picture_revision",
        "project_id":project_id,
        "source_delivery_id":delivery_id,
        "source_delivery_sha256":original["document_sha256"],
        "source_review_id":data["source_review_id"],
        "source_review_sha256":data["source_review_sha256"],
        "source_take_id":data["source_take_id"],
        "source_take_sha256":data["source_take_sha256"],
        "source_float32_presentation_id":data["source_float32_presentation_id"],
        "source_float32_presentation_sha256":data["source_float32_presentation_sha256"],
        "edited_otio_sha256":otio_sha,
        "expected_parent_edit_revision":expected_edit_revision,
        "editorial_map":planned,
        "picture_approved":False,"audio_present":False,
        "original_source_modified":False,"conformed_video_rendered":False,
        "dcp_delivered":False,
    }
    deps=[
        {"object_id":delivery_id,"revision":1,"role":"presentation"},
        {"object_id":data["source_review_id"],"revision":1,"role":"presentation"},
        {"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
    ]
    result=capture.index.register_revision(
        project_id,edit_id,"edit",doc,
        expected_revision=expected_edit_revision,dependencies=deps)
    checked=verify_imported_edit(capture,project_id,edit_id,
                                 Path(package),revision=result["revision"])
    return {**checked,"document_sha256":result["document_sha256"]}


def verify_imported_edit(capture:DigitalCapture,project_id:str,edit_id:str,
                         package:Path,*,revision=None):
    rec=capture.index.read_revision(project_id,edit_id,revision)
    info=rec["data"]
    if (rec["kind"]!="edit" or info.get("format")!=FORMAT or
        info.get("project_id")!=project_id or
        info.get("status")!="unapproved_editorial_picture_revision" or
        info.get("picture_approved") is not False or
        info.get("audio_present") is not False or
        info.get("original_source_modified") is not False or
        info.get("conformed_video_rendered") is not False or
        info.get("dcp_delivered") is not False or
        info.get("expected_parent_edit_revision")!=rec["revision"]-1):
        raise RuntimeError("Imported edit was falsely approved, mutated or mis-parented")
    source=capture.index.read_revision(project_id,info["source_delivery_id"],1)
    if source["document_sha256"]!=info["source_delivery_sha256"]:
        raise RuntimeError("Source B12 editorial media changed since edited OTIO import")
    original=verify_editorial_handoff(
        capture,project_id,info["source_delivery_id"],Path(package),
        check_decode=False)
    if original["status"]!="VERIFIED_PORTABLE_EDITORIAL_HANDOFF":
        raise RuntimeError("Original portable editorial media missing")
    expected_deps=sorted([
        {"object_id":info["source_delivery_id"],"revision":1,"role":"presentation"},
        {"object_id":info["source_review_id"],"revision":1,"role":"presentation"},
        {"object_id":info["source_take_id"],"revision":1,"role":"source_take"},
    ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
    if rec["dependencies"]!=expected_deps:
        raise RuntimeError("Imported edit lost exact original FilmIndex dependency edges")
    data=source["data"]
    for key in ("source_review_id","source_review_sha256","source_take_id",
                "source_take_sha256","source_float32_presentation_id",
                "source_float32_presentation_sha256"):
        if info[key]!=data[key]:
            raise RuntimeError("Imported edit changed original frozen production source")
    raw=capture.index.get_blob(project_id,info["edited_otio_sha256"])
    if _sha(raw)!=info["edited_otio_sha256"]:
        raise RuntimeError("Edited OTIO bytes corrupted after FilmIndex restart")
    parsed=parse_edited_otio(raw,data)
    if parsed!=info["editorial_map"]:
        raise RuntimeError("Original edited OTIO timing/frame mapping was forged")
    return {
        "format":FORMAT,"status":"VERIFIED_EDITED_OTIO_REVISION",
        "project_id":project_id,"edit_id":edit_id,
        "revision":rec["revision"],
        "source_take_id":info["source_take_id"],
        "source_delivery_id":info["source_delivery_id"],
        "otio_sha256":info["edited_otio_sha256"],
        "frames":parsed["frame_count"],"fps":RATE,
        "clips":parsed["clip_count"],"segments":parsed["segments"],
        "original_source_unchanged":True,
        "picture_approved":False,"audio_included":False,
        "conformed_picture_rendered":False,
    }
