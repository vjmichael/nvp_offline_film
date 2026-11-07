"""WO4-03 deterministic master-candidate QC, not a calibrated display or LUFS meter.

Evaluates real derived XYZ12 bytes and the signed 24-bit PCM master. No
substitution of source/presentation SHA, and no inferred auditorium quality.
"""
from __future__ import annotations
from hashlib import sha256
import math
import wave
from io import BytesIO
from backend.nvp_wo4_xyz12_master import FORMAT as PICTURE_FORMAT
from backend.nvp_wo4_pcm_master import FORMAT as SOUND_FORMAT
from backend.nvp_wo4_loudness import measure_pcm24_loudness

FORMAT="nvp.wo4.master_candidate_qc.v1"


def evaluate_master_candidates(picture,sound):
    if (type(picture) is not dict or picture.get("format")!=PICTURE_FORMAT or
            type(sound) is not dict or sound.get("format")!=SOUND_FORMAT or
            picture.get("source_modified") is not False or
            sound.get("source_modified") is not False or
            picture.get("original_take_sha256")!=sound.get("original_take_sha256")):
        raise PermissionError("Matching immutable-source master candidates required")
    raw=picture.get("xyz12")
    if (type(raw) is not bytes or
            len(raw)!=picture.get("width",0)*picture.get("height",0)*6 or
            sha256(raw).hexdigest()!=picture.get("xyz12_sha256")):
        raise PermissionError("Picture source raster SHA/size mismatch")
    if sound.get("frame_count") is None:
        raise ValueError("Sound frame duration required")
    peak=0
    mins=[4095,4095,4095]
    maxes=[0,0,0]
    sums=[0,0,0]
    pixels=len(raw)//6
    for p in range(0,len(raw),6):
        for i in range(3):
            value=int.from_bytes(raw[p+i*2:p+i*2+2],"big")
            if value>4095:
                raise ValueError("Encoded XYZ12 component exceeds legal range")
            mins[i]=min(mins[i],value)
            maxes[i]=max(maxes[i],value)
            sums[i]+=value
            peak=max(peak,value)
    wav=sound.get("wav_bytes")
    if type(wav) is not bytes or not wav.startswith(b"RIFF"):
        raise ValueError("Actual mastered RIFF PCM required")
    with wave.open(BytesIO(wav),"rb") as reader:
        if (reader.getsampwidth()!=3 or reader.getframerate()!=48000 or
                reader.getnchannels()!=len(sound.get("channel_order",[])) or
                reader.getnframes()!=sound["frame_count"]*2000):
            raise ValueError("Sound layout, PCM depth or film timing differs")
        pcm=reader.readframes(reader.getnframes())
    if sha256(pcm).hexdigest()!=sound.get("master_pcm_sha256"):
        raise PermissionError("Mastered PCM differs from approved SHA receipt")
    sq=0
    audio_peak=0
    for i in range(0,len(pcm),3):
        value=int.from_bytes(pcm[i:i+3],"little",signed=True)
        sq+=value*value
        audio_peak=max(audio_peak,abs(value))
    total_samples=len(pcm)//3
    rms=math.sqrt(sq/total_samples)/8388608 if total_samples else 0
    loudness=measure_pcm24_loudness(sound)
    return {
        "format":FORMAT,"status":"DETERMINISTIC_MASTER_QC_RECORDED",
        "picture_xyz12_sha256":picture["xyz12_sha256"],
        "sound_pcm24_sha256":sound["master_pcm_sha256"],
        "source_take_sha256":picture["original_take_sha256"],
        "picture_profile":picture["profile"],
        "picture_pixel_count":pixels,
        "xyz12_component_min":mins,
        "xyz12_component_max":maxes,
        "xyz12_component_mean":[x/pixels for x in sums],
        "sound_channel_order":sound["channel_order"],
        "sound_sample_rate":48000,
        "sound_frames":sound["frame_count"],
        "sound_peak_absolute_24bit":audio_peak,
        "sound_rms_fraction_full_scale":rms,
        "sound_peak_dbfs":(20*math.log10(audio_peak/8388608) if audio_peak else None),
        "sound_loudness_lufs_measured":loudness["measured"],
        "sound_integrated_lufs":loudness["lufs"],
        "true_peak_measured":False,
        "loudness_meter_calibrated":False,
        "calibrated_projector_verified":False,
        "independent_color_accuracy_verified":False,
        "production_master_accepted":False,
        "ffmpeg_used":False,
    }
