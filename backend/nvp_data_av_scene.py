"""DATA-AV-01: FFmpeg-free source/data-first A/V evaluation.

Exact Film Time and a frozen OpenUSD Digital Take are authoritative.
Only requested time and audio sample windows are evaluated. Camera/object
state is data, not a decoded video. PCM output is a disposable AUDIO DEVICE
buffer, never a recorded/BWF master or the project's source of truth.

This first native engine implements deterministic dry spatial sound (distance
attenuation and stereo panning). Full scene acoustic propagation, occlusion,
HRTF and a photoreal live viewport are separate production acceptance gates.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import struct

from backend.nvp_data_av_source import (
    RecordedSoundSources,SAMPLE_RATE,MAX_READ_SAMPLES)
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_openusd_take import OpenUSDTakeCapture,FORMAT as TAKE_FORMAT
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_original_clock_binding import verified_original_clock
from backend.nvp_independent_device_sync import interpolated_window
from backend.nvp_temporal_ledger import TICKS_PER_SECOND,_int

FORMAT="nvp.data_av.native_scene_window.v1"
TICKS_PER_SAMPLE=TICKS_PER_SECOND//SAMPLE_RATE
MAX_SOUND_EVENTS=32
MAX_SAMPLES=4096

def _hash(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()

def _pan(emitter,listener,gain):
    # USD scene coordinates are meters; X is left/right and Z is vertical.
    dx=emitter[0]-listener[0]
    dy=emitter[1]-listener[1]
    dz=emitter[2]-listener[2]
    distance=math.sqrt(dx*dx+dy*dy+dz*dz)
    balance=max(-1.0,min(1.0,dx/(1.0+abs(dx)+abs(dy))))
    attenuation=1.0/(1.0+max(0.0,distance-1.0))
    return (
        attenuation*gain*math.sqrt((1.0-balance)*0.5),
        attenuation*gain*math.sqrt((1.0+balance)*0.5),
    )


class FrozenSceneAV:
    def __init__(self,index:FilmIndex,project_id,take_id, *,
                 expected_take_sha256,listener_path):
        if not isinstance(index,FilmIndex):
            raise TypeError("Native FilmIndex is required")
        _require_pid(project_id)
        _id(take_id,"frozen Digital Take")
        _sha(expected_take_sha256)
        self.index=index
        self.project_id=project_id
        self.take_id=take_id
        self.take=index.read_revision(project_id,take_id,1)
        if (self.take["kind"]!="take" or
            self.take["document_sha256"]!=expected_take_sha256 or
            self.take["data"].get("format")!=TAKE_FORMAT or
            self.take["data"].get("frozen") is not True):
            raise RuntimeError("Unapproved, stale or non-data-first Digital Take")
        self.data=self.take["data"]
        self.duration=self.data["duration_tick"]
        if (type(listener_path) is not str or
            not listener_path.startswith("/World/") or
            len(listener_path)>240):
            raise ValueError("Invalid scene listener")
        self.listener_path=listener_path
        self.scene_state=OpenUSDTimeState(index)
        self.sound=RecordedSoundSources(index)
        self.timeline=self.scene_state.ledger
        # This independently checks frozen source scene, timeline, dependent
        # sample hashes and original Digital Take (never launches a decoder).
        verified=OpenUSDTakeCapture(
            index,verify_creator_action=lambda event,scope:False
        ).verify_take(project_id,take_id)
        if verified["take_document_sha256"]!=expected_take_sha256:
            raise RuntimeError("Frozen source verification changed")
        source=self.scene_state.scene.open(
            project_id,self.data["scene_id"],
            self.data["scene_revision"])[0]
        self.roles=source["data"]["prim_roles"]
        if (listener_path not in self.roles or
            self.roles[listener_path] not in ("camera","anchor","actor")):
            raise ValueError("Listener must be an authored scene object")
        self.closed=False

    def close(self):
        self.closed=True

    def _current_take(self):
        if self.closed:
            raise PermissionError("Creator stopped native data playback")
        if self.index.read_revision(
            self.project_id,self.take_id,1)["document_sha256"] != self.take[
            "document_sha256"]:
            raise RuntimeError("Frozen take or source revision identity changed")

    def snapshot(self,tick):
        self._current_take()
        _int(tick,"source Film Time",maximum=self.duration-1)
        snapshot=self.scene_state.evaluate(
            self.project_id,self.data["scene_id"],
            self.data["scene_revision"],self.data["timeline_id"],
            self.data["timeline_revision"],tick=tick)
        if (snapshot["scene_document_sha256"]!=self.data[
            "scene_document_sha256"] or
            snapshot["timeline_document_sha256"]!=self.data[
                "timeline_document_sha256"]):
            raise RuntimeError("Opened USD state changed after frozen take")
        return snapshot

    def audio_window(self,first_sample,count):
        """Render bounded stereo PCM16LE from exact sparse sound events.

        There is no frame-rate, FFmpeg process, WAV/BWF bounce, temporary MP4,
        filesystem path supplied by a viewer or full-film buffer. The caller
        chooses an exact integer sample cursor and can move backward as easily
        as forward.
        """
        _int(first_sample,"first output sample")
        _int(count,"native audio window",minimum=1,maximum=MAX_SAMPLES)
        start_tick=first_sample*TICKS_PER_SAMPLE
        end_tick=(first_sample+count)*TICKS_PER_SAMPLE
        if start_tick>=self.duration or end_tick>self.duration:
            raise ValueError("Audio request outside frozen Digital Take")
        mid_tick=start_tick+(end_tick-start_tick)//2
        at_start=self.snapshot(start_tick)
        at_end=self.snapshot(end_tick-1)
        positions_a={o["path"]:o["world_translation"]
                     for o in at_start["objects"]}
        positions_b={o["path"]:o["world_translation"]
                     for o in at_end["objects"]}
        if self.listener_path not in positions_a:
            raise RuntimeError("Virtual listener no longer exists")
        page=self.timeline.events_in(
            self.project_id,self.data["timeline_id"],
            self.data["timeline_revision"],start_tick=start_tick,
            end_tick=end_tick,limit=MAX_SOUND_EVENTS+1)
        if page["next_cursor"] is not None or len(page["events"])>MAX_SOUND_EVENTS:
            raise RuntimeError("Sound event density exceeds native mixer budget")
        events=[x for x in page["events"] if x["event_kind"] in (
            "sound","dialogue")]
        left=[0.0]*count
        right=[0.0]*count
        for event in events:
            if event["start_tick"]>=event["end_tick"]:
                continue
            path=event["payload"].get("usd_prim_path")
            if path not in self.roles or path not in positions_a:
                raise RuntimeError("Recorded source event has no known USD emitter")
            gain=event["payload"].get("gain",1.0)
            if type(gain) not in (int,float) or not math.isfinite(gain) or not (
                0.0<=gain<=2.0):
                raise ValueError("Invalid recorded sound event gain")
            record=self.sound.describe(
                self.project_id,event["source_id"],event["source_revision"])
            if record["document_sha256"]!=event["source_document_sha256"]:
                raise RuntimeError("Original recorded sound revision is stale")
            source_count=record["data"]["sample_count"]
            first_active=max(first_sample,
                (event["start_tick"]+TICKS_PER_SAMPLE-1)//TICKS_PER_SAMPLE)
            last_active=min(first_sample+count,
                (event["end_tick"]+TICKS_PER_SAMPLE-1)//TICKS_PER_SAMPLE)
            clock=verified_original_clock(
                self.index,self.project_id,event["source_id"],
                event["start_tick"],event["end_tick"],
                event["payload"].get("source_sync"),
                event["payload"].get("clock_evidence"),
                source_sample_count=source_count)
            if clock is None:
                # Legacy single-device original PCM preserves exact 48-kHz
                # source indices; never infer independent clock metadata.
                first_local=(first_active*TICKS_PER_SAMPLE-event["start_tick"])
                first_src=max(0,first_local//TICKS_PER_SAMPLE)
                last_active=min(last_active,first_active+
                                max(0,source_count-first_src))
                n=last_active-first_active
                if n<=0:continue
                raw=self.sound.read(
                    self.project_id,event["source_id"],
                    event["source_revision"],first_src,n)
                samples=struct.unpack("<"+str(n)+"h",raw)
            else:
                # Independently clocked audio is resampled ONLY into the
                # temporary bounded device window from SHA-verified original
                # samples; the frozen PCM source remains byte-identical.
                n=last_active-first_active
                if n<=0:continue
                samples=interpolated_window(
                    lambda first,count:self.sound.read(
                        self.project_id,event["source_id"],
                        event["source_revision"],first,count),
                    source_count,clock,first_active*TICKS_PER_SAMPLE,n,
                    ticks_per_output_sample=TICKS_PER_SAMPLE)
            for i,val in enumerate(samples):
                cursor=first_active+i-first_sample
                # Interpolate native USD emitter/listener positions across
                # the small read window; no output picture/frame authority.
                fraction=(cursor+0.5)/count
                a=positions_a[path];b=positions_b[path]
                emitter=[a[j]+(b[j]-a[j])*fraction for j in range(3)]
                la=positions_a[self.listener_path]
                lb=positions_b[self.listener_path]
                listener=[la[j]+(lb[j]-la[j])*fraction for j in range(3)]
                l,r=_pan(emitter,listener,gain)
                left[cursor]+=val*l
                right[cursor]+=val*r
        pcm=bytearray(count*4)
        for i in range(count):
            l=max(-32768,min(32767,round(left[i])))
            r=max(-32768,min(32767,round(right[i])))
            struct.pack_into("<hh",pcm,i*4,l,r)
        bytes_out=bytes(pcm)
        return {
            "format":FORMAT,"status":"READY",
            "take_id":self.take_id,
            "take_document_sha256":self.take["document_sha256"],
            "scene_document_sha256":self.data["scene_document_sha256"],
            "timeline_document_sha256":self.data["timeline_document_sha256"],
            "listener_path":self.listener_path,
            "first_sample":first_sample,"sample_count":count,
            "actual_start_tick":str(start_tick),
            "next_tick":str(end_tick),
            "sample_rate":SAMPLE_RATE,"channels":2,
            "sample_encoding":"signed_16_le",
            "audio_sha256":hashlib.sha256(bytes_out).hexdigest(),
            "pcm_base64":base64.b64encode(bytes_out).decode("ascii"),
            "audible_event_ids":[x["event_id"] for x in events],
            "source_modified":False,"film_master_approved":False,
            "frame_based_playback":False,
            "renderer":"native_time_usd_pcm_dry_spatial_v1",
        }
