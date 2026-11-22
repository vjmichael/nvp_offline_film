"""Codec-independent legacy editorial frame mapping.

The B12/B13 interchange format uses an explicit 24 fps source-frame map.
This module validates only immutable metadata for B14 and PCM conform; it
never imports codec adapters, opens media files, or launches processes.
New Film Time authoring remains independent of this historical format.
"""
from __future__ import annotations

RATE = 24
MAX_FRAMES = 480


def _source_rows(edit: dict, original: dict):
    mapping = edit["editorial_map"]
    rows = mapping["frame_map"]
    original_frames = original["media_frames"]
    if (mapping["fps"] != RATE or not 1 <= len(rows) <= MAX_FRAMES or
        mapping["frame_count"] != len(rows) or
        len(original_frames) != original["frame_count"]):
        raise RuntimeError("Unbounded or incomplete editorial source frame mapping")
    for n, row in enumerate(rows, 1):
        srcno = row["source_frame"]
        if (type(srcno) is not int or not 1 <= srcno <= len(original_frames) or
            row["edit_frame"] != n):
            raise RuntimeError("Conform edit frames are not contiguous or bounded")
        src = original_frames[srcno - 1]
        if (src["frame"] != srcno or row["shot_id"] != src["shot_id"] or
            row["original_png16_sha256"] != src["png16_sha256"] or
            row["original_rgb48_sha256"] != src["rgb48_sha256"] or
            row["original_float32_sha256"] != src["source_exr_sha256"]):
            raise RuntimeError("Conform frame map disagrees with immutable FilmIndex media")
        yield n, src
