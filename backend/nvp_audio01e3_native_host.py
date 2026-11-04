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
from backend.nvp_audio01d_chunked_recovery import _read_state, verify_chunked_preview
from backend.nvp_audio01e3_native_journal import AudioJobJournal
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
    def __init__(self, ledger:TaskLedger, root, *, verify_creator_action):
        if not isinstance(ledger,TaskLedger) or not callable(verify_creator_action):
            raise TypeError("Native audio host requires a real ledger and creator policy")
        self.ledger=ledger
        self.root=Path(root)
        if self.root.is_symlink():raise RuntimeError("Unsafe audio job root")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=self.root.resolve()
        self.python=Path(sys.executable).resolve()
        self.worker=Path(__file__).resolve().parents[1]/"tools"/"nvp_audio_native_worker.py"
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
            if (journal["spec"]["total_samples"]!=doc["total_samples"] or
                journal["spec"]["directory"]!=doc["directory"] or
                journal["state"]!="approved"):
                return False
            return True
        except (OSError,KeyError,ValueError,TypeError,RuntimeError):
            return False

    def stage_and_approve(self, plan, sources, total_samples, directory,
                          creator_event, *, ram_mb=1024, duration_s=3600):
        if type(creator_event) is not str or not 1<=len(creator_event)<=128:
            raise ValueError("Creator approval reference required")
        if (type(ram_mb) is not int or not 1024<=ram_mb<=8192 or
            type(duration_s) is not int or not 30<=duration_s<=86400):
            raise ValueError("Bounded audio resource request required")
        job="audiojob_"+secrets.token_hex(12)
        folder=self.root/job
        target=Path(directory)
        if target.exists() or target.is_symlink() or target.parent.is_symlink() or not target.parent.is_dir():
            raise RuntimeError("Audio output must be absent under a safe parent")
        sources={k:str(Path(v).resolve(strict=True)) for k,v in sources.items()}
        # Journal validates source WAV, plan bounds and creator-policy scope.
        registered=self.journal.register(job,plan,sources,total_samples,target,
                            verify_creator_action=self.creator,
                            creator_event=creator_event)
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
              "worker_sha":_sha_file(self.worker)}
        seal=hashlib.sha256(canonical_bytes(spec)).hexdigest()
        approval="audioapproval_"+secrets.token_hex(12)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO audio_native_grants(
                job_id,approval_id,creator_event,scope_json,spec_sha,plan_sha,
                python_sha,worker_sha,expires_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (job,approval,creator_event,canonical_bytes(scope).decode("ascii"),
                 seal,_sha_file(folder/"worker_plan.json"),_sha_file(self.python),
                 _sha_file(self.worker),time.time()+duration_s))
        self.binding.enqueue(AdmissionRequest(job,"compositing","NVP native audio preview",ram_mb),
                             owner_key=self.owner,lane="standard",approval_id=approval,
                             document=spec)
        return {"job_id":job,"state":"QUEUED","contained_worker_started":False,
                "spec_sha256":seal}

    def run_next(self, *, timeout_seconds=1200, test_hold=False):
        if test_hold and os.environ.get("NVP_NATIVE_TERMINATION_TEST") != "1":
            raise PermissionError("Test-only worker hold not authorized")
        admitted=self.binding.claim_next(owner_key=self.owner)
        if admitted is None or not admitted["admitted"]:return admitted
        job=admitted["task_id"]
        proc=None
        clean=False
        try:
            self.binding.verified_spec(job,owner_key=self.owner)
            row=self.journal.read(job)
            self.journal.transition(job,row["generation"],"running","native_os_worker_admitted")
            folder=self.root/job
            self.ledger.update(job,"saving_output","Contained audio chunk rendering")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                command=[str(self.python),str(self.worker),
                         "--plan",str(folder/"worker_plan.json")]
                if test_hold:
                    command.append("--test-hold-after-one-chunk")
                proc=launch_contained(command,
                                      cwd=str(folder),stdout=out,stderr=err,
                                      memory_mb=self._grant_ram(job))
                self._running[job]=proc
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code!=0:raise RuntimeError("Contained audio worker exited "+str(code))
                proc.close();clean=True
                self._running.pop(job,None)
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
                    proc.close()
                    clean=proc.poll() is not None
                except BaseException:clean=False
                self._running.pop(job,None)
            else:clean=True
            if clean:
                # Durable witness is written only after owned process-tree
                # termination was observed and handles were reaped/closed.
                # Never manufacture a witness after an unverified host crash.
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("""INSERT INTO audio_native_os_stop_receipts(
                        job_id,stopped_at,worker_reaped,stop_reason)
                        VALUES(?,?,1,?)""",(job,time.time(),"owned_worker_closed"))
                row=self.journal.read(job)
                if row["state"] in ("approved","running"):
                    self.journal.transition(job,row["generation"],"recovery_required",
                                            "worker_stopped_recovery_required",
                                            cleanup_required=True)
                if self.ledger.get_task(job)["state"]=="ACTIVE":
                    self.ledger.finish(job,"INTERRUPTED","OS-cleaned audio worker needs verification")
            # On unverified cleanup, reservation stays ACTIVE.
            raise

    def _grant_ram(self,job):
        with self.ledger._db() as db:
            return db.execute("SELECT ram_mb FROM tasks WHERE id=?",(job,)).fetchone()[0]

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
        if self.ledger.get_task(job)["state"]!="INTERRUPTED":
            raise RuntimeError("Recovery requires OS-cleaned interrupted admission")
        with self.ledger._db() as db:
            witness=db.execute("""SELECT worker_reaped FROM audio_native_os_stop_receipts
                WHERE job_id=?""",(job,)).fetchone()
        if witness is None or witness[0] != 1:
            raise RuntimeError("No durable verified worker-stop witness; recovery blocked")
        return self.journal.recover(job,attest_stopped=lambda j,s: j not in self._running)
