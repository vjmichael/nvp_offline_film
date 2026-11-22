"""NVP B8: separately contained Blender audit of frozen Digital Take motion.

Build uses original immutable FilmIndex world/performance. Review reopens the
actual output in a second pinned Blender worker and samples approved actor
motion plus the frame-accurate camera cut timeline. All statuses derived from
OS-contained jobs and rehashed artifacts, not model or browser declarations.
"""
from __future__ import annotations

from hashlib import sha256
import json
import secrets
import time

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_blender_worker import BlenderOperation,sha_file
from backend.nvp_frozen_take_render import NativeFrozenTakeRender,_digest
from backend.nvp_frozen_take_stage import _source,WORLD,TIMED,SCRIPT,BLEND
from backend.nvp_native_proxy_audit import _copy_exclusive_verified
from backend.nvp_render_source_stage import _write_exclusive
from backend.nvp_shot_sequence import SHOTS_AUDIT_SCRIPT

FORMAT="nvp.production.frozen_take_blender_audit.v1"
AUDIT_SCRIPT="trusted_frozen_take_audit.py"
AUDIT_OUTPUT="timed_take_audit.json"
PREVIEW_OUTPUT="timed_take_preview.png"


class NativeFrozenTakeAuditor:
    def __init__(self,host:NativeFrozenTakeRender):
        if not isinstance(host,NativeFrozenTakeRender):
            raise TypeError("Trusted native frozen Digital Take host required")
        self.host=host
        self.worker=host.supervisor
        self.ledger=host.ledger
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_frozen_take_audits(
                approval_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL UNIQUE,
                operation_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )""")

    def _approved_build(self,approval_id):
        with self.ledger._db() as db:
            row=db.execute("""SELECT task_id,project_id,take_id,scene_id,
                  capture_sha256,stage_metadata_json,stage_metadata_sha256,
                  document_sha256,expires_at,revoked_at FROM native_frozen_take_consents
                  WHERE approval_id=?""",(approval_id,)).fetchone()
            if row is None:
                raise PermissionError("No approved native frozen take")
            spec=db.execute("""SELECT approval_id,spec_sha256,spec_json
                  FROM authorized_task_specs WHERE task_id=?""",(row[0],)).fetchone()
        (task,pid,tid,sid,capture_sha,meta_raw,meta_sha,doc_sha,expiry,revoked)=row
        if (revoked is not None or time.time()>expiry or spec is None or
            spec[0]!=approval_id or spec[1]!=doc_sha or
            sha256(spec[2].encode("ascii")).hexdigest()!=doc_sha or
            sha256(meta_raw.encode("ascii")).hexdigest()!=meta_sha):
            raise PermissionError("Native frozen-take source approval revoked/expired/altered")
        document=json.loads(spec[2])
        meta=json.loads(meta_raw)
        if (_digest(document)!=doc_sha or
            document.get("task_id")!=task or
            meta.get("capture_sha256")!=capture_sha or
            meta.get("project_id")!=pid or meta.get("take_id")!=tid or
            meta.get("scene_id")!=sid):
            raise RuntimeError("Durable frozen-take metadata does not match approved operation")
        op=BlenderOperation(**document["operation"])
        # This is a POST-COMPLETION audit. The prelaunch grant verifier
        # deliberately refuses any job directory with an existing output;
        # calling it here would reject every real successful .blend. Instead,
        # validate sealed consent + exact pinned source and the native worker
        # journal/outputs (below), without re-enabling launch.
        source=_source(self.host.capture,pid,tid)
        if (source["capture_sha256"]!=capture_sha or
            any(source[name]!=meta.get(name) for name in
                ("capture_sha256","world_sha256","timed_source_sha256",
                 "timed_render_sha256","script_sha256","frame_count")) or
            op.script!=SCRIPT or op.script_sha256!=source["script_sha256"] or
            op.inputs!={WORLD:sha256(source["bytes"][WORLD]).hexdigest(),
                        TIMED:source["timed_render_sha256"]} or
            op.outputs!={BLEND:"blend"} or
            op.arguments!={"--output":BLEND} or op.scene is not None or
            self.worker._activity_id(op.job_id)!=task):
            raise RuntimeError("Completed native frozen take deviates from approved source")
        state=self.ledger.get_task(task)
        if not state or state["state"]!="SUCCEEDED":
            raise RuntimeError("Frozen Digital Take source Blender build is not verified successful")
        accepted=self.worker.verify_completed(op.job_id)
        if accepted["state"]!="SUCCEEDED" or BLEND not in accepted["outputs"]:
            raise RuntimeError("Native timed .blend output not independently accepted")
        return meta,op,accepted,source

    def _make_audit(self,approval_id,meta,op,build,source,ram_mb):
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,operation_json FROM
                     native_frozen_take_audits WHERE approval_id=?""",(approval_id,)).fetchone()
        expected_script=sha256(SHOTS_AUDIT_SCRIPT.encode("utf8")).hexdigest()
        frozen_blend_sha=build["outputs"][BLEND]["sha256"]
        inputs={TIMED:source["timed_render_sha256"],BLEND:frozen_blend_sha}
        outputs={AUDIT_OUTPUT:"json_audit",PREVIEW_OUTPUT:"png"}
        arguments={"--take":TIMED,"--audit":AUDIT_OUTPUT,"--preview":PREVIEW_OUTPUT}
        if row:
            job=BlenderOperation(**json.loads(row[1]))
            if (job.job_id!=row[0] or job.script!=AUDIT_SCRIPT or
                job.script_sha256!=expected_script or job.scene!=BLEND or
                job.inputs!=inputs or job.outputs!=outputs or job.arguments!=arguments or
                job.memory_limit_mb!=ram_mb):
                raise RuntimeError("Previously journaled frozen-take audit specification mutated")
            record=self.ledger.get_task(self.worker._activity_id(job.job_id))
            if record and record["state"]=="SUCCEEDED":
                self.worker.verify_completed(job.job_id)
            else:
                self.worker._validate(job)
            return job

        job_id="frozen_review_"+secrets.token_hex(16)
        jobdir=self.worker.root/job_id
        jobdir.mkdir(mode=0o700,exist_ok=False)
        try:
            original=self.worker.root/op.job_id/BLEND
            if sha_file(original)!=frozen_blend_sha:
                raise RuntimeError("Saved timed Blender source changed before independent review")
            _copy_exclusive_verified(original,jobdir/BLEND,frozen_blend_sha)
            _write_exclusive(jobdir,TIMED,source["bytes"][TIMED])
            _write_exclusive(jobdir,AUDIT_SCRIPT,SHOTS_AUDIT_SCRIPT.encode("utf8"))
            job=BlenderOperation(
                job_id=job_id,script=AUDIT_SCRIPT,
                script_sha256=expected_script,inputs=inputs,
                outputs=outputs,arguments=arguments,scene=BLEND,
                memory_limit_mb=ram_mb,timeout_seconds=240,
                require_linux_cgroup_v2=op.require_linux_cgroup_v2,
                gpu_memory_mb=0,
            )
            self.worker._validate(job)
            # Existing FilmIndex capture must still independently reopen
            # and all stored reference hashes must match before journal.
            fresh=_source(self.host.capture,meta["project_id"],meta["take_id"])
            if fresh["capture_sha256"]!=meta["capture_sha256"]:
                raise RuntimeError("Frozen Digital Take revision replaced during review")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                existing=db.execute("SELECT job_id FROM native_frozen_take_audits WHERE approval_id=?",
                                    (approval_id,)).fetchone()
                if existing:
                    db.rollback()
                    raise RuntimeError("Concurrent native frozen take audit detected")
                db.execute("""INSERT INTO native_frozen_take_audits
                     (approval_id,job_id,operation_json,created_at)
                     VALUES(?,?,?,?)""",
                     (approval_id,job.job_id,job.canonical(),time.time()))
                db.commit()
            return job
        except BaseException:
            import shutil
            shutil.rmtree(jobdir)
            raise

    @staticmethod
    def _verify_checks(report,source):
        if (type(report) is not dict or
            report.get("format")!="nvp.production.blender.take.audit.v1" or
            report.get("passed") is not True or
            report.get("rendered") is not True or
            type(report.get("checks")) is not list):
            raise RuntimeError("Independent timed native audit was not successful")
        recorded=report["checks"]
        if any(type(row) is not dict or row.get("passed") is not True or
               type(row.get("check")) is not str for row in recorded):
            raise RuntimeError("Native timed Blender check failed or malformed")
        take=json.loads(source["bytes"][TIMED])
        required={"take_sha","dependency_sha","fps","duration"}
        for shot in take["shots"]:
            for field in ("camera:","lens:","camera_pose:","cut:"):
                required.add(field+shot["id"])
        for actor in take["actors"]:
            required.add("actor:"+actor["instance_id"])
            for sample in actor["audit_samples"]:
                required.add("pose:"+actor["instance_id"]+":"+str(sample["frame"]))
        actual=[row["check"] for row in recorded]
        if len(actual)!=len(required) or set(actual)!=required:
            raise RuntimeError("Independent timed Blender audit omitted or duplicated frame/cut checks")
        return len(required)

    def reopen_and_verify(self,approval_id,*,ram_mb=2048):
        if type(ram_mb) is not int or not 256<=ram_mb<=65536:
            raise ValueError("Invalid native frozen take review RAM limit")
        meta,op,build,source=self._approved_build(approval_id)
        audit_job=self._make_audit(approval_id,meta,op,build,source,ram_mb)
        record=self.ledger.get_task(self.worker._activity_id(audit_job.job_id))
        if record and record["state"]=="SUCCEEDED":
            output=self.worker.verify_completed(audit_job.job_id)
        else:
            output=self.worker.run(audit_job)
        if output["state"]=="QUEUED":
            return {"format":FORMAT,"state":"QUEUED","worker_started":False,
                    "verified_frozen_timeline":False,
                    "audit_job_id":audit_job.job_id}
        if output["state"]!="SUCCEEDED":
            raise RuntimeError("Second Blender frozen take review did not succeed: "+
                               str(output.get("error")))
        verified=self.worker.verify_completed(audit_job.job_id)
        report=json.loads((self.worker.root/audit_job.job_id/AUDIT_OUTPUT).read_text("utf8"))
        checks=self._verify_checks(report,source)
        # Preserve accepted results independently of editable current scene.
        fresh=_source(self.host.capture,meta["project_id"],meta["take_id"])
        if fresh["capture_sha256"]!=meta["capture_sha256"]:
            raise RuntimeError("Original captured take was modified after Blender audit")
        return {
            "format":FORMAT,"state":"VERIFIED",
            "project_id":meta["project_id"],"scene_id":meta["scene_id"],
            "take_id":meta["take_id"],"capture_sha256":meta["capture_sha256"],
            "world_sha256":source["world_sha256"],
            "timed_render_sha256":source["timed_render_sha256"],
            "script_sha256":source["script_sha256"],
            "frame_rate":source["frame_rate"],"frame_count":source["frame_count"],
            "shot_count":source["shot_count"],"actor_count":source["actor_count"],
            "build_job_id":op.job_id,
            "build_blend_sha256":build["outputs"][BLEND]["sha256"],
            "audit_job_id":audit_job.job_id,
            "audit_json_sha256":verified["outputs"][AUDIT_OUTPUT]["sha256"],
            "preview_png_sha256":verified["outputs"][PREVIEW_OUTPUT]["sha256"],
            "independently_checked_timeline_features":checks,
            "actual_native_blender_reopen":True,
            "film_status":"frozen_proxy_timing_previs_not_final_motion_or_film",
        }
