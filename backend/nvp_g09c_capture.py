"""G09-C original microphone custody & sample-clock evidence.

G06's native OS capture owns raw PCM; G09-C records durable provenance and
interruption state without intercepting or replacing any microphone samples.
A callback's host monotonic timestamp is an *observation*, NOT a calibrated
hardware ADC/AV timestamp or sample-accurate picture sync guarantee.
Final capture receipts are committed in the SAME SQLite transaction as the
G06 original PCM. Crash before that transaction leaves an 'interrupted'
intent, never a falsely 'recorded' sound or automatically published Take.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime,timezone

FORMAT="nvp.g09c.original_capture_audit.v1"
MAX_OBSERVATIONS=30
MAX_SESSIONS_PER_SCENE=250

def _now():return datetime.now(timezone.utc).isoformat()

def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09c_capture_sessions(
        project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
        session_id TEXT NOT NULL,actor_id TEXT,
        state TEXT NOT NULL,original_clip_id TEXT,
        original_sha256 TEXT,receipt_json TEXT,
        started_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,session_id),
        CHECK(state IN ('recording','completed','cancelled',
                        'interrupted','failed')))""")
    db.execute("""CREATE INDEX IF NOT EXISTS g09c_scene_captures
        ON g09c_capture_sessions(project_id,scene_id,updated_at)""")

def _receipt(session,pcm):
    import time
    from backend.nvp_g06_filming import RATE
    raw_hash=hashlib.sha256(pcm).hexdigest()
    with session.lock:
        if session.status!="stopped" or session.error is not None or (
                session.bytes!=len(pcm) or session.frames*2!=len(pcm) or
                session.frames<1):
            raise RuntimeError("Native microphone recording was not completed")
        first=session.first_callback_ns
        last=session.last_callback_ns
        started=session.started_ns
        stopped=session.stopped_ns
        gaps=list(session.largest_gap_ns)
        frames=session.frames
        chunks=session.chunks
        peak=session.peak_abs
    if (type(started) is not int or type(stopped) is not int or
        not started<stopped or not chunks or
        not first or not last or not started<=first<=last<=stopped):
        raise RuntimeError("Native microphone capture timing evidence is incomplete")
    duration_ns=round(frames*1_000_000_000/RATE)
    host_elapsed=stopped-started
    drift=host_elapsed-duration_ns
    # Windows scheduler/driver buffering makes this only a diagnostic.
    return {"format":FORMAT,"session_id":session.id,
        "project_id":session.project_id,"scene_id":session.scene_id,
        "actor_id":session.actor_id,"sample_rate":RATE,
        "source_kind":"native_os_microphone_pcm16le",
        "sample_count":frames,"sample_bytes":len(pcm),
        "callback_count":chunks,"peak_pcm_abs":peak,
        "original_pcm_sha256":raw_hash,
        "host_started_monotonic_ns":started,
        "host_stopped_monotonic_ns":stopped,
        "first_callback_monotonic_ns":first,
        "last_callback_monotonic_ns":last,
        "max_callback_gaps_ns":gaps[:MAX_OBSERVATIONS],
        "observed_elapsed_minus_pcm_ns":drift,
        "hardware_capture_timestamp_calibrated":False,
        "hardware_audio_to_picture_sync_proven":False,
        "native_device_sample_clock_is_original":True,
        "original_pcm_modified":False}

class G09CCaptureJournal:
    def __init__(self,filming):
        self.filming=filming
    def _execute(self,pid,fn,mutate=False):
        def work(db,movie):
            _schema(db)
            return fn(db,movie)
        return self.filming.g05.g04._execute(pid,work,mutate=mutate)
    def begin(self,session):
        def save(db,movie):
            count=db.execute("""SELECT count(*) FROM g09c_capture_sessions
                WHERE project_id=? AND scene_id=?""",
                (session.project_id,session.scene_id)).fetchone()[0]
            if count>=MAX_SESSIONS_PER_SCENE:
                raise RuntimeError("Scene recording journal is full")
            db.execute("""INSERT INTO g09c_capture_sessions(
              project_id,scene_id,session_id,actor_id,state,
              started_at,updated_at) VALUES(?,?,?,?,'recording',?,?)""",
              (session.project_id,session.scene_id,session.id,
               session.actor_id,_now(),_now()))
        self._execute(session.project_id,save,mutate=True)
    def cancel(self,session):
        def update(db,movie):
            db.execute("""UPDATE g09c_capture_sessions SET state='cancelled',
              updated_at=? WHERE project_id=? AND session_id=? AND
              state='recording'""",
              (_now(),session.project_id,session.id))
        return self._execute(session.project_id,update,mutate=True)
    def list(self,pid,scene_id,active_session_ids=()):
        active=set(active_session_ids)
        if len(active)>64:raise ValueError("Too many active microphone sessions")
        def read(db,movie):
            rows=[dict(row) for row in db.execute("""SELECT * FROM g09c_capture_sessions
              WHERE project_id=? AND scene_id=? ORDER BY started_at DESC,
              session_id DESC LIMIT 50""",(pid,scene_id))]
            return rows
        records=self._execute(pid,read)
        stale=[row["session_id"] for row in records
               if row["state"]=="recording" and row["session_id"] not in active]
        if stale:
            def mark(db,movie):
                for sid in stale:
                    db.execute("""UPDATE g09c_capture_sessions SET
                      state='interrupted',updated_at=?
                      WHERE project_id=? AND scene_id=? AND session_id=?
                      AND state='recording'""",
                      (_now(),pid,scene_id,sid))
            self._execute(pid,mark,mutate=True)
            records=self._execute(pid,read)
        return {"format":FORMAT,"scene_id":scene_id,
            "recordings":[{
                "session_id":r["session_id"],"actor_id":r["actor_id"],
                "status":r["state"],"original_clip_id":r["original_clip_id"],
                "original_sha256":r["original_sha256"] if r["state"]=="completed" else None,
                "sample_count":(
                    json.loads(r["receipt_json"])["sample_count"]
                    if r["state"]=="completed" and r["receipt_json"] else None),
                "hardware_sync_proven":False}
                for r in records],
            "interrupted_sessions":len(stale),
            "original_sound_replaced":False}

    @staticmethod
    def seal(db,pid,scene_id,clip_id,receipt):
        _schema(db)
        if (type(receipt) is not dict or receipt.get("format")!=FORMAT or
            receipt.get("project_id")!=pid or
            receipt.get("scene_id")!=scene_id or
            receipt.get("original_pcm_modified") is not False or
            receipt.get("hardware_audio_to_picture_sync_proven") is not False or
            type(receipt.get("sample_count")) is not int or
            receipt["sample_count"]<1):
            raise RuntimeError("Native recording provenance is incomplete")
        row=db.execute("""SELECT state FROM g09c_capture_sessions
          WHERE project_id=? AND scene_id=? AND session_id=?""",
          (pid,scene_id,receipt["session_id"])).fetchone()
        if row is None or row["state"]!="recording":
            raise RuntimeError("Recording session was not properly opened")
        raw=json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False)
        db.execute("""UPDATE g09c_capture_sessions
            SET state='completed',original_clip_id=?,original_sha256=?,
                receipt_json=?,updated_at=? WHERE project_id=? AND
                scene_id=? AND session_id=? AND state='recording'""",
            (clip_id,receipt["original_pcm_sha256"],raw,_now(),
             pid,scene_id,receipt["session_id"]))
