"""NVP B9: native, consent-bound full frozen-take EXR sequence.

Each <=8-frame chunk is submitted through the existing ApprovedBlenderDispatcher
and TaskLedger into the OS-contained Blender worker. Each successful chunk is
independently decoded by a DIFFERENT contained Blender worker and checked by
an OpenEXR header parser before any derived FilmIndex presentation is published.
No model/browser can mint the native creator event; Lu is not involved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time

from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_exr_fidelity import inspect_exr_header
from backend.nvp_b10_render_profiles import profile_for,validate_full_render
from backend.nvp_exr_scripts import EXR_RENDER_SCRIPT,EXR_AUDIT_SCRIPT
from backend.nvp_frozen_take_presentation import verify_presentation
from backend.nvp_frozen_take_stage import _source,TIMED,BLEND
from backend.nvp_native_proxy_audit import _copy_exclusive_verified
from backend.nvp_production_scene import digest
from backend.nvp_render_source_stage import _write_exclusive
from backend.nvp_resource_ledger import TaskLedger

PLAN_FILE="exr_chunk_plan.json"
RENDER_SCRIPT_FILE="trusted_exr_frames.py"
AUDIT_SCRIPT_FILE="trusted_exr_readback.py"
AUDIT_JSON="independent_exr_float_audit.json"
FORMAT="nvp.production.exr_sequence.v1"
MAX_FRAMES_PER_WORKER=8


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha_json(obj):
    return _sha_bytes(canonical_bytes(obj))


def frame_filename(n):
    if type(n) is not int or not 1<=n<=14400:
        raise ValueError("Invalid NVP bounded frame number")
    return "frame_%06d.exr"%n


class NativeEXRSequence:
    """Only a trusted native desktop host should instantiate this service."""

    def __init__(self,capture:DigitalCapture,worker:BlenderWorkerSupervisor,
                 ledger:TaskLedger,*,verify_creator_action):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(worker,BlenderWorkerSupervisor) or
            not isinstance(ledger,TaskLedger) or worker.activity is not ledger or
            not callable(verify_creator_action)):
            raise TypeError("Trusted NVP capture/Blender host/creator action required")
        self.capture=capture
        self.worker=worker
        self.ledger=ledger
        self._creator=verify_creator_action
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_exr_sequences(
              sequence_id TEXT PRIMARY KEY,
              approval_id TEXT NOT NULL UNIQUE,
              project_id TEXT NOT NULL,take_id TEXT NOT NULL,
              preview_id TEXT NOT NULL,preview_sha256 TEXT NOT NULL,
              capture_sha256 TEXT NOT NULL,blend_sha256 TEXT NOT NULL,
              width INTEGER NOT NULL,height INTEGER NOT NULL,
              fps INTEGER NOT NULL,frame_count INTEGER NOT NULL,
              chunk_size INTEGER NOT NULL,ram_mb INTEGER NOT NULL,
              source_script_sha256 TEXT NOT NULL,
              issued_at REAL NOT NULL,expires_at REAL NOT NULL,
              revoked_at REAL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_exr_chunk_jobs(
              sequence_id TEXT NOT NULL,
              start_frame INTEGER NOT NULL,stop_frame INTEGER NOT NULL,
              job_id TEXT NOT NULL UNIQUE,op_json TEXT NOT NULL,
              audit_job_id TEXT UNIQUE,audit_op_json TEXT,
              PRIMARY KEY(sequence_id,start_frame),
              FOREIGN KEY(sequence_id) REFERENCES native_exr_sequences(sequence_id)
            )""")
        self.dispatcher=ApprovedBlenderDispatcher(worker,ledger,
                      approval_check=self._approval_check,
                      pre_worker_check=self._before_worker)

    def _row(self,sequence_id):
        with self.ledger._db() as db:
            db.row_factory=None
            row=db.execute("""SELECT sequence_id,approval_id,project_id,take_id,
                preview_id,preview_sha256,capture_sha256,blend_sha256,
                width,height,fps,frame_count,chunk_size,ram_mb,
                source_script_sha256,issued_at,expires_at,revoked_at
                FROM native_exr_sequences WHERE sequence_id=?""",(sequence_id,)).fetchone()
        if not row:raise KeyError("Unknown native EXR sequence")
        cols=("sequence_id","approval_id","project_id","take_id","preview_id",
              "preview_sha256","capture_sha256","blend_sha256","width","height",
              "fps","frame_count","chunk_size","ram_mb",
              "source_script_sha256","issued_at","expires_at","revoked_at")
        return dict(zip(cols,row))

    def _verify_source(self,seq):
        proof=verify_presentation(self.capture,seq["project_id"],seq["preview_id"])
        preview=self.capture.index.read_revision(seq["project_id"],seq["preview_id"])
        original=_source(self.capture,seq["project_id"],seq["take_id"])
        if (preview["document_sha256"]!=seq["preview_sha256"] or
            proof["source_take_id"]!=seq["take_id"] or
            proof["source_capture_sha256"]!=seq["capture_sha256"] or
            proof["blend_sha256"]!=seq["blend_sha256"] or
            original["capture_sha256"]!=seq["capture_sha256"] or
            original["frame_count"]!=seq["frame_count"] or
            original["frame_rate"]!=seq["fps"] or
            original["script_sha256"]!=seq["source_script_sha256"]):
            raise RuntimeError("Native EXR sequence no longer bound to original frozen Digital Take")
        media=self.capture.index.verify_media_file(
            seq["project_id"],seq["blend_sha256"],"application/octet-stream")
        return original,Path(media["path"])

    def create_from_trusted_native_action(self,project_id,take_id,preview_id,
                                          creator_event,*,width=160,height=90,
                                          chunk_size=8,ram_mb=2048,
                                          duration_s=1800):
        preset=profile_for(width,height)
        if (type(chunk_size) is not int or not 1<=chunk_size<=preset.max_chunk_frames or
            type(ram_mb) is not int or
            not preset.minimum_ram_mb<=ram_mb<=65536 or
            type(duration_s) is not int or not 30<=duration_s<=7200):
            raise ValueError("Invalid resolution-scoped EXR batch, RAM budget or native consent lifetime")
        verified=verify_presentation(self.capture,project_id,preview_id)
        preview=self.capture.index.read_revision(project_id,preview_id)
        original=_source(self.capture,project_id,take_id)
        if (verified["source_take_id"]!=take_id or
            verified["source_capture_sha256"]!=original["capture_sha256"] or
            verified["timeline_frames"]!=original["frame_count"]):
            raise RuntimeError("EXR source must be the verified native output of this frozen take")
        disk_policy=validate_full_render(width,height,chunk_size,ram_mb,
                original["frame_count"],worker_root=self.worker.root,
                archive_root=self.capture.index.blob_root)
        scope={"operation":"nvp.native.frozen_take.full_float32_exr_sequence",
               "project_id":project_id,"take_id":take_id,"preview_id":preview_id,
               "capture_sha256":original["capture_sha256"],
               "native_blend_sha256":verified["blend_sha256"],
               "fps":original["frame_rate"],"frame_count":original["frame_count"],
               "resolution":[width,height],"channels":"RGBA_FLOAT32",
               "engine":"BLENDER_WORKBENCH","view_transform":"Raw",
               "codec":"ZIP","ram_mb":ram_mb,"chunk_size":chunk_size,
               "render_profile":disk_policy["profile"],
               "required_disk_headroom_bytes":disk_policy["required_available_disk_bytes"],
               "post_render_pixel_readback":True}
        if self._creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Actual creator did not authorize full EXR render output")
        # Human approval can take time; recheck authoritative indexed source.
        verify_presentation(self.capture,project_id,preview_id)
        sequence_id="exr_"+secrets.token_hex(16)
        approval_id="exrgrant_"+secrets.token_hex(16)
        now=time.time()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_exr_sequences VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (sequence_id,approval_id,project_id,take_id,preview_id,
                 preview["document_sha256"],original["capture_sha256"],
                 verified["blend_sha256"],width,height,original["frame_rate"],
                 original["frame_count"],chunk_size,ram_mb,
                 original["script_sha256"],now,now+duration_s))
            db.commit()
        return {"format":FORMAT,"sequence_id":sequence_id,
                "approval_id":approval_id,
                "frames":original["frame_count"],"fps":original["frame_rate"],
                "width":width,"height":height,
                "native_creator_approved":True,
                "workers_started":False,
                "full_sequence_verified":False}

    @staticmethod
    def _plans(seq,source):
        take=json.loads(source["bytes"][TIMED])
        shots=[{"id":r["id"],"start_frame":r["start_frame"]}
               for r in take["shots"]]
        for start in range(1,seq["frame_count"]+1,seq["chunk_size"]):
            stop=min(seq["frame_count"],start+seq["chunk_size"]-1)
            frames=[{"frame":f,"file":frame_filename(f)}
                    for f in range(start,stop+1)]
            yield start,stop,{
                "format":"nvp.exr.render_chunk.v1",
                "sequence_id":seq["sequence_id"],
                "project_id":seq["project_id"],
                "take_id":seq["take_id"],
                "capture_sha256":seq["capture_sha256"],
                "source_blend_sha256":seq["blend_sha256"],
                "sequence_sha256":take["sequence_sha"],
                "dependency_sha256":take["dependency_sha"],
                "fps":seq["fps"],"total_frames":seq["frame_count"],
                "resolution":[seq["width"],seq["height"]],
                "engine":"BLENDER_WORKBENCH","color_depth":32,
                "color_mode":"RGBA","exr_codec":"ZIP",
                "view_transform":"Raw","shots":shots,"frames":frames,
            }

    def _chunk(self,seq_id,start):
        with self.ledger._db() as db:
            row=db.execute("""SELECT start_frame,stop_frame,job_id,op_json,
                 audit_job_id,audit_op_json FROM native_exr_chunk_jobs
                 WHERE sequence_id=? AND start_frame=?""",(seq_id,start)).fetchone()
        if not row:return None
        return {"start":row[0],"stop":row[1],"job_id":row[2],
                "op":BlenderOperation(**json.loads(row[3])),
                "audit_id":row[4],
                "audit_op":BlenderOperation(**json.loads(row[5])) if row[5] else None}

    def _approval_check(self,approval_id,digest,document):
        try:
            if type(approval_id) is not str or type(digest) is not str or not isinstance(document,dict):
                return False
            with self.ledger._db() as db:
                found=db.execute("""SELECT sequence_id FROM native_exr_sequences
                     WHERE approval_id=?""",(approval_id,)).fetchone()
            if not found:return False
            seq=self._row(found[0])
            if (seq["revoked_at"] is not None or not
                seq["issued_at"]<=time.time()<=seq["expires_at"]):
                return False
            source,_=self._verify_source(seq)
            op=BlenderOperation(**document["operation"])
            if document.get("kind")!="blender" or document.get("task_id")!=self.worker._activity_id(op.job_id):
                return False
            with self.ledger._db() as db:
                row=db.execute("""SELECT start_frame,op_json FROM native_exr_chunk_jobs
                 WHERE sequence_id=? AND job_id=?""",(seq["sequence_id"],op.job_id)).fetchone()
            if not row or op.canonical()!=row[1]:
                return False
            if hashlib.sha256(canonical_bytes(document)).hexdigest()!=digest:
                return False
            # Verification occurs BEFORE output creation: the native worker
            # deliberately refuses pre-existing output files (no overwrite).
            self.worker._validate(op)
            preset=profile_for(seq["width"],seq["height"])
            if (seq["chunk_size"]>preset.max_chunk_frames or
                seq["ram_mb"]<preset.minimum_ram_mb):
                return False
            if op.memory_limit_mb!=seq["ram_mb"] or op.gpu_memory_mb!=0:
                return False
            return True
        except (RuntimeError,ValueError,PermissionError,KeyError,OSError,TypeError):
            return False

    def _before_worker(self,task_id,document):
        with self.ledger._db() as db:
            row=db.execute("""SELECT approval_id FROM authorized_task_specs
                   WHERE task_id=?""",(task_id,)).fetchone()
        if row is None or not self._approval_check(
                row[0],hashlib.sha256(canonical_bytes(document)).hexdigest(),document):
            raise PermissionError("Native EXR grant or indexed frozen source changed")

    def queue_next_chunk(self,sequence_id):
        seq=self._row(sequence_id)
        if seq["revoked_at"] is not None or time.time()>seq["expires_at"]:
            raise PermissionError("Native full-sequence EXR grant is revoked or expired")
        original,blend=self._verify_source(seq)
        for start,stop,plan in self._plans(seq,original):
            existing=self._chunk(sequence_id,start)
            if existing:
                task_id=self.worker._activity_id(existing["job_id"])
                task=self.ledger.get_task(task_id)
                if task is None:
                    # Source was fsynced and job ledgered, but host died
                    # before atomic scheduler enqueue. Never invent a new
                    # job ID or overwrite the earlier immutable staged files.
                    self.worker._validate(existing["op"])
                    ticket=self.dispatcher.enqueue(
                        existing["op"],approval_id=seq["approval_id"],lane="standard")
                    return {"state":"QUEUED","chunk":[start,existing["stop"]],
                            "job_id":existing["job_id"],"task_id":ticket["task_id"],
                            "recovered_staged_source":True}
                # QUEUED/ACTIVE/SUCCEEDED/FAILED are durable and may not
                # be automatically replayed under a second job identity.
                continue
            job_id="exrjob_"+secrets.token_hex(16)
            jobdir=self.worker.root/job_id
            jobdir.mkdir(mode=0o700,exist_ok=False)
            try:
                blend_sha=seq["blend_sha256"]
                _copy_exclusive_verified(blend,jobdir/BLEND,blend_sha)
                payload=canonical_bytes(plan)
                _write_exclusive(jobdir,PLAN_FILE,payload)
                script=EXR_RENDER_SCRIPT.encode("utf8")
                _write_exclusive(jobdir,RENDER_SCRIPT_FILE,script)
                outputs={item["file"]:"exr" for item in plan["frames"]}
                op=BlenderOperation(
                    job_id=job_id,script=RENDER_SCRIPT_FILE,
                    script_sha256=_sha_bytes(script),
                    inputs={BLEND:blend_sha,PLAN_FILE:_sha_bytes(payload)},
                    outputs=outputs,arguments={"--plan":PLAN_FILE},scene=BLEND,
                    timeout_seconds=600,memory_limit_mb=seq["ram_mb"],
                    gpu_memory_mb=0,
                )
                self.worker._validate(op)
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("""INSERT INTO native_exr_chunk_jobs
                      (sequence_id,start_frame,stop_frame,job_id,op_json)
                      VALUES (?,?,?,?,?)""",
                      (sequence_id,start,stop,job_id,op.canonical()))
                    db.commit()
                ticket=self.dispatcher.enqueue(
                    op,approval_id=seq["approval_id"],lane="standard")
                return {"state":"QUEUED","chunk":[start,stop],
                        "job_id":job_id,"task_id":ticket["task_id"]}
            except BaseException:
                # If a queue or worker has been journaled, do not destroy its
                # source files or pretend its effect is rolled back.
                task=self.ledger.get_task(self.worker._activity_id(job_id))
                if task is None:
                    with self.ledger._db() as db:
                        db.execute("DELETE FROM native_exr_chunk_jobs WHERE job_id=?",(job_id,))
                    shutil.rmtree(jobdir)
                raise
        return None

    def revoke_from_trusted_native_action(self,sequence_id,creator_event):
        """Revoke only after another authenticated native creator action.

        QUEUED tasks can be cancelled with their scheduler owner key;
        ACTIVE workers and RAM reservations remain OS-supervisor-owned.
        """
        seq=self._row(sequence_id)
        scope={"operation":"nvp.native.frozen_take.exr_sequence.revoke",
               "project_id":seq["project_id"],"take_id":seq["take_id"],
               "preview_id":seq["preview_id"],
               "source_take_sha256":seq["capture_sha256"],
               "sequence_id":sequence_id,
               "resolution":[seq["width"],seq["height"]],
               "frames":seq["frame_count"]}
        if self._creator(creator_event,scope) is not True:
            raise PermissionError("Native creator did not authorize sequence cancellation")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            updated=db.execute("""UPDATE native_exr_sequences
                    SET revoked_at=? WHERE sequence_id=? AND revoked_at IS NULL""",
                    (time.time(),sequence_id))
            if updated.rowcount!=1:
                db.rollback()
                raise RuntimeError("EXR sequence consent already revoked")
            jobs=db.execute("""SELECT job_id FROM native_exr_chunk_jobs
                    WHERE sequence_id=?""",(sequence_id,)).fetchall()
            db.commit()
        cancelled=[]
        for (job_id,) in jobs:
            task_id=self.worker._activity_id(job_id)
            task=self.ledger.get_task(task_id)
            if task is not None and task["state"]=="QUEUED":
                try:
                    self.ledger.cancel_queued(task_id,owner_key=self.dispatcher.owner_key)
                    cancelled.append(task_id)
                except (RuntimeError,PermissionError):
                    # A concurrent claimant may own a live Blender process;
                    # never release its RAM or imply the OS worker stopped.
                    pass
        return {"sequence_id":sequence_id,"revoked":True,
                "cancelled_queued_task_ids":cancelled,
                "active_worker_cleanup_claimed":False}

    def run_queued_chunk(self):
        """Existing dispatcher owns physical RAM admission and native process."""
        return self.dispatcher.run_next()

    def _audit_chunk(self,seq,chunk,plan,source):
        render=self.worker.verify_completed(chunk["job_id"])
        if render["state"]!="SUCCEEDED" or set(render["outputs"])!={x["file"] for x in plan["frames"]}:
            raise RuntimeError("Original EXR batch missing independently verified full output set")
        jobdir=self.worker.root/chunk["job_id"]
        for row in plan["frames"]:
            inspect_exr_header(jobdir/row["file"],width=seq["width"],height=seq["height"])
        if chunk["audit_op"] is None:
            job_id="exraudit_"+secrets.token_hex(16)
            audit_dir=self.worker.root/job_id
            audit_dir.mkdir(mode=0o700,exist_ok=False)
            try:
                plan_bytes=canonical_bytes(plan)
                _write_exclusive(audit_dir,PLAN_FILE,plan_bytes)
                script=EXR_AUDIT_SCRIPT.encode("utf8")
                _write_exclusive(audit_dir,AUDIT_SCRIPT_FILE,script)
                inputs={PLAN_FILE:_sha_bytes(plan_bytes)}
                for row in plan["frames"]:
                    path=jobdir/row["file"]
                    sha=render["outputs"][row["file"]]["sha256"]
                    _copy_exclusive_verified(path,audit_dir/row["file"],sha)
                    inputs[row["file"]]=sha
                op=BlenderOperation(
                    job_id=job_id,script=AUDIT_SCRIPT_FILE,
                    script_sha256=_sha_bytes(script),inputs=inputs,
                    outputs={AUDIT_JSON:"json_audit"},
                    arguments={"--plan":PLAN_FILE,"--audit":AUDIT_JSON},
                    memory_limit_mb=seq["ram_mb"],gpu_memory_mb=0,
                    timeout_seconds=600,
                )
                self.worker._validate(op)
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    updated=db.execute("""UPDATE native_exr_chunk_jobs
                       SET audit_job_id=?,audit_op_json=?
                       WHERE sequence_id=? AND start_frame=?
                         AND audit_job_id IS NULL""",
                       (job_id,op.canonical(),seq["sequence_id"],chunk["start"]))
                    if updated.rowcount!=1:
                        db.rollback()
                        raise RuntimeError("Concurrent independent EXR audit staging; reconcile")
                    db.commit()
                chunk["audit_op"]=op
            except BaseException:
                with self.ledger._db() as db:
                    current=db.execute("""SELECT audit_job_id FROM native_exr_chunk_jobs
                        WHERE sequence_id=? AND start_frame=?""",
                        (seq["sequence_id"],chunk["start"])).fetchone()
                if current is not None and current[0] is None:
                    shutil.rmtree(audit_dir)
                raise
        op=chunk["audit_op"]
        try:
            status=self.worker.verify_completed(op.job_id)
        except (KeyError,RuntimeError):
            existing=self.ledger.get_task(self.worker._activity_id(op.job_id))
            if existing and existing["state"] in ("FAILED","CANCELLED","INTERRUPTED","TIMED_OUT"):
                raise RuntimeError("Previously failed independent EXR audit cannot be replayed")
            status=self.worker.run(op)
        if status["state"]=="QUEUED":
            return {"state":"QUEUED","audit_id":op.job_id}
        if status["state"]!="SUCCEEDED":
            raise RuntimeError("Independent Blender EXR pixel readback worker failed")
        verified=self.worker.verify_completed(op.job_id)
        json_path=self.worker.root/op.job_id/AUDIT_JSON
        report=json.loads(json_path.read_text("utf8"))
        expected_names=set()
        for row in plan["frames"]:
            for prefix in ("float32","size","rgba","finite"):
                expected_names.add(prefix+":"+str(row["frame"]))
        checks=report.get("checks",[])
        if (report.get("format")!="nvp.exr.native_float_readback.v1" or
            report.get("passed") is not True or
            report.get("required_channel_depth")!=32 or
            report.get("linear_write_transform")!="Raw" or
            report.get("resolution")!=[seq["width"],seq["height"]] or
            len(checks)!=len(expected_names) or
            {c.get("check") for c in checks}!=expected_names or
            any(c.get("passed") is not True for c in checks) or
            len(report.get("frames",[]))!=len(plan["frames"])):
            raise RuntimeError("Independent Blender readback omitted or falsified EXR channel/pixel checks")
        by_number={f["frame"]:f for f in report["frames"]}
        if len(by_number)!=len(plan["frames"]):
            raise RuntimeError("Duplicate audited EXR frames")
        for row in plan["frames"]:
            value=by_number[row["frame"]]
            if (value.get("file")!=row["file"] or
                value.get("sha256")!=render["outputs"][row["file"]]["sha256"] or
                value.get("decoded_float_buffer") is not True):
                raise RuntimeError("Independent native pixel audit did not read the original frame bytes")
        return {"state":"VERIFIED","render_job_id":chunk["job_id"],
                "audit_job_id":op.job_id,
                "audit_sha256":verified["outputs"][AUDIT_JSON]["sha256"],
                "frames":report["frames"],"checks":len(expected_names)}

    def verify_or_audit_batch(self,sequence_id,start_frame):
        seq=self._row(sequence_id)
        if seq["revoked_at"] is not None or time.time()>seq["expires_at"]:
            raise PermissionError("EXR sequence audit must occur under current native approval")
        source,_=self._verify_source(seq)
        plans={a:(b,p) for a,b,p in self._plans(seq,source)}
        if start_frame not in plans:
            raise KeyError("No such approved native EXR frame batch")
        stop,plan=plans[start_frame]
        chunk=self._chunk(sequence_id,start_frame)
        if not chunk or chunk["stop"]!=stop:
            raise RuntimeError("EXR render batch has not been staged")
        task=self.ledger.get_task(self.worker._activity_id(chunk["job_id"]))
        if task is None or task["state"]!="SUCCEEDED":
            raise RuntimeError("Cannot audit EXR batch without verified finished rendering")
        return self._audit_chunk(seq,chunk,plan,source)

    def full_progress(self,sequence_id):
        seq=self._row(sequence_id)
        with self.ledger._db() as db:
            rows=db.execute("""SELECT start_frame,stop_frame,job_id,audit_job_id FROM
                     native_exr_chunk_jobs WHERE sequence_id=? ORDER BY start_frame""",
                     (sequence_id,)).fetchall()
        return {"sequence_id":sequence_id,
                "frames_total":seq["frame_count"],
                "chunks_total":(seq["frame_count"]+seq["chunk_size"]-1)//seq["chunk_size"],
                "chunks_staged":len(rows),
                "chunks_rendered":sum(self.ledger.get_task(self.worker._activity_id(x[2])) is not None and
                                    self.ledger.get_task(self.worker._activity_id(x[2]))["state"]=="SUCCEEDED"
                                    for x in rows),
                "chunks_audited":sum(bool(x[3]) and self.ledger.get_task(
                                    self.worker._activity_id(x[3])) is not None and
                                    self.ledger.get_task(self.worker._activity_id(x[3]))["state"]=="SUCCEEDED"
                                    for x in rows),
                "rendered_video":False}
