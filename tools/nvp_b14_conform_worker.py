"""B14 contained picture-conform worker: only a host-approved immutable plan.

Not a public API or model-callable operation. Final output is an unapproved
SDR16 review presentation; it is not an edited ProRes master.
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
from backend.nvp_b14_picture_conform import conform_sdr16_picture, verify_conformed_sdr16
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio

PLAN_FIELDS = {"format","studio_db_path","project_id","edit_id","edit_revision",
               "edit_sha256","package_dir","destination_dir","presentation_id"}


def execute(plan_file: Path):
    plan_file = Path(plan_file)
    raw = plan_file.read_bytes()
    plan = json.loads(raw)
    if (type(plan) is not dict or set(plan) != PLAN_FIELDS or
        plan["format"] != "nvp.b14.native_picture_conform_plan.v1" or
        canonical_bytes(plan) != raw or
        type(plan["edit_revision"]) is not int or plan["edit_revision"] < 1):
        raise PermissionError("B14 native conform requires canonical approved plan")
    destination = Path(plan["destination_dir"])
    if (destination.exists() or destination.is_symlink() or
        not destination.parent.is_dir() or destination.parent.is_symlink()):
        raise PermissionError("B14 destination changed or is unsafe")
    capture = DigitalCapture(Studio(Path(plan["studio_db_path"])))
    source = capture.index.read_revision(plan["project_id"], plan["edit_id"],
                                         plan["edit_revision"])
    if (source["kind"] != "edit" or
        source["document_sha256"] != plan["edit_sha256"]):
        raise PermissionError("B14 approved source edit changed")
    finished = conform_sdr16_picture(
        capture, plan["project_id"], plan["edit_id"], plan["edit_revision"],
        Path(plan["package_dir"]), destination, plan["presentation_id"])
    checked = verify_conformed_sdr16(
        capture, plan["project_id"], plan["presentation_id"],
        Path(plan["package_dir"]), destination, edit_revision=plan["edit_revision"])
    if (checked["status"] != "VERIFIED_SDR16_PICTURE_CONFORM" or
        finished["document_sha256"] !=
            capture.index.read_revision(plan["project_id"],plan["presentation_id"],1)["document_sha256"]):
        raise RuntimeError("B14 conform failed independent FilmIndex verification")
    receipt = {"format":"nvp.b14.native_picture_conform_completed.v1",
               "project_id":plan["project_id"],"edit_id":plan["edit_id"],
               "edit_revision":plan["edit_revision"],"edit_sha256":plan["edit_sha256"],
               "presentation_id":plan["presentation_id"],
               "document_sha256":finished["document_sha256"],
               "frames":checked["frames"],"output_dir":str(destination),
               "picture_locked":False,"final_master":False}
    file = plan_file.parent / "conform_receipt.json"
    with file.open("x",encoding="utf8") as stream:
        json.dump(receipt,stream,sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    return receipt


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--plan", required=True)
    args = arg.parse_args()
    print(json.dumps(execute(Path(args.plan)),sort_keys=True))


if __name__=="__main__":
    main()
