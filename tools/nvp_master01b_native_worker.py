"""MASTER-01B: supervised native worker for unapproved 30–60s film reviews.

An already-authorized host creates and verifies the sealed plan, launches this
process inside NVP OS containment, and independently checks the result. The
worker cannot mint a creator grant or approve a final master.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import FilmIndex
from backend.nvp_longform_review import assemble_review, reopen_review
from backend.nvp_studio import Studio

FORMAT = "nvp.master01b.sealed_review_plan.v1"
RECEIPT = "nvp.master01b.native_review_receipt.v1"


def run(plan_path: Path) -> dict:
    if plan_path.is_symlink() or not plan_path.is_file():
        raise RuntimeError("Native MASTER-01B plan absent or symlinked")
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    if (canonical_bytes(plan) != raw or plan.get("format") != FORMAT
        or plan.get("creator_approved_final_master") is not False
        or plan.get("dcp_delivered") is not False):
        raise RuntimeError("Invalid native MASTER-01B sealed technical review plan")
    index = FilmIndex(Studio(plan["studio_db_path"]))
    if plan.get("publication_mode", "worker_publishes") == "host_staged":
        from backend.nvp_master01c_two_phase import prepare_unpublished
        result = prepare_unpublished(index, plan["project_id"], plan["review_id"],
            plan["source_refs"], plan_path.parent / "stage",
            ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"])
        receipt = {"format": "nvp.master01c.native_preparation_receipt.v1",
                   "job_id": plan["job_id"], "project_id": plan["project_id"],
                   "review_id": plan["review_id"],
                   "source_binding_sha256": plan["source_binding_sha256"],
                   "prepared_manifest_sha256": result["manifest_sha256"],
                   "movie_sha256": result["movie_sha256"], "frames": result["frames"],
                   "creator_approved_final_master": False, "dcp_delivered": False}
    elif plan.get("publication_mode", "worker_publishes") == "worker_publishes":
        result = assemble_review(
            index, plan["project_id"], plan["review_id"], plan["source_refs"],
            ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"])
        proof = reopen_review(FilmIndex(Studio(plan["studio_db_path"])),
            plan["project_id"], plan["review_id"],
            ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"])
        if (proof["movie_sha256"] != result["movie_sha256"] or
            proof["status"] != "VERIFIED_TECHNICAL_REVIEW_UNAPPROVED"):
            raise RuntimeError("Native worker could not independently reopen review")
        receipt = {"format": RECEIPT, "job_id": plan["job_id"],
                   "review_id": plan["review_id"], "project_id": plan["project_id"],
                   "source_binding_sha256": plan["source_binding_sha256"],
                   "document_sha256": result["document_sha256"],
                   "movie_sha256": result["movie_sha256"],
                   "frames": result["frames"],
                   "creator_approved_final_master": False,
                   "dcp_delivered": False}
    else:
        raise RuntimeError("Unrecognized host-only review publication mode")
    file = plan_path.parent / "worker_receipt.json"
    with file.open("xb") as writer:
        writer.write(canonical_bytes(receipt))
        writer.flush()
        os.fsync(writer.fileno())
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args(argv)
    run(args.plan)


if __name__ == "__main__":
    main()