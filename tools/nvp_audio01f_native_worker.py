"""AUDIO-01F native worker: sealed picture/sound plan, no authority of its own.

Launched only by the trusted native NVP host through OS containment.
A successful exit is not acceptance; the host independently verifies FilmIndex,
the movie's decoded streams and the unchanged immutable sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_audio01f_picture_sound import build_picture_sound_preview
from backend.nvp_audio01g_fault_matrix import crash_after


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",required=True,type=Path)
    args=parser.parse_args(argv)
    if args.plan.is_symlink() or not args.plan.is_file():
        raise RuntimeError("Sealed AUDIO-01F plan missing")
    raw=args.plan.read_bytes()
    plan=json.loads(raw)
    if (plan.get("format")!="nvp.audio01f.native_plan.v1" or
        plan.get("final_master") is not False or
        plan.get("director_approved") is not False):
        raise RuntimeError("Invalid technical review worker plan")
    # The native host binds project, original indexed media and the precise
    # sealed plan. Worker cannot mint a creator approval or change the scope.
    capture=DigitalCapture(Studio(plan["studio_db_path"]))
    result=build_picture_sound_preview(
        capture,plan["project_id"],plan["candidate_id"],plan["audio_id"],
        Path(plan["package"]),Path(plan["conform_dir"]),
        Path(plan["movie_dir"]),Path(plan["audio_dir"]),
        plan["audio_plan"],{k:Path(v) for k,v in plan["audio_sources"].items()},
        Path(plan["audio_chunks"]),Path(plan["destination"]),
        plan["presentation_id"],ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
    if result["status"]!="VERIFIED_UNAPPROVED_PICTURE_SOUND_REVIEW":
        raise RuntimeError("Native AUDIO-01F failed technical media verification")
    receipt={
        "format":"nvp.audio01f.native_worker_receipt.v1",
        "presentation_id":plan["presentation_id"],
        "document_sha256":result["document_sha256"],
        "frames":result["frames"],
        "samples_per_channel":result["samples_per_channel"],
        "final_master":False
    }
    path=args.plan.parent/"worker_receipt.json"
    with path.open("xb") as stream:
        stream.write(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    crash_after("worker_receipt_fsynced")


if __name__=="__main__":
    main()
