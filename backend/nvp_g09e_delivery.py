"""G09-E durable host-supervised film reel rendering, source and recovery.

Each finished source-time AVI reel is verified by an independently launched
worker before the host publishes the path. Durable g09e_jobs/chunks in the
existing project DB distinguish intent, partial, verified, interrupted and
completed; restart never treats a leftover file as automatic success.

Ordinary project only in this first pass. Locked encrypted G03 movies MUST
NOT be routed into plaintext disk subprocesses: reject them up front.
Sealed long-reel custody is an explicit G09-E pending security group.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import uuid

from backend.nvp_g07_edit import G07Editor
from backend.nvp_g08_native_avi import TICKS_FRAME,TICKS_SAMPLE,FPS
from backend.nvp_g09e_chunk import (
    FRAMES_PER_CHUNK,MAX_CHUNKS,MAX_FRAMES,MAX_CHUNK_BYTES,
    source_digests,chunk_bounds,_canonical,inspect_reel)
from backend.nvp_worker_containment import launch_contained
from backend.nvp_g03_protected_scene_supervisor import _sanitized_worker_env

HEX=re.compile(r"[0-9a-f]{32}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")
FORMAT="nvp.g09e.recoverable_long_film.v1"
ACTIVE=frozenset(("queued","analyzing","rendering","verifying","finalizing"))
RESUMABLE=frozenset(("interrupted","cancelled","failed"))
TERMINAL=frozenset(("completed","cancelled","failed","interrupted"))
MAX_OUTPUT_BYTES=32*1024**3
WORKER_MEMORY_MB=2048
MIN_FREE_DISK=256*1024**2
STALE_SECONDS=120
MAX_RECEIPT_BYTES=2*1024**2

def _now():return datetime.now(timezone.utc).isoformat()

def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09e_jobs(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
        edit_revision INTEGER NOT NULL,
        source_json TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        total_frames INTEGER NOT NULL,
        total_chunks INTEGER NOT NULL,
        status TEXT NOT NULL,
        analysis_json TEXT,analysis_sha256 TEXT,
        manifest_sha256 TEXT,
        owner_id TEXT NOT NULL,
        finished_chunks INTEGER NOT NULL DEFAULT 0,
        finished_bytes INTEGER NOT NULL DEFAULT 0,
        issue TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        CHECK(status IN ('queued','analyzing','rendering','verifying',
                         'finalizing','completed','interrupted',
                         'cancelled','failed')))""")
    db.execute("""CREATE INDEX IF NOT EXISTS g09e_project_jobs
        ON g09e_jobs(project_id,created_at)""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09e_chunks(
        project_id TEXT NOT NULL,job_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        start_frame INTEGER NOT NULL,end_frame INTEGER NOT NULL,
        state TEXT NOT NULL,
        sha256 TEXT NOT NULL,size_bytes INTEGER NOT NULL,
        verification_json TEXT NOT NULL,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,job_id,chunk_index),
        CHECK(state='completed'))""")

def _folder(db_path,pid,jobid=None,create=False):
    if not HEX.fullmatch(pid) or jobid is not None and not HEX.fullmatch(jobid):
        raise ValueError("Choose your own recorded movie and film job")
    data=Path(db_path).resolve(strict=True)
    root=data.parent/"nvp_g09e_exports"
    project=root/pid
    folder=project/jobid if jobid is not None else project
    for candidate in (root,project,folder):
        if candidate.is_symlink():
            raise RuntimeError("A film export path is an unsafe symbolic link")
        if create:candidate.mkdir(parents=True,mode=0o700,exist_ok=True)
        if not candidate.is_dir() or candidate.resolve()!=candidate:
            raise RuntimeError("A source film export folder was replaced")
    return folder

def _json_file(path,*,limit=MAX_RECEIPT_BYTES):
    if path.is_symlink() or not path.is_file() or (
            not 1<=path.stat().st_size<=limit):
        raise RuntimeError("A fixed native worker receipt is missing")
    return json.loads(path.read_text(encoding="utf8"))

def _fsync_dir(path):
    if os.name=="nt":return
    fd=os.open(str(path),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

class G09ELongDelivery:
    def __init__(self,studio,*,access,protected_movie):
        self.studio=studio
        self.access=access
        self.protected_movie=protected_movie
        self.owner=uuid.uuid4().hex
        self.guard=threading.RLock()
        self.running={}
        self.procs={}
        self.revoked=set()
        self._reconciled=False

    @contextmanager
    def _db(self):
        with self.studio._connection() as db:
            _schema(db)
            yield db

    def _auth(self,pid,token):
        if type(pid) is not str or not HEX.fullmatch(pid):
            raise ValueError("Select an original film project")
        if not self.access().permitted(pid,token,renew=False):
            raise PermissionError("Open your film before rendering its long version")
        if self.protected_movie().exists(pid):
            raise PermissionError(
                "Long-film export from encrypted movies needs separately "
                "protected chunk custody. NVP will not expose an unlocked "
                "movie to an ordinary file or rendering worker.")

    def _heartbeat(self,pid,job):
        with self._db() as db:
            db.execute("""UPDATE g09e_jobs SET updated_at=?
                WHERE id=? AND project_id=? AND owner_id=? AND
                status IN ('analyzing','rendering','verifying','finalizing')""",
                (_now(),job,pid,self.owner))

    def _set(self,pid,job,status,*,expected=None,issue=None,analysis=None,
             manifest=None):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT status,owner_id FROM g09e_jobs
                WHERE id=? AND project_id=?""",(job,pid)).fetchone()
            if row is None:raise KeyError("Film render journal was removed")
            if expected is not None and row["status"] not in expected:
                raise RuntimeError("Film export state changed in another app window")
            if row["owner_id"]!=self.owner:
                raise RuntimeError("A different host owns this film operation")
            if row["status"]=="completed" and status!="completed":
                raise RuntimeError("A completed film cannot be reopened")
            additions=[]
            values=[]
            if analysis is not None:
                raw=_canonical(analysis)
                additions.extend(("analysis_json=?","analysis_sha256=?"))
                values.extend((raw.decode("utf8"),sha256(raw).hexdigest()))
            if manifest is not None:
                additions.append("manifest_sha256=?")
                values.append(manifest)
            db.execute("""UPDATE g09e_jobs SET
                status=?,updated_at=?,issue=?"""+
                (","+",".join(additions) if additions else "")+
                """ WHERE id=? AND project_id=? AND owner_id=?""",
                (status,_now(),issue,*values,job,pid,self.owner))

    def _job(self,pid,job):
        with self._db() as db:
            row=db.execute("""SELECT * FROM g09e_jobs
                WHERE id=? AND project_id=?""",(job,pid)).fetchone()
            if row is None:raise KeyError("No long-film rendering job exists")
            return dict(row)

    def reconcile(self):
        """Quarantine stale work; *never* silently resume after app restart."""
        with self.guard:
            with self._db() as db:
                jobs=[dict(row) for row in db.execute(
                    """SELECT id,project_id,owner_id,updated_at,status
                    FROM g09e_jobs WHERE status IN
                    ('queued','analyzing','rendering','verifying','finalizing')""")]
                for rec in jobs:
                    if rec["id"] in self.running:continue
                    try:
                        heartbeat=datetime.fromisoformat(rec["updated_at"])
                        age=(datetime.now(timezone.utc)-heartbeat).total_seconds()
                    except (ValueError,TypeError):age=STALE_SECONDS+1
                    if age<STALE_SECONDS:
                        continue # Another host may still be alive.
                    db.execute("""UPDATE g09e_jobs
                        SET status='interrupted',issue=?,updated_at=?
                        WHERE id=? AND project_id=? AND owner_id=? AND
                        status IN ('queued','analyzing','rendering',
                                   'verifying','finalizing')""",
                        ("Earlier rendering stopped unexpectedly; review and resume.",
                         _now(),rec["id"],rec["project_id"],rec["owner_id"]))
            self._reconciled=True

    def start(self,pid,expected_revision,token):
        self._auth(pid,token)
        self.reconcile()
        if type(expected_revision) is not int or expected_revision<=0:
            raise ValueError("Save your film edit before long rendering")
        editor=G07Editor(self.studio)
        current=editor.view(pid)
        if current["revision"]!=expected_revision or current["missing_sources"]:
            raise RuntimeError("Review and save the current complete original film")
        # Read only the first bounded original source window, then validate
        # the full G07 edit/Take SHA from the authoritative project records.
        first=editor.native_assembly(pid,expected_revision,
            window=(0,min(FRAMES_PER_CHUNK*TICKS_FRAME,
                 round(current["duration_seconds"]*FPS)*TICKS_FRAME)))
        frames=first["duration_tick"]//TICKS_FRAME
        if frames<=720:
            raise ValueError("Use ordinary short film export for the first 30 seconds")
        if not 1<=frames<=MAX_FRAMES or (
                first["duration_tick"]%TICKS_FRAME or
                first["duration_tick"]%TICKS_SAMPLE):
            raise ValueError("The source film must be at most three hours and whole-frame aligned")
        segments=math.ceil(frames/FRAMES_PER_CHUNK)
        if segments>MAX_CHUNKS:raise ValueError("Film has too many native reels")
        source=source_digests(first)
        fingerprint=sha256(_canonical(source)).hexdigest()
        folder=_folder(self.studio.db_path,pid,create=True)
        if shutil.disk_usage(folder).free<MIN_FREE_DISK:
            raise RuntimeError("Not enough local space to begin a long-film export")
        job=uuid.uuid4().hex
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("""SELECT 1 FROM g09e_jobs WHERE project_id=? AND
              status IN ('queued','analyzing','rendering','verifying',
                         'finalizing') LIMIT 1""",(pid,)).fetchone():
                raise RuntimeError("The current movie already has a long export")
            db.execute("""INSERT INTO g09e_jobs(
                id,project_id,edit_revision,source_json,source_sha256,
                total_frames,total_chunks,status,owner_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,'queued',?,?,?)""",
                (job,pid,expected_revision,_canonical(source).decode("utf8"),
                 fingerprint,frames,segments,self.owner,_now(),_now()))
        _folder(self.studio.db_path,pid,job,create=True)
        self._start_thread(pid,job,token)
        return self.read(pid,job,token)

    def _start_thread(self,pid,job,token):
        with self.guard:
            if job in self.running:
                raise RuntimeError("The original film is already being rendered")
            task=threading.Thread(target=self._perform,args=(pid,job,token),
                daemon=True,name="nvp-g09e-reels-"+job[:8])
            self.running[job]=task
            task.start()

    def resume(self,pid,job,token):
        self._auth(pid,token);self.reconcile()
        record=self._job(pid,job)
        if record["status"] not in RESUMABLE:
            raise RuntimeError("This film has not been interrupted or cancelled")
        if record["total_frames"]>MAX_FRAMES:
            raise RuntimeError("Long-film source exceeds its original profile")
        current=G07Editor(self.studio).view(pid)
        if current["revision"]!=record["edit_revision"] or current["missing_sources"]:
            raise RuntimeError("The film edit changed; create a new reviewed export")
        first=G07Editor(self.studio).native_assembly(
            pid,record["edit_revision"],
            window=(0,min(record["total_frames"],FRAMES_PER_CHUNK)*TICKS_FRAME))
        if sha256(_canonical(source_digests(first))).hexdigest()!=record["source_sha256"]:
            raise RuntimeError("The original film or approved finishing changed since this render")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("""SELECT 1 FROM g09e_jobs WHERE project_id=? AND
                status IN ('queued','analyzing','rendering','verifying','finalizing')
                LIMIT 1""",(pid,)).fetchone():
                raise RuntimeError("Another render of this film is active")
            db.execute("""UPDATE g09e_jobs
                SET status='queued',owner_id=?,updated_at=?,issue=NULL
                WHERE id=? AND project_id=? AND status IN
                ('interrupted','cancelled','failed')""",
                (self.owner,_now(),job,pid))
        with self.guard:self.revoked.discard(job)
        self._start_thread(pid,job,token)
        return self.read(pid,job,token)

    def _cmd(self,action,record,index):
        db=Path(self.studio.db_path).resolve(strict=True)
        fixed=["--db",str(db),"--project",record["project_id"],
               "--job",record["id"],"--index",str(index)]
        if getattr(sys,"frozen",False):
            return [str(Path(sys.executable).resolve(strict=True)),
                    "--g09e-worker",action,*fixed]
        # Fixed package script: never a browser-selected code path.
        package=Path(__file__).resolve().parents[1]/"tools"/"nvp_g09e_worker.py"
        if not package.is_file() or package.is_symlink():
            raise RuntimeError("The native reel worker is not installed")
        return [str(Path(sys.executable).resolve(strict=True)),"-B",
                "-m","tools.nvp_g09e_worker",action,*fixed]

    def _worker(self,action,record,index,token):
        pid=record["project_id"];job=record["id"]
        folder=_folder(self.studio.db_path,pid,job)
        if shutil.disk_usage(folder).free<MIN_FREE_DISK:
            raise RuntimeError("Local storage is too full to render another reel")
        path=folder/(f"{action}-{index if index>=0 else 'film'}.log")
        if path.is_symlink() or path.exists():
            path.unlink() if path.is_file() and not path.is_symlink() else None
        with open(path,"xb") as log:
            proc=launch_contained(self._cmd(action,record,index),
                cwd=str(Path(__file__).resolve().parents[1]),
                stdout=log,stderr=log,memory_mb=WORKER_MEMORY_MB,
                env=_sanitized_worker_env())
            with self.guard:self.procs[job]=proc
            try:
                deadline=time.monotonic()+(
                    3600 if action in ("analyze","finalize") else 1200)
                while proc.poll() is None:
                    with self.guard:cancelled=job in self.revoked
                    if cancelled or not self.access().permitted(
                            pid,token,renew=False):
                        proc.terminate_tree()
                        raise InterruptedError("The director stopped or locked the film")
                    if time.monotonic()>deadline:
                        proc.terminate_tree()
                        raise TimeoutError("Bounded native reel worker did not finish")
                    self._heartbeat(pid,job)
                    time.sleep(.5)
                if proc.wait(timeout=10)!=0:
                    with self.guard:
                        cancelled=job in self.revoked
                    if cancelled:
                        raise InterruptedError("The director stopped the native film worker")
                    raise RuntimeError("The contained film worker failed to verify its source")
            finally:
                try:proc.close()
                finally:
                    with self.guard:self.procs.pop(job,None)

    def _completed_chunks(self,pid,job):
        with self._db() as db:
            return {r["chunk_index"]:dict(r) for r in db.execute(
                """SELECT * FROM g09e_chunks WHERE project_id=? AND job_id=?""",
                (pid,job))}

    def _adopt_or_verify_completed(self,record,index,parts):
        pid=record["project_id"];job=record["id"]
        start,end=chunk_bounds(record["total_frames"],index)
        folder=_folder(self.studio.db_path,pid,job)
        source=folder/f"reel-{index:05d}.avi"
        already=parts.get(index)
        if already is not None:
            if (already["start_frame"]!=start or already["end_frame"]!=end or
                not SHA.fullmatch(already["sha256"] or "") or
                source.is_symlink() or not source.is_file() or
                source.stat().st_size!=already["size_bytes"]):
                raise RuntimeError("A prior verified reel cannot be recovered")
            receipt=json.loads(already["verification_json"])
            if receipt.get("file_sha256")!=already["sha256"] or (
                receipt.get("source_sha256")!=record["source_sha256"]):
                raise RuntimeError("Reel custody receipt is no longer valid")
            inspect_reel(source,end-start,expected_sha=already["sha256"])
            return True
        if not source.exists() and not source.is_symlink():return False
        # Crash between verified file link and SQLite completion:
        # independently reopen the already-verified candidate before
        # re-adopting. Never adopt based on filename alone.
        verified=_json_file(folder/f"reel-{index:05d}.verify.json")
        if (verified.get("source_sha256")!=record["source_sha256"] or
            verified.get("index")!=index or verified.get("verified") is not True or
            not SHA.fullmatch(verified.get("file_sha256",""))):
            raise RuntimeError("Orphaned completed reel has no trustworthy provenance")
        inspect_reel(source,end-start,expected_sha=verified["file_sha256"])
        self._complete_chunk(record,index,verified,source)
        return True

    def _complete_chunk(self,record,index,verified,final):
        start,end=chunk_bounds(record["total_frames"],index)
        if (verified.get("source_sha256")!=record["source_sha256"] or
            verified.get("index")!=index or
            verified.get("frames")!=end-start or
            verified.get("audio_samples")!=(end-start)*2000 or
            verified.get("verified") is not True):
            raise RuntimeError("The film reel does not have a verified native source")
        if final.is_symlink() or not final.is_file() or (
                sha256(final.read_bytes()).hexdigest()!=verified["file_sha256"]):
            raise RuntimeError("The native reel changed after independent verification")
        raw=_canonical(verified).decode("utf8");now=_now()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT status,source_sha256 FROM g09e_jobs
                WHERE id=? AND project_id=?""",
                (record["id"],record["project_id"])).fetchone()
            if (not row or row["source_sha256"]!=record["source_sha256"] or
                row["status"] not in ACTIVE):
                raise RuntimeError("Reel publication is no longer authorized")
            db.execute("""INSERT INTO g09e_chunks(
                project_id,job_id,chunk_index,start_frame,end_frame,
                state,sha256,size_bytes,verification_json,created_at,updated_at)
                VALUES (?,?,?,?,?,'completed',?,?,?,?,?)""",
                (record["project_id"],record["id"],index,start,end,
                 verified["file_sha256"],final.stat().st_size,raw,now,now))
            db.execute("""UPDATE g09e_jobs SET
                finished_chunks=(SELECT count(*) FROM g09e_chunks
                    WHERE project_id=? AND job_id=?),
                finished_bytes=(SELECT COALESCE(sum(size_bytes),0)
                    FROM g09e_chunks WHERE project_id=? AND job_id=?),
                updated_at=? WHERE id=? AND project_id=?""",
                (record["project_id"],record["id"],
                 record["project_id"],record["id"],now,
                 record["id"],record["project_id"]))

    def _cleanup_partial(self,folder,index):
        # Only fixed unverified transient names. Never remove a committed
        # completed reel, unknown user file or frozen source!
        name=f"reel-{index:05d}"
        for ext in (".partial.avi",".render.json",".verify.json"):
            path=folder/(name+ext)
            if path.is_symlink():
                raise RuntimeError("Untrusted film candidate link")
            if path.is_file():path.unlink()

    def _perform(self,pid,job,token):
        try:
            record=self._job(pid,job)
            self._auth(pid,token)
            folder=_folder(self.studio.db_path,pid,job)
            if not record["analysis_json"]:
                existing=folder/"analysis-result.json"
                if existing.is_symlink():
                    raise RuntimeError("The sound receipt is an unsafe link")
                if existing.exists():existing.unlink()
                self._set(pid,job,"analyzing",expected={"queued"})
                self._worker("analyze",record,-1,token)
                analysis=_json_file(existing)
                if (analysis.get("format")!="nvp.g09e.analysis.v1" or
                    analysis.get("source_sha256")!=record["source_sha256"] or
                    analysis.get("total_frames")!=record["total_frames"] or
                    sha256(_canonical(analysis["sound_plan"])).hexdigest()!=
                        analysis["sound_plan_sha256"]):
                    raise RuntimeError("Film sound analysis did not match its original")
                self._set(pid,job,"rendering",analysis=analysis,
                    expected={"analyzing"})
                record=self._job(pid,job)
            else:
                report=json.loads(record["analysis_json"])
                if (sha256(_canonical(report)).hexdigest()!=
                        record["analysis_sha256"] or
                    report["source_sha256"]!=record["source_sha256"]):
                    raise RuntimeError("The film-wide mastering plan was changed")
                self._set(pid,job,"rendering",expected={"queued"})
            for i in range(record["total_chunks"]):
                with self.guard:
                    if job in self.revoked:raise InterruptedError()
                self._auth(pid,token)
                parts=self._completed_chunks(pid,job)
                if self._adopt_or_verify_completed(record,i,parts):
                    continue
                if sum(r["size_bytes"] for r in parts.values())+MAX_CHUNK_BYTES>MAX_OUTPUT_BYTES:
                    raise RuntimeError("The 32GiB film quota requires a smaller delivery profile")
                self._cleanup_partial(folder,i)
                self._worker("render",record,i,token)
                self._set(pid,job,"verifying",expected={"rendering"})
                self._worker("verify",record,i,token)
                verify=_json_file(folder/f"reel-{i:05d}.verify.json")
                partial=folder/f"reel-{i:05d}.partial.avi"
                final=folder/f"reel-{i:05d}.avi"
                if final.exists() or final.is_symlink():
                    raise RuntimeError("A previously finished reel occupies this source time")
                inspect_reel(partial,chunk_bounds(record["total_frames"],i)[1]-
                             chunk_bounds(record["total_frames"],i)[0],
                             expected_sha=verify["file_sha256"])
                os.link(partial,final,follow_symlinks=False)
                _fsync_dir(folder)
                self._complete_chunk(record,i,verify,final)
                partial.unlink(missing_ok=True)
                self._set(pid,job,"rendering",expected={"verifying"})
            self._set(pid,job,"finalizing",expected={"rendering"})
            candidate=folder/"candidate-manifest.json"
            if candidate.is_symlink():raise RuntimeError("Unsafe finished manifest")
            if candidate.exists():candidate.unlink()
            self._worker("finalize",record,-1,token)
            manifest=_json_file(candidate)
            if (manifest.get("format")!="nvp.g09e.native_reels.v1" or
                manifest.get("source_sha256")!=record["source_sha256"] or
                manifest.get("total_frames")!=record["total_frames"] or
                manifest.get("reel_count")!=record["total_chunks"] or
                manifest.get("not_a_single_gapless_media_file") is not True):
                raise RuntimeError("The full movie had an invalid source/clock manifest")
            self._auth(pid,token)
            final=folder/"manifest.json"
            if final.is_symlink():
                raise RuntimeError("A finished film index is an unsafe symbolic link")
            if final.exists():
                # Process died after hard-link publication but before the
                # SQLite completed transaction. Re-run the independent
                # finalizer and ONLY adopt exactly identical verified bytes.
                if sha256(final.read_bytes()).hexdigest()!=sha256(
                        candidate.read_bytes()).hexdigest():
                    raise RuntimeError("Orphaned finished film differs from the independently reverified manifest")
            else:
                os.link(candidate,final,follow_symlinks=False)
                _fsync_dir(folder)
            sha=sha256(final.read_bytes()).hexdigest()
            self._set(pid,job,"completed",manifest=sha,expected={"finalizing"})
            candidate.unlink(missing_ok=True)
        except InterruptedError:
            try:self._set(pid,job,"cancelled",issue="Director stopped the film; previously checked reels remain safe.")
            except Exception:pass
        except (TimeoutError,PermissionError):
            try:self._set(pid,job,"interrupted",
                issue="Rendering stopped or the film locked. Checked reels can be reviewed and resumed.")
            except Exception:pass
        except Exception:
            try:self._set(pid,job,"failed",
                issue="One part of the film did not pass source, rendering or output checks.")
            except Exception:pass
        finally:
            with self.guard:
                self.running.pop(job,None);self.procs.pop(job,None)
                self.revoked.discard(job)

    def read(self,pid,job,token):
        self._auth(pid,token);self.reconcile()
        record=self._job(pid,job)
        folder=_folder(self.studio.db_path,pid,job)
        progress=None
        status=record["status"]
        if status in ACTIVE:
            try:progress=_json_file(folder/"progress.json",limit=4096)
            except (RuntimeError,ValueError,OSError):pass
        return {
            "id":job,"format":FORMAT,"status":status,
            "duration_seconds":record["total_frames"]/FPS,
            "frames_total":record["total_frames"],
            "reels_total":record["total_chunks"],
            "reels_verified":record["finished_chunks"],
            "reels_bytes":record["finished_bytes"],
            "progress_percent":round(
                record["finished_chunks"]/max(1,record["total_chunks"])*100,2),
            "phase":progress.get("status") if progress else status,
            "issue":record["issue"],"resumable":status in RESUMABLE,
            "source_sha256":record["source_sha256"],
            "manifest_sha256":record["manifest_sha256"] if status=="completed" else None,
            "completed":status=="completed",
            "original_takes_preserved":True,
            "format_is_segmented_working_avi":True,
            "genuine_feature_length_acceptance_passed":False,
            "encrypted_project_supported":False}

    def list(self,pid,token):
        self._auth(pid,token);self.reconcile()
        with self._db() as db:
            records=list(db.execute("""SELECT id FROM g09e_jobs
                WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 30""",
                (pid,)))
        return [self.read(pid,r["id"],token) for r in records]

    def cancel(self,pid,job,token):
        self._auth(pid,token)
        record=self._job(pid,job)
        if record["status"] not in ACTIVE:
            raise RuntimeError("This film operation is not running")
        with self.guard:
            self.revoked.add(job)
            proc=self.procs.get(job)
            if proc:proc.terminate_tree()
        # The owned runner marks cancelled; do not counterfeit a worker exit
        # or mark a half-written reel as a completed source.
        return self.read(pid,job,token)

    def _completed(self,pid,job,token):
        item=self.read(pid,job,token)
        if item["status"]!="completed":
            raise RuntimeError("Only an independently verified completed film is available")
        folder=_folder(self.studio.db_path,pid,job)
        p=folder/"manifest.json"
        if p.is_symlink() or not p.is_file() or (
                sha256(p.read_bytes()).hexdigest()!=item["manifest_sha256"]):
            raise RuntimeError("The completed long-film manifest changed")
        return folder,_json_file(p)

    def manifest(self,pid,job,token):
        _,manifest=self._completed(pid,job,token)
        return manifest

    def reel_path(self,pid,job,index,token):
        folder,manifest=self._completed(pid,job,token)
        if type(index) is not int or not 0<=index<manifest["reel_count"]:
            raise KeyError("That scene reel does not exist")
        item=manifest["reels"][index]
        if item["index"]!=index or item["path"]!=f"reel-{index:05d}.avi":
            raise RuntimeError("The original film reel index was changed")
        path=folder/item["path"]
        if (path.is_symlink() or not path.is_file() or
            path.stat().st_size!=item["bytes"] or
            sha256(path.read_bytes()).hexdigest()!=item["sha256"]):
            raise RuntimeError("The completed film reel failed authenticated readback")
        return path
