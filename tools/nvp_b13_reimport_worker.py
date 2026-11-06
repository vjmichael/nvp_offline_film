"""B13 OS-contained native-only OpenTimelineIO import worker.

This is never a web POST callback, a user-facing JSON API or model tool.
Only the trusted NVP host stages exact bytes under a short-lived creator
authorization and the shared RAM ledger. The child may commit a derived
FilmIndex 'edit' revision but cannot revise a Digital Take or its masters.
"""
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
from backend.nvp_b13_editorial_roundtrip import (
    import_edited_otio,verify_imported_edit,MAX_OTIO_BYTES)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def execute(plan_file:Path):
    plan_file=Path(plan_file)
    raw=plan_file.read_bytes()
    plan=json.loads(raw)
    expected={"format","project_id","delivery_id","package_dir","edit_id",
              "expected_revision","studio_db_path","otio_sha256",
              "source_delivery_sha256","source_take_sha256"}
    if (type(plan) is not dict or set(plan)!=expected or
        plan["format"]!="nvp.b13.native_edit_reimport_plan.v1" or
        canonical_bytes(plan)!=raw or
        type(plan["expected_revision"]) is not int or
        plan["expected_revision"]<0):
        raise PermissionError("Edited OTIO import plan was not authorized or canonical")
    edited=plan_file.parent/"incoming_edit.otio"
    if (edited.is_symlink() or not edited.is_file() or
        edited.stat().st_size>MAX_OTIO_BYTES or
        hashlib.sha256(edited.read_bytes()).hexdigest()!=plan["otio_sha256"]):
        raise PermissionError("Native edited OTIO source replaced or too large")
    capture=DigitalCapture(Studio(Path(plan["studio_db_path"])))
    origin=capture.index.read_revision(plan["project_id"],plan["delivery_id"],1)
    if (origin["document_sha256"]!=plan["source_delivery_sha256"] or
        origin["data"]["source_take_sha256"]!=plan["source_take_sha256"]):
        raise RuntimeError("Original editorial source delivery changed before import")
    imported=import_edited_otio(
        capture,plan["project_id"],plan["delivery_id"],
        Path(plan["package_dir"]),plan["edit_id"],edited.read_bytes(),
        expected_edit_revision=plan["expected_revision"])
    final=verify_imported_edit(capture,plan["project_id"],plan["edit_id"],
                               Path(plan["package_dir"]),revision=imported["revision"])
    if final["status"]!="VERIFIED_EDITED_OTIO_REVISION":
        raise RuntimeError("Edited revision failed independent FilmIndex verification")
    receipt={
        "format":"nvp.b13.native_edited_otio_completed.v1",
        "project_id":plan["project_id"],
        "delivery_id":plan["delivery_id"],
        "edit_id":plan["edit_id"],"revision":final["revision"],
        "edited_otio_sha256":plan["otio_sha256"],
        "source_delivery_sha256":plan["source_delivery_sha256"],
        "frames":final["frames"],"clips":final["clips"],
        "document_sha256":imported["document_sha256"],
        "native_OS_containment_claimed":False,
        "original_take_modified":False,"rendered_movie_claimed":False,
    }
    dest=plan_file.parent/"verified_import_receipt.json"
    with dest.open("x",encoding="utf8") as out:
        json.dump(receipt,out,sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    return receipt


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--plan",required=True)
    args=cli.parse_args()
    print(json.dumps(execute(Path(args.plan)),sort_keys=True))


if __name__=="__main__":
    main()
