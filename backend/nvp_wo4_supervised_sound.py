"""WO4 native supervisor sound-MXF stage from approved file-backed PCM24.

Unlike the earlier standalone WO4 sound adapter, this uses the SAME pinned,
process-tree-supervised codec runner as picture and leaves interrupted output
in its private stage for durable journal recovery. The source WAV is copied
through bounded buffers to isolate its inode from an external codec worker.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import wave

from backend.nvp_wo4_mxf_stream import wrap_streamed_pcm_mxf,_publish_protected
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo3_mxf_native import INFO_RE,_verify_info
from backend.nvp_wo3_atomic_publish import _fsync_directory
from backend.nvp_wo4_mxf_stream import _pcm_digest
from backend.nvp_wo4_pcm_stream import FORMAT as STREAM_FORMAT
from backend.nvp_wo4_resource_budget import require_stage_space

FORMAT="nvp.wo4.supervised_pcm_sound_mxf.v1"
BUFFER=1024*1024

def _read_guarded_sound(candidate,frames,source_take_sha):
    if (type(candidate) is not dict or
            candidate.get("format")!=STREAM_FORMAT or
            candidate.get("status")!="STREAMED_PCM24_CANDIDATE_PUBLISHED" or
            candidate.get("frame_count")!=frames or
            candidate.get("original_take_sha256")!=source_take_sha or
            candidate.get("source_modified") is not False or
            candidate.get("production_audio_accepted") is not False or
            candidate.get("sample_rate")!=48000 or
            candidate.get("sample_width_bytes")!=3 or
            candidate.get("channel_order") not in (
                ["L","R"],
                ["L","R","C","LFE","Ls","Rs"],
                ["L","R","C","LFE","Ls","Rs","Lrs","Rrs"])):
        raise PermissionError("Native approved source-bound streamed audio required")
    path=Path(candidate.get("destination",""))
    _protected_path(path)
    path=path.resolve(strict=True)
    digest=digest_file(path)
    if (digest!=candidate.get("wav_file_sha256") or
            path.stat().st_size!=candidate.get("wav_file_bytes") or
            _pcm_digest(path,frames,len(candidate["channel_order"]))!=
                candidate.get("master_pcm_sha256")):
        raise PermissionError("Approved WAV or PCM SHA digest differs")
    return path

def wrap_supervised_sound(wrap,info,*,candidate,source_take_sha,frames,
                          sound_uuid,stage_dir,check_cancel):
    from backend.nvp_wo3_mxf_native import _uuid_v4
    if (not isinstance(wrap,ApprovedCodecBinary) or
            not isinstance(info,ApprovedCodecBinary) or
            wrap.product!="ASDCP-asdcp_wrap" or
            info.product!="ASDCP-asdcp_info" or
            type(frames) is not int or not 3<=frames<=7200 or
            not callable(check_cancel)):
        raise PermissionError("Approved bounded CineCert sound job required")
    _uuid_v4(sound_uuid)
    source=_read_guarded_sound(candidate,frames,source_take_sha)
    stage=Path(stage_dir)
    _protected_path(stage,directory=True)
    file=stage/"sound.mxf"
    if file.exists() or file.is_symlink():
        raise FileExistsError("Interrupted sound stage requires explicit recovery")
    # One common protected codec implementation, no second worker launcher.
    result=wrap_streamed_pcm_mxf(wrap,info,candidate,output_root=stage,
                                 asset_uuid=sound_uuid,check_cancel=check_cancel,
                                 stage_checkpoint=True)
    wrapper_result=result["native_wrap_receipt"]
    inspector=result["native_info_receipt"]
    return {"format":FORMAT,"status":"SOUND_MXF_STAGE_VERIFIED",
            "asset_uuid":sound_uuid,"frame_count":frames,
            "file_sha256":digest_file(file),"file_bytes":file.stat().st_size,
            "master_pcm_sha256":candidate["master_pcm_sha256"],
            "source_master_wav_sha256":candidate["wav_file_sha256"],
            "original_take_sha256":source_take_sha,
            "wrapper_sha256":wrap.sha256,"info_sha256":info.sha256,
            "native_wrap_receipt":wrapper_result,
            "native_info_receipt":inspector,
            "whole_mxf_loaded_into_ram":False,
            "source_modified":False,"production_dcp_accepted":False}
