"""G08 protected movie delivery: original source stays in encrypted film store.

No decrypted original or derived movie is placed in an ordinary temp file.
The already-trusted NVP host reads G07's authenticated in-memory source,
renders into a bounded BytesIO and seals the derivative as a distinct
AES-GCM asset with independent authenticated readback. Unlike ordinary
exports, this first protected path DOES NOT claim protected OS process
sandbox or independent-process verification; those remain G03/G09
acceptance obligations. Job states and output index are in sealed SQLite.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import re
import threading
import uuid

from backend.nvp_g03_windows_vault import (
    _encrypt_file,_decrypt_file,_no_link,_token
)
from backend.nvp_g03_live_store import _HashSink,LiveFilmError
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g08_native_avi import (
    render_film,verify_movie,PROFILE,FPS,TICKS_FRAME,TICKS_SAMPLE,
    MAX_SECONDS,MAX_OUTPUT_BYTES)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

HEX=re.compile(r"[0-9a-f]{32}\Z")


def _now():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g08_sealed_export_jobs(
        id TEXT PRIMARY KEY,edit_revision INTEGER NOT NULL,
        edit_sha256 TEXT NOT NULL,
        look_sha256 TEXT NOT NULL DEFAULT '',
        actors_sha256 TEXT NOT NULL DEFAULT '',
        acoustics_sha256 TEXT NOT NULL DEFAULT '',
        finishing_sha256 TEXT NOT NULL DEFAULT '',
        expected_frames INTEGER NOT NULL,
        status TEXT NOT NULL,output_sha256 TEXT,output_bytes INTEGER,
        receipt_json TEXT,issue TEXT,created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(status IN ('queued','rendering','verifying','completed',
                         'cancelled','failed','interrupted')))""")
    if "look_sha256" not in {
          r["name"] for r in db.execute("PRAGMA table_info(g08_sealed_export_jobs)") }:
        db.execute("ALTER TABLE g08_sealed_export_jobs ADD COLUMN look_sha256 TEXT NOT NULL DEFAULT ''")
    if "actors_sha256" not in {
          r["name"] for r in db.execute("PRAGMA table_info(g08_sealed_export_jobs)") }:
        db.execute("ALTER TABLE g08_sealed_export_jobs ADD COLUMN actors_sha256 TEXT NOT NULL DEFAULT ''")
    if "acoustics_sha256" not in {
          r["name"] for r in db.execute("PRAGMA table_info(g08_sealed_export_jobs)") }:
        db.execute("ALTER TABLE g08_sealed_export_jobs ADD COLUMN acoustics_sha256 TEXT NOT NULL DEFAULT ''")
    if "finishing_sha256" not in {
        r["name"] for r in db.execute("PRAGMA table_info(g08_sealed_export_jobs)") }:
        db.execute("ALTER TABLE g08_sealed_export_jobs ADD COLUMN finishing_sha256 TEXT NOT NULL DEFAULT ''")
    db.execute("""CREATE TABLE IF NOT EXISTS g08_sealed_delivery_assets(
        job_id TEXT PRIMARY KEY,opaque_id TEXT NOT NULL,
        digest TEXT NOT NULL,size_bytes INTEGER NOT NULL,
        created_at TEXT NOT NULL)""")


class G08SealedDelivery:
    def __init__(self,live,studio,access):
        self.live=live
        self.studio=studio
        self.access=access
        self._guard=threading.RLock()
        self._jobs={}
        self._progress={}
        self._revoked=set()

    def _check(self,pid,token):
        if type(pid) is not str or not HEX.fullmatch(pid):
            raise ValueError("Select a movie")
        if not self.live().exists(pid):
            raise ValueError("This movie is not protected")
        if not self.access().permitted(pid,token,renew=False):
            raise PermissionError("Unlock the movie before finishing it")

    def _read(self,pid,token,callback):
        store=self.live()
        with store._guard:
            key=store._session(pid,token)
            db,_=store._read_db(store._folder(pid),pid,key)
            try:
                table={r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                return callback(db,table)
            finally:db.close()

    def _change(self,pid,token,callback):
        store=self.live()
        def mutate(db,key,folder):
            _schema(db)
            return callback(db,key,folder)
        return store._change(pid,token,mutate)

    def _publish(self,pid,token,job,data,verified):
        if type(data) is not bytes or not 0<len(data)<=MAX_OUTPUT_BYTES:
            raise ValueError("Finished protected film is too large")
        digest=sha256(data).hexdigest()
        if verified.get("sha256")!=digest or not verified.get("verified"):
            raise RuntimeError("Protected film has not been verified")
        def commit(db,key,folder):
            row=db.execute("""SELECT status FROM g08_sealed_export_jobs
                WHERE id=?""",(job,)).fetchone()
            if row is None or row["status"]!="verifying":
                raise RuntimeError("This protected movie export was cancelled")
            if db.execute("""SELECT 1 FROM g08_sealed_delivery_assets
                WHERE job_id=?""",(job,)).fetchone():
                raise RuntimeError("The finished film already exists")
            # Existing G03 authenticated encryption never writes plaintext.
            name="g08-delivery/"+job
            opaque=_token(name,key)
            final=folder/"assets"/(opaque+".nvpsealed")
            _no_link(folder/"assets")
            if final.exists():
                _no_link(final)
                check=_decrypt_file(final,_HashSink(),key=key,
                    project_id=pid,name=name)
                if check!={"sha256":digest,"size_bytes":len(data)}:
                    raise RuntimeError("A previous protected export differs")
            else:
                _encrypt_file(BytesIO(data),final,key=key,
                              project_id=pid,name=name)
            audit=_decrypt_file(final,_HashSink(),key=key,
                                project_id=pid,name=name)
            if audit!={"sha256":digest,"size_bytes":len(data)}:
                raise RuntimeError("Protected movie encryption readback failed")
            db.execute("""INSERT INTO g08_sealed_delivery_assets
                (job_id,opaque_id,digest,size_bytes,created_at)
                VALUES (?,?,?,?,?)""",(job,opaque,digest,len(data),_now()))
            db.execute("""UPDATE g08_sealed_export_jobs SET
                status='completed',output_sha256=?,output_bytes=?,
                receipt_json=?,updated_at=? WHERE id=?""",
                (digest,len(data),json.dumps(verified,sort_keys=True),
                 _now(),job))
        self._change(pid,token,commit)

    def _set(self,pid,token,job,status,*,issue=None):
        def update(db,key,folder):
            row=db.execute("""SELECT status FROM g08_sealed_export_jobs
                WHERE id=?""",(job,)).fetchone()
            if row is None:raise KeyError("Movie export is missing")
            if row["status"] in ("completed","cancelled","failed","interrupted"):
                raise RuntimeError("This movie export is no longer running")
            db.execute("""UPDATE g08_sealed_export_jobs SET
                status=?,issue=COALESCE(?,issue),updated_at=?
                WHERE id=?""",(status,issue,_now(),job))
        return self._change(pid,token,update)

    def _reconcile(self,pid,token):
        # Read-only polling must NOT publish a fresh encrypted SQLite HEAD.
        # The orphan check is a read; only genuine interrupted work creates
        # a new durable protected revision after unlock/restart.
        with self._guard:
            active={job for job,(owner,thread) in self._jobs.items()
                    if owner==pid and thread.is_alive()}
        def stale(db,tables):
            if "g08_sealed_export_jobs" not in tables:return []
            return [row["id"] for row in db.execute(
                """SELECT id FROM g08_sealed_export_jobs
                   WHERE status IN ('queued','rendering','verifying')""")
                   if row["id"] not in active]
        missing=self._read(pid,token,stale)
        if not missing:return
        def fix(db,key,folder):
            for job in missing:
                db.execute("""UPDATE g08_sealed_export_jobs
                  SET status='interrupted',
                      issue='An earlier film export was interrupted.',
                      updated_at=?
                  WHERE id=? AND status IN ('queued','rendering','verifying')""",
                  (_now(),job))
        self._change(pid,token,fix)

    def start(self,pid,expected_revision,token):
        self._check(pid,token)
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("Save your edit before finishing the movie")
        self._reconcile(pid,token)
        editor=G07Editor(self.studio,live=self.live(),token=token)
        current=editor.view(pid)
        if current["revision"]!=expected_revision or current["missing_sources"]:
            raise RuntimeError("Review the current film edit before delivery")
        assembly=editor.native_assembly(pid,expected_revision)
        from backend.nvp_int01c_source_contract import verify_render_assembly
        verify_render_assembly(assembly,require_bindings=True)
        length=assembly["duration_tick"]
        if (not 0<length<=MAX_SECONDS*TICKS_PER_SECOND or
                length%TICKS_FRAME or length%TICKS_SAMPLE):
            raise ValueError("The first finished film must be 30 seconds or less, with whole-frame trimming")
        job=uuid.uuid4().hex
        def enqueue(db,key,folder):
            if db.execute("""SELECT 1 FROM g08_sealed_export_jobs
                WHERE status IN ('queued','rendering','verifying')
                LIMIT 1""").fetchone():
                raise RuntimeError("A movie is already being finished")
            db.execute("""INSERT INTO g08_sealed_export_jobs
                (id,edit_revision,edit_sha256,look_sha256,actors_sha256,
                 acoustics_sha256,finishing_sha256,
                 expected_frames,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'queued',?,?)""",
                (job,expected_revision,assembly["edit_document_sha256"],
                 assembly["production_looks_sha256"],
                 assembly["actor_performances_sha256"],
                 assembly["acoustic_looks_sha256"],
                 assembly["finishing_sha256"],
                 length//TICKS_FRAME,_now(),_now()))
        self._change(pid,token,enqueue)
        runner=threading.Thread(target=self._run,
            args=(pid,token,job,assembly),daemon=True,name="nvp-g08-sealed-"+job[:8])
        with self._guard:
            self._jobs[job]=(pid,runner)
            self._progress[job]=0
        runner.start()
        return self.read(pid,job,token,refresh=False)

    def _run(self,pid,token,job,assembly):
        try:
            with self._guard:
                if job in self._revoked:raise InterruptedError()
            self._check(pid,token)
            self._set(pid,token,job,"rendering")
            dest=BytesIO()
            def stop():
                with self._guard:
                    cancelled=job in self._revoked
                return cancelled or not self.access().permitted(pid,token,renew=False)
            def progress(done,total):
                with self._guard:self._progress[job]=done
            result=render_film(assembly,dest,cancel=stop,progress=progress)
            if stop():raise InterruptedError()
            self._set(pid,token,job,"verifying")
            data=dest.getvalue()
            expected=assembly["duration_tick"]//TICKS_FRAME
            verified=verify_movie(data,expected,
                                  expected_sha=sha256(data).hexdigest())
            from backend.nvp_g09d_master import verify_completed_movie_sound
            measured=verify_completed_movie_sound(
                data,assembly.get("approved_finishing"))
            if (measured["sample_count"]!=expected*2000 or
                result.get("approved_finishing_sha256")!=
                    assembly["finishing_sha256"]):
                raise RuntimeError("Protected finished soundtrack failed source verification")
            if assembly.get("approved_finishing"):
                if (measured["rendered_pcm_sha256"]!=result.get(
                        "native_sound_mastering",{}).get(
                            "derived_master_sha256")):
                    raise RuntimeError("Protected film's actual PCM is not the approved sound master")
            verified["native_sound_readback"]=measured
            verified["approved_finishing_sha256"]=assembly["finishing_sha256"]
            verified["finishing_sound_independently_verified"]=False
            verified["finished_pcm_reopened_in_memory"]=True
            if stop():raise InterruptedError()
            self._publish(pid,token,job,data,verified)
        except InterruptedError:
            try:self._set(pid,token,job,"cancelled",
                issue="Movie export stopped; original material preserved.")
            except Exception:pass
        except Exception:
            try:
                with self._guard:cancelled=job in self._revoked
                if not cancelled:
                    self._set(pid,token,job,"failed",
                        issue="Movie could not be completed; your edit is safe.")
            except Exception:pass
        finally:
            with self._guard:
                self._jobs.pop(job,None)
                self._progress.pop(job,None)
                self._revoked.discard(job)

    def list(self,pid,token):
        self._check(pid,token)
        self._reconcile(pid,token)
        def read(db,tables):
            if "g08_sealed_export_jobs" not in tables:return []
            return [dict(row) for row in db.execute("""SELECT * FROM g08_sealed_export_jobs
                ORDER BY created_at DESC,id DESC LIMIT 25""")]
        return [self._public(row) for row in self._read(pid,token,read)]

    def _public(self,row):
        job=row["id"];total=row["expected_frames"]
        with self._guard:count=self._progress.get(job,0)
        count=total if row["status"]=="completed" else min(total,count)
        receipt=(json.loads(row["receipt_json"])
                 if row["status"]=="completed" and row["receipt_json"] else {})
        sound=receipt.get("native_sound_readback",{})
        return {"id":job,"edit_revision":row["edit_revision"],
            "sound_quality":{
                "integrated_lufs":sound.get("integrated_lufs"),
                "sample_peak_dbfs":sound.get("sample_peak_dbfs"),
                "review_target_met":sound.get("approved_review_loudness_met"),
                "actual_pcm_verified":bool(
                    receipt.get("finished_pcm_reopened_in_memory")),
                "cinema_audio_certified":False
            } if row["status"]=="completed" else None,
            "status":row["status"],"frames_completed":count,
            "frames_total":total,"progress_percent":round(count/max(1,total)*100,1),
            "duration_seconds":total/FPS,"profile":PROFILE,
            "issue":row["issue"],"output_sha256":row["output_sha256"]
                if row["status"]=="completed" else None,
            "output_bytes":row["output_bytes"]
                if row["status"]=="completed" else None,
            "verified":row["status"]=="completed",
            "download_url":None, # derived in the route, not from a file path
            "original_sources_preserved":True,
            "sealed":True}

    def read(self,pid,job,token,*,refresh=True):
        self._check(pid,token)
        if type(job) is not str or not HEX.fullmatch(job):
            raise ValueError("Choose an existing finished movie")
        if refresh:self._reconcile(pid,token)
        def find(db,tables):
            if "g08_sealed_export_jobs" not in tables:return None
            row=db.execute("SELECT * FROM g08_sealed_export_jobs WHERE id=?",
                           (job,)).fetchone()
            return dict(row) if row else None
        row=self._read(pid,token,find)
        if row is None:raise KeyError("Finished movie not found")
        return self._public(row)

    def cancel(self,pid,job,token):
        current=self.read(pid,job,token)
        if current["status"] not in ("queued","rendering","verifying"):
            raise RuntimeError("This movie is no longer being finished")
        with self._guard:self._revoked.add(job)
        self._set(pid,token,job,"cancelled",issue="Export stopped by director")
        return self.read(pid,job,token)

    def cancel_project(self,pid):
        with self._guard:
            self._revoked.update(job for job,(owner,_) in self._jobs.items()
                                 if owner==pid)

    def movie_bytes(self,pid,job,token):
        current=self.read(pid,job,token)
        if current["status"]!="completed":
            raise RuntimeError("This movie has not been completed")
        def read(db,tables):
            if "g08_sealed_delivery_assets" not in tables:return None
            row=db.execute("""SELECT opaque_id,digest,size_bytes
                FROM g08_sealed_delivery_assets WHERE job_id=?""",
                (job,)).fetchone()
            return dict(row) if row else None
        entry=self._read(pid,token,read)
        if entry is None:raise RuntimeError("The protected movie master is missing")
        store=self.live()
        with store._guard:
            key=store._session(pid,token)
            source=store._folder(pid)/"assets"/(entry["opaque_id"]+".nvpsealed")
            _no_link(source)
            memory=BytesIO()
            digest=_decrypt_file(source,memory,key=key,project_id=pid,
                                  name="g08-delivery/"+job)
            if digest!={"sha256":entry["digest"],"size_bytes":entry["size_bytes"]}:
                raise RuntimeError("Protected movie failed authenticated readback")
            raw=memory.getvalue()
        if sha256(raw).hexdigest()!=current["output_sha256"]:
            raise RuntimeError("Protected movie digest changed")
        return raw
