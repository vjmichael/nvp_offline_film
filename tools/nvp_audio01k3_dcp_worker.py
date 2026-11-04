"""AUDIO-01K.3 sealed, OS-contained DCP-o-matic + DcpDoctor worker.

No FilmIndex master/delivery publication authority. The worker generates and
validates a real SMPTE DCP in a private working folder, copies its assets to
a reserved stage path, and writes a non-authoritative receipt for the host.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01k3_dcp import (
    encode_candidate, inspect_dcp_directory, inspect_cpl_timing,
    validate_strict_smpte, sha_file)


def main():
    if len(sys.argv)!=3 or sys.argv[1]!="--plan":
        raise ValueError("Native SMPTE DCP worker requires sealed plan")
    path=Path(sys.argv[2])
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Unsafe cinema worker plan")
    raw=path.read_bytes()
    plan=json.loads(raw)
    if (canonical_bytes(plan)!=raw or
        plan.get("format")!="nvp.audio01k3.native_plan.v1" or
        plan.get("dcp_delivered") is not False or
        plan.get("creator_approved_theatrical_delivery") is not False):
        raise PermissionError("Worker may generate DCP candidates only")
    job=plan["job_id"];spec=plan["approved_spec"]
    digest=hashlib.sha256(canonical_bytes(spec)).hexdigest()
    with sqlite3.connect(plan["ledger_path"],timeout=30) as db:
        row=db.execute("""SELECT a.spec_sha256,a.spec_json,
                 t.state,g.spec_sha,g.plan_sha,g.revoked,g.expires_at
                 FROM authorized_task_specs a JOIN tasks t ON t.id=a.task_id
                 JOIN native_audio01k3_grants g ON g.job_id=t.id
                 WHERE t.id=? AND a.owner_key=?""",
                 (job,plan["owner_key"])).fetchone()
    if (not row or row[0]!=digest or
        row[1]!=canonical_bytes(spec).decode("ascii") or
        row[2]!="ACTIVE" or row[3]!=digest or
        row[4]!=hashlib.sha256(raw).hexdigest() or row[5] or
        time.time()>row[6]):
        raise PermissionError("No currently admitted and sealed native DCP job")
    for key in ("dcp_create","dcp_cli","dcpdoctor"):
        executable=Path(plan[key])
        if (not executable.is_absolute() or executable.is_symlink() or
            not executable.is_file() or
            sha_file(executable)!=plan[key+"_sha"]):
            raise RuntimeError("Native cinema packager or validator digest changed")
    movie=Path(plan["movie"])
    if movie.is_symlink() or sha_file(movie)!=plan["movie_sha256"]:
        raise RuntimeError("Creator-approved mezzanine bytes changed")
    work=path.parent/"encoding_workspace"
    work.mkdir(mode=0o700)
    dcp,preflight=encode_candidate(
        movie,work,plan["title"],create_bin=plan["dcp_create"],
        cli_bin=plan["dcp_cli"],expected_mov_sha=plan["movie_sha256"])
    qc=validate_strict_smpte(dcp,plan["dcpdoctor"],report_dir=path.parent)
    stage=Path(plan["stage"])
    if (stage.exists() or stage.is_symlink() or
        stage.parent.is_symlink() or not stage.parent.is_dir()):
        raise RuntimeError("No previously staged cinema package permitted")
    stage.mkdir(mode=0o700)
    for file in dcp.iterdir():
        if file.is_symlink() or not file.is_file():
            raise RuntimeError("Unsafe encoded DCP asset")
        dest=stage/file.name
        with file.open("rb") as inp,dest.open("xb") as out:
            shutil.copyfileobj(inp,out,1024*1024)
            out.flush();os.fsync(out.fileno())
    receipt_stage=inspect_dcp_directory(stage)
    timing=inspect_cpl_timing(stage,plan["frames"])
    if receipt_stage["assets"]!=preflight["assets"] or receipt_stage["assets"]!=qc["asset_sha256_proof"]:
        raise RuntimeError("Staged DCP differs from independently validated package")
    receipt={
        "format":"nvp.audio01k3.worker_receipt.v1",
        "source_movie_sha256":plan["movie_sha256"],
        "distribution_document_sha256":plan["distribution_sha"],
        "structural_proof":receipt_stage,
        "cpl_timing":timing,
        "independent_qc":qc,
        "dcp_delivered":False,
        "theatrical_exhibition_certified":False,
    }
    with (path.parent/"worker_receipt.json").open("xb") as f:
        f.write(canonical_bytes(receipt));f.flush();os.fsync(f.fileno())


if __name__=="__main__":
    main()
