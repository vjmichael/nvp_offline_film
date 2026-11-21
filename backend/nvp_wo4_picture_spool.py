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

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file,common_codec_authority,_sha,MAX_STAGE_BYTES
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_wo4_mxf_stream import _copy_protected,_publish_protected
from backend.nvp_wo3_dcp_structure import _linked_entry
from backend.nvp_wo3_j2k_audit import PROFILES,MAX_CODESTREAM
from backend.nvp_dci_codestream import MAX_FRAME_BYTES
from backend.nvp_dci_packets import inspect_cinema_packets, ReelPacketAudit
from backend.nvp_wo3_mxf_native import _read_info,_verify_info
from backend.nvp_wo3_atomic_publish import _fsync_directory
from backend.nvp_wo4_resource_budget import require_stage_space

BLOCK=1024*1024
FRAME_RE=re.compile(r"[0-9]{6}\.j2c\Z")
MAX_FRAMES=7200


def _root(path):
    file=Path(path)
    _protected_path(file,directory=True)
    return file.resolve(strict=True)


def stream_xyz12_to_ppm(source,expected_sha,profile,ppm,check_cancel):
    if profile not in PROFILES:
        raise ValueError("Approved cinema 2K/4K profile required")
    source=Path(source)
    identity=_protected_path(source)
    _protected_path(ppm.parent,directory=True)
    _sha(expected_sha)
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
        st=os.fstat(src.fileno())
        if (st.st_dev,st.st_ino)!=identity:
            raise PermissionError("Original XYZ12 file changed at open")
        _protected_path(ppm)
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
    if _protected_path(source)!=identity or _hash_stream(source)!=(expected_sha,count):
        raise PermissionError("Original source changed while constructing PPM")
    return {"source_sha256":expected_sha,"bytes":size,
            "ppm_sha256":digest_file(ppm),"whole_reel_loaded_into_ram":False}


def encode_disk_xyz12(codec,*,profile,source_path,source_sha256,
                      private_work,check_cancel,source_take_sha,timeout=3600):
    if (not isinstance(codec,ApprovedCodecBinary) or
            codec.product!="OpenJPEG-opj_compress"):
        raise PermissionError("Only SHA-reviewed OpenJPEG encoder allowed")
    origin=_sha(source_take_sha)
    common_codec_authority(codec)
    root=_root(private_work)
    width,height,_=PROFILES[profile]
    require_stage_space(root,width*height*6+MAX_CODESTREAM+1024*1024)
    output=root/"frame.j2c"
    if output.exists() or _linked_entry(output):
        raise FileExistsError("Uncommitted codestream stage must be reviewed")
    if not callable(check_cancel) or check_cancel():
        raise InterruptedError("Creator cancelled picture encoding")
    with codec.stage(origin) as stage:
        require_stage_space(stage,width*height*6+MAX_CODESTREAM+1024*1024)
        inp=stage/"approved_xyz.ppm"
        input_receipt=stream_xyz12_to_ppm(source_path,source_sha256,profile,inp,check_cancel)
        cinema=(["-cinema4K"] if profile.startswith("4K_") else ["-cinema2K","24"])
        process=codec.run(["-i",inp.name,"-o","cinema.j2k",*cinema,
                           "-p","CPRL","-mct","0","-I"],cwd=stage,timeout=timeout)
        encoded=stage/"cinema.j2k"
        _protected_path(encoded)
        if not 80<=encoded.stat().st_size<=MAX_FRAME_BYTES:
            raise RuntimeError(f"Real JPEG2000 codestream outside cinema byte bounds: {encoded.stat().st_size} bytes (limit {MAX_FRAME_BYTES})")
        header=inspect_cinema_packets(_read_bounded_protected_codestream(encoded),profile)
        if (_hash_stream(Path(source_path))!=(source_sha256,width*height*6)
                or check_cancel()):
            raise PermissionError("Approved source changed or encoding cancelled")
        _publish_protected(encoded,output,header["raw_codestream_sha256"],
                           encoded.stat().st_size,check_cancel)
    return {
        "format":"nvp.wo4.spool_frame.v1",
        "status":"ENCODED_J2K_STAGE_VERIFIED",
        "source_sha256":source_sha256,
        "original_take_sha256":origin,
        "codestream_sha256":header["raw_codestream_sha256"],
        "codestream_bytes":output.stat().st_size,
        "cinema_rate_constraints":header,
        "native_codec_sha256":codec.sha256,
        "worker":process,
        "input":input_receipt,
        "full_decode_verified":False,
        "production_dcp_accepted":False,
        "source_modified":False,
    }


def _read_bounded_protected_codestream(path):
    identity=_protected_path(path)
    with path.open("rb") as stream:
        start=os.fstat(stream.fileno())
        if ((start.st_dev,start.st_ino)!=identity or
                not 80<=start.st_size<=MAX_FRAME_BYTES):
            raise PermissionError("Verified frame file missing or unsafe")
        raw=stream.read(MAX_FRAME_BYTES+1)
        stop=os.fstat(stream.fileno())
        if (len(raw)!=start.st_size or
                (stop.st_dev,stop.st_ino,stop.st_size,stop.st_mtime_ns)!=
                (start.st_dev,start.st_ino,start.st_size,start.st_mtime_ns)):
            raise PermissionError("Protected codestream changed during bounded read")
    if _protected_path(path)!=identity:
        raise PermissionError("Protected codestream replaced during bounded read")
    return raw


def verify_frame_file(path,expected_sha,profile,*,audit=None):
    p=Path(path)
    raw=_read_bounded_protected_codestream(p)
    if audit is not None and audit.profile!=profile:
        raise ValueError("Reel audit profile mismatch")
    if sha256(raw).hexdigest()!=expected_sha:
        raise PermissionError("Completed JPEG2000 frame digest changed")
    if audit is None:
        inspect_cinema_packets(raw,profile)
    if _read_bounded_protected_codestream(p)!=raw:
        raise PermissionError("Completed JPEG2000 frame bytes changed on reopen")
    if audit is not None:
        audit.add(raw)
    return len(raw)


def wrap_disk_j2k_picture(wrap,info,*,frames_dir,stage_dir,
                          frame_count,profile,asset_uuid,check_cancel,
                          source_take_sha,ordered_codestream_sha256,timeout=3600):
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
    origin=_sha(source_take_sha)
    common_codec_authority(wrap,info)
    if (type(ordered_codestream_sha256) not in (tuple,list) or
            len(ordered_codestream_sha256)!=frame_count or not callable(check_cancel)):
        raise PermissionError("Exact approved ordered frame SHA manifest required")
    shas=tuple(_sha(value) for value in ordered_codestream_sha256)
    expected=[f"{i:06d}.j2c" for i in range(frame_count)]
    if sorted(p.name for p in frames.iterdir())!=expected:
        raise PermissionError("Uncommitted/orphan codestream files require review")
    sizes=[]
    rate_audit=ReelPacketAudit(profile)
    for name,digest in zip(expected,shas):
        if check_cancel():
            raise InterruptedError("Creator cancelled picture MXF")
        sizes.append(verify_frame_file(frames/name,digest,profile,audit=rate_audit))
    bound=sum(sizes)+frame_count*8192+16*1024*1024
    if sum(sizes)+bound>MAX_STAGE_BYTES-4*1024*1024:
        raise ValueError("Approved reel exceeds current protected stage budget; split reel")
    require_stage_space(stage,bound)
    out=stage/"picture.mxf"
    if out.exists() or _linked_entry(out):
        raise FileExistsError("Uncommitted picture MXF exists; review before resume")
    with wrap.stage(origin) as work:
        require_stage_space(work,sum(sizes)+bound)
        spool=work/"source_j2c"
        spool.mkdir()
        _protected_path(spool,directory=True)
        for name,digest,size in zip(expected,shas,sizes):
            _copy_protected(frames/name,spool/name,digest,size,check_cancel)
        process=wrap.run(["-L","-a",uid.replace("-",""),"-p","24","-d",
                           str(frame_count),"source_j2c","picture.mxf"],
                           cwd=work,timeout=timeout)
        native=work/"picture.mxf"
        _protected_path(native)
        if not 128<=native.stat().st_size<=MAX_STAGE_BYTES//2:
            raise RuntimeError("Native picture MXF missing or exceeds budget")
        props,checked=_read_info(info,native.name,work)
        _verify_info(props,uid,frame_count)
        for name,digest,size in zip(expected,shas,sizes):
            if _hash_stream(frames/name)!=(digest,size):
                raise PermissionError("Approved spool changed during native wrapping")
        file_sha,file_size=_hash_stream(native)
        _publish_protected(native,out,file_sha,file_size,check_cancel)
    return {
        "format":"nvp.wo4.file_picture_mxf.v1",
        "status":"NATIVE_PICTURE_MXF_STAGE_VERIFIED",
        "file_sha256":file_sha,
        "file_bytes":file_size,
        "original_take_sha256":origin,
        "ordered_codestream_sha256":list(shas),
        "asset_uuid":uid,"profile":profile,
        "edit_rate":[24,1],"frame_count":frame_count,
        "wrapper_sha256":wrap.sha256,
        "info_sha256":info.sha256,
        "wrapper_process":process,
        "info_process":checked,
        "whole_mxf_loaded_into_ram":False,
        "cinema_rate_constraints":rate_audit.finish(frame_count),
        "independent_dci_validator_passed":False,
        "production_dcp_accepted":False,
    }
