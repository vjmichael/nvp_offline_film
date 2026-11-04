"""B12 real native production acceptance: original 120-frame take to OTIO and MOV.

The complete source is genuine B9 Blender Float32 EXR, then B11's official
ACES2 SDR 16-bit PNG frame review. This B12 fixture only uses actual persisted
source data; OTIO/PNG portability and ProRes MOV decoding are independent.
The native creator event is test-only and never stands for installed UI auth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from backend.nvp_b12_native_delivery import NativeB12DeliveryHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from tools.nvp_stack02c3b11_real_editorial import fixture as b11_fixture


def fixture(path,blender):
    root=Path(path).resolve()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    original=b11_fixture(root/"b11_original",blender)
    if (original["original_b9_all_float32_frames"]!=120 or
        original["genuine_16bit_rgb_png_frames"]!=120 or
        original["full_independent_png16_readback"] is not True or
        original["filmindex_source_and_derived_reopened_after_restart"] is not True):
        raise RuntimeError("Native B11 original film editorial proof missing")
    db=root/"b11_original"/"b9_frozen_source"/"frozen_take_source"/"film.sqlite3"
    studio=Studio(db)
    with studio._connection() as handle:
        pids=[x[0] for x in handle.execute("SELECT id FROM projects")]
    if len(pids)!=1:
        raise RuntimeError("Exactly one original NVP film project expected")
    pid=pids[0]
    original_review_id=original["native_review_presentation_id"]
    ledger=TaskLedger(root/"native_b12_resources")
    capture=DigitalCapture(studio)
    trusted=object()
    scopes=[]
    def authentic_fixture(signal,scope):
        scopes.append(scope)
        return (signal is trusted and
                scope["project_id"]==pid and
                scope["source_review_id"]==original_review_id and
                scope["source_take_id"] and
                scope["frame_count"]==120 and scope["fps"]==24 and
                len(scope["camera_cutlist"])==2 and
                scope["professional_video_profiles"]==["prores_422_hq_mov"] and
                scope["audio_present"] is False)
    exporter=NativeB12DeliveryHost(
        capture,ledger,root/"supervised_otio_delivery",
        verify_creator_action=authentic_fixture)
    receipt=exporter.stage_and_approve(
        pid,original_review_id,trusted,profiles=("prores_422_hq_mov",),
        ram_mb=2048,duration_s=7200)
    ledger.sampler=lambda:ResourceSnapshot(1,16384,900,0,())
    denied=exporter.run_next()
    if denied is None or denied["state"]!="QUEUED":
        raise RuntimeError("Insufficient RAM must refuse native editorial process")
    ledger.sampler=lambda:ResourceSnapshot(1,32768,24000,0,())
    executed=exporter.run_next(timeout_seconds=3600)
    if executed is None or executed["state"]!="SUCCEEDED":
        raise RuntimeError("Original NVP frozen OTIO/media/ProRes handoff did not complete")
    restarted=NativeB12DeliveryHost(
        DigitalCapture(Studio(db)),ledger,exporter.root,
        verify_creator_action=lambda *_:False)
    proof=restarted.verify_completed(receipt["job_id"])
    if (proof["frames"]!=120 or proof["fps"]!=24 or
        proof["cut_count"]!=2 or proof["official_otio_parsed"] is not True or
        proof["full_rgb48_independent_decode"] is not True or
        proof["video_candidates_verified"]!=["prores_422_hq_mov"] or
        proof["portable_media_all_present"] is not True or
        proof["source_float32_exr_unchanged"] is not True):
        raise RuntimeError("Fresh NVP process could not reopen complete editorial interchange")
    package=Path(executed["package_directory"])
    if (not (package/"timeline.otio").is_file() or
        not (package/"prores_422_hq_mov.mov").is_file() or
        len(list((package/"media").glob("review_*.png")))!=120 or
        ledger.snapshot()["reservations"]["ram_mb"]!=0):
        raise RuntimeError("B12 native portable film artifacts missing or RAM leaked")
    report={
        "format":"nvp.stack02c3b12.native_otio_delivery_acceptance.v1",
        "original_digital_take_sha256":original["original_take_sha256"],
        "verified_source_float32_frame_count":120,
        "verified_input_aces2_sdr_png16_frames":120,
        "portable_output_png16_frames":120,
        "exact_original_frozen_camera_cuts":proof["cut_count"],
        "fps":24,"running_time_s":5,
        "real_OpenTimelineIO_0_18_1_schema_parsed":True,
        "otio_portable_package_reference":"timeline.otio",
        "verified_prores_profile":"prores_422_hq_mov",
        "real_10bit_yuv422_decoded_and_compared":True,
        "native_OS_contained_worker":True,
        "native_creator_presence_event":"test_fixture_only_not_installed_UI",
        "disk_handoff_directory":str(package),
        "FilmIndex_verified_after_restart":True,
        "physical_RAM_reservation_remaining_mb":0,
        "audio_included":False,"final_picture_lock":False,
        "film_master_approved":False,"cinema_DCP_delivered":False,
        "lu_DLC_interface_dependency":False,
    }
    (root/"nvp_b12_real_acceptance.json").write_text(
        json.dumps(report,sort_keys=True,indent=2),"utf8")
    return report


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--out",required=True)
    cli.add_argument("--blender",default="blender")
    args=cli.parse_args()
    print(json.dumps(fixture(args.out,args.blender),indent=2,sort_keys=True))
