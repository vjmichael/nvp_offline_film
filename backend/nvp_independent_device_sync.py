"""DA-02E native two-independent-device timing authority.

PortAudio ADC times are STREAM-relative, not interchangeable across devices.
Each stream is independently calibrated to one host monotonic clock using
bracketed Pa_GetStreamTime reads. Per-buffer first ADC sample timestamps
establish a bounded sample-index => host-time affine clock relation.
We reject timing jumps, overflow, calibration jitter and excessive drift;
we NEVER overwrite/retime the original PCM. Film Time mapping is a frozen,
versioned derivative with a source SHA, not a claim of genlock.

A real installed dual-sound-card loopback must verify host API accuracy.
"""
from __future__ import annotations
from hashlib import sha256
import json
import math
import statistics

from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.data_av.independent_device_clock.v1"
SYNC_FORMAT="nvp.data_av.independent_sample_map.v1"
RATE=48000
NANO=1_000_000_000
DEN=1_000_000
MAX_ANCHORS=4096
MIN_ANCHORS=8
MIN_SPAN_NS=750_000_000
MAX_PPM=2000
MAX_ADC_RESIDUAL_NS=2_000_000
MAX_CALIBRATION_SPREAD_NS=2_000_000
MAX_CALIBRATION_BRACKET_NS=2_000_000
MAX_OFFSET_NS=2_000_000_000
MAX_DURATION_S=600


def _int(n,what):
    if type(n) is not int or n<0:
        raise ValueError("Invalid nonnegative "+what)
    return n


def _digest(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                            allow_nan=False).encode("utf8")).hexdigest()


class DeviceTimeTrack:
    def __init__(self,device_id):
        self.device_id=_int(device_id,"device identity")
        self.calibrations=[]
        self.anchors=[]
        self.sample_count=0
        self.last_adc_ns=None
        self.error=None

    def calibrate(self,before_ns,stream_time_ns,after_ns):
        for val in (before_ns,stream_time_ns,after_ns):
            _int(val,"native calibration timestamp")
        if (after_ns<before_ns or
                after_ns-before_ns>MAX_CALIBRATION_BRACKET_NS):
            raise RuntimeError("Host clock calibration bracket is too wide")
        if len(self.calibrations)>=MAX_ANCHORS:
            raise RuntimeError("Too many clock calibration anchors")
        offset=(before_ns+after_ns)//2-stream_time_ns
        self.calibrations.append((offset,after_ns-before_ns))

    def add(self,frames,adc_first_stream_ns,*,status_ok=True):
        _int(frames,"source buffer sample count")
        _int(adc_first_stream_ns,"ADC first-sample timestamp")
        if not status_ok:
            self.error="Native input underflow/overflow or stream reset"
            raise RuntimeError(self.error)
        if not 1<=frames<=RATE:
            raise ValueError("Unbounded native device callback")
        if self.last_adc_ns is not None and adc_first_stream_ns<=self.last_adc_ns:
            raise RuntimeError("Nonmonotonic original ADC clock")
        self.last_adc_ns=adc_first_stream_ns
        # Preserve all PCM packets but store at most ~4 clock anchors/second.
        # This keeps original provenance bounded for a full ten-minute Take.
        if not self.anchors or self.sample_count-self.anchors[-1][0]>=RATE//4:
            if len(self.anchors)>=MAX_ANCHORS:
                raise RuntimeError("Too many ADC clock anchors")
            self.anchors.append((self.sample_count,adc_first_stream_ns,frames))
        self.sample_count+=frames
        if self.sample_count>MAX_DURATION_S*RATE:
            raise RuntimeError("Independent source exceeded original audio bound")

    def seal(self):
        if self.error or len(self.calibrations)<MIN_ANCHORS or (
                len(self.anchors)<MIN_ANCHORS):
            raise RuntimeError("Independent source has insufficient clock evidence")
        offsets=[v[0] for v in self.calibrations]
        if max(offsets)-min(offsets)>MAX_CALIBRATION_SPREAD_NS:
            raise RuntimeError("Unstable stream clock to monotonic correlation")
        offset=round(statistics.median(offsets))
        x0=self.anchors[0][0]
        t0=self.anchors[0][1]
        xs=[n-x0 for n,_,_ in self.anchors]
        ys=[ns-t0 for _,ns,_ in self.anchors]
        if max(ys)<MIN_SPAN_NS:
            raise RuntimeError("Capture too short to verify independent clock drift")
        xbar=sum(xs)/len(xs);ybar=sum(ys)/len(ys)
        divisor=sum((x-xbar)**2 for x in xs)
        if not divisor:
            raise RuntimeError("No measured ADC sample clock slope")
        period=sum((x-xbar)*(y-ybar) for x,y in zip(xs,ys))/divisor
        if not math.isfinite(period) or period<=0:
            raise RuntimeError("Invalid effective independent sample period")
        ppm=round((period*RATE/NANO-1)*1_000_000)
        if abs(ppm)>MAX_PPM:
            raise RuntimeError("Uncorrectable independent device clock drift")
        intercept=round(sum(y-period*x for x,y in zip(xs,ys))/len(xs))
        residual=max(abs(y-intercept-period*x) for x,y in zip(xs,ys))
        if residual>MAX_ADC_RESIDUAL_NS:
            raise RuntimeError("Independent audio ADC times contain discontinuity")
        first_ns=t0+intercept+offset
        if first_ns<0:
            raise RuntimeError("Missing valid host monotonic audio epoch")
        scaled_ticks=round(period*TICKS_PER_SECOND*DEN/NANO)
        if scaled_ticks<=0:
            raise RuntimeError("Invalid native Film Time sample period")
        model={
            "device_id":self.device_id,"sample_rate_declared":RATE,
            "source_sample_count":self.sample_count,
            "first_sample_monotonic_ns":first_ns,
            "sample_period_tick_num":scaled_ticks,
            "sample_period_tick_den":DEN,
            "measured_drift_ppm":ppm,
            "max_adc_residual_ns":math.ceil(residual),
            "calibration_spread_ns":max(offsets)-min(offsets),
            "calibration_bracket_max_ns":max(w for _,w in self.calibrations),
            "adc_anchor_count":len(self.anchors),
            "clock_calibration_count":len(self.calibrations),
            "adc_anchor_sha256":_digest(self.anchors),
            "calibration_sha256":_digest(self.calibrations),
            "timestamp_source":"portaudio_inputBufferAdcTime_bracketed_stream_clock",
            "hardware_genlock":False,
        }
        return model


def align_devices(a,b,*,camera_duration_tick):
    """Build one shared monotonic Film Time origin from two independent clocks.

    The two originals remain independent. Derivative audition interpolation
    applies each source's measured sample-to-time map; no PCM file is modified.
    """
    if (type(a) is not dict or type(b) is not dict or
            a.get("device_id")==b.get("device_id")):
        raise ValueError("Two distinct verified independent input devices required")
    _int(camera_duration_tick,"authoritative camera Film Time duration")
    first_a=a["first_sample_monotonic_ns"]
    first_b=b["first_sample_monotonic_ns"]
    if abs(first_a-first_b)>MAX_OFFSET_NS:
        raise RuntimeError("Independent device capture starts cannot be aligned")
    origin=min(first_a,first_b)
    maps=[]
    for p in (a,b):
        start=round((p["first_sample_monotonic_ns"]-origin)*
                    TICKS_PER_SECOND/NANO)
        period=p["sample_period_tick_num"]
        den=p["sample_period_tick_den"]
        count=p["source_sample_count"]
        end=start+(count*period+den-1)//den
        if end>camera_duration_tick:
            raise RuntimeError("Independent device source exceeds the verified camera timeline")
        maps.append({
            "format":SYNC_FORMAT,"device_id":p["device_id"],
            "first_tick":start,"last_tick_exclusive":end,
            "sample_period_tick_num":period,
            "sample_period_tick_den":den,
            "source_sample_count":count,
            "measured_drift_ppm":p["measured_drift_ppm"],
            "adc_residual_ns":p["max_adc_residual_ns"],
            "source_clock_model_sha256":_digest(p),
            "original_pcm_unmodified":True,
            "synchronized_hardware_clock":False,
        })
    return {"format":FORMAT,"origin_monotonic_ns":origin,
            "clock_models":[a,b],"sample_maps":maps,
            "original_pcm_unmodified":True,
            "hardware_genlocked":False,
            "timing_validated_in_installed_hardware":False}


def verified_source_map(value,*,source_sample_count,event_start,event_end):
    if (type(value) is not dict or
            set(value)!={"format","device_id","first_tick","last_tick_exclusive",
                         "sample_period_tick_num","sample_period_tick_den",
                         "source_sample_count","measured_drift_ppm",
                         "adc_residual_ns","source_clock_model_sha256",
                         "original_pcm_unmodified","synchronized_hardware_clock"}):
        raise RuntimeError("Unverified native independent device clock metadata")
    if (value["format"]!=SYNC_FORMAT or
        value["original_pcm_unmodified"] is not True or
        value["synchronized_hardware_clock"] is not False or
        type(value["sample_period_tick_den"]) is not int or
        value["sample_period_tick_den"]!=DEN or
        type(value["sample_period_tick_num"]) is not int or
        not 140000*DEN<=value["sample_period_tick_num"]<=155000*DEN or
        type(value["first_tick"]) is not int or
        type(value["last_tick_exclusive"]) is not int or
        value["first_tick"]!=event_start or
        value["last_tick_exclusive"]!=event_end or
        type(value["source_sample_count"]) is not int or
        value["source_sample_count"]!=source_sample_count or
        type(value["adc_residual_ns"]) is not int or
        not 0<=value["adc_residual_ns"]<=MAX_ADC_RESIDUAL_NS or
        type(value["measured_drift_ppm"]) is not int or
        abs(value["measured_drift_ppm"])>MAX_PPM):
        raise RuntimeError("Independent clock map/source does not match original samples")
    actual=(source_sample_count*value["sample_period_tick_num"]+DEN-1)//DEN
    if event_end-event_start!=actual:
        raise RuntimeError("Original ADC clock map has inconsistent event duration")
    return value


def interpolated_window(read_original,source_count,sync,first_tick,output_count,
                        *,ticks_per_output_sample):
    """Seek-safe derived resampling; leave source PCM and Film Time immutable."""
    import struct
    if (type(output_count) is not int or not 0<=output_count<=4096 or
        type(first_tick) is not int or first_tick<0):
        raise ValueError("Unbounded derived synchronized sound sample window")
    if output_count==0:return []
    start=sync["first_tick"];period=sync["sample_period_tick_num"]
    den=sync["sample_period_tick_den"]
    sample_ids=[]
    for i in range(output_count):
        tick=first_tick+i*ticks_per_output_sample
        numerator=(tick-start)*den
        if numerator<0:
            sample_ids.append(None)
        else:
            n=numerator//period
            if n>=source_count:sample_ids.append(None)
            else:sample_ids.append((n,numerator%period))
    valid=[s for s in sample_ids if s is not None]
    if not valid:return [0]*output_count
    lo=min(s[0] for s in valid)
    hi=min(source_count,max(s[0] for s in valid)+2)
    if not 0<=hi-lo<=8192:raise RuntimeError("Native derivative exceeds bounded source read")
    raw=read_original(lo,hi-lo)
    if len(raw)!=(hi-lo)*2:
        raise RuntimeError("Incomplete original mono PCM in synchronized audition")
    values=struct.unpack("<"+str(hi-lo)+"h",raw)
    output=[]
    for row in sample_ids:
        if row is None:output.append(0);continue
        n,part=row
        a=values[n-lo]
        b=values[min(n+1,hi-1)-lo]
        # Only derivative resampling; no source revision is overwritten.
        output.append(round(a+(b-a)*part/period))
    return output
