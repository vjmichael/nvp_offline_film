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

from backend.nvp_supervised_codec_process import run_supervised_codec
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
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise PermissionError("Approved original WAV is missing or symlinked")
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
    if not stage.is_absolute() or not stage.is_dir() or stage.is_symlink():
        raise PermissionError("Private sound stage required")
    require_stage_space(stage,source.stat().st_size*2+1024*1024)
    if any((stage/name).exists() or (stage/name).is_symlink()
           for name in ("sound.wav","sound.mxf")):
        raise FileExistsError("Interrupted sound stage requires explicit recovery")
    # Deliberate independent copy, NOT a source-hardlink. A buggy CineCert
    # executable cannot change the creator-approved original WAV inode.
    with source.open("rb") as inp, (stage/"sound.wav").open("xb") as out:
        while chunk:=inp.read(BUFFER):
            if check_cancel():
                raise InterruptedError("Creator cancelled sound input copy")
            out.write(chunk)
        out.flush();os.fsync(out.fileno())
    if (digest_file(stage/"sound.wav")!=candidate["wav_file_sha256"] or
            digest_file(source)!=candidate["wav_file_sha256"]):
        raise PermissionError("Approved WAV changed before native sound wrap")
    wrapper_result=run_supervised_codec(
        wrap,["-L","-a",sound_uuid.replace("-",""),
              "-p","24","-d",str(frames),"sound.wav","sound.mxf"],
        workdir=stage,check_cancel=check_cancel,timeout=7200)
    file=stage/"sound.mxf"
    if file.is_symlink() or not file.is_file() or file.stat().st_size<128:
        raise RuntimeError("Native CineCert sound MXF not created")
    inspector=run_supervised_codec(
        info,["-i","-d","sound.mxf"],
        workdir=stage,check_cancel=check_cancel,
        timeout=300,read_stdout=True)
    output=inspector.pop("stdout").decode("utf-8","replace")
    props={k.strip().lower().replace(" ","_"):v.strip()
           for k,v in INFO_RE.findall(output)}
    if not props.get("label_set_type","").startswith("SMPTE"):
        raise RuntimeError("Non-SMPTE native sound track")
    _verify_info(props,sound_uuid,frames)
    # Verify both the private worker input and original approved source.
    if (digest_file(source)!=candidate["wav_file_sha256"] or
            digest_file(stage/"sound.wav")!=candidate["wav_file_sha256"] or
            _pcm_digest(source,frames,len(candidate["channel_order"]))!=
                candidate["master_pcm_sha256"]):
        raise PermissionError("CineCert modified approved sound source or input")
    if check_cancel():
        raise InterruptedError("Creator cancelled before sound file checkpoint")
    with file.open("rb+") as stream:
        os.fsync(stream.fileno())
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
