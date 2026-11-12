"""W1-E protected continuous original microphone custody for G03 live films.

The native device provides actual PCM16LE. A bounded writer puts each 5-second
chunk through LiveFilmStore.put_original(), which authenticates ciphertext
before publishing a sealed SQLite source-index revision. No original microphone
PCM or database pages are ever written to plaintext staging files.

A complete recording is published only by a separate host-controlled
transaction that checks every sealed chunk and its exact sample position. The
authoritative original is the ordered sequence of AES-GCM sealed assets. G06
original PCM rows contain deliberately EMPTY BLOB placeholders (never sources)
and are usable only through VerifiedSealedPCM with a valid unlocked grant.
"""
from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
import uuid

from backend.nvp_g06_filming import RATE,_now,_sha,_stage
from backend.nvp_g06_chunked_capture import (
    CHUNK_SAMPLES,MAX_CALLBACK_SAMPLES,MAX_PIECES,QUEUE_LIMIT,SOURCE_SAMPLES,
    FORMAT as RECORDING_FORMAT,_json,_schema as source_schema)
from backend.nvp_g09c_capture import G09CCaptureJournal

FORMAT="nvp.w1e.sealed_original_chunks.v1"
MEDIA_TYPE="audio/x-nvp-original-pcm16le"
MAX_CHUNK_BYTES=CHUNK_SAMPLES*2


def _schema(db):
    source_schema(db)
    db.execute("""CREATE TABLE IF NOT EXISTS w1e_capture_chunks(
        project_id TEXT NOT NULL,session_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,start_sample INTEGER NOT NULL,
        sample_count INTEGER NOT NULL,asset_name TEXT NOT NULL,
        pcm_sha256 TEXT NOT NULL,
        PRIMARY KEY(project_id,session_id,chunk_index),
        UNIQUE(project_id,asset_name))""")
    db.execute("""CREATE TABLE IF NOT EXISTS w1e_sealed_clip_members(
        clip_id TEXT PRIMARY KEY,recording_id TEXT NOT NULL,
        project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
        first_sample INTEGER NOT NULL,sample_count INTEGER NOT NULL,
        pcm_sha256 TEXT NOT NULL)""")


def _chunks(db,pid,session_id):
    return [dict(row) for row in db.execute("""
        SELECT chunk_index,start_sample,sample_count,asset_name,pcm_sha256
        FROM w1e_capture_chunks WHERE project_id=? AND session_id=?
        ORDER BY chunk_index""",(pid,session_id))]


def _member(db,pid,scene_id,clip_id):
    if not db.execute("""SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='w1e_sealed_clip_members'""").fetchone():
        return None
    row=db.execute("""SELECT * FROM w1e_sealed_clip_members
        WHERE clip_id=? AND project_id=? AND scene_id=?""",
        (clip_id,pid,scene_id)).fetchone()
    if row is None:
        return None
    member=dict(row)
    manifest=db.execute("""SELECT segments_json,manifest_sha256,
        original_sha256,sample_count,actor_id
        FROM g06_long_recording_manifests
        WHERE project_id=? AND scene_id=? AND recording_id=?""",
        (pid,scene_id,member["recording_id"])).fetchone()
    if manifest is None or _sha(manifest["segments_json"].encode("utf8"))!=manifest["manifest_sha256"]:
        raise RuntimeError("The sealed original recording manifest was replaced")
    document=json.loads(manifest["segments_json"])
    if (document.get("format")!=RECORDING_FORMAT or
        document.get("recording_id")!=member["recording_id"] or
        document.get("original_pcm_sha256")!=manifest["original_sha256"] or
        document.get("sample_count")!=manifest["sample_count"]):
        raise RuntimeError("Sealed source recording identity changed")
    parts=document["segments"]
    cursor=0;found=False
    if not isinstance(parts,list) or not 1<=len(parts)<=32:
        raise RuntimeError("Invalid sealed recording source manifest")
    for seg in parts:
        if (seg.get("first_sample")!=cursor or
            type(seg.get("sample_count")) is not int or
            not 1<=seg["sample_count"]<=RATE*120):
            raise RuntimeError("Sealed source segment offset changed")
        linked=db.execute("""SELECT m.first_sample,m.sample_count,
            m.pcm_sha256,o.pcm_sha256,o.sample_count,length(o.pcm)
            FROM w1e_sealed_clip_members AS m
            JOIN g06_original_pcm AS o ON o.id=m.clip_id
            WHERE m.project_id=? AND m.scene_id=? AND
            m.recording_id=? AND m.clip_id=?""",
            (pid,scene_id,member["recording_id"],seg["clip_id"])).fetchone()
        if (linked is None or linked[0]!=seg["first_sample"] or
            linked[1]!=seg["sample_count"] or
            linked[2]!=seg["pcm_sha256"] or
            linked[3]!=seg["pcm_sha256"] or
            linked[4]!=seg["sample_count"] or linked[5]!=0):
            raise RuntimeError("A sealed recording sibling or clip marker was changed")
        if seg["clip_id"]==clip_id:
            if (found or seg["first_sample"]!=member["first_sample"] or
                seg["sample_count"]!=member["sample_count"] or
                seg["pcm_sha256"]!=member["pcm_sha256"]):
                raise RuntimeError("Sealed source segment was substituted")
            found=True
        cursor+=seg["sample_count"]
    if not found or cursor!=manifest["sample_count"]:
        raise RuntimeError("Sealed source is not contiguous")
    clip=db.execute("""SELECT actor_id,pcm_sha256,sample_count,length(pcm)
        FROM g06_original_pcm WHERE id=? AND project_id=? AND scene_id=?""",
        (clip_id,pid,scene_id)).fetchone()
    if (clip is None or clip[0]!=manifest["actor_id"] or
        clip[1]!=member["pcm_sha256"] or clip[2]!=member["sample_count"] or
        clip[3]!=0):
        raise RuntimeError("A sealed source marker is not trustworthy")
    return {**member,"recording_sha256":manifest["original_sha256"],
        "recording_manifest_sha256":manifest["manifest_sha256"]}


def original_identity(db,pid,scene_id,clip_id):
    member=_member(db,pid,scene_id,clip_id)
    if member is None:return None
    return {"original_recording_id":member["recording_id"],
        "recording_sha256":member["recording_sha256"],
        "recording_manifest_sha256":member["recording_manifest_sha256"],
        "recording_source_start_sample":member["first_sample"]}


class VerifiedSealedPCM:
    """Host-only random-access original PCM backed by AES-GCM sealed chunks.

    The object is not serializable; the protected worker must receive
    explicitly reviewed bounded source windows through anonymous pipes.
    Every source access rechecks G03 host session grants and authenticates
    its original encrypted chunk. Cache is one five-second chunk per object.
    """

    def __init__(self,live,token,db,pid,scene_id,clip_id):
        member=_member(db,pid,scene_id,clip_id)
        if member is None:raise RuntimeError("Sealed original clip does not exist")
        self.live=live;self.token=token;self.pid=pid
        self.scene_id=scene_id;self.clip_id=clip_id
        self.length=member["sample_count"]*2
        self.expected_sha256=member["pcm_sha256"]
        self.first_sample=member["first_sample"]
        self.session_id=member["recording_id"]
        self.chunks=_chunks(db,pid,self.session_id)
        self._cached_index=None;self._cached_raw=b""
        # Source evaluators access one PCM16 sample at a time. An in-memory
        # host key check runs on EVERY sample so a local director lock takes
        # effect immediately. The disk-backed cross-process grant check runs
        # at most 100ms apart and ALWAYS before a new sealed chunk read.
        # The supervisor also checks authorization before reel publication.
        self._last_grant_check_ns=0
        self._grant_recheck_ns=100_000_000
        first=0
        if not 1<=len(self.chunks)<=MAX_PIECES:
            raise RuntimeError("The original encrypted chunks are unavailable")
        for i,part in enumerate(self.chunks):
            if (part["chunk_index"]!=i or part["start_sample"]!=first or
                not 1<=part["sample_count"]<=CHUNK_SAMPLES):
                raise RuntimeError("Sealed source chunks are not contiguous")
            first+=part["sample_count"]
        if first<member["first_sample"]+member["sample_count"]:
            raise RuntimeError("The encrypted source loses original samples")
        self._validated_sha=False

    def __len__(self):return self.length

    @property
    def verified_sha256(self):
        self.verify_complete()
        return self.expected_sha256

    def _chunk(self,index):
        # Every sample checks immediate local key revocation in memory.
        # Synthetic hosts without that fast gate retain strict per-access
        # _session checks instead of silently skipping authorization.
        local=getattr(self.live,"local_session_live",None)
        if callable(local):
            if not local(self.pid,self.token):
                raise PermissionError("Original microphone host key was revoked")
        else:
            self.live._session(self.pid,self.token)
        now_ns=time.monotonic_ns()
        if (self._cached_index!=index or
            now_ns-self._last_grant_check_ns>=self._grant_recheck_ns):
            self.live._session(self.pid,self.token)
            self._last_grant_check_ns=now_ns
        if self._cached_index!=index:
            item=self.chunks[index]
            raw=self.live.get_original(self.pid,self.token,item["asset_name"])
            if (len(raw)!=item["sample_count"]*2 or
                _sha(raw)!=item["pcm_sha256"]):
                raise RuntimeError("Sealed microphone source failed authentication")
            self._cached_index=index;self._cached_raw=raw
        return self._cached_raw

    def __getitem__(self,key):
        if not isinstance(key,slice):
            raise TypeError("Protected PCM supports bounded byte windows")
        start,end,step=key.indices(self.length)
        if step!=1 or end-start>1024*1024:
            raise ValueError("A protected audio read exceeds one MiB")
        if start>=end:return b""
        output=bytearray()
        source_start=self.first_sample*2+start
        source_end=self.first_sample*2+end
        for index,part in enumerate(self.chunks):
            first=part["start_sample"]*2
            last=first+part["sample_count"]*2
            if last<=source_start or first>=source_end:continue
            left=max(first,source_start);right=min(last,source_end)
            raw=self._chunk(index)
            output.extend(raw[left-first:right-first])
        if len(output)!=end-start:
            raise RuntimeError("A sealed source PCM window is incomplete")
        return bytes(output)

    def verify_complete(self):
        if self._validated_sha:
            self.live._session(self.pid,self.token)
            self._last_grant_check_ns=time.monotonic_ns()
            return
        digest=hashlib.sha256()
        for at in range(0,self.length,1024*1024):
            digest.update(self[at:min(self.length,at+1024*1024)])
        if digest.hexdigest()!=self.expected_sha256:
            raise RuntimeError("Sealed original PCM digest differs from frozen source")
        self._validated_sha=True


class SealedOriginalChunkStore:
    """Durable sealed project writer; no project SQLite or PCM on raw disk."""

    def __init__(self,filming,session_id,pid,scene_id,actor_id,stage_sha256):
        if filming.g05.g04.live is None or not filming.g05.g04.token:
            raise PermissionError("An unlocked encrypted film host is required")
        self.filming=filming
        self.live=filming.g05.g04.live
        self.token=filming.g05.g04.token
        self.session_id=session_id;self.project_id=pid
        self.scene_id=scene_id;self.actor_id=actor_id
        self.stage_sha256=stage_sha256
        self.q=queue.Queue(maxsize=QUEUE_LIMIT)
        self.thread=None;self.error=None
        self.total_samples=0;self.digest=hashlib.sha256()
        self.final_sha256=None;self._ended=False
        self._lock=threading.RLock()

    def _execute(self,callback,mutate=False):
        def task(db,movie,source):
            _schema(db)
            return callback(db,movie,source)
        return self.filming._with(self.project_id,self.scene_id,
                                  task,mutate=mutate)

    def begin(self):
        def initialize(db,movie,source):
            db.execute("""INSERT INTO g06_long_capture_sessions(
                session_id,project_id,scene_id,actor_id,stage_sha256,
                status,started_at,updated_at)
                VALUES(?,?,?,?,?,'recording',?,?)""",
                (self.session_id,self.project_id,self.scene_id,
                 self.actor_id,self.stage_sha256,_now(),_now()))
        self._execute(initialize,mutate=True)
        self.thread=threading.Thread(target=self._write_loop,
            daemon=True,name="nvp-sealed-original-"+self.session_id[:8])
        self.thread.start()

    def push(self,raw):
        if not raw or len(raw)%2 or len(raw)>MAX_CALLBACK_SAMPLES*2:
            raise RuntimeError("A microphone callback exceeded sealed admission")
        with self._lock:
            if self._ended or self.error:
                raise RuntimeError("The sealed microphone writer is unavailable")
            if self.total_samples+len(raw)//2>SOURCE_SAMPLES:
                raise RuntimeError("The 30-minute scene capture limit was reached")
            self.q.put_nowait(raw)
            self.digest.update(raw)
            self.total_samples+=len(raw)//2

    def _append(self,index,first,raw):
        if (not 0<len(raw)<=MAX_CHUNK_BYTES or len(raw)%2 or
            first+len(raw)//2>SOURCE_SAMPLES or index>=MAX_PIECES):
            raise RuntimeError("A sealed original source chunk is invalid")
        name=f"capture/{self.session_id}/chunk-{index:04d}.pcm16le"
        # This operation writes ciphertext and independently reads its GCM
        # tag before the live source index HEAD becomes authoritative.
        self.live.put_original(self.project_id,self.token,name,raw,
                               media_type=MEDIA_TYPE)
        digest=_sha(raw)
        def publish(db,movie,source):
            rec=db.execute("""SELECT status,committed_samples,committed_chunks,
                stage_sha256 FROM g06_long_capture_sessions WHERE
                project_id=? AND session_id=?""",
                (self.project_id,self.session_id)).fetchone()
            if (rec is None or rec["status"]!="recording" or
                rec["stage_sha256"]!=self.stage_sha256 or
                rec["committed_samples"]!=first or
                rec["committed_chunks"]!=index):
                raise RuntimeError("Sealed microphone chunk lost session order")
            db.execute("""INSERT INTO w1e_capture_chunks(
                project_id,session_id,chunk_index,start_sample,sample_count,
                asset_name,pcm_sha256) VALUES(?,?,?,?,?,?,?)""",
                (self.project_id,self.session_id,index,first,len(raw)//2,
                 name,digest))
            db.execute("""UPDATE g06_long_capture_sessions
                SET committed_chunks=?,committed_samples=?,updated_at=?
                WHERE project_id=? AND session_id=? AND status='recording'""",
                (index+1,first+len(raw)//2,_now(),
                 self.project_id,self.session_id))
        self._execute(publish,mutate=True)

    def _write_loop(self):
        try:
            pending=bytearray()
            index=0;first=0
            while True:
                raw=self.q.get()
                if raw is None:
                    if pending:
                        self._append(index,first,bytes(pending))
                    break
                pending.extend(raw)
                while len(pending)>=MAX_CHUNK_BYTES:
                    part=bytes(pending[:MAX_CHUNK_BYTES])
                    self._append(index,first,part)
                    del pending[:MAX_CHUNK_BYTES]
                    first+=CHUNK_SAMPLES
                    index+=1
        except Exception as error:
            with self._lock:self.error=error

    def finish_spooling(self,*,expected_samples):
        with self._lock:
            if self._ended:
                raise RuntimeError("The original encrypted capture is closed")
            self._ended=True
            self.final_sha256=self.digest.hexdigest()
            if expected_samples!=self.total_samples:
                raise RuntimeError("Native microphone sample count changed")
        self.q.put(None,timeout=10)
        self.thread.join(timeout=60)
        if self.thread.is_alive() or self.error:
            raise RuntimeError("A sealed microphone writer could not finish")
        def stop(db,movie,source):
            record=db.execute("""SELECT status,committed_samples,committed_chunks
                FROM g06_long_capture_sessions WHERE project_id=? AND
                session_id=?""",(self.project_id,self.session_id)).fetchone()
            if (record is None or record["status"]!="recording" or
                record["committed_samples"]!=self.total_samples or
                not 1<=record["committed_chunks"]<=MAX_PIECES):
                raise RuntimeError("A sealed original capture lost its tail")
            db.execute("""UPDATE g06_long_capture_sessions SET
                status='stopped',updated_at=? WHERE project_id=?
                AND session_id=? AND status='recording'""",
                (_now(),self.project_id,self.session_id))
        self._execute(stop,mutate=True)
        return {"sample_count":self.total_samples,
            "original_pcm_sha256":self.final_sha256}

    def discard(self):
        if self.thread is not None and self.thread.is_alive():
            self.q.put(None,timeout=10)
            self.thread.join(timeout=60)
            if self.thread.is_alive():
                raise RuntimeError("Sealed recording writer could not be stopped")
        def mark(db,movie,source):
            db.execute("""UPDATE g06_long_capture_sessions SET
                status='cancelled',updated_at=? WHERE project_id=? AND
                session_id=? AND status IN ('recording','stopped','failed')""",
                (_now(),self.project_id,self.session_id))
        self._execute(mark,mutate=True)
        # Immutable sealed staging assets remain quarantined by index:
        # cancellation never exposes them as an original or unseals to disk.

    def publish(self,filming,receipt):
        if filming is not self.filming or not self._ended or self.error:
            raise RuntimeError("Sealed recording cannot be published")
        if (receipt["original_pcm_sha256"]!=self.final_sha256 or
            receipt["sample_count"]!=self.total_samples):
            raise RuntimeError("Sealed recording provenance changed")
        pid=self.project_id;sid=self.scene_id
        rows=self._execute(lambda db,movie,source:_chunks(db,pid,self.session_id))
        if not rows or len(rows)>MAX_PIECES:
            raise RuntimeError("Sealed source chunk sequence is absent")
        first=0;digest=hashlib.sha256()
        segments=[];segment_digest=hashlib.sha256()
        part_samples=0;part_start=0;part_counter=0
        for index,part in enumerate(rows):
            if (part["chunk_index"]!=index or
                part["start_sample"]!=first or
                not 1<=part["sample_count"]<=CHUNK_SAMPLES):
                raise RuntimeError("Original source chunks are reordered")
            raw=self.live.get_original(pid,self.token,part["asset_name"])
            if len(raw)!=part["sample_count"]*2 or _sha(raw)!=part["pcm_sha256"]:
                raise RuntimeError("Original sealed source hash was changed")
            digest.update(raw);segment_digest.update(raw)
            first+=part["sample_count"];part_samples+=part["sample_count"]
            if part_samples>=RATE*120 or index==len(rows)-1:
                segments.append({"clip_id":uuid.uuid4().hex,
                    "first_sample":part_start,"sample_count":part_samples,
                    "pcm_sha256":segment_digest.hexdigest()})
                part_start+=part_samples;part_samples=0
                segment_digest=hashlib.sha256()
                part_counter+=1
        if (first!=self.total_samples or digest.hexdigest()!=self.final_sha256 or
            part_start!=first or len(segments)>32):
            raise RuntimeError("A sealed source failed full-stream verification")
        doc={"format":RECORDING_FORMAT,"recording_id":self.session_id,
            "project_id":pid,"scene_id":sid,"actor_id":self.actor_id,
            "sample_rate":RATE,"channels":1,"sample_count":first,
            "original_pcm_sha256":self.final_sha256,"segments":segments}
        encoded=_json(doc)
        group_sha=_sha(encoded.encode("utf8"))
        def commit(db,movie,source):
            _schema(db)
            head,stage,plan,raw=_stage(db,source,pid,sid)
            if stage["usd_sha256"]!=self.stage_sha256:
                raise RuntimeError("Original scene stage changed during capture")
            approved_actors={x["actor_id"] for x in plan["objects"]
                              if x["role"]=="actor"}
            if self.actor_id and self.actor_id not in approved_actors:
                raise RuntimeError("Captured voice no longer belongs to the stage")
            session=db.execute("""SELECT status,committed_samples,committed_chunks,
                stage_sha256 FROM g06_long_capture_sessions WHERE
                project_id=? AND scene_id=? AND session_id=?""",
                (pid,sid,self.session_id)).fetchone()
            if (session is None or session["status"]!="stopped" or
                session["stage_sha256"]!=self.stage_sha256 or
                session["committed_samples"]!=first or
                session["committed_chunks"]!=len(rows)):
                raise RuntimeError("Encrypted original capture is incomplete")
            stored=_chunks(db,pid,self.session_id)
            if stored!=rows:
                raise RuntimeError("Sealed capture metadata changed after review")
            timestamp=_now()
            for part in segments:
                # Empty BLOB means "requires encrypted source broker", NEVER
                # silently substitute zero/synthetic audio from this row.
                db.execute("""INSERT INTO g06_original_pcm(
                    id,project_id,scene_id,actor_id,source_kind,pcm,
                    pcm_sha256,sample_rate,channels,sample_count,recorded_at)
                    VALUES(?,?,?,?,'native_microphone_pcm16le',?,?,?,?,?,?)""",
                    (part["clip_id"],pid,sid,self.actor_id,b"",
                     part["pcm_sha256"],RATE,1,part["sample_count"],timestamp))
                db.execute("""INSERT INTO w1e_sealed_clip_members(
                    clip_id,recording_id,project_id,scene_id,
                    first_sample,sample_count,pcm_sha256)
                    VALUES(?,?,?,?,?,?,?)""",
                    (part["clip_id"],self.session_id,pid,sid,
                     part["first_sample"],part["sample_count"],part["pcm_sha256"]))
            db.execute("""INSERT INTO g06_long_recording_manifests(
                recording_id,project_id,scene_id,actor_id,session_id,
                sample_count,original_sha256,segments_json,manifest_sha256,
                recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (self.session_id,pid,sid,self.actor_id,self.session_id,
                 first,self.final_sha256,encoded,group_sha,timestamp))
            G09CCaptureJournal.seal(db,pid,sid,self.session_id,receipt)
            db.execute("""UPDATE g06_long_capture_sessions SET
                status='completed',original_recording_id=?,original_sha256=?,
                updated_at=? WHERE project_id=? AND session_id=? AND
                status='stopped'""",
                (self.session_id,self.final_sha256,_now(),pid,self.session_id))
            return {"recording_id":self.session_id,
                "clip_ids":[seg["clip_id"] for seg in segments],
                "segments":segments,"sample_count":first,
                "original_pcm_sha256":self.final_sha256,
                "duration_seconds":first/RATE,
                "manifest_sha256":group_sha,
                "encrypted_source":True,
                "original_source_unchanged":True,
                "recorded_from_native_microphone":True}
        return self._execute(commit,mutate=True)
