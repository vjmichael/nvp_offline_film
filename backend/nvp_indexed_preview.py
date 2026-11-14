"""NVP source-indexed *review* extraction using FFmpeg accurate seek.

Indexed PTS is verified against the decoder's showinfo PTS for EVERY frame.
No full original-file SHA is computed in this preview path. This is
provisional review media, NEVER an accepted final film master.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

from backend.nvp_native_frame_index import NVPFrameIndex, stamp, seek_seconds

PTS = re.compile(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\b")
PNG = b"\x89PNG\r\n\x1a\n"
MAX_LOG = 4 * 1024 * 1024


def extract(index: NVPFrameIndex, *, ffmpeg, project, asset, source_sha,
            source, first_zero, count, output_dir, first_output=1, timeout=120):
    """Extract a small indexed source interval into an already-authorized dir."""
    if type(count) is not int or not 1 <= count <= 96:
        raise ValueError("Bounded source range is required")
    ffmpeg = Path(ffmpeg)
    if not ffmpeg.is_absolute() or not ffmpeg.is_file() or ffmpeg.is_symlink():
        raise PermissionError("Native decoder executable must be explicit and trusted")
    src = Path(source)
    before = stamp(src)
    wanted = index.window(project, asset, source_sha, src,
                          first_zero=first_zero, count=count)
    if wanted["source_stamp"] != before:
        raise RuntimeError("Source metadata changed since indexing")
    frames = wanted["frames"]
    seek_time = seek_seconds(frames[0]["pts"], wanted["stream_start_pts"],
                             wanted["time_base_num"], wanted["time_base_den"])
    dest = Path(output_dir)
    if (dest.is_symlink() or not dest.is_absolute() or
        not dest.is_dir() or dest.parent.is_symlink()):
        raise RuntimeError("Review output directory must already be authorized")
    pattern = str(dest / "review_%09d.png")
    cmd = [str(ffmpeg), "-hide_banner", "-nostdin", "-v", "info",
           "-ss", seek_time, "-copyts", "-i", str(src),
           "-map", "0:v:0", "-an", "-vf", "showinfo",
           "-fps_mode", "passthrough", "-frames:v", str(count),
           "-start_number", str(first_output), "-f", "image2", pattern]
    with tempfile.TemporaryFile() as log:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=log,
                                timeout=timeout, check=False)
        end = log.seek(0, os.SEEK_END)
        if result.returncode != 0 or end > MAX_LOG:
            raise RuntimeError("Indexed native preview failed or exceeded log budget")
        log.seek(0)
        observed = []
        for line in log:
            match = PTS.search(line.decode("utf-8", "replace"))
            if match:
                observed.append((int(match[1]), int(match[2])))
    if observed != [(i, item["pts"]) for i, item in enumerate(frames)]:
        raise RuntimeError("Decoded source timestamps disagree with NVP index")
    if stamp(src) != before:
        raise RuntimeError("Media changed during preview extraction")
    output = []
    for offset, item in enumerate(frames):
        frame_no = first_output + offset
        file = dest / f"review_{frame_no:09d}.png"
        if not file.is_file() or file.is_symlink():
            raise RuntimeError("Expected indexed frame not created by decoder")
        with file.open("rb") as f:
            if f.read(8) != PNG:
                raise RuntimeError("Native frame output is not PNG")
        h = hashlib.sha256()
        with file.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        output.append({"frame": frame_no, "source_frame_zero": item["ordinal"],
                       "pts": item["pts"], "sha256": h.hexdigest(),
                       "size_bytes": file.stat().st_size})
    return {"status": "DECODED_REVIEW_SOURCE_UNVERIFIED", "frames": output,
            "source_stamp": before,
            "source_sha256_at_original_ingest": source_sha,
            "source_sha_verified_this_operation": False}
