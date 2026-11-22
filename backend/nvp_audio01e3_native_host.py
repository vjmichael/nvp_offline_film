"""AUDIO-01E.3 native audio host: B14 authorization/admission/containment path.

The desktop host supplies a real creator-policy callback. Only native host
code may invoke this class. No model / browser grant is accepted as authority.
Recovery requires a verified reaped worker handle or external OS supervision
after host loss; stale reservations are not cleared optimistically.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_audio01d_chunked_recovery import _read_state, _audit_chunks, _validate, _check_inputs, verify_chunked_preview, run_chunked_preview
from backend.nvp_audio01e3_native_journal import AudioJobJournal
from backend.nvp_film_index import _id
from backend.nvp_audio_native_staging_lock import AudioStagingLock
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained

def _sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

class NativeAudioHost:
    def __init__(self, ledger:TaskLedger, root, *, verify_creator_action,
                 strict_linux_tree=None, systemd_recovery=None):
        if not isinstance(ledger,TaskLedger) or not callable(verify_creator_action):
            raise TypeError("Native audio host requires a real ledger and creator policy")
        if strict_linux_tree is None:
            strict_linux_tree=(sys.platform=="linux")
        if type(strict_linux_tree) is not bool:
            raise TypeError("Strict Linux containment flag must be boolean")
        self.strict_linux_tree=strict_linux_tree
        if systemd_recovery is not None:
            from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority
            if (sys.platform != "linux" or not strict_linux_tree or
                type(systemd_recovery) is not SystemdRecoveryAuthority):
                raise PermissionError("Systemd recovery requires strict installed Linux host authority")
        self.systemd_recovery=systemd_recovery
        self.ledger=ledger
        self.root=Path(root)
        if self.root.is_symlink():raise RuntimeError("Unsafe audio job root")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=self.root.resolve()
        self.python=Path(sys.executable).resolve()
        # In a Linux onedir build, the fixed role lives inside the frozen
        # executable. Bind the exact executable identity instead of hashing
        # a nonexistent Python script in the bundled runtime.
        self._frozen_linux=sys.platform=="linux" and getattr(sys,"frozen",False)
        if self._frozen_linux and not self.strict_linux_tree:
            raise PermissionError("Frozen Linux audio requires strict kernel custody")
        self.worker=(self.python if self._frozen_linux else
                     Path(__file__).resolve().parents[1]/"tools"/"nvp_audio_native_worker.py")
        self.creator=verify_creator_action
        self.journal=AudioJobJournal(self.ledger.root/"audio_native_journal.sqlite3")
        self.owner="audionative_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:20]
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_grants(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                creator_event TEXT NOT NULL, scope_json TEXT NOT NULL,
                spec_sha TEXT NOT NULL, plan_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL, worker_sha TEXT NOT NULL,
                expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_os_stop_receipts(
                job_id TEXT PRIMARY KEY, stopped_at REAL NOT NULL,
                worker_reaped INTEGER NOT NULL CHECK(worker_reaped=1),
                stop_reason TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_staging_leases(
                directory TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL,
                predecessor TEXT
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_admission_outbox(
                job_id TEXT PRIMARY KEY, approved_document TEXT NOT NULL,
                document_sha TEXT NOT NULL, approval_id TEXT NOT NULL,
                owner_key TEXT NOT NULL, ram_mb INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','enqueued'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_service_bindings(
                job_id TEXT PRIMARY KEY, unit TEXT NOT NULL, invocation TEXT NOT NULL,
                start_sha TEXT NOT NULL, grant_sha TEXT NOT NULL, journal_sha TEXT NOT NULL,
                owner_key TEXT NOT NULL, approval_id TEXT NOT NULL, stop_sha TEXT
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_launch_boundaries(
                job_id TEXT PRIMARY KEY, phase TEXT NOT NULL CHECK(phase IN ('reserved','launch-intent'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_initial_output_intents(
                job_id TEXT PRIMARY KEY, checkpoint_sha TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_abandonments(
                job_id TEXT PRIMARY KEY, creator_event TEXT UNIQUE NOT NULL,
                scope_sha TEXT NOT NULL, stop_sha TEXT NOT NULL
            )""")
        self.binding=ApprovedTaskBindings(self.ledger,approval_check=self._check)
        self._running={}  # host-owned live process handles only

    def _grant(self,job):
        with self.ledger._db() as db:
            db.row_factory=__import__("sqlite3").Row
            row=db.execute("SELECT * FROM audio_native_grants WHERE job_id=?",
                           (job,)).fetchone()
        if row is None:raise KeyError("Native audio grant missing")
        return dict(row)

    def _check(self,approval_id,seal,doc):
        try:
            with self.ledger._db() as db:
                row=db.execute("""SELECT job_id FROM audio_native_grants
                    WHERE approval_id=?""",(approval_id,)).fetchone()
            if row is None:return False
            grant=self._grant(row[0])
            job=grant["job_id"]
            folder=self.root/job
            if (grant["revoked"] or time.time()>grant["expires_at"] or
                hashlib.sha256(canonical_bytes(doc)).hexdigest()!=seal or
                grant["spec_sha"]!=seal or doc["task_id"]!=job or
                doc["kind"]!="compositing" or
                grant["python_sha"]!=_sha_file(self.python) or
                grant["worker_sha"]!=_sha_file(self.worker) or
                grant["plan_sha"]!=_sha_file(folder/"worker_plan.json") or
                self.creator(grant["creator_event"],json.loads(grant["scope_json"])) is not True):
                return False
            journal=self.journal.read(job)
            with self.ledger._db() as db:
                lease=db.execute("""SELECT job_id,predecessor FROM audio_native_staging_leases
                    WHERE directory=?""",(doc["directory"],)).fetchone()
            if lease!=(job,doc.get("resume_from")):
                return False
            if (journal["spec"]["total_samples"]!=doc["total_samples"] or
                journal["spec"]["directory"]!=doc["directory"] or
                journal["state"]!="approved"):
                return False
            return True
        except (OSError,KeyError,ValueError,TypeError,RuntimeError):
            return False

    def stage_and_approve(self, plan, sources, total_samples, directory,
                          creator_event, *, ram_mb=1024, duration_s=3600, resume_from=None, project_source=None):
        if type(creator_event) is not str or not 1<=len(creator_event)<=128:
            raise ValueError("Creator approval reference required")
        if (type(ram_mb) is not int or not 1024<=ram_mb<=8192 or
            type(duration_s) is not int or not 30<=duration_s<=86400):
            raise ValueError("Bounded audio resource request required")
        job="audiojob"+secrets.token_hex(12)
        folder=self.root/job
        target=Path(directory)
        if target.is_symlink() or target.parent.is_symlink() or not target.parent.is_dir():
            raise RuntimeError("Audio output path or parent unsafe")
        sources={k:str(Path(v).resolve(strict=True)) for k,v in sources.items()}
        if project_source is not None and resume_from is not None:
            raise ValueError("Fresh project audio only; continuation requires separate review")
        if resume_from is None:
            if target.exists():
                raise RuntimeError("Fresh native audio job requires absent output")
        else:
            _id(resume_from,"preceding audio job")
            prior=self.journal.read(resume_from)
            oldspec=prior["spec"]
            if (prior["state"]!="reconciled" or
                self.ledger.get_task(resume_from)["state"]!="INTERRUPTED" or
                oldspec["directory"]!=str(target.absolute()) or
                oldspec["plan"]!=plan or
                oldspec["sources"]!=sources or
                oldspec["total_samples"]!=total_samples):
                raise RuntimeError("Recovery continuation must bind a reconciled predecessor")
            with self.ledger._db() as db:
                witness=db.execute("""SELECT worker_reaped FROM audio_native_os_stop_receipts
                    WHERE job_id=?""",(resume_from,)).fetchone()
            if witness!=(1,):
                raise RuntimeError("Continuation has no verified worker stop")
            if not target.is_dir():
                raise RuntimeError("Reconciled PCM checkpoint unavailable")
            state=_read_state(target)
            stems=_validate(plan,sources,total_samples)
            _check_inputs(stems,sources,state["sources"])
            samples=_audit_chunks(target,state)
            if state["status"]!="in_progress" or samples<prior["last_next_sample"]:
                raise RuntimeError("Continuation checkpoint has regressed or completed")
            for sid,sha in oldspec["source_sha256"].items():
                if _sha_file(sources[sid])!=sha:
                    raise RuntimeError("Recovered audio source changed")
        # Journal validates source WAV, plan bounds and creator-policy scope.
        registered=self.journal.register(job,plan,sources,total_samples,target,
                            verify_creator_action=self.creator,
                            creator_event=creator_event, project_source=project_source)
        scope=self.journal.read(job)["spec"]
        folder.mkdir(mode=0o700)
        worker_plan={
            "format":"nvp.native.audio.worker_plan.v1","job_id":job,
            "plan":plan,"sources":sources,"total_samples":total_samples,
            "directory":str(target.absolute()),
            "source_sha256":scope["source_sha256"],
            "final_master":False,"director_approved":False
        }
        plan_bytes=canonical_bytes(worker_plan)
        with (folder/"worker_plan.json").open("xb") as f:
            f.write(plan_bytes);f.flush();os.fsync(f.fileno())
        spec={"task_id":job,"kind":"compositing",
              "directory":scope["directory"],"total_samples":total_samples,
              "ram_mb":ram_mb,"plan_sha":_sha_file(folder/"worker_plan.json"),
              "worker_sha":_sha_file(self.worker),
              "resume_from":resume_from}
        seal=hashlib.sha256(canonical_bytes(spec)).hexdigest()
        approval="audioapproval"+secrets.token_hex(12)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            dest=str(target.absolute())
            if resume_from is None:
                db.execute("""INSERT INTO audio_native_staging_leases
                    (directory,job_id,predecessor) VALUES(?,?,NULL)""",(dest,job))
            else:
                changed=db.execute("""UPDATE audio_native_staging_leases
                    SET job_id=?,predecessor=? WHERE directory=? AND job_id=?""",
                    (job,resume_from,dest,resume_from)).rowcount
                if changed!=1:
                    raise RuntimeError("Staging lease changed or already resumed")
            db.execute("""INSERT INTO audio_native_grants(
                job_id,approval_id,creator_event,scope_json,spec_sha,plan_sha,
                python_sha,worker_sha,expires_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (job,approval,creator_event,canonical_bytes(scope).decode("ascii"),
                 seal,_sha_file(folder/"worker_plan.json"),_sha_file(self.python),
                 _sha_file(self.worker),time.time()+duration_s))
            db.execute("""INSERT INTO audio_native_admission_outbox(
                job_id,approved_document,document_sha,approval_id,owner_key,ram_mb,state
            ) VALUES(?,?,?,?,?,?,'pending')""",
                (job,canonical_bytes(spec).decode("ascii"),seal,approval,self.owner,ram_mb))
            db.commit()
        self.reconcile_admission_outbox(job)
        return {"job_id":job,"state":"QUEUED","contained_worker_started":False,
                "resume_from":resume_from,"spec_sha256":seal}

    def run_next(self, *, timeout_seconds=1200, test_hold=False, expected_task_id=None, should_cancel=None):
        if test_hold and os.environ.get("NVP_NATIVE_TERMINATION_TEST") != "1":
            raise PermissionError("Test-only worker hold not authorized")
        if should_cancel is not None and not callable(should_cancel):
            raise TypeError("Trusted cancellation predicate required")
        if should_cancel is not None and should_cancel():
            return {"state":"NOT_CLAIMED","task_id":expected_task_id,"admitted":False}
        admitted=self._claim_next(expected_task_id=expected_task_id) if expected_task_id is not None else self._claim_next()
        if admitted is None or not admitted["admitted"]:return admitted
        job=admitted["task_id"]
        proc=None
        clean=False
        worker_reaped=False
        staging_lock=None
        try:
            approved_doc=self.binding.verified_spec(job,owner_key=self.owner)
            staging_lock=AudioStagingLock(self.journal.read(job)["spec"]["directory"]).acquire()
            row=self.journal.read(job)
            self.journal.transition(job,row["generation"],"running","native_os_worker_admitted")
            folder=self.root/job
            # Prepare only the exact approved audio output under the staging
            # lease. Never grant the output parent to the child Landlock rule.
            audio_scope={}
            if self.strict_linux_tree and sys.platform=="linux":
                spec=row["spec"]
                target=Path(spec["directory"])
                if (not target.is_absolute() or target.resolve()!=target or
                    target.is_relative_to(self.root) or self.root.is_relative_to(target) or
                    target.is_relative_to(self.ledger.root) or self.ledger.root.is_relative_to(target) or
                    any(Path(src).is_relative_to(target) for src in spec["sources"].values())):
                    raise PermissionError("Unsafe approved audio output scope")
                if self.systemd_recovery is not None and approved_doc.get("resume_from") is None and target.exists():
                    raise PermissionError("Fresh approved output unexpectedly appeared")
                if not target.exists():
                    if self.systemd_recovery is not None:
                        initial_sha=self._record_initial_output_intent(job)
                        from backend.nvp_audio_initial_output import publish_initial
                        publish_initial(spec,initial_sha,folder)
                    else:
                        run_chunked_preview(spec["plan"],spec["sources"],spec["total_samples"],target,max_new_chunks=0)
                if not target.is_dir() or any(p.is_symlink() or not p.is_file() or p.stat().st_nlink!=1 for p in target.iterdir()):
                    raise PermissionError("Audio output contains unsafe entries")
                audio_scope={"linux_audio_output":str(target)}
            self.ledger.update(job,"saving_output","Contained audio chunk rendering")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                command=[str(self.python),
                         "--nvp-linux-audio-worker" if self._frozen_linux else str(self.worker),
                         "--plan",str(folder/"worker_plan.json")]
                if test_hold:
                    command.append("--test-hold-after-one-chunk")
                self._mark_launch_intent(job)
                proc=launch_contained(command,
                                      cwd=str(folder),stdout=out,stderr=err,
                                      memory_mb=self._grant_ram(job),
                                      linux_cgroup_tree_required=self.strict_linux_tree,**audio_scope)
                self._running[job]=proc
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds, should_cancel=should_cancel)
                if code!=0:raise RuntimeError("Contained audio worker exited "+str(code))
                proc.close();clean=True
                worker_reaped=True
                self._running.pop(job,None)
                proc=None  # Windows PROCESS handle is invalid after close()
            self.ledger.update(job,"verifying_output","Replaying audio chunks independently")
            spec=self.journal.read(job)["spec"]
            proof=verify_chunked_preview(spec["plan"],spec["sources"],
                                         spec["total_samples"],spec["directory"],replay=True)
            receipt=json.loads((folder/"worker_verified_receipt.json").read_text("utf8"))
            if (receipt.get("format")!="nvp.audio.native.worker_verified.v1" or
                receipt.get("job_id")!=job or
                receipt.get("samples")!=spec["total_samples"] or
                receipt.get("final_master") is not False):
                raise RuntimeError("Audio worker completion receipt mismatched")
            row=self.journal.read(job)
            self.journal.transition(job,row["generation"],"completed","verified_audio",
                                    next_sample=spec["total_samples"])
            self.ledger.finish(job,"SUCCEEDED","Native contained audio PCM replay verified")
            return {"state":"SUCCEEDED","job_id":job,"proof":proof}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    reaped=proc.poll() is not None
                    proc.close()
                    clean=reaped
                    worker_reaped=reaped
                except BaseException:clean=False
                self._running.pop(job,None)
            else:clean=True
            if clean:
                # A pre-launch failure has no process to reap: do not invent
                # an OS-stop witness. Only a real owned handle can supply it.
                if worker_reaped:
                    with self.ledger._db() as db:
                        db.execute("BEGIN IMMEDIATE")
                        db.execute("""INSERT INTO audio_native_os_stop_receipts(
                            job_id,stopped_at,worker_reaped,stop_reason)
                            VALUES(?,?,1,?)""",(job,time.time(),"owned_worker_closed"))
                        db.commit()
                row=self.journal.read(job)
                if row["state"] in ("approved","running"):
                    self.journal.transition(job,row["generation"],"recovery_required",
                                            "worker_stopped_recovery_required",
                                            cleanup_required=True)
                if self.ledger.get_task(job)["state"]=="ACTIVE":
                    self.ledger.finish(job,"INTERRUPTED","OS-cleaned audio worker needs verification")
            # On unverified cleanup, reservation stays ACTIVE.
            raise
        finally:
            if staging_lock is not None:
                staging_lock.release()

    def close_unclaimed_project_preview(self, job):
        """Close only a never-claimed project queue; replay split commits.

        No OS-stop receipt is inferred and no active reservation is released.
        """
        row = self.journal.read(job)
        spec = row["spec"]
        if not spec.get("project_source") or row["last_next_sample"] != 0:
            raise PermissionError("Not an unclaimed project preview")
        target = Path(spec["directory"])
        with AudioStagingLock(target):
            grant = self._grant(job)
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                doc = self._verify_service_approved_document(db, job, row, grant)
                task = db.execute("SELECT state,reserved FROM tasks WHERE id=?",(job,)).fetchone()
                schedule = db.execute("SELECT owner_key,claimed_at FROM task_schedule WHERE task_id=?",(job,)).fetchone()
                lease = db.execute("SELECT job_id FROM audio_native_staging_leases WHERE directory=?",(spec["directory"],)).fetchone()
                if (doc.get("resume_from") is not None or schedule != (self.owner,None) or
                    task not in (("QUEUED",0),("CANCELLED",0)) or
                    target.exists() or target.is_symlink() or
                    any(db.execute("SELECT 1 FROM " + table + " WHERE job_id=?",(job,)).fetchone()
                        for table in ("audio_native_service_bindings","audio_native_launch_boundaries",
                                      "audio_native_os_stop_receipts","audio_native_initial_output_intents"))):
                    raise PermissionError("Cannot close a possibly admitted audio job")
                if row["state"] == "approved" and row["generation"] == 0:
                    if lease != (job,):
                        raise PermissionError("Unclaimed preview lease changed")
                elif row["state"] == "failed" and row["generation"] == 1 and task == ("CANCELLED",0):
                    with self.journal._db() as jdb:
                        note = jdb.execute("SELECT note FROM audio_native_events WHERE job_id=? AND generation=1 AND next_state='failed'",(job,)).fetchone()
                    if note != ("unclaimed_project_preview_closed",) or lease not in (None,(job,)):
                        raise PermissionError("Unclaimed closure evidence changed")
                else:
                    raise PermissionError("Unclaimed preview journal changed")
                if task == ("QUEUED",0):
                    detail = "Project sound preview closed before worker admission"
                    db.execute("UPDATE tasks SET state='CANCELLED',phase='cancelled',detail=?,updated_at=? WHERE id=?",(detail,time.time(),job))
                    self.ledger._event(db,job,"CANCELLED","cancelled",detail,None)
                db.execute("UPDATE audio_native_grants SET revoked=1 WHERE job_id=?",(job,))
                db.commit()
            if row["state"] == "approved":
                self.journal.transition(job,0,"failed","unclaimed_project_preview_closed",cleanup_required=False)
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM audio_native_staging_leases WHERE job_id=? AND directory=?",(job,spec["directory"]))
                db.commit()
        return {"state":"CANCELLED","worker_started":False}

    def reconcile_journal_only(self,job):
        """Fail-closed cleanup of a never-admitted journal-only crash record.

        No worker may have started: require absent native grant, TaskLedger
        task, staging lease, and output path. Preserve a terminal audit trail;
        never synthesize creator consent, OS-stop receipts or queued work.
        """
        record=self.journal.read(job)
        if (record["state"]!="approved" or record["generation"]!=0 or
            record["last_next_sample"]!=0):
            raise RuntimeError("Journal-only cleanup requires untouched approved intent")
        spec=record["spec"]
        target=Path(spec["directory"])
        with AudioStagingLock(target):
            with self.ledger._db() as db:
                grant=db.execute("SELECT 1 FROM audio_native_grants WHERE job_id=?",
                                 (job,)).fetchone()
                task=db.execute("SELECT 1 FROM tasks WHERE id=?",(job,)).fetchone()
                lease=db.execute("""SELECT 1 FROM audio_native_staging_leases
                    WHERE job_id=? OR directory=?""",(job,str(target.absolute()))).fetchone()
            if grant or task or lease or target.exists() or target.is_symlink():
                raise RuntimeError("Journal-only record has unverified downstream effects")
            return self.journal.transition(job,0,"failed",
                "pre_admission_crash_closed_without_worker")

    def reconcile_admission_outbox(self,job):
        """Idempotent native replay of split-commit grant to TaskLedger queue.

        Must be called by trusted host after authorization, before executing.
        ApprovedTaskBindings.enqueue is itself atomic with queued task/receipt.
        No ACTIVE job is ever recreated or resource reservation released.
        """
        with self.ledger._db() as db:
            row=db.execute("""SELECT approved_document,document_sha,approval_id,
                owner_key,ram_mb,state FROM audio_native_admission_outbox
                WHERE job_id=?""",(job,)).fetchone()
        if row is None:
            raise RuntimeError("Unrecognized legacy admission; quarantine only")
        serialized,seal,approval,owner,ram_mb,state=row
        document=json.loads(serialized)
        if (canonical_bytes(document).decode("ascii")!=serialized or
            hashlib.sha256(serialized.encode("ascii")).hexdigest()!=seal or
            document.get("task_id")!=job or document.get("kind")!="compositing" or
            owner!=self.owner or document.get("ram_mb")!=ram_mb):
            raise RuntimeError("Persisted admission outbox is corrupt")
        # Recheck the current creator policy, code/source hashes, lease and
        # job journal on every replay, never trust an old approval indefinitely.
        if not self._check(approval,seal,document):
            raise PermissionError("Audio creator approval or bound source no longer valid")
        with self.ledger._db() as db:
            task=db.execute("SELECT state FROM tasks WHERE id=?",(job,)).fetchone()
        if task is None:
            self.binding.enqueue(AdmissionRequest(job,"compositing",
                "NVP native audio preview",ram_mb),owner_key=owner,
                lane="standard",approval_id=approval,document=document)
        elif task[0]=="QUEUED":
            verified=self.binding.verified_spec(job,owner_key=owner,
                                                  require_active=False)
            if verified!=document:
                raise RuntimeError("Existing queued task differs from sealed outbox")
        else:
            raise RuntimeError("Outbox recovery cannot touch admitted or terminal task")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            updated=db.execute("""UPDATE audio_native_admission_outbox
                SET state='enqueued' WHERE job_id=? AND document_sha=?
                AND state IN ('pending','enqueued')""",(job,seal)).rowcount
            if updated!=1:
                raise RuntimeError("Admission outbox was replaced")
            db.commit()
        return {"job_id":job,"status":"VERIFIED_QUEUED","spec_sha256":seal}

    def audit_incomplete_admissions(self):
        """Read-only crash audit; never release a resource or forge approval.

        A host crash between journal registration, grant/lease commit and
        ApprovedTaskBindings.enqueue can leave a staged but unscheduled job.
        Only report these cases. A separate trusted transaction reconciler
        must verify all OS and source effects before changing anything.
        """
        with self.ledger._db() as db:
            rows=db.execute("""SELECT g.job_id,g.spec_sha,l.directory,
                t.state,a.task_id
                FROM audio_native_grants g
                LEFT JOIN audio_native_staging_leases l ON l.job_id=g.job_id
                LEFT JOIN tasks t ON t.id=g.job_id
                LEFT JOIN authorized_task_specs a ON a.task_id=g.job_id
                ORDER BY g.job_id""").fetchall()
        results=[]
        for job,sha,directory,task_state,sealed in rows:
            record=self.journal.read(job)
            reason=None
            if task_state is None or sealed is None:
                reason="ADMISSION_NOT_ATOMIC_WITH_GRANT"
            elif record["state"]=="approved" and task_state=="ACTIVE":
                reason="ADMITTED_BUT_WORKER_NOT_ATTESTED"
            if reason:
                results.append({"job_id":job,"status":"QUARANTINED_NEEDS_NATIVE_AUDIT",
                                "reason":reason,"journal_state":record["state"],
                                "task_state":task_state,
                                "lease_present":directory is not None,
                                "spec_sha256":sha})
        return results

    def _grant_ram(self,job):
        with self.ledger._db() as db:
            return db.execute("SELECT ram_mb FROM tasks WHERE id=?",(job,)).fetchone()[0]

    def _verify_service_approved_document(self,db,job,row,grant):
        # Verify the original approval and queue seal without treating an expired
        # or revoked old grant as authority to resume. New consent is mandatory.
        stored=db.execute("""SELECT a.owner_key,a.approval_id,a.kind,a.spec_sha256,a.spec_json,
            s.owner_key FROM authorized_task_specs a JOIN task_schedule s ON s.task_id=a.task_id
            WHERE a.task_id=?""",(job,)).fetchone()
        if (not stored or stored[:4]!=(self.owner,grant["approval_id"],"compositing",grant["spec_sha"]) or
            stored[5]!=self.owner or hashlib.sha256(stored[4].encode("ascii")).hexdigest()!=stored[3]):
            raise PermissionError("Approved task binding changed")
        doc=json.loads(stored[4]);spec=row["spec"]
        if (canonical_bytes(doc).decode("ascii")!=stored[4] or doc.get("task_id")!=job or
            doc.get("kind")!="compositing" or doc.get("directory")!=spec["directory"] or
            doc.get("total_samples")!=spec["total_samples"] or doc.get("plan_sha")!=grant["plan_sha"] or
            doc.get("worker_sha")!=grant["worker_sha"] or
            canonical_bytes(spec).decode("ascii")!=grant["scope_json"]):
            raise PermissionError("Approved task document does not match audio journal")
        return doc

    def _claim_next(self, *, expected_task_id=None):
        kwargs={} if self.systemd_recovery is None else {"_prepare_admission":self._bind_systemd_generation}
        return self.binding.claim_next(owner_key=self.owner,expected_task_id=expected_task_id,**kwargs)

    def _bind_systemd_generation(self,db,job):
        """Called within the ledger's reservation transaction, never postclaim."""
        from backend.nvp_linux_service_recovery import digest
        start=self.systemd_recovery.current()
        row=self.journal.read(job); grant=self._grant(job)
        self._verify_service_approved_document(db,job,row,grant)
        task=db.execute("SELECT state,reserved FROM tasks WHERE id=?",(job,)).fetchone()
        lease=db.execute("SELECT job_id FROM audio_native_staging_leases WHERE directory=?",(row["spec"]["directory"],)).fetchone()
        if task!=("QUEUED",0) or lease!=(job,) or row["state"]!="approved" or row["generation"]!=0:
            raise PermissionError("Cannot bind nonqueued or unleased admission")
        db.execute("""INSERT INTO audio_native_service_bindings
            (job_id,unit,invocation,start_sha,grant_sha,journal_sha,owner_key,approval_id)
            VALUES(?,?,?,?,?,?,?,?)""",(job,start["unit"],start["invocation"],digest(start),
            grant["spec_sha"],row["spec_sha"],self.owner,grant["approval_id"]))
        db.execute("INSERT INTO audio_native_launch_boundaries VALUES(?,'reserved')",(job,))

    def _record_initial_output_intent(self,job):
        """Persist the exact zero-chunk checkpoint before any output write."""
        from backend.nvp_linux_service_recovery import digest
        from backend.nvp_audio_initial_output import initial_bytes
        current=self.systemd_recovery.current()
        row=self.journal.read(job); grant=self._grant(job); spec=row["spec"]
        checkpoint_sha=hashlib.sha256(initial_bytes(spec)).hexdigest()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._verify_service_approved_document(db,job,row,grant)
            binding=db.execute("SELECT unit,invocation,start_sha FROM audio_native_service_bindings WHERE job_id=?",(job,)).fetchone()
            task=db.execute("SELECT state,reserved FROM tasks WHERE id=?",(job,)).fetchone()
            phase=db.execute("SELECT phase FROM audio_native_launch_boundaries WHERE job_id=?",(job,)).fetchone()
            lease=db.execute("SELECT job_id,predecessor FROM audio_native_staging_leases WHERE directory=?",(spec["directory"],)).fetchone()
            target=Path(spec["directory"])
            if (binding!=(current['unit'],current['invocation'],digest(current)) or task!=("ACTIVE",1)
                or phase!=("reserved",) or row["state"]!="running" or row["generation"]!=1
                or lease!=(job,None) or target.exists() or target.is_symlink()
                or target.resolve()!=target or target.is_relative_to(self.root) or self.root.is_relative_to(target)
                or target.is_relative_to(self.ledger.root) or self.ledger.root.is_relative_to(target)
                or any(Path(src).is_relative_to(target) for src in spec["sources"].values())):
                raise PermissionError("Initial output intent requires fresh exclusive approved admission")
            db.execute("INSERT INTO audio_native_initial_output_intents VALUES(?,?)",(job,checkpoint_sha))
            db.commit()
        return checkpoint_sha

    def _mark_launch_intent(self,job):
        if self.systemd_recovery is None:
            return
        from backend.nvp_linux_service_recovery import digest
        current=self.systemd_recovery.current()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            binding=db.execute("SELECT unit,invocation,start_sha FROM audio_native_service_bindings WHERE job_id=?",(job,)).fetchone()
            task=db.execute("SELECT state,reserved FROM tasks WHERE id=?",(job,)).fetchone()
            if binding!=(current['unit'],current['invocation'],digest(current)) or task!=("ACTIVE",1):
                raise PermissionError("Launch requires original active service admission")
            if db.execute("UPDATE audio_native_launch_boundaries SET phase='launch-intent' WHERE job_id=? AND phase='reserved'",(job,)).rowcount!=1:
                raise PermissionError("Missing or reused native launch boundary")
            db.commit()

    def abandon_systemd_missing_output(self,job,*,creator_event):
        """Explicitly abandon a stopped uncertain job, not certify nonexecution.

        Only absent fresh output is eligible; existing or linked artifacts,
        resumed jobs and unresolved source changes require separate review.
        Never create media or reuse the prior grant.
        """
        if type(creator_event) is not str or not 1<=len(creator_event)<=128:
            raise ValueError("Explicit creator abandonment reference required")
        return self._recover_systemd_interrupted(job,abandon_event=creator_event)

    def recover_systemd_interrupted(self,job):
        return self._recover_systemd_interrupted(job)

    def _recover_systemd_interrupted(self,job,*,abandon_event=None):
        """Replay root-authenticated old-generation stop, then reconcile PCM.

        Idempotent after either SQLite commit. No caller-supplied witness or new
        consent accepted; continuing work still needs stage_and_approve.
        An unbound admission, or missing authenticated stop/reboot witness, is refused.
        """
        if self.systemd_recovery is None or job in self._running:
            raise PermissionError("No installed service recovery authority or live local worker")
        from backend.nvp_linux_service_recovery import digest
        row=self.journal.read(job); spec=row["spec"]; grant=self._grant(job)
        with AudioStagingLock(spec["directory"]):
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                bind=db.execute("""SELECT unit,invocation,start_sha,grant_sha,journal_sha,
                    owner_key,approval_id,stop_sha FROM audio_native_service_bindings WHERE job_id=?""",(job,)).fetchone()
                if not bind or bind[0]!=self.systemd_recovery.unit or bind[3:7]!=(grant["spec_sha"],row["spec_sha"],self.owner,grant["approval_id"]):
                    raise PermissionError("Missing or changed service admission binding")
                self._verify_service_approved_document(db,job,row,grant)
                stop=self.systemd_recovery.stopped(bind[1],bind[2]); stop_sha=digest(stop)
                lease=db.execute("SELECT job_id FROM audio_native_staging_leases WHERE directory=?",(spec["directory"],)).fetchone()
                task=db.execute("SELECT state,reserved FROM tasks WHERE id=?",(job,)).fetchone()
                reason="systemd_generation_stop:"+bind[1]
                existing=db.execute("SELECT worker_reaped,stop_reason FROM audio_native_os_stop_receipts WHERE job_id=?",(job,)).fetchone()
                # An approved generation-zero fresh job never reached the
                # durable running transition (which precedes every launch).
                # An absent output is not by itself evidence of nonexecution.
                original=json.loads(db.execute("SELECT spec_json FROM authorized_task_specs WHERE task_id=?",(job,)).fetchone()[0])
                target=Path(spec["directory"])
                phase=db.execute("SELECT phase FROM audio_native_launch_boundaries WHERE job_id=?",(job,)).fetchone()
                # A generation-one running journal may precede actual launch.
                # Only the new atomically committed reserved boundary proves
                # absence of launch intent; legacy running rows stay quarantined.
                before_launch=(row["state"]=="approved" and row["generation"]==0 or
                    phase==("reserved",) and row["state"]=="running" and row["generation"]==1)
                prelaunch=(original.get("resume_from") is None and not target.exists() and not target.is_symlink() and
                    phase!=("launch-intent",) and row["last_next_sample"]==0 and
                    (before_launch or row["state"]=="failed" and row["generation"] in (1,2)))
                if prelaunch and row["state"]=="failed":
                    with self.journal._db() as jdb:
                        event=jdb.execute("SELECT note FROM audio_native_events WHERE job_id=? AND generation=? AND next_state='failed'",(job,row["generation"])).fetchone()
                    prelaunch=event==("authenticated_prelaunch_reservation_closed",) and (row["generation"]==1 or phase==("reserved",))
                abandoned=db.execute("SELECT creator_event,scope_sha,stop_sha FROM audio_native_abandonments WHERE job_id=?",(job,)).fetchone()
                abandon=abandon_event is not None or abandoned is not None
                if abandon:
                    scope={"action":"abandon_interrupted_audio","job_id":job,
                        "original_spec_sha256":row["spec_sha"],"stop_sha256":stop_sha,
                        "directory":spec["directory"],"final_master":False}
                    scope_sha=hashlib.sha256(canonical_bytes(scope)).hexdigest()
                    if (original.get("resume_from") is not None or phase!=("launch-intent",)
                        or target.exists() or target.is_symlink() or row["last_next_sample"]!=0
                        or row["state"] not in ("running","failed") or row["generation"] not in (1,2)):
                        raise PermissionError("Only stopped uncertain fresh missing output can be abandoned")
                    if abandoned is None:
                        if (abandon_event==grant["creator_event"] or task!=("ACTIVE",1) or row["state"]!="running"
                            or grant["revoked"] or self.creator(abandon_event,scope) is not True):
                            raise PermissionError("Fresh creator abandonment approval required")
                    elif (abandoned[1:]!=(scope_sha,stop_sha) or abandon_event not in (None,abandoned[0])):
                        raise PermissionError("Abandonment replay differs from committed decision")
                    prelaunch=False
                # Do not release an admitted job with missing output after launch
                # was intended or for an ambiguous legacy running admission.
                if not prelaunch and not abandon and not target.exists():
                    raise PermissionError("Missing audio output after possible launch; quarantine")
                if (row["state"]=="failed" and not prelaunch and not abandon):
                    raise PermissionError("Failed task is not a verified prelaunch closure")
                if ((lease!=(job,) and not ((prelaunch or abandoned is not None) and row["state"]=="failed" and lease is None)) or row["state"] not in ("running","approved","recovery_required","reconciled","failed") or
                    task not in (("ACTIVE",1),("INTERRUPTED",0)) or
                    bind[7] not in (None,stop_sha) or
                    existing not in (None,(1,reason)) or
                    (task[0]=="INTERRUPTED" and (bind[7]!=stop_sha or existing!=(1,reason)))):
                    raise PermissionError("Service-stop witness cannot authorize this admission state")
                # Check source and immutable plan before releasing a reservation.
                if (grant["plan_sha"]!=_sha_file(self.root/job/"worker_plan.json") or
                    any(_sha_file(src)!=spec["source_sha256"][sid] for sid,src in spec["sources"].items())):
                    raise PermissionError("Authorized audio inputs changed")
                initial=db.execute("SELECT checkpoint_sha FROM audio_native_initial_output_intents WHERE job_id=?",(job,)).fetchone()
                if (initial is not None and phase==("reserved",) and target.exists()
                    and row["state"] in ("running","recovery_required")):
                    from backend.nvp_audio_initial_output import publish_initial
                    publish_initial(spec,initial[0],self.root/job,recovering=True)
                if task[0]=="ACTIVE":
                    if abandon:
                        db.execute("INSERT INTO audio_native_abandonments VALUES(?,?,?,?)",(job,abandon_event,scope_sha,stop_sha))
                        db.execute("UPDATE audio_native_grants SET revoked=1 WHERE job_id=?",(job,))
                    db.execute("INSERT INTO audio_native_os_stop_receipts VALUES(?,?,1,?)",(job,time.time(),reason))
                    db.execute("UPDATE audio_native_service_bindings SET stop_sha=? WHERE job_id=?",(stop_sha,job))
                    detail="Authenticated systemd service generation stopped"
                    db.execute("""UPDATE tasks SET state='INTERRUPTED',phase='recovering',detail=?,
                        completed_fraction=NULL,reserved=0,updated_at=? WHERE id=? AND state='ACTIVE'""",(detail,time.time(),job))
                    self.ledger._event(db,job,"INTERRUPTED","recovering",detail,None)
                db.commit()
            # Separate durable journal: repeat safely if host died after commit.
            row=self.journal.read(job)
            if abandon:
                if row["state"]=="running":
                    self.journal.transition(job,row["generation"],"failed","creator_abandoned_uncertain_stopped_audio",cleanup_required=False)
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("DELETE FROM audio_native_staging_leases WHERE directory=? AND job_id=?",(spec["directory"],job))
                    db.commit()
                return {"state":"failed","abandoned":True,"worker_started":None,"next_sample":0}
            if prelaunch:
                if row["state"] in ("approved","running"):
                    self.journal.transition(job,row["generation"],"failed","authenticated_prelaunch_reservation_closed",cleanup_required=False)
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("UPDATE audio_native_grants SET revoked=1 WHERE job_id=?",(job,))
                    db.execute("DELETE FROM audio_native_staging_leases WHERE directory=? AND job_id=?",(spec["directory"],job))
                    db.commit()
                return {"state":"failed","prelaunch_closed":True,"next_sample":0,"worker_started":False}

            if row["state"] in ("approved","running"):
                self.journal.transition(job,row["generation"],"recovery_required",
                    "authenticated_systemd_generation_stopped",cleanup_required=True)
            row=self.journal.read(job)
            if row["state"]=="reconciled":
                return {"state":"reconciled","generation":row["generation"],"next_sample":row["last_next_sample"],"already_reconciled":True}
            return self.journal.recover(job,attest_stopped=lambda j,s:j==job and j not in self._running)

    def recover_stopped(self,job):
        """Host may recover after it has OS-confirmed no active owned worker.

        After HOST crash we do not have the old Job Object or cgroup proof; do
        NOT unlock/finish an ACTIVE reservation using process-name heuristics.
        """
        if job in self._running:
            proc=self._running[job]
            if proc.poll() is None:
                raise RuntimeError("Cannot reconcile a living contained worker")
            proc.close()
            self._running.pop(job)
        task=self.ledger.get_task(job)
        if task is None or task["state"]!="INTERRUPTED":
            raise RuntimeError("Recovery requires OS-cleaned interrupted admission")
        with self.ledger._db() as db:
            witness=db.execute("""SELECT worker_reaped FROM audio_native_os_stop_receipts
                WHERE job_id=?""",(job,)).fetchone()
        if witness is None or witness[0] != 1:
            raise RuntimeError("No durable verified worker-stop witness; recovery blocked")
        with AudioStagingLock(self.journal.read(job)["spec"]["directory"]):
            return self.journal.recover(job,attest_stopped=lambda j,s: j not in self._running)
