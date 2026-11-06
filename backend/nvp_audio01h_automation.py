"""AUDIO-01H: sample-accurate, bounded PCM16 automation (unapproved).

Pure DSP; it does not authorize file access, launch workers, publish media,
measure standards-compliant integrated loudness or approve a final mix.
The native NVP host must supervise all subsequent media operations.
"""
from __future__ import annotations

from array import array
import math
import sys

RATE = 48000
CHANNELS = 2
MAX_SAMPLES = 480 * 2000  # AUDIO-01F ten/twenty second bound: 480 frames at 24fps
MAX_ABS_DB = 24.0


def validate_automation(points, total_samples):
    """Canonical points: [[sample_index, gain_db], ...], endpoints mandatory.

    Gain envelopes interpolate in decibels; zero duration segments are rejected.
    The final sample index is total_samples - 1, never an inclusive extra sample.
    """
    if type(total_samples) is not int or not 1 <= total_samples <= MAX_SAMPLES:
        raise ValueError("Invalid bounded picture-clock sample count")
    if not isinstance(points, (list, tuple)) or not 1 <= len(points) <= 4096:
        raise ValueError("Automation requires 1..4096 control points")
    checked = []
    last = -1
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("Automation point must be [sample_index, gain_db]")
        index, db = point
        if type(index) is not int or index <= last or index >= total_samples:
            raise ValueError("Automation samples must increase within picture duration")
        if type(db) not in (float, int) or not math.isfinite(db) or abs(db) > MAX_ABS_DB:
            raise ValueError("Automation gain must be finite and within +/-24 dB")
        checked.append((index, float(db)))
        last = index
    if checked[0][0] != 0 or checked[-1][0] != total_samples - 1:
        raise ValueError("Automation must explicitly bind both timeline endpoints")
    return tuple(checked)


def apply_pcm16_stereo(pcm, points, *, total_samples):
    """Return a new little-endian PCM16 stereo buffer without modifying input.

    Raises on any clipped output: no automatic limiter or hidden attenuation.
    Caller must use immutable input, authorized worker and staged publication.
    """
    envelope = validate_automation(points, total_samples)
    if not isinstance(pcm, bytes) or len(pcm) != total_samples * CHANNELS * 2:
        raise ValueError("PCM byte count does not equal exact timeline duration")
    values = array("h")
    values.frombytes(pcm)
    if sys.byteorder != "little":
        values.byteswap()
    out = array("h")
    segment = 0
    for frame in range(total_samples):
        while segment + 1 < len(envelope) - 1 and frame > envelope[segment + 1][0]:
            segment += 1
        a, gain_a = envelope[segment]
        if segment + 1 < len(envelope):
            b, gain_b = envelope[segment + 1]
            db = gain_a + (gain_b - gain_a) * ((frame - a) / (b - a))
        else:
            db = gain_a
        factor = 10.0 ** (db / 20.0)
        for channel in range(CHANNELS):
            sample = int(round(values[frame * CHANNELS + channel] * factor))
            if sample < -32768 or sample > 32767:
                raise ValueError("Automation would clip PCM16; explicit remix required")
            out.append(sample)
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


def pcm16_peak_dbfs(pcm):
    """Sample peak only; NOT a true-peak or integrated-LUFS measurement."""
    if not isinstance(pcm, bytes) or len(pcm) % 4:
        raise ValueError("Expected complete interleaved stereo PCM16")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(s) for s in samples), default=0)
    return float("-inf") if not peak else 20.0 * math.log10(peak / 32768.0)
