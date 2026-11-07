"""WO4 multichannel BS.1770-style K-weighted gated programme loudness.

Deterministic 48 kHz K-weighted channel energy and 400 ms / 75% overlapping
absolute/relative gates. LFE is excluded; this is a measurement candidate,
not a BS.1770 certified meter or a cinema mix target. True peak with
oversampled reconstruction is still a separate independent acceptance gate.
"""
from __future__ import annotations
from io import BytesIO
import math
import wave
from hashlib import sha256

FORMAT="nvp.wo4.k_weighted_loudness_candidate.v1"
# ITU-R BS.1770 48 kHz reference biquads (a0 = 1)
SHELF_B=(1.53512485958697,-2.69169618940638,1.19839281085285)
SHELF_A=(1.0,-1.69065929318241,0.73248077421585)
RLB_B=(1.0,-2.0,1.0)
RLB_A=(1.0,-1.99004745483398,0.99007225036621)
# 1.41 power weights for side/rear surround, LFE excluded.
WEIGHTS={
    ("L","R"):(1.,1.),
    ("L","R","C","LFE","Ls","Rs"):(1.,1.,1.,0.,1.41,1.41),
    ("L","R","C","LFE","Ls","Rs","Lrs","Rrs"):
        (1.,1.,1.,0.,1.41,1.41,1.41,1.41),
}


def _biquad(sample,state,b,a):
    x1,x2,y1,y2=state
    y=b[0]*sample+b[1]*x1+b[2]*x2-a[1]*y1-a[2]*y2
    state[:]=[sample,x1,y,y1]
    return y


def measure_pcm24_loudness(master):
    if (type(master) is not dict or
            master.get("format")!="nvp.wo4.pcm24_candidate.v1" or
            master.get("source_modified") is not False or
            type(master.get("wav_bytes")) is not bytes):
        raise PermissionError("Verified native PCM24 candidate required")
    channels=tuple(master.get("channel_order",()))
    if channels not in WEIGHTS:
        raise PermissionError("Explicit supported speaker channel order required")
    with wave.open(BytesIO(master["wav_bytes"]),"rb") as reader:
        if (reader.getframerate()!=48000 or reader.getsampwidth()!=3 or
                reader.getnchannels()!=len(channels) or
                reader.getnframes()!=master.get("frame_count",0)*2000):
            raise PermissionError("Source PCM sample frequency/length mismatch")
        pcm=reader.readframes(reader.getnframes())
    if sha256(pcm).hexdigest()!=master.get("master_pcm_sha256"):
        raise PermissionError("Source sound master SHA mismatch")
    frame_count=len(pcm)//(3*len(channels))
    window=19200
    step=4800
    if frame_count<window:
        return {"format":FORMAT,"status":"INSUFFICIENT_400MS_AUDIO",
                "measured":False,"lufs":None,"true_peak_measured":False,
                "production_audio_accepted":False}
    states_shelf=[[0.,0.,0.,0.] for _ in channels]
    states_rlb=[[0.,0.,0.,0.] for _ in channels]
    # Energy buffers are per-sample because 400 ms blocks overlap at 100 ms.
    weighted_energy=[0.]*frame_count
    sample_peak=0
    for frame in range(frame_count):
        power=0.
        for ch,weight in enumerate(WEIGHTS[channels]):
            pos=(frame*len(channels)+ch)*3
            value=int.from_bytes(pcm[pos:pos+3],"little",signed=True)
            sample_peak=max(sample_peak,abs(value))
            v=value/8388608.
            shelved=_biquad(v,states_shelf[ch],SHELF_B,SHELF_A)
            filtered=_biquad(shelved,states_rlb[ch],RLB_B,RLB_A)
            power+=weight*filtered*filtered
        weighted_energy[frame]=power
    # Block energy already includes channel weights. Absolute and relative
    # gates operate on energies rather than averaging logarithmic LKFS.
    prefix=[0.]
    for energy in weighted_energy:
        prefix.append(prefix[-1]+energy)
    blocks=[]
    for start in range(0,frame_count-window+1,step):
        energy=(prefix[start+window]-prefix[start])/window
        if energy>0:
            blocks.append((energy,-0.691+10*math.log10(energy)))
    absolute=[e for e,l in blocks if l>=-70.]
    if not absolute:
        integrated=None
        relative_gate=None
    else:
        mean=sum(absolute)/len(absolute)
        relative_gate=-0.691+10*math.log10(mean)-10.
        accepted=[e for e,l in blocks if l>=-70. and l>=relative_gate]
        integrated=(-0.691+10*math.log10(sum(accepted)/len(accepted))
                    if accepted else None)
    return {"format":FORMAT,"status":"K_WEIGHTED_GATE_MEASURED",
            "measured":integrated is not None,
            "lufs":integrated,
            "relative_gate_lkfs":relative_gate,
            "block_count":len(blocks),
            "channel_order":list(channels),
            "lfe_excluded":True,
            "sample_peak_dbfs":(20*math.log10(sample_peak/8388608.)
                                if sample_peak else None),
            "true_peak_measured":False,
            "standards_meter_calibration_verified":False,
            "production_audio_accepted":False,"source_modified":False}
