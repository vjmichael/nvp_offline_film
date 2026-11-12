"""G09-C data-first 3D acoustics over frozen OpenUSD and original 48k PCM.

Presentation/source mapping is G07's exact 7_056_000_000 Hz Film Time.
Moving emitters are evaluated from ORIGINAL time-sampled G06 OpenUSD; source
sound samples remain immutable. The listener is the chosen G07 3D camera.
The bounded source-derived mix uses equal-power stereo, near-ear delay,
distance attenuation, geometry-based obstruction, temperature-independent
air absorption, two early reflection taps and a soft sample limiter.

This is physically motivated stereo, NOT claimed binaural HRTF, ambisonics,
full room IR convolution, ray-traced acoustics or discrete Dolby Atmos.
Weather audio is a deterministic DERIVED effect, never a microphone source.
All mix windows are source-time addressable with no prior state: continuous
playback, random seeks and export produce the same sample at every boundary.
"""
from __future__ import annotations
import math
import struct
from hashlib import sha256
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_g09c_acoustics import _base,_json,_sha

RATE=48000
TICK_SAMPLE=TICKS_PER_SECOND//RATE
CELL=480 # 10ms spatial evaluation, recompute at camera/environment boundaries
MAX_WINDOW=RATE*2
MAX_ACTIVE=32
MAX_STAGE_OBJECTS=128

def _dot(a,b):return sum(a[i]*b[i] for i in range(3))
def _norm(a):
    mag=math.sqrt(_dot(a,a))
    return [v/mag for v in a] if mag>1e-9 else None
def _sub(a,b):return [a[i]-b[i] for i in range(3)]
def _cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0]]
def _clamp(v,a,b):return min(b,max(a,v))

def _position(world,path,tick,fallback):
    """Exact source-local OpenUSD movement; no new ActorID translation."""
    if not path.startswith("/World/Objects/"):
        return fallback
    from pxr import Usd,UsdGeom
    prim=world.stage.GetPrimAtPath(path)
    if not prim or not prim.IsA(UsdGeom.Xform):
        raise RuntimeError("The original 3D sound emitter is missing")
    transform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
        Usd.TimeCode(float(tick)))
    p=transform.ExtractTranslation()
    xyz=[float(p[i]) for i in range(3)]
    if any(not math.isfinite(v) or abs(v)>1e5 for v in xyz):
        raise RuntimeError("Original sound movement cannot be evaluated")
    return xyz

def _obstructed(world,emitter,camera,tick,emitter_path,derived_pieces=()):
    """Ray versus bounded stage-object spheres; conservative coarse proxy.

    True production acoustics uses worker-verified mesh BVH/ray tracing later.
    A moving actor/camera or emitter is never treated as a wall.
    """
    if len(world.record["stage_objects"])>MAX_STAGE_OBJECTS:
        raise ValueError("Original film environment has too many sound obstacles")
    delta=_sub(camera,emitter)
    segment_len=math.sqrt(_dot(delta,delta))
    if segment_len<.02:return False
    direction=[v/segment_len for v in delta]
    from pxr import Usd,UsdGeom
    for obj in world.record["stage_objects"]:
        if obj["role"] in ("camera","light","actor") or (
                emitter_path=="/World/Objects/"+obj["id"]):
            continue
        prim=world.stage.GetPrimAtPath("/World/Objects/"+obj["id"])
        if not prim or not prim.IsA(UsdGeom.Xform):continue
        transform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode(float(tick)))
        p=transform.ExtractTranslation()
        center=[float(p[i]) for i in range(3)]
        radius=.5*max(obj["scale"][:3])
        if radius<=0:continue
        offset=_sub(center,emitter)
        along=_dot(offset,direction)
        if not .12<along<segment_len-.12:continue
        near=[offset[i]-along*direction[i] for i in range(3)]
        if _dot(near,near)<(radius*.83)**2:return True
    # Approved G09-A architecture remains a DERIVED physical set, but it
    # can still obstruct a source speaker without rewriting G06 geometry.
    for piece in derived_pieces:
        radius=.5*max(piece["scale"])
        offset=_sub(piece["position"],emitter)
        along=_dot(offset,direction)
        if not .12<along<segment_len-.12:continue
        near=[offset[i]-along*direction[i] for i in range(3)]
        if _dot(near,near)<(radius*.83)**2:return True
    return False

def _spatial(world,recorded,seg,source_tick,setting,edit,derived_pieces=()):
    cam=seg["camera"]["position"]
    forward=_norm(_sub(seg["camera"]["look_at"],cam))
    if forward is None:raise RuntimeError("Film listening camera has no direction")
    side=_norm(_cross(forward,[0.,0.,1.]))
    if side is None:side=[1.,0.,0.]
    emitter=_position(world,recorded["emitter_path"],source_tick,
                      recorded["emitter_position"])
    vector=_sub(emitter,cam)
    dist=math.sqrt(_dot(vector,vector))
    unit=_norm(vector)
    balance=_clamp(edit["pan"],-1,1)
    obstruction=False
    if edit["spatial"]:
        alignment=_dot(unit,side) if unit is not None else 0
        balance=_clamp(balance+alignment*setting["stereo_width"],-1,1)
        obstruction=(_obstructed(world,emitter,cam,source_tick,
                                recorded["emitter_path"],derived_pieces)
                     if setting["obstruction"] else False)
        rolloff=setting["distance_rolloff"]
        distance_gain=1./(1.+max(0.,dist-1.)/15.)**rolloff
        obstruction_gain=(1.-setting["obstruction"]*.65
                          if obstruction else 1.)
        distance_gain*=obstruction_gain
        # Maximum interaural time difference ~0.6ms, aligned to samples.
        itd=round(.0006*RATE*balance)
    else:
        distance_gain=1.
        itd=0
    return (math.sqrt(max(0.,(1.-balance)/2))*distance_gain,
            math.sqrt(max(0.,(1.+balance)/2))*distance_gain,
            max(0,itd),max(0,-itd),dist,obstruction)

def _sample(recorded,src_sample,obstructed=False,air=0.):
    if not 0<=src_sample<recorded["sample_count"]:return 0.
    pcm=recorded["pcm16le"]
    at=src_sample*2
    val=int.from_bytes(pcm[at:at+2],"little",signed=True)
    if not obstructed and not air:return float(val)
    # Non-destructive local two-neighbor lowpass. It is addressable by
    # source index, so chunk splitting never changes the audio samples.
    lo=max(0,src_sample-3);hi=min(recorded["sample_count"]-1,src_sample+3)
    raw=0.
    for index in range(lo,hi+1):
        raw+=int.from_bytes(pcm[index*2:index*2+2],"little",signed=True)
    smoothed=raw/(hi-lo+1)
    mix=_clamp((.75 if obstructed else 0.)+air,0.,.92)
    return val*(1-mix)+smoothed*mix

def _weather_noise(seed,index):
    # A deterministic hash-based signal, NOT a captured weather recording.
    v=(seed ^ ((index+1)*0x9e3779b1))&0xffffffff
    v=(v^(v>>16))*0x7feb352d&0xffffffff
    v=(v^(v>>15))*0x846ca68b&0xffffffff
    return ((v^(v>>16))/2147483647.)-1.

def _weather_at(seg,tick,setting):
    if not setting["weather_sounds"]:return 0.,None
    src_tick=seg["source_in_tick"]+tick-seg["start_tick"]
    events=seg.get("_source_events",[])
    for event in events:
        if (event["kind"] in ("wind","rain","snow") and
            event["start_tick"]<=src_tick<event["end_tick"]):
            intensity=float(event.get("intensity") or 0)
            return setting["weather_level"]*_clamp(intensity/10.,0.,1.),event
    return 0.,None

def _soft_limit(v):
    # Preserve unity-gain speech and source PCM dynamics through the normal
    # range. Only protect the last ~8% before 16-bit clipping. This
    # deterministic knee cannot vary with chunk, frame rate or seek order.
    knee=30000.
    absolute=abs(v)
    if absolute<=knee:
        return int(_clamp(round(v),-32768,32767))
    limit=32767.
    shaped=knee+(limit-knee)*math.tanh((absolute-knee)/(limit-knee))
    return int(_clamp(round(math.copysign(shaped,v)),-32768,32767))

class SpatialFilmMixer:
    """Continuous audio presentation clock, accepts source-safe random seeks.

    Worlds can be reused from the concurrent picture renderer, avoiding
    repeated USD parse/creation and keeping both streams on one Film Time.
    """
    def __init__(self,assembly,worlds):
        self.assembly=assembly
        self.worlds=worlds
        self.total=assembly["duration_tick"]
        self.segments=assembly["segments"]
        self.sources=assembly["original_takes"]
        self.settings=assembly.get("acoustic_looks",{})
        self.context={}
        if len(self.segments)>250:
            raise ValueError("The edited film exceeds 250 source shots")
        for i,seg in enumerate(self.segments):
            if seg["take_id"] not in self.sources:
                if assembly.get("window") is None:
                    raise RuntimeError("The original microphone Take is missing")
                continue
            source=self.sources[seg["take_id"]]
            take_id=seg["take_id"]
            choices=self.settings.get(take_id)
            if choices:
                if choices["acoustics"]["take_sha256"]!=source["take_sha256"] or (
                        choices["sha256"]!=_sha(
                            _json(choices["acoustics"]).encode("utf8"))):
                    raise RuntimeError("Approved room sound changed after film review")
                setting=choices["acoustics"]
            else:
                setting=_base(take_id,source["take_sha256"],source)
            audio={a["clip_id"]:a for a in source["audio"]}
            if len(seg["audio"])>MAX_ACTIVE:
                raise ValueError("Too many simultaneous original sound sources")
            for edit in seg["audio"]:
                item=audio.get(edit["clip_id"])
                if item is None:
                    raise RuntimeError("A film sound decision lost its original recording")
                if (len(item["pcm16le"])!=item["sample_count"]*2 or
                    sha256(item["pcm16le"]).hexdigest()!=item["pcm_sha256"]):
                    raise RuntimeError("Original audio bytes changed after filming")
            approved_set=assembly.get("production_looks",{}).get(take_id)
            pieces=(approved_set["look"]["set_pieces"]
                    if approved_set else ())
            if len(pieces)>110:
                raise ValueError("The film has too many derived sound obstacles")
            self.context[seg["clip_id"]]={
                "seg":seg,"index":i,"world":worlds[take_id],
                "setting":setting,"audio":audio,"cells":{},
                "derived_pieces":pieces}
            seg["_source_events"]=source["events"]
    def _cell(self,ctx,item,edit,tick):
        seg=ctx["seg"]
        # A 10ms cell has one ABSOLUTE Film Time sample position.
        # Sampling at the first sample of an arbitrary request would
        # otherwise produce a different panorama after a seek/restart.
        cell_index=tick//(CELL*TICK_SAMPLE)
        at_tick=max(seg["start_tick"],cell_index*CELL*TICK_SAMPLE)
        src_tick=seg["source_in_tick"]+at_tick-seg["start_tick"]
        src_tick=_clamp(src_tick,0,self.sources[seg["take_id"]]["duration_tick"])
        cell=(cell_index,item["clip_id"])
        cache=ctx["cells"]
        if cell not in cache:
            if len(cache)>650:cache.clear()
            cache[cell]=_spatial(
                ctx["world"],item,seg,src_tick,ctx["setting"],edit,
                ctx["derived_pieces"])
        return cache[cell]
    def window(self,start_sample,count):
        if (type(start_sample) is not int or start_sample<0 or
            type(count) is not int or not 1<=count<=MAX_WINDOW or
            start_sample*TICK_SAMPLE>=self.total):
            raise ValueError("Choose an available continuous sound moment")
        total_count=math.ceil(self.total/TICK_SAMPLE)
        count=min(count,total_count-start_sample)
        mix_l=[0.]*count;mix_r=[0.]*count
        start_tick=start_sample*TICK_SAMPLE
        end_tick=start_tick+count*TICK_SAMPLE
        for seg in self.segments:
            if seg["start_tick"]>=end_tick or seg["end_tick"]<=start_tick:continue
            ctx=self.context.get(seg["clip_id"])
            if ctx is None:
                raise RuntimeError("An active film segment is missing its approved source window")
            setting=ctx["setting"]
            source_audio=ctx["audio"]
            index=ctx["index"]
            lo=max(start_tick,seg["start_tick"])
            hi=min(end_tick,seg["end_tick"])
            first=max(0,math.ceil((lo-start_tick)/TICK_SAMPLE))
            last=min(count,math.ceil((hi-start_tick)/TICK_SAMPLE))
            for edit in seg["audio"]:
                if not edit["enabled"] or not edit["gain"]:continue
                item=source_audio[edit["clip_id"]]
                base=seg["start_tick"]+item["start_tick"]+edit["offset_tick"]-seg["source_in_tick"]
                signal_start=max(first,math.ceil((base-start_tick)/TICK_SAMPLE))
                # True delayed source reflections can arrive after the last
                # original PCM sample. Include that causal tail while the
                # present edited shot is still active; never invent source.
                echo_tail=0
                if edit["spatial"]:
                    if setting["reflections"]:
                        echo_tail=max(echo_tail,round(RATE*
                            setting["room_size"]*1.58/343.))
                    if setting["reverb"]:
                        echo_tail=max(echo_tail,round(RATE*
                            setting["room_size"]*2.5/343.)+29)
                signal_end=min(last,math.ceil((
                    base+item["duration_tick"]+echo_tail*TICK_SAMPLE-
                    start_tick)/TICK_SAMPLE))
                if signal_start>=signal_end:continue
                master=edit["gain"]*self.assembly["master_gain"]
                for n in range(signal_start,signal_end):
                    presentation_tick=start_tick+n*TICK_SAMPLE
                    sample_index=(presentation_tick-base)//TICK_SAMPLE
                    left,right,itd_left,itd_right,dist,blocked=self._cell(
                        ctx,item,edit,presentation_tick)
                    air=(setting["air_absorption"]*
                         _clamp(dist/120.,0.,1.)) if edit["spatial"] else 0.
                    # Causal stereo/near-ear delays, plus true delayed source
                    # reflection taps. No reverb state reset at chunk seams.
                    a=_sample(item,sample_index-itd_left,blocked,air)
                    b=_sample(item,sample_index-itd_right,blocked,air)
                    if edit["spatial"] and setting["reflections"]:
                        # Source-independent early acoustic reflections.
                        d1=round(RATE*setting["room_size"]/343.)
                        d2=round(d1*1.58)
                        wet=setting["reflections"]
                        reflected=(_sample(item,sample_index-d1,True,.23)*.7+
                                   _sample(item,sample_index-d2,True,.36)*.3)
                        a+=wet*reflected
                        b+=wet*reflected*.92
                    if edit["spatial"] and setting["reverb"]:
                        # Short diffuse tail from genuine recorded audio.
                        wet=setting["reverb"]
                        d3=round(RATE*setting["room_size"]*2.5/343.)
                        a+=wet*.22*_sample(item,sample_index-d3,True,.4)
                        b+=wet*.22*_sample(item,sample_index-d3-29,True,.4)
                    fade=1.
                    incoming=seg["transition"]["duration_tick"]
                    if index>0 and incoming and presentation_tick<seg["start_tick"]+incoming:
                        fade=(presentation_tick-seg["start_tick"])/incoming
                    if index+1<len(self.segments):
                        following=self.segments[index+1]
                        outgoing=following["transition"]["duration_tick"]
                        if outgoing and presentation_tick>=following["start_tick"]:
                            fade=1.-(presentation_tick-following["start_tick"])/outgoing
                    fade=_clamp(fade,0,1)
                    mix_l[n]+=a*left*master*fade
                    mix_r[n]+=b*right*master*fade
            if setting["weather_sounds"]:
                # Atmospheric event signal is derived, disclosed and
                # approved. It is spatially broad but not an original PCM.
                for n in range(first,last):
                    now=start_tick+n*TICK_SAMPLE
                    amount,event=_weather_at(seg,now,setting)
                    if event is None or amount<=0:continue
                    seed=int(event["id"][:8],16)
                    noise=_weather_noise(seed,start_sample+n)
                    amplitude=3200*amount
                    mix_l[n]+=noise*amplitude
                    mix_r[n]+=_weather_noise(seed^0x13579,start_sample+n)*amplitude
        data=bytearray(count*4)
        peak=0
        for n in range(count):
            l=_soft_limit(mix_l[n]);r=_soft_limit(mix_r[n])
            struct.pack_into("<hh",data,4*n,l,r)
            peak=max(peak,abs(l),abs(r))
        return bytes(data),{"start_sample":start_sample,
            "sample_count":count,
            "start_tick":start_tick,
            "end_tick":start_tick+count*TICK_SAMPLE,
            "output_channels":2,"sample_rate":RATE,
            "sample_peak":peak,
            "source_pcm_rewritten":False,
            "acoustic_look_sha256":self.assembly.get("acoustic_looks_sha256"),
            "derived_environment_sound":any(
                c["setting"]["weather_sounds"] for c in self.context.values()),
            "ambisonics_or_hrtf_claimed":False}
