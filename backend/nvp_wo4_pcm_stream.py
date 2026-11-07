"""WO4 long-form PCM24 native stream mastering, no whole-track RAM copy.

A trusted desktop host supplies an OS-approved, SHA-bound local raw PCM24 path
and creator approval callback. This module never grants its own filesystem
access. It reads bounded sample blocks, writes an independently tracked WAV,
fsyncs it, and publishes it via atomic hard-link creation (no replacement).

RIFF/WAVE size bounds remain explicit; multichannel feature masters exceeding
4 GiB require RF64 or reel partitioning, not a silent overflow. No FFmpeg.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import os
from pathlib import Path
import re
import tempfile
import uuid
import wave

from backend.nvp_wo4_pcm_master import (
    CHANNEL_LAYOUTS, MAX_FRAMES, MAX_24, MIN_24, _round_away)
from backend.nvp_wo3_atomic_publish import _fsync_directory

FORMAT = "nvp.wo4.streamed_pcm24_candidate.v1"
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
FRAMES_PER_BLOCK = 4096
MAX_RIFF_PCM_BYTES = (1 << 32) - 128


def _hash_stream(file):
    hasher = hashlib.sha256()
    size = 0
    with file.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def stream_master_pcm24_candidate(source_path, *, source_sha256,
                                  original_take_sha256, cinema_frames,
                                  channel_layout, output_root, approve,
                                  gain_numerator=1, gain_denominator=1):
    if not callable(approve):
        raise PermissionError("Native creator authorization callback required")
    if (type(source_sha256) is not str or not HEX_SHA.fullmatch(source_sha256)
            or type(original_take_sha256) is not str or
            not HEX_SHA.fullmatch(original_take_sha256)):
        raise PermissionError("Trusted source PCM and frozen Take digests required")
    if channel_layout not in CHANNEL_LAYOUTS:
        raise ValueError("Declared cinema speaker order required")
    if type(cinema_frames) is not int or not 3 <= cinema_frames <= MAX_FRAMES:
        raise ValueError("Bounded cinema reel duration required")
    if (type(gain_numerator) is not int or
            type(gain_denominator) is not int or
            not 0 <= gain_numerator <= 16 or
            not 1 <= gain_denominator <= 16):
        raise ValueError("Bounded approved rational gain required")
    gain = Fraction(gain_numerator, gain_denominator)
    if gain > 4:
        raise ValueError("Gain exceeds native mastering policy")

    source = Path(source_path)
    root = Path(output_root)
    if (not source.is_absolute() or not source.is_file() or
            source.is_symlink() or not root.is_absolute() or
            not root.is_dir() or root.is_symlink()):
        raise PermissionError("Trusted OS-selected source and output directories required")
    source = source.resolve(strict=True)
    root = root.resolve(strict=True)
    channels = len(CHANNEL_LAYOUTS[channel_layout])
    sample_frames = cinema_frames * 2000
    expected = sample_frames * channels * 3
    if expected > MAX_RIFF_PCM_BYTES:
        raise ValueError("Classic RIFF cannot hold this cinema track; use reel split/RF64")
    checked_hash, checked_size = _hash_stream(source)
    if checked_size != expected or checked_hash != source_sha256:
        raise PermissionError("Approved original PCM duration or SHA mismatch")
    scope = {
        "format": FORMAT,
        "operation": "nvp.wo4.master_original_pcm24_file.v1",
        "source_sha256": source_sha256,
        "original_take_sha256": original_take_sha256,
        "sample_rate": 48000, "cinema_frames": cinema_frames,
        "channel_order": list(CHANNEL_LAYOUTS[channel_layout]),
        "output_root": str(root),
        "gain": [gain.numerator, gain.denominator],
        "source_modified": False,
    }
    if approve(dict(scope)) is not True:
        return {"format": FORMAT, "status": "DENIED", "source_modified": False}

    fd, stage_name = tempfile.mkstemp(prefix=".nvp-wo4-pcm-", suffix=".wav",
                                      dir=root)
    stage = Path(stage_name)
    destination = root / ("PCM24_" + str(uuid.uuid4()) + ".wav")
    raw_hasher = hashlib.sha256()
    derived_hasher = hashlib.sha256()
    peak_in = 0
    peak_out = 0
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as original:
            with wave.open(output, "wb") as wav:
                wav.setnchannels(channels)
                wav.setsampwidth(3)
                wav.setframerate(48000)
                wav.setnframes(sample_frames)
                remaining = expected
                while remaining:
                    count = min(remaining, FRAMES_PER_BLOCK * channels * 3)
                    packet = original.read(count)
                    if len(packet) != count:
                        raise RuntimeError("Original PCM changed during mastering")
                    remaining -= len(packet)
                    raw_hasher.update(packet)
                    transformed = bytearray(len(packet))
                    for index in range(0, len(packet), 3):
                        value = int.from_bytes(packet[index:index+3],
                                               "little", signed=True)
                        peak_in = max(peak_in, abs(value))
                        scaled = _round_away(value * gain.numerator,
                                             gain.denominator)
                        if not MIN_24 <= scaled <= MAX_24:
                            raise ValueError("Mastering gain clips the original PCM")
                        peak_out = max(peak_out, abs(scaled))
                        transformed[index:index+3] = scaled.to_bytes(
                            3, "little", signed=True)
                    derived_hasher.update(transformed)
                    wav.writeframesraw(transformed)
                if original.read(1):
                    raise RuntimeError("Original PCM grew during mastering")
            output.flush()
            os.fsync(output.fileno())
        if raw_hasher.hexdigest() != source_sha256:
            raise PermissionError("Original PCM changed after creator approval")
        # Stage bytes are complete before the kernel atomically reserves the
        # final name. No fallback to os.replace or check-then-rename.
        os.link(stage, destination)
        _fsync_directory(root)
        published_hash, published_size = _hash_stream(destination)
        return {
            "format": FORMAT,
            "status": "STREAMED_PCM24_CANDIDATE_PUBLISHED",
            "destination": str(destination),
            "wav_file_sha256": published_hash,
            "wav_file_bytes": published_size,
            "source_pcm_sha256": source_sha256,
            "master_pcm_sha256": derived_hasher.hexdigest(),
            "original_take_sha256": original_take_sha256,
            "frame_count": cinema_frames,
            "channel_order": list(CHANNEL_LAYOUTS[channel_layout]),
            "sample_rate": 48000, "sample_width_bytes": 3,
            "gain": [gain.numerator, gain.denominator],
            "peak_input_absolute": peak_in,
            "peak_output_absolute": peak_out,
            "source_modified": False,
            "whole_reel_loaded_into_ram": False,
            "classic_riff_under_4gib": True,
            "production_audio_accepted": False,
            "ffmpeg_used": False,
        }
    finally:
        stage.unlink(missing_ok=True)
