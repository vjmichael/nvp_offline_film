"""AUDIO-01E.3 native child: only consumes a host-sealed immutable plan.

The native host must have admitted this child through ApprovedTaskBindings,
TaskLedger and OS containment. This tool cannot grant its own permissions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.nvp_audio01d_chunked_recovery import run_chunked_preview, verify_chunked_preview

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--plan",type=Path,required=True)
    ap.add_argument("--test-hold-after-one-chunk",action="store_true",
                    help="CI-only: render first chunk, then remain alive for OS termination")
    a=ap.parse_args(argv)
    if a.test_hold_after_one_chunk and os.environ.get("NVP_NATIVE_TERMINATION_TEST")!="1":
        raise RuntimeError("Test-only process hold disabled")
    if a.plan.is_symlink() or not a.plan.is_file():
        raise RuntimeError("Missing sealed plan")
    raw=a.plan.read_bytes()
    data=json.loads(raw)
    if (data.get("format")!="nvp.native.audio.worker_plan.v1" or
        data.get("final_master") is not False or
        data.get("director_approved") is not False):
        raise RuntimeError("Untrusted audio worker plan")
    target=Path(data["directory"])
    sources={key:Path(value) for key,value in data["sources"].items()}
    for sid,p in sources.items():
        h=hashlib.sha256()
        with p.open("rb") as f:
            for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
        if h.hexdigest()!=data["source_sha256"][sid]:
            raise RuntimeError("Audio source differs from approved plan")
    if a.test_hold_after_one_chunk:
        result=run_chunked_preview(data["plan"],sources,data["total_samples"],
                                   target,max_new_chunks=1)
        # Never claim this is completed. A real process-tree kill is required.
        (a.plan.parent/"test_worker_ready").write_text(str(os.getpid()),"ascii")
        while True:time.sleep(.1)
    result=run_chunked_preview(data["plan"],sources,data["total_samples"],target)
    if result["status"]!="COMPLETE_AUDIO_CHUNK_PREVIEW":
        raise RuntimeError("Audio worker did not complete")
    proof=verify_chunked_preview(data["plan"],sources,data["total_samples"],target)
    if proof["status"]!="VERIFIED_CHUNKED_AUDIO_PREVIEW":
        raise RuntimeError("Audio worker generated unverified chunks")
    (a.plan.parent/"worker_verified_receipt.json").write_text(
        json.dumps({"format":"nvp.audio.native.worker_verified.v1",
                    "job_id":data["job_id"],"samples":data["total_samples"],
                    "final_master":False},sort_keys=True),"utf8")

if __name__=="__main__":
    main()
