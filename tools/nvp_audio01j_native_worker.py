"""AUDIO-01J sealed native final AV worker, no creator approval authority.

It rejects plans without a matching ACTIVE ApprovedTaskBindings record and a
host-issued, unexpired, unrevoked native grant. The host independently checks
the published FilmIndex/movie receipt after worker termination.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01j_final_av import export_final_av
from backend.nvp_audio01j_fault_matrix import crash_after
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def main():
    if len(sys.argv)!=3 or sys.argv[1]!="--plan":
        raise ValueError("Sealed native AV plan required")
    filename=Path(sys.argv[2])
    if filename.is_symlink() or not filename.is_file():
        raise RuntimeError("Native AV plan missing or symlinked")
    raw=filename.read_bytes();plan=json.loads(raw)
    if (canonical_bytes(plan)!=raw or
        plan.get("format")!="nvp.audio01j.native_plan.v1" or
        plan.get("dcp_delivered") is not False):
        raise RuntimeError("Untrusted final AV worker plan")
    spec=plan["approved_spec"]
    digest=hashlib.sha256(canonical_bytes(spec)).hexdigest()
    job=plan["job_id"]
    db=sqlite3.connect(plan["ledger_path"],timeout=20)
    try:
        found=db.execute("""SELECT a.spec_sha256,a.spec_json,t.state,g.spec_sha,
               g.plan_sha,g.revoked,g.expires_at
               FROM authorized_task_specs a JOIN tasks t ON a.task_id=t.id
               JOIN native_audio01j_grants g ON g.job_id=t.id
               WHERE t.id=? AND a.owner_key=?""",
               (job,plan["owner_key"])).fetchone()
    finally:db.close()
    import time
    if (not found or found[0]!=digest or
        found[1]!=canonical_bytes(spec).decode("ascii") or
        found[2]!="ACTIVE" or found[3]!=digest or
        found[4]!=hashlib.sha256(raw).hexdigest() or
        found[5] or time.time()>found[6]):
        raise PermissionError("Final AV worker has no active sealed native approval")
    capture=DigitalCapture(Studio(plan["studio_db_path"]))
    result=export_final_av(
        capture,plan["project_id"],plan["picture_lock_id"],
        plan["audio_delivery_id"],plan["movie_dir"],plan["audio_dir"],
        plan["destination"],plan["export_id"],
        ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
    receipt={"format":"nvp.audio01j.worker_receipt.v1",
             "export_id":plan["export_id"],
             "candidate_id":result["candidate_id"],
             "document_sha256":result["document_sha256"],
             "mov_sha256":result["mov_sha256"],"final_master":False,
             "dcp_delivered":False}
    with (filename.parent/"worker_receipt.json").open("xb") as out:
        out.write(canonical_bytes(receipt));out.flush();os.fsync(out.fileno())
    crash_after("av_worker_receipt_fsynced")


if __name__=="__main__":
    main()
