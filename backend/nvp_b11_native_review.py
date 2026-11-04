"""B11 native creator-approved, resource-admitted full SDR editorial preview.

The existing standard COLOR-01B ACES2 view and 16-bit FFmpeg readback are
reused; the new work is an adapter to original B9 FLOAT32 FilmIndex media.

No web/model endpoint. Only installed native host supplying an authenticated
local creator callback may grant an exact review. The child is supervised
through TaskLedger admission and OS containment; all images persist on disk.
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
from backend.nvp_b11_editorial import (
    frozen_review_source,verify_sdr_review,SOURCE_COLOR_SPACE,
    NEAR_OPAQUE_ALPHA_POLICY,MAX_ALPHA_SHORTFALL)
from backend.nvp_color_ocio import color_policy
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_render_source_stage import _write_exclusive
from backend.nvp_worker_containment import launch_contained

PLAN="native_sdr_review_plan.json"
DONE="completed_review_receipt.json"
FORMAT="nvp.production.native_b11_sdr_review.v1"


def _digest(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda:source.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


class NativeB11ReviewHost:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root:Path,
                 *,verify_creator_action):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(ledger,TaskLedger) or
            not callable(verify_creator_action)):
            raise TypeError("NVP native creator verifier, FilmIndex capture and TaskLedger required")
        self.capture=capture
        self.ledger=ledger
        self.root=Path(root)
        if self.root.is_symlink():
            raise RuntimeError("Native review workspace must not be symlinked")
        self.root=self.root.resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self._creator=verify_creator_action
        self.python=Path(sys.executable).resolve()
        self.script=Path(__file__).resolve().parents[1]/"tools"/"nvp_b11_review_worker.py"
        self.owner_key="b11_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:24]
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_b11_review_grants(
                job_id TEXT PRIMARY KEY,approval_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,exr_presentation_id TEXT NOT NULL,
                exr_source_sha256 TEXT NOT NULL,take_id TEXT NOT NULL,
                take_sha256 TEXT NOT NULL,review_id TEXT NOT NULL,
                frames INTEGER NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,
                policy_sha256 TEXT NOT NULL,plan_sha256 TEXT NOT NULL,
                spec_sha256 TEXT NOT NULL,python_sha256 TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,ram_mb INTEGER NOT NULL,
                issued_at REAL NOT NULL,expires_at REAL NOT NULL,
                revoked_at REAL,review_document_sha256 TEXT
            )""")
        self.bindings=ApprovedTaskBindings(ledger,approval_check=self._check)

    def _record(self,job_id):
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,approval_id,project_id,exr_presentation_id,
                   exr_source_sha256,take_id,take_sha256,review_id,
                   frames,width,height,policy_sha256,plan_sha256,
                   spec_sha256,python_sha256,script_sha256,ram_mb,
                   issued_at,expires_at,revoked_at,review_document_sha256
                   FROM native_b11_review_grants WHERE job_id=?""",
                   (job_id,)).fetchone()
        if row is None:raise KeyError("Unknown NVP B11 review job")
        names=("job_id","approval_id","project_id","exr_presentation_id",
               "exr_source_sha256","take_id","take_sha256","review_id",
               "frames","width","height","policy_sha256","plan_sha256",
               "spec_sha256","python_sha256","script_sha256","ram_mb",
               "issued_at","expires_at","revoked_at","review_document_sha256")
        return dict(zip(names,row))

    def _verified_source(self,row):
        source=frozen_review_source(self.capture,row["project_id"],
                                    row["exr_presentation_id"])
        if (source["source_presentation_sha256"]!=row["exr_source_sha256"] or
            source["source_take_id"]!=row["take_id"] or
            source["source_take_sha256"]!=row["take_sha256"] or
            source["frame_count"]!=row["frames"] or
            source["resolution"]!=[row["width"],row["height"]]):
            raise RuntimeError("Review source or original frozen take changed")
        return source

    def _check(self,approval,digest,document):
        try:
            if (type(approval) is not str or type(digest) is not str or
                type(document) is not dict):
                return False
            with self.ledger._db() as db:
                match=db.execute("""SELECT job_id FROM native_b11_review_grants
                    WHERE approval_id=?""",(approval,)).fetchone()
            if match is None:return False
            row=self._record(match[0])
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=time.time()<=row["expires_at"] or
                row["spec_sha256"]!=digest or _digest(document)!=digest or
                document.get("kind")!="compositing" or
                document.get("task_id")!=row["job_id"] or
                document.get("project_id")!=row["project_id"] or
                document.get("source_exr_sha256")!=row["exr_source_sha256"] or
                document.get("review_id")!=row["review_id"] or
                document.get("ram_mb")!=row["ram_mb"]):
                return False
            folder=self.root/row["job_id"]
            if (_sha(self.python)!=row["python_sha256"] or
                _sha(self.script)!=row["script_sha256"] or
                _sha(folder/PLAN)!=row["plan_sha256"] or
                (folder/DONE).exists()):
                return False
            meta=json.loads((folder/PLAN).read_text("ascii"))
            if (meta["source_presentation_sha256"]!=row["exr_source_sha256"] or
                meta["source_take_sha256"]!=row["take_sha256"] or
                meta["review_id"]!=row["review_id"] or
                meta["policy_sha256"]!=row["policy_sha256"] or
                meta.get("alpha_policy")!=NEAR_OPAQUE_ALPHA_POLICY or
                meta.get("max_alpha_shortfall")!=MAX_ALPHA_SHORTFALL):
                return False
            policy,_=color_policy()
            if _digest(policy)!=row["policy_sha256"]:
                return False
            self._verified_source(row)
            return True
        except (KeyError,RuntimeError,ValueError,OSError,TypeError):
            return False

    def stage_and_approve(self,project_id,source_exr_id,creator_event,*,
                          ram_mb=2048,duration_s=1800):
        if (type(ram_mb) is not int or not 1024<=ram_mb<=65536 or
            type(duration_s) is not int or not 60<=duration_s<=7200):
            raise ValueError("Invalid native SDR review RAM/lifetime request")
        source=frozen_review_source(self.capture,project_id,source_exr_id)
        width,height=source["resolution"]
        if width*height*4*4*8>ram_mb*1024*1024//2:
            raise ValueError("Native review RAM insufficient for repeated full float buffers")
        bytes_reserved=2*width*height*6*source["frame_count"]+1024**3
        if min(shutil.disk_usage(self.root).free,
               shutil.disk_usage(self.capture.index.blob_root).free)<bytes_reserved:
            raise RuntimeError("Insufficient disk capacity for full FilmIndex SDR review")
        policy,_=color_policy()
        scope={
            "operation":"nvp.native.frozen_float32.aces2_sdr_review",
            "project_id":project_id,"source_presentation_id":source_exr_id,
            "source_presentation_sha256":source["source_presentation_sha256"],
            "source_take_id":source["source_take_id"],
            "source_take_sha256":source["source_take_sha256"],
            "frames":source["frame_count"],"fps":24,
            "resolution":[width,height],"original_float32_rgba":True,
            "output":"color_managed_ACES2_sRGB_16bit_RGB_PNG_sequence",
            "ocio_config_sha256":policy["config_sha256"],
            "processor_cache_id":policy["processor_cache_id"],
            "alpha_policy":NEAR_OPAQUE_ALPHA_POLICY,
            "max_alpha_shortfall":MAX_ALPHA_SHORTFALL,
            "transparency_compositing_approved":False,
            "estimated_disk_headroom_bytes":bytes_reserved,
            "ram_mb":ram_mb,
        }
        if self._creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Native creator did not approve exact full SDR editorial review")
        if frozen_review_source(self.capture,project_id,source_exr_id)!=source:
            raise RuntimeError("Frozen Digital Take changed while awaiting creator approval")
        job_id="reviewjob_"+secrets.token_hex(16)
        review_id="sdrreview_"+secrets.token_hex(16)
        folder=self.root/job_id
        folder.mkdir(mode=0o700,exist_ok=False)
        approval="b11approval_"+secrets.token_hex(16)
        source_policy_sha=_digest(policy)
        spec={"task_id":job_id,"kind":"compositing",
              "project_id":project_id,"source_exr_sha256":source["source_presentation_sha256"],
              "source_take_sha256":source["source_take_sha256"],
              "review_id":review_id,"ram_mb":ram_mb,
              "script_sha256":_sha(self.script),"python_sha256":_sha(self.python),
              "ocio_policy_sha256":source_policy_sha}
        plan={
            "format":"nvp.b11.native_review_plan.v1",
            "project_id":project_id,"source_presentation_id":source_exr_id,
            "source_presentation_sha256":source["source_presentation_sha256"],
            "source_take_id":source["source_take_id"],
            "source_take_sha256":source["source_take_sha256"],
            "review_id":review_id,"studio_db_path":str(self.capture.studio.db_path),
            "output_dir":str(folder/"display_frames"),"source_primaries":SOURCE_COLOR_SPACE,
            "frames":source["frame_count"],"fps":24,
            "resolution":[width,height],"policy_sha256":source_policy_sha,
            "alpha_policy":NEAR_OPAQUE_ALPHA_POLICY,
            "max_alpha_shortfall":MAX_ALPHA_SHORTFALL,
        }
        try:
            _write_exclusive(folder,PLAN,canonical_bytes(plan))
            now=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO native_b11_review_grants
                    (job_id,approval_id,project_id,exr_presentation_id,
                     exr_source_sha256,take_id,take_sha256,review_id,frames,
                     width,height,policy_sha256,plan_sha256,spec_sha256,
                     python_sha256,script_sha256,ram_mb,issued_at,expires_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (job_id,approval,project_id,source_exr_id,
                     source["source_presentation_sha256"],source["source_take_id"],
                     source["source_take_sha256"],review_id,source["frame_count"],
                     width,height,source_policy_sha,_sha(folder/PLAN),_digest(spec),
                     _sha(self.python),_sha(self.script),ram_mb,now,now+duration_s))
                db.commit()
            self.bindings.enqueue(
                AdmissionRequest(job_id,"compositing",
                                 "ACES2 16-bit full SDR film review",ram_mb),
                owner_key=self.owner_key,lane="standard",
                approval_id=approval,document=spec)
            return {"format":FORMAT,"job_id":job_id,"review_id":review_id,
                    "state":"QUEUED","workers_started":False,
                    "frames":source["frame_count"],
                    "original_source_sha256":source["source_presentation_sha256"]}
        except BaseException:
            task=self.ledger.get_task(job_id)
            if task is None:
                # Once journaled, retain the durable grant for repair rather
                # than delete an immutable source identity.
                with self.ledger._db() as db:
                    found=db.execute("""SELECT 1 FROM native_b11_review_grants
                            WHERE job_id=?""",(job_id,)).fetchone()
                if not found:shutil.rmtree(folder)
            raise

    def run_next(self,*,timeout_seconds=1800):
        if type(timeout_seconds) is not int or not 60<=timeout_seconds<=3600:
            raise ValueError("Invalid native full SDR review OS timeout")
        admitted=self.bindings.claim_next(owner_key=self.owner_key)
        if admitted is None or not admitted["admitted"]:
            return admitted
        job_id=admitted["task_id"]
        proc=None
        launched=False
        os_cleanup_proven=False
        try:
            spec=self.bindings.verified_spec(job_id,owner_key=self.owner_key)
            row=self._record(job_id)
            if (spec["source_exr_sha256"]!=row["exr_source_sha256"] or
                spec["ram_mb"]!=row["ram_mb"] or
                _sha(self.script)!=row["script_sha256"] or
                _sha(self.python)!=row["python_sha256"]):
                raise PermissionError("Native SDR review source or exact worker identity changed")
            if not self._check(row["approval_id"],_digest(spec),spec):
                raise PermissionError("Original film source or native creator approval revoked")
            folder=self.root/job_id
            self.ledger.update(job_id,"rendering","True Float32 ACES2 SDR view and PNG16 per-frame native readback")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                launched=True
                proc=launch_contained(
                    [str(self.python),str(self.script),"--plan",str(folder/PLAN)],
                    cwd=str(folder),stdout=out,stderr=err,
                    memory_mb=row["ram_mb"])
                returned=proc.wait(timeout=timeout_seconds)
                if returned!=0:
                    raise RuntimeError("Contained SDR review worker refused film output: "+str(returned))
                proc.close()
                os_cleanup_proven=True
            self.ledger.update(job_id,"verifying_output",
                               "Reopening indexed 16-bit PNGs and source FilmIndex after worker shutdown")
            report=json.loads((folder/DONE).read_text("utf8"))
            proof=verify_sdr_review(
                self.capture,row["project_id"],row["review_id"],decode_png=True)
            record=self.capture.index.read_revision(row["project_id"],row["review_id"])
            if (report.get("format")!="nvp.b11.native_review_completed.v1" or
                report.get("presentation_sha256")!=record["document_sha256"] or
                report.get("frames")!=row["frames"] or
                report.get("source_take_id")!=row["take_id"] or
                report.get("original_source_sha256")!=row["exr_source_sha256"] or
                report.get("all_frames_decoded") is not True):
                raise RuntimeError("Native SDR completed receipt forged or incomplete")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE native_b11_review_grants
                    SET review_document_sha256=? WHERE job_id=?
                    AND review_document_sha256 IS NULL""",
                    (record["document_sha256"],job_id))
                db.commit()
            self.ledger.finish(job_id,"SUCCEEDED","OS-contained full SDR review audited and indexed")
            return {**proof,"state":"SUCCEEDED","job_id":job_id,
                    "original_source_preserved":True}
        except BaseException as exc:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    proc.close()
                    os_cleanup_proven=proc.poll() is not None
                except BaseException:
                    os_cleanup_proven=False
            if not launched:os_cleanup_proven=True
            if os_cleanup_proven and self.ledger.get_task(job_id)["state"]=="ACTIVE":
                self.ledger.finish(job_id,"FAILED",
                                   ("Native SDR review failed: "+type(exc).__name__)[:240])
            # Otherwise retain ACTIVE RAM reservation until kernel-verified
            # worker cleanup. Never invent a completed or failed OS effect.
            raise

    def verify_completed(self,job_id):
        row=self._record(job_id)
        task=self.ledger.get_task(job_id)
        if not task or task["state"]!="SUCCEEDED":
            raise RuntimeError("OS-contained review not proven completed")
        source=self._verified_source(row)
        if _sha(self.root/job_id/PLAN)!=row["plan_sha256"]:
            raise RuntimeError("Native SDR review plan changed after completion")
        proof=verify_sdr_review(self.capture,row["project_id"],row["review_id"],
                                decode_png=True)
        record=self.capture.index.read_revision(row["project_id"],row["review_id"])
        if (record["document_sha256"]!=row["review_document_sha256"] or
            proof["review_frame_count"]!=source["frame_count"]):
            raise RuntimeError("Durable native SDR completion/source identity changed")
        return {**proof,"state":"VERIFIED_COMPLETE","job_id":job_id}

    def revoke_from_trusted_native_action(self,job_id,creator_event):
        row=self._record(job_id)
        scope={"operation":"nvp.native.frozen_float32.sdr_review.revoke",
               "project_id":row["project_id"],"source_take_id":row["take_id"],
               "review_id":row["review_id"],"source_sha256":row["exr_source_sha256"]}
        if self._creator(creator_event,scope) is not True:
            raise PermissionError("Native review revocation not authenticated")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE native_b11_review_grants
                  SET revoked_at=? WHERE job_id=? AND revoked_at IS NULL""",
                  (time.time(),job_id))
            if changed.rowcount!=1:
                db.rollback()
                raise RuntimeError("Native SDR review grant already revoked")
            db.commit()
        cancelled=False
        task=self.ledger.get_task(job_id)
        if task and task["state"]=="QUEUED":
            try:
                self.ledger.cancel_queued(job_id,owner_key=self.owner_key)
                cancelled=True
            except (RuntimeError,PermissionError):
                pass
        return {"revoked":True,"cancelled_queued":cancelled,
                "active_os_cleanup_claimed":False}
