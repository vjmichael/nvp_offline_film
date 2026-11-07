"""WO4 disk-streamed 48k K-weighted loudness without loading full WAV.

Consumes the SHA-verified, immutable-source WO4 disk master. The 400 ms
window keeps only 19,200 energies in memory and stores one 100 ms block
measurement per interval. Suitable for long audio reels within RIFF bounds.
This remains a diagnostic, not an accredited BS.1770/true-peak meter.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import math
from pathlib import Path
import wave

from backend.nvp_wo4_pcm_stream import FORMAT as PCM_STREAM_FORMAT, _hash_stream
from backend.nvp_wo4_loudness import (
    FORMAT, SHELF_B, SHELF_A, RLB_B, RLB_A, WEIGHTS, _biquad)

WINDOW=19200
STEP=4800
READ_FRAMES=4096


def measure_streamed_pcm24_loudness(master):
    if (type(master) is not dict or
            master.get("format")!=PCM_STREAM_FORMAT or
            master.get("status")!="STREAMED_PCM24_CANDIDATE_PUBLISHED" or
            master.get("source_modified") is not False):
        raise PermissionError("Trusted SHA-bound streamed WO4 master required")
    labels=tuple(master.get("channel_order",()))
    if labels not in WEIGHTS:
        raise PermissionError("Unknown native cinema channel mapping")
    file=Path(master.get("destination",""))
    if not file.is_absolute() or file.is_symlink() or not file.is_file():
        raise PermissionError("Trusted local mastered WAV file required")
    verified_sha,verified_size=_hash_stream(file)
    if (verified_sha!=master.get("wav_file_sha256") or
            verified_size!=master.get("wav_file_bytes")):
        raise PermissionError("Disk WAV differs from creator-approved receipt")
    states_shelf=[[0.,0.,0.,0.] for _ in labels]
    states_rlb=[[0.,0.,0.,0.] for _ in labels]
    window=deque()
    running_energy=0.
    blocks=[]
    sample_peak=0
    raw_digest=sha256()
    sample_count=0
    with wave.open(str(file),"rb") as reader:
        if (reader.getnchannels()!=len(labels) or
                reader.getsampwidth()!=3 or reader.getframerate()!=48000 or
                reader.getnframes()!=master.get("frame_count",0)*2000 or
                reader.getcomptype()!="NONE"):
            raise PermissionError("Disk PCM mastering format or duration differs")
        while True:
            packet=reader.readframes(READ_FRAMES)
            if not packet:
                break
            stride=len(labels)*3
            if len(packet)%stride:
                raise RuntimeError("Disk PCM truncated during native loudness QC")
            raw_digest.update(packet)
            for pos in range(0,len(packet),stride):
                total=0.
                for ch,weight in enumerate(WEIGHTS[labels]):
                    offset=pos+ch*3
                    sample=int.from_bytes(
                        packet[offset:offset+3],"little",signed=True)
                    sample_peak=max(sample_peak,abs(sample))
                    value=sample/8388608.
                    shelved=_biquad(value,states_shelf[ch],SHELF_B,SHELF_A)
                    filtered=_biquad(shelved,states_rlb[ch],RLB_B,RLB_A)
                    total+=weight*filtered*filtered
                if len(window)==WINDOW:
                    running_energy-=window.popleft()
                window.append(total)
                running_energy+=total
                sample_count+=1
                if (sample_count>=WINDOW and
                        (sample_count-WINDOW)%STEP==0):
                    energy=max(0.,running_energy/WINDOW)
                    if energy>0:
                        blocks.append((energy,-0.691+10*math.log10(energy)))
    if (raw_digest.hexdigest()!=master.get("master_pcm_sha256") or
            sample_count!=master["frame_count"]*2000 or
            _hash_stream(file)!=(verified_sha,verified_size)):
        raise PermissionError("Mastered PCM changed during streamed loudness QC")
    absolute=[e for e,l in blocks if l>=-70.]
    if not absolute:
        integrated=None
        relative_gate=None
    else:
        mean=sum(absolute)/len(absolute)
        relative_gate=-0.691+10*math.log10(mean)-10
        accepted=[e for e,l in blocks if l>=-70. and l>=relative_gate]
        integrated=(-0.691+10*math.log10(sum(accepted)/len(accepted))
                    if accepted else None)
    return {
        "format":FORMAT,
        "status":("K_WEIGHTED_GATE_MEASURED" if sample_count>=WINDOW
                  else "INSUFFICIENT_400MS_AUDIO"),
        "measured":integrated is not None,
        "lufs":integrated,
        "relative_gate_lkfs":relative_gate,
        "block_count":len(blocks),
        "channel_order":list(labels),
        "lfe_excluded":True,
        "sample_peak_dbfs":(
            20*math.log10(sample_peak/8388608.) if sample_peak else None),
        "whole_track_loaded_into_ram":False,
        "maximum_window_samples":WINDOW,
        "true_peak_measured":False,
        "standards_meter_calibration_verified":False,
        "production_audio_accepted":False,
        "source_modified":False,
    }
