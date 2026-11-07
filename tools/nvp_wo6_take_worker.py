"""OS-contained first-party WO6-05 immutable OpenUSD Take operation.

Private trusted host runner, not an AI-facing tool. Revalidates exact source
SHA and refuses to overwrite any prior Take or DCP. Source/admission policy
is independently enforced in the parent before this process is launched.
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
from backend.nvp_wo6_worker_admission import verify_admitted_worker
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_wo6_native_take_action import (
    OPERATION, FORMAT, RECEIPT_FORMAT, _exact_source, _preflight,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--studio-db", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--ledger-db", required=True)
    parser.add_argument("--owner-key", required=True)
    args = parser.parse_args(argv)
    spec_path = Path(args.spec)
    if (not spec_path.is_absolute() or spec_path.is_symlink() or
            not Path(args.studio_db).is_absolute()):
        raise PermissionError("Worker must receive native absolute host paths")
    raw = spec_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.expected_sha:
        raise PermissionError("Creator-authorized exact action spec SHA changed")
    spec = json.loads(raw)
    if (canonical_bytes(spec) != raw or spec.get("format") != FORMAT or
            spec.get("operation") != OPERATION or
            spec.get("kind") != "compositing"):
        raise PermissionError("Worker spec format or canonical bytes invalid")
    verify_admitted_worker(spec, ledger_db=args.ledger_db, owner_key=args.owner_key)
    studio = Studio(Path(args.studio_db))
    index = FilmIndex(studio)
    _preflight(index, spec)
    accepted = {
        "project_id": spec["project_id"], "take_id": spec["take_id"],
        "scene_id": spec["scene_id"], "scene_revision": spec["scene_revision"],
        "scene_document_sha256": spec["scene_sha256"],
        "timeline_id": spec["timeline_id"],
        "timeline_revision": spec["timeline_revision"],
        "timeline_document_sha256": spec["timeline_sha256"],
        "checkpoint_ticks": spec["sample_ticks"],
    }
    def approved(event, payload):
        return (
            event == "native_host_approved_spec" and
            payload.get("operation") == "nvp.freeze.usd_temporal_take.v1" and
            all(payload.get(k) == value for k, value in accepted.items())
        )
    take = OpenUSDTakeCapture(index, verify_creator_action=approved)
    result = take.freeze(
        spec["project_id"], spec["take_id"],
        scene_id=spec["scene_id"], scene_revision=spec["scene_revision"],
        timeline_id=spec["timeline_id"],
        timeline_revision=spec["timeline_revision"],
        sample_ticks=spec["sample_ticks"],
        creator_event="native_host_approved_spec")
    if result["revision"] != 1:
        raise RuntimeError("New Take operation unexpectedly revised an older Take")
    proof = take.verify_take(spec["project_id"], spec["take_id"])
    if (proof["take_document_sha256"] != result["document_sha256"] or
            proof["scene_document_sha256"] != spec["scene_sha256"] or
            proof["timeline_document_sha256"] != spec["timeline_sha256"]):
        raise RuntimeError("New native Take failed exact source re-open proof")
    # If a source head raced during output, the new historical Take remains
    # immutable but the job must NOT claim a current approved source.
    _exact_source(index, spec["project_id"], spec["scene_id"],
                  spec["scene_revision"], spec["scene_sha256"], "scene")
    _exact_source(index, spec["project_id"], spec["timeline_id"],
                  spec["timeline_revision"], spec["timeline_sha256"], "temporal")
    receipt = {
        "format": RECEIPT_FORMAT, "task_id": spec["task_id"],
        "project_id": spec["project_id"], "new_take_id": spec["take_id"],
        "take_revision": 1,
        "take_document_sha256": proof["take_document_sha256"],
        "scene_sha256": proof["scene_document_sha256"],
        "timeline_sha256": proof["timeline_document_sha256"],
        "source_impact_sha256": spec["preview_sha256"],
        "native_take_verified": True,
        "existing_dcp_replaced": False, "rendered_frames": False,
        "creative_film_screening_completed": False,
        "final_presentation_approved": False,
    }
    target = spec_path.parent / "receipt.json"
    with target.open("xb") as stream:
        stream.write(canonical_bytes(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
