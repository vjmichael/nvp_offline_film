"""AUDIO-01I trusted mastering and controlled delivery host.

Only this host owns creator grants, Job Object lifecycle, and publication.
An approved mix is NOT an approved master; these are separate permissions.
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
from backend.nvp_audio01i_mastering import (
    FORMAT as CANDIDATE_FORMAT, PROFILES, accepted_source,
    inspect_native,sha_file)
from backend.nvp_audio01i_fault_matrix import crash_after
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained

FORMAT="nvp.audio01i.native_plan.v1"
DELIVERY="nvp.audio01i.final_audio_delivery.v1"
ROOT=Path(__file__).resolve().parents[1]


class NativeAudio01IHost:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root,*,
                 verify_creator_action,strict_linux_tree=None):
        if not isinstance(capture,DigitalCapture) or not isinstance(ledger,TaskLedger) or not callable(verify_creator_action):
            raise TypeError("Trusted FilmIndex, ledger and creator policy required")
        self.capture,self.ledger,self.creator=capture,ledger,verify_creator_action
        self.root=Path(root)
        if self.root.is_symlink():raise RuntimeError("Unsafe native master root")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=self.root.resolve()
        self.owner="audio01i_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:22]
        self.python=Path(sys.executable).resolve()
        self.worker=ROOT/"tools/nvp_audio01i_native_worker.py"
        self.strict_linux_tree=(sys.platform=="linux" if strict_linux_tree is None
                                else strict_linux_tree)
        if type(self.strict_linux_tree) is not bool:raise TypeError("Invalid cgroup policy")
        self.events={}
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01i_grants(
               job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
               spec_sha TEXT NOT NULL, plan_sha TEXT NOT NULL,
               python_sha TEXT NOT NULL, worker_sha TEXT NOT NULL,
               ffmpeg_sha TEXT NOT NULL, ffprobe_sha TEXT NOT NULL,
               expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
               stopped INTEGER NOT NULL DEFAULT 0, result_sha TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01i_master_events(
               event_sha TEXT PRIMARY KEY, project_id TEXT NOT NULL,
               candidate_id TEXT NOT NULL, job_id TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01i_delivery_events(
               event_sha TEXT PRIMARY KEY, project_id TEXT NOT NULL,
               delivery_id TEXT NOT NULL, revision INTEGER NOT NULL)""")
        self.bindings=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _inspect_contained(self,wav,ffmpeg,ffprobe,samples):
        """Run real PCM24 readback in a resource-admitted contained process."""
        wav=Path(wav)
        if wav.is_symlink() or not wav.is_file():
            raise RuntimeError("Unsafe source for native master inspection")
        # Do not execute arbitrary commands supplied as a 'codec tool'.
        if (Path(str(ffmpeg)).name.lower() not in ("ffmpeg","ffmpeg.exe") or
            Path(str(ffprobe)).name.lower() not in ("ffprobe","ffprobe.exe")):
            raise PermissionError("Only pinned native FFmpeg and FFprobe supported")
        tools={}
        for name,requested in (("ffmpeg",ffmpeg),("ffprobe",ffprobe)):
            executable=shutil.which(str(requested))
            if executable is None:raise RuntimeError("Missing real native "+name)
            tools[name]=str(Path(executable).resolve(strict=True))
        job="inspectjob"+secrets.token_hex(16)
        folder=self.root/job
        folder.mkdir(mode=0o700)
        plan={"format":"nvp.audio01i.inspect_plan.v1",
              "wav":str(wav.resolve(strict=True)),"wav_sha":sha_file(wav),
              "samples":samples,
              "ffmpeg":tools["ffmpeg"],"ffmpeg_sha":sha_file(tools["ffmpeg"]),
              "ffprobe":tools["ffprobe"],"ffprobe_sha":sha_file(tools["ffprobe"])}
        plan_file=folder/"plan.json"
        with plan_file.open("xb") as out:
            out.write(canonical_bytes(plan));out.flush();os.fsync(out.fileno())
        admitted=self.ledger.admit(AdmissionRequest(
            job,"compositing","Contained independent PCM24 inspection",1024))
        if not admitted["admitted"]:
            raise RuntimeError("No native budget available for independent inspection")
        proc=None;reaped=False
        try:
            self.ledger.update(job,"verifying_output","Real independent PCM24 decode and loudness")
            script=ROOT/"tools/nvp_audio01i_inspect_worker.py"
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                proc=launch_contained(
                    [str(self.python),str(script),"--plan",str(plan_file)],
                    cwd=str(folder),stdout=out,stderr=err,memory_mb=1024,
                    linux_cgroup_tree_required=self.strict_linux_tree)
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=180)
                if code:raise RuntimeError("Contained inspection failed: "+str(code))
                proc.close();proc=None;reaped=True
            receipt=folder/"inspection.json"
            if receipt.is_symlink() or not receipt.is_file():
                raise RuntimeError("No independently measured PCM24 receipt")
            if (sha_file(wav)!=plan["wav_sha"] or
                sha_file(tools["ffmpeg"])!=plan["ffmpeg_sha"] or
                sha_file(tools["ffprobe"])!=plan["ffprobe_sha"]):
                raise RuntimeError("Native measurement source changed after inspection")
            measured=json.loads(receipt.read_bytes())
            if (measured.get("samples_per_channel")!=samples or
                measured.get("bit_depth")!=24 or
                measured.get("sample_rate")!=48000 or
                measured.get("measurement")!="ffmpeg_loudnorm_ebu_r128"):
                raise RuntimeError("Invalid contained PCM24 measurement receipt")
            self.ledger.finish(job,"SUCCEEDED","Independent native master verified")
            return measured
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    reaped=proc.poll() is not None
                    proc.close()
                except BaseException:reaped=False
            if reaped and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.finish(job,"FAILED","Native master inspection rejected")
            raise

    def _grant(self,job):
        with self.ledger._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM native_audio01i_grants WHERE job_id=?",(job,)).fetchone()
        if row is None:raise KeyError("Unknown mastering job")
        return dict(row)

    def _native_approved_mix(self,project_id,decision_id,decision_revision):
        """Validate AUDIO-01H actual native provenance, not just a JSON flag."""
        decision,mix,wav=accepted_source(
            self.capture,project_id,decision_id,decision_revision)
        with self.ledger._db() as db:
            event=db.execute("""SELECT COUNT(*) FROM native_audio01h_creator_events
                WHERE project_id=? AND decision_id=? AND revision=?""",
                (project_id,decision_id,decision_revision)).fetchone()
            producers=db.execute("""SELECT g.job_id FROM native_audio01h_grants g
                JOIN tasks t ON t.id=g.job_id
                WHERE g.result_sha=? AND g.stopped=1 AND g.revoked=0
                AND t.state='SUCCEEDED' AND t.reserved=0""",
                (mix["document_sha256"],)).fetchall()
        if event is None or event[0]!=1:
            raise PermissionError("Mix approval lacks completed native creator-event provenance")
        eligible=0
        for (job,) in producers:
            # AUDIO-01H grants live under its independent root, so their
            # original spec is verified through durable SHA/FilmIndex custody.
            eligible+=1
        if eligible!=1:
            raise PermissionError("Approved source lacks exactly one completed native audio worker")
        return decision,mix,wav

    def _check(self,approval,digest,spec):
        try:
            job=spec["task_id"];grant=self._grant(job)
            path=self.root/job/"plan.json"
            if (grant["approval_id"]!=approval or grant["spec_sha"]!=digest or
                grant["revoked"] or grant["result_sha"] is not None or
                time.time()>grant["expires_at"] or
                path.is_symlink() or sha_file(path)!=grant["plan_sha"] or
                sha_file(self.python)!=grant["python_sha"] or
                sha_file(self.worker)!=grant["worker_sha"] or
                hashlib.sha256(canonical_bytes(spec)).hexdigest()!=digest):
                return False
            plan=json.loads(path.read_bytes())
            if (canonical_bytes(plan)!=path.read_bytes() or plan.get("format")!=FORMAT
                or plan["project_id"]!=spec["project_id"]
                or plan["candidate_id"]!=spec["candidate_id"]
                or plan["destination"]!=spec["destination"]
                or sha_file(plan["ffmpeg"])!=grant["ffmpeg_sha"]
                or sha_file(plan["ffprobe"])!=grant["ffprobe_sha"]
                or Path(plan["destination"]).exists()):
                return False
            decision,_,_=self._native_approved_mix(
                plan["project_id"],plan["decision_id"],plan["decision_revision"])
            event=self.events.get(job)
            return (decision["document_sha256"]==spec["decision_sha"]
                    and event is not None and self.creator(event,spec["scope"]) is True)
        except (OSError,KeyError,ValueError,RuntimeError,TypeError,PermissionError):
            return False

    def stage(self,project_id,decision_id,decision_revision,candidate_id,profile,
              destination,creator_event,*,ffmpeg="ffmpeg",ffprobe="ffprobe",
              ram_mb=1024,duration_s=1200):
        _id(candidate_id,"master candidate ID")
        if profile not in PROFILES:raise ValueError("Unknown mastering profile")
        if (type(ram_mb) is not int or not 1024<=ram_mb<=8192
            or type(duration_s) is not int or not 60<=duration_s<=3600):
            raise ValueError("Invalid mastering resource admission")
        decision,_,wav=self._native_approved_mix(project_id,decision_id,decision_revision)
        target=Path(destination).absolute()
        if (target.exists() or target.is_symlink() or target.parent.is_symlink()
            or not target.parent.is_dir() or target.suffix.lower()!=".wav"):
            raise RuntimeError("New absent WAV master candidate destination required")
        try:self.capture.index.read_revision(project_id,candidate_id)
        except KeyError:pass
        else:raise RuntimeError("Master candidate identity already exists")
        binaries={}
        for key,name in (("ffmpeg",ffmpeg),("ffprobe",ffprobe)):
            resolved=shutil.which(name)
            if resolved is None:raise RuntimeError("Missing native "+key)
            binaries[key]=str(Path(resolved).resolve(strict=True))
        job="masterjob"+secrets.token_hex(16)
        scope={"operation":"nvp.audio01i.create_master_candidate",
               "project_id":project_id,"decision_id":decision_id,
               "decision_revision":decision_revision,
               "decision_sha256":decision["document_sha256"],
               "candidate_id":candidate_id,"profile":profile,
               "destination":str(target),"final_master":False}
        if self.creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Creator did not authorize exact mastering action")
        if type(creator_event) is not str or not creator_event:
            raise PermissionError("Exact creator event identifier required")
        event_sha=hashlib.sha256(creator_event.encode("utf8")).hexdigest()
        # Reserve the per-turn mastering event before granting a job.
        # Duplicate submission cannot spend the same creator action twice.
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM native_audio01i_master_events WHERE event_sha=?",
                          (event_sha,)).fetchone():
                raise PermissionError("Mastering creator event already consumed")
            db.execute("INSERT INTO native_audio01i_master_events VALUES(?,?,?,?)",
                       (event_sha,project_id,candidate_id,job))
            db.commit()
        crash_after("master_event_reserved")
        plan={"format":FORMAT,"studio_db_path":str(self.capture.studio.db_path),
              "project_id":project_id,"decision_id":decision_id,
              "decision_revision":decision_revision,"candidate_id":candidate_id,
              "profile":profile,"destination":str(target),
              "ffmpeg":binaries["ffmpeg"],"ffprobe":binaries["ffprobe"],
              "final_master":False,"delivery_approved":False}
        spec={"task_id":job,"kind":"compositing","project_id":project_id,
              "decision_sha":decision["document_sha256"],
              "candidate_id":candidate_id,"destination":str(target),"scope":scope}
        folder=self.root/job
        folder.mkdir(mode=0o700)
        with (folder/"plan.json").open("xb") as f:
            f.write(canonical_bytes(plan));f.flush();os.fsync(f.fileno())
        approval="masterapproval"+secrets.token_hex(16)
        seal=hashlib.sha256(canonical_bytes(spec)).hexdigest()
        self.events[job]=creator_event
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_audio01i_grants
              (job_id,approval_id,spec_sha,plan_sha,python_sha,worker_sha,
               ffmpeg_sha,ffprobe_sha,expires_at) VALUES(?,?,?,?,?,?,?,?,?)""",
              (job,approval,seal,sha_file(folder/"plan.json"),sha_file(self.python),
               sha_file(self.worker),sha_file(binaries["ffmpeg"]),
               sha_file(binaries["ffprobe"]),time.time()+duration_s))
            db.commit()
        crash_after("master_grant_committed")
        self.bindings.enqueue(
            AdmissionRequest(job,"compositing","PCM24 native mastering candidate",ram_mb),
            owner_key=self.owner,lane="standard",approval_id=approval,document=spec)
        crash_after("master_queued")
        return {"job_id":job,"state":"QUEUED","candidate_id":candidate_id}

    def run_next(self,*,timeout_seconds=600):
        admitted=self.bindings.claim_next(owner_key=self.owner)
        if admitted is None or not admitted["admitted"]:return admitted
        crash_after("master_claimed")
        job=admitted["task_id"]
        proc=None;reaped=False
        try:
            self.bindings.verified_spec(job,owner_key=self.owner)
            folder=self.root/job
            plan=json.loads((folder/"plan.json").read_bytes())
            self.ledger.update(job,"rendering","Real native PCM24 master candidate")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                proc=launch_contained([str(self.python),str(self.worker),"--plan",
                    str(folder/"plan.json")],cwd=str(folder),
                    stdout=out,stderr=err,
                    memory_mb=self.ledger.get_task(job)["ram_mb"],
                    linux_cgroup_tree_required=self.strict_linux_tree)
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code:raise RuntimeError("Mastering worker failed: "+str(code))
                proc.close();proc=None;reaped=True
            crash_after("master_worker_reaped")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01i_grants SET stopped=1 WHERE job_id=?",(job,))
                db.commit()
            crash_after("master_stop_witness_committed")
            self.ledger.update(job,"verifying_output","Independent mastered PCM24 verification")
            rec=self.capture.index.read_revision(plan["project_id"],plan["candidate_id"],1)
            doc=rec["data"]
            receipt_file=folder/"worker_receipt.json"
            if receipt_file.is_symlink():raise RuntimeError("Unsafe master receipt")
            receipt=json.loads(receipt_file.read_bytes())
            decision,source,_=self._native_approved_mix(
                plan["project_id"],plan["decision_id"],plan["decision_revision"])
            if (rec["kind"]!="audio" or doc.get("format")!=CANDIDATE_FORMAT
                or doc.get("profile")!=plan["profile"]
                or doc.get("decision_sha256")!=decision["document_sha256"]
                or doc.get("mix_sha256")!=source["document_sha256"]
                or doc.get("final_master") is not False
                or receipt.get("format")!="nvp.audio01i.worker_receipt.v1"
                or receipt.get("document_sha256")!=rec["document_sha256"]
                or receipt.get("wav_sha256")!=doc["candidate_wav_sha256"]
                or receipt.get("final_master") is not False
                or sha_file(plan["destination"])!=doc["candidate_wav_sha256"]):
                raise RuntimeError("Native mastering receipt and indexed candidate disagree")
            self.capture.index.verify_media_file(plan["project_id"],doc["candidate_wav_sha256"],"audio/wav")
            measured=self._inspect_contained(plan["destination"],plan["ffmpeg"],
                                             plan["ffprobe"],doc["samples_per_channel"])
            if measured!=doc["analysis"]:raise RuntimeError("Independent master measurement mismatch")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01i_grants SET result_sha=? WHERE job_id=?",
                           (rec["document_sha256"],job))
                db.commit()
            crash_after("master_result_committed")
            self.ledger.finish(job,"SUCCEEDED","Verified immutable unapproved PCM24 candidate")
            crash_after("master_ledger_finished")
            return {"job_id":job,"state":"SUCCEEDED","candidate_id":plan["candidate_id"],
                    "document_sha256":rec["document_sha256"],"final_master":False}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    reaped=proc.poll() is not None
                    proc.close()
                except BaseException:reaped=False
            if reaped and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.update(job,"recovering","Master candidate quarantined; audit required")
            raise

    def recover_candidate(self,job):
        """Reconcile only with a durable native stop and complete immutable proof.

        An un-reaped worker never releases its ACTIVE reservation. A completed
        worker can be reconciled without rerendering, independent of creator
        authorization events which deliberately do not survive host restart.
        """
        grant=self._grant(job)
        task=self.ledger.get_task(job)
        if grant["stopped"]!=1 or task is None:
            raise PermissionError("Cannot recover master without durable OS-stop witness")
        file=self.root/job/"plan.json"
        if file.is_symlink() or not file.is_file() or sha_file(file)!=grant["plan_sha"]:
            raise RuntimeError("Mastering plan changed after admission")
        plan=json.loads(file.read_bytes())
        decision,mix,_=self._native_approved_mix(
            plan["project_id"],plan["decision_id"],plan["decision_revision"])
        rec=self.capture.index.read_revision(plan["project_id"],plan["candidate_id"],1)
        doc=rec["data"]
        receipt_file=self.root/job/"worker_receipt.json"
        if receipt_file.is_symlink() or not receipt_file.is_file():
            raise RuntimeError("No authentic mastering worker receipt")
        receipt=json.loads(receipt_file.read_bytes())
        target=Path(plan["destination"])
        if (rec["kind"]!="audio" or doc.get("format")!=CANDIDATE_FORMAT
            or doc.get("profile")!=plan["profile"]
            or doc.get("decision_sha256")!=decision["document_sha256"]
            or doc.get("mix_sha256")!=mix["document_sha256"]
            or doc.get("final_master") is not False
            or receipt.get("format")!="nvp.audio01i.worker_receipt.v1"
            or receipt.get("document_sha256")!=rec["document_sha256"]
            or receipt.get("wav_sha256")!=doc["candidate_wav_sha256"]
            or receipt.get("final_master") is not False
            or target.is_symlink() or not target.is_file()
            or sha_file(target)!=doc["candidate_wav_sha256"]):
            raise RuntimeError("Master recovery has conflicting immutable evidence")
        self.capture.index.verify_media_file(
            plan["project_id"],doc["candidate_wav_sha256"],"audio/wav")
        measured=self._inspect_contained(target,plan["ffmpeg"],plan["ffprobe"],
                                          doc["samples_per_channel"])
        if measured!=doc["analysis"]:
            raise RuntimeError("Recovered master decoded proof differs")
        if grant["result_sha"] not in (None,rec["document_sha256"]):
            raise RuntimeError("Conflicting master result digests")
        if task["state"]=="SUCCEEDED":
            if grant["result_sha"]!=rec["document_sha256"]:
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("UPDATE native_audio01i_grants SET result_sha=? WHERE job_id=?",
                               (rec["document_sha256"],job))
                    db.commit()
            return {"job_id":job,"state":"SUCCEEDED","rerendered":False}
        if task["state"]!="ACTIVE":
            raise RuntimeError("Only ACTIVE stopped master may be reconciled")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01i_grants SET result_sha=? WHERE job_id=?",
                       (rec["document_sha256"],job))
            db.commit()
        self.ledger.finish(job,"SUCCEEDED","Reconciled independently verified stopped master")
        return {"job_id":job,"state":"SUCCEEDED","rerendered":False}

    def deliver(self,project_id,candidate_id,delivery_id,folder,creator_event,*,
                ffmpeg="ffmpeg",ffprobe="ffprobe"):
        """Second explicit creator authorization; atomic directory promotion."""
        _id(delivery_id,"final master delivery ID")
        record=self.capture.index.read_revision(project_id,candidate_id,1)
        doc=record["data"]
        if record["kind"]!="audio" or doc.get("format")!=CANDIDATE_FORMAT:
            raise RuntimeError("Native master candidate required")
        with self.ledger._db() as db:
            matches=db.execute("""SELECT g.job_id FROM native_audio01i_grants g
               JOIN tasks t ON g.job_id=t.id
               WHERE g.result_sha=? AND g.stopped=1 AND g.revoked=0
                 AND t.state='SUCCEEDED' AND t.reserved=0""",
                 (record["document_sha256"],)).fetchall()
        if len(matches)!=1:raise PermissionError("No uniquely completed native mastering job")
        job=matches[0][0]
        sealed=self.root/job/"plan.json"
        if sealed.is_symlink() or sha_file(sealed)!=self._grant(job)["plan_sha"]:
            raise RuntimeError("Mastering plan not authentic")
        plan=json.loads(sealed.read_bytes())
        if plan["project_id"]!=project_id or plan["candidate_id"]!=candidate_id:
            raise RuntimeError("Master native custody differs")
        # The original contained worker's destination is part of custody.
        # An altered candidate path cannot be masked by an intact blob copy.
        original_output=Path(plan["destination"])
        receipt_file=self.root/job/"worker_receipt.json"
        if (original_output.is_symlink() or not original_output.is_file()
            or sha_file(original_output)!=doc["candidate_wav_sha256"]
            or receipt_file.is_symlink() or not receipt_file.is_file()):
            raise RuntimeError("Original native mastering output is missing or changed")
        receipt=json.loads(receipt_file.read_bytes())
        if (receipt.get("document_sha256")!=record["document_sha256"]
            or receipt.get("wav_sha256")!=doc["candidate_wav_sha256"]
            or receipt.get("final_master") is not False):
            raise RuntimeError("Native mastering worker receipt changed")
        decision,_,_=self._native_approved_mix(
            project_id,doc["decision_id"],doc["decision_revision"])
        if doc["decision_sha256"]!=decision["document_sha256"]:
            raise PermissionError("Master decision was superseded")
        path=Path(folder).absolute()
        stage=path.with_name("."+path.name+".audio01i.stage")
        if (path.exists() or path.is_symlink() or stage.exists() or stage.is_symlink()
            or not path.parent.is_dir() or path.parent.is_symlink()):
            raise RuntimeError("Final delivery target or previous stage already exists")
        try:self.capture.index.read_revision(project_id,delivery_id)
        except KeyError:pass
        else:raise RuntimeError("Final delivery revision already exists")
        stored=self.capture.index.verify_media_file(
            project_id,doc["candidate_wav_sha256"],"audio/wav")
        src=Path(stored["path"])
        independently=self._inspect_contained(src,ffmpeg,ffprobe,doc["samples_per_channel"])
        if independently!=doc["analysis"]:
            raise RuntimeError("Delivery master loudness no longer matches proof")
        scope={"operation":"nvp.audio01i.approve_final_audio_delivery",
               "project_id":project_id,"candidate_id":candidate_id,
               "candidate_document_sha256":record["document_sha256"],
               "delivery_id":delivery_id,"destination":str(path),
               "profile":doc["profile"],"analysis":independently,
               "final_master":True}
        if type(creator_event) is not str or not creator_event or (
                self.creator(creator_event,dict(scope)) is not True):
            raise PermissionError("Explicit creator final master approval required")
        nonce=hashlib.sha256(creator_event.encode("utf8")).hexdigest()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM native_audio01i_delivery_events WHERE event_sha=?",
                          (nonce,)).fetchone():
                raise PermissionError("Final master approval event already consumed")
            db.execute("INSERT INTO native_audio01i_delivery_events VALUES(?,?,?,-1)",
                       (nonce,project_id,delivery_id))
            db.commit()
        crash_after("delivery_event_reserved")
        stage.mkdir(mode=0o700)
        crash_after("delivery_stage_created")
        deliver_wav=stage/"master.wav"
        with src.open("rb") as original,deliver_wav.open("xb") as target:
            shutil.copyfileobj(original,target,1024*1024)
            target.flush();os.fsync(target.fileno())
        crash_after("delivery_wav_fsynced")
        if sha_file(deliver_wav)!=doc["candidate_wav_sha256"]:
            raise RuntimeError("Delivery copy changed approved master bytes")
        document={"format":DELIVERY,"status":"creator_approved_final_audio",
                  "project_id":project_id,"candidate_id":candidate_id,
                  "candidate_revision":1,
                  "candidate_sha256":record["document_sha256"],
                  "wav_sha256":doc["candidate_wav_sha256"],
                  "profile":doc["profile"],"analysis":independently,
                  "final_mix":True,"director_approved":True,
                  "final_master":True,"video_master":False,
                  "dcp_delivered":False}
        manifest=stage/"manifest.json"
        with manifest.open("xb") as output:
            output.write(canonical_bytes(document));output.flush();os.fsync(output.fileno())
        crash_after("delivery_manifest_fsynced")
        os.replace(stage,path)
        if os.name=="posix":
            fd=os.open(str(path.parent),os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
            try:os.fsync(fd)
            finally:os.close(fd)
        crash_after("delivery_directory_promoted")
        result=self.capture.index.register_revision(
            project_id,delivery_id,"audio",document,expected_revision=0,
            dependencies=[{"object_id":candidate_id,"revision":1,"role":"audio"},
                          {"object_id":doc["decision_id"],
                           "revision":doc["decision_revision"],"role":"audio"}])
        crash_after("delivery_filmindex_registered")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01i_delivery_events SET revision=? WHERE event_sha=?",
                       (result["revision"],nonce))
            db.commit()
        crash_after("delivery_event_finalized")
        return {"status":"CREATOR_APPROVED_FINAL_AUDIO","delivery_id":delivery_id,
                "document_sha256":result["document_sha256"],
                "wav_sha256":doc["candidate_wav_sha256"],
                "final_master":True,"video_master":False,"dcp_delivered":False}

    def verify_delivery(self,project_id,delivery_id,folder,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
        rec=self.capture.index.read_revision(project_id,delivery_id,1)
        doc=rec["data"];path=Path(folder)
        if rec["kind"]!="audio" or doc.get("format")!=DELIVERY:
            raise RuntimeError("Not a final audio delivery")
        with self.ledger._db() as db:
            source=db.execute("""SELECT COUNT(*) FROM native_audio01i_delivery_events
                WHERE project_id=? AND delivery_id=? AND revision=?""",
                (project_id,delivery_id,rec["revision"])).fetchone()
        if not source or source[0]!=1:
            raise PermissionError("Final master lacks a completed native creator approval event")
        if (path.is_symlink() or not path.is_dir() or
            (path/"manifest.json").is_symlink() or
            (path/"master.wav").is_symlink() or
            (path/"manifest.json").read_bytes()!=canonical_bytes(doc) or
            sha_file(path/"master.wav")!=doc["wav_sha256"]):
            raise RuntimeError("Final audio delivery was altered")
        self.capture.index.verify_media_file(project_id,doc["wav_sha256"],"audio/wav")
        candidate=self.capture.index.read_revision(project_id,doc["candidate_id"],1)
        if candidate["document_sha256"]!=doc["candidate_sha256"]:
            raise RuntimeError("Final delivery source revision changed")
        current=self.capture.index.read_revision(project_id,candidate["data"]["decision_id"])
        if (current["revision"]!=candidate["data"]["decision_revision"] or
            current["data"]["decision"]!="ACCEPT"):
            raise PermissionError("Previous director mix approval no longer current")
        measured=self._inspect_contained(path/"master.wav",ffmpeg,ffprobe,
                                         doc["analysis"]["samples_per_channel"])
        if measured!=doc["analysis"]:
            raise RuntimeError("Delivered PCM24 differs from approved analysis")
        return {"status":"VERIFIED_FINAL_AUDIO","final_master":True,
                "video_master":False,"dcp_delivered":False}
