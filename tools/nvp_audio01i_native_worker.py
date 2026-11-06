"""AUDIO-01I sealed mastering worker; no creator approval authority."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01i_fault_matrix import crash_after
from backend.nvp_audio01i_mastering import render_candidate
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def main():
    if len(sys.argv)!=3 or sys.argv[1]!="--plan":
        raise ValueError("Sealed mastering plan required")
    path=Path(sys.argv[2])
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Missing sealed mastering plan")
    raw=path.read_bytes()
    plan=json.loads(raw)
    if (canonical_bytes(plan)!=raw or
        plan.get("format")!="nvp.audio01i.native_plan.v1" or
        plan.get("final_master") is not False or
        plan.get("delivery_approved") is not False):
        raise PermissionError("Mastering worker may render candidates only")
    cap=DigitalCapture(Studio(plan["studio_db_path"]))
    result=render_candidate(
        cap,plan["project_id"],plan["decision_id"],plan["decision_revision"],
        plan["candidate_id"],plan["profile"],plan["destination"],
        ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
    receipt={"format":"nvp.audio01i.worker_receipt.v1",
             "candidate_id":plan["candidate_id"],
             "document_sha256":result["document_sha256"],
             "wav_sha256":result["wav_sha256"],"final_master":False}
    with (path.parent/"worker_receipt.json").open("xb") as out:
        out.write(canonical_bytes(receipt))
        out.flush()
        os.fsync(out.fileno())
    crash_after("candidate_receipt_fsynced")


if __name__=="__main__":
    main()
