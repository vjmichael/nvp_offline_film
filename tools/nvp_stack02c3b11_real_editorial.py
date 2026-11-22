"""NVP B11: real original 120-frame Float32 EXR -> ACES2 SDR16 editorial review.

Reuses B9 actual frozen Digital Take, 15 native Blender render and 15 actual
float pixel readback jobs, then another explicitly approved contained NVP
worker applies the *existing* COLOR-01B ACES 2 SDR view. Every resulting
16-bit PNG is decoded and hashed, filed as a new project presentation and
rechecked after a fresh NVP Studio/FilmIndex restart.

CI's creator action is an isolated fixture signal, not a shipped desktop UI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from backend.nvp_b11_native_review import NativeB11ReviewHost
from backend.nvp_b11_editorial import verify_sdr_review
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from tools.nvp_stack02c3b9_real_exr import fixture as original_float_fixture


def fixture(out,blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    executable=Path(shutil.which(blender) or blender).resolve()
    if not executable.is_file():
        raise RuntimeError("Genuine native Blender required to make B11 source")
    version=subprocess.run([str(executable),"-b","--version"],
                           capture_output=True,text=True,check=True,timeout=20).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("B11 cannot accept a fake Blender source")
    b9=original_float_fixture(root/"b9_frozen_source",str(executable),160,90)
    if (b9["full_disk_index_reopen_verified"] is not True or
        b9["full_timed_take_exr_frames"]!=120 or
        b9["all_frames_32_bit_float_rgba"] is not True):
        raise RuntimeError("Original B9 native FilmIndex source not accepted")
    film_db=root/"b9_frozen_source"/"frozen_take_source"/"film.sqlite3"
    studio=Studio(film_db)
    with studio._connection() as db:
        projects=[x[0] for x in db.execute("SELECT id FROM projects")]
    if len(projects)!=1:
        raise RuntimeError("Original frozen source film ambiguous")
    project_id=projects[0]
    capture=DigitalCapture(studio)
    ledger=TaskLedger(root/"native_editorial_activity")
    event=object()
    seen=[]
    def trusted_test_only_creator(signal,scope):
        seen.append(scope)
        return (signal is event and scope.get("project_id")==project_id and
                scope.get("source_take_id")==b9["source_take_id"] and
                scope.get("frames")==120 and scope.get("fps")==24 and
                scope.get("output")=="color_managed_ACES2_sRGB_16bit_RGB_PNG_sequence")
    host=NativeB11ReviewHost(
        capture,ledger,root/"contained_editorial_worker",
        verify_creator_action=trusted_test_only_creator)
    queued=host.stage_and_approve(
        project_id,b9["indexed_frame_presentation_id"],event,
        ram_mb=2048,duration_s=7200)
    previous=ledger.sampler
    ledger.sampler=lambda:ResourceSnapshot(1,16384,900,0,())
    low=host.run_next()
    if (low is None or low["state"]!="QUEUED" or
        ledger.snapshot()["reservations"]["ram_mb"]!=0):
        raise RuntimeError("Unsafe physical RAM did not prevent native editorial work")
    ledger.sampler=previous
    executed=host.run_next(timeout_seconds=2700)
    if executed["state"]!="SUCCEEDED":
        raise RuntimeError("Actual native full SDR editorial review was not accepted")
    # Completely new native host + Studio = persistent original source and
    # independently checkable derived display-referred RGB PNG sequence.
    reopened_capture=DigitalCapture(Studio(film_db))
    again=NativeB11ReviewHost(
        reopened_capture,ledger,host.root,
        verify_creator_action=lambda *_:False)
    checked=again.verify_completed(queued["job_id"])
    if (checked["state"]!="VERIFIED_COMPLETE" or
        checked["review_frame_count"]!=120 or
        checked["fps"]!=24 or checked["cut_count"]!=2 or
        checked["all_frames_decoded"] is not True):
        raise RuntimeError("Native editorial review not restart-safe")
    raw=reopened_capture.index.read_revision(project_id,queued["review_id"])
    if (len(raw["data"]["review_frames"])!=120 or
        [x["frame"] for x in raw["data"]["review_frames"]]!=list(range(1,121)) or
        raw["data"]["calibrated_display_or_final_grade"] is not False or
        raw["data"]["fully_rendered_video_file"] is not False or
        raw["data"]["display_review_alpha_policy"]!="nvp.display_review.near_opaque_aa_alpha_v1" or
        any(x["alpha_audit"]["source_alpha_min"]<.997 or
            x["alpha_audit"]["actual_transparency_composited"] is not False
            for x in raw["data"]["review_frames"])):
        raise RuntimeError("Review cannot pretend to be a finished film")
    if ledger.snapshot()["reservations"]["ram_mb"]!=0:
        raise RuntimeError("Native 120-frame SDR view retained RAM reservation")
    receipt={
        "format":"nvp.stack02c3b11.real_aces2_sdr_editorial.v1",
        "original_take_sha256":b9["source_take_sha256"],
        "original_b9_all_float32_frames":120,
        "actual_native_blender_source":True,
        "native_separate_aces2_review_worker":True,
        "official_ocio_sdr_display_view":checked["color_policy"]["view"],
        "ocio_config_serialized_sha256":checked["color_policy"]["config_sha256"],
        "genuine_16bit_rgb_png_frames":120,
        "near_opaque_workbench_aa_alpha_policy":
            raw["data"]["display_review_alpha_policy"],
        "true_transparency_composition_performed":False,
        "authoritative_original_exr_alpha_untouched":True,
        "full_independent_png16_readback":True,
        "original_fps":checked["fps"],
        "exact_immutable_camera_cuts":checked["cutlist"],
        "native_review_presentation_id":queued["review_id"],
        "filmindex_source_and_derived_reopened_after_restart":True,
        "original_frozen_take_unchanged":True,
        "actual_OS_resource_reservation_remaining_mb":0,
        "native_creator_event":"test_fixture_not_installed_UI",
        "master_movie_encoded":False,
        "display_calibrated":False,
        "soundtrack_mixed":False,
        "lu_dlc_interface_dependency":False,
    }
    (root/"nvp_b11_editorial_acceptance.json").write_text(
        json.dumps(receipt,sort_keys=True,indent=2),"utf8")
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--blender",default="blender")
    args=p.parse_args()
    print(json.dumps(fixture(args.out,args.blender),indent=2,sort_keys=True))
