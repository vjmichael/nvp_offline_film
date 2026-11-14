"""NVP B10 native-only approved ACES2/OCIO EXR color worker.

The bounded CPU transform runs as a separate OS-contained Python process,
NOT inside the NVP GUI or on a direct FastAPI/model request. The exact
source EXR, OCIO binary/config identity, output contract, verified Python
interpreter/script, project, take and RAM budget are bound to a short-lived
trusted native creator action in the same durable TaskLedger used by Blender.
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
from backend.nvp_b10_ocio import CONFIG_URI,_sha,load_verified_config
from backend.nvp_b10_color_verify import verify_acescg_frame
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_exr_fidelity import inspect_exr_header
from backend.nvp_exr_publish import verify_indexed_exr_sequence
from backend.nvp_native_proxy_audit import _copy_exclusive_verified
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_worker_containment import launch_contained

OUTPUT="acescg_frame.exr"
SOURCE="linear_rec709_frame.exr"
REPORT="color_transform_receipt.json"


class NativeOCIOColorWorker:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root:Path,
                 *,verify_creator_action):
        if not isinstance(capture,DigitalCapture) or not isinstance(ledger,TaskLedger):
            raise TypeError("NVP indexed film and shared resource ledger required")
        if not callable(verify_creator_action):
            raise TypeError("Native creator-presence verifier required")
        self.capture=capture
        self.ledger=ledger
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink():
            raise RuntimeError("Native color workspace may not be a symlink")
        self._creator=verify_creator_action
        self.python=Path(sys.executable).resolve()
        self.python_sha=_sha(self.python)
        self.script=Path(__file__).with_name("nvp_b10_ocio.py").resolve()
        self.script_sha=_sha(self.script)
        self.owner_key="ocio_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:24]
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_b10_color_jobs(
                job_id TEXT PRIMARY KEY,
                approval_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                source_presentation_id TEXT NOT NULL,
                source_presentation_sha256 TEXT NOT NULL,
                source_take_id TEXT NOT NULL,
                source_take_sha256 TEXT NOT NULL,
                frame INTEGER NOT NULL,
                source_sha256 TEXT NOT NULL,
                expected_config_sha256 TEXT NOT NULL,
                document_sha256 TEXT NOT NULL,
                python_sha256 TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,
                width INTEGER NOT NULL,height INTEGER NOT NULL,
                ram_mb INTEGER NOT NULL,
                issued_at REAL NOT NULL,expires_at REAL NOT NULL,
                revoked_at REAL, output_sha256 TEXT, report_sha256 TEXT
            )""")
        self.bindings=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _read(self,job_id):
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,approval_id,project_id,
               source_presentation_id,source_presentation_sha256,
               source_take_id,source_take_sha256,frame,source_sha256,
               expected_config_sha256,document_sha256,
               python_sha256,script_sha256,width,height,ram_mb,
               issued_at,expires_at,revoked_at,output_sha256,report_sha256
               FROM native_b10_color_jobs WHERE job_id=?""",(job_id,)).fetchone()
        if row is None:raise KeyError("Unknown NVP native color conversion job")
        names=("job_id","approval_id","project_id","source_presentation_id",
               "source_presentation_sha256","source_take_id",
               "source_take_sha256","frame","source_sha256",
               "expected_config_sha256","document_sha256",
               "python_sha256","script_sha256","width","height","ram_mb",
               "issued_at","expires_at","revoked_at","output_sha256","report_sha256")
        return dict(zip(names,row))

    def _source(self,row):
        record=self.capture.index.read_revision(row["project_id"],
                                                 row["source_presentation_id"])
        if record["document_sha256"]!=row["source_presentation_sha256"]:
            raise RuntimeError("Indexed source presentation revision changed")
        data=record["data"]
        if (data.get("format")!="nvp.presentation.scene_linear_float32_exr_sequence.v1" or
            data.get("source_take_id")!=row["source_take_id"] or
            data.get("source_take_sha256")!=row["source_take_sha256"] or
            data.get("view_transform")!="Raw" or
            data.get("render_engine")!="BLENDER_WORKBENCH"):
            raise RuntimeError("Original source primaries/presentation were not verified")
        frame=data["frames"][row["frame"]-1]
        if frame["frame"]!=row["frame"] or frame["sha256"]!=row["source_sha256"]:
            raise RuntimeError("NVP original exact source frame changed")
        stored=self.capture.index.verify_media_file(
            row["project_id"],frame["sha256"],"image/x-exr")
        return Path(stored["path"])

    def _check(self,approval,digest,document):
        try:
            if type(approval) is not str or type(digest) is not str:
                return False
            with self.ledger._db() as db:
                result=db.execute("""SELECT job_id FROM native_b10_color_jobs
                       WHERE approval_id=?""",(approval,)).fetchone()
            if not result:return False
            row=self._read(result[0])
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=time.time()<=row["expires_at"] or
                row["document_sha256"]!=digest or
                hashlib.sha256(canonical_bytes(document)).hexdigest()!=digest or
                document.get("task_id")!=row["job_id"] or
                document.get("kind")!="compositing"):
                return False
            source=self._source(row)
            if (_sha(source)!=row["source_sha256"] or
                _sha(self.python)!=row["python_sha256"] or
                _sha(self.script)!=row["script_sha256"] or
                _sha(self.root/row["job_id"]/SOURCE)!=row["source_sha256"] or
                (self.root/row["job_id"]/OUTPUT).exists()):
                return False
            _,_,identity=load_verified_config()
            return identity["config_serialized_sha256"]==row["expected_config_sha256"]
        except (KeyError,ValueError,TypeError,RuntimeError,OSError):
            return False

    def stage_and_approve(self,project_id,presentation_id,frame,creator_event,
                          *,ram_mb=4096,duration_s=1800):
        if type(frame) is not int or frame<1:
            raise ValueError("Positive integer original frame required")
        if (type(ram_mb) is not int or not 1024<=ram_mb<=65536 or
            type(duration_s) is not int or not 30<=duration_s<=7200):
            raise ValueError("Invalid color processing RAM or consent lifetime")
        # Verifies all source frame blobs and original frozen DTP ancestry.
        verified=verify_indexed_exr_sequence(self.capture,project_id,presentation_id)
        presentation=self.capture.index.read_revision(project_id,presentation_id)
        data=presentation["data"]
        if frame>verified["frames"]:
            raise ValueError("Selected frame is outside immutable Digital Take")
        width,height=verified["width"],verified["height"]
        color_peak=width*height*4*4*12
        if color_peak>ram_mb*1024*1024//2:
            raise ValueError("Approved color RAM budget cannot safely load Float32 image")
        _,_,identity=load_verified_config()
        selected=data["frames"][frame-1]
        expected_sha=selected["sha256"]
        scope={
            "operation":"nvp.native.aces2.ocio.float32_color_convert",
            "project_id":project_id,"source_presentation_id":presentation_id,
            "source_take_id":data["source_take_id"],
            "source_take_sha256":data["source_take_sha256"],
            "frame":frame,"input_exr_sha256":expected_sha,
            "resolution":[width,height],"source_color_space":identity["source_space"],
            "target_color_space":"ACEScg",
            "config_uri":CONFIG_URI,
            "config_serialized_sha256":identity["config_serialized_sha256"],
            "ram_mb":ram_mb,"output_format":"OPEN_EXR_RGBA_FLOAT32",
            "original_frozen_take_preserved":True,
        }
        if self._creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Trusted native creator has not approved exact ACES transform")
        job_id="ociojob_"+secrets.token_hex(16)
        jobdir=self.root/job_id
        jobdir.mkdir(mode=0o700,exist_ok=False)
        try:
            media=self.capture.index.verify_media_file(project_id,expected_sha,"image/x-exr")
            _copy_exclusive_verified(Path(media["path"]),jobdir/SOURCE,expected_sha)
            inspect_exr_header(jobdir/SOURCE,width=width,height=height)
            document={
                "task_id":job_id,"kind":"compositing",
                "project_id":project_id,"source_presentation_id":presentation_id,
                "source_take_id":data["source_take_id"],
                "source_take_sha256":data["source_take_sha256"],
                "frame":frame,"source_sha256":expected_sha,
                "config_serialized_sha256":identity["config_serialized_sha256"],
                "python_sha256":self.python_sha,"script_sha256":self.script_sha,
                "width":width,"height":height,"ram_mb":ram_mb,
                "target_space":"ACEScg","output":OUTPUT,
            }
            digest=hashlib.sha256(canonical_bytes(document)).hexdigest()
            approval="ocio_approval_"+secrets.token_hex(16)
            now=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO native_b10_color_jobs VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)""",
                    (job_id,approval,project_id,presentation_id,
                     presentation["document_sha256"],data["source_take_id"],
                     data["source_take_sha256"],frame,expected_sha,
                     identity["config_serialized_sha256"],digest,
                     self.python_sha,self.script_sha,width,height,ram_mb,
                     now,now+duration_s))
                db.commit()
            self.bindings.enqueue(
                AdmissionRequest(job_id,"compositing","ACES 2.0 "+str(frame),ram_mb),
                owner_key=self.owner_key,lane="standard",approval_id=approval,
                document=document)
            return {"job_id":job_id,"approval_id":approval,
                    "state":"QUEUED","source_sha256":expected_sha,
                    "config_sha256":identity["config_serialized_sha256"],
                    "native_worker_started":False}
        except BaseException:
            # If scheduler registration succeeded, retain staged source and
            # durable grant; it requires NVP recovery rather than unsafe deletion.
            task=self.ledger.get_task(job_id)
            if task is None:
                shutil.rmtree(jobdir)
            raise

    def _verify_finished(self,row):
        jobdir=self.root/row["job_id"]
        receipt=json.loads((jobdir/REPORT).read_text("utf8"))
        result=verify_acescg_frame(
            jobdir/SOURCE,jobdir/OUTPUT,receipt,
            width=row["width"],height=row["height"])
        if (receipt["source_exr_sha256"]!=row["source_sha256"] or
            receipt["config"]["config_serialized_sha256"]!=row["expected_config_sha256"]):
            raise RuntimeError("Color job output violates source/config identity")
        return receipt,result

    def run_next(self,*,timeout_seconds=240):
        if type(timeout_seconds) is not int or not 1<=timeout_seconds<=600:
            raise ValueError("Invalid supervised color processing timeout")
        ticket=self.bindings.claim_next(owner_key=self.owner_key)
        if ticket is None or not ticket["admitted"]:
            return ticket
        job_id=ticket["task_id"]
        proc=None
        launch_attempted=False
        closed=False
        try:
            doc=self.bindings.verified_spec(job_id,owner_key=self.owner_key)
            row=self._read(job_id)
            if (doc["source_sha256"]!=row["source_sha256"] or
                doc["config_serialized_sha256"]!=row["expected_config_sha256"] or
                doc["python_sha256"]!=row["python_sha256"] or
                doc["script_sha256"]!=row["script_sha256"] or
                doc["ram_mb"]!=row["ram_mb"] or
                self.ledger.get_task(job_id)["ram_mb"]!=row["ram_mb"]):
                raise PermissionError("Approved native color worker source or memory changed")
            # Recheck source/consent after admission, as close to execution
            # as possible. Approval is host-owned; no model/web route exists.
            with self.ledger._db() as db:
                approval=db.execute("""SELECT approval_id FROM native_b10_color_jobs
                    WHERE job_id=?""",(job_id,)).fetchone()[0]
            if not self._check(approval,hashlib.sha256(canonical_bytes(doc)).hexdigest(),doc):
                raise PermissionError("Creator revoked or altered color source before spawn")
            folder=self.root/job_id
            args=[str(self.python),str(self.script),
                  "--src",str(folder/SOURCE),"--dst",str(folder/OUTPUT),
                  "--report",str(folder/REPORT),
                  "--width",str(row["width"]),"--height",str(row["height"]),
                  "--sha",row["source_sha256"],
                  "--config-sha",row["expected_config_sha256"]]
            self.ledger.update(job_id,"rendering","Real pinned OpenColorIO ACES 2.0 CPU transform")
            with (folder/"stdout.log").open("wb") as out, (folder/"stderr.log").open("wb") as err:
                launch_attempted=True
                proc=launch_contained(args,cwd=str(folder),stdout=out,stderr=err,
                                      memory_mb=row["ram_mb"])
                code=proc.wait(timeout=timeout_seconds)
                if code!=0:
                    raise RuntimeError("OS-contained OCIO worker failed with exit "+str(code))
                proc.close()
                closed=True
            self.ledger.update(job_id,"verifying_output","Independent ACEScg pixel and metadata audit")
            receipt,proof=self._verify_finished(row)
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE native_b10_color_jobs SET output_sha256=?,
                    report_sha256=? WHERE job_id=? AND output_sha256 IS NULL""",
                    (receipt["output_exr_sha256"],_sha(folder/REPORT),job_id))
                db.commit()
            self.ledger.finish(job_id,"SUCCEEDED","Genuine ACEScg Float32 EXR verified and OS worker closed")
            return {"state":"SUCCEEDED","job_id":job_id,
                    "source_sha256":receipt["source_exr_sha256"],
                    "acescg_sha256":receipt["output_exr_sha256"],
                    "config_sha256":row["expected_config_sha256"],
                    "independent_checks":proof}
        except BaseException as exc:
            safe=False
            if proc is None:
                # An OS launcher may fail after creating a suspended child
                # but before handing its containment handle to NVP. Never
                # release reserved memory when kernel cleanup is uncertain.
                safe=not launch_attempted
            else:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    closed=True
                    safe=proc.poll() is not None
                except BaseException:
                    safe=False
            if safe and self.ledger.get_task(job_id)["state"]=="ACTIVE":
                self.ledger.finish(job_id,"FAILED",
                                   ("Native color effect refused: "+type(exc).__name__)[:240])
            # Otherwise retain ACTIVE reservation pending OS cleanup proof.
            raise

    def verify_completed(self,job_id):
        row=self._read(job_id)
        if self.ledger.get_task(job_id)["state"]!="SUCCEEDED":
            raise RuntimeError("Color CPU worker is not independently completed")
        receipt,proof=self._verify_finished(row)
        if (receipt["output_exr_sha256"]!=row["output_sha256"] or
            _sha(self.root/job_id/REPORT)!=row["report_sha256"]):
            raise RuntimeError("Color source or journal output changed after successful acceptance")
        return {**proof,"job_id":job_id,
                "project_id":row["project_id"],"frame":row["frame"],
                "source_take_id":row["source_take_id"],
                "source_take_sha256":row["source_take_sha256"]}
