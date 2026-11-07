"""WO4-01: source-preserving, deterministic PCM24 cinema master candidate.

Exact source-sample duration at 48kHz and 24 presentation frames/s. Input is
trusted native PCM sample bytes, not a browser path. Original PCM is untouched.
Mastering gain is a creator-approved rational factor; integer arithmetic and
round-to-nearest-away-from-zero are deterministic across Windows/Linux.
This is not yet a calibrated auditorium loudness or DCI mastering approval.
"""
from __future__ import annotations
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import wave

FORMAT = "nvp.wo4.pcm24_candidate.v1"
CHANNEL_LAYOUTS = {
    "stereo": ("L","R"),
    "5.1": ("L","R","C","LFE","Ls","Rs"),
    "7.1": ("L","R","C","LFE","Ls","Rs","Lrs","Rrs"),
}
MAX_FRAMES = 144000
MAX_PCM_BYTES = 8*48000*3*60*10
MIN_24 = -(1<<23)
MAX_24 = (1<<23)-1


def _round_away(numerator, denominator):
    magnitude = (2*abs(numerator)+denominator)//(2*denominator)
    return magnitude if numerator>=0 else -magnitude


def master_pcm24_candidate(source_pcm: bytes, *, source_sha256: str,
                           original_take_sha256: str,
                           cinema_frames: int, channel_layout: str,
                           gain_numerator: int=1, gain_denominator: int=1,
                           creator_approved: bool=False):
    if creator_approved is not True:
        raise PermissionError("Explicit trusted film sound mastering approval required")
    if (type(source_pcm) is not bytes or not 0<len(source_pcm)<=MAX_PCM_BYTES
            or type(source_sha256) is not str or len(source_sha256)!=64
            or source_sha256!=sha256(source_pcm).hexdigest()
            or type(original_take_sha256) is not str
            or len(original_take_sha256)!=64
            or any(c not in "0123456789abcdef" for c in original_take_sha256)):
        raise PermissionError("Exact original PCM and frozen Take SHA custody required")
    if channel_layout not in CHANNEL_LAYOUTS:
        raise ValueError("Explicit cinema channel labels required")
    if type(cinema_frames) is not int or not 3<=cinema_frames<=MAX_FRAMES:
        raise ValueError("Bounded cinema Film Time duration required")
    channels = len(CHANNEL_LAYOUTS[channel_layout])
    samples_per_channel = cinema_frames*2000
    if len(source_pcm) != samples_per_channel*channels*3:
        raise ValueError("Source PCM length differs from exact 24 fps / 48 kHz timing")
    if (type(gain_numerator) is not int or type(gain_denominator) is not int or
            not 0<=gain_numerator<=16 or not 1<=gain_denominator<=16):
        raise ValueError("Bounded rational gain required")
    gain = Fraction(gain_numerator, gain_denominator)
    if gain>4:
        raise ValueError("Unsafe mastering gain magnitude")
    output = bytearray(len(source_pcm))
    clipped = 0
    peak_in = 0
    peak_out = 0
    for position in range(0,len(source_pcm),3):
        value = int.from_bytes(source_pcm[position:position+3],"little",signed=True)
        peak_in=max(peak_in,abs(value))
        scaled = _round_away(value*gain.numerator,gain.denominator)
        if scaled>MAX_24:
            scaled=MAX_24;clipped+=1
        if scaled<MIN_24:
            scaled=MIN_24;clipped+=1
        peak_out=max(peak_out,abs(scaled))
        output[position:position+3]=scaled.to_bytes(3,"little",signed=True)
    if clipped:
        raise ValueError("Mastering would clip PCM24 samples: revise gain before approval")
    buffer=BytesIO()
    with wave.open(buffer,"wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(3)
        writer.setframerate(48000)
        writer.writeframes(output)
    final=bytes(output)
    return {
        "format":FORMAT,
        "status":"SOURCE_BOUND_PCM24_MASTER_CANDIDATE",
        "wav_bytes":buffer.getvalue(),
        "source_pcm_sha256":source_sha256,
        "master_pcm_sha256":sha256(final).hexdigest(),
        "original_take_sha256":original_take_sha256,
        "frame_count":cinema_frames,
        "sample_rate":48000,
        "sample_width_bytes":3,
        "channel_order":list(CHANNEL_LAYOUTS[channel_layout]),
        "gain": [gain.numerator,gain.denominator],
        "peak_input_absolute":peak_in,
        "peak_output_absolute":peak_out,
        "clipped_samples":0,
        "source_modified":False,
        "cinema_loudness_calibrated":False,
        "production_audio_accepted":False,
        "ffmpeg_used":False,
    }
