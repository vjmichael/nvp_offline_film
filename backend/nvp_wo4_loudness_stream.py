"""Bounded 48k K-weighted loudness: two verified passes, no block history.

The diagnostic preserves filter/window continuity between PCM packets and
reels. It is not an accredited BS.1770 or oversampled true-peak meter.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import math
import os
from pathlib import Path
import wave

from backend.nvp_wo4_pcm_stream import FORMAT as PCM_STREAM_FORMAT, _hash_stream, _protected_path
from backend.nvp_wo4_loudness import (
    FORMAT, SHELF_B, SHELF_A, RLB_B, RLB_A, WEIGHTS, _biquad)

WINDOW=19200
STEP=4800
READ_FRAMES=4096


def _scan(factory,labels,gate):
    shelf=[[0.,0.,0.,0.] for _ in labels]
    rlb=[[0.,0.,0.,0.] for _ in labels]
    window=deque();running=0.;peak=0;count=0;blocks=0;total=0.;accepted=0
    raw=sha256();stride=len(labels)*3
    for packet in factory():
        if type(packet) is not bytes or not 0<len(packet)<=READ_FRAMES*stride or len(packet)%stride:
            raise RuntimeError("Invalid bounded PCM loudness packet")
        raw.update(packet)
        for pos in range(0,len(packet),stride):
            power=0.
            for ch,weight in enumerate(WEIGHTS[labels]):
                offset=pos+ch*3
                sample=int.from_bytes(packet[offset:offset+3],"little",signed=True)
                peak=max(peak,abs(sample))
                shelved=_biquad(sample/8388608.,shelf[ch],SHELF_B,SHELF_A)
                filtered=_biquad(shelved,rlb[ch],RLB_B,RLB_A)
                power+=weight*filtered*filtered
            if len(window)==WINDOW:
                running-=window.popleft()
            window.append(power);running+=power;count+=1
            if count>=WINDOW and (count-WINDOW)%STEP==0:
                energy=max(0.,running/WINDOW)
                if energy>0:
                    blocks+=1
                    loudness=-0.691+10*math.log10(energy)
                    if loudness>=-70. and loudness>=gate:
                        total+=energy;accepted+=1
    return raw.hexdigest(),count,peak,blocks,total,accepted


def measure_bounded_packets(factory, labels, expected_samples, expected_sha):
    """Replay exactly the same verified PCM stream; never retain block list."""
    labels=tuple(labels)
    if labels not in WEIGHTS or not callable(factory) or type(expected_samples) is not int or expected_samples<=0:
        raise ValueError("Exact PCM diagnostic input required")
    first=_scan(factory,labels,-70.)
    digest,count,peak,blocks,total,n=first
    if digest!=expected_sha or count!=expected_samples:
        raise PermissionError("Original master PCM hash or sample clock changed")
    integrated=None;relative=None
    if n:
        relative=-0.691+10*math.log10(total/n)-10
        second=_scan(factory,labels,relative)
        if second[:4]!=first[:4]:
            raise PermissionError("Mastered PCM changed between loudness passes")
        if second[5]:
            integrated=-0.691+10*math.log10(second[4]/second[5])
    return {"format":FORMAT,"status":("K_WEIGHTED_GATE_MEASURED" if count>=WINDOW
                else "INSUFFICIENT_400MS_AUDIO"),"measured":integrated is not None,
            "lufs":integrated,"relative_gate_lkfs":relative,"block_count":blocks,
            "channel_order":list(labels),"lfe_excluded":True,
            "sample_peak_dbfs":20*math.log10(peak/8388608.) if peak else None,
            "whole_track_loaded_into_ram":False,"maximum_window_samples":WINDOW,
            "block_history_materialized":False,"true_peak_measured":False,
            "standards_meter_calibration_verified":False,"production_audio_accepted":False,
            "source_modified":False}


def measure_streamed_pcm24_loudness(master):
    if (type(master) is not dict or master.get("format")!=PCM_STREAM_FORMAT or
            master.get("status")!="STREAMED_PCM24_CANDIDATE_PUBLISHED" or
            master.get("source_modified") is not False):
        raise PermissionError("Trusted SHA-bound streamed WO4 master required")
    labels=tuple(master.get("channel_order",()))
    if labels not in WEIGHTS:
        raise PermissionError("Unknown native cinema channel mapping")
    file=Path(master.get("destination",""));identity=_protected_path(file)
    expected=(master.get("wav_file_sha256"),master.get("wav_file_bytes"))
    samples=master["frame_count"]*2000
    def packets():
        if _hash_stream(file)!=expected:
            raise PermissionError("Disk WAV differs from creator-approved receipt")
        with file.open("rb") as original,wave.open(original,"rb") as reader:
            info=os.fstat(original.fileno())
            if ((info.st_dev,info.st_ino)!=identity or
                    reader.getnchannels()!=len(labels) or reader.getsampwidth()!=3 or
                    reader.getframerate()!=48000 or reader.getnframes()!=samples or
                    reader.getcomptype()!="NONE"):
                raise PermissionError("Protected WAV mastering format or identity differs")
            while packet:=reader.readframes(READ_FRAMES):
                yield packet
        if _protected_path(file)!=identity or _hash_stream(file)!=expected:
            raise PermissionError("Mastered PCM changed during streamed loudness QC")
    return measure_bounded_packets(packets,labels,samples,master.get("master_pcm_sha256"))
