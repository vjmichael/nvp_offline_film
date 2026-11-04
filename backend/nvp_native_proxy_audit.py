"""NVP B7 independent native Blender reopen of an approved proxy scene.

The build and its source must have been authorized by the host-only
NativeApprovedProxyRender and completed under the existing containment.
The independent reviewer reopens the actual .blend via the pinned Blender
binary in a *second* resource-admitted OS-contained worker. It is a derived,
read-only native audit covered by the exact creator-approved render workflow.
This is not exposed through NVP's untrusted FastAPI or a model tool.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import time

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_blender_acceptance import AUDIT_SCRIPT
from backend.nvp_blender_worker import BlenderOperation,sha_file
from backend.nvp_native_proxy_render import NativeApprovedProxyRender,_digest
from backend.nvp_render_preflight import verify_scene_preflight
from backend.nvp_render_source_stage import _write_exclusive,OUTPUT_FILE,WORLD_FILE

AUDIT_FORMAT="nvp.production.native_reopened_proxy_audit.v1"
AUDIT_SCRIPT_NAME="trusted_blender_reopen_audit.py"
AUDIT_OUTPUT="independent_geometry_audit.json"
PREVIEW_OUTPUT="independent_preview.png"


def _copy_exclusive_verified(source:Path,target:Path,expected_sha:str):
    """Stream native .blend through bounded, exclusive file; no 512MiB bytes allocation."""
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as output,source.open("rb") as original:
            fd=-1
            total=0
            while True:
                part=original.read(1024*1024)
                if not part:break
                total+=len(part)
                if total>512*1024*1024:
                    raise RuntimeError("Blender saved scene larger than audited worker bound")
                output.write(part)
            output.flush()
            os.fsync(output.fileno())
    finally:
        if fd!=-1:os.close(fd)
    if target.is_symlink() or sha_file(target)!=expected_sha:
        raise RuntimeError("Copied Blender scene changed during independent audit staging")


class NativeProxySceneAuditor:
    def __init__(self,host:NativeApprovedProxyRender):
        if not isinstance(host,NativeApprovedProxyRender):
            raise TypeError("Real host-owned NVP renderer required")
        self.host=host
        self.worker=host.supervisor
        self.ledger=host.ledger
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_proxy_scene_audits(
              approval_id TEXT PRIMARY KEY,
              job_id TEXT NOT NULL UNIQUE,
              operation_json TEXT NOT NULL,
              created_at REAL NOT NULL
            )""")

    def _authorized_finished_source(self,approval_id):
        with self.ledger._db() as db:
            consent=db.execute("""SELECT task_id,proof_json,proof_sha256,
                document_sha256,expires_at,revoked_at
                FROM native_proxy_render_consents WHERE approval_id=?""",
                (approval_id,)).fetchone()
            if consent is None:
                raise PermissionError("No durable native render consent")
            task_id,raw,proof_sha,approved_digest,expiry,revoked=consent
            spec=db.execute("""SELECT approval_id,spec_sha256,spec_json
                  FROM authorized_task_specs WHERE task_id=?""",(task_id,)).fetchone()
        if (revoked is not None or time.time()>expiry or
            sha256(raw.encode("ascii")).hexdigest()!=proof_sha or
            spec is None or spec[0]!=approval_id or
            sha256(spec[2].encode("ascii")).hexdigest()!=approved_digest or
            spec[1]!=approved_digest):
            raise PermissionError("Native build permission expired, revoked or altered")
        proof=json.loads(raw)
        document=json.loads(spec[2])
        if _digest(document)!=approved_digest or document.get("task_id")!=task_id:
            raise RuntimeError("Durable approved operation does not match task")
        op=BlenderOperation(**document["operation"])
        if (self.worker._activity_id(op.job_id)!=task_id or
            op.inputs!={WORLD_FILE:proof["world_sha256"]} or
            op.script_sha256!=proof["blender_script_sha256"] or
            op.outputs!={OUTPUT_FILE:"blend"} or
            op.arguments!={"--output":OUTPUT_FILE}):
            raise RuntimeError("Approved source/Blender operation changed")
        verify_scene_preflight(self.host.studio,proof)
        task=self.ledger.get_task(task_id)
        if task is None or task["state"]!="SUCCEEDED":
            raise RuntimeError("Original native build is not verified successful")
        build=self.worker.verify_completed(op.job_id)
        if build["state"]!="SUCCEEDED" or OUTPUT_FILE not in build["outputs"]:
            raise RuntimeError("Missing independently rechecked native Blender build output")
        build_dir=self.worker.root/op.job_id
        for name,expected in ((WORLD_FILE,proof["world_sha256"]),
                              (op.script,proof["blender_script_sha256"])):
            if sha_file(build_dir/name)!=expected:
                raise RuntimeError("Original approved scene source was modified")
        return proof,op,build

    def _prepare_audit(self,approval_id,proof,op,build,*,ram_mb):
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,operation_json
                  FROM native_proxy_scene_audits WHERE approval_id=?""",
                  (approval_id,)).fetchone()
        if row is not None:
            audit_op=BlenderOperation(**json.loads(row[1]))
            if (audit_op.job_id!=row[0] or
                audit_op.script!=AUDIT_SCRIPT_NAME or
                audit_op.script_sha256!=sha256(AUDIT_SCRIPT.encode("utf8")).hexdigest() or
                audit_op.scene!=OUTPUT_FILE or
                audit_op.inputs!={WORLD_FILE:proof["world_sha256"],
                                  OUTPUT_FILE:build["outputs"][OUTPUT_FILE]["sha256"]} or
                audit_op.outputs!={AUDIT_OUTPUT:"json_audit",PREVIEW_OUTPUT:"png"} or
                audit_op.arguments!={"--manifest":WORLD_FILE,
                                     "--audit":AUDIT_OUTPUT,"--render":PREVIEW_OUTPUT} or
                audit_op.memory_limit_mb!=ram_mb):
                raise RuntimeError("Durable independent audit operation changed")
            active=self.ledger.get_task(self.worker._activity_id(audit_op.job_id))
            if active and active["state"]=="SUCCEEDED":
                self.worker.verify_completed(audit_op.job_id)
            else:
                self.worker._validate(audit_op)
            return audit_op

        # A creator-approved native build includes a scoped second-worker
        # geometry/preview audit, never arbitrary new scene effects.
        job_id="review_"+secrets.token_hex(16)
        audit_dir=self.worker.root/job_id
        audit_dir.mkdir(mode=0o700,exist_ok=False)
        try:
            build_dir=self.worker.root/op.job_id
            build_blend=build_dir/OUTPUT_FILE
            blend_sha=build["outputs"][OUTPUT_FILE]["sha256"]
            if sha_file(build_blend)!=blend_sha:
                raise RuntimeError("Saved Blender output changed before review")
            _copy_exclusive_verified(build_blend,audit_dir/OUTPUT_FILE,blend_sha)
            approved_manifest=(build_dir/WORLD_FILE).read_bytes()
            _write_exclusive(audit_dir,WORLD_FILE,approved_manifest)
            source=AUDIT_SCRIPT.encode("utf8")
            _write_exclusive(audit_dir,AUDIT_SCRIPT_NAME,source)
            audit_op=BlenderOperation(
                job_id=job_id,script=AUDIT_SCRIPT_NAME,
                script_sha256=sha256(source).hexdigest(),
                inputs={WORLD_FILE:proof["world_sha256"],
                        OUTPUT_FILE:blend_sha},
                outputs={AUDIT_OUTPUT:"json_audit",PREVIEW_OUTPUT:"png"},
                arguments={"--manifest":WORLD_FILE,
                           "--audit":AUDIT_OUTPUT,"--render":PREVIEW_OUTPUT},
                scene=OUTPUT_FILE,
                memory_limit_mb=ram_mb,timeout_seconds=240,
                require_linux_cgroup_v2=op.require_linux_cgroup_v2,
                gpu_memory_mb=0,
            )
            self.worker._validate(audit_op)
            # A source edit before this second worker invalidates review.
            verify_scene_preflight(self.host.studio,proof)
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                existing=db.execute("""SELECT job_id,operation_json FROM
                     native_proxy_scene_audits WHERE approval_id=?""",
                     (approval_id,)).fetchone()
                if existing is not None:
                    db.rollback()
                    raise RuntimeError("Concurrent native audit staging detected; reconcile")
                db.execute("""INSERT INTO native_proxy_scene_audits
                      (approval_id,job_id,operation_json,created_at)
                      VALUES(?,?,?,?)""",
                      (approval_id,job_id,audit_op.canonical(),time.time()))
                db.commit()
            return audit_op
        except BaseException:
            # No worker has been started for the new random job ID at this
            # point. Only its own staged sources are removed on refusal.
            import shutil
            shutil.rmtree(audit_dir)
            raise

    def reopen_and_verify(self,approval_id,*,ram_mb=2048):
        if type(ram_mb) is not int or not 256<=ram_mb<=65536:
            raise ValueError("Invalid independent Blender audit memory budget")
        proof,op,build=self._authorized_finished_source(approval_id)
        audit_op=self._prepare_audit(approval_id,proof,op,build,ram_mb=ram_mb)
        # Re-run source/host admission rules for a recovered queued audit.
        verify_scene_preflight(self.host.studio,proof)
        task=self.ledger.get_task(self.worker._activity_id(audit_op.job_id))
        if task and task["state"]=="SUCCEEDED":
            audit=self.worker.verify_completed(audit_op.job_id)
        else:
            audit=self.worker.run(audit_op)
        if audit["state"]=="QUEUED":
            return {"format":AUDIT_FORMAT,"state":"QUEUED",
                    "worker_started":False,"verified_real_blender_reopen":False,
                    "audit_job_id":audit_op.job_id}
        if audit["state"]!="SUCCEEDED":
            raise RuntimeError("Independent Blender reopen failed: "+str(audit.get("error")))
        verified=self.worker.verify_completed(audit_op.job_id)
        output_dir=self.worker.root/audit_op.job_id
        report=json.loads((output_dir/AUDIT_OUTPUT).read_text("utf8"))
        if (report.get("format")!="nvp.blender.audit.v1" or
            report.get("scene_id")!=proof["scene_id"] or
            report.get("passed") is not True or
            not isinstance(report.get("checks"),list) or
            not report["checks"] or
            any(x.get("passed") is not True for x in report["checks"])):
            raise RuntimeError("Independent native geometry/visibility audit incomplete")
        verify_scene_preflight(self.host.studio,proof)
        return {"format":AUDIT_FORMAT,"state":"VERIFIED",
                "verified_real_blender_reopen":True,
                "project_id":proof["project_id"],"scene_id":proof["scene_id"],
                "world_sha256":proof["world_sha256"],
                "script_sha256":proof["blender_script_sha256"],
                "build_job_id":op.job_id,
                "build_blend_sha256":build["outputs"][OUTPUT_FILE]["sha256"],
                "audit_job_id":audit_op.job_id,
                "audit_json_sha256":verified["outputs"][AUDIT_OUTPUT]["sha256"],
                "preview_png_sha256":verified["outputs"][PREVIEW_OUTPUT]["sha256"],
                "audit_checks":len(report["checks"]),
                "audit_blender_version":report["blender"],
                "native_completion":"contained_and_independently_reopened",
                "film_grade":"proxy_previsualization_only_not_final_take"}
