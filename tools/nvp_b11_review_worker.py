"""NVP B11 worker-side entrypoint for exact frozen-take SDR review contract.

No creator consent is accepted from CLI. The trusted host alone stages and
authenticates the canonical plan before launching this pinned script through
NVP's OS containment and physical RAM admission. The script reads only the
indexed original Float32 presentation and publishes a NEW 16-bit SDR review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_b11_editorial import (
    render_aces2_sdr_review,frozen_review_source,SOURCE_COLOR_SPACE,
    NEAR_OPAQUE_ALPHA_POLICY,MAX_ALPHA_SHORTFALL)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def execute(plan_path:Path):
    source=json.loads(plan_path.read_text("ascii"))
    if (source.get("format")!="nvp.b11.native_review_plan.v1" or
        set(source)!={"format","project_id","source_presentation_id",
                     "source_presentation_sha256","source_take_id",
                     "source_take_sha256","review_id","studio_db_path",
                     "output_dir","source_primaries","frames","fps",
                     "resolution","policy_sha256","alpha_policy",
                     "max_alpha_shortfall"}):
        raise PermissionError("Malformed or unapproved native editorial plan")
    if (source["source_primaries"]!=SOURCE_COLOR_SPACE or source["fps"]!=24 or
        source.get("alpha_policy")!=NEAR_OPAQUE_ALPHA_POLICY or
        source.get("max_alpha_shortfall")!=MAX_ALPHA_SHORTFALL):
        raise PermissionError("Unverified original film source color, alpha or timing")
    if Path(source["output_dir"]).resolve()!=plan_path.parent/"display_frames":
        raise PermissionError("Native editor output was redirected")
    import hashlib
    from backend.nvp_color_ocio import color_policy
    policy,_=color_policy()
    if hashlib.sha256(canonical_bytes(policy)).hexdigest()!=source["policy_sha256"]:
        raise PermissionError("Native film SDR color policy changed")
    studio=Studio(Path(source["studio_db_path"]))
    capture=DigitalCapture(studio)
    actual=frozen_review_source(capture,source["project_id"],
                                source["source_presentation_id"])
    for k in ("source_presentation_sha256","source_take_id","source_take_sha256"):
        if actual[k]!=source[k]:
            raise RuntimeError("Original film source moved before color review")
    if (actual["frame_count"]!=source["frames"] or
        actual["resolution"]!=source["resolution"] or
        actual["fps"]!=source["fps"]):
        raise RuntimeError("Original frozen take timing or resolution changed")
    result=render_aces2_sdr_review(
        capture,source["project_id"],source["source_presentation_id"],
        source["review_id"],Path(source["output_dir"]),
        source_primaries_declared=True)
    receipt=plan_path.parent/"completed_review_receipt.json"
    with receipt.open("x",encoding="utf8") as out:
        out.write(json.dumps({
            "format":"nvp.b11.native_review_completed.v1",
            "review_id":source["review_id"],
            "project_id":source["project_id"],
            "source_take_id":source["source_take_id"],
            "original_source_sha256":source["source_presentation_sha256"],
            "presentation_sha256":result["presentation_sha256"],
            "frames":result["review_frame_count"],
            "all_frames_decoded":result["all_frames_decoded"],
            "screening_master":False,
        },sort_keys=True,ensure_ascii=True))
        out.flush()
        import os
        os.fsync(out.fileno())
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",required=True)
    args=parser.parse_args()
    print(json.dumps(execute(Path(args.plan)),sort_keys=True))


if __name__=="__main__":
    main()
