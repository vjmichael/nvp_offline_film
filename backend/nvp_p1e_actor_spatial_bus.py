"""P1-E: ActorID-owned, original recorded dialogue -> exact-tick 3D stereo.

This is a bounded, deterministic 48kHz PCM16LE dry spatial bus for genuine
ActorDialogueDirector source attributions. One channel is never inferred from
an object label. The director grants one scoped, immutable mix intent;
a separate export approval is still needed to write any output.

Not HRTF, emotion synthesis, reverb, sampled convolution, phoneme matching,
or a replacement for the original recorded PCM / original time clock.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct

from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_p1bc_actor_registry import (
    ActorDialogueDirector,DIALOGUE_FORMAT)
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_data_av_scene import (
    _pan,SAMPLE_RATE,TICKS_PER_SAMPLE,MAX_SAMPLES,FrozenSceneAV)
from backend.nvp_temporal_ledger import _int

FORMAT="nvp.p1e.actor_owned_dry_spatial_bus.v1"
MAX_ROUTES=8
ROUTE_FIELDS=frozenset(("dialogue_id","revision","gain"))


def _canonical(doc):
    return json.dumps(doc,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


class NativeActorSpatialBus:
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("Authoritative FilmIndex and native director grant required")
        self.index=index
        self.approve=verify_director_action
        self.dialogue=ActorDialogueDirector(
            index,verify_director_action=lambda *_:False)
        self.sources=RecordedSoundSources(index)

    def _dialogue(self,project_id,route):
        rec=self.index.read_revision(project_id,route["dialogue_id"],route["revision"])
        data=rec["data"]
        if (rec["kind"]!="dialogue" or data.get("format")!=DIALOGUE_FORMAT or
            data.get("voice_synthesized") is not False or
            data.get("lip_sync_generated") is not False):
            raise RuntimeError("Audio route must be genuine canonical ActorID voice")
        take,scene,binding,event,audio,_=self.dialogue._original_event(
            project_id,data["source_take_id"],data["actor_id"],data["event_id"])
        if (take["document_sha256"]!=data["source_take_sha256"] or
            scene["document_sha256"]!=data["scene_document_sha256"] or
            audio["document_sha256"]!=data["original_pcm_document_sha256"] or
            binding["actor_id"]!=data["actor_id"] or
            binding["path"]!=data["actor_usd_prim_path"] or
            event["start_tick"]!=data["start_tick"] or
            event["end_tick"]!=data["end_tick"]):
            raise RuntimeError("Original actor voice route changed since approval")
        if ("source_sync" in event["payload"] or
            "clock_evidence" in event["payload"]):
            raise RuntimeError("Multi-device source clock needs separate source-synced actor mix")
        if event["start_tick"]%TICKS_PER_SAMPLE:
            raise RuntimeError("Source event starts mid original PCM sample; no silent time shift")
        return rec,take,scene,binding,event,audio

    def publish(self,project_id,mix_id,*,take_id,listener_path,routes,
                creator_event,expected_revision=0):
        _require_pid(project_id)
        _id(mix_id,"ActorID spatial mix")
        _id(take_id,"original source Digital Take")
        _int(expected_revision,"expected spatial mix revision")
        if type(listener_path) is not str or not (
                listener_path.startswith("/World/") and len(listener_path)<=240):
            raise ValueError("Spatial listener must be one authored USD prim")
        if type(routes) is not list or not 1<=len(routes)<=MAX_ROUTES:
            raise ValueError("Original actor source mix supports one to eight voices")
        checked=[]
        unique=set()
        dependencies={}
        take_sha=None
        for row in routes:
            if type(row) is not dict or set(row)!=ROUTE_FIELDS:
                raise ValueError("Actor mix route needs exact dialogue ID/revision/gain")
            did=_id(row["dialogue_id"],"actor dialogue source")
            rev=_int(row["revision"],"original dialogue revision",minimum=1)
            gain=row["gain"]
            if type(gain) not in (float,int) or not math.isfinite(gain) or not 0<=gain<=2:
                raise ValueError("Director original actor gain is outside dry mix bounds")
            if did in unique:
                raise ValueError("Same original voice event is routed more than once")
            unique.add(did)
            original,take,scene,binding,event,audio=self._dialogue(
                project_id,{"dialogue_id":did,"revision":rev})
            if take["object_id"]!=take_id:
                raise RuntimeError("Spatial mix cannot silently combine different original Takes")
            if take_sha is None:take_sha=take["document_sha256"]
            if take["document_sha256"]!=take_sha:
                raise RuntimeError("Spatial voices do not share a frozen source Take")
            av=FrozenSceneAV(self.index,project_id,take_id,
                expected_take_sha256=take_sha,listener_path=listener_path)
            av.close()  # Source listener checked, never starts a device
            route={"dialogue_id":did,"revision":rev,
                   "dialogue_document_sha256":original["document_sha256"],
                   "actor_id":binding["actor_id"],
                   "actor_prim":binding["path"],
                   "source_pcm_sha256":audio["document_sha256"],
                   "gain":float(gain)}
            checked.append(route)
            for object_id,revision,role in (
                (did,rev,"dialogue"),
                (binding["actor_id"],binding["actor_revision"],"actor"),
                (audio["object_id"],audio["revision"],"audio"),
            ):
                dependencies[(object_id,revision,role)]={
                    "object_id":object_id,"revision":revision,"role":role}
        checked=sorted(checked,key=lambda x:x["dialogue_id"])
        document={"format":FORMAT,"take_id":take_id,
                  "take_document_sha256":take_sha,
                  "listener_path":listener_path,
                  "routes":checked,
                  "routes_sha256":hashlib.sha256(_canonical(checked)).hexdigest(),
                  "audio_sample_rate":SAMPLE_RATE,"channels":2,
                  "source_pcm_immutable":True,"dry_stereo_3d_panning":True,
                  "hrtf_processed":False,"voice_generated":False,
                  "phoneme_sync_computed":False,"sound_master_approved":False}
        scope={"operation":"nvp.p1e.commit_actor_dry_spatial_mix.v1",
               "project_id":project_id,"mix_id":mix_id,
               "expected_revision":expected_revision,
               "take_document_sha256":take_sha,
               "routes_sha256":document["routes_sha256"],
               "listener_path":listener_path,"sound_master_approved":False}
        if self.approve(creator_event,dict(scope)) is not True:
            raise PermissionError("Director refused exact original actor sound mix")
        for r in checked:
            record,*_=self._dialogue(project_id,r)
            if record["document_sha256"]!=r["dialogue_document_sha256"]:
                raise RuntimeError("Actor original source changed during approval")
        deps=[{"object_id":take_id,"revision":1,"role":"source_take"}]
        deps.extend(sorted(dependencies.values(),key=lambda x:(
            x["object_id"],x["revision"],x["role"])))
        return self.index.register_revision(
            project_id,mix_id,"presentation",document,
            expected_revision=expected_revision,dependencies=deps)

    def open(self,project_id,mix_id,revision):
        record=self.index.read_revision(project_id,mix_id,revision)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
            doc.get("sound_master_approved") is not False or
            doc.get("source_pcm_immutable") is not True or
            doc.get("hrtf_processed") is not False or
            doc.get("voice_generated") is not False or
            doc.get("phoneme_sync_computed") is not False):
            raise RuntimeError("Not an original P1-E actor-owned stereo bus")
        if hashlib.sha256(_canonical(doc["routes"])).hexdigest()!=doc["routes_sha256"]:
            raise RuntimeError("Original actor routing changed")
        take=self.index.read_revision(project_id,doc["take_id"],1)
        if take["document_sha256"]!=doc["take_document_sha256"]:
            raise RuntimeError("Original actor spatial mix source changed")
        for r in doc["routes"]:
            original,*_=self._dialogue(project_id,r)
            if original["document_sha256"]!=r["dialogue_document_sha256"]:
                raise RuntimeError("Original actor spatial mix changed its frozen dialogue")
        return record

    def window(self,project_id,mix_id,revision,*,first_sample,count):
        """Read a bounded exact original-PCM sample window as stereo bytes."""
        rec=self.open(project_id,mix_id,revision)
        doc=rec["data"]
        first=_int(first_sample,"source PCM cursor")
        n=_int(count,"bounded PCM window",minimum=1,maximum=MAX_SAMPLES)
        begin_tick=first*TICKS_PER_SAMPLE
        end_tick=(first+n)*TICKS_PER_SAMPLE
        av=FrozenSceneAV(self.index,project_id,doc["take_id"],
            expected_take_sha256=doc["take_document_sha256"],
            listener_path=doc["listener_path"])
        try:
            if end_tick>av.duration:
                raise ValueError("Original PCM spatial read exceeds frozen Take")
            at_first=av.snapshot(begin_tick)
            at_last=av.snapshot(end_tick-1)
        finally:
            av.close()
        def locations(snapshot):
            return {v["path"]:v["world_translation"] for v in snapshot["objects"]}
        a=locations(at_first)
        b=locations(at_last)
        if doc["listener_path"] not in a or doc["listener_path"] not in b:
            raise RuntimeError("Authorized source listener missing at PCM time")
        output_l=[0.0]*n
        output_r=[0.0]*n
        active=[]
        for route in doc["routes"]:
            original,take,scene,binding,event,audio=self._dialogue(project_id,route)
            actor=route["actor_prim"]
            if actor not in a or actor not in b:
                raise RuntimeError("Original ActorID cannot be located in USD mix")
            first_active=max(first,event["start_tick"]//TICKS_PER_SAMPLE)
            last_active=min(first+n,
                (event["end_tick"]+TICKS_PER_SAMPLE-1)//TICKS_PER_SAMPLE)
            if first_active>=last_active:
                continue
            start_source=first_active-event["start_tick"]//TICKS_PER_SAMPLE
            available=audio["data"]["sample_count"]-start_source
            total=min(last_active-first_active,max(0,available))
            if not total:continue
            pcm=self.sources.read(project_id,event["source_id"],
                                  event["source_revision"],start_source,total)
            samples=struct.unpack("<"+str(total)+"h",pcm)
            source_gain=event["payload"].get("gain",1.0)
            if (type(source_gain) not in (int,float) or
                not math.isfinite(source_gain) or not 0<=source_gain<=2):
                raise RuntimeError("Original voice event gain is not bounded")
            for j,val in enumerate(samples):
                cursor=first_active+j-first
                fraction=(cursor+0.5)/n
                emitter=[a[actor][i]+(b[actor][i]-a[actor][i])*fraction
                         for i in range(3)]
                listener=[a[doc["listener_path"]][i]+
                          (b[doc["listener_path"]][i]-
                           a[doc["listener_path"]][i])*fraction
                          for i in range(3)]
                left,right=_pan(emitter,listener,route["gain"]*source_gain)
                output_l[cursor]+=val*left
                output_r[cursor]+=val*right
            active.append({"actor_id":route["actor_id"],
                           "original_dialogue_id":route["dialogue_id"],
                           "source_pcm_sha256":route["source_pcm_sha256"],
                           "event_id":event["event_id"]})
        out=bytearray(n*4)
        for i in range(n):
            struct.pack_into("<hh",out,4*i,
                 max(-32768,min(32767,round(output_l[i]))),
                 max(-32768,min(32767,round(output_r[i]))))
        data=bytes(out)
        return {"format":FORMAT,"mix_document_sha256":rec["document_sha256"],
                "take_document_sha256":doc["take_document_sha256"],
                "first_sample":first,"sample_count":n,
                "active_original_actors":active,
                "original_pcm_bytes":data,
                "stereo_sha256":hashlib.sha256(data).hexdigest(),
                "sample_rate":SAMPLE_RATE,"channels":2,
                "audio_source_modified":False,
                "hrtf_processed":False,"voice_generated":False,
                "sound_master_approved":False}
