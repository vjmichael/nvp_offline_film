"""SCALE-03C: exact FilmIndex source-bound review windows with FFMS2 indexing.

Only call from a creator-authorized OS-contained native worker. This is a
review-frame decoder, not an approved picture conform or full-quality master.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from backend.nvp_ffms2_native import FFMS2, sha_file
from backend.nvp_ffms2_index_cache import FFMS2SourceIndex
from backend.nvp_source_window_decode import (
    _read_sources, _canonical, verify_review_window, FORMAT, PNG_SIGNATURE)
from backend.nvp_source_window_preflight import SourceWindowPreflight, FORMAT as PLAN_FORMAT
from backend.nvp_bound_editorial import BoundEditorialPublisher
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio


def execute_ffms2_window(studio_path, plan, destination, *,
                         library_path, index_root, expected_library_sha256):
    if type(plan) is not dict or plan.get("format") != PLAN_FORMAT:
        raise ValueError("Unrecognized exact editorial source-window plan")
    libfile = Path(library_path)
    if (not libfile.is_absolute() or libfile.is_symlink() or
        not libfile.is_file() or
        sha_file(libfile) != expected_library_sha256):
        raise PermissionError("FFMS2 native library executable hash mismatch")
    ffms = FFMS2(libfile)
    cache = FFMS2SourceIndex(ffms, index_root)
    studio = Studio(Path(studio_path))
    index = FilmIndex(studio)
    inventory = SourceMediaInventory(ExternalMediaCatalog(studio))
    bridge = SourceFilmBridge(index, inventory)
    current = SourceWindowPreflight(
        BoundEditorialPublisher(index), bridge).prepare(
            plan["project_id"], plan["edit_id"], plan["edit_revision"],
            first_frame=plan["first_frame"], frame_count=plan["frame_count"])
    if current != plan:
        raise RuntimeError("Indexed source plan changed before FFMS2 decode")
    dest = Path(destination)
    if (not dest.is_absolute() or dest.exists() or dest.is_symlink() or
        not dest.parent.is_dir() or dest.parent.is_symlink()):
        raise RuntimeError("FFMS2 review destination must be new and absolute")
    dest.mkdir(mode=0o700)
    output = []
    for part in current["slices"]:
        path = _read_sources(studio, plan["project_id"], part["source_id"])
        entry = cache.get_or_create(
            plan["project_id"], part["source_id"], path, part["source_sha256"])
        with ffms.open_video(path, entry["index_path"],
                             track=entry["track"]) as session:
            source_start = part["source_first_frame"] - 1
            source_stop = source_start + part["frame_count"]
            if source_stop > entry["num_frames"]:
                raise RuntimeError("FFMS2 indexed frame count shorter than edit range")
            for offset, frame_zero in enumerate(range(source_start, source_stop)):
                out_no = part["output_first_frame"] + offset
                image_path = dest / f"review_{out_no:09d}.png"
                timing = session.frame_metadata(frame_zero)
                png = session.save_png(frame_zero, image_path)
                with image_path.open("rb") as fp:
                    if fp.read(8) != PNG_SIGNATURE:
                        raise RuntimeError("FFMS2 produced invalid PNG review frame")
                output.append({
                    "frame": out_no, "path": image_path.name,
                    "size_bytes": png["size_bytes"], "sha256": png["sha256"],
                    "source_id": part["source_id"],
                    "source_revision": part["source_revision"],
                    "source_frame_zero": frame_zero,
                    "pts": timing["pts"],
                    "time_base_num": timing["time_base_num"],
                    "time_base_den": timing["time_base_den"],
                    "index_sha256": entry["index_sha256"],
                })
        # The external original is not immutable: rehash after decode.
        observed = bridge.resolve_source(
            plan["project_id"], part["source_id"], part["source_revision"],
            verify_bytes=True)
        if (observed["availability"] != "VERIFIED" or
            observed["source_sha256"] != part["source_sha256"]):
            raise RuntimeError("Original media changed while FFMS2 decoded it")
    if (len(output) != plan["frame_count"] or
        [f["frame"] for f in output] !=
        list(range(plan["first_frame"], plan["first_frame"] + plan["frame_count"]))):
        raise RuntimeError("Native indexed source-window returned wrong frame count/order")
    if sha_file(libfile) != expected_library_sha256:
        raise RuntimeError("Native FFMS2 library changed during decode")
    receipt = {"format": FORMAT, "decoder_backend": "ffms2",
               "edit_document_sha256": plan["edit_document_sha256"],
               "first_frame": plan["first_frame"], "frame_count": plan["frame_count"],
               "frames": output, "approved_final": False}
    with (dest / "review_receipt.json").open("xb") as out:
        out.write(_canonical(receipt))
        out.flush()
        os.fsync(out.fileno())
    return verify_review_window(dest, plan)
