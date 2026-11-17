"""WO4 reviewed CineCert MXF sound wrapping from a disk-spooled PCM24 WAV.

This adapter never loads the approved WAV or resulting MXF into Python RAM.
It consumes only a native host's SHA-bound streamed WO4 receipt and a pinned
CineCert wrapper/info executable. The codec receives a private stream-copied
WAV, never a hardlink to approved source media. Output is no-clobber. Exact source PCM SHA is
independently rechecked after wrapper execution. No FFmpeg or shell.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import tempfile
from uuid import uuid4
import wave
from copy import deepcopy
from backend.nvp_wo4_pcm_stream import _protected_path
from backend.nvp_wo3_native_codecs import common_codec_authority, _sha, MAX_STAGE_BYTES
from backend.nvp_wo4_resource_budget import require_stage_space
from backend.nvp_wo3_dcp_structure import _linked_entry

from backend.nvp_wo4_pcm_stream import FORMAT as PCM_STREAM_FORMAT, _hash_stream
from backend.nvp_wo3_atomic_publish import _fsync_directory
from backend.nvp_wo3_mxf_native import _read_info, _verify_info
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary

FORMAT="nvp.wo4.streamed_native_pcm_mxf_candidate.v1"
UUID4=re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def _pcm_digest(file,frame_count,channels):
    identity=_protected_path(Path(file))
    digest=sha256()
    with Path(file).open("rb") as source, wave.open(source,"rb") as reader:
        st=os.fstat(source.fileno())
        if (st.st_dev,st.st_ino)!=identity:
            raise PermissionError("Mastered WAV replaced at open")
        if (reader.getframerate()!=48000 or reader.getsampwidth()!=3 or
                reader.getnchannels()!=channels or
                reader.getnframes()!=frame_count*2000 or
                reader.getcomptype()!="NONE"):
            raise PermissionError("Native PCM mastering WAV has invalid timing or format")
        remaining=reader.getnframes()
        while remaining:
            count=min(remaining,8192)
            block=reader.readframes(count)
            if len(block)!=count*channels*3:
                raise RuntimeError("Native mastered PCM WAV truncated")
            digest.update(block)
            remaining-=count
    if _protected_path(Path(file))!=identity:
        raise PermissionError("Mastered WAV replaced during read")
    return digest.hexdigest()


def _copy_protected(src,dst,expected_sha,expected_size,check_cancel):
    src,dst=Path(src),Path(dst)
    _sha(expected_sha)
    if type(expected_size) is not int or not 1<=expected_size<=MAX_STAGE_BYTES:
        raise ValueError("Bounded protected media file size required")
    identity=_protected_path(src)
    _protected_path(dst.parent,directory=True)
    h=sha256()
    size=0
    with src.open("rb") as inp,dst.open("xb") as out:
        st=os.fstat(inp.fileno())
        if (st.st_dev,st.st_ino)!=identity:
            raise PermissionError("Protected source changed at open")
        target_identity=_protected_path(dst)  # Verify actual EFS before writing.
        st=os.fstat(out.fileno())
        if (st.st_dev,st.st_ino)!=target_identity:
            raise PermissionError("Protected destination changed at open")
        while chunk:=inp.read(1024*1024):
            if check_cancel():
                raise InterruptedError("Creator cancelled protected media copy")
            size+=len(chunk)
            if size>expected_size:
                raise PermissionError("Source exceeded approved file size")
            h.update(chunk)
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())
    if (size!=expected_size or h.hexdigest()!=expected_sha or
            _protected_path(src)!=identity or
            _hash_stream(src)!=(expected_sha,expected_size) or
            _hash_stream(dst)!=(expected_sha,expected_size)):
        raise PermissionError("Protected stream copy changed approved media")
    return dst


def _publish_protected(src,target,expected_sha,expected_size,check_cancel):
    target=Path(target)
    root=target.parent
    identity=_protected_path(root,directory=True)
    if target.exists() or _linked_entry(target):
        raise FileExistsError("Existing file requires explicit recovery")
    require_stage_space(root,expected_size)
    temp_root=Path(tempfile.mkdtemp(prefix=".nvp-wo4-copy-",dir=root))
    temp_identity=_protected_path(temp_root,directory=True)
    temporary=temp_root/"media"
    try:
        _copy_protected(src,temporary,expected_sha,expected_size,check_cancel)
        if check_cancel() or _protected_path(root,directory=True)!=identity:
            raise InterruptedError("Protected publication cancelled or directory changed")
        seal=_protected_path(temporary)
        os.link(temporary,target)
        try:
            if (_protected_path(target)!=seal or
                _hash_stream(target)!=(expected_sha,expected_size)):
                raise PermissionError("Protected output changed after publication")
            _fsync_directory(root)
        except BaseException:
            if not _linked_entry(target) and _protected_path(target)==seal:
                target.unlink()
            raise
    finally:
        if _protected_path(temp_root,directory=True)==temp_identity:
            temporary.unlink(missing_ok=True)
            temp_root.rmdir()
    return target


def wrap_streamed_pcm_mxf(wrap:ApprovedCodecBinary,info:ApprovedCodecBinary,
                          candidate,*,output_root,asset_uuid=None,check_cancel=lambda:False,
                          stage_checkpoint=False):
    if (not isinstance(wrap,ApprovedCodecBinary) or
            not isinstance(info,ApprovedCodecBinary) or
            wrap.product!="ASDCP-asdcp_wrap" or
            info.product!="ASDCP-asdcp_info"):
        raise PermissionError("Reviewed native CineCert sound codecs required")
    if (type(candidate) is not dict or
            candidate.get("format")!=PCM_STREAM_FORMAT or
            candidate.get("status")!="STREAMED_PCM24_CANDIDATE_PUBLISHED" or
            candidate.get("source_modified") is not False or
            candidate.get("production_audio_accepted") is not False or
            candidate.get("sample_rate")!=48000 or
            candidate.get("sample_width_bytes")!=3):
        raise PermissionError("Only approved disk-spooled original PCM24 accepted")
    candidate=deepcopy(candidate)
    if not callable(check_cancel) or type(stage_checkpoint) is not bool:
        raise PermissionError("Trusted cancellation hook required")
    origin=_sha(candidate.get("original_take_sha256"))
    frames=candidate.get("frame_count")
    channels=candidate.get("channel_order")
    if (type(frames) is not int or not 3<=frames<=144000 or
            channels not in (["L","R"],
                ["L","R","C","LFE","Ls","Rs"],
                ["L","R","C","LFE","Ls","Rs","Lrs","Rrs"])):
        raise PermissionError("Native original sound duration and channels required")
    path=Path(candidate.get("destination",""))
    root=Path(output_root)
    _protected_path(path)
    _protected_path(root,directory=True)
    path=path.resolve(strict=True)
    root=root.resolve(strict=True)
    source_sha,source_size=_hash_stream(path)
    if (source_sha!=candidate.get("wav_file_sha256") or
            source_size!=candidate.get("wav_file_bytes") or
            _pcm_digest(path,frames,len(channels))!=candidate.get("master_pcm_sha256")):
        raise PermissionError("Original approved WAV source or sample SHA mismatch")
    if asset_uuid is None:
        asset_uuid=str(uuid4())
    if type(asset_uuid) is not str or not UUID4.fullmatch(asset_uuid):
        raise ValueError("Exact canonical native MXF asset UUIDv4 required")
    if source_size>MAX_STAGE_BYTES//2-16*1024*1024:
        raise ValueError("PCM reel exceeds current protected stage budget; split reel")
    common_codec_authority(wrap,info)
    target=root/("sound.mxf" if stage_checkpoint else "SoundMXF_"+asset_uuid+".mxf")
    if target.exists() or _linked_entry(target):
        raise FileExistsError("Existing sound track requires review")
    with wrap.stage(origin) as stage:
        require_stage_space(stage,source_size*2+16*1024*1024)
        private_source=stage/"source.wav"
        _copy_protected(path,private_source,source_sha,source_size,check_cancel)
        if check_cancel():
            raise InterruptedError("Creator cancelled sound wrap")
        result=wrap.run(["-L","-a",asset_uuid.replace("-",""),
                         "-p","24","-d",str(frames),
                         private_source.name,"sound.mxf"],cwd=stage,timeout=3600)
        file=stage/"sound.mxf"
        if _linked_entry(file) or not file.is_file() or not 128<=file.stat().st_size<=MAX_STAGE_BYTES//2:
            raise RuntimeError("Native CineCert MXF sound track not created")
        props,info_receipt=_read_info(info,file.name,stage)
        _verify_info(props,asset_uuid,frames)
        # Input remains the identical approved bytes after native execution.
        after,size_after=_hash_stream(path)
        staged_after,staged_size=_hash_stream(private_source)
        if (after!=source_sha or size_after!=source_size or
                staged_after!=source_sha or staged_size!=source_size or
                _pcm_digest(path,frames,len(channels))!=candidate["master_pcm_sha256"]):
            raise PermissionError("Approved sound changed during native MXF encoding")
        with file.open("rb+") as stream:
            os.fsync(stream.fileno())
        mxf_sha,mxf_size=_hash_stream(file)
        _publish_protected(file,target,mxf_sha,mxf_size,check_cancel)
        return {
            "format":FORMAT,
            "status":"STREAMED_NATIVE_SOUND_MXF_PUBLISHED",
            "asset_uuid":asset_uuid,
            "destination":str(target),
            "mxf_file_sha256":mxf_sha,
            "mxf_file_bytes":mxf_size,
            "source_master_wav_sha256":source_sha,
            "master_pcm_sha256":candidate["master_pcm_sha256"],
            "original_take_sha256":candidate["original_take_sha256"],
            "channel_order":list(channels),
            "frame_count":frames,
            "edit_rate":[24,1],
            "native_wrapper_sha256":wrap.sha256,
            "native_info_sha256":info.sha256,
            "native_wrap_receipt":result,
            "native_info_receipt":info_receipt,
            "whole_mxf_loaded_into_ram":False,
            "source_modified":False,
            "production_dcp_accepted":False,
            "ffmpeg_used":False,
        }
