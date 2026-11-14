"""NVP B10 real 1080p Blender frame and official ACES2 native color acceptance.

Source: genuine B8 frozen DTP, B9 complete 120-frame indexed Float32 EXRs.
Higher resolution: native contained 1920x1080 frame + independent native
Blender float pixel readback. Color: separate actual CPU OpenColorIO 2.5.2
ACES 2.0 conversion in OS-contained, creator-authorized RAM-admitted worker
from the B9 indexed original to genuine ACEScg Float32 OpenEXR, independently
reopened/verified and published as immutable FilmIndex derived presentation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from backend.nvp_b10_color_publish import publish_acescg_frame,verify_indexed_acescg_frame
from backend.nvp_b10_color_worker import NativeOCIOColorWorker
from backend.nvp_b10_ocio import load_verified_config
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_exr_sequence import NativeEXRSequence
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from tools.nvp_stack02c3b9_real_exr import fixture as b9_fixture


def fixture(out,blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    executable=Path(shutil.which(blender) or blender).resolve()
    if not executable.is_file():
        raise RuntimeError("Real Blender is required for 1080p B10 acceptance")
    version=subprocess.run(
        [str(executable),"-b","--version"],capture_output=True,
        check=True,text=True,timeout=20).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("Real Blender binary did not pass native version probe")
    # Full B9 verification must succeed first. No fabricated/Dummy EXR source.
    b9=b9_fixture(root/"b9_full_source",str(executable),160,90)
    if (b9["full_disk_index_reopen_verified"] is not True or
        b9["full_timed_take_exr_frames"]!=120 or
        b9["all_frames_32_bit_float_rgba"] is not True):
        raise RuntimeError("B9 original all-frame native evidence missing")
    db_path=root/"b9_full_source"/"frozen_take_source"/"film.sqlite3"
    studio=Studio(db_path)
    with studio._connection() as db:
        pids=[r[0] for r in db.execute("SELECT id FROM projects")]
    if len(pids)!=1:
        raise RuntimeError("B10 requires exactly one frozen source film")
    pid=pids[0]
    capture=DigitalCapture(studio)
    event=object()
    scopes=[]
    def verified_fixture_creator(incoming,context):
        scopes.append(context)
        if incoming is not event or context.get("project_id")!=pid:
            return False
        if context.get("operation")=="nvp.native.frozen_take.full_float32_exr_sequence":
            return (context.get("resolution")==[1920,1080] and
                    context.get("render_profile")=="full_HD" and
                    context.get("frame_count")==120 and
                    context.get("chunk_size")==1)
        if context.get("operation")=="nvp.native.aces2.ocio.float32_color_convert":
            return (context.get("resolution")==[160,90] and
                    context.get("target_color_space")=="ACEScg")
        return False
    ledger=TaskLedger(root/"b10_native_resource_activity")
    worker=BlenderWorkerSupervisor(root/"high_resolution_worker",
          blender_executable=executable,blender_sha256=sha_file(executable),
          blender_version=version,activity_ledger=ledger)
    high=NativeEXRSequence(capture,worker,ledger,
                          verify_creator_action=verified_fixture_creator)
    b8_preview_id=b9["source_immutable_native_blend_sha256"] # not a FilmIndex ID
    # B9's original EXR presentation points to its verified B8 .blend record.
    b9_index=capture.index.read_revision(pid,b9["indexed_frame_presentation_id"])
    actual_b8_preview_id=b9_index["data"]["source_preview_id"]
    high_receipt=high.create_from_trusted_native_action(
        pid,b9["source_take_id"],actual_b8_preview_id,
        event,width=1920,height=1080,chunk_size=1,ram_mb=3072,
        duration_s=7200)
    first=high.queue_next_chunk(high_receipt["sequence_id"])
    if first is None or first["chunk"]!=[1,1]:
        raise RuntimeError("Native Full HD work must stage exactly frame 1")
    native=high.run_queued_chunk()
    if native is None or native.get("state")!="SUCCEEDED":
        raise RuntimeError("Real 1920x1080 Blender scene did not pass admission: "+str(native))
    audited=high.verify_or_audit_batch(high_receipt["sequence_id"],1)
    if audited["state"]!="VERIFIED" or len(audited["frames"])!=1:
        raise RuntimeError("Second real Blender 1080p float readback not accepted")
    high_frame=worker.root/first["job_id"]/"frame_000001.exr"
    if not high_frame.is_file():
        raise RuntimeError("1920x1080 frame not emitted by actual Blender")

    # The official ACES2.0 config is available and pinned, independent of
    # Blender's bundled/possibly older default OCIO environment.
    config=load_verified_config()[2]
    native_color=NativeOCIOColorWorker(
        capture,ledger,root/"native_ocio_color_worker",
        verify_creator_action=verified_fixture_creator)
    approval=native_color.stage_and_approve(
        pid,b9["indexed_frame_presentation_id"],1,event,ram_mb=2048)
    completed=native_color.run_next()
    if completed is None or completed.get("state")!="SUCCEEDED":
        raise RuntimeError("Native OpenColorIO ACES2 transform failed: "+str(completed))
    color=native_color.verify_completed(completed["job_id"])
    published=publish_acescg_frame(native_color,completed["job_id"])
    after_restart=verify_indexed_acescg_frame(
        DigitalCapture(Studio(db_path)),pid,published["presentation_id"])
    if (after_restart["status"]!="VERIFIED_INDEXED_ACESCG_FLOAT32" or
        after_restart["color_space"]!="ACEScg" or
        after_restart["original_take_unchanged"] is not True):
        raise RuntimeError("Native ACEScg color EXR was not independently durable")
    if ledger.snapshot()["reservations"]["ram_mb"]!=0:
        raise RuntimeError("OCIO/native Blender RAM reservations were not fully released")
    report={
        "format":"nvp.stack02c3b10.real_hires_aces2.v1",
        "actual_blender_version":version,
        "blender_binary_sha256":sha_file(executable),
        "original_frozen_take_id":b9["source_take_id"],
        "original_frozen_take_sha256":b9["source_take_sha256"],
        "base_all_120_frame_native_float_exr_verified":True,
        "real_full_hd_frame_count_proven":1,
        "real_full_hd_resolution":[1920,1080],
        "full_hd_source_float32_channel_verified":True,
        "full_hd_independent_float_readback_checks":audited["checks"],
        "full_hd_native_rendering_supervised":True,
        "complete_1080p_sequence_rendered":False,
        "official_ocio_version":config["library_version"],
        "official_aces2_config_uri":config["config_uri"],
        "official_ocio_config_serialized_sha256":
            config["config_serialized_sha256"],
        "native_ocio_color_worker_separately_supervised":True,
        "native_acescg_float_exr_pixels_verified":True,
        "native_acescg_alpha_preserved":color["alpha_preserved"],
        "native_acescg_color_pixel_checks":color["sampled_pixels"],
        "indexed_color_presentation_id":published["presentation_id"],
        "indexed_color_reopened_after_restart":True,
        "acescg_color_transform_implemented":True,
        "full_blender_input_primaries_proven":False,
        "aces2_display_output_transform_proven":False,
        "final_film_video_or_dcp":False,
        "native_creator_event":"fixture_only_not_installed_desktop",
        "resource_ram_reservations_mb_after_completion":0,
        "lu_dlc_interface_dependency":False,
    }
    (root/"nvp_b10_real_hires_aces_acceptance.json").write_text(
        json.dumps(report,sort_keys=True,indent=2),"utf8")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--blender",default="blender")
    args=p.parse_args()
    print(json.dumps(fixture(args.out,args.blender),sort_keys=True,indent=2))
