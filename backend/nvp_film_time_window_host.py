"""INDEX-TIME-03 trusted native host adapter for imported film-time windows.

No new execution engine: delegates authorization to ApprovedTaskBindings,
resource accounting to TaskLedger, containment to launch_contained, and
cancellation/pressure observation to wait_guarded. A task is not proof of a
creator-approved film. Both modes produce unapproved review PNGs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_film_time_window_preflight import FilmTimeWindowPreflight
from backend.nvp_film_time_window_decode import verify_film_time_window
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_source_window_decode import _sha_file
from backend.nvp_worker_containment import launch_contained

TABLE = "nvp_native_film_time_window_grants"


class NativeFilmTimeWindowHost:
    def __init__(self, preflight: FilmTimeWindowPreflight, ledger: TaskLedger,
                 root: Path, *, verify_creator_action,
                 ffmpeg_path=None, ffprobe_path=None, index_root=None):
        if (not isinstance(preflight,FilmTimeWindowPreflight) or
            not isinstance(ledger,TaskLedger) or
            not callable(verify_creator_action)):
            raise TypeError("Trusted film-time host needs preflight, ledger and creator policy")
        self.preflight = preflight
        self.ledger = ledger
        self.creator = verify_creator_action
        home = Path(root)
        if home.is_symlink() or (home.exists() and not home.is_dir()):
            raise RuntimeError("Unsafe native task workspace")
        home.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root = home.resolve()
        self.python = Path(sys.executable).resolve()
        self.script = Path(__file__).resolve().parents[1]/"tools"/"nvp_source_window_worker.py"
        self.ffmpeg = Path(ffmpeg_path or shutil.which("ffmpeg") or "")
        self.ffprobe = Path(ffprobe_path or shutil.which("ffprobe") or "")
        for executable in (self.python,self.script,self.ffmpeg,self.ffprobe):
            if (not executable.is_absolute() or executable.is_symlink() or
                not executable.is_file()):
                raise RuntimeError("Explicit native executable or source-window worker missing")
        self.ffmpeg=self.ffmpeg.resolve()
        self.ffprobe=self.ffprobe.resolve()
        cache=Path(index_root) if index_root is not None else self.root/"source_index_cache"
        if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
            raise RuntimeError("Unsafe indexed source cache")
        cache.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.index_root=cache.resolve()
        self.source_db=preflight.publisher.index.studio.db_path.resolve()
        self.owner="filmtime_"+hashlib.sha256(
            (str(self.root)+"|"+str(self.source_db)).encode()).hexdigest()[:20]
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nvp_native_film_time_window_grants (
                task_id TEXT PRIMARY KEY,
                approval_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL,
                edit_id TEXT NOT NULL,
                edit_revision INTEGER NOT NULL,
                edit_sha TEXT NOT NULL,
                clip_ordinal INTEGER NOT NULL,
                first_zero INTEGER NOT NULL,
                frame_count INTEGER NOT NULL,
                mode TEXT NOT NULL,
                destination TEXT NOT NULL,
                source_db TEXT NOT NULL,
                plan_sha TEXT NOT NULL,
                spec_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL,
                script_sha TEXT NOT NULL,
                ffmpeg_sha TEXT NOT NULL,
                ffprobe_sha TEXT NOT NULL,
                ffmpeg_path TEXT NOT NULL,
                ffprobe_path TEXT NOT NULL,
                index_cache_root TEXT NOT NULL,
                ram_mb INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                result_sha TEXT
            )""")
        self.binding=ApprovedTaskBindings(self.ledger,approval_check=self._check)

    def _row(self,task):
        with self.ledger._db() as db:
            db.row_factory=__import__("sqlite3").Row
            row=db.execute("SELECT * FROM "+TABLE+" WHERE task_id=?",
                           (task,)).fetchone()
        if row is None:
            raise KeyError("No native film-time source job grant")
        return dict(row)

    def _plan(self,task,row):
        path=self.root/task/"window_plan.json"
        if path.is_symlink() or not path.is_file() or _sha_file(path)!=row["plan_sha"]:
            raise RuntimeError("Native film-time plan absent or changed")
        raw=path.read_bytes()
        plan=json.loads(raw)
        if raw!=canonical_bytes(plan):
            raise RuntimeError("Native film-time plan is not canonical")
        if any((
            plan.get("project_id")!=row["project_id"],
            plan.get("edit_id")!=row["edit_id"],
            plan.get("edit_revision")!=row["edit_revision"],
            plan.get("edit_document_sha256")!=row["edit_sha"],
            plan.get("clip_ordinal")!=row["clip_ordinal"],
            plan.get("first_source_frame_zero")!=row["first_zero"],
            plan.get("frame_count")!=row["frame_count"],
            plan.get("mode")!=row["mode"],
        )):
            raise RuntimeError("Task grant and sealed editorial plan disagree")
        return plan

    def _check(self,approval,digest,doc):
        try:
            with self.ledger._db() as db:
                found=db.execute("SELECT task_id FROM "+TABLE+
                                 " WHERE approval_id=?",(approval,)).fetchone()
            if found is None:
                return False
            row=self._row(found[0])
            if any((
                row["revoked_at"] is not None,
                time.time()>row["expires_at"],
                digest!=row["spec_sha"],
                hashlib.sha256(canonical_bytes(doc)).hexdigest()!=digest,
                doc.get("task_id")!=row["task_id"],
                doc.get("kind")!="compositing",
                doc.get("operation")!="nvp.native.film_time.review.v1",
                doc.get("edit_sha")!=row["edit_sha"],
                doc.get("clip_ordinal")!=row["clip_ordinal"],
                doc.get("first_zero")!=row["first_zero"],
                doc.get("frame_count")!=row["frame_count"],
                doc.get("mode")!=row["mode"],
                doc.get("destination")!=row["destination"],
                doc.get("ram_mb")!=row["ram_mb"],
                doc.get("source_db")!=row["source_db"],
                doc.get("plan_sha")!=row["plan_sha"],
                doc.get("python_sha")!=row["python_sha"],
                doc.get("script_sha")!=row["script_sha"],
                doc.get("ffmpeg_sha")!=row["ffmpeg_sha"],
                doc.get("ffprobe_sha")!=row["ffprobe_sha"],
                doc.get("ffmpeg_path")!=row["ffmpeg_path"],
                doc.get("ffprobe_path")!=row["ffprobe_path"],
                doc.get("index_cache_root")!=row["index_cache_root"],
                Path(row["destination"]).exists(),
                Path(row["destination"]).is_symlink(),
                str(self.source_db)!=row["source_db"],
                _sha_file(self.python)!=row["python_sha"],
                _sha_file(self.script)!=row["script_sha"],
                _sha_file(self.ffmpeg)!=row["ffmpeg_sha"],
                _sha_file(self.ffprobe)!=row["ffprobe_sha"],
            )):
                return False
            self._plan(row["task_id"],row)
            return True
        except (OSError,KeyError,ValueError,TypeError,RuntimeError):
            return False

    def stage_and_approve(self,project_id,edit_id,revision,*,clip_ordinal,
                          first_zero,count,mode,destination,creator_event,
                          ram_mb=1024,duration_s=1800):
        if (type(ram_mb) is not int or not 1024<=ram_mb<=8192 or
            type(duration_s) is not int or not 60<=duration_s<=3600):
            raise ValueError("Invalid native resource grant bounds")
        scope_args=dict(project_id=project_id,edit_id=edit_id,
                        revision=revision,clip_ordinal=clip_ordinal,
                        first_zero=first_zero,count=count,mode=mode)
        plan=self.preflight.prepare(**scope_args)
        dest=Path(destination)
        if (not dest.is_absolute() or dest.is_symlink() or dest.exists() or
            not dest.parent.is_dir() or dest.parent.is_symlink()):
            raise RuntimeError("Approved native destination must be new and safely located")
        destination=str(dest)
        creator_scope={
            "operation":"nvp.native.film_time.review.v1",
            "project_id":project_id,
            "edit_id":edit_id,"edit_revision":revision,
            "edit_document_sha256":plan["edit_document_sha256"],
            "clip_ordinal":clip_ordinal,"first_zero":first_zero,
            "frame_count":count,
            "film_first_tick":plan["frames"][0]["film_time_tick"],
            "film_last_tick":plan["frames"][-1]["film_time_tick"],
            "mode":mode,"destination":destination,"ram_mb":ram_mb,
            "source_integrity":plan["source_integrity"],
            "final_master":False,
        }
        if self.creator(creator_event,dict(creator_scope)) is not True:
            raise PermissionError("Creator did not approve exact film-time review scope")
        if self.preflight.prepare(**scope_args)!=plan or dest.exists():
            raise RuntimeError("Source/edit changed during creator authorization")
        task="filmtime_"+secrets.token_hex(16)
        folder=self.root/task
        folder.mkdir(mode=0o700,exist_ok=False)
        raw=canonical_bytes(plan)
        with (folder/"window_plan.json").open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        hashes={
            "python_sha":_sha_file(self.python),
            "script_sha":_sha_file(self.script),
            "ffmpeg_sha":_sha_file(self.ffmpeg),
            "ffprobe_sha":_sha_file(self.ffprobe),
        }
        plan_sha=hashlib.sha256(raw).hexdigest()
        spec={
            "task_id":task,"kind":"compositing",
            "operation":"nvp.native.film_time.review.v1",
            "edit_sha":plan["edit_document_sha256"],
            "clip_ordinal":clip_ordinal,"first_zero":first_zero,
            "frame_count":count,"mode":mode,
            "destination":destination,"source_db":str(self.source_db),
            "plan_sha":plan_sha,"ram_mb":ram_mb,
            **hashes,
            "ffmpeg_path":str(self.ffmpeg),
            "ffprobe_path":str(self.ffprobe),
            "index_cache_root":str(self.index_root),
        }
        approval="filmapproval_"+secrets.token_hex(16)
        row={
            "task_id":task,"approval_id":approval,
            "project_id":project_id,"edit_id":edit_id,
            "edit_revision":revision,"edit_sha":plan["edit_document_sha256"],
            "clip_ordinal":clip_ordinal,"first_zero":first_zero,
            "frame_count":count,"mode":mode,
            "destination":destination,"source_db":str(self.source_db),
            "plan_sha":plan_sha,
            "spec_sha":hashlib.sha256(canonical_bytes(spec)).hexdigest(),
            **hashes,
            "ffmpeg_path":str(self.ffmpeg),"ffprobe_path":str(self.ffprobe),
            "index_cache_root":str(self.index_root),
            "ram_mb":ram_mb,"expires_at":time.time()+duration_s,
        }
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO "+TABLE+" ("+",".join(row)+") VALUES ("+
                       ",".join("?" for _ in row)+")",tuple(row.values()))
            db.commit()
        try:
            self.binding.enqueue(
                AdmissionRequest(task,"compositing",
                                 "Review sealed imported film-time window",ram_mb),
                owner_key=self.owner,lane="standard",
                approval_id=approval,document=spec)
        except BaseException:
            # No worker was admitted or started. If a different scheduler
            # managed to enqueue, keep the immutable grant for reconciliation.
            if self.ledger.get_task(task) is None:
                with self.ledger._db() as db:
                    db.execute("DELETE FROM "+TABLE+" WHERE task_id=?",(task,))
                shutil.rmtree(folder)
            raise
        return {
            "task_id":task,"state":"QUEUED","mode":mode,
            "review_frames":count,"native_worker_started":False,
            "edit_document_sha256":plan["edit_document_sha256"],
            "approved_final_master":False,
        }

    def revoke_queued(self,task):
        """Atomically revoke a queued grant and cancel its never-started task.

        Uses the SAME TaskLedger SQLite writer transaction as scheduler
        admission: no worker may be admitted between revocation and queue
        cancellation. ACTIVE workers require supervised process cancellation.
        """
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            state=db.execute("""SELECT t.state FROM tasks t
                JOIN task_schedule s ON s.task_id=t.id
                WHERE t.id=? AND s.owner_key=?""",
                (task,self.owner)).fetchone()
            if state is None or state[0]!="QUEUED":
                raise RuntimeError("Only never-started owned film-time tasks can be revoked")
            now=time.time()
            grant=db.execute(
                "UPDATE "+TABLE+" SET revoked_at=? "
                "WHERE task_id=? AND revoked_at IS NULL",
                (now,task))
            if grant.rowcount!=1:
                raise RuntimeError("Creator review grant already revoked or missing")
            detail="Creator revoked queued film-time review; no worker started"
            cancelled=db.execute("""UPDATE tasks
                SET state='CANCELLED',phase='cancelled',detail=?,
                    completed_fraction=NULL,reserved=0,updated_at=?
                WHERE id=? AND state='QUEUED'""",
                (detail,now,task))
            if cancelled.rowcount!=1:
                raise RuntimeError("Native task changed during queued revocation")
            self.ledger._event(db,task,"CANCELLED","cancelled",detail,None)
            db.commit()
        return {"task_id":task,"state":"CANCELLED",
                "worker_started":False,"creator_grant_revoked":True}

    def run_next(self,*,timeout_seconds=900,should_cancel=None):
        admitted=self.binding.claim_next(owner_key=self.owner)
        if not admitted or not admitted["admitted"]:
            return admitted
        task=admitted["task_id"]
        proc=None
        cleaned=False
        attempted=False
        try:
            self.binding.verified_spec(task,owner_key=self.owner)
            row=self._row(task)
            plan=self._plan(task,row)
            args=dict(project_id=row["project_id"],edit_id=row["edit_id"],
                      revision=row["edit_revision"],
                      clip_ordinal=row["clip_ordinal"],
                      first_zero=row["first_zero"],
                      count=row["frame_count"],mode=row["mode"])
            if self.preflight.prepare(**args)!=plan:
                raise RuntimeError("Native film-time preflight became stale before admission")
            self.ledger.update(task,"rendering",
                               "Decoding bounded unapproved film-time review")
            folder=self.root/task
            command=[
                str(self.python),str(self.script),
                "--plan",str(folder/"window_plan.json"),
                "--destination",row["destination"],
                "--studio-db",row["source_db"],
                "--ffmpeg",row["ffmpeg_path"],
                "--ffmpeg-sha",row["ffmpeg_sha"],
                "--decoder-backend","film_time_index",
                "--ffprobe",row["ffprobe_path"],
                "--ffprobe-sha",row["ffprobe_sha"],
                "--index-root",row["index_cache_root"],
            ]
            with (folder/"stdout.log").open("wb") as out, (
                folder/"stderr.log").open("wb") as err:
                attempted=True
                proc=launch_contained(
                    command,cwd=str(folder),stdout=out,stderr=err,
                    memory_mb=row["ram_mb"])
                code=wait_guarded(
                    proc,self.ledger,task,timeout_seconds=timeout_seconds,
                    should_cancel=should_cancel)
                if code!=0:
                    raise RuntimeError("Contained imported film-time worker failed")
                proc.close()
                cleaned=True
            self.ledger.update(task,"verifying_output",
                               "Independently auditing film-time source and review receipts")
            if self.preflight.prepare(**args)!=plan:
                raise RuntimeError("Saved edit/source changed during native worker")
            result=verify_film_time_window(row["destination"],plan)
            receipt=Path(row["destination"])/"review_receipt.json"
            sha=_sha_file(receipt)
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE "+TABLE+" SET result_sha=? WHERE task_id=? "+
                           "AND result_sha IS NULL",(sha,task))
                db.commit()
            self.ledger.finish(
                task,"SUCCEEDED","Verified unapproved imported film-time review")
            return {**result,"task_id":task,"state":"SUCCEEDED"}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    cleaned=proc.poll() is not None
                except BaseException:
                    cleaned=False
            if not attempted:
                cleaned=True
            if cleaned and self.ledger.get_task(task)["state"]=="ACTIVE":
                self.ledger.finish(
                    task,"FAILED","Native imported film-time window failed")
            raise

    def verify_completed(self,task):
        row=self._row(task)
        if (self.ledger.get_task(task)["state"]!="SUCCEEDED" or
            not row["result_sha"]):
            raise RuntimeError("No verified completed film-time window")
        plan=self._plan(task,row)
        result=verify_film_time_window(row["destination"],plan)
        if (_sha_file(Path(row["destination"])/"review_receipt.json")
                !=row["result_sha"]):
            raise RuntimeError("Durable published film-time receipt changed")
        return result

    def recover_interrupted(self,task,*,confirm_worker_tree_stopped):
        """Requires a trusted OS containment/fencing proof, never a PID guess.

        Preserves any partial output for quarantine/audit, retains ACTIVE
        reservation if termination is not proven, and never marks a partial
        job successful or silently requeues it.
        """
        if not callable(confirm_worker_tree_stopped):
            raise TypeError("Trusted process-tree termination proof required")
        row=self._row(task)
        state=self.ledger.get_task(task)
        if state is None or state["state"]!="ACTIVE":
            raise RuntimeError("Only active abandoned jobs can be reconciled")
        if confirm_worker_tree_stopped({
            "task_id":task,"destination":row["destination"],
            "project_id":row["project_id"],
            "edit_document_sha256":row["edit_sha"],
        }) is not True:
            raise PermissionError("Cannot release reserved resources before OS tree fencing")
        self.ledger.finish(
            task,"INTERRUPTED","Contained worker was fenced; outputs require new approval")
        return {
            "task_id":task,"state":"INTERRUPTED",
            "reserved_resources_released":True,
            "partial_output_quarantined_for_inspection":True,
            "automatic_retry":False,
        }
