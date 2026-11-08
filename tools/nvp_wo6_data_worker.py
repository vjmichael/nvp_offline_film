"""Private, contained native DA-01 Film Time and DA-06 color decision writer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_wo6_worker_admission import verify_admitted_worker
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_film_index import FilmIndex
from backend.nvp_native_color_decisions import NativeColorDecisions
from backend.nvp_wo6_sound_editorial_decisions import (
    publish_sound_cue,publish_editorial_cut)
from backend.nvp_studio import Studio
from backend.nvp_wo6_native_data_action import (
    FORMAT, RECEIPT, OPERATION, _preflight, verify_decision_output)
from backend.nvp_wo6_native_take_action import _exact_source


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--spec",required=True)
    parser.add_argument("--studio-db",required=True)
    parser.add_argument("--expected-sha",required=True)
    parser.add_argument("--ledger-db", required=True)
    parser.add_argument("--owner-key", required=True)
    options=parser.parse_args(argv)
    path=Path(options.spec)
    database=Path(options.studio_db)
    if (not path.is_absolute() or path.is_symlink() or
            not database.is_absolute() or database.is_symlink()):
        raise PermissionError("Worker requires host-owned absolute source paths")
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=options.expected_sha:
        raise PermissionError("Native decision spec digest differs")
    doc=json.loads(raw)
    if (canonical_bytes(doc)!=raw or doc.get("format")!=FORMAT or
            doc.get("operation")!=OPERATION or doc.get("kind")!="compositing"):
        raise PermissionError("Not a sealed native decision operation")
    verify_admitted_worker(doc, ledger_db=options.ledger_db, owner_key=options.owner_key)
    index=FilmIndex(Studio(database))
    _preflight(index,doc)
    if doc["decision_kind"]=="color":
        record=NativeColorDecisions(index).publish(
            doc["project_id"],doc["decision_id"],take_id=doc["source_id"],
            take_sha256=doc["source_sha256"],parameters=doc["payload"],
            expected_revision=0)
    elif doc["decision_kind"]=="camera_sequence":
        record=ExactTimeShotSequence(index).publish(
            doc["project_id"],doc["decision_id"],
            scene_id=doc["source_id"],scene_revision=doc["source_revision"],
            duration_tick=doc["duration_tick"],shots=doc["payload"],
            expected_revision=0)
    elif doc["decision_kind"]=="sound_cue":
        record=publish_sound_cue(index,doc)
    elif doc["decision_kind"]=="editorial_cut":
        record=publish_editorial_cut(index,doc)
    else:
        raise ValueError("Native worker cannot dispatch arbitrary operation")
    output=verify_decision_output(index,doc)
    if record["document_sha256"]!=output["document_sha256"]:
        raise RuntimeError("Published native decision cannot be reopened")
    if doc["decision_kind"] in ("camera_sequence","sound_cue","editorial_cut"):
        _exact_source(index,doc["project_id"],doc["source_id"],
                      doc["source_revision"],doc["source_sha256"],
                      {"camera_sequence":"scene","sound_cue":"temporal",
                       "editorial_cut":"presentation"}[doc["decision_kind"]])
    receipt={
        "format":RECEIPT,"task_id":doc["task_id"],
        "project_id":doc["project_id"],"decision_id":doc["decision_id"],
        "decision_kind":doc["decision_kind"],
        "decision_sha256":output["document_sha256"],
        "source_impact_sha256":doc["preview_sha256"],
        "source_sha256":doc["source_sha256"],
        "rendered_frames":False,
        "original_take_modified":False,"original_scene_modified":False,
        "existing_dcp_replaced":False,"film_delivered":False,
        "director_release_approved":False,
        "reviewed_ai_consultation":doc.get("reviewed_ai_consultation"),
        "model_instruction_executed":False,
        "model_approval_accepted":False,
    }
    with (path.parent/"receipt.json").open("xb") as stream:
        stream.write(canonical_bytes(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return 0


if __name__=="__main__":
    raise SystemExit(main())
