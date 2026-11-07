"""WO3-03: native SMPTE ASDCP MXF wrapping, no FFmpeg or fabricated essence.

Trusted host calls this with SHA-pinned, source-approved JPEG2000 codestreams
or 24-bit PCM WAV. Uses reviewed CineCert asdcplib binary, not generic shell.
A separate SHA-pinned asdcp-info binary verifies declared MXF edit rate,
asset UUID, count and SMPTE labels before allowing package construction.
Further independent decode and DCI compliance are separate gates.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import struct
import tempfile
import uuid
import wave

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary
from backend.nvp_wo3_j2k_audit import inspect_j2k_header

FORMAT="nvp.wo3.native_asdcp_track.v1"
MAX_REEL_FRAMES=144000
INFO_RE=re.compile(r"(?m)^\s*([A-Za-z][A-Za-z ]+):\s*([^\r\n]+)\s*$")


def _uuid_v4(value):
    if type(value) is not str:
        raise ValueError("Source-bound MXF UUID required")
    ident=uuid.UUID(value)
    if ident.version!=4 or str(ident)!=value.lower():
        raise ValueError("Native cinema UUID must be canonical UUIDv4")
    return value


def _frame_receipts(frames,profile):
    if type(frames) is not list or not 1<=len(frames)<=MAX_REEL_FRAMES:
        raise ValueError("Source picture sequence bounded to one reel")
    seen=[]
    for i,frame in enumerate(frames):
        if type(frame) is not dict or frame.get("format")!=(
            "nvp.wo3.native_openjpeg_frame.v1") or not all(k in frame for k in (
            "codestream","codestream_sha256",
            "independent_header_constraints_verified",
            "original_approved_presentation_sha256")):
            raise PermissionError("Only exact approved native J2K outputs allowed")
        raw=frame["codestream"]
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=frame[
            "codestream_sha256"] or frame[
            "independent_header_constraints_verified"] is not True:
            raise PermissionError("Native source JPEG2000 SHA or header invalid")
        if inspect_j2k_header(raw,profile)["raw_codestream_sha256"]!=frame[
            "codestream_sha256"]:
            raise PermissionError("Cinema codestream profile differs")
        seen.append(frame["original_approved_presentation_sha256"])
    if len(set(seen))!=1 or len(seen[0])!=64:
        raise PermissionError("All picture frames must bind one approved film")
    return seen[0]


def _read_info(info:ApprovedCodecBinary,filename,workdir):
    if info.product!="ASDCP-asdcp_info":
        raise PermissionError("Pinned independent MXF info binary required")
    # asdcp-info takes a single MXF file argument; never arbitrary options.
    result=info.run([filename],cwd=workdir,include_stdout=True)
    text=result.pop("stdout")
    if len(text)>64*1024:
        raise ValueError("Unbounded native MXF metadata")
    props={k.strip().lower().replace(" ","_"):v.strip()
           for k,v in INFO_RE.findall(text.decode("utf-8","replace"))}
    if props.get("label_set_type")!="SMPTE":
        raise RuntimeError("Native wrapper produced Interop, not SMPTE MXF")
    return props,result


def _verify_info(props,asset_uuid,frames):
    found=props.get("assetuuid") or props.get("asset_uuid")
    if found is None or found.lower()!=asset_uuid:
        raise RuntimeError("Native MXF asset UUID not bound to approved receipt")
    rate=props.get("editrate") or props.get("edit_rate")
    duration=props.get("containerduration") or props.get("container_duration")
    if rate!="24/1" or duration!=str(frames):
        raise RuntimeError("MXF picture/sound edit rate and duration mismatch")


def wrap_cinema_picture(wrap:ApprovedCodecBinary,info:ApprovedCodecBinary,
                        frames,*,profile,asset_uuid):
    if wrap.product!="ASDCP-asdcp_wrap":
        raise PermissionError("Pinned asdcplib SMPTE wrapper required")
    uid=_uuid_v4(asset_uuid)
    origin=_frame_receipts(frames,profile)
    with tempfile.TemporaryDirectory(prefix="nvp-wo3-mxf-pic-") as tmp:
        root=Path(tmp);in_dir=root/"source_j2c";in_dir.mkdir()
        for i,frame in enumerate(frames):
            (in_dir/("%06d.j2c"%i)).write_bytes(frame["codestream"])
        result=wrap.run(["-L","-a",uid.replace("-",""),
                         "-p","24","-d",str(len(frames)),
                         in_dir.name,"picture.mxf"],cwd=root)
        target=root/"picture.mxf"
        if target.is_symlink() or not target.is_file():
            raise RuntimeError("Native SMPTE picture MXF not produced")
        props,info_receipt=_read_info(info,target.name,root)
        _verify_info(props,uid,len(frames))
        raw=target.read_bytes()
        return {"format":FORMAT,"kind":"picture","asset_uuid":uid,
                "bytes":raw,"sha256":hashlib.sha256(raw).hexdigest(),
                "frame_count":len(frames),"edit_rate":[24,1],
                "original_approved_presentation_sha256":origin,
                "wrapper_sha256":wrap.sha256,"info_sha256":info.sha256,
                "native_wrap_receipt":result,
                "native_info_receipt":info_receipt,
                "dci_compliance_verified":False,
                "independent_essence_decode_verified":False,
                "ffmpeg_used":False,"source_modified":False}


def wrap_cinema_pcm(wrap:ApprovedCodecBinary,info:ApprovedCodecBinary,
                    wav_bytes,*,asset_uuid,frame_count,origin_sha256):
    if wrap.product!="ASDCP-asdcp_wrap" or (
        type(wav_bytes) is not bytes or not wav_bytes.startswith(b"RIFF") or
        not 1<=frame_count<=MAX_REEL_FRAMES):
        raise PermissionError("Real 24-bit source WAV and pinned wrapper required")
    uid=_uuid_v4(asset_uuid)
    with tempfile.TemporaryDirectory(prefix="nvp-wo3-mxf-snd-") as tmp:
        root=Path(tmp);wav=root/"source.wav";wav.write_bytes(wav_bytes)
        with wave.open(str(wav),"rb") as handle:
            if (handle.getframerate()!=48000 or
                handle.getsampwidth()!=3 or
                handle.getnchannels() not in (2,6,8) or
                handle.getnframes()!=frame_count*2000 or
                handle.getcomptype()!="NONE"):
                raise ValueError("Real cinema audio must be exact PCM24 48k")
        result=wrap.run(["-L","-a",uid.replace("-",""),
                         "-p","24","-d",str(frame_count),
                         wav.name,"sound.mxf"],cwd=root)
        target=root/"sound.mxf"
        if target.is_symlink() or not target.is_file():
            raise RuntimeError("Native SMPTE sound MXF not produced")
        props,info_receipt=_read_info(info,target.name,root)
        _verify_info(props,uid,frame_count)
        raw=target.read_bytes()
        return {"format":FORMAT,"kind":"sound","asset_uuid":uid,
                "bytes":raw,"sha256":hashlib.sha256(raw).hexdigest(),
                "frame_count":frame_count,"edit_rate":[24,1],
                "original_approved_presentation_sha256":origin_sha256,
                "wrapper_sha256":wrap.sha256,"info_sha256":info.sha256,
                "native_wrap_receipt":result,
                "native_info_receipt":info_receipt,
                "dci_compliance_verified":False,
                "independent_essence_decode_verified":False,
                "ffmpeg_used":False,"source_modified":False}
