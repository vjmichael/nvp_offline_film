"""DA-03D: source-verified measured 48 kHz binaural impulse convolution.

User-supplied HRIR/BRIR source has its own immutable FilmIndex SHA,
direction, sample rate and license notice. No dataset is invented or
bundled; no renderer may call this a calibrated cinema binaural master
without separate physical testing. This is a source-first FIR kernel:
arbitrary seek windows read original pre-window PCM, not hidden state.
"""
from __future__ import annotations
import math
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha

FORMAT="nvp.data_av.source_binaural_ir.v1"
KINDS=("anechoic_hrir","room_brir")
MAX_TAPS=160
RATE=48000


def _validate(kind,responses):
    if kind not in KINDS or type(responses) is not list or not 2<=len(responses)<=48:
        raise ValueError("Native source IR kind/direction count is unsupported")
    seen=set();length=None;result=[]
    for item in responses:
        if type(item) is not dict or set(item)!={"azimuth_deg","left","right"}:
            raise ValueError("Original measured IR needs azimuth and L/R impulses")
        az=item["azimuth_deg"]
        if type(az) not in (int,float) or not math.isfinite(az) or not -180<=az<180:
            raise ValueError("Measured IR direction invalid")
        az=round(float(az),5)
        if az in seen:raise ValueError("Duplicated measured direction")
        seen.add(az)
        l=item["left"];r=item["right"]
        if (type(l) is not list or type(r) is not list or len(l)!=len(r)
                or not 1<=len(l)<=MAX_TAPS):
            raise ValueError("Binaural impulse channels are not finite/equal size")
        if length is not None and len(l)!=length:
            raise ValueError("All original impulse directions must share latency")
        length=len(l)
        for x in (l,r):
            if (any(type(v) not in (int,float) or
                    not math.isfinite(v) or abs(v)>2 for v in x) or
                    sum(abs(v) for v in x)>8):
                raise ValueError("Unbounded or nonfinite original impulse tap")
        result.append({"azimuth_deg":az,
                       "left":[float(x) for x in l],
                       "right":[float(x) for x in r]})
    return sorted(result,key=lambda x:x["azimuth_deg"])


class NativeMeasuredBinauralIR:
    def __init__(self,index:FilmIndex,project_id,profile_id,expected_sha256):
        if not isinstance(index,FilmIndex):
            raise TypeError("Original FilmIndex required")
        _require_pid(project_id);_id(profile_id,"measured IR source");_sha(expected_sha256)
        self.index=index;self.pid=project_id;self.source_id=profile_id
        self.source_sha=expected_sha256
        rec=index.read_revision(project_id,profile_id,1)
        if rec["kind"]!="audio" or rec["document_sha256"]!=expected_sha256:
            raise RuntimeError("Binaural impulse profile identity is not verified")
        data=rec["data"]
        if (data.get("format")!=FORMAT or data.get("sample_rate")!=RATE or
            data.get("source_modified") is not False):
            raise RuntimeError("Original measured IR source has changed")
        self.kind=data["measurement_kind"]
        self.directions=_validate(self.kind,data["responses"])
        self.tap_count=len(self.directions[0]["left"])

    @classmethod
    def publish(cls,index,project_id,source_id,*,measurement_kind,
                measured_source_label,license_notice,responses,
                native_creator_approval):
        if not isinstance(index,FilmIndex) or not callable(native_creator_approval):
            raise TypeError("Trusted original index and native approval required")
        _require_pid(project_id);_id(source_id,"original measured IR ID")
        if (type(measured_source_label) is not str or
            not 4<=len(measured_source_label)<=180 or
            type(license_notice) is not str or
            not 4<=len(license_notice)<=512):
            raise ValueError("Measured impulse provenance/redistribution notice required")
        checked=_validate(measurement_kind,responses)
        scope={"operation":"nvp.native_binaural_ir.publish.v1",
               "source_id":source_id,"measurement_kind":measurement_kind,
               "response_count":len(checked),"sample_rate":RATE,
               "no_ffmpeg":True}
        if native_creator_approval(scope) is not True:
            raise PermissionError("Creator denied original impulse publication")
        return index.register_revision(project_id,source_id,"audio",{
            "format":FORMAT,"sample_rate":RATE,
            "measurement_kind":measurement_kind,
            "measured_source_label":measured_source_label,
            "license_notice":license_notice,
            "responses":checked,"source_modified":False,
            "independently_calibrated":False,"film_master_approved":False,
        },expected_revision=0)

    def response_for(self,azimuth):
        if type(azimuth) not in (int,float) or not math.isfinite(azimuth):
            raise ValueError("Untrusted listener-relative source bearing")
        az=(float(azimuth)+180)%360-180
        return min(self.directions,key=lambda x:
                   abs((az-x["azimuth_deg"]+180)%360-180))

    def response_at(self,emitter,listener,world_matrix):
        from backend.nvp_native_spatial_acoustics import _xyz,_right
        delta=[a-b for a,b in zip(_xyz(emitter),_xyz(listener))]
        if math.sqrt(sum(v*v for v in delta))<1e-8:
            return self.response_for(0)
        right=_right(world_matrix)
        if type(world_matrix) is not list or len(world_matrix)!=4:
            raise ValueError("No original USD listener rotation")
        front=_xyz([-x for x in world_matrix[2][:3]])
        az=math.degrees(math.atan2(
            sum(x*y for x,y in zip(delta,right)),
            sum(x*y for x,y in zip(delta,front))))
        return self.response_for(az)

    def convolve(self,pcm,history,response):
        if (type(pcm) not in (list,tuple) or type(history) not in (list,tuple) or
            len(pcm)>4096 or len(history)>self.tap_count-1 or
            any(type(v) is not int or not -32768<=v<=32767
                for v in (*pcm,*history))):
            raise ValueError("Invalid bounded original PCM convolution window")
        if response not in self.directions:
            raise RuntimeError("Measured IR direction is not from this source")
        current=self.index.read_revision(self.pid,self.source_id,1)
        if current["document_sha256"]!=self.source_sha:
            raise RuntimeError("Original binaural IR identity changed")
        count=self.tap_count
        joined=[0]*max(0,count-1-len(history))+list(history)+list(pcm)
        left=[];right=[]
        for i in range(len(pcm)):
            k=i+count-1
            left.append(sum(joined[k-t]*response["left"][t]
                            for t in range(count)))
            right.append(sum(joined[k-t]*response["right"][t]
                             for t in range(count)))
        return left,right
