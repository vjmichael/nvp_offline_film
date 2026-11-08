"""Private OS-contained WO6 director-shot operation; never AI-addressable."""
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
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_studio import Studio
from backend.nvp_wo6_native_shot_action import (
    FORMAT, RECEIPT, _check_shot_source,
)
from backend.nvp_wo6_native_take_action import _exact_source


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--studio-db", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--ledger-db", required=True)
    parser.add_argument("--owner-key", required=True)
    args = parser.parse_args(argv)
    target = Path(args.spec)
    if (not target.is_absolute() or target.is_symlink() or
            not Path(args.studio_db).is_absolute()):
        raise PermissionError("Untrusted worker input path")
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.expected_sha:
        raise PermissionError("Native host-issued shot digest mismatch")
    spec = json.loads(raw)
    if (canonical_bytes(spec) != raw or spec.get("format") != FORMAT or
            spec.get("operation") != "nvp.film.author_director_shot.v1" or
            spec.get("kind") != "compositing"):
        raise PermissionError("Invalid canonical native shot task")
    verify_admitted_worker(spec, ledger_db=args.ledger_db, owner_key=args.owner_key)
    index = FilmIndex(Studio(Path(args.studio_db)))
    _check_shot_source(index, spec)
    def verified_host_only(event, request):
        return (event == "host_verified_exact_shot_spec" and
                request.get("operation") ==
                "nvp.usd.director_shot_override.v1" and
                request.get("project_id") == spec["project_id"] and
                request.get("shot_id") == spec["shot_id"] and
                request.get("take_id") == spec["take_id"] and
                request.get("take_document_sha256") == spec["take_sha256"] and
                request.get("scene_document_sha256") == spec["scene_sha256"] and
                request.get("start_tick") == spec["start_tick"] and
                request.get("end_tick") == spec["end_tick"] and
                request.get("purpose") == spec["purpose"] and
                request.get("continuity_policy") == spec["continuity_policy"] and
                request.get("reason") == spec["reason"] and
                request.get("usd_layer_sha256") == spec["shot_layer_sha256"] and
                request.get("final_render_approval") is False)
    shooter = OpenUSDShotOverrides(
        index, verify_director_action=verified_host_only)
    created = shooter.publish(
        spec["project_id"], spec["shot_id"], take_id=spec["take_id"],
        start_tick=spec["start_tick"], end_tick=spec["end_tick"],
        changes=spec["changes"], purpose=spec["purpose"],
        continuity_policy=spec["continuity_policy"], reason=spec["reason"],
        expected_revision=0, creator_event="host_verified_exact_shot_spec")
    if created["revision"] != 1:
        raise RuntimeError("Native shot unexpectedly rewrote an existing revision")
    reopened = shooter.evaluate(
        spec["project_id"], spec["shot_id"], 1,
        tick=spec["start_tick"])
    if reopened["shot_document_sha256"] != created["document_sha256"]:
        raise RuntimeError("Native shot reopen digest mismatch")
    # A concurrent revision after the shot commit must not be called a
    # successful current-source change. Preserve the old immutable shot
    # but return failure requiring explicit reconciliation.
    _exact_source(index, spec["project_id"], spec["scene_id"],
                  spec["scene_revision"], spec["scene_sha256"], "scene")
    receipt = {
        "format": RECEIPT, "task_id": spec["task_id"],
        "project_id": spec["project_id"], "shot_id": spec["shot_id"],
        "shot_sha256": created["document_sha256"],
        "shot_revision": 1, "take_sha256": spec["take_sha256"],
        "source_impact_sha256": spec["preview_sha256"],
        "action_kind": spec["action_kind"], "rendered_frames": False,
        "original_scene_modified": False, "old_take_modified": False,
        "existing_dcp_replaced": False, "creative_screening_completed": False,
        "reviewed_ai_consultation":spec.get("reviewed_ai_consultation"),
        "model_instruction_executed":False,
        "model_approval_accepted":False,
    }
    with (target.parent / "receipt.json").open("xb") as stream:
        stream.write(canonical_bytes(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
