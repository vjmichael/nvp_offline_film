"""NVP source-bound native indexed *preview* window execution.

Frame index authored by NVP in SQLite, with FFprobe first-time frame PTS
scan and FFmpeg bounded accurate-seek decode. No FFMS2 and NO original SHA
rehash for previews. The result is not a cryptographically verified source
nor an approved picture/master.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from backend.nvp_native_frame_index import NVPFrameIndex, stamp
from backend.nvp_indexed_preview import extract
from backend.nvp_source_window_decode import (
    _read_sources, _canonical, verify_review_window, FORMAT)
from backend.nvp_source_window_preflight import SourceWindowPreflight, FORMAT as PLAN_FORMAT
from backend.nvp_bound_editorial import BoundEditorialPublisher
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio


def execute_indexed_window(studio_path, plan, destination, *,
                           ffprobe_path, ffmpeg_path, index_root,
                           timeout=900):
    if type(plan) is not dict or plan.get("format") != PLAN_FORMAT or (
        plan.get("source_preflight") != "PRESENT_UNVERIFIED_PREVIEW_ONLY"):
        raise RuntimeError("NVP indexed review requires an explicitly unverified preview plan")
    studio = Studio(Path(studio_path))
    index = FilmIndex(studio)
    inventory = SourceMediaInventory(ExternalMediaCatalog(studio))
    bridge = SourceFilmBridge(index, inventory)
    preflight = SourceWindowPreflight(BoundEditorialPublisher(index), bridge)
    current = preflight.prepare(
        plan["project_id"], plan["edit_id"], plan["edit_revision"],
        first_frame=plan["first_frame"], frame_count=plan["frame_count"],
        integrity_policy="preview")
    if current != plan:
        raise RuntimeError("Committed editorial source window changed before decoding")
    cache = NVPFrameIndex(Path(index_root), ffprobe=Path(ffprobe_path))
    dest = Path(destination)
    if (not dest.is_absolute() or dest.is_symlink() or dest.exists() or
        not dest.parent.is_dir() or dest.parent.is_symlink()):
        raise RuntimeError("Native indexed preview destination must be new")
    dest.mkdir(mode=0o700)
    all_frames = []
    for part in current["slices"]:
        source = _read_sources(studio, plan["project_id"], part["source_id"])
        before = stamp(source)
        decoded = extract(
            cache, ffmpeg=Path(ffmpeg_path), project=plan["project_id"],
            asset=part["source_id"], source_sha=part["source_sha256"],
            source=source, first_zero=part["source_first_frame"] - 1,
            count=part["frame_count"], output_dir=dest,
            first_output=part["output_first_frame"],
            timeout=min(timeout, 3600))
        if decoded["source_stamp"] != before or stamp(source) != before:
            raise RuntimeError("Indexed media changed while native worker decoded")
        for row in decoded["frames"]:
            row["source_id"] = part["source_id"]
            row["source_revision"] = part["source_revision"]
            row["source_document_sha256"] = part["source_document_sha256"]
            row["source_sha256_at_original_ingest"] = part["source_sha256"]
            all_frames.append(row)
    if (len(all_frames) != plan["frame_count"] or
        [x["frame"] for x in all_frames] !=
        list(range(plan["first_frame"], plan["first_frame"] + plan["frame_count"]))):
        raise RuntimeError("Indexed preview frame origin or order invalid")
    # No second full-source SHA here. Recheck fast availability + exact
    # FilmIndex source-revision parity only.
    if preflight.prepare(
        plan["project_id"], plan["edit_id"], plan["edit_revision"],
        first_frame=plan["first_frame"], frame_count=plan["frame_count"],
        integrity_policy="preview") != plan:
        raise RuntimeError("Editorial decision changed during preview")
    receipt = {
        "format": FORMAT, "decoder_backend": "nvp_sqlite_index_v1",
        "source_integrity": "UNVERIFIED_FAST_PREVIEW",
        "source_sha_rehashed": False,
        "edit_document_sha256": plan["edit_document_sha256"],
        "first_frame": plan["first_frame"], "frame_count": plan["frame_count"],
        "frames": all_frames, "approved_final": False,
    }
    with (dest / "review_receipt.json").open("xb") as out:
        out.write(_canonical(receipt))
        out.flush()
        os.fsync(out.fileno())
    return verify_review_window(dest, plan)
