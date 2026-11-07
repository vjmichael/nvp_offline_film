"""WO4-LF02 file-backed, real OpenJPEG → CineCert picture MXF workers.

Exactly one full XYZ12 frame (up to 4K) is stream-validated per worker.
Codestreams/MXF stay on disk, rather than a feature-length Python list.
A caller must own the durable job lease and host-approved immutable source.
No DCP is declared accepted merely from header/MXF metadata.
"""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import re

from backend.nvp_supervised_codec_process import run_supervised_codec
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo3_j2k_audit import PROFILES,inspect_j2k_header,MAX_CODESTREAM
from backend.nvp_wo3_mxf_native import INFO_RE,_verify_info
from backend.nvp_wo3_atomic_publish import _fsync_directory
from backend.nvp_wo4_resource_budget import require_stage_space

BLOCK=1024*1024
FRAME_RE=re.compile(r"[0-9]{6}\.j2c\Z")
MAX_FRAMES=7200


def _root(path):
    file=Path(path)
    if not file.is_absolute() or file.is_symlink() or not file.is_dir():
        raise PermissionError("Trusted absolute native spool directory required")
    return file.resolve(strict=True)


def stream_xyz12_to_ppm(source,expected_sha,profile,ppm,check_cancel):
    if profile not in PROFILES:
        raise ValueError("Approved cinema 2K/4K profile required")
    source=Path(source)
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise PermissionError("Trusted original XYZ12 frame file required")
    width,height,_=PROFILES[profile]
    count=width*height*6
    if source.stat().st_size!=count:
        raise ValueError("Original XYZ12 frame does not match selected cinema profile")
    if ppm.exists() or ppm.is_symlink():
        raise FileExistsError("Production work stage already exists; recovery required")
    digest=sha256()
    size=0
    header=f"P6\n{width} {height}\n4095\n".encode("ascii")
    with source.open("rb") as src,ppm.open("xb") as target:
        target.write(header)
        carry=b""
        while part:=src.read(BLOCK):
            if check_cancel():
                raise InterruptedError("Cancelled before native JPEG2000 encoding")
            size+=len(part)
            if size>count:
                raise ValueError("Original XYZ12 source grew during read")
            digest.update(part)
            checked=carry+part
            if len(checked)%2:
                carry=checked[-1:]
                checked=checked[:-1]
            else:
                carry=b""
            if any(checked[k]&0xF0 for k in range(0,len(checked),2)):
                raise ValueError("Source XYZ12 has components above 4095")
            target.write(checked)
        if carry or size!=count or digest.hexdigest()!=expected_sha:
            raise PermissionError("Original XYZ12 source SHA/size mismatch")
        target.flush()
        os.fsync(target.fileno())
    if digest_file(source)!=expected_sha:
        raise PermissionError("Original source changed while constructing PPM")
    return {"source_sha256":expected_sha,"bytes":size,
            "ppm_sha256":digest_file(ppm),"whole_reel_loaded_into_ram":False}


def encode_disk_xyz12(codec,*,profile,source_path,source_sha256,
                      private_work,check_cancel,timeout=3600):
    if (not isinstance(codec,ApprovedCodecBinary) or
            codec.product!="OpenJPEG-opj_compress"):
        raise PermissionError("Only SHA-reviewed OpenJPEG encoder allowed")
    root=_root(private_work)
    width,height,_=PROFILES[profile]
    require_stage_space(root,width*height*6+MAX_CODESTREAM+1024*1024)
    inp=root/"frame.ppm"
    output=root/"frame.j2c"
    if output.exists() or output.is_symlink():
        raise FileExistsError("Uncommitted codestream stage must be reviewed")
    input_receipt=stream_xyz12_to_ppm(
        source_path,source_sha256,profile,inp,check_cancel)
    cinema=(["-cinema4K"] if profile.startswith("4K_")
            else ["-cinema2K","24"])
    process=run_supervised_codec(
        codec,["-i","frame.ppm","-o","frame.j2c",*cinema,
               "-p","CPRL","-mct","0","-I"],
        workdir=root,check_cancel=check_cancel,timeout=timeout)
    if (output.is_symlink() or not output.is_file()
            or not 80<=output.stat().st_size<=MAX_CODESTREAM):
        raise RuntimeError("Real bounded JPEG2000 codestream missing")
    # Exactly one codestream at a time, <=16 MiB, not the entire reel.
    header=inspect_j2k_header(output.read_bytes(),profile)
    with output.open("rb+") as stream:
        os.fsync(stream.fileno())
    return {
        "format":"nvp.wo4.spool_frame.v1",
        "status":"ENCODED_J2K_STAGE_VERIFIED",
        "source_sha256":source_sha256,
        "codestream_sha256":header["raw_codestream_sha256"],
        "codestream_bytes":output.stat().st_size,
        "native_codec_sha256":codec.sha256,
        "worker":process,
        "input":input_receipt,
        "full_decode_verified":False,
        "production_dcp_accepted":False,
        "source_modified":False,
    }


def verify_frame_file(path,expected_sha,profile):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 80<=p.stat().st_size<=MAX_CODESTREAM:
        raise PermissionError("Verified frame file missing or unsafe")
    head=inspect_j2k_header(p.read_bytes(),profile)
    if head["raw_codestream_sha256"]!=expected_sha:
        raise PermissionError("Completed JPEG2000 frame digest changed")
    return p.stat().st_size


def wrap_disk_j2k_picture(wrap,info,*,frames_dir,stage_dir,
                          frame_count,profile,asset_uuid,check_cancel,
                          timeout=7200):
    if (not isinstance(wrap,ApprovedCodecBinary) or
            not isinstance(info,ApprovedCodecBinary) or
            wrap.product!="ASDCP-asdcp_wrap" or
            info.product!="ASDCP-asdcp_info"):
        raise PermissionError("Reviewed CineCert wrap+info tools required")
    if (profile not in PROFILES or type(frame_count) is not int or
            not 3<=frame_count<=MAX_FRAMES):
        raise ValueError("Bounded cinema frame count and 2K/4K profile required")
    from backend.nvp_wo3_mxf_native import _uuid_v4
    uid=_uuid_v4(asset_uuid)
    frames=_root(frames_dir)
    stage=_root(stage_dir)
    # Verify deterministic, gap-free native spool sequence before handing it
    # to a worker. Caller has already matched these to SQLite frame receipts.
    actual=sorted(p.name for p in frames.iterdir())
    expected=[f"{i:06d}.j2c" for i in range(frame_count)]
    if actual!=expected:
        raise PermissionError("Uncommitted/orphan codestream files require review")
    for i in range(frame_count):
        if check_cancel():
            raise InterruptedError("Creator cancelled picture MXF")
        path=frames/expected[i]
        if path.is_symlink() or path.stat().st_size>MAX_CODESTREAM:
            raise PermissionError("Unsafe native picture codestream")
        # SQLite checkpoint hashes are checked by the supervisor before this call.
    # Admission uses bytes of the already SHA-verified codestreams plus
    # a conservative 8 KiB/frame MXF index/header allowance. The previous
    # hard-coded 1 MiB/frame over-reservation blocked 5-minute low-entropy
    # reel packaging on 14 GiB CI workers despite tiny actual JPEG2000 data.
    # Runtime ENOSPC still fails closed with the stage retained for review.
    require_stage_space(stage,
        sum((frames/name).stat().st_size for name in expected)
        +frame_count*8192+16*1024*1024)
    out=stage/"picture.mxf"
    if out.exists() or out.is_symlink():
        raise FileExistsError("Uncommitted picture MXF exists; review before resume")
    process=run_supervised_codec(
        wrap,["-L","-a",uid.replace("-",""),
              "-p","24","-d",str(frame_count),
              str(frames),"picture.mxf"],workdir=stage,
        check_cancel=check_cancel,timeout=timeout)
    if out.is_symlink() or not out.is_file() or out.stat().st_size<128:
        raise RuntimeError("Native picture MXF not created")
    checked=run_supervised_codec(
        info,["-i","-d","picture.mxf"],workdir=stage,
        check_cancel=check_cancel,timeout=300,read_stdout=True)
    text=checked.pop("stdout").decode("utf-8","replace")
    props={k.strip().lower().replace(" ","_"):v.strip()
           for k,v in INFO_RE.findall(text)}
    if not props.get("label_set_type","").startswith("SMPTE"):
        raise RuntimeError("Native MXF is not SMPTE label set")
    _verify_info(props,uid,frame_count)
    with out.open("rb+") as stream:
        os.fsync(stream.fileno())
    return {
        "format":"nvp.wo4.file_picture_mxf.v1",
        "status":"NATIVE_PICTURE_MXF_STAGE_VERIFIED",
        "file_sha256":digest_file(out),
        "file_bytes":out.stat().st_size,
        "asset_uuid":uid,"profile":profile,
        "edit_rate":[24,1],"frame_count":frame_count,
        "wrapper_sha256":wrap.sha256,
        "info_sha256":info.sha256,
        "wrapper_process":process,
        "info_process":checked,
        "whole_mxf_loaded_into_ram":False,
        "independent_dci_validator_passed":False,
        "production_dcp_accepted":False,
    }
