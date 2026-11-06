"""INDEX-TIME-03 contained worker: decode real indexed PTS as film-time review.

Uses the existing NVPFrameIndex/FFmpeg accurate-seek extraction path and
source inventory. Both preview and conform-preparation produce unapproved
PNG review frames; conform-preparation additionally rehashes the original
before and after decoding. This cannot publish a picture or cinema master.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_film_index import FilmIndex
from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_film_time_window_preflight import FilmTimeWindowPreflight, FORMAT as PLAN_FORMAT
from backend.nvp_indexed_preview import extract
from backend.nvp_native_frame_index import NVPFrameIndex, stamp
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_window_decode import _canonical, _sha_file, _read_sources, PNG_SIGNATURE
from backend.nvp_studio import Studio

FORMAT = "nvp.review.film_time_source_window.v1"
MAX_RECEIPT = 128 * 1024


def _hash_plan(plan):
    return hashlib.sha256(_canonical(plan)).hexdigest()


def verify_film_time_window(destination, plan):
    """Independent exact-frame provenance and PNG integrity audit.

    This verifies produced review bytes against a sealed task plan. It DOES
    NOT independently verify current original media SHA, approve picture,
    or claim that a final conform/DCP has been created.
    """
    if type(plan) is not dict or plan.get("format") != PLAN_FORMAT:
        raise ValueError("Wrong sealed film-time window plan")
    dest = Path(destination)
    if not dest.is_absolute() or dest.is_symlink() or not dest.is_dir():
        raise RuntimeError("Native time-window output missing or unsafe")
    receipt_path = dest / "review_receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RuntimeError("Native time-window receipt not published")
    if receipt_path.stat().st_size > MAX_RECEIPT:
        raise RuntimeError("Native film-time receipt exceeds size limit")
    raw = receipt_path.read_bytes()
    doc = json.loads(raw)
    if (raw != _canonical(doc) or doc.get("format") != FORMAT or
        doc.get("plan_sha256") != _hash_plan(plan) or
        doc.get("edit_document_sha256") != plan["edit_document_sha256"] or
        doc.get("source_document_sha256") != plan["source_document_sha256"] or
        doc.get("source_sha256_at_original_ingest") !=
            plan["source_sha256_at_original_ingest"] or
        doc.get("mode") != plan["mode"] or
        doc.get("frame_count") != plan["frame_count"] or
        doc.get("approved_final") is not False or
        doc.get("native_film_events_modified") is not False or
        doc.get("output_is_unapproved_png_review") is not True):
        raise RuntimeError("Native film-time review receipt changed")
    original_verified = plan["mode"] == "conform_prepare"
    if (doc.get("source_sha_rehashed_at_worker") is not original_verified or
        doc.get("source_integrity") != (
            "FULL_SHA_VERIFIED_BEFORE_AND_AFTER_REVIEW" if original_verified
            else "SOURCE_STAMP_UNVERIFIED_PREVIEW")):
        raise RuntimeError("False source integrity evidence in native receipt")
    frames = doc.get("frames")
    if type(frames) is not list or len(frames) != plan["frame_count"]:
        raise RuntimeError("Incomplete authored-time review receipt")
    for expected, actual in zip(plan["frames"], frames):
        no = expected["review_frame"]
        name = f"review_{no:09d}.png"
        path = dest / name
        if (type(actual) is not dict or
            actual.get("review_frame") != no or
            actual.get("source_frame_zero") != expected["source_frame_zero"] or
            actual.get("source_pts") != expected["source_pts"] or
            actual.get("film_time_tick") != expected["film_time_tick"] or
            actual.get("exact_time") != expected["exact_time"] or
            actual.get("quantization_error_ticks") !=
                expected["quantization_error_ticks"] or
            actual.get("path") != name or
            path.is_symlink() or not path.is_file() or
            path.stat().st_size != actual.get("size_bytes") or
            _sha_file(path) != actual.get("sha256")):
            raise RuntimeError("Review picture altered or source film time mismatched")
        with path.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                raise RuntimeError("Film-time review output is not a PNG")
    return {
        "status": "VERIFIED_UNAPPROVED_FILM_TIME_REVIEW",
        "mode": plan["mode"],
        "review_frames": len(frames),
        "edit_document_sha256": plan["edit_document_sha256"],
        "source_integrity": doc["source_integrity"],
        "approved_final": False,
        "rendered_master": False,
    }


def execute_film_time_window(studio_path, plan, destination, *,
                             ffprobe_path, ffmpeg_path, index_root,
                             timeout=900):
    if (type(plan) is not dict or plan.get("format") != PLAN_FORMAT or
        plan.get("mode") not in ("preview", "conform_prepare")):
        raise ValueError("Expected exactly one indexed film-time source window")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("Invalid contained worker time bound")
    ffprobe, ffmpeg = Path(ffprobe_path), Path(ffmpeg_path)
    if any(not p.is_absolute() or p.is_symlink() or not p.is_file()
           for p in (ffprobe, ffmpeg)):
        raise PermissionError("Real pinned native FFmpeg/FFprobe paths required")
    studio = Studio(Path(studio_path))
    index = FilmIndex(studio)
    inventory = SourceMediaInventory(ExternalMediaCatalog(studio))
    bridge = SourceFilmBridge(index, inventory)
    cache = NVPFrameIndex(Path(index_root), ffprobe=ffprobe)
    publisher = FilmTimeEditorialPublisher(index, bridge, cache)
    preflight = FilmTimeWindowPreflight(publisher)
    scope = dict(
        project_id=plan["project_id"], edit_id=plan["edit_id"],
        revision=plan["edit_revision"],
        clip_ordinal=plan["clip_ordinal"],
        first_zero=plan["first_source_frame_zero"],
        count=plan["frame_count"], mode=plan["mode"])
    if preflight.prepare(**scope) != plan:
        raise RuntimeError("Approved saved editorial window changed at worker launch")
    dest = Path(destination)
    if (not dest.is_absolute() or dest.is_symlink() or dest.exists() or
        not dest.parent.is_dir() or dest.parent.is_symlink()):
        raise RuntimeError("Native film-time output must be a new safe directory")
    source = _read_sources(studio,plan["project_id"],plan["source_id"])
    original_stamp = stamp(source)
    if original_stamp != plan["source_stamp"]:
        raise RuntimeError("Original source changed before native film-time extraction")
    dest.mkdir(mode=0o700)
    decoded=extract(
        cache,ffmpeg=ffmpeg,project=plan["project_id"],
        asset=plan["source_id"],
        source_sha=plan["source_sha256_at_original_ingest"],source=source,
        first_zero=plan["first_source_frame_zero"],
        count=plan["frame_count"],output_dir=dest,
        first_output=1,timeout=timeout)
    if (decoded["source_stamp"] != original_stamp or
        stamp(source) != original_stamp or
        len(decoded["frames"]) != plan["frame_count"]):
        raise RuntimeError("Original changed during source-indexed film-time decode")
    if plan["mode"]=="conform_prepare":
        proven=bridge.resolve_source(
            plan["project_id"],plan["source_id"],
            plan["source_revision"],verify_bytes=True)
        if (proven["availability"]!="VERIFIED" or
            proven["verified_bytes"] is not True or
            proven["source_sha256"]!=plan["source_sha256_at_original_ingest"]):
            raise RuntimeError("Source bytes failed post-decode conform preparation")
    if preflight.prepare(**scope)!=plan:
        raise RuntimeError("Source edit, original or timestamps changed after native decode")
    rendered=[]
    for row,expected in zip(decoded["frames"],plan["frames"]):
        if (row["frame"]!=expected["review_frame"] or
            row["source_frame_zero"]!=expected["source_frame_zero"] or
            row["pts"]!=expected["source_pts"]):
            raise RuntimeError("Real decoder PTS disagrees with saved film-time edit")
        rendered.append({
            "review_frame": expected["review_frame"],
            "source_frame_zero": expected["source_frame_zero"],
            "source_pts": expected["source_pts"],
            "film_time_tick": expected["film_time_tick"],
            "exact_time": expected["exact_time"],
            "quantization_error_ticks": expected["quantization_error_ticks"],
            "path": f"review_{row['frame']:09d}.png",
            "sha256": row["sha256"], "size_bytes": row["size_bytes"],
        })
    receipt={
        "format":FORMAT,
        "plan_sha256":_hash_plan(plan),
        "edit_document_sha256":plan["edit_document_sha256"],
        "source_document_sha256":plan["source_document_sha256"],
        "source_sha256_at_original_ingest":plan["source_sha256_at_original_ingest"],
        "mode":plan["mode"],
        "frame_count":plan["frame_count"],
        "frames":rendered,
        "source_integrity":(
            "FULL_SHA_VERIFIED_BEFORE_AND_AFTER_REVIEW"
            if plan["mode"]=="conform_prepare"
            else "SOURCE_STAMP_UNVERIFIED_PREVIEW"),
        "source_sha_rehashed_at_worker":plan["mode"]=="conform_prepare",
        "approved_final":False,
        "native_film_events_modified":False,
        "output_is_unapproved_png_review":True,
    }
    with (dest/"review_receipt.json").open("xb") as out:
        out.write(_canonical(receipt))
        out.flush()
        os.fsync(out.fileno())
    return verify_film_time_window(dest, plan)
