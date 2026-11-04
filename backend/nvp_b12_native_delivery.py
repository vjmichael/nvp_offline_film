"""Native OS-contained B12 editorial interchange/delivery worker.

Only a trusted NVP desktop host may stage a creator-approved, immutable
source-bound task through ApprovedTaskBindings and measured TaskLedger.
A model or HTTP route cannot authorize native package/encoder execution.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings,canonical_bytes
from backend.nvp_b12_editorial_delivery import (
    _review,_sha_file,verify_editorial_handoff,PROFILES,OTIO_VERSION,FORMAT)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_worker_containment import launch_contained

PLAN_FILE="b12_delivery_plan.json"
COMPLETE="b12_delivery_completed.json"


def _digest(x):
    return hashlib.sha256(canonical_bytes(x)).hexdigest()


class NativeB12DeliveryHost:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root:Path,*,
                 verify_creator_action):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(ledger,TaskLedger) or
            not callable(verify_creator_action)):
            raise TypeError("Trusted native creator action and FilmIndex resource ledger required")
        self.capture=capture
        self.ledger=ledger
        self.root=Path(root)
        if self.root.is_symlink():
            raise RuntimeError("Native B12 workspace cannot be symlinked")
        self.root=self.root.resolve()
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.python=Path(sys.executable).resolve()
        self.script=Path(__file__).resolve().parents[1]/"tools"/"nvp_b12_delivery_worker.py"
        self._creator=verify_creator_action
        self.owner_key="b12_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:24]
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_b12_deliveries(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL,review_id TEXT NOT NULL,
                review_sha256 TEXT NOT NULL,source_take_id TEXT NOT NULL,
                source_take_sha256 TEXT NOT NULL,delivery_id TEXT NOT NULL UNIQUE,
                frames INTEGER NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,
                profiles_json TEXT NOT NULL,plan_sha256 TEXT NOT NULL,
                spec_sha256 TEXT NOT NULL,python_sha256 TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,ram_mb INTEGER NOT NULL,
                issued_at REAL NOT NULL,expires_at REAL NOT NULL,
                revoked_at REAL,delivery_document_sha256 TEXT
            )""")
        self.binding=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _row(self,job_id):
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,approval_id,project_id,review_id,
               review_sha256,source_take_id,source_take_sha256,delivery_id,
               frames,width,height,profiles_json,plan_sha256,spec_sha256,
               python_sha256,script_sha256,ram_mb,issued_at,expires_at,
               revoked_at,delivery_document_sha256 FROM native_b12_deliveries
               WHERE job_id=?""",(job_id,)).fetchone()
        if row is None:raise KeyError("Unknown native B12 delivery job")
        names=("job_id","approval_id","project_id","review_id",
               "review_sha256","source_take_id","source_take_sha256",
               "delivery_id","frames","width","height","profiles_json",
               "plan_sha256","spec_sha256","python_sha256",
               "script_sha256","ram_mb","issued_at","expires_at",
               "revoked_at","delivery_document_sha256")
        return dict(zip(names,row))

    def _check(self,approval,digest,document):
        try:
            if type(approval) is not str or type(digest) is not str:
                return False
            with self.ledger._db() as db:
                entry=db.execute("""SELECT job_id FROM native_b12_deliveries
                           WHERE approval_id=?""",(approval,)).fetchone()
            if not entry:return False
            row=self._row(entry[0])
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=time.time()<=row["expires_at"] or
                row["spec_sha256"]!=digest or _digest(document)!=digest or
                document.get("task_id")!=row["job_id"] or
                document.get("kind")!="compositing" or
                document.get("source_review_sha256")!=row["review_sha256"] or
                document.get("delivery_id")!=row["delivery_id"] or
                document.get("ram_mb")!=row["ram_mb"]):
                return False
            folder=self.root/row["job_id"]
            if (_sha_file(folder/PLAN_FILE)!=row["plan_sha256"] or
                _sha_file(self.python)!=row["python_sha256"] or
                _sha_file(self.script)!=row["script_sha256"] or
                (folder/COMPLETE).exists()):
                return False
            plan=json.loads((folder/PLAN_FILE).read_text("ascii"))
            if (plan.get("review_sha256")!=row["review_sha256"] or
                plan.get("source_take_sha256")!=row["source_take_sha256"] or
                plan.get("delivery_id")!=row["delivery_id"] or
                plan.get("profiles")!=json.loads(row["profiles_json"])):
                return False
            review,d,proof=_review(self.capture,row["project_id"],row["review_id"])
            return (review["document_sha256"]==row["review_sha256"] and
                    d["source_take_sha256"]==row["source_take_sha256"] and
                    d["frame_count"]==row["frames"] and
                    d["width"]==row["width"] and d["height"]==row["height"])
        except (KeyError,ValueError,TypeError,RuntimeError,OSError):
            return False

    def stage_and_approve(self,project_id,review_id,creator_event,*,
                          profiles=("prores_422_hq_mov",),ram_mb=2048,
                          duration_s=3600):
        if (type(profiles) not in (tuple,list) or len(profiles)>2 or
            len(set(profiles))!=len(profiles) or
            any(p not in PROFILES for p in profiles)):
            raise ValueError("Only established bounded ProRes/DNxHR profiles allowed")
        if (type(ram_mb) is not int or not 2048<=ram_mb<=65536 or
            type(duration_s) is not int or not 60<=duration_s<=7200):
            raise ValueError("B12 creator approval needs bounded RAM/lifetime")
        doc,data,proof=_review(self.capture,project_id,review_id)
        count,width,height=data["frame_count"],data["width"],data["height"]
        if width*height*16*10>ram_mb*1024*1024//2:
            raise ValueError("B12 real frame buffers exceed native RAM grant")
        if profiles and width*height>1024*576:
            raise RuntimeError("Technical MOV codec only supported at previously validated raster")
        worst=2*count*width*height*6+2*1024**3
        if min(shutil.disk_usage(self.root).free,
               shutil.disk_usage(self.capture.index.blob_root).free)<worst:
            raise RuntimeError("Insufficient disk for non-destructive editorial interchange")
        policy=data["color_policy"]
        scope={
            "operation":"nvp.native.frozen_editorial.otio_prores_dnxhr",
            "project_id":project_id,"source_review_id":review_id,
            "source_review_sha256":doc["document_sha256"],
            "source_take_id":data["source_take_id"],
            "source_take_sha256":data["source_take_sha256"],
            "source_exr_sha256":data["source_presentation_sha256"],
            "frame_count":count,"fps":24,"resolution":[width,height],
            "camera_cutlist":data["cutlist"],
            "ocio_config_sha256":policy["config_sha256"],
            "source_precision":"RGBA_FLOAT32",
            "portable_editorial_precision":"SDR_RGB_PNG16",
            "otio_version":OTIO_VERSION,
            "professional_video_profiles":list(profiles),
            "audio_present":False,"final_master_approved":False,
            "disk_reserve_bytes":worst,"ram_mb":ram_mb,
        }
        if self._creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Native creator did not authorize exact full editorial delivery")
        if _review(self.capture,project_id,review_id)[0]["document_sha256"]!=doc["document_sha256"]:
            raise RuntimeError("Original NVP scene review changed during native approval")
        job="deliveryjob_"+secrets.token_hex(16)
        delivery="editorial_"+secrets.token_hex(16)
        folder=self.root/job
        folder.mkdir(mode=0o700,exist_ok=False)
        grant="b12approval_"+secrets.token_hex(16)
        spec={"task_id":job,"kind":"compositing",
              "project_id":project_id,"source_review_sha256":doc["document_sha256"],
              "source_take_sha256":data["source_take_sha256"],
              "delivery_id":delivery,"ram_mb":ram_mb,
              "profiles":list(profiles),"otio_version":OTIO_VERSION,
              "python_sha256":_sha_file(self.python),
              "script_sha256":_sha_file(self.script)}
        plan={"format":"nvp.b12.native_delivery_plan.v1",
              "project_id":project_id,"review_id":review_id,
              "review_sha256":doc["document_sha256"],
              "source_take_id":data["source_take_id"],
              "source_take_sha256":data["source_take_sha256"],
              "delivery_id":delivery,"frames":count,
              "resolution":[width,height],"studio_db_path":str(self.capture.studio.db_path),
              "output_root":str(folder/"handoff"),
              "profiles":list(profiles)}
        try:
            path=folder/PLAN_FILE
            with path.open("xb") as out:
                out.write(canonical_bytes(plan))
                out.flush()
                import os
                os.fsync(out.fileno())
            now=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO native_b12_deliveries(
                    job_id,approval_id,project_id,review_id,review_sha256,
                    source_take_id,source_take_sha256,delivery_id,frames,width,height,
                    profiles_json,plan_sha256,spec_sha256,python_sha256,script_sha256,
                    ram_mb,issued_at,expires_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (job,grant,project_id,review_id,doc["document_sha256"],
                     data["source_take_id"],data["source_take_sha256"],delivery,
                     count,width,height,json.dumps(list(profiles)),_sha_file(path),
                     _digest(spec),_sha_file(self.python),_sha_file(self.script),
                     ram_mb,now,now+duration_s))
                db.commit()
            self.binding.enqueue(
                AdmissionRequest(job,"compositing","OTIO and technical editorial delivery",ram_mb),
                owner_key=self.owner_key,lane="standard",approval_id=grant,document=spec)
            return {"format":"nvp.b12.native_delivery_queue.v1",
                    "job_id":job,"delivery_id":delivery,"state":"QUEUED",
                    "native_worker_started":False,"frames":count,
                    "source_review_sha256":doc["document_sha256"],
                    "professional_profiles":list(profiles)}
        except BaseException:
            task=self.ledger.get_task(job)
            if task is None:
                with self.ledger._db() as db:
                    exists=db.execute("SELECT 1 FROM native_b12_deliveries WHERE job_id=?",
                                      (job,)).fetchone()
                if not exists:shutil.rmtree(folder)
            raise

    def _package(self,row):
        root=self.root/row["job_id"]/"handoff"
        name="handoff_"+hashlib.sha256(
            (row["project_id"]+"|"+row["delivery_id"]).encode()).hexdigest()[:24]
        return root/name

    def run_next(self,*,timeout_seconds=3600):
        if type(timeout_seconds) is not int or not 60<=timeout_seconds<=7200:
            raise ValueError("Invalid native editorial worker timeout")
        admission=self.binding.claim_next(owner_key=self.owner_key)
        if admission is None or not admission["admitted"]:
            return admission
        job=admission["task_id"]
        proc=None
        launch_attempted=False
        os_cleanup_proven=False
        try:
            spec=self.binding.verified_spec(job,owner_key=self.owner_key)
            row=self._row(job)
            if not self._check(row["approval_id"],_digest(spec),spec):
                raise PermissionError("NVP source, native consent, or image delivery plan revoked")
            folder=self.root/job
            launch_attempted=True
            self.ledger.update(job,"rendering","Building exact media/OTIO and audited ProRes/DNxHR")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                proc=launch_contained(
                    [str(self.python),str(self.script),"--plan",str(folder/PLAN_FILE)],
                    cwd=str(folder),stdout=out,stderr=err,memory_mb=row["ram_mb"])
                rc=proc.wait(timeout=timeout_seconds)
                if rc!=0:
                    raise RuntimeError("Contained NVP OTIO/media encoder rejected handoff: "+str(rc))
                proc.close()
                os_cleanup_proven=True
            self.ledger.update(job,"verifying_output","Independent OTIO/media/video source readback after worker shutdown")
            receipt=json.loads((folder/COMPLETE).read_text("utf8"))
            proof=verify_editorial_handoff(
                self.capture,row["project_id"],row["delivery_id"],self._package(row),
                check_decode=True)
            indexed=self.capture.index.read_revision(row["project_id"],row["delivery_id"])
            if (receipt.get("format")!="nvp.b12.native_delivery_completed.v1" or
                receipt.get("delivery_id")!=row["delivery_id"] or
                receipt.get("presentation_sha256")!=indexed["document_sha256"] or
                receipt.get("frames")!=row["frames"] or
                receipt.get("source_review_sha256")!=row["review_sha256"] or
                receipt.get("native_OS_containment_claimed") is not False):
                raise RuntimeError("NVP editorial handoff completion evidence forged")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE native_b12_deliveries SET delivery_document_sha256=?
                      WHERE job_id=? AND delivery_document_sha256 IS NULL""",
                      (indexed["document_sha256"],job))
                db.commit()
            self.ledger.finish(job,"SUCCEEDED","Portable OTIO/PNG/video handoff fully verified")
            return {**proof,"state":"SUCCEEDED","job_id":job,
                    "package_directory":str(self._package(row))}
        except BaseException as exc:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    proc.close()
                    os_cleanup_proven=proc.poll() is not None
                except BaseException:
                    os_cleanup_proven=False
            if not launch_attempted:
                os_cleanup_proven=True
            if os_cleanup_proven and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.finish(job,"FAILED",
                                   ("Native OTIO delivery refused: "+type(exc).__name__)[:240])
            # Ambiguous process existence holds the resource reservation.
            raise

    def verify_completed(self,job):
        row=self._row(job)
        task=self.ledger.get_task(job)
        if not task or task["state"]!="SUCCEEDED":
            raise RuntimeError("NVP editorial delivery not independently completed")
        if _sha_file(self.root/job/PLAN_FILE)!=row["plan_sha256"]:
            raise RuntimeError("Native delivery plan altered since process completion")
        film=self.capture.index.read_revision(row["project_id"],row["delivery_id"])
        if film["document_sha256"]!=row["delivery_document_sha256"]:
            raise RuntimeError("Indexed editorial delivery changed after successful worker")
        return verify_editorial_handoff(self.capture,row["project_id"],
              row["delivery_id"],self._package(row),check_decode=True)

    def revoke_from_trusted_native_action(self,job,signal):
        row=self._row(job)
        scope={"operation":"nvp.native.editorial_delivery.revoke",
               "project_id":row["project_id"],"source_take_id":row["source_take_id"],
               "review_id":row["review_id"],"delivery_id":row["delivery_id"]}
        if self._creator(signal,scope) is not True:
            raise PermissionError("Native creator did not authenticate editorial cancellation")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE native_b12_deliveries SET revoked_at=?
                    WHERE job_id=? AND revoked_at IS NULL""",(time.time(),job))
            if changed.rowcount!=1:
                db.rollback()
                raise RuntimeError("Native B12 grant already revoked")
            db.commit()
        cancelled=False
        task=self.ledger.get_task(job)
        if task and task["state"]=="QUEUED":
            try:
                self.ledger.cancel_queued(job,owner_key=self.owner_key)
                cancelled=True
            except (PermissionError,RuntimeError):
                pass
        return {"revoked":True,"queued_cancelled":cancelled,
                "active_OS_process_terminated_claimed":False}
