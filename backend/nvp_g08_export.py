"""G08 NVP-owned native movie export host: custody, receipts and recovery.

Only ordinary (non-encrypted) film output is allowed through a filesystem
worker until the separately required G03 sealed worker custody path is ready.
No browser-selected executable/path, no automatic model export authority,
no shell, no FFmpeg. All work uses an exact G07 edit-source digest.
Runtime reconciles incomplete jobs to INTERRUPTED and never invents a
successful movie based merely on a leftover candidate file.

A first completed G08 movie is a real bounded MJPEG+PCM16 AVI. This is NOT
a ProRes/DCP mastering claim or a full-length production renderer.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from backend.nvp_g07_edit import G07Editor
from backend.nvp_g08_native_avi import (
    PROFILE,WIDTH,HEIGHT,FPS,TICKS_FRAME,TICKS_SAMPLE,
    MAX_SECONDS,MAX_OUTPUT_BYTES)
from backend.nvp_worker_containment import launch_contained
from backend.nvp_g03_protected_scene_supervisor import _sanitized_worker_env

HEX=re.compile(r"[0-9a-f]{32}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")
ACTIVE={"queued","rendering","verifying"}
FINISHED={"completed","cancelled","failed","interrupted"}


def _now():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g08_export_jobs(
      id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
      edit_revision INTEGER NOT NULL,edit_sha256 TEXT NOT NULL,
      look_sha256 TEXT NOT NULL DEFAULT '',
      expected_frames INTEGER NOT NULL,status TEXT NOT NULL,
      progress_frames INTEGER NOT NULL DEFAULT 0,
      output_sha256 TEXT,output_bytes INTEGER,receipt_json TEXT,
      issue TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
      CHECK(status IN ('queued','rendering','verifying','completed',
                       'cancelled','failed','interrupted')))""")
    db.execute("""CREATE INDEX IF NOT EXISTS g08_project_jobs
       ON g08_export_jobs(project_id,created_at)""")
    if "look_sha256" not in {
         r["name"] for r in db.execute("PRAGMA table_info(g08_export_jobs)") }:
        db.execute("ALTER TABLE g08_export_jobs ADD COLUMN look_sha256 TEXT NOT NULL DEFAULT ''")


def _folder(db_path,pid):
    if type(pid) is not str or not HEX.fullmatch(pid):
        raise ValueError("Select a movie from your projects")
    root=Path(db_path).resolve(strict=True).parent/"nvp_g08_exports"
    if root.is_symlink():raise RuntimeError("Export directory is untrusted")
    root.mkdir(mode=0o700,exist_ok=True)
    folder=root/pid
    if folder.is_symlink():raise RuntimeError("Movie export directory is untrusted")
    folder.mkdir(mode=0o700,exist_ok=True)
    return folder


def _safe_file(path):
    path=Path(path)
    if path.is_symlink():raise RuntimeError("Movie export has an unsafe file link")
    if not path.is_file():raise FileNotFoundError("Movie export does not exist")
    return path


def _fsync_folder(folder):
    if os.name=="nt":return
    fd=os.open(str(folder),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _receipt(path,maximum=4096):
    raw=_safe_file(path).read_bytes()
    if not 5<=len(raw)<=maximum:
        raise RuntimeError("Native movie receipt is incomplete")
    return json.loads(raw)


class G08MovieExporter:
    def __init__(self,studio,*,access,protected_movie):
        self.studio=studio
        self.access=access
        self.protected_movie=protected_movie
        self._guard=threading.RLock()
        self._running={}
        self._procs={}
        self._revoked=set()
        self._reconciled=False

    @contextmanager
    def _db(self):
        with self.studio._connection() as db:
            _schema(db)
            yield db

    def _check_movie(self,pid,token):
        if type(pid) is not str or not HEX.fullmatch(pid):
            raise ValueError("Select a valid movie")
        if not self.access().permitted(pid,token,renew=False):
            raise PermissionError("Open and unlock the film before exporting it")
        if self.protected_movie().exists(pid):
            # Protected movies must never have their plaintext USD/PCM staged
            # by an ordinary user-privileged movie worker or disk exporter.
            raise PermissionError(
                "Secure movie delivery is not yet available on this installation. " +
                "Your original film remains protected.")

    def reconcile(self):
        with self._guard:
            if self._reconciled:return
            with self._db() as db:
                pending=db.execute("""SELECT id,project_id FROM g08_export_jobs
                  WHERE status IN ('queued','rendering','verifying')""").fetchall()
                for record in pending:
                    if record["id"] in self._running:continue
                    db.execute("""UPDATE g08_export_jobs SET status='interrupted',
                      issue='An earlier export was interrupted; start it again.',
                      updated_at=? WHERE id=?""",(_now(),record["id"]))
                    try:
                        folder=_folder(self.studio.db_path,record["project_id"])
                        # Do not touch a completed final movie; if it was not
                        # independently verified it must remain unpublished.
                        for name in (record["id"]+".partial.avi",
                                     record["id"]+".avi"):
                            path=folder/name
                            if path.exists() and not path.is_symlink():
                                path.unlink()
                    except OSError:
                        pass
            self._reconciled=True

    def prepare(self,pid,expected_revision,token):
        self.reconcile()
        self._check_movie(pid,token)
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("Save a film edit before exporting")
        # The trusted host reads the immutable source itself. Neither a model
        # nor the WebView can supply source media or an output path.
        assembly=G07Editor(self.studio).native_assembly(pid,expected_revision)
        if assembly["edit_revision"]!=expected_revision or (
                not SHA.fullmatch(assembly["edit_document_sha256"]) or
                not SHA.fullmatch(assembly["production_looks_sha256"])):
            raise RuntimeError("The saved edit is not current")
        total=assembly["duration_tick"]
        if (not 0<total<=MAX_SECONDS*TICKS_FRAME*FPS or
                total%TICKS_FRAME or total%TICKS_SAMPLE):
            raise ValueError(
                "First delivery requires a movie of 30 seconds or less, " +
                "trimmed to a whole frame at 24 frames/second")
        if not assembly["segments"]:
            raise ValueError("Add at least one recorded Take to your film")
        with self._db() as db:
            # Exactly one movie export at a time even across two independent
            # NVP hosts. SELECT + publication share SQLite writer custody.
            db.execute("BEGIN IMMEDIATE")
            queued=db.execute("""SELECT id FROM g08_export_jobs
                WHERE project_id=? AND status IN ('queued','rendering','verifying')
                LIMIT 1""",(pid,)).fetchone()
            if queued:
                raise RuntimeError("This movie is already being exported")
            job=uuid.uuid4().hex
            folder=_folder(self.studio.db_path,pid)
            if (folder/(job+".avi")).exists() or (
                    folder/(job+".partial.avi")).exists():
                raise RuntimeError("Movie export destination collision")
            db.execute("""INSERT INTO g08_export_jobs
                (id,project_id,edit_revision,edit_sha256,look_sha256,expected_frames,
                status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'queued',?,?)""",
                (job,pid,expected_revision,
                 assembly["edit_document_sha256"],
                 assembly["production_looks_sha256"],total//TICKS_FRAME,
                 _now(),_now()))
        thread=threading.Thread(target=self._perform,
             args=(pid,job,token),daemon=True,name="nvp-g08-"+job[:8])
        with self._guard:self._running[job]=thread
        thread.start()
        return self.read(pid,job,token)

    def _set(self,pid,job,status,*,progress=None,sha=None,size=None,
             receipt=None,issue=None,expected=None):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT status FROM g08_export_jobs
                WHERE id=? AND project_id=?""",(job,pid)).fetchone()
            if row is None:raise KeyError("Movie export job is missing")
            if expected is not None and row["status"] not in expected:
                raise RuntimeError("Export changed while processing")
            if row["status"] in FINISHED and status!=row["status"]:
                raise RuntimeError("A finished export cannot be reopened")
            db.execute("""UPDATE g08_export_jobs SET status=?,
                progress_frames=COALESCE(?,progress_frames),
                output_sha256=COALESCE(?,output_sha256),
                output_bytes=COALESCE(?,output_bytes),
                receipt_json=COALESCE(?,receipt_json),
                issue=COALESCE(?,issue),updated_at=?
                WHERE id=? AND project_id=?""",
                (status,progress,sha,size,
                 json.dumps(receipt,sort_keys=True) if receipt else None,
                 issue,_now(),job,pid))

    @staticmethod
    def _command(action,studio,pid,job,record,folder):
        if getattr(sys,"frozen",False):
            # Installed native launcher must explicitly route this reviewed
            # subcommand; never fall back to an uncontained subprocess.
            return [str(Path(sys.executable).resolve(strict=True)),
                    "--g08-export-worker",action,
                    "--db",str(Path(studio.db_path).resolve(strict=True)),
                    "--project",pid,"--job",job,
                    "--revision",str(record["edit_revision"]),
                    "--edit-sha",record["edit_sha256"],
                    "--looks-sha",record["look_sha256"],
                    "--frames",str(record["expected_frames"]),
                    "--output-sha",record["output_sha256"] or "",
                    "--progress",str(folder/(job+".progress.json")),
                    "--receipt",str(folder/(job+(
                        ".render.json" if action=="render" else ".verify.json")))]
        reviewed=Path(__file__).resolve().parents[1]/"tools"/"nvp_g08_export_worker.py"
        if not reviewed.is_file() or reviewed.is_symlink():
            raise RuntimeError("NVP's fixed native exporter is not installed")
        return [str(Path(sys.executable).resolve(strict=True)),"-B",
                "-m","tools.nvp_g08_export_worker",action,
                "--db",str(Path(studio.db_path).resolve(strict=True)),
                "--project",pid,"--job",job,
                "--revision",str(record["edit_revision"]),
                "--edit-sha",record["edit_sha256"],
                "--looks-sha",record["look_sha256"],
                "--frames",str(record["expected_frames"]),
                "--output-sha",record["output_sha256"] or "",
                "--progress",str(folder/(job+".progress.json")),
                "--receipt",str(folder/(job+(
                    ".render.json" if action=="render" else ".verify.json")))]

    def _run_worker(self,action,pid,job,folder,record):
        command=self._command(action,self.studio,pid,job,record,folder)
        log=folder/(job+"."+action+".log")
        # Job Object (Windows), parent-custodied process group (Linux).
        # No shell; executable and reviewed script path fixed by the host.
        with open(log,"xb") as stdout:
            proc=launch_contained(command,cwd=str(Path(__file__).resolve().parents[1]),
                stdout=stdout,stderr=stdout,memory_mb=0,
                env=_sanitized_worker_env())
            with self._guard:self._procs[job]=proc
            try:
                stop=time.monotonic()+900
                while proc.poll() is None:
                    with self._guard:
                        cancelled=job in self._revoked
                    if cancelled:
                        proc.terminate_tree()
                        raise InterruptedError("Export cancelled by the director")
                    if time.monotonic()>stop:
                        proc.terminate_tree()
                        raise TimeoutError("Export exceeded its bounded runtime")
                    time.sleep(.2)
                code=proc.wait(timeout=5)
                if code!=0:
                    raise RuntimeError(
                        "NVP could not finish rendering or independently reopening this film")
            finally:
                try:proc.close()
                finally:
                    with self._guard:self._procs.pop(job,None)

    def _perform(self,pid,job,token):
        folder=None
        partial=None
        final=None
        try:
            folder=_folder(self.studio.db_path,pid)
            partial=folder/(job+".partial.avi")
            final=folder/(job+".avi")
            with self._db() as db:
                record=dict(db.execute("""SELECT * FROM g08_export_jobs
                    WHERE id=? AND project_id=?""",(job,pid)).fetchone())
            with self._guard:
                if job in self._revoked:raise InterruptedError()
            self._check_movie(pid,token)
            self._set(pid,job,"rendering",expected={"queued"})
            self._run_worker("render",pid,job,folder,record)
            with self._guard:
                if job in self._revoked:raise InterruptedError()
            self._check_movie(pid,token)
            render_receipt=_receipt(folder/(job+".render.json"))
            if (render_receipt.get("job_id")!=job or
                render_receipt.get("edit_sha256")!=record["edit_sha256"] or
                render_receipt.get("approved_look_sha256")!=record["look_sha256"] or
                render_receipt.get("frames")!=record["expected_frames"] or
                not SHA.fullmatch(render_receipt.get("sha256","")) or
                render_receipt.get("ffmpeg_used") is not False):
                raise RuntimeError("Export picture/sound receipt is not valid")
            actual_sha=sha256(_safe_file(partial).read_bytes()).hexdigest()
            if actual_sha!=render_receipt["sha256"]:
                raise RuntimeError("Rendered movie bytes differ from worker receipt")
            self._set(pid,job,"verifying",progress=record["expected_frames"],
                      sha=actual_sha,size=partial.stat().st_size,
                      expected={"rendering"})
            # No final movie name is published before an independent
            # verifier has decoded and inspected the complete candidate.
            record["output_sha256"]=actual_sha
            self._run_worker("verify",pid,job,folder,record)
            verified=_receipt(folder/(job+".verify.json"))
            if (not verified.get("verified") or
                verified.get("sha256")!=actual_sha or
                verified.get("frames")!=record["expected_frames"] or
                verified.get("audio_samples_per_channel")!=
                    record["expected_frames"]*2000):
                raise RuntimeError("Rendered movie failed independent readback")
            with self._guard:
                if job in self._revoked:raise InterruptedError()
            self._check_movie(pid,token)
            # No-overwrite publish on the SAME filesystem. A hostile
            # preexisting filename or link can never be silently replaced.
            if final.exists() or final.is_symlink():
                raise RuntimeError("A finished movie path is already occupied")
            os.link(partial,final,follow_symlinks=False)
            _fsync_folder(folder)
            self._set(pid,job,"completed",progress=record["expected_frames"],
                      sha=actual_sha,size=verified["bytes"],receipt=verified,
                      expected={"verifying"})
            partial.unlink(missing_ok=True)
        except InterruptedError:
            try:
                with self._db() as db:
                    state=db.execute("""SELECT status FROM g08_export_jobs
                        WHERE id=?""",(job,)).fetchone()
                if state and state["status"]!="cancelled":
                    self._set(pid,job,"cancelled",issue="Movie export cancelled")
            except Exception:pass
        except Exception:
            try:
                with self._db() as db:
                    state=db.execute("""SELECT status FROM g08_export_jobs
                        WHERE id=?""",(job,)).fetchone()
                if state and state["status"] not in {"cancelled","interrupted"}:
                    self._set(pid,job,"failed",
                        issue="Movie export did not complete; your original recordings are safe.")
            except Exception:pass
        finally:
            for file in (partial,final):
                if file is None:continue
                # A delivered file is not removed on successful completion.
                try:
                    with self._db() as db:
                        status=db.execute("""SELECT status FROM g08_export_jobs
                            WHERE id=?""",(job,)).fetchone()
                    if (status is None or status["status"]!="completed") and (
                            file.exists() and not file.is_symlink()):
                        file.unlink()
                except (OSError,KeyError):
                    pass
            with self._guard:
                self._procs.pop(job,None)
                self._running.pop(job,None)
                self._revoked.discard(job)

    def read(self,pid,job,token):
        self.reconcile()
        self._check_movie(pid,token)
        if not isinstance(job,str) or not HEX.fullmatch(job):
            raise ValueError("Select an existing movie export")
        with self._db() as db:
            row=db.execute("""SELECT * FROM g08_export_jobs
                WHERE id=? AND project_id=?""",(job,pid)).fetchone()
            if row is None:raise KeyError("Movie export was not found")
            record=dict(row)
        if record["status"]=="rendering":
            progress=_folder(self.studio.db_path,pid)/(job+".progress.json")
            try:
                state=_receipt(progress,2048)
                if (state.get("job_id")==job and
                    state.get("edit_sha256")==record["edit_sha256"] and
                    type(state.get("frames_completed")) is int):
                    record["progress_frames"]=min(
                        record["expected_frames"],max(
                            record["progress_frames"],state["frames_completed"]))
            except (OSError,ValueError,RuntimeError):
                pass
        return {"id":job,"edit_revision":record["edit_revision"],
            "status":record["status"],"frames_completed":record["progress_frames"],
            "frames_total":record["expected_frames"],
            "progress_percent":round(100*record["progress_frames"]/
                                      max(1,record["expected_frames"]),1),
            "duration_seconds":record["expected_frames"]/FPS,
            "profile":PROFILE,"issue":record["issue"],
            "output_sha256":record["output_sha256"] if
                record["status"]=="completed" else None,
            "output_bytes":record["output_bytes"] if
                record["status"]=="completed" else None,
            "verified":record["status"]=="completed",
            "download_url":"/api/projects/"+pid+"/export/"+job+"/movie"
                if record["status"]=="completed" else None,
            "original_sources_preserved":True}

    def list(self,pid,token):
        self.reconcile()
        self._check_movie(pid,token)
        with self._db() as db:
            jobs=db.execute("""SELECT id FROM g08_export_jobs
                WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 25""",
                (pid,)).fetchall()
        return [self.read(pid,x["id"],token) for x in jobs]

    def cancel(self,pid,job,token):
        self.reconcile()
        self._check_movie(pid,token)
        with self._guard:
            with self._db() as db:
                row=db.execute("""SELECT status FROM g08_export_jobs
                    WHERE id=? AND project_id=?""",(job,pid)).fetchone()
                if row is None:raise KeyError("Movie export not found")
                if row["status"] not in ACTIVE:
                    raise RuntimeError("This movie export is not active")
            self._revoked.add(job)
            proc=self._procs.get(job)
            if proc:
                proc.terminate_tree()
            self._set(pid,job,"cancelled",issue="Export cancelled by director",
                      expected=ACTIVE)
        return self.read(pid,job,token)

    def cancel_project(self,pid):
        with self._guard:
            jobs=[]
            with self._db() as db:
                jobs=[row["id"] for row in db.execute(
                    """SELECT id FROM g08_export_jobs WHERE project_id=?
                       AND status IN ('queued','rendering','verifying')""",(pid,))]
            for job in jobs:
                self._revoked.add(job)
                proc=self._procs.get(job)
                if proc:
                    try:proc.terminate_tree()
                    except OSError:pass
                try:self._set(pid,job,"cancelled",
                        issue="Movie locked during export",expected=ACTIVE)
                except Exception:pass

    def movie_path(self,pid,job,token):
        info=self.read(pid,job,token)
        if not info["verified"]:
            raise RuntimeError("This movie has not passed independent verification")
        path=_safe_file(_folder(self.studio.db_path,pid)/(job+".avi"))
        if (path.stat().st_size!=info["output_bytes"] or
            sha256(path.read_bytes()).hexdigest()!=info["output_sha256"]):
            raise RuntimeError("Published movie bytes failed their source receipt")
        return path
