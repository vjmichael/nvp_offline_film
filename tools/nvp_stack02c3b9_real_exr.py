"""NVP B9 genuine FULL 120-frame scene-linear OpenEXR frozen-take acceptance.

Reuses a *real* B8 Frozen DTP + native Blender build + independently indexed
presentation as source. Runs 15 bounded EXR render workers and 15 separate
float pixel-readback workers; each job uses OS containment + real RAM
admission. High-bit-depth EXRs are not 8-bit PNG conversions.

The native creator UI event in CI is a deterministic fixture signal only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_exr_publish import publish_exr_sequence,verify_indexed_exr_sequence
from backend.nvp_exr_sequence import NativeEXRSequence
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from tools.nvp_stack02c3b8_real_frozen_take import fixture as frozen_source_fixture


def fixture(out,blender,width=160,height=90):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    exe=Path(shutil.which(blender) or blender).resolve()
    if not exe.is_file():
        raise RuntimeError("Real Blender required for true native EXR frame evidence")
    version=subprocess.run([str(exe),"-b","--version"],capture_output=True,
                            text=True,timeout=20,check=True).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("Unexpected native Blender version")

    # Use B8's *real* source lineage and two supervised native Blender runs.
    b8=frozen_source_fixture(root/"frozen_take_source",str(exe))
    studio=Studio(root/"frozen_take_source"/"film.sqlite3")
    with studio._connection() as db:
        pids=[r[0] for r in db.execute("SELECT id FROM projects")]
    if len(pids)!=1:
        raise RuntimeError("Expected one original indexed B8 film")
    pid=pids[0]
    capture=DigitalCapture(studio)
    tid=b8["approved_take_id"]
    preview=b8["filmindex_derived_presentation_id"]
    if b8["filmindex_presentation_restart_verification"] is not True:
        raise RuntimeError("Original indexed timed native Blender source not independently verified")

    ledger=TaskLedger(root/"exr_activity")
    worker=BlenderWorkerSupervisor(
        root/"native_exr_worker",blender_executable=exe,
        blender_sha256=sha_file(exe),blender_version=version,
        activity_ledger=ledger)
    event=object()
    consent_scopes=[]
    def native_creator_fixture(incoming,scope):
        consent_scopes.append(scope)
        return (incoming is event and
                scope["project_id"]==pid and
                scope["take_id"]==tid and
                scope["frame_count"]==120 and
                scope["fps"]==24 and
                scope["channels"]=="RGBA_FLOAT32" and
                scope["view_transform"]=="Raw")
    renderer=NativeEXRSequence(capture,worker,ledger,
                               verify_creator_action=native_creator_fixture)
    receipt=renderer.create_from_trusted_native_action(
        pid,tid,preview,event,width=width,height=height,
        chunk_size=8,ram_mb=2048,duration_s=7200)
    sid=receipt["sequence_id"]
    real_sampler=ledger.sampler
    all_chunks=[]
    for i in range(15):
        staged=renderer.queue_next_chunk(sid)
        if staged is None:
            raise RuntimeError("EXR output prematurely reported complete")
        if i==0:
            ledger.sampler=lambda:ResourceSnapshot(1,16384,800,0,())
            blocked=renderer.run_queued_chunk()
            if (blocked is None or blocked.get("state")!="QUEUED" or
                any((worker.root/staged["job_id"]).glob("frame_*.exr"))):
                raise RuntimeError("Low-memory native EXR worker was not prevented from starting")
            ledger.sampler=real_sampler
        built=renderer.run_queued_chunk()
        if built is None or built.get("state")!="SUCCEEDED":
            raise RuntimeError("Contained EXR native frame renderer did not finish: "+str(built))
        checked=renderer.verify_or_audit_batch(sid,staged["chunk"][0])
        if checked["state"]!="VERIFIED":
            raise RuntimeError("Second native Blender EXR float pixel readback refused: "+str(checked))
        all_chunks.append(checked)
    if renderer.queue_next_chunk(sid) is not None:
        raise RuntimeError("Extra frames appeared after the full timed native sequence")
    progress=renderer.full_progress(sid)
    if (progress["frames_total"]!=120 or progress["chunks_total"]!=15 or
        progress["chunks_rendered"]!=15 or progress["chunks_audited"]!=15):
        raise RuntimeError("Native EXR renderer omitted or duplicated a chunk")
    if ledger.snapshot()["reservations"]["ram_mb"]!=0:
        raise RuntimeError("NVP full EXR sequence retained an actual RAM reservation")
    published=publish_exr_sequence(renderer,sid)
    index_restarted=DigitalCapture(Studio(studio.db_path))
    reopened=verify_indexed_exr_sequence(index_restarted,pid,published["presentation_id"])
    if (reopened["status"]!="VERIFIED_COMPLETE_EXR_SEQUENCE" or
        reopened["frames"]!=120 or reopened["fps"]!=24 or
        reopened["actual_rgba_float32"] is not True):
        raise RuntimeError("Restarted FilmIndex failed real full-frame EXR verification")

    report={
        "format":"nvp.stack02c3b9.real_native_full_float_exr.v1",
        "actual_blender_version":version,
        "actual_blender_binary_sha256":sha_file(exe),
        "source_take_id":tid,"source_take_sha256":published["source_take_sha256"],
        "source_immutable_native_blend_sha256":b8["blender_take_sha256"],
        "frozen_original_source_reopened":True,
        "full_timed_take_exr_frames":reopened["frames"],
        "fps":reopened["fps"],"resolution":[reopened["width"],reopened["height"]],
        "native_render_worker_batches":len(all_chunks),
        "independent_native_pixel_readback_batches":len(all_chunks),
        "all_frames_32_bit_float_rgba":True,
        "native_scene_linear_raw_write":True,
        "ocio_config_fingerprint_verified":False,
        "aces_working_space_verified":False,
        "native_host_creator_event":"fixture_simulated_not_installed_UI",
        "readback_checks":sum(row["checks"] for row in all_chunks),
        "low_RAM_refusal_before_start":True,
        "native_activity_reservation_remaining_mb":0,
        "indexed_frame_presentation_id":published["presentation_id"],
        "full_disk_index_reopen_verified":True,
        "original_take_remains_unmodified":True,
        "finished_video_or_dcp":False,
        "lu_dlc_runtime_dependency":False,
    }
    (root/"nvp_b9_real_exr_acceptance.json").write_text(
        json.dumps(report,sort_keys=True,indent=2),"utf8")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--blender",default="blender")
    p.add_argument("--width",type=int,default=160)
    p.add_argument("--height",type=int,default=90)
    args=p.parse_args()
    print(json.dumps(fixture(args.out,args.blender,args.width,args.height),
                     sort_keys=True,indent=2))
