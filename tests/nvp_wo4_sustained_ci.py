"""WO4 actual full-duration native cinema MXF + file-backed SMPTE feature stress.

CI only: 2h 2K / 3h 4K at 24fps, complete 5-minute reels, real OpenJPEG
and CineCert MXF wrapping, real stereo PCM24 48k sound for every reel, final
multi-reel CPL/PKL/AssetMap and independent full file hash verification.

IMPORTANT: only THREE different synthetic original XYZ12 frames are actually
encoded. Their approved J2K bytes are REUSED in repeating sequences across
all 172,800 or 259,200 picture slots to make a full-duration hosted CI test
practical. A synthetic five-minute PCM24 stereo master is likewise repeated
per reel. This measures native wrapping, duration, disk-backed assembly,
hashing and output durability—not sustained unique-frame image rendering,
theatrical quality or installed Windows/Linux Lu acceptance. No FFmpeg.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
from uuid import uuid4

from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo4_picture_spool import (
    encode_disk_xyz12,wrap_disk_j2k_picture,verify_frame_file)
from backend.nvp_wo4_supervised_sound import wrap_supervised_sound
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_wo4_resource_budget import plan_feature
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_production_journal import TICKS_PER_SECOND

CHECKPOINT_STEP=8
FRAME_TICKS=TICKS_PER_SECOND//24
MIN_REMAINING=800*1024*1024

def output(event,**fields):
    print(json.dumps({"event":event,**fields},sort_keys=True),flush=True)

def codec(env,product):
    path=os.getenv(env)
    if not path:
        raise RuntimeError("Native pinned codec missing: "+env)
    file=Path(path).resolve(strict=True)
    return ApprovedCodecBinary(file,product=product,sha256=digest_file(file))

def write_xyz12(file,width,height,code):
    pixel=code.to_bytes(2,"big")*3
    h=sha256()
    remaining=width*height
    with file.open("xb") as out:
        while remaining:
            count=min(remaining,65536)
            packet=pixel*count
            out.write(packet)
            h.update(packet)
            remaining-=count
        out.flush();os.fsync(out.fileno())
    return h.hexdigest()

def write_silent_pcm24(file,frame_count):
    # 48,000 samples/second at 24fps = 2,000 sample frames/film frame.
    total=frame_count*2000*2*3
    digest=sha256()
    block=b"\0"*(1024*1024)
    with file.open("xb") as stream:
        remaining=total
        while remaining:
            chunk=block[:min(remaining,len(block))]
            stream.write(chunk)
            digest.update(chunk)
            remaining-=len(chunk)
        stream.flush();os.fsync(stream.fileno())
    if file.stat().st_size!=total:
        raise AssertionError("Generated PCM24 sample count changed")
    return digest.hexdigest()

def rss_bytes():
    # Linux / GitHub ubuntu hosted: ru_maxrss is KiB for both categories.
    return {"parent_peak_rss_bytes":resource.getrusage(
        resource.RUSAGE_SELF).ru_maxrss*1024,
        "native_children_peak_rss_bytes":resource.getrusage(
        resource.RUSAGE_CHILDREN).ru_maxrss*1024}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--hours",type=int,choices=(2,3),required=True)
    parser.add_argument("--profile",choices=("2K_FLAT_24","4K_SCOPE_24"),
                        required=True)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--audit",type=Path,required=True)
    args=parser.parse_args()
    started=time.monotonic()
    width,height,fps=PROFILES[args.profile]
    assert fps==24
    total_frames=args.hours*3600*fps
    plan=plan_feature(frames=total_frames,profile=args.profile,channels=2)
    assert plan["reel_count"]==args.hours*12
    assert all(p["frame_count"]==7200 for p in plan["reels"])
    root=args.root.resolve()
    if root.is_symlink() or root.exists():
        raise FileExistsError("Fresh trusted scratch dir required for duration test")
    root.mkdir(mode=0o700,parents=True)
    disk_start=shutil.disk_usage(root)
    if disk_start.free<8*1024**3:
        raise OSError("Runner does not have 8GiB free scratch after codec build")
    outputs=root/"native_tracks"
    outputs.mkdir()
    origin=root/"original_xyz12"
    origin.mkdir()
    works=root/"j2k_workers"
    works.mkdir()
    frames=root/"picture_frames"
    frames.mkdir()
    # All codec binaries must be native SHA-pinned and reviewed at runtime.
    openjpeg=codec("NVP_NATIVE_OPENJPEG","OpenJPEG-opj_compress")
    wrap=codec("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap")
    info=codec("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info")
    original_shas={}
    j2k=[]
    for index,code in enumerate((256,1024,2400)):
        raw=origin/f"frame_{index}.xyz12"
        original_shas[str(raw)]=write_xyz12(raw,width,height,code)
        work=works/f"frame_{index}"
        work.mkdir()
        receipt=encode_disk_xyz12(
            openjpeg,profile=args.profile,
            source_path=str(raw),source_sha256=original_shas[str(raw)],
            private_work=work,check_cancel=lambda:False,timeout=900)
        assert receipt["status"]=="ENCODED_J2K_STAGE_VERIFIED"
        codestream=work/"frame.j2c"
        assert receipt["codestream_sha256"]==digest_file(codestream)
        j2k.append((codestream,receipt["codestream_sha256"]))
    # 7,200 actual named J2K inputs, in a deterministic three-frame loop.
    # Hardlinks prevent a second encoding of identical test-only frames.
    for index in range(7200):
        os.link(j2k[index%3][0],frames/f"{index:06d}.j2c")
    for index in (0,1,2,3599,7199):
        expected=j2k[index%3][1]
        assert verify_frame_file(
            frames/f"{index:06d}.j2c",expected,args.profile)>0
    pcm=root/"original_stereo_pcm24.pcm"
    pcm_sha=write_silent_pcm24(pcm,7200)
    wav_root=root/"approved_pcm"
    wav_root.mkdir()
    take_sha=sha256(b"NVP_CI_SYNTHETIC_LONGFORM_IMMUTABLE_TAKE").hexdigest()
    master=stream_master_pcm24_candidate(
        pcm,source_sha256=pcm_sha,original_take_sha256=take_sha,
        cinema_frames=7200,channel_layout="stereo",
        output_root=wav_root,approve=lambda scope:
        scope["original_take_sha256"]==take_sha)
    assert master["status"]=="STREAMED_PCM24_CANDIDATE_PUBLISHED"
    sha_in=master["wav_file_sha256"]
    original_shas[str(pcm)]=pcm_sha
    original_shas[master["destination"]]=sha_in
    ids={kind:str(uuid4()) for kind in ("cpl","pkl","assetmap")}
    measured_peak_used=0
    reel_receipts=[]
    first_unit=None
    for reel_plan in plan["reels"]:
        i=reel_plan["reel_number"]-1
        stage=outputs/f"reel_{i:02d}"
        stage.mkdir()
        picture_stage=stage/"picture"
        picture_stage.mkdir()
        picture=wrap_disk_j2k_picture(
            wrap,info,frames_dir=frames,stage_dir=picture_stage,
            frame_count=7200,profile=args.profile,asset_uuid=str(uuid4()),
            check_cancel=lambda:False,timeout=900)
        assert picture["status"]=="NATIVE_PICTURE_MXF_STAGE_VERIFIED"
        sound_stage=stage/"sound"
        sound_stage.mkdir()
        sound=wrap_supervised_sound(
            wrap,info,candidate=master,source_take_sha=take_sha,
            frames=7200,sound_uuid=str(uuid4()),
            stage_dir=sound_stage,check_cancel=lambda:False)
        assert sound["status"]=="SOUND_MXF_STAGE_VERIFIED"
        # The private derivative WAV was verified before the MXF receipt,
        # so remove ONLY this disposable codec input copy to limit CI disk.
        (sound_stage/"sound.wav").unlink()
        picture_file=picture_stage/"picture.mxf"
        sound_file=sound_stage/"sound.mxf"
        assert digest_file(picture_file)==picture["file_sha256"]
        assert digest_file(sound_file)==sound["file_sha256"]
        segment={
            "start_tick":reel_plan["start_tick"],
            "end_tick":reel_plan["end_tick"],
            "frames":reel_plan["frame_count"],"reel_uuid":str(uuid4()),
            "picture":{
                "file_path":str(picture_file),
                "file_sha256":picture["file_sha256"],
                "file_bytes":picture["file_bytes"],
                "asset_uuid":picture["asset_uuid"]},
            "sound":{
                "file_path":str(sound_file),
                "file_sha256":sound["file_sha256"],
                "file_bytes":sound["file_bytes"],
                "asset_uuid":sound["asset_uuid"]}}
        reel_receipts.append(segment)
        available=shutil.disk_usage(root)
        measured_peak_used=max(measured_peak_used,disk_start.free-available.free)
        if first_unit is None:
            first_unit=picture["file_bytes"]+sound["file_bytes"]
            # Real host runner has 14GiB SSD. Enforce deterministic
            # full-duration output feasibility BEFORE wrapping all reels.
            required=2*len(plan["reels"])*first_unit+1024**3
            if available.free+first_unit<required:
                raise OSError(
                    f"GitHub hosted disk cannot hold BOTH full-duration "
                    f"source tracks and published feature DCP: "
                    f"required~{required}, free~{available.free}. "
                    f"Use larger runner or sharded long-form export.")
        if available.free<MIN_REMAINING:
            raise OSError("Low disk headroom before exact SHA checkpoint")
        if (i+1)%CHECKPOINT_STEP==0 or i==0 or i+1==len(plan["reels"]):
            output("native_reel_verified",profile=args.profile,
                   reel=i+1,total_reels=len(plan["reels"]),
                   completed_frames=(i+1)*7200,
                   pic_mxf_bytes=picture["file_bytes"],
                   snd_mxf_bytes=sound["file_bytes"],
                   available_bytes=available.free,
                   wall_seconds=round(time.monotonic()-started,2),
                   **rss_bytes())
    assert sum(p["frames"] for p in reel_receipts)==total_frames
    assert reel_receipts[-1]["end_tick"]==args.hours*3600*TICKS_PER_SECOND
    for path,digest in original_shas.items():
        assert digest_file(path)==digest, "Original media changed during export"
    stage_output=root/"final_feature"
    stage_output.mkdir()
    result=publish_multireel_dcp(
        reels=reel_receipts,ids=ids,
        title=f"NVP Synthetic {args.hours}h {args.profile} Duration Stress",
        profile=args.profile,output_root=stage_output,
        check_cancel=lambda:False)
    assert result["status"]=="MULTIREEL_STRUCTURAL_DCP_PUBLISHED"
    assert result["reel_count"]==len(reel_receipts)
    assert result["total_frames"]==total_frames
    assert result["production_dcp_accepted"] is False
    assert result["whole_feature_in_ram"] is False
    audit=inspect_dcp_structure(result["destination"])
    assert audit["status"]=="STRUCTURE_AND_SHA_VERIFIED"
    assert audit["reel_count"]==len(reel_receipts)
    assert audit["reel_durations"]==[7200]*len(reel_receipts)
    assert len(audit["tracks"])==len(reel_receipts)*2
    assert audit["cpl_uuid"]==ids["cpl"]
    output("full_duration_native_export_complete",hours=args.hours,
           profile=args.profile,frame_slots=total_frames,
           native_mxf_reels=len(reel_receipts),
           decoded_unique_j2k_frames=0,
           unique_j2k_encoded=3,
           repeated_j2k_slots=total_frames-3,
           source_pcm24_reel_count=1,
           repeated_sound_reels=len(reel_receipts),
           duration_seconds=args.hours*3600,
           duration_ticks=reel_receipts[-1]["end_tick"],
           output=result["destination"],
           full_smpte_structure_hashes_verified=True,
           independent_full_essence_decode=False,
           cinema_certification=False,
           real_time_render_of_all_unique_frames=False,
           elapsed_seconds=round(time.monotonic()-started,2),
           **rss_bytes())
    end_disk=shutil.disk_usage(root)
    measured_peak_used=max(measured_peak_used,disk_start.free-end_disk.free)
    report={
        "format":"nvp.wo4.github_ci_full_duration_synthetic_reels.v1",
        "status":"FULL_DURATION_NATIVE_MXF_AND_STRUCTURAL_DCP_VERIFIED",
        "test_mode":"repeat_three_real_j2k_codestreams_per_5min_reel",
        "hours":args.hours,"profile":args.profile,
        "frame_rate":24,"frame_slots":total_frames,
        "reels":len(reel_receipts),
        "unique_original_xyz12_encodes":3,
        "reused_picture_slots":total_frames-3,
        "repeated_stereo_pcm24_master":True,
        "all_native_picture_sound_mxf_wrapped":True,
        "complete_file_backed_smpte_dcp":True,
        "structural_pkls_sha1_verified":True,
        "sha256_source_custody_preserved":True,
        "independent_full_essence_decode":False,
        "unique_frame_render_benchmarked":False,
        "sustained_real_cinema_mxf_wrap_benchmarked":True,
        "feature_journal_filmindex_integration_benchmarked":False,
        "production_dci_accepted":False,
        "elapsed_seconds":round(time.monotonic()-started,3),
        "peak_disk_used_bytes":measured_peak_used,
        "initial_free_bytes":disk_start.free,
        "final_free_bytes":end_disk.free,
        "working_set_bytes":rss_bytes(),
        "total_dcp_assets":len(result["file_sha256"]),
        "output_cpl_uuid":ids["cpl"],
        "file_sha256_manifest":result["file_sha256"],
        "native_openjpeg_sha256":openjpeg.sha256,
        "native_asdcplib_wrapper_sha256":wrap.sha256,
        "native_asdcplib_info_sha256":info.sha256}
    args.audit.parent.mkdir(parents=True,exist_ok=True)
    with args.audit.open("x",encoding="utf-8") as dest:
        json.dump(report,dest,sort_keys=True,indent=2)
    output("WO4_SUSTAINED_CI_PASS",hours=args.hours,
           profile=args.profile,frame_slots=total_frames,
           reels=len(reel_receipts),
           elapsed_seconds=report["elapsed_seconds"],
           peak_disk_used_bytes=measured_peak_used,
           parent_peak_rss_bytes=report["working_set_bytes"]["parent_peak_rss_bytes"],
           genuine_native_picture_sound_mxf=True,
           finished_full_duration_smpte_package=True,
           all_unique_frames_encoded=False,
           physical_cinema_accepted=False)

if __name__=="__main__":
    main()
