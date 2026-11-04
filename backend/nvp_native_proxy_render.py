"""NVP B7: creator-bound native approval for exact staged proxy render.

Host-only code. NEVER publish these methods as untrusted FastAPI routes.
An installed native host must inject authentication of an actual creator UI
event. This module does not implement that native user-presence UI.
"""
from __future__ import annotations

from hashlib import sha256
import json
import secrets
import time

from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor
from backend.nvp_render_source_stage import verify_staged_proxy_source
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio


def _document(supervisor, operation):
    return {"task_id": supervisor._activity_id(operation.job_id),
            "kind":"blender","operation":json.loads(operation.canonical())}


def _digest(doc):
    return sha256(canonical_bytes(doc)).hexdigest()


class NativeApprovedProxyRender:
    """Native host facade with per-project consent and immutable dispatcher."""

    def __init__(self, studio, supervisor, ledger, *, verify_creator_action):
        if (not isinstance(studio,Studio) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not isinstance(ledger,TaskLedger) or supervisor.activity is not ledger):
            raise TypeError("Require NVP Studio, native supervisor and shared task ledger")
        if not callable(verify_creator_action):
            raise TypeError("Trusted native creator-action verifier is required")
        self.studio=studio
        self.supervisor=supervisor
        self.ledger=ledger
        self._creator=verify_creator_action
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_proxy_render_consents(
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                scene_id TEXT NOT NULL,
                proof_json TEXT NOT NULL,
                proof_sha256 TEXT NOT NULL,
                document_sha256 TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                queued_at REAL
            )""")
        self.dispatcher=ApprovedBlenderDispatcher(
            supervisor,ledger,approval_check=self._approval_check,
            pre_worker_check=self._before_worker)

    def _approval_check(self, approval_id, digest, document):
        if type(approval_id) is not str or type(digest) is not str or not isinstance(document,dict):
            return False
        try:
            with self.ledger._db() as db:
                row=db.execute("""SELECT task_id,project_id,scene_id,proof_json,
                    proof_sha256,document_sha256,issued_at,expires_at,revoked_at
                    FROM native_proxy_render_consents WHERE approval_id=?""",
                    (approval_id,)).fetchone()
            if row is None:
                return False
            task_id,pid,sid,raw,proof_sha,doc_sha,issued,expires,revoked=row
            if (revoked is not None or not issued<=time.time()<=expires or
                digest!=doc_sha or document.get("task_id")!=task_id or
                document.get("kind")!="blender" or
                _digest(document)!=doc_sha or
                sha256(raw.encode("ascii")).hexdigest()!=proof_sha):
                return False
            proof=json.loads(raw)
            op=BlenderOperation(**document["operation"])
            if (proof.get("project_id")!=pid or proof.get("scene_id")!=sid or
                self.supervisor._activity_id(op.job_id)!=task_id):
                return False
            staged={
                "format":"nvp.production.staged_proxy_render.v1",
                "operation":op,"stage_dir":self.supervisor.root/op.job_id,
                "project_id":pid,"scene_id":sid,
                "project_revision":proof["project_revision"],
                "world_revision":proof["world_revision"],
                "world_sha256":proof["world_sha256"],
                "blender_script_sha256":proof["blender_script_sha256"],
                "native_approval":"not_granted","execution":"not_started",
                "resource_admission":"not_checked",
            }
            verify_staged_proxy_source(self.studio,self.supervisor,staged,proof)
            return True
        except (KeyError,TypeError,ValueError,RuntimeError,PermissionError,OSError):
            return False

    def _before_worker(self,task_id,document):
        """Recheck live consent/source directly before existing worker launch."""
        with self.ledger._db() as db:
            row=db.execute("SELECT approval_id FROM native_proxy_render_consents WHERE task_id=?",
                           (task_id,)).fetchone()
        if row is None or not self._approval_check(row[0],_digest(document),document):
            raise PermissionError("Render authorization expired/revoked or source changed")

    def consent_from_trusted_native_action(self,staged,proof,creator_event,*,duration_s=600):
        if type(duration_s) is not int or not 10<=duration_s<=1800:
            raise ValueError("Native render consent lifetime out of bounds")
        verify_staged_proxy_source(self.studio,self.supervisor,staged,proof)
        op=staged["operation"]
        document=_document(self.supervisor,op)
        digest=_digest(document)
        context={"operation":"nvp.native.proxy_build",
                 "project_id":proof["project_id"],"scene_id":proof["scene_id"],
                 "project_revision":proof["project_revision"],
                 "world_revision":proof["world_revision"],
                 "world_sha256":proof["world_sha256"],
                 "blender_script_sha256":proof["blender_script_sha256"],
                 "job_id":op.job_id,"document_sha256":digest,
                 "expected_ram_mb":op.memory_limit_mb,
                 "expected_gpu_mb":op.gpu_memory_mb,
                 "device_id":op.gpu_device_id,
                 "output_contract":"blend_build_and_independent_reopen_audit_preview"}
        # Host-provided callback MUST authenticate actual native UI user event
        # and exact context; a browser/model bool is never a consent signal.
        if self._creator(creator_event,dict(context)) is not True:
            raise PermissionError("Creator did not approve this exact native render")
        verify_staged_proxy_source(self.studio,self.supervisor,staged,proof)
        raw=canonical_bytes(proof)
        approval_id="nvp_render_"+secrets.token_hex(16)
        now=time.time()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_proxy_render_consents
                (approval_id,task_id,project_id,scene_id,proof_json,proof_sha256,
                 document_sha256,issued_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (approval_id,document["task_id"],proof["project_id"],proof["scene_id"],
                 raw.decode("ascii"),sha256(raw).hexdigest(),digest,now,now+duration_s))
            db.commit()
        return {"approval_id":approval_id,"task_id":document["task_id"],
                "document_sha256":digest,"expires_at":now+duration_s,
                "worker_started":False}

    def enqueue_approved(self,staged,proof,approval_id,*,lane="standard"):
        verify_staged_proxy_source(self.studio,self.supervisor,staged,proof)
        op=staged["operation"]
        document=_document(self.supervisor,op)
        if not self._approval_check(approval_id,_digest(document),document):
            raise PermissionError("No current exact creator render authorization")
        ticket=self.dispatcher.enqueue(op,approval_id=approval_id,lane=lane)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE native_proxy_render_consents SET queued_at=?
                     WHERE approval_id=? AND task_id=?""",
                     (time.time(),approval_id,document["task_id"]))
            db.commit()
        return ticket

    def run_next(self):
        return self.dispatcher.run_next()

    def revoke_from_trusted_native_action(self,approval_id,creator_event):
        with self.ledger._db() as db:
            row=db.execute("""SELECT project_id,scene_id,task_id,document_sha256
                    FROM native_proxy_render_consents WHERE approval_id=?""",
                    (approval_id,)).fetchone()
        if row is None:
            raise KeyError("Native render grant not found")
        if self._creator(creator_event,{"operation":"nvp.native.proxy_revoke",
                "project_id":row[0],"scene_id":row[1],
                "task_id":row[2],"document_sha256":row[3]}) is not True:
            raise PermissionError("Revocation action did not authenticate")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            updated=db.execute("""UPDATE native_proxy_render_consents SET revoked_at=?
                   WHERE approval_id=? AND revoked_at IS NULL""",(time.time(),approval_id))
            if updated.rowcount!=1:
                db.rollback()
                raise RuntimeError("Already revoked")
            db.commit()
        # Cancel a still-queued task using its scheduler ownership. This
        # never releases ACTIVE reservations or claims an OS worker stopped.
        cancelled=False
        task=self.ledger.get_task(row[2])
        if task is not None and task["state"]=="QUEUED":
            try:
                self.ledger.cancel_queued(row[2],owner_key=self.dispatcher.owner_key)
                cancelled=True
            except (RuntimeError,PermissionError):
                # A concurrent worker may have admitted it. Its resources
                # and cancellation remain supervisor-owned, never guessed.
                pass
        return {"approval_id":approval_id,"revoked":True,
                "queued_work_cancelled":cancelled}
