"""G09-E bounded, state-continuous source film loudness and PCM finishing.

A full film can span many immutable 10-second AVI assets, but its loudness
and finishing gain must be chosen ONCE for the entire Film Time continuum,
not independently per chunk. This implements a 100ms/400ms K-weighted
BS.1770-style programme meter, 10 LU relative/−70 LUFS absolute gating,
sample-peak headroom and sample-index-addressable fades. Filter state is
continuous over windows, not reset when a new render asset begins.

An accelerated scipy/numpy path is preferred for meaningful feature-length
work. Without those pinned runtimes only a conservative <= 10-minute
slow native-python fallback is admitted. It makes no true-peak (dBTP) or
cinema loudness compliance claim.
"""
from __future__ import annotations
from array import array
from collections import deque
from hashlib import sha256
import math
import struct
import sys
from backend.nvp_g09d_master import HIGH_B,HIGH_A,PASS_B,PASS_A,_biquad

RATE=48000
BLOCK=RATE//10
WINDOW=BLOCK*4
MAX_SAMPLE_COUNT=3*3600*RATE
MAX_INPUT_BYTES=48000*4
FORMAT="nvp.g09e.streaming_sound_master.v1"

class FilmMeter:
    def __init__(self,*,duration_samples):
        if (type(duration_samples) is not int or
            not 1<=duration_samples<=MAX_SAMPLE_COUNT):
            raise ValueError("Film exceeds the three-hour PCM analysis profile")
        self.duration=duration_samples
        self.samples=0
        self.peak=0
        self.block_count=0
        self.block_power=0.
        self.history=deque(maxlen=4)
        self.gates=[]
        self._state=[[0.,0.,0.,0.] for _ in range(4)]
        try:
            import numpy as np
            from scipy.signal import lfilter
            self.np=np;self.filter=lfilter
            self.high_state=np.zeros((2,2),dtype=np.float64)
            self.pass_state=np.zeros((2,2),dtype=np.float64)
            self.engine="scipy-accelerated-biquad"
        except ImportError:
            self.np=None;self.filter=None
            self.engine="python-biquad-short-project"
            if duration_samples>10*60*RATE:
                raise RuntimeError(
                    "Install and pin the native accelerated sound DSP before "
                    "analyzing films longer than ten minutes")
    def _block(self,power):
        self.history.append(power/BLOCK)
        if len(self.history)==4:
            energy=sum(self.history)/4
            if energy>0 and -.691+10*math.log10(energy)>-70:
                self.gates.append(energy)
    def feed(self,raw):
        if (type(raw) is not bytes or not len(raw)%4==0 or
            not 0<len(raw)<=MAX_INPUT_BYTES):
            raise ValueError("Use at most one exact second of source PCM")
        count=len(raw)//4
        if self.samples+count>self.duration:
            raise RuntimeError("The source meter exceeded the film clock")
        if self.np is not None:
            np=self.np
            x=np.frombuffer(raw,dtype="<i2").reshape(-1,2)
            self.peak=max(self.peak,int(np.max(np.abs(x.astype(np.int32)))))
            floated=x.astype(np.float64)/32768.
            filtered,self.high_state=self.filter(
                HIGH_B,HIGH_A,floated,axis=0,zi=self.high_state)
            filtered,self.pass_state=self.filter(
                PASS_B,PASS_A,filtered,axis=0,zi=self.pass_state)
            energy=np.sum(filtered*filtered,axis=1)
            offset=0
            while offset<count:
                n=min(BLOCK-self.block_count,count-offset)
                self.block_power+=float(np.sum(energy[offset:offset+n]))
                self.block_count+=n;offset+=n
                if self.block_count==BLOCK:
                    self._block(self.block_power)
                    self.block_power=0.;self.block_count=0
        else:
            pcm=array("h");pcm.frombytes(raw)
            if sys.byteorder!="little":pcm.byteswap()
            self.peak=max(self.peak,max(abs(v) for v in pcm))
            for i in range(0,len(pcm),2):
                energy=0.
                for channel in (0,1):
                    a=pcm[i+channel]/32768.
                    high=_biquad(a,HIGH_B,HIGH_A,self._state[channel*2])
                    passout=_biquad(high,PASS_B,PASS_A,self._state[channel*2+1])
                    energy+=passout*passout
                self.block_power+=energy;self.block_count+=1
                if self.block_count==BLOCK:
                    self._block(self.block_power)
                    self.block_power=0.;self.block_count=0
        self.samples+=count
    def finish(self):
        if self.samples!=self.duration:
            raise RuntimeError("Source soundtrack analysis did not cover the film")
        if self.duration<WINDOW:
            # A sub-400ms film is padded with silence for the gate window.
            energy=(sum(self.history)*BLOCK+self.block_power)/WINDOW
            if energy>0 and -.691+10*math.log10(energy)>-70:
                self.gates=[energy]
        if not self.gates:lufs=None
        else:
            preliminary=sum(self.gates)/len(self.gates)
            relative=-.691+10*math.log10(preliminary)-10.
            floor=10**((max(-70.,relative)+.691)/10)
            qualified=[e for e in self.gates if e>=floor]
            lufs=(-.691+10*math.log10(sum(qualified)/len(qualified))
                  if qualified else None)
        return {"sample_count":self.samples,"sample_peak_abs":self.peak,
            "integrated_lufs":round(lufs,3) if lufs is not None else None,
            "meter_engine":self.engine,
            "gated_400ms_blocks":len(self.gates),
            "true_peak_measured":False,
            "physical_multichannel_cinema_certified":False}

def plan_gain(measured,finishing):
    """One deterministic film-wide gain; never a per-chunk AGC compressor."""
    if type(measured) is not dict or type(finishing) not in (dict,type(None)):
        raise ValueError("Invalid film-wide sound mastering plan")
    if finishing is None:
        return {"format":FORMAT,"source":measured,
            "gain":1.,"peak_ceiling_dbfs":0.,
            "target_integrated_lufs":None,"intention":"working",
            "fade_in_samples":0,"fade_out_samples":0,
            "target_claimed_reached":False,
            "genuine_original_source_not_modified":True}
    doc=finishing["finishing"]
    target=doc["audio"]["target_lufs"]
    peak_db=doc["audio"]["peak_ceiling_dbfs"]
    absolute_peak=measured["sample_peak_abs"]
    possible=32767*10**(peak_db/20)/(absolute_peak or 1)
    pre=measured["integrated_lufs"]
    required=(10**((target-pre)/20) if pre is not None else 1.)
    gain=min(required,10**(12/20),possible)
    if not math.isfinite(gain) or gain<0:
        raise RuntimeError("The requested cinema sound level cannot be safely applied")
    estimated=(pre+20*math.log10(gain) if pre is not None and gain>0 else None)
    # Nonlinear gating/fades may move integrated loudness, so a nominal
    # estimate must NEVER be advertised as a verified final LUFS.
    return {"format":FORMAT,"source":measured,
        "gain":round(gain,12),
        "peak_ceiling_dbfs":peak_db,
        "target_integrated_lufs":target,
        "intention":doc["finishing_intent"],
        "fade_in_samples":round(doc["audio"]["fade_in_seconds"]*RATE),
        "fade_out_samples":round(doc["audio"]["fade_out_seconds"]*RATE),
        "predicted_lufs_before_fades":round(estimated,3)
            if estimated is not None else None,
        "target_claimed_reached":False,
        "genuine_original_source_not_modified":True}

def finish_window(original,plan,*,start_sample,total_samples):
    if (type(original) is not bytes or not original or
        len(original)%4 or len(original)>MAX_INPUT_BYTES or
        type(start_sample) is not int or start_sample<0 or
        type(total_samples) is not int or
        start_sample+len(original)//4>total_samples):
        raise ValueError("Audio chunk is outside the original Film Time")
    if plan["format"]!=FORMAT:
        raise RuntimeError("Sound finishing plan is not trusted")
    source=array("h");source.frombytes(original)
    if sys.byteorder!="little":source.byteswap()
    fade_in=plan["fade_in_samples"];fade_out=plan["fade_out_samples"]
    gain=plan["gain"]
    max_abs=0
    for i in range(0,len(source),2):
        absolute=start_sample+i//2
        envelope=1.
        if fade_in:
            envelope=min(envelope,absolute/fade_in)
        if fade_out:
            envelope=min(envelope,max(0,(total_samples-1-absolute)/fade_out))
        for channel in (0,1):
            value=round(source[i+channel]*gain*envelope)
            value=int(max(-32768,min(32767,value)))
            source[i+channel]=value
            max_abs=max(max_abs,abs(value))
    if max_abs>32767*10**(plan["peak_ceiling_dbfs"]/20)+1:
        raise RuntimeError("Final film sound exceeds its approved sample peak")
    if sys.byteorder!="little":source.byteswap()
    return source.tobytes()
