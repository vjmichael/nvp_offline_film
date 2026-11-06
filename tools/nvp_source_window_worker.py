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
from backend.nvp_ffms2_source_window import execute_ffms2_window


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
    args.add_argument("--decoder-backend", choices=("ffmpeg", "ffms2"), default="ffmpeg")
    args.add_argument("--ffms2-library")
    args.add_argument("--ffms2-sha")
    args.add_argument("--ffms2-index-root")
    opts = args.parse_args()
    raw = Path(opts.plan).read_bytes()
    plan = json.loads(raw)
    if raw != canonical_bytes(plan):
        raise PermissionError("Native review window plan is not canonically sealed")
    if (len(opts.ffmpeg_sha) != 64 or
        sha_file(opts.ffmpeg) != opts.ffmpeg_sha):
        raise PermissionError("Approved FFmpeg executable has changed")
    if opts.decoder_backend == "ffms2":
        if (not opts.ffms2_library or not opts.ffms2_sha or
            not opts.ffms2_index_root or len(opts.ffms2_sha) != 64 or
            sha_file(opts.ffms2_library) != opts.ffms2_sha):
            raise PermissionError("Sealed native FFMS2 engine is unavailable or altered")
        result = execute_ffms2_window(
            opts.studio_db, plan, opts.destination,
            library_path=opts.ffms2_library,
            index_root=opts.ffms2_index_root,
            expected_library_sha256=opts.ffms2_sha)
    else:
        result = execute_source_window(
            opts.studio_db, plan, opts.destination,
            ffmpeg_path=opts.ffmpeg)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
