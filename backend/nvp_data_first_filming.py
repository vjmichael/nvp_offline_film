"""DA-03: DATA-FIRST filmed scene sound producer for frozen Digital Takes.

A trusted recorder supplies immutable mono PCM16LE sample chunks, exact
emitter identity and integer Film Time. This service never accepts a video
file, FFmpeg path, BWF mandate or browser-calculated audio playback timeline.
It combines independently verifiable exact camera observations with source
audio events and freezes one creator-approved Digital Take. On a failure,
staged sound data may remain unreferenced but NO false-approved Take exists.

A real microphone/voice/procedural generator device adapter is still a
separate native capture integration; the caller of this service must be
the trusted, supervised recording host.
"""
from __future__ import annotations

import math
import hashlib
import tempfile
import struct

from backend.nvp_data_av_source import (RecordedSoundSources,SAMPLE_RATE,MAX_CHUNK_BYTES,MAX_CHUNKS)
from backend.nvp_exact_time_shots import ExactTimeShotSequence,MAX_SHOTS
from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture,MAX_CHECKPOINTS
from backend.nvp_temporal_ledger import (
    TemporalLedger,TICKS_PER_SECOND,_int)

FORMAT="nvp.data_av.filming_capture.v1"
SAMPLE_TICK=TICKS_PER_SECOND//SAMPLE_RATE
MAX_AUDIO_EVENTS=32


class NativeSceneSoundCapture:
    def __init__(self,index:FilmIndex,*,approve_take):
        if not isinstance(index,FilmIndex) or not callable(approve_take):
            raise TypeError("Trusted original film index and native approval callback required")
        self.index=index
        self.approve_take=approve_take
        self.sources=RecordedSoundSources(index)
        self.timeline=TemporalLedger(index)
        self.camera=ExactTimeShotSequence(index)
        self.scene=OpenUSDSceneBridge(index)

    def capture(self,project_id,take_id,*,scene_id,scene_revision,
                camera_timeline_id,camera_timeline_revision,
                sound_timeline_id,recordings):
        """Create an approved source-only Take from a trusted recording host.

        recordings: generator-backed list of typed native host dictionaries,
        each with immutable original PCM16LE chunk iterator, speaker/sound
        emitter path, and actual integer Film Time.
        """
        _require_pid(project_id)
        ids=(take_id,scene_id,camera_timeline_id,sound_timeline_id)
        for x in ids:_id(x,"filming capture identity")
        if len(set(ids))!=len(ids):
            raise ValueError("Film Take and sources need distinct identities")
        if type(scene_revision) is not int or scene_revision<=0:
            raise ValueError("Invalid frozen scene revision")
        if type(camera_timeline_revision) is not int or camera_timeline_revision<=0:
            raise ValueError("Invalid original camera timeline revision")
        plan=self.camera.read(project_id,camera_timeline_id,camera_timeline_revision)
        if (plan["scene_id"]!=scene_id or
            plan["scene_revision"]!=scene_revision):
            raise RuntimeError("Camera observations are not bound to filming scene")
        source,stage=self.scene.open(project_id,scene_id,scene_revision)
        if source["document_sha256"]!=plan["scene_document_sha256"]:
            raise RuntimeError("Camera scene identity changed before filming")
        # Refuse occupied output identities before publishing any PCM. A
        # late timeline/Take collision must not orphan fresh source revisions.
        for output_id in (sound_timeline_id,take_id):
            try:
                self.index.read_revision(project_id,output_id,1)
            except KeyError:
                pass
            else:
                raise ValueError("Filming output identity already published")
        if type(recordings) is not list or not 1<=len(recordings)<=MAX_AUDIO_EVENTS:
            raise ValueError("Record a finite, bounded set of original sound events")
        # Preflight identities before writing any immutable PCM revisions.
        # Reusing a source ID would otherwise fail only after an earlier
        # recording had already been published, leaving avoidable orphans.
        source_ids=set()
        event_ids=set()
        prepared_chunks={}
        chunk_digests={}
        spooled=[]
        prepared_entries=[]
        camera_events=self.timeline.events_in(
            project_id,camera_timeline_id,camera_timeline_revision,
            start_tick=0,end_tick=int(plan["duration_tick"]),limit=MAX_SHOTS+1)
        if camera_events["next_cursor"] is not None:
            raise RuntimeError("Partial camera observation history cannot be filmed")
        camera_ids={ev["event_id"] for ev in camera_events["events"]}
        duration=int(plan["duration_tick"])
        try:
            for entry in recordings:
                if type(entry) is not dict or set(entry)!={
                    "event_id","event_kind","subject_id","source_id",
                    "usd_prim_path","start_tick","end_tick","gain","pcm_chunks"
                }:
                    raise ValueError("Recorded sound requires typed source/evidence/Film Time")
                eid=_id(entry["event_id"],"recorded sound event")
                sid=_id(entry["source_id"],"original audio source")
                if (eid==sid or eid in event_ids or eid in camera_ids or eid in ids or
                    sid in source_ids or sid in ids or sid in camera_ids or
                    sid in event_ids or eid in source_ids):
                    raise ValueError("Duplicate or reserved recording identity")
                if entry["event_kind"] not in ("sound","dialogue"):
                    raise ValueError("Captured audio must be a sound or dialogue event")
                _id(entry["subject_id"],"sound source subject")
                if entry["usd_prim_path"] not in source["data"]["prim_roles"]:
                    raise RuntimeError("Sound emitter is not part of original 3D scene")
                start=_int(entry["start_tick"],"captured sound start")
                end=_int(entry["end_tick"],"captured sound end",minimum=1)
                gain=entry["gain"]
                if (end<=start or end>duration or
                    type(gain) not in (int,float) or not math.isfinite(gain) or
                    not 0<=gain<=2):
                    raise ValueError("Captured sound has invalid timing/gain")
                # An existing immutable source ID cannot be republished at revision 1.
                # Check all IDs before writing any new source in this batch.
                try:
                    self.index.read_revision(project_id,sid,1)
                except KeyError:
                    pass
                else:
                    raise ValueError("Original audio source identity already published")
                # Spool even one-shot streaming iterators before publishing ANY
                # immutable source. A later truncated iterator must not leave
                # earlier source revisions behind. Disk spill keeps RAM bounded.
                chunks=entry["pcm_chunks"]
                spool=tempfile.SpooledTemporaryFile(max_size=MAX_CHUNK_BYTES,mode="w+b")
                spooled.append(spool)
                samples=0
                count=0
                digests=[]
                for chunk in chunks:
                    if (type(chunk) is not bytes or
                        not 0<len(chunk)<=MAX_CHUNK_BYTES or len(chunk)%2 or
                        count>=MAX_CHUNKS):
                        raise ValueError("Invalid captured PCM16LE chunk")
                    # A short write (including a full disk or interrupted
                    # temporary backing store) is not a validated recording.
                    # Refuse the entire batch before publishing source data.
                    header=struct.pack("<I",len(chunk))
                    if spool.write(header)!=len(header) or spool.write(chunk)!=len(chunk):
                        raise OSError("Incomplete captured PCM spool write")
                    digests.append(hashlib.sha256(chunk).digest())
                    samples+=len(chunk)//2
                    count+=1
                required=(end-start+SAMPLE_TICK-1)//SAMPLE_TICK
                if not count or samples<required:
                    raise ValueError("Captured PCM is shorter than its Film Time event")
                spool.seek(0)
                prepared_chunks[sid]=spool
                chunk_digests[sid]=tuple(digests)
                # Freeze validated metadata as well as materialized PCM. A native
                # callback must not be able to rewrite a later event mid-batch.
                frozen=dict(entry)
                frozen["pcm_chunks"]=prepared_chunks[sid]
                prepared_entries.append(frozen)
                event_ids.add(eid)
                source_ids.add(sid)
            def replay(spool,expected_digests):
                spool.seek(0)
                chunk_index=0
                while True:
                    size=spool.read(4)
                    if not size:
                        if chunk_index!=len(expected_digests):
                            raise RuntimeError("Captured PCM spool chunk count changed")
                        return
                    if len(size)!=4:
                        raise RuntimeError("Damaged captured PCM spool header")
                    n=struct.unpack("<I",size)[0]
                    if not 0<n<=MAX_CHUNK_BYTES or n%2:
                        raise RuntimeError("Damaged captured PCM spool size")
                    chunk=spool.read(n)
                    if len(chunk)!=n:
                        raise RuntimeError("Truncated captured PCM spool")
                    if (chunk_index>=len(expected_digests) or
                        hashlib.sha256(chunk).digest()!=expected_digests[chunk_index]):
                        raise RuntimeError("Captured PCM spool changed after validation")
                    chunk_index+=1
                    yield chunk
            # Verify every completed spool before publishing the first source.
            # A damaged later spool must not orphan an earlier immutable PCM
            # revision. Replay still rechecks digests at publication time.
            for entry in prepared_entries:
                sid=entry["source_id"]
                for _ in replay(prepared_chunks[sid],chunk_digests[sid]):
                    pass
            events=[]
            seen=set(ev["event_id"] for ev in camera_events["events"])
            for ev in camera_events["events"]:
                events.append({"event_id":ev["event_id"],
                               "event_kind":"camera",
                               "subject_id":ev["subject_id"],
                               "start_tick":ev["start_tick"],
                               "end_tick":ev["end_tick"],
                               "source_id":ev["source_id"],
                               "source_revision":ev["source_revision"],
                               "payload":ev["payload"]})
            # Original mono source signal is stored independently, not a room mix.
            # Exact per-emitter timing and the scene geometry remain authoritative.
            for entry in prepared_entries:
                eid=_id(entry["event_id"],"recorded sound event")
                if eid in seen:
                    raise ValueError("Collision with a camera or sound event")
                seen.add(eid)
                if entry["event_kind"] not in ("sound","dialogue"):
                    raise ValueError("Captured audio must be a sound or dialogue event")
                _id(entry["subject_id"],"sound source subject")
                audio_id=_id(entry["source_id"],"original audio source")
                if audio_id in ids:
                    raise ValueError("Sound may not replace the scene, timeline or Take")
                path=entry["usd_prim_path"]
                if path not in source["data"]["prim_roles"]:
                    raise RuntimeError("Sound emitter is not part of original 3D scene")
                start=_int(entry["start_tick"],"captured sound start")
                end=_int(entry["end_tick"],"captured sound end",minimum=1)
                gain=entry["gain"]
                if (end<=start or end>duration or
                    type(gain) not in (int,float) or not math.isfinite(gain) or
                    not 0<=gain<=2):
                    raise ValueError("Captured sound has invalid timing/gain")
                receipt=self.sources.publish(
                    project_id,audio_id,replay(prepared_chunks[audio_id],chunk_digests[audio_id]),expected_revision=0)
                source_record=self.index.read_revision(
                    project_id,audio_id,receipt["revision"])
                available=source_record["data"]["sample_count"]
                required=(end-start+SAMPLE_TICK-1)//SAMPLE_TICK
                if available<required:
                    raise RuntimeError("Actual recorded source contains fewer samples than its event")
                events.append({
                    "event_id":eid,
                    "event_kind":entry["event_kind"],
                    "subject_id":entry["subject_id"],
                    "start_tick":start,"end_tick":end,
                    "source_id":audio_id,
                    "source_revision":receipt["revision"],
                    "payload":{"format":FORMAT,
                               "usd_prim_path":path,
                               "gain":float(gain),
                               "source_sample_rate":SAMPLE_RATE,
                               "original_recording":True,
                               "acoustic_mix_frozen":False}})
            combined=self.timeline.publish(
                project_id,sound_timeline_id,events,
                duration_tick=duration,expected_revision=0)
            timestamps={0}
            for item in events:
                if item["start_tick"]<duration:
                    timestamps.add(item["start_tick"])
                if item["end_tick"]<duration:
                    timestamps.add(item["end_tick"])
            checkpoints=sorted(timestamps)[:MAX_CHECKPOINTS]
            def approve(event,scope):
                if (scope.get("operation")!="nvp.freeze.usd_temporal_take.v1" or
                    scope.get("scene_document_sha256")!=source["document_sha256"] or
                    scope.get("timeline_document_sha256")!=
                        combined["document_sha256"] or
                    scope.get("take_id")!=take_id):
                    return False
                return self.approve_take(event,scope) is True
            take=OpenUSDTakeCapture(
                self.index,verify_creator_action=approve).freeze(
                    project_id,take_id,
                    scene_id=scene_id,scene_revision=scene_revision,
                    timeline_id=sound_timeline_id,
                    timeline_revision=1,sample_ticks=checkpoints,
                    creator_event={"kind":"trusted_native_filming_host",
                                   "source_scene_sha256":source["document_sha256"],
                                   "event_manifest_sha256":combined["document_sha256"]})
            return {
                "format":FORMAT,"status":"FROZEN_ORIGINAL_SCENE_SOUND_TAKE",
                "take_id":take_id,
                "take_document_sha256":take["document_sha256"],
                "timeline_document_sha256":combined["document_sha256"],
                "camera_timeline_document_sha256":plan["document_sha256"],
                "original_sound_count":len(prepared_entries),
                "duration_tick":str(duration),
                "original_scene_modified":False,
                "original_sound_modified":False,
                "audio_mix_flattened":False,
                "picture_frames_generated":False,
                "master_approved":False,
            }
    
        finally:
            for spool in spooled:
                spool.close()