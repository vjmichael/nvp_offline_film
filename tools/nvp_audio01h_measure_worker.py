"""Contained AUDIO-01H EBU R128 measurement subprocess.

No approval authority. Host pins SHA and supervises worker plus FFmpeg tree.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01h_loudness import analyze_wav


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "--plan":
        raise ValueError("Expected sealed native AUDIO-01H measurement plan")
    path = Path(sys.argv[2])
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Missing measurement plan")
    raw = path.read_bytes()
    plan = json.loads(raw)
    if (canonical_bytes(plan) != raw or
        plan.get("format") != "nvp.audio01h.measure_plan.v1" or
        plan.get("final_master") is not False):
        raise RuntimeError("Invalid native loudness plan")
    source = Path(plan["wav"])
    if source.is_symlink() or not source.is_file() or (
            hashlib.sha256(source.read_bytes()).hexdigest() != plan["wav_sha256"]):
        raise RuntimeError("Native loudness source mismatch")
    executable=Path(plan["ffmpeg"])
    if (not executable.is_absolute() or executable.is_symlink() or
        not executable.is_file() or
        hashlib.sha256(executable.read_bytes()).hexdigest()!=plan["ffmpeg_sha256"]):
        raise RuntimeError("Pinned FFmpeg executable changed")
    measure = analyze_wav(source, ffmpeg=str(executable),
                          expected_samples=plan["samples"])
    with (path.parent / "measurement.json").open("xb") as out:
        out.write(canonical_bytes(measure))
        out.flush()
        os.fsync(out.fileno())


if __name__ == "__main__":
    main()
