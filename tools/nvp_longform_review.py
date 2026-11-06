"""Developer-only NVP-MASTER-01A technical-review assembly CLI.

This is not the production native worker authorization/containment path and
cannot grant creator picture lock, final master or DCP approval.

Example:
  python -m tools.nvp_longform_review --studio-db /work/studio.sqlite3 \
    --project-id <32hex> --review-id shortfilm_review \
    --reel reel_a:1 --reel reel_b:1 --reel reel_c:1 \
    --report /work/preview-proof.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_longform_review import assemble_review, reopen_review


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio-db", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--reel", action="append", required=True,
                        help="Exact source reel object ID:revision (repeat in timeline order)")
    parser.add_argument("--report", type=Path, help="Create-only JSON verification report")
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--ffprobe", default=None)
    args = parser.parse_args(argv)
    if args.studio_db.is_symlink() or not args.studio_db.is_file():
        parser.error("Existing, nonsymlinked NVP studio database is required")
    refs = []
    for entry in args.reel:
        if ":" not in entry:
            parser.error("Reel identity must have object_id:revision form")
        identity, version = entry.rsplit(":", 1)
        if not version.isascii() or not version.isdecimal():
            parser.error("Reel revision must be a positive decimal integer")
        refs.append({"object_id": identity, "revision": int(version)})
    if args.report is not None and (args.report.is_symlink() or args.report.exists()
                                    or not args.report.parent.is_dir()):
        parser.error("Report destination must be a new file in an existing directory")
    index = FilmIndex(Studio(args.studio_db))
    produced = assemble_review(index, args.project_id, args.review_id, refs,
                               ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    independent = reopen_review(FilmIndex(Studio(args.studio_db)), args.project_id,
                                args.review_id, ffprobe=args.ffprobe)
    result = {**produced, "verified_media_path": independent["path"],
              "verification": independent["status"],
              "report_grants_director_approval": False}
    output = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.report is not None:
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()