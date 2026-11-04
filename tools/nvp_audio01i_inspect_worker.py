"""AUDIO-01I bounded contained inspector: no authority to publish or approve."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01i_mastering import inspect_native,sha_file


def main():
    if len(sys.argv)!=3 or sys.argv[1]!="--plan":
        raise ValueError("Expected sealed audio inspection plan")
    plan_file=Path(sys.argv[2])
    if plan_file.is_symlink() or not plan_file.is_file():
        raise RuntimeError("No safe native inspection plan")
    raw=plan_file.read_bytes()
    plan=json.loads(raw)
    if (canonical_bytes(plan)!=raw or
        plan.get("format")!="nvp.audio01i.inspect_plan.v1"):
        raise RuntimeError("Invalid sealed PCM24 inspection plan")
    for key in ("ffmpeg","ffprobe","wav"):
        path=Path(plan[key])
        if (not path.is_absolute() or path.is_symlink() or
            not path.is_file() or sha_file(path)!=plan[key+"_sha"]):
            raise RuntimeError("Pinned inspection input or executable changed: "+key)
    result=inspect_native(plan["wav"],plan["ffmpeg"],
                          plan["ffprobe"],plan["samples"])
    with (plan_file.parent/"inspection.json").open("xb") as out:
        out.write(canonical_bytes(result))
        out.flush();os.fsync(out.fileno())


if __name__=="__main__":
    main()
