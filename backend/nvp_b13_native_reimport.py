"""NVP B13 trusted native creator approval and contained OTIO picture reimport.

Queued metadata import is not a browser/model tool.  Untrusted OTIO bytes
are parsed only by an OS-contained Python worker, with exact source/bytes
bound to a durable creator event and physically measured RAM reservation.
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

from backend.nvp_approved_tasks import ApprovedTaskBindings,canonical_bytes
from backend.nvp_b12_editorial_delivery import verify_editorial_handoff
from backend.nvp_b13_editorial_roundtrip import (
    MAX_OTIO_BYTES,verify_imported_edit)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_worker_containment import launch_contained
from backend.nvp_resource_supervisor import wait_guarded

PLAN="native_edit_import_plan.json"
EDITED="incoming_edit.otio"
RECEIPT="verified_import_receipt.json"


def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def dig(doc):
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


class NativeB13ImportHost:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root:Path,*,
                 verify_creator_action):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(ledger,TaskLedger) or
            not callable(verify_creator_action)):
            raise TypeError("A trusted native NVP creator verifier and resource ledger are required")
        self.capture=capture
        self.ledger=ledger
        self.root=Path(root)
        if self.root.is_symlink():
            raise RuntimeError("Trusted native edit inbox cannot be symlinked")
        self.root=self.root.resolve()
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.python=Path(sys.executable).resolve()
        self.script=Path(__file__).resolve().parents[1]/"tools"/"nvp_b13_reimport_worker.py"
        self.owner_key="b13_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:24]
        self._creator=verify_creator_action
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_b13_import_grants(
                 job_id TEXT PRIMARY KEY,approval_id TEXT UNIQUE NOT NULL,
                 project_id TEXT NOT NULL,delivery_id TEXT NOT NULL,
                 delivery_sha256 TEXT NOT NULL,take_sha256 TEXT NOT NULL,
                 package_dir TEXT NOT NULL,edit_id TEXT NOT NULL,
                 expected_revision INTEGER NOT NULL,
                 edited_otio_sha256 TEXT NOT NULL,plan_sha256 TEXT NOT NULL,
                 spec_sha256 TEXT NOT NULL,python_sha256 TEXT NOT NULL,
                 script_sha256 TEXT NOT NULL,ram_mb INTEGER NOT NULL,
                 issued_at REAL NOT NULL,expires_at REAL NOT NULL,
                 revoked_at REAL,result_document_sha256 TEXT
            )""")
        self.binding=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _row(self,job_id):
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,approval_id,project_id,delivery_id,
                     delivery_sha256,take_sha256,package_dir,edit_id,
                     expected_revision,edited_otio_sha256,plan_sha256,
                     spec_sha256,python_sha256,script_sha256,ram_mb,
                     issued_at,expires_at,revoked_at,result_document_sha256
                     FROM native_b13_import_grants WHERE job_id=?""",
                     (job_id,)).fetchone()
        if not row:
            raise KeyError("Unknown original NVP creator-authorized OTIO import")
        names=("job_id","approval_id","project_id","delivery_id","delivery_sha256",
               "take_sha256","package_dir","edit_id","expected_revision",
               "edited_otio_sha256","plan_sha256","spec_sha256",
               "python_sha256","script_sha256","ram_mb","issued_at",
               "expires_at","revoked_at","result_document_sha256")
        return dict(zip(names,row))

    def _source(self,row):
        package=Path(row["package_dir"])
        verified=verify_editorial_handoff(
            self.capture,row["project_id"],row["delivery_id"],package,
            check_decode=False)
        if verified["status"]!="VERIFIED_PORTABLE_EDITORIAL_HANDOFF":
            raise RuntimeError("NVP edited OTIO media source isn't an accepted B12 package")
        source=self.capture.index.read_revision(row["project_id"],row["delivery_id"],1)
        if (source["document_sha256"]!=row["delivery_sha256"] or
            source["data"]["source_take_sha256"]!=row["take_sha256"]):
            raise RuntimeError("Frozen editorial source changed before edit import")
        if row["expected_revision"]:
            prior=self.capture.index.read_revision(row["project_id"],row["edit_id"])
            if (prior["revision"]!=row["expected_revision"] or
                prior["kind"]!="edit" or
                prior["data"].get("source_delivery_sha256")!=row["delivery_sha256"]):
                raise RuntimeError("Concurrent edited-film revision or source conflict")
        else:
            try:
                self.capture.index.read_revision(row["project_id"],row["edit_id"])
            except KeyError:
                pass
            else:
                raise RuntimeError("New film edit ID was already committed")
        return source

    def _check(self,approval,digest,document):
        try:
            if type(approval) is not str or type(digest) is not str:
                return False
            with self.ledger._db() as db:
                found=db.execute("""SELECT job_id FROM native_b13_import_grants
                            WHERE approval_id=?""",(approval,)).fetchone()
            if not found:return False
            row=self._row(found[0])
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=time.time()<=row["expires_at"] or
                row["spec_sha256"]!=digest or dig(document)!=digest or
                document.get("kind")!="compositing" or
                document.get("task_id")!=row["job_id"] or
                document.get("edited_otio_sha256")!=row["edited_otio_sha256"] or
                document.get("delivery_sha256")!=row["delivery_sha256"] or
                document.get("expected_revision")!=row["expected_revision"] or
                document.get("ram_mb")!=row["ram_mb"]):
                return False
            folder=self.root/row["job_id"]
            if (sha_file(folder/PLAN)!=row["plan_sha256"] or
                sha_file(folder/EDITED)!=row["edited_otio_sha256"] or
                sha_file(self.python)!=row["python_sha256"] or
                sha_file(self.script)!=row["script_sha256"] or
                (folder/RECEIPT).exists()):
                return False
            plan=json.loads((folder/PLAN).read_text("ascii"))
            if (plan.get("otio_sha256")!=row["edited_otio_sha256"] or
                plan.get("source_delivery_sha256")!=row["delivery_sha256"] or
                plan.get("edit_id")!=row["edit_id"] or
                plan.get("package_dir")!=row["package_dir"]):
                return False
            self._source(row)
            return True
        except (OSError,KeyError,TypeError,ValueError,RuntimeError):
            return False

    def stage_and_approve(self,project_id,delivery_id,package:Path,
                          incoming_otio:Path,creator_event,*,
                          edit_id=None,expected_revision=0,
                          ram_mb=1024,duration_s=1200):
        if (type(expected_revision) is not int or expected_revision<0 or
            type(ram_mb) is not int or not 1024<=ram_mb<=8192 or
            type(duration_s) is not int or not 60<=duration_s<=3600):
            raise ValueError("NVP B13 revision, RAM or native authorization duration invalid")
        source=verify_editorial_handoff(
            self.capture,project_id,delivery_id,Path(package),check_decode=False)
        if source["status"]!="VERIFIED_PORTABLE_EDITORIAL_HANDOFF":
            raise RuntimeError("B12 portable source media isn't verified")
        origin=self.capture.index.read_revision(project_id,delivery_id,1)
        inp=Path(incoming_otio)
        if inp.is_symlink() or not inp.is_file() or not 0<inp.stat().st_size<=MAX_OTIO_BYTES:
            raise RuntimeError("Edited OTIO input unavailable, symlinked or over size limit")
        raw=inp.read_bytes()
        if len(raw)>MAX_OTIO_BYTES:
            raise RuntimeError("NLE was editing OTIO while it was staged")
        edited_sha=hashlib.sha256(raw).hexdigest()
        target=edit_id if edit_id is not None else "edit_"+secrets.token_hex(16)
        _id(target,"FilmIndex edit identity")
        if expected_revision:
            current=self.capture.index.read_revision(project_id,target)
            if (current["revision"]!=expected_revision or
                current["kind"]!="edit" or
                current["data"]["source_delivery_sha256"]!=origin["document_sha256"]):
                raise RuntimeError("Expected edit revision/source conflict before creator approval")
        else:
            try:
                self.capture.index.read_revision(project_id,target)
            except KeyError:
                pass
            else:
                raise RuntimeError("Edited FilmIndex object already exists")
        scope={
            "operation":"nvp.native.editorial.otio_edited_picture_import",
            "project_id":project_id,"delivery_id":delivery_id,
            "source_delivery_sha256":origin["document_sha256"],
            "source_take_id":origin["data"]["source_take_id"],
            "source_take_sha256":origin["data"]["source_take_sha256"],
            "source_original_float32_sha256":origin["data"]["source_float32_presentation_sha256"],
            "edited_otio_sha256":edited_sha,
            "new_edit_id":target,"expected_revision":expected_revision,
            "source_fps":24,"maximum_output_frames":480,
            "editing_ops":"reorder_trim_split_repeat_from_original_shots_only",
            "audio_import_allowed":False,"effects_import_allowed":False,
            "original_frozen_take_modified":False,
            "ram_mb":ram_mb,
        }
        if self._creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Native NVP director did not approve exact edited OTIO input")
        # Confirm inputs are unchanged across the human authorization window.
        if (sha_file(inp)!=edited_sha or
            self.capture.index.read_revision(project_id,delivery_id,1)["document_sha256"]!=
                origin["document_sha256"]):
            raise RuntimeError("Edited OTIO bytes or NVP source changed during native creator approval")
        job="editjob_"+secrets.token_hex(16)
        folder=self.root/job
        folder.mkdir(mode=0o700,exist_ok=False)
        grant="editapproval_"+secrets.token_hex(16)
        info={
            "format":"nvp.b13.native_edit_reimport_plan.v1",
            "project_id":project_id,"delivery_id":delivery_id,
            "package_dir":str(Path(package).resolve()),
            "edit_id":target,"expected_revision":expected_revision,
            "studio_db_path":str(self.capture.studio.db_path),
            "otio_sha256":edited_sha,
            "source_delivery_sha256":origin["document_sha256"],
            "source_take_sha256":origin["data"]["source_take_sha256"],
        }
        spec={
            "task_id":job,"kind":"compositing","project_id":project_id,
            "delivery_sha256":origin["document_sha256"],
            "edited_otio_sha256":edited_sha,"edit_id":target,
            "expected_revision":expected_revision,"ram_mb":ram_mb,
            "python_sha256":sha_file(self.python),
            "script_sha256":sha_file(self.script),
        }
        try:
            for name,blob in ((EDITED,raw),(PLAN,canonical_bytes(info))):
                with (folder/name).open("xb") as output:
                    output.write(blob)
                    output.flush()
                    os.fsync(output.fileno())
            if sha_file(folder/EDITED)!=edited_sha:
                raise RuntimeError("Staged edited OTIO bytes changed")
            now=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO native_b13_import_grants(
                    job_id,approval_id,project_id,delivery_id,delivery_sha256,
                    take_sha256,package_dir,edit_id,expected_revision,
                    edited_otio_sha256,plan_sha256,spec_sha256,python_sha256,
                    script_sha256,ram_mb,issued_at,expires_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (job,grant,project_id,delivery_id,origin["document_sha256"],
                     origin["data"]["source_take_sha256"],info["package_dir"],
                     target,expected_revision,edited_sha,sha_file(folder/PLAN),
                     dig(spec),sha_file(self.python),sha_file(self.script),
                     ram_mb,now,now+duration_s))
                db.commit()
            self.binding.enqueue(
                AdmissionRequest(job,"compositing","Validate edited OTIO and record original-film revision",ram_mb),
                owner_key=self.owner_key,lane="standard",approval_id=grant,document=spec)
            return {"state":"QUEUED","job_id":job,"edit_id":target,
                    "expected_revision":expected_revision,
                    "source_sha256":origin["document_sha256"],
                    "otio_sha256":edited_sha,"native_worker_started":False}
        except BaseException:
            task=self.ledger.get_task(job)
            if task is None:
                with self.ledger._db() as db:
                    present=db.execute("""SELECT 1 FROM native_b13_import_grants
                             WHERE job_id=?""",(job,)).fetchone()
                if not present:shutil.rmtree(folder)
            raise

    def run_next(self,*,timeout_seconds=240):
        if type(timeout_seconds) is not int or not 30<=timeout_seconds<=600:
            raise ValueError("NVP native edit import timeout invalid")
        admission=self.binding.claim_next(owner_key=self.owner_key)
        if admission is None or not admission["admitted"]:
            return admission
        job=admission["task_id"]
        proc=None
        launch_attempted=False
        cleanup=False
        try:
            spec=self.binding.verified_spec(job,owner_key=self.owner_key)
            row=self._row(job)
            if not self._check(row["approval_id"],dig(spec),spec):
                raise PermissionError("Native edit source or creator authority changed before spawn")
            folder=self.root/job
            self.ledger.update(job,"processing_prompt","Parsing genuine OpenTimelineIO edit inside OS containment")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                launch_attempted=True
                proc=launch_contained(
                    [str(self.python),str(self.script),"--plan",str(folder/PLAN)],
                    cwd=str(folder),stdout=out,stderr=err,memory_mb=row["ram_mb"])
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code!=0:
                    raise RuntimeError("Contained edited OTIO import failed: "+str(code))
                proc.close()
                cleanup=True
            self.ledger.update(job,"verifying_output","Independently reopening imported cut decisions and original take")
            report=json.loads((folder/RECEIPT).read_text("utf8"))
            audited=verify_imported_edit(
                self.capture,row["project_id"],row["edit_id"],
                Path(row["package_dir"]),
                revision=row["expected_revision"]+1)
            rev=self.capture.index.read_revision(
                row["project_id"],row["edit_id"],row["expected_revision"]+1)
            if (report.get("format")!="nvp.b13.native_edited_otio_completed.v1" or
                report.get("edited_otio_sha256")!=row["edited_otio_sha256"] or
                report.get("edit_id")!=row["edit_id"] or
                report.get("revision")!=audited["revision"] or
                report.get("frames")!=audited["frames"] or
                report.get("document_sha256")!=rev["document_sha256"] or
                report.get("original_take_modified") is not False or
                report.get("rendered_movie_claimed") is not False):
                raise RuntimeError("Native import receipt differs from original FilmIndex edits")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE native_b13_import_grants
                    SET result_document_sha256=? WHERE job_id=?
                    AND result_document_sha256 IS NULL""",
                    (rev["document_sha256"],job))
                db.commit()
            self.ledger.finish(job,"SUCCEEDED","Edited OpenTimelineIO revision safely indexed and verified")
            return {**audited,"state":"SUCCEEDED","job_id":job,
                    "original_master_preserved":True}
        except BaseException as exc:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    proc.close()
                    cleanup=proc.poll() is not None
                except BaseException:
                    cleanup=False
            if not launch_attempted:
                cleanup=True
            if cleanup and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.finish(job,"FAILED",
                                   ("Native OTIO reimport refused: "+type(exc).__name__)[:240])
            # Unknown process cleanup retains ACTIVE RAM reservation.
            raise

    def verify_completed(self,job):
        row=self._row(job)
        task=self.ledger.get_task(job)
        if not task or task["state"]!="SUCCEEDED":
            raise RuntimeError("Native original-film edit import not completed")
        rec=self.capture.index.read_revision(
            row["project_id"],row["edit_id"],row["expected_revision"]+1)
        if rec["document_sha256"]!=row["result_document_sha256"]:
            raise RuntimeError("Durable edited import receipt lost exact revision identity")
        if sha_file(self.root/job/EDITED)!=row["edited_otio_sha256"]:
            raise RuntimeError("Original edited OTIO inbox changed after job completion")
        return verify_imported_edit(
            self.capture,row["project_id"],row["edit_id"],Path(row["package_dir"]),
            revision=row["expected_revision"]+1)

    def revoke_from_trusted_native_action(self,job,signal):
        row=self._row(job)
        scope={
            "operation":"nvp.native.editorial.otio_import.revoke",
            "project_id":row["project_id"],"source_delivery_id":row["delivery_id"],
            "edit_id":row["edit_id"],"expected_revision":row["expected_revision"],
            "edited_otio_sha256":row["edited_otio_sha256"],
        }
        if self._creator(signal,scope) is not True:
            raise PermissionError("Native NVP director did not authorize edit import cancellation")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE native_b13_import_grants SET revoked_at=?
                     WHERE job_id=? AND revoked_at IS NULL""",(time.time(),job))
            if changed.rowcount!=1:
                db.rollback()
                raise RuntimeError("Edited OTIO grant already cancelled")
            db.commit()
        task=self.ledger.get_task(job)
        cancelled=False
        if task is not None and task["state"]=="QUEUED":
            try:
                self.ledger.cancel_queued(job,owner_key=self.owner_key)
                cancelled=True
            except (RuntimeError,PermissionError):
                pass
        return {"revoked":True,"queued_cancelled":cancelled,
                "live_worker_terminated_claimed":False}
