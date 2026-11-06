"""AUDIO-01J trusted AV host: picture lock, final mux authorization, OS containment.

Creator approval is verified in the host, not granted by a worker. A worker
must carry an ACTIVE sealed task and matching native grant. Crash uncertainty
keeps ACTIVE RAM reservations; registered AV requires an OS-stop witness.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings,canonical_bytes
from backend.nvp_audio01j_picture_lock import approve_picture,validate_picture_lock
from backend.nvp_audio01j_fault_matrix import crash_after
from backend.nvp_audio01j_final_av import (
    approved_inputs,verify_final_av,verify_av_candidate,
    candidate_id_for,final_master_document)
from backend.nvp_audio01i_mastering import sha_file
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained
from backend.nvp_film_index import _id

FORMAT="nvp.audio01j.native_plan.v1"
ROOT=Path(__file__).resolve().parents[1]


class NativeAudio01JHost:
    def __init__(self,capture,ledger:TaskLedger,root,*,verify_creator_action,
                 audio_host,strict_linux_tree=None):
        if (not isinstance(ledger,TaskLedger) or not callable(verify_creator_action)
            or not callable(getattr(audio_host,"verify_delivery",None))):
            raise TypeError("Trusted ledger, creator policy and AUDIO-01I host required")
        self.capture,self.ledger,self.creator=capture,ledger,verify_creator_action
        self.audio_host=audio_host
        requested=Path(root)
        if requested.is_symlink():raise RuntimeError("Unsafe AV host root")
        requested.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=requested.resolve()
        self.python=Path(sys.executable).resolve()
        self.worker=ROOT/"tools/nvp_audio01j_native_worker.py"
        self.owner="audio01j_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:22]
        self.strict_linux_tree=(sys.platform=="linux" if strict_linux_tree is None
                                else strict_linux_tree)
        if type(self.strict_linux_tree) is not bool:
            raise ValueError("Invalid Linux tree containment policy")
        self.events={}
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01j_grants(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                spec_sha TEXT NOT NULL, plan_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL, worker_sha TEXT NOT NULL,
                ffmpeg_sha TEXT NOT NULL, ffprobe_sha TEXT NOT NULL,
                expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                stopped INTEGER NOT NULL DEFAULT 0,result_sha TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01j_creator_events(
                event_sha TEXT PRIMARY KEY,project_id TEXT NOT NULL,
                operation TEXT NOT NULL,object_id TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT -1)""")
        with ledger._db() as db:
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS native_audio01j_one_action_per_output
                ON native_audio01j_creator_events(project_id,operation,object_id)""")
        self.bindings=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _grant(self,job):
        with self.ledger._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM native_audio01j_grants WHERE job_id=?",
                           (job,)).fetchone()
        if row is None:raise KeyError("Unknown final AV grant")
        return dict(row)

    def _event(self,event,project,operation,object_id):
        if type(event) is not str or not event:
            raise PermissionError("Authenticated creator event identifier required")
        identity=hashlib.sha256(event.encode("utf8")).hexdigest()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM native_audio01j_creator_events WHERE event_sha=?",
                          (identity,)).fetchone():
                raise PermissionError("Creator event already used")
            db.execute("INSERT INTO native_audio01j_creator_events VALUES(?,?,?,?,?)",
                       (identity,project,operation,object_id,-1))
            db.commit()
        return identity

    def approve_picture(self,project_id,candidate_id,lock_id,package,
                        conform_dir,movie_dir,creator_event,*,
                        ffmpeg="ffmpeg",ffprobe="ffprobe"):
        _id(lock_id,"picture lock")
        # Authenticate operation identity before irrevocably spending nonce.
        candidate=self.capture.index.read_revision(project_id,candidate_id,1)
        scope={"operation":"nvp.audio01j.picture_lock_request",
               "project_id":project_id,"candidate_id":candidate_id,
               "candidate_sha256":candidate["document_sha256"],"lock_id":lock_id}
        if self.creator(creator_event,scope) is not True:
            raise PermissionError("Unapproved creator picture lock request")
        nonce=self._event(creator_event,project_id,"picture_lock",lock_id)
        crash_after("picture_event_reserved")
        result=approve_picture(self.capture,project_id,candidate_id,lock_id,
            package,conform_dir,movie_dir,creator_event=creator_event,
            verify_creator_action=self.creator,ffmpeg=ffmpeg,ffprobe=ffprobe)
        crash_after("picture_lock_indexed")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01j_creator_events SET revision=1 WHERE event_sha=?",
                       (nonce,));db.commit()
        crash_after("picture_event_completed")
        return result

    def _check(self,approval,digest,spec):
        try:
            job=spec["task_id"];grant=self._grant(job)
            path=self.root/job/"plan.json"
            if (grant["approval_id"]!=approval or grant["spec_sha"]!=digest
                or grant["revoked"] or grant["result_sha"] is not None
                or time.time()>grant["expires_at"]
                or path.is_symlink() or sha_file(path)!=grant["plan_sha"]
                or sha_file(self.python)!=grant["python_sha"]
                or sha_file(self.worker)!=grant["worker_sha"]
                or hashlib.sha256(canonical_bytes(spec)).hexdigest()!=digest):
                return False
            plan=json.loads(path.read_bytes())
            if (canonical_bytes(plan)!=path.read_bytes()
                or plan.get("format")!=FORMAT
                or plan.get("approved_spec")!=spec
                or plan.get("destination")!=spec["destination"]
                or plan.get("export_id")!=spec["export_id"]
                or plan.get("project_id")!=spec["project_id"]
                or sha_file(plan["ffmpeg"])!=grant["ffmpeg_sha"]
                or sha_file(plan["ffprobe"])!=grant["ffprobe_sha"]
                or Path(plan["destination"]).exists()
                or Path(plan["destination"]).is_symlink()):
                return False
            # Recheck the current AUDIO-01I approval head at admission,
            # not just when the operation was originally queued.
            self.audio_host.verify_delivery(
                plan["project_id"],plan["audio_delivery_id"],plan["audio_dir"],
                ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
            lock,_,audio,_,_,_=approved_inputs(
                self.capture,plan["project_id"],plan["picture_lock_id"],
                plan["audio_delivery_id"],plan["movie_dir"],plan["audio_dir"])
            event=self.events.get(job)
            return (lock["document_sha256"]==spec["lock_sha"]
                    and audio["document_sha256"]==spec["audio_sha"]
                    and event is not None and self.creator(event,spec["creator_scope"]) is True)
        except (KeyError,TypeError,ValueError,OSError,PermissionError,RuntimeError):
            return False

    def stage(self,project_id,lock_id,audio_delivery_id,movie_dir,audio_dir,
              destination,export_id,creator_event,*,
              ffmpeg="ffmpeg",ffprobe="ffprobe",ram_mb=1024,duration_s=1800):
        _id(export_id,"final AV export")
        if (type(ram_mb) is not int or not 1024<=ram_mb<=8192
            or type(duration_s) is not int or not 60<=duration_s<=3600):
            raise ValueError("Invalid final AV resource bounds")
        # Independently verify full AUDIO-01I creator-approved, hashed master.
        self.audio_host.verify_delivery(
            project_id,audio_delivery_id,audio_dir,ffmpeg=ffmpeg,ffprobe=ffprobe)
        lock,picture,audio,video,wav,frames=approved_inputs(
            self.capture,project_id,lock_id,audio_delivery_id,movie_dir,audio_dir)
        with self.ledger._db() as db:
            found=db.execute("""SELECT COUNT(*) FROM native_audio01j_creator_events
                WHERE project_id=? AND operation='picture_lock'
                  AND object_id=? AND revision=1""",(project_id,lock_id)).fetchone()
        if not found or found[0]!=1:
            raise PermissionError("Picture lock not from native creator event")
        target=Path(destination).absolute()
        if (target.exists() or target.is_symlink() or target.parent.is_symlink()
            or not target.parent.is_dir() or
            target.with_name("."+target.name+".audio01j.stage").exists()
            or target.with_name("."+target.name+".audio01j.stage").is_symlink()):
            raise RuntimeError("Final AV output/staging must be absent")
        try:self.capture.index.read_revision(project_id,export_id)
        except KeyError:pass
        else:raise RuntimeError("Final AV identity already exists")
        binaries={}
        for name,requested in (("ffmpeg",ffmpeg),("ffprobe",ffprobe)):
            resolved=shutil.which(str(requested))
            if resolved is None:raise RuntimeError("No native "+name)
            binaries[name]=str(Path(resolved).resolve(strict=True))
        scope={"operation":"nvp.audio01j.approve_final_audiovisual_export",
               "project_id":project_id,"picture_lock_id":lock_id,
               "picture_lock_sha256":lock["document_sha256"],
               "audio_delivery_id":audio_delivery_id,
               "audio_delivery_sha256":audio["document_sha256"],
               "export_id":export_id,"destination":str(target),
               "frames":frames,"final_master":True,"dcp_delivered":False}
        if self.creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Creator denied exact final audiovisual export")
        nonce=self._event(creator_event,project_id,"final_av",export_id)
        crash_after("av_export_event_reserved")
        job="avjob"+secrets.token_hex(16)
        spec={"task_id":job,"kind":"compositing","project_id":project_id,
              "export_id":export_id,"destination":str(target),
              "lock_sha":lock["document_sha256"],
              "audio_sha":audio["document_sha256"],"creator_scope":scope}
        plan={"format":FORMAT,"studio_db_path":str(self.capture.studio.db_path),
              "ledger_path":str(self.ledger.db_path),
              "job_id":job,"owner_key":self.owner,"approved_spec":spec,
              "project_id":project_id,"picture_lock_id":lock_id,
              "audio_delivery_id":audio_delivery_id,
              "movie_dir":str(Path(movie_dir).resolve(strict=True)),
              "audio_dir":str(Path(audio_dir).resolve(strict=True)),
              "destination":str(target),"export_id":export_id,
              "ffmpeg":binaries["ffmpeg"],"ffprobe":binaries["ffprobe"],
              "dcp_delivered":False}
        folder=self.root/job;folder.mkdir(mode=0o700)
        with (folder/"plan.json").open("xb") as f:
            f.write(canonical_bytes(plan));f.flush();os.fsync(f.fileno())
        approval="avapproval"+secrets.token_hex(16)
        seal=hashlib.sha256(canonical_bytes(spec)).hexdigest()
        self.events[job]=creator_event
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_audio01j_grants(job_id,approval_id,
                spec_sha,plan_sha,python_sha,worker_sha,
                ffmpeg_sha,ffprobe_sha,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (job,approval,seal,sha_file(folder/"plan.json"),
                 sha_file(self.python),sha_file(self.worker),
                 sha_file(binaries["ffmpeg"]),sha_file(binaries["ffprobe"]),
                 time.time()+duration_s))
            db.commit()
        crash_after("av_grant_committed")
        self.bindings.enqueue(AdmissionRequest(job,"compositing",
            "Approved picture + final PCM24 audio MOV export",ram_mb),
            owner_key=self.owner,lane="standard",approval_id=approval,document=spec)
        crash_after("av_queued")
        return {"job_id":job,"state":"QUEUED","export_id":export_id,
                "creator_event_sha":nonce}

    def _publish_verified_master(self,job,plan):
        """Only trusted host may turn a stopped worker's candidate into a master."""
        if self._grant(job)["stopped"]!=1:
            raise PermissionError("No durable native OS-stop evidence for AV publication")
        with self.ledger._db() as db:
            event=db.execute("""SELECT COUNT(*) FROM native_audio01j_creator_events
                WHERE project_id=? AND operation='final_av' AND object_id=?
                AND revision IN (-1,1)""",
                (plan["project_id"],plan["export_id"])).fetchone()
        if not event or event[0]!=1:
            raise PermissionError("Missing durably reserved exact creator export action")
        self.audio_host.verify_delivery(
            plan["project_id"],plan["audio_delivery_id"],plan["audio_dir"],
            ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
        verified=verify_av_candidate(
            self.capture,plan["project_id"],plan["export_id"],
            plan["destination"],plan["movie_dir"],plan["audio_dir"],
            ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
        candidate=self.capture.index.read_revision(
            plan["project_id"],verified["candidate_id"],1)
        receipt_file=self.root/job/"worker_receipt.json"
        if receipt_file.is_symlink() or not receipt_file.is_file():
            raise RuntimeError("Missing final AV worker candidate receipt")
        receipt=json.loads(receipt_file.read_bytes())
        if (receipt.get("format")!="nvp.audio01j.worker_receipt.v1"
            or receipt.get("export_id")!=plan["export_id"]
            or receipt.get("candidate_id")!=verified["candidate_id"]
            or receipt.get("document_sha256")!=candidate["document_sha256"]
            or receipt.get("mov_sha256")!=candidate["data"]["rendered_mov_sha256"]
            or receipt.get("final_master") is not False
            or receipt.get("dcp_delivered") is not False):
            raise RuntimeError("Worker receipt cannot authorize a final master")
        document=final_master_document(candidate)
        deps=[{"object_id":verified["candidate_id"],"revision":1,"role":"presentation"},
              {"object_id":plan["picture_lock_id"],"revision":1,"role":"presentation"},
              {"object_id":plan["audio_delivery_id"],"revision":1,"role":"audio"}]
        try:
            previous=self.capture.index.read_revision(
                plan["project_id"],plan["export_id"],1)
        except KeyError:
            recorded=self.capture.index.register_revision(
                plan["project_id"],plan["export_id"],"master",document,
                expected_revision=0,dependencies=deps)
            master=self.capture.index.read_revision(
                plan["project_id"],plan["export_id"],1)
            if recorded["document_sha256"]!=master["document_sha256"]:
                raise RuntimeError("Host master publication digest changed")
        else:
            master=previous
            if (master["kind"]!="master" or master["data"]!=document
                or master["dependencies"]!=sorted(
                    deps,key=lambda d:(d["object_id"],d["revision"],d["role"]))):
                raise RuntimeError("Conflicting host-only master publication")
        return master,verified

    def run_next(self,*,timeout_seconds=900):
        admitted=self.bindings.claim_next(owner_key=self.owner)
        if admitted is None or not admitted["admitted"]:return admitted
        crash_after("av_claimed")
        job=admitted["task_id"];proc=None;reaped=False
        try:
            self.bindings.verified_spec(job,owner_key=self.owner)
            folder=self.root/job
            plan=json.loads((folder/"plan.json").read_bytes())
            self.ledger.update(job,"rendering","Contained picture+PCM24 final mux")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                proc=launch_contained(
                    [str(self.python),str(self.worker),"--plan",str(folder/"plan.json")],
                    cwd=str(folder),stdout=out,stderr=err,
                    memory_mb=self.ledger.get_task(job)["ram_mb"],
                    linux_cgroup_tree_required=self.strict_linux_tree)
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code:raise RuntimeError("Final AV native worker exited "+str(code))
                proc.close();proc=None;reaped=True
            crash_after("av_worker_reaped")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01j_grants SET stopped=1 WHERE job_id=?",(job,))
                db.commit()
            # A mix revoked during render is not a deliverable, even if its
            # completed MOV still decodes correctly.
            self.audio_host.verify_delivery(
                plan["project_id"],plan["audio_delivery_id"],plan["audio_dir"],
                ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
            crash_after("av_stop_witness_committed")
            self.ledger.update(job,"verifying_output","Independent FilmIndex and decoded media proof")
            rec,candidate_proof=self._publish_verified_master(job,plan)
            crash_after("av_master_registered")
            verified=verify_final_av(
                self.capture,plan["project_id"],plan["export_id"],
                plan["destination"],plan["movie_dir"],plan["audio_dir"],
                ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01j_grants SET result_sha=? WHERE job_id=?",
                           (rec["document_sha256"],job))
                db.commit()
            crash_after("av_result_committed")
            self.ledger.finish(job,"SUCCEEDED","Verified final synchronized AV master")
            crash_after("av_ledger_succeeded")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE native_audio01j_creator_events SET revision=1
                    WHERE project_id=? AND operation='final_av' AND object_id=?
                    AND revision=-1""",(plan["project_id"],plan["export_id"]))
                db.commit()
            crash_after("av_event_completed")
            return {"job_id":job,**verified,"state":"SUCCEEDED",
                    "document_sha256":rec["document_sha256"]}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    reaped=proc.poll() is not None
                    proc.close()
                except BaseException:reaped=False
            if reaped and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.update(job,"recovering",
                                   "Incomplete final AV verification, native audit required")
            raise

    def verify_published(self,project_id,export_id,output_dir,movie_dir,audio_dir,*,
                         ffmpeg="ffmpeg",ffprobe="ffprobe"):
        """Native creator/worker custody is mandatory beyond FilmIndex records."""
        rec=self.capture.index.read_revision(project_id,export_id,1)
        with self.ledger._db() as db:
            rows=db.execute("""SELECT g.job_id FROM native_audio01j_grants g
                JOIN tasks t ON t.id=g.job_id
                WHERE g.result_sha=? AND g.stopped=1 AND g.revoked=0
                  AND t.state='SUCCEEDED' AND t.reserved=0""",
                (rec["document_sha256"],)).fetchall()
            decisions=db.execute("""SELECT COUNT(*) FROM native_audio01j_creator_events
                WHERE project_id=? AND operation='final_av' AND object_id=?
                AND revision=1""",(project_id,export_id)).fetchone()
        if len(rows)!=1 or not decisions or decisions[0]!=1:
            raise PermissionError("No completed native AV worker and creator publication")
        job=rows[0][0]
        grant=self._grant(job)
        file=self.root/job/"plan.json"
        if file.is_symlink() or not file.is_file() or sha_file(file)!=grant["plan_sha"]:
            raise RuntimeError("Native final AV plan is not authentic")
        plan=json.loads(file.read_bytes())
        if (plan["project_id"]!=project_id or plan["export_id"]!=export_id
            or Path(plan["destination"])!=Path(output_dir).absolute()):
            raise RuntimeError("Native published AV identity/location differs")
        self.audio_host.verify_delivery(
            project_id,plan["audio_delivery_id"],plan["audio_dir"],
            ffmpeg=ffmpeg,ffprobe=ffprobe)
        return verify_final_av(self.capture,project_id,export_id,output_dir,
                               movie_dir,audio_dir,ffmpeg=ffmpeg,ffprobe=ffprobe)

    def recover_completed(self,job):
        """Recover a stopped, complete AV mux, never rerender or seize unknown OS work."""
        grant=self._grant(job)
        task=self.ledger.get_task(job)
        if grant["stopped"]!=1 or task is None:
            raise PermissionError("No durable native AV worker-stop witness")
        sealed=self.root/job/"plan.json"
        if sealed.is_symlink() or sha_file(sealed)!=grant["plan_sha"]:
            raise RuntimeError("Native AV plan was changed after admission")
        plan=json.loads(sealed.read_bytes())
        row,_=self._publish_verified_master(job,plan)
        verify_final_av(self.capture,plan["project_id"],plan["export_id"],
            plan["destination"],plan["movie_dir"],plan["audio_dir"],
            ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
        if grant["result_sha"] not in (None,row["document_sha256"]):
            raise RuntimeError("Conflicting final AV completion digest")
        if task["state"] not in ("ACTIVE","SUCCEEDED"):
            raise RuntimeError("Cannot recover final AV from unknown state")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01j_grants SET result_sha=? WHERE job_id=?",
                       (row["document_sha256"],job))
            db.commit()
        if task["state"]=="ACTIVE":
            self.ledger.finish(job,"SUCCEEDED","Reconciled exact native stopped AV master")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE native_audio01j_creator_events SET revision=1
                WHERE project_id=? AND operation='final_av' AND object_id=?
                  AND revision=-1""",(plan["project_id"],plan["export_id"]))
            db.commit()
        return {"job_id":job,"state":"SUCCEEDED","rerendered":False}
