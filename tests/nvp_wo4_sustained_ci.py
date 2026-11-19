"""Windows protected native repeated-frame duration stress (synthetic only).

Adapted from original WO4 2/3-hour repeated-frame stress. No unprotected
subprocess, shared-inode worker inputs, or synthetic result represented as a
unique-frame render. Native stage limit is unchanged: split into smaller reels
based on actual encoded bytes. The physical creator-film target is separate.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from nvp_wo3_fixture_authority import fixture_codec
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_wo3_native_codecs import MAX_STAGE_BYTES
from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_wo4_picture_spool import encode_disk_xyz12,wrap_disk_j2k_picture
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate,_hash_stream
from backend.nvp_wo4_mxf_stream import _copy_protected
from backend.nvp_wo4_supervised_sound import wrap_supervised_sound
from backend.nvp_wo4_resource_budget import plan_feature,require_stage_space
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_w1g_release_gate import inspect_original_process_journals


def run(root,profile,frame_count,reel_frames,*,dual_qualification=False):
    if os.name!="nt" or os.environ.get("GITHUB_ACTIONS")!="true":
        raise PermissionError("Generated Windows CI fixtures only")
    if (profile not in PROFILES or type(frame_count) is not int or
        not 6<=frame_count<=30*60*24 or type(reel_frames) is not int or
        not 3<=reel_frames<=7200 or frame_count<=reel_frames):
        raise ValueError("Bounded synthetic multireel duration required")
    if type(dual_qualification) is not bool or (dual_qualification and (frame_count,reel_frames)!=(48,24)):
        raise ValueError("Dual qualification requires two full 24-frame reels")
    root=Path(root).absolute()
    root.mkdir(mode=0o700,exist_ok=False)
    require_efs_stage(root)
    origin=sha256(b"WO4 repeated synthetic frame fixture").hexdigest()
    decision=sha256(b"WO4 generated repeated-frame duration decision").hexdigest()
    enc=fixture_codec("NVP_NATIVE_OPENJPEG","OpenJPEG-opj_compress")
    wrap=fixture_codec("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap")
    info=fixture_codec("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info")
    never=lambda:False
    width,height,_=PROFILES[profile]
    started=time.monotonic()
    originals=[]
    encoded=[]
    unique=12 if dual_qualification else 3
    for i in range(unique):
        value=(120,1000,2200)[i%3]
        path=root/f"input-{i}.xyz12"
        if dual_qualification:
            from nvp_wo4_unique_frame_pilot_ci import patterned_xyz12
            digest=patterned_xyz12(path,width,height,i)
        else:
            line=value.to_bytes(2,"big")*3*width
            h=sha256()
            with path.open("xb") as out:
                for _ in range(height):
                    out.write(line);h.update(line)
                out.flush();os.fsync(out.fileno())
            digest=h.hexdigest()
        originals.append((path,digest))
        stage=root/f"codec-{i}";stage.mkdir()
        record=encode_disk_xyz12(enc,profile=profile,source_path=str(path),
            source_sha256=digest,source_take_sha=origin,private_work=stage,check_cancel=never)
        if record["source_sha256"]!=digest:
            raise PermissionError("Encoded picture reference identity changed")
        encoded.append((stage/"frame.j2c",record["codestream_sha256"],record["codestream_bytes"]))
    if len({e[1] for e in encoded})!=unique:
        raise RuntimeError("Synthetic inputs must encode distinct codestreams")
    peak=max(e[2] for e in encoded)
    # Two copies, per-frame overhead and 20 MiB reserve; also obey the
    # exact streamed sound bound for stereo PCM24.
    limit=min(reel_frames,7200,(MAX_STAGE_BYTES-20*1024*1024)//(2*peak+8192),
              (MAX_STAGE_BYTES//2-16*1024*1024-128)//12000)
    plan=plan_feature(frames=frame_count,profile=profile,channels=2,max_reel_frames=limit)
    if not 2<=plan["reel_count"]<=127:
        raise ValueError("Synthetic duration exceeds approved feature dependency budget")
    require_stage_space(root,frame_count*(4*peak+4*12000+16384)+64*1024*1024)
    if dual_qualification and [r["frame_count"] for r in plan["reels"]]!=[24,24]:
        raise RuntimeError("Dual qualification requires both full reels")
    parts=[]
    expected_reels=[]
    by_source_digest={digest:path for path,digest in originals}
    for n,r in enumerate(plan["reels"]):
        count=r["frame_count"]
        reel=root/f"reel-{n:03d}";reel.mkdir()
        frames=reel/"frames";frames.mkdir()
        pstage=reel/"picture";pstage.mkdir()
        sstage=reel/"sound";sstage.mkdir()
        shas=[]
        references=[]
        for i in range(count):
            position=((r["first_frame"]+i) if not dual_qualification or n==0 else (unique-1-i))%unique
            source,digest,size=encoded[position]
            references.append(originals[position][1])
            _copy_protected(source,frames/f"{i:06d}.j2c",digest,size,never)
            shas.append(digest)
        pic_id=str(uuid4());snd_id=str(uuid4())
        pic=wrap_disk_j2k_picture(wrap,info,frames_dir=frames,stage_dir=pstage,
            frame_count=count,profile=profile,asset_uuid=pic_id,check_cancel=never,
            source_take_sha=origin,ordered_codestream_sha256=shas)
        pcm=reel/"source.pcm"
        pcm_digest=sha256()
        block=b"\0"*12000
        with pcm.open("xb") as out:
            for i in range(count):
                if dual_qualification:
                    # Distinct nonzero 24-bit stereo samples across reels.
                    value=(n*24+i+1)*1000
                    block=(value.to_bytes(3,"little",signed=True)+(-value).to_bytes(3,"little",signed=True))*2000
                out.write(block);pcm_digest.update(block)
            out.flush();os.fsync(out.fileno())
        wav=stream_master_pcm24_candidate(pcm,source_sha256=pcm_digest.hexdigest(),
            original_take_sha256=origin,cinema_frames=count,channel_layout="stereo",
            output_root=reel,approve=lambda _:True)
        sound=wrap_supervised_sound(wrap,info,candidate=wav,source_take_sha=origin,
            frames=count,sound_uuid=snd_id,stage_dir=sstage,check_cancel=never)
        expected_reels.append({"picture_uuid":pic_id,"sound_uuid":snd_id,"frames":count,
            "ordered_codestream_sha256":shas,"pcm_sha256":pcm_digest.hexdigest()})
        if dual_qualification:expected_reels[-1]["ordered_xyz12_sha256"]=references
        fields={"source_take_sha256":origin,"frame_count":count,"edit_rate":[24,1],
                "source_modified":False,"production_dcp_accepted":False}
        parts.append({"start_tick":r["start_tick"],"end_tick":r["end_tick"],
            "frames":count,"reel_uuid":str(uuid4()),
            "picture":{**fields,"kind":"picture","asset_uuid":pic_id,"profile":profile,
                "file_path":str(pstage/"picture.mxf"),"file_sha256":pic["file_sha256"],"file_bytes":pic["file_bytes"]},
            "sound":{**fields,"kind":"sound","asset_uuid":snd_id,
                "file_path":str(sstage/"sound.mxf"),"file_sha256":sound["file_sha256"],"file_bytes":sound["file_bytes"]}})
    output=root/"export";output.mkdir()
    result=publish_multireel_dcp(reels=parts,ids={k:str(uuid4()) for k in ("cpl","pkl","assetmap")},
        title="Generated native duration sample",profile=profile,output_root=output,
        check_cancel=never,approve=lambda _:True,source_take_sha256=origin,mastering_decision_sha256=decision)
    audit=inspect_dcp_structure(result["destination"])
    if audit["reel_durations"]!=[r["frames"] for r in parts] or sum(audit["reel_durations"])!=frame_count:
        raise RuntimeError("Native duration differs from planned frame count")
    dual_report=None
    schema_report=None
    if dual_qualification:
        from backend.nvp_dci_package_xsd import validate_official_package_xsd
        schemas=os.environ.get("NVP_DCI_SCHEMA_REFERENCE")
        if not schemas:raise RuntimeError("Pinned independent XSD source required for dual qualification")
        reviewed=validate_official_package_xsd(result["destination"],schemas,expected_profile=profile,source_set="LIBDCP_REVIEWED_MIRROR")
        if not reviewed["reviewed_smpte_xsd_mirror_verified"]:raise RuntimeError("Native package reviewed XSD gate failed")
        schema_report={k:reviewed[k] for k in ("schema_source_set","schema_source_sha256","metadata_sha256","reviewed_smpte_xsd_mirror_verified","official_smpte_xsd_verified")}
        from backend.nvp_wo3_independent_essence import decode_full_multireel_candidate
        def reference_reader(digest):
            from backend.nvp_wo3_dcp_structure import _linked_entry
            path=by_source_digest[digest]
            from backend.nvp_w1g_encrypted_source import verify_efs_inputs
            if _linked_entry(path) or not path.is_file():
                raise PermissionError("Reference raster identity changed")
            verify_efs_inputs(path.parent,names=(path.name,))
            with path.open("rb") as stream:
                return stream.read(width*height*6+1)
        dual_report=decode_full_multireel_candidate(result["destination"],
            unwrap=fixture_codec("NVP_NATIVE_ASDCP_UNWRAP","ASDCP-asdcp_unwrap"),
            decoder=fixture_codec("NVP_NATIVE_OPENJPEG_DECODE","OpenJPEG-opj_decompress"),
            second_decoder=fixture_codec("NVP_NATIVE_JASPER_DECODE","JasPer-nvp_decode"),
            expected_reels=expected_reels,profile=profile,reference_reader=reference_reader,descriptor_info=info)
        if (dual_report["frames_decoded"]!=48 or not dual_report["all_reel_packet_coverage_verified"] or
            not dual_report["all_tracks_minimum_one_second_verified"] or
            not dual_report["all_reels_mxf_descriptor_crosscheck_verified"] or
            not dual_report["nvp_unsigned_xml_profile_verified"] or
            not dual_report["all_reels_independent_second_decoder_verified"] or
            not dual_report["all_reels_source_xyz12_comparison_complete"] or
            dual_report["feature_source_xyz12_summary"]["source_to_openjpeg"]["frames_compared"]!=48 or
            dual_report["feature_source_xyz12_summary"]["source_to_jasper"]["frames_compared"]!=48 or
            not dual_report["all_reels_pcm24_sample_exact"] or
            dual_report["pcm_channel_count"]!=2 or dual_report["pcm_sample_frames_per_channel"]!=96000 or
            not all(r["pcm24_48000_sample_exact"] for r in dual_report["reels"])):
            raise RuntimeError("Independent full native essence qualification incomplete")
    for path,digest in originals:
        if _hash_stream(path)[0]!=digest:
            raise PermissionError("Generated source changed")
    custody=inspect_original_process_journals()
    if custody["unresolved_original_native_launches"] or custody["original_windows_launch_journals_verified"]<1:
        raise RuntimeError("Missing native custody")
    return {"status":"WO4_PROTECTED_NATIVE_DURATION_SAMPLE_PASS","profile":profile,
            "frame_slots":frame_count,"duration_seconds":frame_count/24,
            "encoded_unique_source_frames":unique,"reused_frame_slots":frame_count-unique,
            "dual_decoder_report":dual_report,
            "package_xsd_report":schema_report,
            "real_native_reels":len(parts),"complete_structural_asset_hashes_verified":True,
            "elapsed_seconds":round(time.monotonic()-started,3),
            "creator_film_throughput_verified":False,"production_dcp_accepted":False}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--profile",choices=("2K_FLAT_24","4K_SCOPE_24"),required=True)
    parser.add_argument("--frames",type=int,default=48)
    parser.add_argument("--reel-frames",type=int,default=24)
    parser.add_argument("--dual-qualification",action="store_true")
    args=parser.parse_args()
    print(json.dumps(run(args.root,args.profile,args.frames,args.reel_frames,dual_qualification=args.dual_qualification)),flush=True)
