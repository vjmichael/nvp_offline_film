"""SCALE-03B: contained-worker-side extraction of bounded review PNG windows.

Not a final color-managed conform, approved picture, or cinema master.
The native host must authorize a sealed exact edit/window, hash-pin FFmpeg,
reserve resources, and launch this module in OS-contained supervision.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess

from backend.nvp_source_window_preflight import SourceWindowPreflight, FORMAT as PLAN_FORMAT
from backend.nvp_bound_editorial import BoundEditorialPublisher
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio

FORMAT = "nvp.review.native_source_window.v1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def _read_sources(studio, project_id, source_id):
    with studio._connection() as db:
        row = db.execute("""SELECT m.media_path,m.sha256,d.volume_id,v.registered_root,
            d.path_relative FROM scale_source_media m
            JOIN scale_source_details d ON d.project_id=m.project_id
                 AND d.asset_id=m.asset_id
            JOIN scale_source_volumes v ON v.project_id=d.project_id
                 AND v.volume_id=d.volume_id
            WHERE m.project_id=? AND m.asset_id=?""",
            (project_id, source_id)).fetchone()
    if row is None:
        raise RuntimeError("Original camera media missing from native inventory")
    root, path = Path(row["registered_root"]), Path(row["media_path"])
    if (root.is_symlink() or not root.is_dir() or path.is_symlink() or
        not path.is_file() or root / row["path_relative"] != path):
        raise RuntimeError("Original source path or volume changed")
    return path


def verify_review_window(destination, plan):
    """Independent review-frame byte and interval checks, never final-master QC."""
    dest = Path(destination)
    if dest.is_symlink() or not dest.is_dir():
        raise RuntimeError("Review window directory missing or unsafe")
    receipt_file = dest / "review_receipt.json"
    if receipt_file.is_symlink() or not receipt_file.is_file():
        raise RuntimeError("Completed source-window receipt is missing")
    raw = receipt_file.read_bytes()
    doc = json.loads(raw)
    if raw != _canonical(doc) or doc.get("format") != FORMAT or (
        doc.get("edit_document_sha256") != plan["edit_document_sha256"] or
        doc.get("first_frame") != plan["first_frame"] or
        doc.get("frame_count") != plan["frame_count"] or
        doc.get("approved_final") is not False):
        raise RuntimeError("Review window receipt was changed")
    frames = doc.get("frames")
    if type(frames) is not list or len(frames) != plan["frame_count"]:
        raise RuntimeError("Incomplete review frame manifest")
    if doc.get("decoder_backend") == "nvp_sqlite_index_v1":
        if (doc.get("source_integrity") != "UNVERIFIED_FAST_PREVIEW" or
            doc.get("source_sha_rehashed") is not False or
            plan.get("source_preflight") != "PRESENT_UNVERIFIED_PREVIEW_ONLY"):
            raise RuntimeError("Indexed preview claims unearned source integrity")
    for index, item in enumerate(frames):
        expected = plan["first_frame"] + index
        if doc.get("decoder_backend") == "nvp_sqlite_index_v1":
            matching = [s for s in plan["slices"]
                        if s["output_first_frame"] <= expected <
                        s["output_first_frame"] + s["frame_count"]]
            if len(matching) != 1:
                raise RuntimeError("Indexed receipt frame is outside editorial slices")
            part = matching[0]
            correct_frame = (part["source_first_frame"] - 1 +
                             expected - part["output_first_frame"])
            if (item.get("source_id") != part["source_id"] or
                item.get("source_revision") != part["source_revision"] or
                item.get("source_document_sha256") != part["source_document_sha256"] or
                item.get("source_sha256_at_original_ingest") != part["source_sha256"] or
                item.get("source_frame_zero") != correct_frame or
                type(item.get("pts")) is not int):
                raise RuntimeError("NVP indexed preview source frame provenance mismatch")
        name = f"review_{expected:09d}.png"
        frame = dest / name
        if (type(item) is not dict or item.get("frame") != expected or
            item.get("path") != name or frame.is_symlink() or not frame.is_file() or
            frame.stat().st_size != item.get("size_bytes") or
            _sha_file(frame) != item.get("sha256")):
            raise RuntimeError("Review PNG missing or altered")
        with frame.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                raise RuntimeError("Decoded review frame is not a PNG")
    return {"status": "VERIFIED_UNAPPROVED_SOURCE_REVIEW", "frames": len(frames),
            "edit_document_sha256": doc["edit_document_sha256"],
            "source_integrity": doc.get("source_integrity", "LEGACY_REVIEW_POLICY"),
            "decoder_backend": doc.get("decoder_backend", "ffmpeg_legacy")}


def execute_source_window(studio_path, plan, destination, *, ffmpeg_path, timeout=900):
    """Only a trusted native host may invoke this effectful worker operation.

    All source SHA bytes and FilmIndex bindings are reverified inside worker.
    Refuses a changed plan and refuses an existing output directory.
    FFmpeg decodes only selected frames to short-lived PNG review material.
    """
    if type(plan) is not dict or plan.get("format") != PLAN_FORMAT:
        raise ValueError("Native source window must be an exact preflight plan")
    ffmpeg = Path(ffmpeg_path)
    if not ffmpeg.is_absolute() or ffmpeg.is_symlink() or not ffmpeg.is_file():
        raise PermissionError("Native FFmpeg executable must be an absolute pinned file")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("Invalid native window timeout")
    studio = Studio(Path(studio_path))
    index = FilmIndex(studio)
    inventory = SourceMediaInventory(ExternalMediaCatalog(studio))
    bridge = SourceFilmBridge(index, inventory)
    preflight = SourceWindowPreflight(BoundEditorialPublisher(index), bridge)
    current = preflight.prepare(
        plan["project_id"], plan["edit_id"], plan["edit_revision"],
        first_frame=plan["first_frame"], frame_count=plan["frame_count"])
    if current != plan:
        raise RuntimeError("Sealed source window became stale or changed")
    dest = Path(destination)
    if dest.exists() or dest.is_symlink() or not dest.parent.is_dir() or (
        dest.parent.is_symlink()):
        raise RuntimeError("Native review destination must be absent under safe parent")
    dest.mkdir(mode=0o700)
    output = []
    for part in current["slices"]:
        source = _read_sources(studio, plan["project_id"], part["source_id"])
        original_start = part["source_first_frame"] - 1
        original_end = original_start + part["frame_count"] - 1
        output_start = part["output_first_frame"]
        pattern = dest / "review_%09d.png"
        # Decoding from frame zero is correct for this first fixed-frame-rate
        # source path, but expensive for late seeks in very long originals.
        # A verified keyframe seek/index path is a later scalability gate.
        cmd = [str(ffmpeg), "-hide_banner", "-v", "error", "-nostdin",
               "-i", str(source), "-map", "0:v:0", "-an",
               "-vf", f"select=between(n\\,{original_start}\\,{original_end})",
               "-vsync", "0", "-frames:v", str(part["frame_count"]),
               "-start_number", str(output_start), "-f", "image2",
               str(pattern)]
        result = run_owned_subprocess(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout,
                                check=False)
        if result.returncode:
            raise RuntimeError("Contained FFmpeg source-frame decoding failed")
        # An external source can change during the actual decode. Never accept
        # those bytes unless the original source still matches FilmIndex.
        after = bridge.resolve_source(plan["project_id"], part["source_id"],
                                      part["source_revision"], verify_bytes=True)
        if after["availability"] != "VERIFIED" or (
            after["source_sha256"] != part["source_sha256"]):
            raise RuntimeError("Source changed during review-frame decoding")
        for n in range(output_start, output_start + part["frame_count"]):
            name = f"review_{n:09d}.png"
            file = dest / name
            if file.is_symlink() or not file.is_file():
                raise RuntimeError("FFmpeg returned too few review frames")
            with file.open("rb") as stream:
                if stream.read(8) != PNG_SIGNATURE:
                    raise RuntimeError("Native source decode did not produce PNG")
            output.append({"frame": n, "path": name,
                           "sha256": _sha_file(file),
                           "size_bytes": file.stat().st_size})
    if len(output) != plan["frame_count"]:
        raise RuntimeError("Native source-frame decode length mismatch")
    receipt = {"format": FORMAT, "edit_document_sha256": plan["edit_document_sha256"],
               "first_frame": plan["first_frame"], "frame_count": plan["frame_count"],
               "frames": output, "approved_final": False}
    with (dest / "review_receipt.json").open("xb") as stream:
        stream.write(_canonical(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return verify_review_window(dest, plan)
