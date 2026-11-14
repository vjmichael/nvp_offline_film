"""G07 source-time picture and PCM sound preview — derived and disposable.

A preview samples an independently reopened immutable G06 performance USD
stage and original source PCM. It never becomes a FilmIndex source, Take,
audio recording or final rendered film. Input is G07's validated edit list.
Exact Film Time maps output positions to original source moments without FPS.
"""
from __future__ import annotations

import io
import math
import struct
import wave

from backend.nvp_g07_edit import G07Editor,_project,_sec,_secs,_sha,RATE,TICKS_PER_SAMPLE
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

MAX_AUDIO_PREVIEW_SECONDS=5
MAX_PICTURE_SHOTS=2


def _active(segments,t):
    live=[]
    for i,s in enumerate(segments):
        if s["start_tick"]<=t<s["end_tick"]:
            fade=s["transition"]["duration_tick"]
            incoming=(fade>0 and i>0 and t<s["start_tick"]+fade)
            weight=(t-s["start_tick"])/fade if incoming else 1.0
            live.append((s,max(0.,min(1.,weight))))
    if len(live)==2:
        live.sort(key=lambda pair:pair[0]["start_tick"])
        old,new=live
        return [(old[0],1-new[1]),(new[0],new[1])]
    return live[:MAX_PICTURE_SHOTS]


def _stage_at(raw,objects,tick):
    from pxr import Sdf,Usd,UsdGeom
    layer=Sdf.Layer.CreateAnonymous("nvp-g07-source-preview.usda")
    if not layer.ImportFromString(raw.decode("utf8")) or (
            layer.subLayerPaths or layer.GetExternalReferences()):
        raise RuntimeError("The original filmed scene cannot be reopened")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if not stage or not stage.GetPrimAtPath("/World"):
        raise RuntimeError("Filmed OpenUSD stage was not preserved")
    poses=[]
    tc=Usd.TimeCode(float(tick))
    for item in objects:
        path="/World/Objects/"+item["id"]
        prim=stage.GetPrimAtPath(path)
        if not prim or not prim.IsA(UsdGeom.Xform):
            raise RuntimeError("A filmed object is missing from its original USD")
        transform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(tc)
        location=transform.ExtractTranslation()
        poses.append({
            "id":item["id"],"name":item["name"],"role":item["role"],
            "actor_id":item["actor_id"],"shape":item["shape"],
            "position":[float(location[i]) for i in range(3)],
            "rotation":item["rotation"],"scale":item["scale"],
            "color":item["color"]})
    return poses


def _snapshot(db,editor,pid,tick):
    revision,doc=_project(db,pid)
    length,segments=editor._validate(db,pid,doc)
    if not segments:
        return {"format":"nvp.g07.picture_preview.v1","revision":revision,
                "duration_seconds":0,"position_seconds":0,"shots":[],
                "source_picture_rendered":False,
                "final_video_rendered":False}
    tick=min(tick,max(0,length-1))
    if tick<0:
        raise ValueError("Choose a positive film moment")
    shots=[];cache={}
    for seg,weight in _active(segments,tick):
        row,source,audio=editor._take(db,pid,seg["take_id"],cache)
        src_tick=seg["source_in_tick"]+tick-seg["start_tick"]
        poses=_stage_at(row["performance_usd"],source["stage_objects"],src_tick)
        active=[{"kind":v["kind"],"object_id":v["object_id"],
                 "actor_id":v["actor_id"],"note":v["note"]}
                for v in source["events"] if
                v["start_tick"]<=src_tick<v["end_tick"]]
        setting=source.get("stage_setting",{})
        shots.append({"clip_id":seg["clip_id"],"take_id":seg["take_id"],
            "take_sha256":seg["take_sha256"],
            "scene_id":seg["scene_id"],
            "source_time_seconds":_secs(src_tick),
            "camera":seg["camera"],"grade":seg["grade"],
            "opacity":round(weight,6),
            "objects":poses,"scene_setting":setting,"active_events":active})
    return {"format":"nvp.g07.picture_preview.v1",
        "revision":revision,"duration_seconds":_secs(length),
        "position_seconds":_secs(tick),"shots":shots,
        "source_picture_rendered":False,
        "preview_is_sampled_native_openusd":True,
        "final_video_rendered":False}


def picture(editor:G07Editor,pid,position_seconds):
    tick=_sec(position_seconds)
    def read(db,movie):
        return _snapshot(db,editor,pid,tick)
    return editor._execute(pid,read)


def _stereo_gain(emitter,camera,pan,spatial):
    if not spatial:
        balance=pan;distance_gain=1.0
    else:
        cam=camera["position"];look=camera["look_at"]
        vx=look[0]-cam[0];vy=look[1]-cam[1]
        norm=max(math.hypot(vx,vy),.00001)
        dx=emitter[0]-cam[0];dy=emitter[1]-cam[1]
        side=(dx*vy-dy*vx)/norm
        dist=math.sqrt(sum((emitter[i]-cam[i])**2 for i in range(3)))
        balance=max(-1.,min(1.,pan+side/max(dist,1.0)))
        distance_gain=1./(1.+dist/25.)
    return (math.sqrt(max(0.,(1.-balance)/2.))*distance_gain,
            math.sqrt(max(0.,(1.+balance)/2.))*distance_gain)


def audio_window(editor:G07Editor,pid,start_seconds,duration_seconds):
    """Evaluate selected immutable PCM windows into a disposable stereo WAV."""
    start=_sec(start_seconds)
    duration=_sec(duration_seconds,limit=MAX_AUDIO_PREVIEW_SECONDS)
    if duration<=0 or duration>MAX_AUDIO_PREVIEW_SECONDS*TICKS_PER_SECOND:
        raise ValueError("Listen to at most five seconds at a time")
    if start%TICKS_PER_SAMPLE or duration%TICKS_PER_SAMPLE:
        raise ValueError("The listening window must align to original audio samples")
    samples=duration//TICKS_PER_SAMPLE
    if samples>MAX_AUDIO_PREVIEW_SECONDS*RATE:
        raise ValueError("Listening request too large")
    def read(db,movie):
        revision,doc=_project(db,pid)
        total,segments=editor._validate(db,pid,doc)
        if not segments or start>=total:
            raise ValueError("This film has no source sound at that moment")
        end=min(total,start+duration)
        count=max(0,(end-start)//TICKS_PER_SAMPLE)
        left=[0.]*count;right=[0.]*count
        cache={}
        master=doc["master_gain"]
        # Sum only the portion of each source segment that intersects the
        # requested window. Dissolve weights are evaluated per sample.
        for index,seg in enumerate(segments):
            lo=max(start,seg["start_tick"])
            hi=min(end,seg["end_tick"])
            if hi<=lo:continue
            row,take,sounds=editor._take(db,pid,seg["take_id"],cache)
            source_by_id={item["clip_id"]:item for item in sounds}
            for selection in seg["audio"]:
                if not selection["enabled"] or not selection["gain"]:
                    continue
                original=source_by_id[selection["clip_id"]]
                clip=db.execute("""SELECT pcm,pcm_sha256,sample_count FROM g06_original_pcm
                    WHERE project_id=? AND scene_id=? AND id=?""",
                    (pid,row["scene_id"],original["clip_id"])).fetchone()
                if clip is None or _sha(clip["pcm"])!=clip["pcm_sha256"] or (
                        clip["pcm_sha256"]!=original["pcm_sha256"]):
                    raise RuntimeError("Original sound cannot be evaluated safely")
                raw=bytes(clip["pcm"])
                lead=(original["start_tick"]+selection["offset_tick"])
                sound_start=seg["start_tick"]+lead-seg["source_in_tick"]
                sound_end=sound_start+original["duration_tick"]
                a=max(lo,sound_start);b=min(hi,sound_end)
                if a>=b:continue
                lpan,rpan=_stereo_gain(original["emitter_position"],
                                     seg["camera"],selection["pan"],
                                     selection["spatial"])
                coeff=selection["gain"]*master
                src=memoryview(raw)
                first=max(0,(a-start+TICKS_PER_SAMPLE-1)//TICKS_PER_SAMPLE)
                last=min(count,(b-start+TICKS_PER_SAMPLE-1)//TICKS_PER_SAMPLE)
                for j in range(first,last):
                    moment=start+j*TICKS_PER_SAMPLE
                    original_tick=moment-sound_start
                    original_index=original_tick//TICKS_PER_SAMPLE
                    if not 0<=original_index<clip["sample_count"]:
                        continue
                    pos=original_index*2
                    value=int.from_bytes(src[pos:pos+2],"little",signed=True)
                    # Per-sample editorial crossfade, not a destructive
                    # resampling of the original PCM source.
                    weight=1.
                    if (index>0 and seg["transition"]["duration_tick"] and
                        moment<seg["start_tick"]+seg["transition"]["duration_tick"]):
                        weight=(moment-seg["start_tick"])/seg["transition"]["duration_tick"]
                    elif (index+1<len(segments) and
                          segments[index+1]["transition"]["duration_tick"] and
                          moment>=segments[index+1]["start_tick"]):
                        next_seg=segments[index+1]
                        weight=1.-(moment-next_seg["start_tick"])/next_seg["transition"]["duration_tick"]
                    weight=max(0.,min(1.,weight))
                    left[j]+=value*coeff*lpan*weight
                    right[j]+=value*coeff*rpan*weight
        output=bytearray()
        for j in range(count):
            l=max(-32768,min(32767,round(left[j])))
            r=max(-32768,min(32767,round(right[j])))
            output.extend(struct.pack("<hh",l,r))
        out=io.BytesIO()
        with wave.open(out,"wb") as wav:
            wav.setnchannels(2);wav.setsampwidth(2)
            wav.setframerate(RATE);wav.writeframes(bytes(output))
        return out.getvalue()
    return editor._execute(pid,read)
