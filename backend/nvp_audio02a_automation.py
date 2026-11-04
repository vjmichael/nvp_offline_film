"""AUDIO-02A: deterministic sample-domain mix automation; unapproved preview.

Source is indexed WAV, PCM16 stereo 48kHz. Every automation boundary is in
integer sample coordinates. Produces new WAV without mutating source.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import struct
import wave

RATE=48000
LIMIT=RATE*60*120
FORMAT="nvp.audio.automation_pcm16.v1"


def automate_stem(source,destination,points):
    """Apply bounded piecewise linear gain keyframes in thousandths of unity.

    Values are gain in thousandths, not dB: 1000 = unity, 0 = silence.
    Fixed-point interpolation makes output deterministic across Windows/Linux.
    """
    inp=Path(source);out=Path(destination)
    if inp.is_symlink() or not inp.is_file() or out.exists() or out.is_symlink():
        raise RuntimeError("Source unsafe or destination occupied")
    if not out.parent.is_dir() or out.parent.is_symlink():
        raise RuntimeError("Unsafe audio output directory")
    if (type(points) is not list or not 2<=len(points)<=20000 or
        any(type(p) is not dict or set(p)!={"sample","gain_milli"}
            for p in points)):
        raise ValueError("Invalid gain automation points")
    with wave.open(str(inp),"rb") as wav:
        n=wav.getnframes()
        if (wav.getnchannels()!=2 or wav.getsampwidth()!=2 or
            wav.getframerate()!=RATE or wav.getcomptype()!="NONE" or
            not 1<=n<=LIMIT):
            raise RuntimeError("Automation requires bounded 48k PCM16 stereo")
        positions=[p["sample"] for p in points]
        if (positions[0]!=0 or positions[-1]!=n-1 or
            any(type(k) is not int for k in positions) or
            any(a>=b for a,b in zip(positions,positions[1:])) or
            any(type(p["gain_milli"]) is not int or
                not 0<=p["gain_milli"]<=4000 for p in points)):
            raise ValueError("Keyframes must be ordered over entire stem")
        sha=hashlib.sha256()
        with out.open("xb") as output_file, wave.open(output_file,"wb") as dest:
            dest.setnchannels(2);dest.setsampwidth(2);dest.setframerate(RATE)
            at=0;segment=0
            while at<n:
                raw=wav.readframes(min(4096,n-at))
                if not raw or len(raw)%4:
                    raise RuntimeError("Truncated original PCM")
                payload=bytearray()
                for left,right in struct.iter_unpack("<hh",raw):
                    while segment+1<len(points)-1 and at>points[segment+1]["sample"]:
                        segment+=1
                    lo,hi=points[segment],points[segment+1]
                    span=hi["sample"]-lo["sample"]
                    gain=(lo["gain_milli"]*(hi["sample"]-at)+
                          hi["gain_milli"]*(at-lo["sample"])+span//2)//span
                    for sample in (left,right):
                        magnitude=(abs(sample)*gain+500)//1000
                        value=magnitude if sample>=0 else -magnitude
                        payload.extend(struct.pack("<h",max(-32768,min(32767,value))))
                    at+=1
                dest.writeframesraw(payload)
                sha.update(payload)
            if at!=n:raise RuntimeError("Automation frame count mismatch")
    return {"format":FORMAT,"samples_per_channel":n,
            "audio_pcm_sha256":sha.hexdigest(),"points":points,
            "director_approved":False,"final_master":False}
