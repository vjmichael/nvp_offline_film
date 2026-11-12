"""W1-D: native microphone -> durably staged, bounded original PCM chunks.

Ordinary (non-encrypted) film projects only. One device callback never writes
SQLite: it queues bounded PCM; a dedicated writer commits five-second pieces.
A stopped stream is NOT an original until a separate, human-requested finish
atomically verifies all pieces and publishes legacy immutable G06 original
clips plus their exact contiguous group manifest.

An interrupted process leaves journaled, non-publishable pieces. It cannot
automatically create a Take, original sound or a completed recording on reboot.
"""
from __future__ import annotations

import array
from contextlib import closing
import hashlib
import json
from pathlib import Path
import queue
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import uuid

from backend.nvp_g06_native_recorder import NativeMicrophoneSession
from backend.nvp_g06_filming import RATE, MAX_SECONDS, _now, _stage, _sha
from backend.nvp_g09c_capture import G09CCaptureJournal

CHUNK_SAMPLES = RATE * 5
SOURCE_SAMPLES = RATE * MAX_SECONDS   # current G06 scene limit: 30 minutes
MAX_CALLBACK_SAMPLES = RATE           # reject unexpected >1s callback
QUEUE_LIMIT = 32                     # never hold an unbounded recording in RAM
MAX_PIECES = (SOURCE_SAMPLES + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES
MIN_DISK_HEADROOM=128*1024*1024
FORMAT = "nvp.g06.chunked_microphone_original.v1"


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False)


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g06_long_capture_sessions(
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,scene_id TEXT NOT NULL,actor_id TEXT,
        stage_sha256 TEXT NOT NULL,
        status TEXT NOT NULL,committed_samples INTEGER NOT NULL DEFAULT 0,
        committed_chunks INTEGER NOT NULL DEFAULT 0,
        original_recording_id TEXT,original_sha256 TEXT,
        started_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        CHECK(status IN ('recording','stopped','completed','interrupted',
                         'cancelled','failed')))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g06_long_capture_chunks(
        session_id TEXT NOT NULL,project_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,start_sample INTEGER NOT NULL,
        sample_count INTEGER NOT NULL,pcm BLOB NOT NULL,
        pcm_sha256 TEXT NOT NULL,
        PRIMARY KEY(session_id,chunk_index),
        CHECK(sample_count>0))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g06_long_recording_manifests(
        recording_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
        scene_id TEXT NOT NULL,actor_id TEXT,session_id TEXT NOT NULL,
        sample_count INTEGER NOT NULL,original_sha256 TEXT NOT NULL,
        segments_json TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,
        recorded_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS g06_long_recording_members(
        clip_id TEXT PRIMARY KEY,recording_id TEXT NOT NULL,
        project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
        first_sample INTEGER NOT NULL,sample_count INTEGER NOT NULL,
        pcm_sha256 TEXT NOT NULL)""")
    db.execute("""CREATE INDEX IF NOT EXISTS g06_long_capture_scene
        ON g06_long_capture_sessions(project_id,scene_id,updated_at)""")
    db.execute("""CREATE INDEX IF NOT EXISTS g06_long_recording_scene
        ON g06_long_recording_manifests(project_id,scene_id,recorded_at)""")


def recording_member(db,pid,scene_id,clip_id):
    """Verify original segment's membership in a complete frozen stream.

    The manifest is the signed-by-hash source mapping, not a changeable EDL.
    Missing rows mean an ordinary legacy short microphone source. A mismatched
    group/member is always a source-integrity failure.
    """
    # Historic ordinary Takes must remain read-only when no long recorder
    # has ever created its tables. Do not migrate source storage on read.
    if not db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
        AND name='g06_long_recording_members'""").fetchone():
        return None
    part=db.execute("""SELECT * FROM g06_long_recording_members
        WHERE clip_id=? AND project_id=? AND scene_id=?""",
        (clip_id,pid,scene_id)).fetchone()
    if part is None:
        return None
    manifest=db.execute("""SELECT * FROM g06_long_recording_manifests
        WHERE recording_id=? AND project_id=? AND scene_id=?""",
        (part["recording_id"],pid,scene_id)).fetchone()
    if manifest is None:
        raise RuntimeError("Original microphone stream manifest is missing")
    raw=manifest["segments_json"]
    if _sha(raw.encode("utf8"))!=manifest["manifest_sha256"]:
        raise RuntimeError("Frozen microphone source manifest changed")
    document=json.loads(raw)
    if (document.get("format")!=FORMAT or
        document.get("original_pcm_sha256")!=manifest["original_sha256"] or
        document.get("recording_id")!=part["recording_id"] or
        document.get("project_id")!=pid or
        document.get("scene_id")!=scene_id or
        document.get("sample_count")!=manifest["sample_count"]):
        raise RuntimeError("Original microphone stream provenance changed")
    segments=document["segments"]
    if not isinstance(segments,list) or not 1<=len(segments)<=32:
        raise RuntimeError("Original stream segment manifest is invalid")
    cursor=0
    found=False
    for segment in segments:
        if (segment["first_sample"]!=cursor or
            type(segment["sample_count"]) is not int or
            segment["sample_count"]<1 or
            segment["sample_count"]>RATE*120):
            raise RuntimeError("Original audio segments lost their sample order")
        cursor+=segment["sample_count"]
        origin=db.execute("""SELECT m.recording_id,m.first_sample,
            m.sample_count,m.pcm_sha256,o.pcm_sha256 AS source_sha256,
            o.sample_count AS original_samples,length(o.pcm) AS byte_count,
            o.project_id,o.scene_id,o.actor_id
            FROM g06_long_recording_members AS m
            JOIN g06_original_pcm AS o ON o.id=m.clip_id
            WHERE m.clip_id=? AND m.project_id=? AND m.scene_id=?""",
            (segment["clip_id"],pid,scene_id)).fetchone()
        if (origin is None or origin["recording_id"]!=part["recording_id"] or
            origin["first_sample"]!=segment["first_sample"] or
            origin["sample_count"]!=segment["sample_count"] or
            origin["original_samples"]!=segment["sample_count"] or
            origin["pcm_sha256"]!=segment["pcm_sha256"] or
            origin["source_sha256"]!=segment["pcm_sha256"] or
            origin["byte_count"]!=segment["sample_count"]*2 or
            origin["project_id"]!=pid or origin["scene_id"]!=scene_id or
            origin["actor_id"]!=manifest["actor_id"]):
            raise RuntimeError("A stream segment source or mapping changed")
        if segment["clip_id"]==clip_id:
            if (found or segment["pcm_sha256"]!=part["pcm_sha256"] or
                segment["sample_count"]!=part["sample_count"] or
                segment["first_sample"]!=part["first_sample"]):
                raise RuntimeError("Original microphone segment identity changed")
            found=True
    if not found or cursor!=manifest["sample_count"]:
        raise RuntimeError("Original audio stream is incomplete")
    return {"original_recording_id":part["recording_id"],
            "recording_sha256":manifest["original_sha256"],
            "recording_manifest_sha256":manifest["manifest_sha256"],
            "recording_source_start_sample":part["first_sample"]}


class DurableOriginalChunkStore:
    """Single project-scoped source recorder. Never writes decoded PCM files."""

    def __init__(self, studio, session_id, project_id, scene_id, actor_id,
                 stage_sha256):
        db_path=Path(studio.db_path)
        if not db_path.is_file() or db_path.is_symlink():
            raise RuntimeError("The ordinary project source database is unavailable")
        self.db_path=db_path.resolve(strict=True)
        self.session_id=session_id
        self.project_id=project_id
        self.scene_id=scene_id
        self.actor_id=actor_id
        self.stage_sha256=stage_sha256
        self.q=queue.Queue(maxsize=QUEUE_LIMIT)
        self.thread=None
        self.error=None
        self.total_samples=0
        self.digest=hashlib.sha256()
        self.final_sha256=None
        self._ended=False
        self._lock=threading.RLock()

    def _db(self):
        db=sqlite3.connect(self.db_path,timeout=20)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def begin(self):
        if shutil.disk_usage(self.db_path.parent).free<MIN_DISK_HEADROOM:
            raise RuntimeError("Not enough free storage to record original sound")
        with closing(self._db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _schema(db)
            db.execute("""INSERT INTO g06_long_capture_sessions(
              session_id,project_id,scene_id,actor_id,stage_sha256,
              status,started_at,updated_at)
              VALUES (?,?,?,?,?,'recording',?,?)""",
              (self.session_id,self.project_id,self.scene_id,self.actor_id,
               self.stage_sha256,_now(),_now()))
        self.thread=threading.Thread(target=self._write_loop,
            daemon=True,name="nvp-native-pcm-"+self.session_id[:8])
        self.thread.start()

    def push(self, raw):
        if not raw or len(raw)%2 or len(raw)>MAX_CALLBACK_SAMPLES*2:
            raise RuntimeError("Native callback sample count exceeds its bound")
        with self._lock:
            if self.error or self._ended:
                raise RuntimeError("The native recording spool is unavailable")
            if self.total_samples+len(raw)//2>SOURCE_SAMPLES:
                raise RuntimeError("This scene has reached its 30-minute source limit")
            self.q.put_nowait(raw)
            self.total_samples+=len(raw)//2
            self.digest.update(raw)

    def _commit_chunk(self, db, data, index, first):
        if (not 0<len(data)<=CHUNK_SAMPLES*2 or len(data)%2 or
            index>=MAX_PIECES or first+len(data)//2>SOURCE_SAMPLES):
            raise RuntimeError("Original microphone chunk exceeds admission")
        if shutil.disk_usage(self.db_path.parent).free<MIN_DISK_HEADROOM:
            raise RuntimeError("Original sound spool ran out of safe disk headroom")
        with db:
            record=db.execute("""SELECT status,committed_samples,committed_chunks
              FROM g06_long_capture_sessions WHERE project_id=? AND
              scene_id=? AND session_id=?""",
              (self.project_id,self.scene_id,self.session_id)).fetchone()
            if (record is None or record["status"]!="recording" or
                record["committed_samples"]!=first or
                record["committed_chunks"]!=index):
                raise RuntimeError("A native source chunk was already published or reordered")
            db.execute("""INSERT INTO g06_long_capture_chunks(
                session_id,project_id,chunk_index,start_sample,sample_count,
                pcm,pcm_sha256) VALUES(?,?,?,?,?,?,?)""",
                (self.session_id,self.project_id,index,first,len(data)//2,
                 data,_sha(data)))
            db.execute("""UPDATE g06_long_capture_sessions SET
              committed_samples=?,committed_chunks=?,updated_at=?
              WHERE project_id=? AND session_id=? AND status='recording'""",
              (first+len(data)//2,index+1,_now(),self.project_id,self.session_id))

    def _write_loop(self):
        try:
            db=self._db()
            try:
                pending=bytearray()
                first=index=0
                while True:
                    item=self.q.get()
                    if item is None:
                        if pending:
                            self._commit_chunk(db,bytes(pending),index,first)
                            first+=len(pending)//2
                            index+=1
                        break
                    pending.extend(item)
                    while len(pending)>=CHUNK_SAMPLES*2:
                        chunk=bytes(pending[:CHUNK_SAMPLES*2])
                        self._commit_chunk(db,chunk,index,first)
                        del pending[:CHUNK_SAMPLES*2]
                        first+=CHUNK_SAMPLES
                        index+=1
            finally:
                db.close()
        except Exception as error:
            with self._lock:
                self.error=error

    def finish_spooling(self, *,expected_samples):
        with self._lock:
            if self._ended:
                raise RuntimeError("The native recording spool was already finalized")
            self._ended=True
            self.final_sha256=self.digest.hexdigest()
            if expected_samples!=self.total_samples:
                raise RuntimeError("Microphone callback and spool lengths disagree")
        self.q.put(None,timeout=10)
        self.thread.join(timeout=30)
        if self.thread.is_alive() or self.error:
            raise RuntimeError("Original microphone chunks were not durably committed")
        with closing(self._db()) as db, db:
            row=db.execute("""SELECT committed_samples,committed_chunks,status
                FROM g06_long_capture_sessions
                WHERE project_id=? AND session_id=?""",
                (self.project_id,self.session_id)).fetchone()
            if (row is None or row["status"]!="recording" or
                row["committed_samples"]!=self.total_samples or
                not 1<=row["committed_chunks"]<=MAX_PIECES):
                raise RuntimeError("The durable audio spool is incomplete")
            with db:
                db.execute("""UPDATE g06_long_capture_sessions
                    SET status='stopped',updated_at=?
                    WHERE project_id=? AND session_id=? AND status='recording'""",
                    (_now(),self.project_id,self.session_id))
        return {"sample_count":self.total_samples,
                "original_pcm_sha256":self.final_sha256}

    def discard(self):
        # Cancellation is deliberate: no staged clip may later become original.
        if self.thread is not None and self.thread.is_alive():
            try:self.q.put(None,timeout=10)
            except queue.Full:pass
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                raise RuntimeError("Recording writer could not be stopped safely")
        with closing(self._db()) as db, db:
            _schema(db)
            with db:
                db.execute("""UPDATE g06_long_capture_sessions SET
                    status='cancelled',updated_at=?
                    WHERE project_id=? AND session_id=? AND status IN
                    ('recording','stopped','failed')""",
                    (_now(),self.project_id,self.session_id))
                db.execute("""DELETE FROM g06_long_capture_chunks
                    WHERE project_id=? AND session_id=? AND EXISTS(
                    SELECT 1 FROM g06_long_capture_sessions
                    WHERE project_id=? AND session_id=? AND status='cancelled')""",
                    (self.project_id,self.session_id,self.project_id,
                     self.session_id))

    def publish(self,filming,receipt):
        """One host writer transaction publishes ordinary clips AND manifest.

        No original audio is published from interrupted/cancelled sources.
        """
        pid=self.project_id;sid=self.scene_id
        if not self._ended or self.error or not self.final_sha256:
            raise RuntimeError("Native original recording did not finish")
        if (receipt.get("original_pcm_sha256")!=self.final_sha256 or
            receipt.get("sample_count")!=self.total_samples):
            raise RuntimeError("Microphone sample evidence changed after recording")

        def commit(db,movie,source):
            _schema(db)
            head,stage,plan,_raw=_stage(db,source,pid,sid)
            if stage["usd_sha256"]!=self.stage_sha256:
                raise RuntimeError("Original stage was revised while recording")
            approved_actors={obj["actor_id"] for obj in plan["objects"]
                             if obj["role"]=="actor"}
            if self.actor_id is not None and self.actor_id not in approved_actors:
                raise RuntimeError("Original speaker is no longer in this scene")
            session=db.execute("""SELECT status,committed_samples,committed_chunks,
                stage_sha256 FROM g06_long_capture_sessions
                WHERE project_id=? AND scene_id=? AND session_id=?""",
                (pid,sid,self.session_id)).fetchone()
            if (session is None or session["status"]!="stopped" or
                session["stage_sha256"]!=self.stage_sha256 or
                session["committed_samples"]!=self.total_samples or
                session["committed_chunks"]>MAX_PIECES):
                raise RuntimeError("Recording was interrupted or cannot be published")
            chunks=db.execute("""SELECT chunk_index,start_sample,sample_count,
                pcm,pcm_sha256 FROM g06_long_capture_chunks WHERE
                session_id=? AND project_id=? ORDER BY chunk_index""",
                (self.session_id,pid))
            all_hash=hashlib.sha256()
            segments=[]
            batch=bytearray()
            first_sample=0
            cursor=0
            piece_count=0
            recorded=_now()
            group_id=self.session_id
            for row in chunks:
                if (row["chunk_index"]!=piece_count or
                    row["start_sample"]!=cursor or
                    row["sample_count"]<1 or
                    row["sample_count"]>CHUNK_SAMPLES or
                    len(row["pcm"])!=row["sample_count"]*2 or
                    _sha(row["pcm"])!=row["pcm_sha256"]):
                    raise RuntimeError("Durably recorded microphone chunk changed")
                raw=bytes(row["pcm"])
                all_hash.update(raw)
                batch.extend(raw)
                cursor+=row["sample_count"]
                piece_count+=1
                # Existing native Take source has a maximum 120s PCM clip.
                # Preserve same source samples, publish bounded ordered clips.
                if len(batch)>=RATE*2*120 or cursor==self.total_samples:
                    clip_id=uuid.uuid4().hex
                    pcm=bytes(batch)
                    digest=_sha(pcm)
                    db.execute("""INSERT INTO g06_original_pcm(
                        id,project_id,scene_id,actor_id,source_kind,pcm,
                        pcm_sha256,sample_rate,channels,sample_count,recorded_at)
                        VALUES(?,?,?,?,'native_microphone_pcm16le',?,?,?,?,?)""",
                        (clip_id,pid,sid,self.actor_id,pcm,digest,RATE,1,
                         len(pcm)//2,recorded))
                    db.execute("""INSERT INTO g06_long_recording_members(
                        clip_id,recording_id,project_id,scene_id,
                        first_sample,sample_count,pcm_sha256)
                        VALUES(?,?,?,?,?,?,?)""",
                        (clip_id,group_id,pid,sid,first_sample,
                         len(pcm)//2,digest))
                    segments.append({"clip_id":clip_id,
                        "first_sample":first_sample,"sample_count":len(pcm)//2,
                        "pcm_sha256":digest})
                    first_sample+=len(pcm)//2
                    batch.clear()
            if (piece_count!=session["committed_chunks"] or
                cursor!=self.total_samples or
                all_hash.hexdigest()!=self.final_sha256 or
                first_sample!=cursor or not segments or len(segments)>32):
                raise RuntimeError("Original recording is not complete and ordered")
            manifest={"format":FORMAT,"recording_id":group_id,
                "project_id":pid,"scene_id":sid,"actor_id":self.actor_id,
                "sample_rate":RATE,"channels":1,"sample_count":cursor,
                "original_pcm_sha256":self.final_sha256,
                "segments":segments}
            canonical=_json(manifest)
            db.execute("""INSERT INTO g06_long_recording_manifests(
                recording_id,project_id,scene_id,actor_id,session_id,
                sample_count,original_sha256,segments_json,manifest_sha256,
                recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (group_id,pid,sid,self.actor_id,self.session_id,cursor,
                 self.final_sha256,canonical,_sha(canonical.encode("utf8")),
                 recorded))
            G09CCaptureJournal.seal(db,pid,sid,group_id,receipt)
            # The same SQLite commit publishes the immutable originals and
            # removes the provisional five-second staging copies. A crash
            # cannot leave originals published without their manifest.
            db.execute("""DELETE FROM g06_long_capture_chunks
                WHERE project_id=? AND session_id=?""",(pid,self.session_id))
            db.execute("""UPDATE g06_long_capture_sessions SET
                status='completed',original_recording_id=?,original_sha256=?,
                updated_at=? WHERE project_id=? AND session_id=?
                AND status='stopped'""",
                (group_id,self.final_sha256,_now(),pid,self.session_id))
            return {"recording_id":group_id,"clip_ids":[x["clip_id"] for x in segments],
                "segments":segments,"sample_count":cursor,
                "duration_seconds":cursor/RATE,
                "original_pcm_sha256":self.final_sha256,
                "manifest_sha256":_sha(canonical.encode("utf8")),
                "recorded_from_native_microphone":True,
                "original_source_unchanged":True}
        return filming._with(pid,sid,commit,mutate=True)


class NativeLongMicrophoneSession(NativeMicrophoneSession):
    def __init__(self,project_id,scene_id,actor_id,*,session_grant,
                 studio,stage_sha256,device_factory=None,filming=None):
        super().__init__(project_id,scene_id,actor_id,
                         session_grant=session_grant,device_factory=device_factory)
        if filming is not None and filming.g05.g04.live is not None:
            from backend.nvp_g06_sealed_capture import SealedOriginalChunkStore
            self.store=SealedOriginalChunkStore(
                filming,self.id,project_id,scene_id,actor_id,stage_sha256)
        else:
            self.store=DurableOriginalChunkStore(
                studio,self.id,project_id,scene_id,actor_id,stage_sha256)
        self.is_long=True
        self.stream_sha256=None

    def _callback(self):
        samples=yield
        while True:
            with self.lock:
                if self.status=="recording" and self.error is None:
                    try:
                        if type(samples) is not array.array or samples.typecode!="h":
                            raise RuntimeError("Native microphone returned invalid samples")
                        if samples:
                            raw=samples.tobytes()
                            if sys.byteorder!="little":
                                copy=array.array("h",samples)
                                copy.byteswap()
                                raw=copy.tobytes()
                            self.store.push(raw)
                            now=time.monotonic_ns()
                            if self.first_callback_ns is None:
                                self.first_callback_ns=now
                            elif self.last_callback_ns is not None:
                                gap=now-self.last_callback_ns
                                self.largest_gap_ns.append(gap)
                                self.largest_gap_ns=sorted(
                                    self.largest_gap_ns,reverse=True)[:30]
                            self.last_callback_ns=now
                            self.chunks+=1
                            self.peak_abs=max(self.peak_abs,max(abs(v) for v in samples))
                            self.bytes+=len(raw)
                            self.frames+=len(samples)
                    except Exception as error:
                        self.error=error
            samples=yield

    def begin(self):
        self.store.begin()
        try:
            result=super().begin()
        except Exception:
            self.store.discard()
            raise
        return {**result,"max_duration_seconds":MAX_SECONDS,
                "durably_chunked":True,
                "sample_clock":"native_48000_pcm_samples",
                "source_published":False}

    def stop(self):
        with self.lock:
            if self.status!="recording":
                raise RuntimeError("No active original microphone session")
            self.status="stopping"
            device=self.device
            self.status="recording"
        try:
            device.stop()
            device.close()
        except Exception as error:
            with self.lock:
                self.status="failed"
                self.error=RuntimeError("Native microphone stop was not verified")
            raise RuntimeError("Original microphone stop failed") from error
        with self.lock:
            self.status="stopped"
            self.stopped_ns=time.monotonic_ns()
            self.device=None
            if self.error or self.frames<1 or self.bytes!=self.frames*2:
                raise RuntimeError("Native source callback failed; no original can publish")
        result=self.store.finish_spooling(expected_samples=self.frames)
        self.stream_sha256=result["original_pcm_sha256"]
        return result

    def cancel(self):
        with self.lock:
            if self.status in ("cancelled","finished"):
                return
            device=self.device
            self.status="cancelling"
        if device is not None:
            try:
                device.stop()
                device.close()
            except Exception as exc:
                with self.lock:
                    self.status="failed"
                    self.error=exc
                raise RuntimeError("Original recording device needs shutdown review") from exc
        self.store.discard()
        with self.lock:
            self.device=None
            self.status="cancelled"
            self.parts.clear()
            self.bytes=0
            self.frames=0


def discard_interrupted_capture(filming,pid,scene_id,session_id):
    """Explicit director removal of abandoned non-source microphone chunks.

    Never deletes a completed original, original clip, frozen Take or scene.
    A human must first inspect interrupted status and explicitly choose discard.
    """
    from backend.nvp_g06_filming import HEX
    if not isinstance(session_id,str) or not HEX.fullmatch(session_id):
        raise ValueError("Choose an interrupted original microphone session")
    if filming.g05.g04.live is not None:
        raise PermissionError("Protected original source requires sealed custody")
    def discard(db,movie,source):
        _schema(db)
        row=db.execute("""SELECT status,committed_samples FROM
            g06_long_capture_sessions WHERE project_id=? AND scene_id=?
            AND session_id=?""",(pid,scene_id,session_id)).fetchone()
        if row is None:
            raise KeyError("The recording is not in this scene")
        if row["status"] not in ("interrupted","failed","cancelled"):
            raise RuntimeError("Only an interrupted, non-original recording can be discarded")
        if db.execute("""SELECT 1 FROM g06_long_recording_manifests
            WHERE project_id=? AND scene_id=? AND session_id=?""",
            (pid,scene_id,session_id)).fetchone():
            raise RuntimeError("A completed original recording may never be discarded as a spool")
        db.execute("""DELETE FROM g06_long_capture_chunks WHERE
            project_id=? AND session_id=?""",(pid,session_id))
        db.execute("""UPDATE g06_long_capture_sessions SET
            status='cancelled',committed_chunks=0,updated_at=?
            WHERE project_id=? AND session_id=? AND status IN
            ('interrupted','failed','cancelled')""",
            (_now(),pid,session_id))
        db.execute("""UPDATE g09c_capture_sessions SET
            state='cancelled',updated_at=?
            WHERE project_id=? AND scene_id=? AND session_id=?
            AND state IN ('interrupted','failed','cancelled')""",
            (_now(),pid,scene_id,session_id))
        return {"session_id":session_id,"status":"cancelled",
                "original_published":False,
                "only_unpublished_staged_chunks_discarded":True}
    return filming._with(pid,scene_id,discard,mutate=True)


def long_capture_health(db,pid,scene_id,active_ids=()):
    """Conservative restart: past active streams become interrupted, not source."""
    _schema(db)
    active=set(active_ids)
    if len(active)>64:
        raise ValueError("Too many active microphone sessions")
    rows=list(db.execute("""SELECT * FROM g06_long_capture_sessions
        WHERE project_id=? AND scene_id=?
        ORDER BY updated_at DESC LIMIT 50""",(pid,scene_id)))
    interrupted=[r["session_id"] for r in rows
                 if r["status"] in ("recording","stopped")
                 and r["session_id"] not in active]
    for identifier in interrupted:
        db.execute("""UPDATE g06_long_capture_sessions SET
          status='interrupted',updated_at=?
          WHERE project_id=? AND session_id=? AND status IN
          ('recording','stopped')""",(_now(),pid,identifier))
    if interrupted:
        rows=list(db.execute("""SELECT * FROM g06_long_capture_sessions
            WHERE project_id=? AND scene_id=?
            ORDER BY updated_at DESC LIMIT 50""",(pid,scene_id)))
    return [{"session_id":row["session_id"],
             "actor_id":row["actor_id"],"status":row["status"],
             "committed_samples":row["committed_samples"],
             "sample_count":row["committed_samples"]
                if row["status"]=="completed" else None,
             "original_recording_id":row["original_recording_id"],
             "durable_chunks":0 if row["status"]=="completed"
                 else row["committed_chunks"],
             "recorded_chunk_count":row["committed_chunks"],
             "source_published":row["status"]=="completed",
             "requires_human_review":row["status"]=="interrupted"}
            for row in rows]
