"""Contained SCALE-03B source-window worker entrypoint. Not a public API."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_source_window_decode import execute_source_window
from backend.nvp_native_indexed_window import execute_indexed_window


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--plan", required=True)
    args.add_argument("--destination", required=True)
    args.add_argument("--studio-db", required=True)
    args.add_argument("--ffmpeg", required=True)
    args.add_argument("--ffmpeg-sha", required=True)
    args.add_argument("--decoder-backend", choices=("ffmpeg", "nvp_index"),
                      default="ffmpeg")
    args.add_argument("--ffprobe")
    args.add_argument("--ffprobe-sha")
    args.add_argument("--index-root")
    opts = args.parse_args()
    raw = Path(opts.plan).read_bytes()
    plan = json.loads(raw)
    if raw != canonical_bytes(plan):
        raise PermissionError("Native review window plan is not canonically sealed")
    if (len(opts.ffmpeg_sha) != 64 or
        sha_file(opts.ffmpeg) != opts.ffmpeg_sha):
        raise PermissionError("Approved FFmpeg executable has changed")
    if opts.decoder_backend == "nvp_index":
        if (not opts.ffprobe or not opts.ffprobe_sha or not opts.index_root or
            sha_file(opts.ffprobe) != opts.ffprobe_sha):
            raise PermissionError("Sealed native NVP index tool was altered or unavailable")
        result = execute_indexed_window(
            opts.studio_db, plan, opts.destination,
            ffprobe_path=opts.ffprobe, ffmpeg_path=opts.ffmpeg,
            index_root=opts.index_root)
    else:
        result = execute_source_window(
            opts.studio_db, plan, opts.destination,
            ffmpeg_path=opts.ffmpeg)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
