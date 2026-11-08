"""WO6-07E: one exact editorial frame and corresponding *real* source PCM.

This is SOURCE-time director audition, not rendered frames, continuous 24 fps
movie playback, PCM24 mix/master, or final film release. Sound and scene
provenance come from existing FilmIndex/OpenUSD/TemporalLedger only.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO
import json
import struct
import wave

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly, FORMAT as EDIT_FORMAT
from backend.nvp_temporal_ledger import (
    TemporalLedger, TICKS_PER_SECOND, tick_from_frame)
from backend.nvp_wo6_scene_context import assemble_film_crew_context

FORMAT="nvp.wo6_07e.exact_edited_source_pcm_review.v1"
FPS=24
SAMPLE_RATE=48000
SAMPLES_PER_FRAME=SAMPLE_RATE//FPS
AUDIO_WINDOW_FRAMES=12  # at most half a second of authentic PCM per human click
SOURCE_AUDIO_WINDOW_SAMPLES=SAMPLES_PER_FRAME*AUDIO_WINDOW_FRAMES
TICKS_PER_SAMPLE=TICKS_PER_SECOND//SAMPLE_RATE
MAX_ACTIVE_EVENTS=32
MAX_MIXED_PCM_EVENTS=4
MAX_OUTPUT_FRAME=24*60*60*3  # review 3h bounded original source


def _sealed_events(index,pid,timeline_id,rev,start,end):
    temporal=TemporalLedger(index)
    source=temporal._revision(pid,timeline_id,rev)
    temporal.verify(pid,timeline_id,rev)
    # Source revisions may contain millions of events. Only a bounded
    # actively overlapping slice is needed; queries never fabricate completeness.
    active=temporal.events_in(
        pid,timeline_id,rev,start_tick=start,end_tick=end,
        limit=MAX_ACTIVE_EVENTS+1)["events"]
    if len(active)>MAX_ACTIVE_EVENTS:
        raise RuntimeError("Source review would truncate active native events")
    return source,active


def _verify_derived_audio_timeline(index,pid,take,timeline_id,rev,sha):
    original=take["data"]
    baseline=TemporalLedger(index)._revision(
        pid,original["timeline_id"],original["timeline_revision"])
    if baseline["document_sha256"]!=original["timeline_document_sha256"]:
        raise PermissionError("Frozen Take's original temporal SHA changed")
    selected=TemporalLedger(index)._revision(pid,timeline_id,rev)
    if selected["document_sha256"]!=sha:
        raise PermissionError("Chosen source sound revision has changed")
    if (timeline_id==original["timeline_id"] and
            rev==original["timeline_revision"]):
        return selected,False
    # An edited sound timeline is allowed only when its whole original
    # event manifest is preserved byte-for-byte and it adds exactly
    # ONE original-PCM event. No automatic remaster/retiming.
    if (selected["data"]["duration_tick"]!=baseline["data"]["duration_tick"] or
            baseline["data"]["event_count"]>128 or
            selected["data"]["event_count"]!=baseline["data"]["event_count"]+1):
        raise PermissionError("Derived audio timeline is not one source-preserving cue edit")
    length=baseline["data"]["duration_tick"]
    temporal=TemporalLedger(index)
    # Reopen the WHOLE bounded source event ledger for strict derived-cue
    # parity; the per-frame source window retains a tighter active limit.
    temporal.verify(pid,original["timeline_id"],original["timeline_revision"])
    temporal.verify(pid,timeline_id,rev)
    old=temporal.events_in(
        pid,original["timeline_id"],original["timeline_revision"],
        start_tick=0,end_tick=length,limit=129)["events"]
    new=temporal.events_in(
        pid,timeline_id,rev,start_tick=0,end_tick=length,limit=130)["events"]
    if len(old)!=baseline["data"]["event_count"] or (
            len(new)!=selected["data"]["event_count"]):
        raise PermissionError("Cannot establish unchanged complete original audio events")
    def canonical(item):
        return json.dumps(item,sort_keys=True,separators=(",",":"),allow_nan=False)
    old_map={e["event_id"]:canonical(e) for e in old}
    new_map={e["event_id"]:canonical(e) for e in new}
    if (any(new_map.get(k)!=v for k,v in old_map.items()) or
            len(new_map)!=len(old_map)+1):
        raise PermissionError("The sound edit discarded or revised original timeline events")
    added=[e for e in new if e["event_id"] not in old_map]
    if len(added)!=1 or added[0]["event_kind"]!="sound":
        raise PermissionError("Sound edit did not add one original PCM cue")
    extra=added[0]
    item=RecordedSoundSources(index).describe(
        pid,extra["source_id"],extra["source_revision"])
    if (item["document_sha256"]!=extra["source_document_sha256"] or
            extra["payload"].get("recorded_source_sha256")!=item["document_sha256"] or
            extra["payload"].get("director_entered_sound_cue") is not True):
        raise PermissionError("Derived cue lacks original source PCM provenance")
    return selected,True


def _window_pcm(index,pid,active,source_tick,requested_samples):
    """Exact-sample bounded sum in PCM16, no assumed mastered audio."""
    sounds=[e for e in active if e["event_kind"] in ("dialogue","sound","music")]
    if len(sounds)>MAX_MIXED_PCM_EVENTS:
        raise RuntimeError("Too many overlapping sources for audited preview")
    mixed=[0]*requested_samples
    accepted=[]
    omissions=[]
    for event in sounds:
        source=index.read_revision(pid,event["source_id"],event["source_revision"])
        if source["document_sha256"]!=event["source_document_sha256"]:
            raise PermissionError("Indexed audible event source digest differs")
        if source["kind"]!="audio":
            omissions.append({"event_id":event["event_id"],
                              "reason":"NOT_RECORDED_PCM_AUDIO"})
            continue
        audio=RecordedSoundSources(index).describe(
            pid,event["source_id"],event["source_revision"])
        elapsed=source_tick-event["start_tick"]
        if elapsed<0:
            raise RuntimeError("Event reported active before original start")
        # A frame may cross event start/end. Compute the precise active
        # interval and skip silence up to the event's native start.
        offset=min(requested_samples,
                   max(0,(event["start_tick"]-source_tick+
                          TICKS_PER_SAMPLE-1)//TICKS_PER_SAMPLE))
        limit=min(requested_samples,
                  max(0,(event["end_tick"]-source_tick)//
                      TICKS_PER_SAMPLE))
        if limit<=offset:
            continue
        # Source-first-sample is explicit only on WO6-07D added cue; old
        # dialogue/musical stems are anchored at event start with offset 0.
        first=event["payload"].get("source_first_sample",0)
        gain=event["payload"].get("gain",1)
        if (type(first) is not int or first<0 or
                type(gain) not in (int,float) or
                not 0<=gain<=2):
            raise PermissionError("Native source cue has invalid PCM offset or gain")
        now=source_tick+offset*TICKS_PER_SAMPLE
        delta=now-event["start_tick"]
        if delta<0 or delta%TICKS_PER_SAMPLE:
            raise RuntimeError("Exact sound cursor cannot align to native sample")
        at=first+delta//TICKS_PER_SAMPLE
        possible=max(0,audio["data"]["sample_count"]-at)
        count=min(limit-offset,possible)
        if count==0:
            omissions.append({"event_id":event["event_id"],
                              "reason":"RECORDED_PCM_WINDOW_EXHAUSTED"})
            continue
        # Native chunk verification is performed on every read.
        source_stream=bytearray()
        # The immutable original source reader admits at most 8192 samples
        # per call. Audition uses bounded paged 48 kHz reads, not a full
        # soundtrack copied to RAM.
        for begin in range(0,count,8192):
            source_stream.extend(RecordedSoundSources(index).read(
                pid,event["source_id"],event["source_revision"],
                at+begin,min(8192,count-begin)))
        wave_bytes=bytes(source_stream)
        for idx,(sample,) in enumerate(struct.iter_unpack("<h",wave_bytes)):
            mixed[offset+idx]+=round(sample*gain)
        if count<limit-offset:
            omissions.append({"event_id":event["event_id"],
                              "reason":"RECORDED_PCM_END_BEFORE_CUE_END"})
        accepted.append({
            "event_id":event["event_id"],"event_kind":event["event_kind"],
            "source_id":event["source_id"],
            "source_document_sha256":audio["document_sha256"],
            "source_sample_first":at,"sample_count":count,
            "gain":gain,
            "source_pcm_window_sha256":sha256(wave_bytes).hexdigest(),
            "source_audio_verified":True,
        })
    if not accepted:
        return None,[],omissions
    samples=struct.pack(
        "<"+"h"*requested_samples,
        *(max(-32768,min(32767,x)) for x in mixed))
    binary=BytesIO()
    with wave.open(binary,"wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(samples)
    return binary.getvalue(),accepted,omissions


def sample_editorial_source(index,project_id,edit_id,edit_revision,edit_sha,
                            frame_zero,*,sound_timeline_id=None,
                            sound_timeline_revision=None,
                            sound_timeline_sha256=None):
    if not isinstance(index,FilmIndex):
        raise TypeError("Source preview requires existing trusted FilmIndex")
    _require_pid(project_id)
    _id(edit_id,"original editorial cut")
    _sha(edit_sha)
    if (type(edit_revision) is not int or edit_revision<1 or
            type(frame_zero) is not int or
            not 0<=frame_zero<MAX_OUTPUT_FRAME):
        raise ValueError("Exact bounded original edit revision and 24 fps frame required")
    selected=(sound_timeline_id,sound_timeline_revision,sound_timeline_sha256)
    if any(x is None for x in selected) and not all(x is None for x in selected):
        raise ValueError("Exact derived sound timeline ID/revision/SHA must be supplied together")
    if sound_timeline_id is not None:
        _id(sound_timeline_id,"recorded soundtrack timeline")
        _sha(sound_timeline_sha256)
        if type(sound_timeline_revision) is not int or sound_timeline_revision<1:
            raise ValueError("Original sound source requires exact revision")
    slate=DigitalSlateBranches(index,verify_editor_action=lambda *_:False)
    edit=SlateSequenceAssembly(slate,verify_editor_action=lambda *_:False)
    committed=edit.open_edit(project_id,edit_id,edit_revision)
    if committed["kind"]!="edit" or committed["document_sha256"]!=edit_sha or (
            committed["data"].get("format")!=EDIT_FORMAT):
        raise PermissionError("Native slate editorial source SHA mismatch")
    output_tick=tick_from_frame(frame_zero,FPS,1)
    if output_tick>=committed["data"]["duration_tick"]:
        raise ValueError("Requested source frame after end of committed edit")
    projected=edit.source_at(
        project_id,edit_id,edit_revision,timeline_tick=output_tick,
        expected_edit_sha256=edit_sha)
    take=index.read_revision(project_id,projected["source_take_id"],1)
    if take["document_sha256"]!=projected["source_take_sha256"]:
        raise PermissionError("Editorial source Take changed during review")
    source_tick=int(projected["source_tick"])
    packet=assemble_film_crew_context(
        index,project_id,projected["source_take_id"],1,
        source_tick,max_prims=16,max_events=16)
    sound_id=(sound_timeline_id or take["data"]["timeline_id"])
    sound_rev=(sound_timeline_revision or take["data"]["timeline_revision"])
    sound_sha=(sound_timeline_sha256 or
               take["data"]["timeline_document_sha256"])
    source,derived=_verify_derived_audio_timeline(
        index,project_id,take,sound_id,sound_rev,sound_sha)
    if source["data"]["duration_tick"]!=take["data"]["duration_tick"]:
        raise PermissionError("Selected sound timeline differs from exact Take duration")
    # Do not cross an editorial splice and pretend its next Take's audio is
    # already decoded/mixed. The next review frame maps independently.
    clip=next(x for x in committed["data"]["segments"]
              if x["segment_id"]==projected["segment_id"])
    clip_end=clip["timeline_end_tick"]
    requested=min(SOURCE_AUDIO_WINDOW_SAMPLES,
                  (clip_end-output_tick)//TICKS_PER_SAMPLE,
                  (source["data"]["duration_tick"]-source_tick)//TICKS_PER_SAMPLE)
    if requested<1:
        raise RuntimeError("Native edit boundary has no source PCM sample at this frame")
    end=source_tick+requested*TICKS_PER_SAMPLE
    _,active=_sealed_events(
        index,project_id,sound_id,sound_rev,source_tick,end)
    audio,tracks,omissions=_window_pcm(
        index,project_id,active,source_tick,requested)
    # Context asset lists, producer model IDs and actual sound samples are
    # not automatically sent to any external/local model.
    content={
        "format":FORMAT,"project_id":project_id,
        "edit_id":edit_id,"edit_revision":edit_revision,
        "edit_document_sha256":edit_sha,
        "output_frame_zero":frame_zero,"fps_num":FPS,"fps_den":1,
        "output_film_time_tick":str(output_tick),
        "source_film_time_tick":str(source_tick),
        "source_projection":projected,
        "source_take_id":take["object_id"],
        "source_take_sha256":take["document_sha256"],
        "scene_context_sha256":packet["context_sha256"],
        "source_historical_heads_not_current":packet[
            "historical_take_not_current_scene"],
        "scene_poses":[{"prim_path":x["prim_path"],"role":x["role"],
                        "world_translation":x["world_translation"],
                        "native_schema":x.get("native_schema")}
                       for x in packet["visible_scene_prims"]],
        "authored_event_ids":[x["event_id"] for x in packet["active_events"]],
        "source_audio_timeline_id":sound_id,
        "source_audio_timeline_sha256":sound_sha,
        "source_audio_timeline_is_derived":derived,
        "source_pcm_tracks":tracks,
        "source_pcm_omissions":omissions,
        "source_pcm_sample_rate":SAMPLE_RATE,
        "source_pcm_samples":requested if audio is not None else 0,
        "source_pcm_wav_sha256":sha256(audio).hexdigest() if audio else None,
        "audio_data_url":(
            "data:audio/wav;base64,"+base64.b64encode(audio).decode("ascii")
            if audio else None),
        "frame_spans_edit_boundary":requested<SOURCE_AUDIO_WINDOW_SAMPLES,
        "audio_excerpt_max_frames":AUDIO_WINDOW_FRAMES,
        "zero_audio_when_no_source":audio is None,
        "audio_played_by_host":False,
        "audio_muted_until_user_action":True,
        "frame_pixels_rendered":False,
        "screen_image_provided":False,
        "frame_and_audio_continuous_24fps_verified":False,
        "finished_film_mastered_audio":False,
        "independent_director_approval":False,
        "native_worker_authorized":False,
        "effect":"read","original_source_modified":False,
    }
    # Sha over the exact review provenance; do not treat WAV base64 string
    # as a creative permission or a task result.
    content["source_review_sha256"]=sha256(json.dumps(
        {k:v for k,v in content.items() if k!="audio_data_url"},
        sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")).hexdigest()
    if len(json.dumps(content,ensure_ascii=True))>120000:
        raise RuntimeError("Source review exceeded bounded IPC response")
    if index.read_revision(
            project_id,edit_id,edit_revision)["document_sha256"]!=edit_sha:
        raise RuntimeError("Original editorial source changed during review")
    return content
