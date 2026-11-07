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

from backend.nvp_wo4_pcm_stream import FORMAT as PCM_STREAM_FORMAT, _hash_stream
from backend.nvp_wo3_atomic_publish import _fsync_directory
from backend.nvp_wo3_mxf_native import _read_info, _verify_info
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary

FORMAT="nvp.wo4.streamed_native_pcm_mxf_candidate.v1"
UUID4=re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def _pcm_digest(file,frame_count,channels):
    digest=sha256()
    with wave.open(str(file),"rb") as reader:
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
    return digest.hexdigest()


def wrap_streamed_pcm_mxf(wrap:ApprovedCodecBinary,info:ApprovedCodecBinary,
                          candidate,*,output_root,asset_uuid=None):
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
    frames=candidate.get("frame_count")
    channels=candidate.get("channel_order")
    if (type(frames) is not int or not 3<=frames<=144000 or
            channels not in (["L","R"],
                ["L","R","C","LFE","Ls","Rs"],
                ["L","R","C","LFE","Ls","Rs","Lrs","Rrs"])):
        raise PermissionError("Native original sound duration and channels required")
    path=Path(candidate.get("destination",""))
    root=Path(output_root)
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or not root.is_absolute() or root.is_symlink()
            or not root.is_dir()):
        raise PermissionError("Trusted local mastered audio and output root required")
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
    stage=Path(tempfile.mkdtemp(prefix=".nvp-wo4-mxf-",dir=root))
    target=root/("SoundMXF_"+asset_uuid+".mxf")
    try:
        # Hardlinking a frozen WAV into a native worker shares an inode:
        # codec write bugs could mutate the approved file. Stream-copy into
        # a private stage instead, with no complete soundtrack in RAM.
        private_source=stage/"master.wav"
        with path.open("rb") as source, private_source.open("xb") as private:
            shutil.copyfileobj(source,private,1024*1024)
            private.flush()
            os.fsync(private.fileno())
        private_sha,private_size=_hash_stream(private_source)
        if private_sha!=source_sha or private_size!=source_size:
            raise PermissionError("Private codec input differs from approved WAV")
        result=wrap.run(["-L","-a",asset_uuid.replace("-",""),
                         "-p","24","-d",str(frames),
                         private_source.name,"sound.mxf"],cwd=stage,timeout=3600)
        file=stage/"sound.mxf"
        if file.is_symlink() or not file.is_file() or file.stat().st_size<128:
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
        os.link(file,target)
        _fsync_directory(root)
        mxf_sha,mxf_size=_hash_stream(target)
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
    finally:
        shutil.rmtree(stage,ignore_errors=False)
