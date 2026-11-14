"""AUDIO-01H.1: inspect real 48kHz stereo PCM using FFmpeg EBU R128.

Technical evidence only. This module never normalizes, overwrites, publishes,
approves, or labels a preview a master. Pinned FFmpeg authorization belongs
to the trusted native host rather than this worker-side analyzer.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

RATE = 48000
MAX_SAMPLES = 480 * 2000
_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\"input_tp\"[^{}]*\}", re.S)


def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as src:
        for part in iter(lambda: src.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def analyze_wav(path, *, ffmpeg="ffmpeg", expected_samples=None, timeout=120):
    """Return input LUFS, loudness range, and oversampled true peak in dBTP.

    loudnorm's analysis pass is an EBU R128/BS.1770 measurement, not a
    mastering instruction. Reject non-finite/silent or malformed evidence.
    """
    src = Path(path)
    if src.is_symlink() or not src.is_file():
        raise RuntimeError("Measurement requires existing, non-symlinked WAV")
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("Invalid measurement timeout")
    with wave.open(str(src), "rb") as wav:
        samples = wav.getnframes()
        if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth(),
            wav.getcomptype()) != (2, RATE, 2, "NONE"):
            raise ValueError("Only stereo 48 kHz PCM16 WAV is supported")
    if samples < 1 or samples > MAX_SAMPLES:
        raise ValueError("WAV exceeds bounded timeline")
    if expected_samples is not None and (type(expected_samples) is not int
                                         or samples != expected_samples):
        raise ValueError("Sound duration differs from locked picture clock")
    original = _sha(src)
    command = [str(ffmpeg), "-nostdin", "-hide_banner", "-v", "info",
               "-i", str(src), "-map", "0:a:0", "-af",
               "loudnorm=I=-23:TP=-2:LRA=7:print_format=json",
               "-f", "null", "-"]
    done = subprocess.run(command, capture_output=True,
                          stdin=subprocess.DEVNULL, timeout=timeout,
                          check=False)
    if done.returncode:
        raise RuntimeError("FFmpeg loudness analysis failed: " +
                           done.stderr.decode("utf8", "replace")[-700:])
    evidence = done.stderr.decode("utf8", "replace")
    matches = _JSON.findall(evidence)
    if len(matches) != 1:
        raise RuntimeError("Missing or ambiguous FFmpeg loudness measurement")
    data = json.loads(matches[0])
    values = {}
    for name in ("input_i", "input_tp", "input_lra", "input_thresh"):
        try:
            value = float(data[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Invalid loudness evidence: " + name) from exc
        if not math.isfinite(value):
            raise RuntimeError("Silent or unmeasurable loudness: " + name)
        values[name] = value
    if values["input_lra"] < 0 or values["input_tp"] > 12:
        raise RuntimeError("Unreasonable native loudness evidence")
    if _sha(src) != original:
        raise RuntimeError("Measurement source mutated during inspection")
    return {
        "format": "nvp.audio01h.loudness_evidence.v1",
        "wav_sha256": original, "samples_per_channel": samples,
        "sample_rate": RATE, "channels": 2,
        "integrated_lufs": values["input_i"],
        "loudness_range_lu": values["input_lra"],
        "true_peak_dbtp": values["input_tp"],
        "relative_threshold_lufs": values["input_thresh"],
        "measure_method": "ffmpeg_loudnorm_analysis_ebu_r128",
        "normalized": False, "final_mix": False, "director_approved": False
    }
