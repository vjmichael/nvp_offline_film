"""B12 native worker: no CLI/user permission. Trusted NVP host grants and admits.

Only the exact persisted source review and approved plans enter the official
OpenTimelineIO exporter and existing NVP professional video codec gateway.
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
from backend.nvp_b12_editorial_delivery import create_editorial_handoff,PROFILES
from backend.nvp_b11_editorial import verify_sdr_review
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def execute(path):
    path=Path(path)
    raw=path.read_bytes()
    plan=json.loads(raw)
    keys={"format","project_id","review_id","review_sha256","source_take_id",
          "source_take_sha256","delivery_id","frames","resolution",
          "studio_db_path","output_root","profiles"}
    if (type(plan) is not dict or set(plan)!=keys or
        plan.get("format")!="nvp.b12.native_delivery_plan.v1" or
        canonical_bytes(plan)!=raw):
        raise PermissionError("Native NVP editorial plan not canonical/approved")
    if (plan["output_root"]!=str(path.parent/"handoff") or
        Path(plan["studio_db_path"]).resolve()!=Path(plan["studio_db_path"]) or
        type(plan["profiles"]) is not list or
        len(plan["profiles"])!=len(set(plan["profiles"])) or
        any(profile not in PROFILES for profile in plan["profiles"])):
        raise PermissionError("Native editorial path, codec or authority changed")
    capture=DigitalCapture(Studio(Path(plan["studio_db_path"])))
    checked=verify_sdr_review(capture,plan["project_id"],plan["review_id"])
    document=capture.index.read_revision(plan["project_id"],plan["review_id"])
    data=document["data"]
    if (document["document_sha256"]!=plan["review_sha256"] or
        data["source_take_id"]!=plan["source_take_id"] or
        data["source_take_sha256"]!=plan["source_take_sha256"] or
        checked["review_frame_count"]!=plan["frames"] or
        [data["width"],data["height"]]!=plan["resolution"]):
        raise RuntimeError("Indexed original editorial review changed after approval")
    result=create_editorial_handoff(
        capture,plan["project_id"],plan["review_id"],plan["delivery_id"],
        Path(plan["output_root"]),profiles=plan["profiles"])
    record=capture.index.read_revision(plan["project_id"],plan["delivery_id"])
    report={
        "format":"nvp.b12.native_delivery_completed.v1",
        "delivery_id":plan["delivery_id"],
        "project_id":plan["project_id"],
        "source_take_id":plan["source_take_id"],
        "source_review_sha256":plan["review_sha256"],
        "presentation_sha256":record["document_sha256"],
        "frames":result["frames"],
        "otio_independently_parsed":result["official_otio_parsed"],
        "portable_media_verified":result["portable_media_all_present"],
        "professional_video_profiles":result["video_candidates_verified"],
        "native_OS_containment_claimed":False,  # only HOST may make kernel claim
        "screening_master_approved":False,
        "original_source_unchanged":True,
    }
    out=path.parent/"b12_delivery_completed.json"
    with out.open("x",encoding="utf8") as handle:
        json.dump(report,handle,sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",required=True)
    args=parser.parse_args()
    print(json.dumps(execute(Path(args.plan)),sort_keys=True))


if __name__=="__main__":
    main()
