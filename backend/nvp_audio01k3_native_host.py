"""AUDIO-01K.3 trusted native DCP host: creator approval, containment, QC.

Implements an actual SMPTE DCP *candidate* through DCP-o-matic and DcpDoctor.
A successful candidate is NOT yet a theatrically approved delivery.
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
from backend.nvp_audio01k3_dcp import (
    FORMAT, PROFILE, _safe_name, inspect_dcp_directory,inspect_cpl_timing,sha_file)
from backend.nvp_film_index import _id
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained

ROOT=Path(__file__).resolve().parents[1]
PLAN="nvp.audio01k3.native_plan.v1"


class NativeAudio01K3Host:
    def __init__(self,capture,ledger:TaskLedger,root,*,distribution_host,
                 verify_creator_action,strict_linux_tree=None):
        if (not isinstance(ledger,TaskLedger) or
            not callable(getattr(distribution_host,"verify",None)) or
            not callable(verify_creator_action)):
            raise TypeError("Trusted native ledger, distribution and creator policy required")
        self.capture=capture
        self.ledger=ledger
        self.distribution=distribution_host
        self.creator=verify_creator_action
        requested=Path(root)
        if requested.is_symlink():
            raise RuntimeError("Unsafe DCP host root")
        requested.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.root=requested.resolve()
        self.python=Path(sys.executable).resolve()
        self.worker=ROOT/"tools/nvp_audio01k3_dcp_worker.py"
        self.owner="audio01k3_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:22]
        self.strict_linux_tree=(sys.platform=="linux" if strict_linux_tree is None
                                else strict_linux_tree)
        if type(self.strict_linux_tree) is not bool:
            raise ValueError("Invalid delegated Linux containment policy")
        self.events={}
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01k3_grants(
                job_id TEXT PRIMARY KEY,approval_id TEXT UNIQUE NOT NULL,
                spec_sha TEXT NOT NULL,plan_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL,worker_sha TEXT NOT NULL,
                create_sha TEXT NOT NULL,cli_sha TEXT NOT NULL,
                doctor_sha TEXT NOT NULL,expires_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                stopped INTEGER NOT NULL DEFAULT 0,
                result_sha TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01k3_events(
                event_sha TEXT PRIMARY KEY,project_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT -1)""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS native_audio01k3_single_candidate
                ON native_audio01k3_events(project_id,candidate_id)""")
        self.bindings=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _grant(self,job):
        with self.ledger._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM native_audio01k3_grants WHERE job_id=?",
                           (job,)).fetchone()
        if row is None: raise KeyError("No native SMPTE DCP grant")
        return dict(row)

    def _source(self,plan):
        project=plan["project_id"]
        proof=self.distribution.verify(project,plan["distribution_id"],
             plan["distribution_dir"],plan["final_av_dir"],
             plan["movie_dir"],plan["audio_dir"],
             ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
        if proof.get("status")!="VERIFIED_MEZZANINE_DISTRIBUTION":
            raise PermissionError("DCP source is not an approved mezzanine")
        doc=self.capture.index.read_revision(project,plan["distribution_id"],1)
        if (doc["document_sha256"]!=plan["distribution_sha"] or
            doc["data"]["delivered_movie_sha256"]!=plan["movie_sha256"]):
            raise PermissionError("DCP original approved source digest changed")
        movie=Path(plan["movie"])
        if movie.is_symlink() or not movie.is_file() or sha_file(movie)!=plan["movie_sha256"]:
            raise RuntimeError("DCP input MOV changed after creator approval")
        return doc

    def _check(self,approval,digest,spec):
        try:
            job=spec["task_id"]
            grant=self._grant(job)
            path=self.root/job/"plan.json"
            if (grant["approval_id"]!=approval or grant["spec_sha"]!=digest or
                grant["revoked"] or grant["result_sha"] is not None or
                time.time()>grant["expires_at"] or path.is_symlink() or
                sha_file(path)!=grant["plan_sha"] or
                sha_file(self.python)!=grant["python_sha"] or
                sha_file(self.worker)!=grant["worker_sha"] or
                hashlib.sha256(canonical_bytes(spec)).hexdigest()!=digest):
                return False
            plan=json.loads(path.read_bytes())
            if (canonical_bytes(plan)!=path.read_bytes() or plan.get("format")!=PLAN
                or plan.get("approved_spec")!=spec or
                plan["project_id"]!=spec["project_id"] or
                plan["candidate_id"]!=spec["candidate_id"] or
                plan["destination"]!=spec["destination"] or
                Path(plan["destination"]).exists() or
                Path(plan["stage"]).exists() or
                any(sha_file(plan[key])!=grant[column] for key,column in (
                    ("dcp_create","create_sha"),("dcp_cli","cli_sha"),
                    ("dcpdoctor","doctor_sha")))):
                return False
            self._source(plan)
            event=self.events.get(job)
            return event is not None and self.creator(event,spec["scope"]) is True
        except (OSError,ValueError,KeyError,RuntimeError,TypeError,PermissionError):
            return False

    def stage(self,project_id,distribution_id,distribution_dir,final_av_dir,
              movie_dir,audio_dir,candidate_id,destination,title,creator_event,*,
              create_bin="dcpomatic2_create",cli_bin="dcpomatic2_cli",
              doctor_bin="dcpdoctor",ffmpeg="ffmpeg",ffprobe="ffprobe",
              ram_mb=4096,duration_s=7200):
        _id(candidate_id,"cinema DCP candidate ID")
        _safe_name(title)
        if (type(ram_mb) is not int or not 2048<=ram_mb<=8192 or
            type(duration_s) is not int or not 300<=duration_s<=86400):
            raise ValueError("Invalid DCP worker RAM budget or creator grant lifetime")
        dest=Path(destination).absolute()
        staged=dest.with_name("."+dest.name+".audio01k3.stage")
        if (dest.exists() or dest.is_symlink() or staged.exists() or
            staged.is_symlink() or dest.parent.is_symlink() or
            not dest.parent.is_dir()):
            raise RuntimeError("Destination and previous cinema staging must be absent")
        try:self.capture.index.read_revision(project_id,candidate_id)
        except KeyError:pass
        else:raise RuntimeError("Cinema DCP candidate ID is already in FilmIndex")
        # Never execute a model-specified arbitrary shell program as a
        # stand-in for a cinema encoder or independent validator.
        allowed={
            "dcp_create": {"dcpomatic2_create","dcpomatic2_create.exe"},
            "dcp_cli": {"dcpomatic2_cli","dcpomatic2_cli.exe"},
            "dcpdoctor": {"dcpdoctor","dcpdoctor.exe"},
            "ffmpeg": {"ffmpeg","ffmpeg.exe"},
            "ffprobe": {"ffprobe","ffprobe.exe"},
        }
        provided={"dcp_create":create_bin,"dcp_cli":cli_bin,
                  "dcpdoctor":doctor_bin,"ffmpeg":ffmpeg,"ffprobe":ffprobe}
        for key,value in provided.items():
            if Path(str(value)).name.lower() not in allowed[key]:
                raise PermissionError("Unsupported native cinema executable: "+key)
        paths={}
        for key,value in (("dcp_create",create_bin),("dcp_cli",cli_bin),
                          ("dcpdoctor",doctor_bin),("ffmpeg",ffmpeg),
                          ("ffprobe",ffprobe)):
            location=shutil.which(str(value))
            if location is None:
                raise RuntimeError("Missing real installed native cinema dependency: "+key)
            paths[key]=str(Path(location).resolve(strict=True))
        distribution=self.capture.index.read_revision(project_id,distribution_id,1)
        movie=Path(distribution_dir)/"feature_master.mov"
        if (movie.is_symlink() or not movie.is_file() or
            sha_file(movie)!=distribution["data"]["delivered_movie_sha256"]):
            raise RuntimeError("Cinema source is missing or changed")
        scope={"operation":"nvp.audio01k3.author_dcp_candidate",
               "project_id":project_id,"distribution_id":distribution_id,
               "distribution_sha":distribution["document_sha256"],
               "movie_sha256":distribution["data"]["delivered_movie_sha256"],
               "candidate_id":candidate_id,"destination":str(dest),
               "profile":PROFILE,"title":title,
               "dcp_delivered":False}
        if (type(creator_event) is not str or not creator_event or
            self.creator(creator_event,dict(scope)) is not True):
            raise PermissionError("Creator denied exact SMPTE cinema candidate")
        job="dcpjob"+secrets.token_hex(16)
        spec={"task_id":job,"kind":"compositing","project_id":project_id,
              "candidate_id":candidate_id,"destination":str(dest),
              "scope":scope}
        plan={"format":PLAN,"studio_db_path":str(self.capture.studio.db_path),
              "ledger_path":str(self.ledger.db_path),"job_id":job,
              "owner_key":self.owner,"approved_spec":spec,
              "project_id":project_id,"distribution_id":distribution_id,
              "distribution_sha":distribution["document_sha256"],
              "distribution_dir":str(Path(distribution_dir).resolve(strict=True)),
              "final_av_dir":str(Path(final_av_dir).resolve(strict=True)),
              "movie_dir":str(Path(movie_dir).resolve(strict=True)),
              "audio_dir":str(Path(audio_dir).resolve(strict=True)),
              "movie":str(movie.resolve(strict=True)),
              "movie_sha256":distribution["data"]["delivered_movie_sha256"],
              "frames":distribution["data"]["frames"],
              "candidate_id":candidate_id,"destination":str(dest),
              "stage":str(staged),"title":title,
              **{key:paths[key] for key in paths},
              **{key+"_sha":sha_file(paths[key]) for key in (
                  "dcp_create","dcp_cli","dcpdoctor")},
              "dcp_delivered":False,"creator_approved_theatrical_delivery":False}
        self._source(plan)
        folder=self.root/job
        folder.mkdir(mode=0o700)
        with (folder/"plan.json").open("xb") as f:
            f.write(canonical_bytes(plan))
            f.flush();os.fsync(f.fileno())
        approval="dcpapproval"+secrets.token_hex(16)
        digest=hashlib.sha256(canonical_bytes(spec)).hexdigest()
        event_sha=hashlib.sha256(creator_event.encode("utf8")).hexdigest()
        self.events[job]=creator_event
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM native_audio01k3_events WHERE event_sha=?",
                          (event_sha,)).fetchone():
                raise PermissionError("DCP creator event previously consumed")
            db.execute("INSERT INTO native_audio01k3_events VALUES(?,?,?,-1)",
                       (event_sha,project_id,candidate_id))
            db.execute("""INSERT INTO native_audio01k3_grants(
                job_id,approval_id,spec_sha,plan_sha,python_sha,worker_sha,
                create_sha,cli_sha,doctor_sha,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (job,approval,digest,sha_file(folder/"plan.json"),
                 sha_file(self.python),sha_file(self.worker),
                 plan["dcp_create_sha"],plan["dcp_cli_sha"],
                 plan["dcpdoctor_sha"],time.time()+duration_s))
            db.commit()
        self.bindings.enqueue(AdmissionRequest(
            job,"compositing","SMPTE DCP J2K/MXF authoring",ram_mb),
            owner_key=self.owner,lane="standard",approval_id=approval,
            document=spec)
        return {"job_id":job,"state":"QUEUED","candidate_id":candidate_id}

    def _verify_candidate(self,job,plan):
        grant=self._grant(job)
        if grant["stopped"]!=1:
            raise PermissionError("No durable native DCP worker stop witness")
        folder=self.root/job
        file=folder/"worker_receipt.json"
        if file.is_symlink() or not file.is_file():
            raise RuntimeError("No trustworthy cinema worker receipt")
        receipt=json.loads(file.read_bytes())
        staged=Path(plan["stage"])
        target=Path(plan["destination"])
        if staged.exists() and target.exists():
            raise RuntimeError("Conflicting DCP staging and published directory")
        source=staged if staged.is_dir() else target
        from backend.nvp_audio01k3_dcp import inspect_dcp_directory
        proof=inspect_dcp_directory(source)
        if (receipt.get("format")!="nvp.audio01k3.worker_receipt.v1"
            or receipt.get("distribution_document_sha256")!=plan["distribution_sha"]
            or receipt.get("source_movie_sha256")!=plan["movie_sha256"]
            or receipt.get("dcp_delivered") is not False
            or receipt.get("structural_proof")!=proof):
            raise RuntimeError("Contained DCP receipt differs from actual assets")
        reel_clock=inspect_cpl_timing(source,plan["frames"])
        if receipt.get("cpl_timing")!=reel_clock:
            raise RuntimeError("DCP reel timing differs from approved source duration")
        qc=receipt.get("independent_qc")
        if (not isinstance(qc,dict) or
            qc.get("format")!="nvp.audio01k3.independent_smpte_qc.v1" or
            qc.get("smpte_validator_passed") is not True or
            qc.get("asset_sha256_proof")!=proof["assets"] or
            qc.get("validator_sha256")!=plan["dcpdoctor_sha"]):
            raise RuntimeError("Independent cinema QC missing or mismatched")
        for name,digest in (
            ("dcpdoctor_stdout.txt",qc["stdout_sha256"]),
            ("dcpdoctor_stderr.txt",qc["stderr_sha256"])
        ):
            evidence=folder/name
            if (evidence.is_symlink() or not evidence.is_file()
                or evidence.stat().st_size>2*1024*1024
                or sha_file(evidence)!=digest):
                raise RuntimeError("Independent validator audit evidence changed")
        self._source(plan)
        return source,proof,qc

    def run_next(self,*,timeout_seconds=7200):
        admitted=self.bindings.claim_next(owner_key=self.owner)
        if admitted is None or not admitted["admitted"]:
            return admitted
        job=admitted["task_id"]
        proc=None;reaped=False
        try:
            self.bindings.verified_spec(job,owner_key=self.owner)
            folder=self.root/job
            plan=json.loads((folder/"plan.json").read_bytes())
            self.ledger.update(job,"rendering","Contained JPEG2000/MXF SMPTE authoring")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                proc=launch_contained(
                    [str(self.python),str(self.worker),"--plan",str(folder/"plan.json")],
                    cwd=str(folder),stdout=out,stderr=err,
                    memory_mb=self.ledger.get_task(job)["ram_mb"],
                    linux_cgroup_tree_required=self.strict_linux_tree)
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code:
                    raise RuntimeError("Native cinema worker exited: "+str(code))
                proc.close();proc=None;reaped=True
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01k3_grants SET stopped=1 WHERE job_id=?",
                           (job,))
                db.commit()
            rec=self._publish_candidate(job,plan)
            return {"job_id":job,"state":"SUCCEEDED",
                    "candidate_id":plan["candidate_id"],
                    "document_sha256":rec["document_sha256"],
                    "dcp_candidate":True,"dcp_delivered":False}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    reaped=proc.poll() is not None
                    proc.close()
                except BaseException:reaped=False
            if reaped and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.update(job,"recovering",
                    "DCP candidate interrupted; durable audit required")
            raise

    def _publish_candidate(self,job,plan):
        source,proof,qc=self._verify_candidate(job,plan)
        dest=Path(plan["destination"])
        if source!=dest:
            if dest.exists() or dest.is_symlink():
                raise RuntimeError("DCP delivery destination is already occupied")
            os.replace(source,dest)
            if os.name=="posix":
                fd=os.open(str(dest.parent),os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
                try:os.fsync(fd)
                finally:os.close(fd)
        doc={"format":FORMAT,"status":"independently_validated_dcp_candidate",
             "profile":PROFILE,"project_id":plan["project_id"],
             "distribution_id":plan["distribution_id"],
             "distribution_sha256":plan["distribution_sha"],
             "original_mov_sha256":plan["movie_sha256"],
             "asset_proof":proof,"independent_qc":qc,
             "cpl_timing":inspect_cpl_timing(dest,plan["frames"]),
             "dcp_candidate":True,"dcp_delivered":False,
             "creator_approved_theatrical_delivery":False}
        try:
            previous=self.capture.index.read_revision(
                plan["project_id"],plan["candidate_id"],1)
        except KeyError:
            self.capture.index.register_revision(
                plan["project_id"],plan["candidate_id"],"presentation",doc,
                expected_revision=0,dependencies=[
                    {"object_id":plan["distribution_id"],"revision":1,"role":"presentation"}])
            previous=self.capture.index.read_revision(
                plan["project_id"],plan["candidate_id"],1)
        if (previous["kind"]!="presentation" or previous["data"]!=doc):
            raise RuntimeError("Conflicting DCP candidate FilmIndex revision")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01k3_grants SET result_sha=? WHERE job_id=?",
                       (previous["document_sha256"],job))
            db.commit()
        task=self.ledger.get_task(job)
        if task["state"]=="ACTIVE":
            self.ledger.finish(job,"SUCCEEDED","Independent SMPTE candidate verified")
        elif task["state"]!="SUCCEEDED":
            raise RuntimeError("Cannot reconcile cinema worker in unknown state")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE native_audio01k3_events SET revision=1
                WHERE project_id=? AND candidate_id=? AND revision=-1""",
                (plan["project_id"],plan["candidate_id"]))
            db.commit()
        return previous

    def recover_completed(self,job):
        grant=self._grant(job)
        if grant["stopped"]!=1:
            raise PermissionError("Cannot recover un-reaped cinema worker")
        plan_file=self.root/job/"plan.json"
        if plan_file.is_symlink() or sha_file(plan_file)!=grant["plan_sha"]:
            raise RuntimeError("Original cinema plan was altered")
        plan=json.loads(plan_file.read_bytes())
        row=self._publish_candidate(job,plan)
        return {"job_id":job,"state":"SUCCEEDED",
                "document_sha256":row["document_sha256"],
                "rerendered":False,"dcp_delivered":False}

    def verify_candidate(self,project_id,candidate_id,job):
        grant=self._grant(job)
        task=self.ledger.get_task(job)
        if (grant["stopped"]!=1 or grant["revoked"] or
            not task or task["state"]!="SUCCEEDED" or task["reserved"]!=0):
            raise PermissionError("DCP has no completed native authoring custody")
        plan_file=self.root/job/"plan.json"
        if plan_file.is_symlink() or sha_file(plan_file)!=grant["plan_sha"]:
            raise RuntimeError("Native DCP plan digest changed")
        plan=json.loads(plan_file.read_bytes())
        if plan["project_id"]!=project_id or plan["candidate_id"]!=candidate_id:
            raise RuntimeError("Native DCP identity changed")
        row=self.capture.index.read_revision(project_id,candidate_id,1)
        if (grant["result_sha"]!=row["document_sha256"] or
            row["kind"]!="presentation" or
            row["data"].get("format")!=FORMAT or
            row["data"].get("dcp_delivered") is not False):
            raise RuntimeError("DCP candidate FilmIndex/native custody disagrees")
        source,proof,qc=self._verify_candidate(job,plan)
        if (source != Path(plan["destination"]) or
            row["data"]["asset_proof"] != proof or
            row["data"]["independent_qc"] != qc or
            row["data"]["cpl_timing"] != inspect_cpl_timing(source,plan["frames"]) or
            row["data"]["distribution_sha256"] != plan["distribution_sha"] or
            row["data"]["original_mov_sha256"] != plan["movie_sha256"] or
            row["data"]["creator_approved_theatrical_delivery"] is not False):
            raise RuntimeError("Published DCP candidate, QC or source custody changed")
        return {"status":"VERIFIED_SMPTE_DCP_CANDIDATE",
                "asset_count":proof["asset_count"],
                "independent_validator_passed":True,
                "dcp_delivered":False}
