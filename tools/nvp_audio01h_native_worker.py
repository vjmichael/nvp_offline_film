"""Contained AUDIO-01H automation worker. Plan never conveys approval authority."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_audio01h_stem_revision import automate_stem
from backend.nvp_audio01h_fault_matrix import crash_after


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "--plan":
        raise ValueError("Only sealed native AUDIO-01H worker plans supported")
    plan_file = Path(sys.argv[2])
    if plan_file.is_symlink() or not plan_file.is_file():
        raise RuntimeError("Missing sealed audio plan")
    raw = plan_file.read_bytes()
    plan = json.loads(raw)
    if canonical_bytes(plan) != raw or plan.get("format") != "nvp.audio01h.native_plan.v1":
        raise RuntimeError("Noncanonical audio worker plan")
    if plan.get("final_master") is not False or plan.get("director_approved") is not False:
        raise RuntimeError("Worker cannot approve final delivery")
    capture = DigitalCapture(Studio(plan["studio_db_path"]))
    def exact_scope(scope):
        return scope == plan["authorized_scope"]
    result = automate_stem(
        capture, plan["project_id"], plan["source_audio_id"],
        plan["stem_id"], plan["points"], plan["source_dir"],
        plan["destination"], plan["output_id"], authorize=exact_scope)
    receipt = {"format": "nvp.audio01h.worker_receipt.v1",
               "output_id": result["output_id"],
               "document_sha256": result["document_sha256"],
               "wav_sha256": result["wav_sha256"], "final_master": False}
    with (plan_file.parent / "worker_receipt.json").open("xb") as out:
        out.write(canonical_bytes(receipt))
        out.flush()
        os.fsync(out.fileno())
    crash_after("worker_receipt_fsynced")


if __name__ == "__main__":
    main()
