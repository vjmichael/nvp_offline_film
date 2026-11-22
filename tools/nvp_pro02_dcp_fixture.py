"""Independent PRO-02 DCP-o-matic cinema package smoke test.

It uses the exact NVP FilmIndex+blobs from the frozen-take/ProRes native CI
acceptance artifact, not an unrelated synthetic colorbar. Audio is explicitly
a *technical silent film test*, never director-approved dialog or cinema-ready.
Requires the optional DCP-o-matic CLI and its independent verifier installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nvp_cinema_dcp import CinemaDCP
from backend.nvp_cinema_duration import DURATION_PAD
from backend.nvp_studio import Studio


def fixture(db_path, output):
    db=Path(db_path).resolve()
    if not db.is_file():
        raise RuntimeError("Expected real frozen NVP film database from native acceptance")
    studio=Studio(db)
    projects=studio.list_projects()
    if len(projects)!=1:
        raise RuntimeError("Could not identify exact real film/project source")
    project_id=projects[0]["id"]
    cinema=CinemaDCP(studio)
    source_id="motion_prores_hq"
    before=cinema.motion.reopen(project_id,source_id,check_decode=True)
    take_id=before["record"]["data"]["source_take_id"]
    take_before=cinema.motion.capture.reopen(project_id,take_id)
    pre=cinema.preflight(project_id,source_id,audio_policy="explicit_silent_test",
                         duration_policy=DURATION_PAD)
    if pre["status"]!="technical_test_only" or not pre["warnings"]:
        raise RuntimeError("A source lacking approved sound must not be flagged theatrical-ready")
    result=cinema.package_technical_test(
        project_id,source_id,"dcp_smpte_2k_flat_technical",
        output,name="NVP Silent Test",profile="smpte_2k_flat_24",
        audio_policy="explicit_silent_test",director_silent_test_approval=True,
        duration_policy=DURATION_PAD,director_padding_approval=True,
        timeout=1200)
    reopened=CinemaDCP(Studio(db))
    verify=reopened.reopen(project_id,"dcp_smpte_2k_flat_technical",
                           check_decode=True)
    take_after=reopened.motion.capture.reopen(project_id,take_id)
    if take_before["record"]["document_sha256"]!=take_after["record"]["document_sha256"]:
        raise RuntimeError("DCP package work altered the original director-approved take")
    if verify["screening_ready"]:
        raise RuntimeError("Technical test cannot silently become a verified cinema master")
    picture=result["picture_evidence"]
    if picture["status"]!="independent_mxf_jpeg2000_decode_technical_only":
        raise RuntimeError("DCP lacks independently decoded JPEG 2000 MXF picture evidence")
    duration=pre["duration_contract"]
    if (picture["total_decoded_frames"]!=duration["dcp_frames"] or
        picture["source_frames"]!=before["record"]["data"]["frame_count"] or
        picture["duration_contract"]!=duration):
        raise RuntimeError("DCP duration and source-timecode proof disagree")
    if duration["black_tail_frames"]:
        zero=picture["black_tail_evidence"]
        if (not zero or zero["status"]!="independent_exact_zero_tail" or
            zero["padded_frames"]!=duration["black_tail_frames"]):
            raise RuntimeError("Director-approved black DCP extension was not proved")

    if verify["structure"]!=result["structure"]:
        raise RuntimeError("Package differs from the independently reopened indexed DCP")
    report={
        "format":"nvp.pro02.dcp.test.v1",
        "status":"passed_source_bound_duration_verified_technical_dcp",
        "source_take_sha256":take_after["record"]["document_sha256"],
        "source_motion_sha256":before["record"]["document_sha256"],
        "source_video_sha256":before["media"]["sha256"],
        "package_dir":result["package_dir"],
        "structure":result["structure"],
        "picture_evidence":picture,
        "duration_contract":duration,
        "preflight":pre,
        "externally_verified_by":"dcpomatic2_verify_cli",
        "screening_ready":False,
        "known_issues":[
            "Generated from low-res 8-bit proxy picture, not calibrated 12-bit XYZ cinema master",
            "Technical silent output: approved waveform/mix absent",
            "No independently measured projector/server ingest or festival venue compatibility",
        ],
    }
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    (out/"technical_dcp_report.json").write_text(
        json.dumps(report,indent=2,sort_keys=True),"utf-8")
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    report=fixture(args.db,args.out)
    print(json.dumps({"status":report["status"],"screening_ready":False,
          "asset_count":report["structure"]["asset_count"],
          "source_motion_sha":report["source_motion_sha256"]},indent=2))


if __name__=="__main__":
    main()
