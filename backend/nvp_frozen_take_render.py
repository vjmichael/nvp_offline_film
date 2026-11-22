"""NVP B8: first-party NVP native host authorization for frozen Digital Takes.

This is NOT a FastAPI route and NEVER trusts a model/browser-provided consent.
Installed desktop host MUST authenticate the creator UI action via the
injected verify_creator_action callback. The CI callback is a fixture.
"""
from __future__ import annotations

from hashlib import sha256
import json
import secrets
import time

from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_frozen_take_stage import FORMAT,verify_frozen_stage
from backend.nvp_resource_ledger import TaskLedger


def _doc(supervisor,op):
    return {"task_id":supervisor._activity_id(op.job_id),
            "kind":"blender","operation":json.loads(op.canonical())}


def _digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


class NativeFrozenTakeRender:
    """Approved frozen take -> existing NVP worker, not live editable scene."""

    def __init__(self,capture:DigitalCapture,supervisor:BlenderWorkerSupervisor,
                 ledger:TaskLedger,*,verify_creator_action):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not isinstance(ledger,TaskLedger) or supervisor.activity is not ledger or
            not callable(verify_creator_action)):
            raise TypeError("Trusted FilmIndex capture/native worker/creator verifier required")
        self.capture=capture
        self.supervisor=supervisor
        self.ledger=ledger
        self._creator=verify_creator_action
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_frozen_take_consents(
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                take_id TEXT NOT NULL,
                scene_id TEXT NOT NULL,
                capture_sha256 TEXT NOT NULL,
                stage_metadata_json TEXT NOT NULL,
                stage_metadata_sha256 TEXT NOT NULL,
                document_sha256 TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL
            )""")
        self.dispatcher=ApprovedBlenderDispatcher(
            supervisor,ledger,approval_check=self._check,
            pre_worker_check=self._before_worker)

    @staticmethod
    def _meta(staged):
        return {name:staged[name] for name in
                ("format","project_id","scene_id","take_id","capture_sha256",
                 "world_sha256","timed_source_sha256","timed_render_sha256",
                 "script_sha256","frame_count","frame_rate",
                 "shot_count","actor_count")}

    def _check(self,approval_id,digest,document):
        if type(approval_id) is not str or type(digest) is not str or not isinstance(document,dict):
            return False
        try:
            with self.ledger._db() as db:
                row=db.execute("""SELECT task_id,project_id,take_id,scene_id,
                    capture_sha256,stage_metadata_json,stage_metadata_sha256,
                    document_sha256,issued_at,expires_at,revoked_at
                    FROM native_frozen_take_consents WHERE approval_id=?""",
                    (approval_id,)).fetchone()
            if not row:
                return False
            task,pid,tid,sid,capture_sha,raw,meta_sha,doc_sha,issued,expires,revoked=row
            if (revoked is not None or not issued<=time.time()<=expires or
                doc_sha!=digest or _digest(document)!=doc_sha or
                document.get("task_id")!=task or document.get("kind")!="blender" or
                sha256(raw.encode("ascii")).hexdigest()!=meta_sha):
                return False
            op=BlenderOperation(**document["operation"])
            meta=json.loads(raw)
            if (meta.get("project_id")!=pid or meta.get("take_id")!=tid or
                meta.get("scene_id")!=sid or meta.get("capture_sha256")!=capture_sha or
                self.supervisor._activity_id(op.job_id)!=task):
                return False
            staged={**meta,"operation":op,
                    "stage_dir":self.supervisor.root/op.job_id,
                    "native_approval":"not_granted",
                    "execution":"not_started","resource_admission":"not_checked"}
            verify_frozen_stage(self.capture,self.supervisor,staged)
            return True
        except (KeyError,ValueError,TypeError,RuntimeError,PermissionError,OSError):
            return False

    def _before_worker(self,task_id,document):
        with self.ledger._db() as db:
            row=db.execute("SELECT approval_id FROM native_frozen_take_consents WHERE task_id=?",
                           (task_id,)).fetchone()
        if not row or not self._check(row[0],_digest(document),document):
            raise PermissionError("Frozen take render approval/source no longer authorized")

    def consent_from_trusted_native_action(self,staged,creator_event,*,duration_s=600):
        if type(duration_s) is not int or not 10<=duration_s<=1800:
            raise ValueError("Frozen take native approval expiry out of bounds")
        verify_frozen_stage(self.capture,self.supervisor,staged)
        op=staged["operation"]
        doc=_doc(self.supervisor,op)
        digest=_digest(doc)
        context={
            "operation":"nvp.native.frozen_digital_take.build_and_reopen",
            "project_id":staged["project_id"],"scene_id":staged["scene_id"],
            "take_id":staged["take_id"],
            "capture_sha256":staged["capture_sha256"],
            "world_sha256":staged["world_sha256"],
            "timed_source_sha256":staged["timed_source_sha256"],
            "timed_render_sha256":staged["timed_render_sha256"],
            "script_sha256":staged["script_sha256"],
            "frames":staged["frame_count"],"fps":staged["frame_rate"],
            "shots":staged["shot_count"],
            "job_id":op.job_id,"document_sha256":digest,
            "requested_ram_mb":op.memory_limit_mb,"requested_gpu_mb":op.gpu_memory_mb,
            "gpu_device_id":op.gpu_device_id,
            "output_contract":"timed_blend_plus_independent_camera_actor_frame_audit_png",
        }
        if self._creator(creator_event,dict(context)) is not True:
            raise PermissionError("No authenticated native creator consent for exact frozen take")
        verify_frozen_stage(self.capture,self.supervisor,staged)
        meta=canonical_bytes(self._meta(staged))
        approval_id="nvp_take_"+secrets.token_hex(16)
        now=time.time()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_frozen_take_consents
                (approval_id,task_id,project_id,take_id,scene_id,capture_sha256,
                 stage_metadata_json,stage_metadata_sha256,document_sha256,
                 issued_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (approval_id,doc["task_id"],staged["project_id"],staged["take_id"],
                 staged["scene_id"],staged["capture_sha256"],meta.decode("ascii"),
                 sha256(meta).hexdigest(),digest,now,now+duration_s))
            db.commit()
        return {"approval_id":approval_id,"task_id":doc["task_id"],
                "capture_sha256":staged["capture_sha256"],
                "document_sha256":digest,"expires_at":now+duration_s,
                "native_worker_started":False}

    def enqueue_approved(self,staged,approval_id,*,lane="standard"):
        verify_frozen_stage(self.capture,self.supervisor,staged)
        op=staged["operation"]
        doc=_doc(self.supervisor,op)
        if not self._check(approval_id,_digest(doc),doc):
            raise PermissionError("No matching native creator/frozen take approval")
        return self.dispatcher.enqueue(op,approval_id=approval_id,lane=lane)

    def run_next(self):
        return self.dispatcher.run_next()

    def revoke_from_trusted_native_action(self,approval_id,event):
        with self.ledger._db() as db:
            row=db.execute("""SELECT project_id,take_id,scene_id,task_id,
                 document_sha256 FROM native_frozen_take_consents WHERE approval_id=?""",
                 (approval_id,)).fetchone()
        if not row:
            raise KeyError("Frozen take native consent not found")
        ctx={"operation":"nvp.native.frozen_digital_take.revoke",
             "project_id":row[0],"take_id":row[1],"scene_id":row[2],
             "task_id":row[3],"document_sha256":row[4]}
        if self._creator(event,ctx) is not True:
            raise PermissionError("Native creator revocation not authenticated")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE native_frozen_take_consents SET revoked_at=?
               WHERE approval_id=? AND revoked_at IS NULL""",(time.time(),approval_id))
            if changed.rowcount!=1:
                db.rollback()
                raise RuntimeError("Native frozen take consent already revoked")
            db.commit()
        cancelled=False
        task=self.ledger.get_task(row[3])
        if task and task["state"]=="QUEUED":
            try:
                self.ledger.cancel_queued(row[3],owner_key=self.dispatcher.owner_key)
                cancelled=True
            except (RuntimeError,PermissionError):
                pass
        return {"approval_id":approval_id,"revoked":True,
                "queued_work_cancelled":cancelled}
