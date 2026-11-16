"""AUDIO-02B: objective measured LUFS and true-peak quality report.

FFmpeg loudnorm's first pass is measurement ONLY, not a secretly normalized
mix. Approval is always a separate authenticated creator action.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import wave

FORMAT="nvp.audio.loudness_technical_qc.v1"
FIELDS=("input_i","input_tp","input_lra","input_thresh")
SHA_PATTERN=re.compile(r"^[0-9a-f]{64}$")


def measure_mix(wav_path,*,ffmpeg="ffmpeg",target_lufs=-16.0,
                ceiling_dbtp=-1.0):
    path=Path(wav_path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Audio QC source missing or symlinked")
    if not shutil.which(ffmpeg):
        raise RuntimeError("Real FFmpeg required for loudness and true-peak measurement")
    with wave.open(str(path),"rb") as wav:
        frames=wav.getnframes()
        if (wav.getnchannels()!=2 or wav.getsampwidth()!=2 or
            wav.getframerate()!=48000 or frames<48000):
            raise RuntimeError("AUDIO-02B needs at least one second of stereo PCM16/48k")
    with path.open("rb") as src:
        original_sha=hashlib.file_digest(src,"sha256").hexdigest()
    if (type(target_lufs) not in (int,float) or
        type(ceiling_dbtp) not in (int,float) or
        not -36<=target_lufs<=-5 or not -9<=ceiling_dbtp<=0):
        raise ValueError("Invalid bounded loudness review target")
    cmd=[ffmpeg,"-nostdin","-hide_banner","-v","info",
        "-i",str(path),"-map","0:a:0",
        "-af",f"loudnorm=I={target_lufs}:TP={ceiling_dbtp}:LRA=11:print_format=json",
        "-f","null","-"]
    run=run_owned_subprocess(cmd,capture_output=True,timeout=240,check=False)
    if run.returncode:
        raise RuntimeError("Native loudness analysis failed: "+
                           run.stderr.decode("utf8","replace")[-700:])
    output=run.stderr.decode("utf8","replace")
    matches=re.findall(r'\{\s*"input_i".*?\}',output,re.DOTALL)
    if len(matches)!=1:
        raise RuntimeError("Expected one native loudnorm measured payload")
    data=json.loads(matches[0])
    measured={}
    for field in FIELDS:
        measured[field]=float(data[field])
        if not math.isfinite(measured[field]):
            raise RuntimeError("Nonfinite loudness measurement")
    # Measurement does not normalize; out-of-range must be corrected through
    # an explicit newly rendered mix, never relabeled as a passed master.
    within=abs(measured["input_i"]-target_lufs)<=2.0 and (
        measured["input_tp"]<=ceiling_dbtp)
    return {"format":FORMAT,"source_sha256":original_sha,
            "samples_per_channel":frames,"sample_rate":48000,
            "integrated_lufs":measured["input_i"],
            "true_peak_dbtp":measured["input_tp"],
            "loudness_range_lu":measured["input_lra"],
            "relative_gate_lufs":measured["input_thresh"],
            "target_lufs":target_lufs,"true_peak_ceiling_dbtp":ceiling_dbtp,
            "qc_passed":bool(within),"measured_not_normalized":True,
            "director_approved":False,"final_master":False}
