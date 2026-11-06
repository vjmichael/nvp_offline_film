"""Trusted B14 native conform host: exact creator approval, durable admission,
OS-contained execution, live resource watchdog and independent source verification.

No browser or model call may supply an approval verifier; desktop host must
provide a real native creator-policy callback.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings,canonical_bytes
from backend.nvp_b14_picture_conform import verify_conformed_sdr16
from backend.nvp_b13_editorial_roundtrip import verify_imported_edit
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained

PLAN="conform_plan.json"
RECEIPT="conform_receipt.json"


def _sha_file(file):
    digest=hashlib.sha256()
    with Path(file).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(document):
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


class NativeB14ConformHost:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root:Path,*,
                 verify_creator_action):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(ledger,TaskLedger) or not callable(verify_creator_action)):
            raise TypeError("Native B14 requires a FilmIndex, TaskLedger and trusted creator verifier")
        self.capture,self.ledger=capture,ledger
        root=Path(root)
        if root.is_symlink():
            raise RuntimeError("Native B14 job root cannot be symlinked")
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=root.resolve()
        self.python=Path(sys.executable).resolve()
        self.script=Path(__file__).resolve().parents[1]/"tools"/"nvp_b14_conform_worker.py"
        self.owner_key="b14_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:24]
        self._creator=verify_creator_action
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_b14_conform_grants(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL, edit_id TEXT NOT NULL,
                edit_revision INTEGER NOT NULL, edit_sha TEXT NOT NULL,
                package_dir TEXT NOT NULL, destination_dir TEXT NOT NULL,
                presentation_id TEXT NOT NULL, ram_mb INTEGER NOT NULL,
                plan_sha TEXT NOT NULL, spec_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL, script_sha TEXT NOT NULL,
                expires_at REAL NOT NULL, revoked_at REAL,
                result_sha TEXT)""")
        self.binding=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _row(self,job):
        with self.ledger._db() as db:
            db.row_factory=__import__("sqlite3").Row
            row=db.execute("SELECT * FROM native_b14_conform_grants WHERE job_id=?",
                           (job,)).fetchone()
        if row is None:raise KeyError("Unknown B14 native conform job")
        return dict(row)

    def _check(self,approval,digest,doc):
        try:
            with self.ledger._db() as db:
                record=db.execute("SELECT job_id FROM native_b14_conform_grants WHERE approval_id=?",
                                  (approval,)).fetchone()
            if record is None:return False
            row=self._row(record[0])
            if (row["revoked_at"] is not None or time.time()>row["expires_at"] or
                digest!=row["spec_sha"] or _digest(doc)!=digest or
                doc.get("task_id")!=row["job_id"] or
                doc.get("kind")!="compositing" or
                doc.get("edit_sha")!=row["edit_sha"] or
                doc.get("edit_revision")!=row["edit_revision"] or
                doc.get("destination_dir")!=row["destination_dir"] or
                doc.get("ram_mb")!=row["ram_mb"] or
                _sha_file(self.python)!=row["python_sha"] or
                _sha_file(self.script)!=row["script_sha"]):
                return False
            folder=self.root/row["job_id"]
            if (_sha_file(folder/PLAN)!=row["plan_sha"] or
                (folder/RECEIPT).exists() or
                Path(row["destination_dir"]).exists() or
                Path(row["destination_dir"]).is_symlink()):
                return False
            plan=json.loads((folder/PLAN).read_text("ascii"))
            if (plan["edit_sha256"]!=row["edit_sha"] or
                plan["presentation_id"]!=row["presentation_id"] or
                plan["destination_dir"]!=row["destination_dir"] or
                plan["package_dir"]!=row["package_dir"]):
                return False
            edit=self.capture.index.read_revision(row["project_id"],row["edit_id"],
                                                  row["edit_revision"])
            return edit["kind"]=="edit" and edit["document_sha256"]==row["edit_sha"]
        except (OSError,KeyError,TypeError,ValueError,RuntimeError):
            return False

    def stage_and_approve(self,project_id,edit_id,edit_revision,package:Path,
                          destination:Path,creator_event,*,presentation_id=None,
                          ram_mb=1024,duration_s=1200):
        if (type(edit_revision) is not int or edit_revision<1 or
            type(ram_mb) is not int or not 1024<=ram_mb<=8192 or
            type(duration_s) is not int or not 60<=duration_s<=3600):
            raise ValueError("Invalid B14 native resource/time/revision request")
        edit=self.capture.index.read_revision(project_id,edit_id,edit_revision)
        if edit["kind"]!="edit":raise RuntimeError("B14 source is not a committed edit")
        proof=verify_imported_edit(self.capture,project_id,edit_id,
                                   Path(package),revision=edit_revision)
        if proof["status"]!="VERIFIED_EDITED_OTIO_REVISION":
            raise RuntimeError("B13 edit source failed independent verification")
        destination=Path(destination)
        if (destination.exists() or destination.is_symlink() or
            not destination.parent.is_dir() or destination.parent.is_symlink()):
            raise RuntimeError("B14 target must be a new directory under a safe parent")
        dest=str(destination.absolute())
        pack=str(Path(package).resolve())
        identity=presentation_id or "b14conform_"+secrets.token_hex(16)
        _id(identity,"B14 presentation")
        try:self.capture.index.read_revision(project_id,identity)
        except KeyError:pass
        else:raise RuntimeError("B14 presentation identity already committed")
        scope={"operation":"nvp.native.presentation.sdr16_picture_conform",
               "project_id":project_id,"edit_id":edit_id,"edit_revision":edit_revision,
               "edit_sha256":edit["document_sha256"],"destination_dir":dest,
               "presentation_id":identity,"ram_mb":ram_mb,
               "source_take_modified":False,"final_master":False}
        if self._creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Native NVP creator refused exact B14 picture conform")
        if (self.capture.index.read_revision(project_id,edit_id,edit_revision)["document_sha256"]!=
                edit["document_sha256"] or destination.exists()):
            raise RuntimeError("B14 source or destination changed during creator approval")
        job="conformjob_"+secrets.token_hex(16)
        folder=self.root/job
        folder.mkdir(exist_ok=False,mode=0o700)
        plan={"format":"nvp.b14.native_picture_conform_plan.v1",
              "studio_db_path":str(self.capture.studio.db_path),
              "project_id":project_id,"edit_id":edit_id,
              "edit_revision":edit_revision,"edit_sha256":edit["document_sha256"],
              "package_dir":pack,"destination_dir":dest,"presentation_id":identity}
        spec={"task_id":job,"kind":"compositing","project_id":project_id,
              "edit_sha":edit["document_sha256"],"edit_revision":edit_revision,
              "destination_dir":dest,"ram_mb":ram_mb,
              "python_sha":_sha_file(self.python),"script_sha":_sha_file(self.script)}
        with (folder/PLAN).open("xb") as stream:
            stream.write(canonical_bytes(plan))
            stream.flush()
            os.fsync(stream.fileno())
        approval="conformapproval_"+secrets.token_hex(16)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_b14_conform_grants(
                job_id,approval_id,project_id,edit_id,edit_revision,edit_sha,
                package_dir,destination_dir,presentation_id,ram_mb,plan_sha,spec_sha,
                python_sha,script_sha,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job,approval,project_id,edit_id,edit_revision,edit["document_sha256"],
                 pack,dest,identity,ram_mb,_sha_file(folder/PLAN),_digest(spec),
                 _sha_file(self.python),_sha_file(self.script),time.time()+duration_s))
            db.commit()
        self.binding.enqueue(AdmissionRequest(job,"compositing",
                             "Safely conform exact editor revision",ram_mb),
                             owner_key=self.owner_key,lane="standard",
                             approval_id=approval,document=spec)
        return {"job_id":job,"state":"QUEUED","presentation_id":identity,
                "edit_revision":edit_revision,"native_worker_started":False}

    def run_next(self,*,timeout_seconds=600):
        admission=self.binding.claim_next(owner_key=self.owner_key)
        if admission is None or not admission["admitted"]:return admission
        job=admission["task_id"];proc=None;cleanup=False;attempted=False
        try:
            self.binding.verified_spec(job,owner_key=self.owner_key)
            row=self._row(job)
            self.ledger.update(job,"saving_output","Conforming B13 edit inside native containment")
            folder=self.root/job
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                attempted=True
                proc=launch_contained([str(self.python),str(self.script),
                                      "--plan",str(folder/PLAN)],
                                      cwd=str(folder),stdout=out,stderr=err,
                                      memory_mb=row["ram_mb"])
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code!=0:raise RuntimeError("B14 native contained worker failed: "+str(code))
                proc.close()
                cleanup=True
            self.ledger.update(job,"verifying_output","Independently checking exact conformed film")
            receipt=json.loads((folder/RECEIPT).read_text("utf8"))
            result=verify_conformed_sdr16(self.capture,row["project_id"],
                row["presentation_id"],Path(row["package_dir"]),
                Path(row["destination_dir"]),edit_revision=row["edit_revision"])
            record=self.capture.index.read_revision(row["project_id"],row["presentation_id"],1)
            if (receipt.get("format")!="nvp.b14.native_picture_conform_completed.v1" or
                receipt.get("document_sha256")!=record["document_sha256"] or
                receipt.get("edit_sha256")!=row["edit_sha"] or
                receipt.get("frames")!=result["frames"] or
                receipt.get("picture_locked") is not False or
                receipt.get("final_master") is not False):
                raise RuntimeError("B14 native worker output receipt invalid")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_b14_conform_grants SET result_sha=? WHERE job_id=? AND result_sha IS NULL",
                           (record["document_sha256"],job))
                db.commit()
            self.ledger.finish(job,"SUCCEEDED","B14 original-source SDR16 picture conform verified")
            return {**result,"state":"SUCCEEDED","job_id":job}
        except BaseException as exc:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    proc.close()
                    cleanup=proc.poll() is not None
                except BaseException:cleanup=False
            if not attempted:cleanup=True
            if cleanup and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.finish(job,"FAILED",("B14 native conform failed: "+type(exc).__name__)[:240])
            raise

    def verify_completed(self,job):
        row=self._row(job)
        if self.ledger.get_task(job)["state"]!="SUCCEEDED" or not row["result_sha"]:
            raise RuntimeError("B14 has no committed native conform receipt")
        result=verify_conformed_sdr16(self.capture,row["project_id"],
            row["presentation_id"],Path(row["package_dir"]),
            Path(row["destination_dir"]),edit_revision=row["edit_revision"])
        record=self.capture.index.read_revision(row["project_id"],row["presentation_id"],1)
        if record["document_sha256"]!=row["result_sha"]:
            raise RuntimeError("B14 final FilmIndex receipt changed")
        return result
