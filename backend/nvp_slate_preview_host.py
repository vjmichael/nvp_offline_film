"""SLATE-05 native host: one frozen OpenUSD source -> contained Blender proxy.

Only a trusted installed host may create approvals. Browser/model requests
cannot provide executable Python, native Blender args or a consent receipt.
The existing ApprovedBlenderDispatcher / TaskLedger / resource admission /
BlenderWorkerSupervisor handles launch, cancellation, OS containment, durable
worker receipts and independent output inspection. No new process runner.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import secrets
import shutil
import time

from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_film_index import FilmIndex
from backend.nvp_render_source_stage import _write_exclusive
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_slate_lazy_preview import SlateLazyPreview
from backend.nvp_slate_preview_cache import SlatePreviewCache
from backend.nvp_slate_proxy_recipe import (
    BLENDER_SCRIPT,capture_proxy,recipe,preview_cache_key,
    canonical,sha,DIMENSIONS)

CONSENT_FORMAT="nvp.slate.lowfi_preview_native_consent.v1"
MAX_CONSENT_SECONDS=600
SOURCE_FILE="slate_source_preview.json"
SCRIPT_FILE="trusted_slate_preview.py"
OUTPUT_FILE="preview.png"


def _spec(supervisor,op):
    return {"task_id":supervisor._activity_id(op.job_id),
            "kind":"blender","operation":json.loads(op.canonical())}


def _digest(doc):
    return sha256(canonical_bytes(doc)).hexdigest()


class NativeSlatePreviewHost:
    """Host-authenticated, resource-admitted low-fi proxy PNG render adapter."""

    def __init__(self,index,supervisor,ledger,cache,*,verify_creator_action):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not isinstance(ledger,TaskLedger) or supervisor.activity is not ledger or
            not isinstance(cache,SlatePreviewCache) or
            not callable(verify_creator_action)):
            raise TypeError("Real source FilmIndex, native contained worker, task ledger and trust verifier required")
        self.index=index
        self.supervisor=supervisor
        self.ledger=ledger
        self.cache=cache
        self.lazy=SlateLazyPreview(index)
        self.approve=verify_creator_action
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nvp_slate_preview_consents(
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                edit_id TEXT NOT NULL,
                edit_revision INTEGER NOT NULL,
                film_tick INTEGER NOT NULL,
                quality TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                ticket_sha256 TEXT NOT NULL,
                source_manifest_sha256 TEXT NOT NULL,
                spec_sha256 TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                queued_at REAL
            )""")
        self.dispatcher=ApprovedBlenderDispatcher(
            supervisor,ledger,approval_check=self._approval_check,
            pre_worker_check=self._before_worker)

    def _approval_check(self,approval_id,digest,document):
        if type(approval_id) is not str or not isinstance(document,dict):
            return False
        try:
            with self.ledger._db() as db:
                row=db.execute("""SELECT * FROM nvp_slate_preview_consents
                    WHERE approval_id=?""",(approval_id,)).fetchone()
            if row is None:
                return False
            now=time.time()
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=now<=row["expires_at"] or
                row["spec_sha256"]!=digest or
                _digest(document)!=digest or
                document.get("kind")!="blender" or
                document.get("task_id")!=row["task_id"]):
                return False
            op=BlenderOperation(**document["operation"])
            if (self.supervisor._activity_id(op.job_id)!=row["task_id"] or
                op.script!=SCRIPT_FILE or
                op.script_sha256!=sha(BLENDER_SCRIPT.encode("utf-8")) or
                op.inputs!={SOURCE_FILE:row["source_manifest_sha256"]} or
                op.outputs!={OUTPUT_FILE:"png"} or
                op.arguments!={"--manifest":SOURCE_FILE,"--preview":OUTPUT_FILE} or
                op.scene is not None or op.gpu_memory_mb!=0):
                return False
            ticket=self.lazy.select(
                row["project_id"],row["edit_id"],row["edit_revision"],
                film_tick=row["film_tick"],quality=row["quality"])
            if (sha(canonical(ticket))!=row["ticket_sha256"] or
                preview_cache_key(ticket,row["quality"])!=row["cache_key"]):
                return False
            directory=self.supervisor.root/op.job_id
            if (sha_file(directory/SCRIPT_FILE)!=op.script_sha256 or
                sha_file(directory/SOURCE_FILE)!=row["source_manifest_sha256"]):
                return False
            raw=(directory/SOURCE_FILE).read_bytes()
            if len(raw)>128*1024:
                return False
            source=json.loads(raw)
            if (source.get("source_take_sha256")!=ticket["source_take_document_sha256"] or
                source.get("source_shot_sha256")!=ticket["source_shot_document_sha256"] or
                source.get("source_tick")!=ticket["source_tick"] or
                source.get("cache_key")!=ticket["cache_key"] or
                (source.get("width"),source.get("height"))!=DIMENSIONS[row["quality"]]):
                return False
            pending=self.cache._job(op.job_id)
            if (pending["state"]!="PENDING" or
                pending["cache_key"]!=row["cache_key"] or
                pending["recipe_sha256"]!=row["source_manifest_sha256"]):
                return False
            return True
        except (OSError,KeyError,ValueError,RuntimeError,TypeError,
                PermissionError,IndexError):
            return False

    def _before_worker(self,task_id,document):
        with self.ledger._db() as db:
            row=db.execute("""SELECT approval_id FROM nvp_slate_preview_consents
                WHERE task_id=?""",(task_id,)).fetchone()
        if row is None or not self._approval_check(
                row[0],_digest(document),document):
            raise PermissionError("Low-fi preview source, consent or resource spec changed")

    def request(self,project_id,edit_id,revision,*,film_tick,
                quality="thumbnail",creator_event,ram_mb=1024,
                timeout_seconds=120,strict_linux_cgroup=False):
        """Cache hit or EXPLICITLY approved queued preview, never automatic run."""
        if (type(ram_mb) is not int or not 256<=ram_mb<=8192 or
            type(timeout_seconds) is not int or not 1<=timeout_seconds<=600 or
            type(strict_linux_cgroup) is not bool):
            raise ValueError("Invalid bounded preview worker resources")
        ticket=self.lazy.select(
            project_id,edit_id,revision,film_tick=film_tick,quality=quality)
        if ticket["status"]!="SOURCE_REFERENCE_SELECTED":
            return {"status":ticket["status"],"task_started":False,
                    "source_data_loaded":False,"rendered":False}
        key=preview_cache_key(ticket,quality)
        present=self.cache.lookup(project_id,key)
        if present:
            return {"status":"CACHE_HIT",**present,"new_task_started":False}
        # This source lookup is the expensive path and reads at most ONE
        # OpenUSD source stage, not every Take or entire film timeline.
        snapshot=capture_proxy(self.index,ticket)
        doc=recipe(snapshot,quality)
        doc["source_cache_key"]=key
        raw=canonical(doc)
        if len(raw)>128*1024:
            raise ValueError("Bounded low-fi source proxy recipe exceeded budget")
        if self.cache.lookup(project_id,key):
            return {"status":"CACHE_HIT","cache_key":key,
                    "new_task_started":False}
        job_id="slateprev_"+secrets.token_hex(12)
        jobdir=self.supervisor.root/job_id
        if jobdir.is_symlink():
            raise RuntimeError("Native preview stage escaped workspace")
        jobdir.mkdir(mode=0o700,exist_ok=False)
        try:
            _write_exclusive(jobdir,SCRIPT_FILE,BLENDER_SCRIPT.encode("utf-8"))
            _write_exclusive(jobdir,SOURCE_FILE,raw)
            op=BlenderOperation(
                job_id=job_id,script=SCRIPT_FILE,
                script_sha256=sha(BLENDER_SCRIPT.encode("utf-8")),
                inputs={SOURCE_FILE:sha(raw)},
                outputs={OUTPUT_FILE:"png"},
                arguments={"--manifest":SOURCE_FILE,"--preview":OUTPUT_FILE},
                timeout_seconds=timeout_seconds,memory_limit_mb=ram_mb,
                gpu_memory_mb=0,gpu_device_id=None,
                require_linux_cgroup_v2=strict_linux_cgroup)
            self.supervisor._validate(op)
            exact=_spec(self.supervisor,op)
            spec_sha=_digest(exact)
            context={
                "operation":"nvp.slate.authorize_lowfi_preview.v1",
                "project_id":project_id,"edit_id":edit_id,
                "edit_revision":revision,"edit_document_sha256":
                    ticket["edit_document_sha256"],
                "film_tick":film_tick,"source_tick":ticket["source_tick"],
                "source_take_document_sha256":ticket["source_take_document_sha256"],
                "source_shot_document_sha256":ticket["source_shot_document_sha256"],
                "quality":quality,"preview_cache_key":key,
                "source_recipe_sha256":sha(raw),
                "worker_script_sha256":op.script_sha256,
                "worker_spec_sha256":spec_sha,"job_id":job_id,
                "requested_ram_mb":ram_mb,"requested_gpu_mb":0,
                "output_kind":"lowfi_blocking_proxy_png_not_final_film",
                "final_master_approval":False,
            }
            if self.approve(creator_event,dict(context)) is not True:
                raise PermissionError("Creator did not explicitly authorize source-bound native preview")
            # No unapproved reservation, nor a new worker on a cache hit.
            pending=self.cache.reserve(
                project_id,key,job_id=job_id,
                source_sha256=ticket["source_take_document_sha256"],
                recipe_sha256=sha(raw),
                width=doc["width"],height=doc["height"])
            if pending["status"]!="PENDING":
                return {"status":pending["status"],"cache_key":key,
                        "task_started":False}
            approval_id="slateprevconsent_"+secrets.token_hex(12)
            start=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO nvp_slate_preview_consents(
                    approval_id,task_id,project_id,edit_id,edit_revision,
                    film_tick,quality,cache_key,ticket_sha256,
                    source_manifest_sha256,spec_sha256,issued_at,expires_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (approval_id,exact["task_id"],project_id,edit_id,revision,
                     film_tick,quality,key,sha(canonical(ticket)),sha(raw),
                     spec_sha,start,start+MAX_CONSENT_SECONDS))
                db.commit()
            try:
                queued=self.dispatcher.enqueue(
                    op,approval_id=approval_id,lane="interactive")
            except Exception:
                self.cache.fail(job_id,state="FAILED")
                raise
            with self.ledger._db() as db:
                db.execute("""UPDATE nvp_slate_preview_consents
                    SET queued_at=? WHERE approval_id=?""",
                    (time.time(),approval_id))
            return {
                "status":"QUEUED","task_id":exact["task_id"],
                "job_id":job_id,"approval_id":approval_id,
                "cache_key":key,"source_recipe_sha256":sha(raw),
                "native_worker_started":False,"picture_generated":False,
                "creator_approved_lowfi_preview_only":True,
                "full_feature_render_approved":False,
            }
        except BaseException:
            # Never delete staged inputs after the worker is registered:
            # crash recovery relies on the immutable spec and jobdir.
            with self.ledger._db() as db:
                row=db.execute("""SELECT 1 FROM nvp_slate_preview_consents
                    WHERE task_id=?""",(self.supervisor._activity_id(job_id),)).fetchone()
            if row is None:
                shutil.rmtree(jobdir,ignore_errors=True)
            raise

    def run_next(self):
        """One supervised resource-admitted Blender task; then audit/cache PNG."""
        result=self.dispatcher.run_next()
        if result is None or result.get("admitted") is False:
            return result
        job_id=result.get("id")
        if job_id is None:
            return result
        if result.get("state")=="SUCCEEDED":
            # A completed native audit is necessary but not sufficient:
            # independent PNG hash, dimensions and cache atomic commit follow.
            cached=self.cache.accept_verified(self.supervisor,job_id)
            return {**result,"cache_result":cached}
        if result.get("state") in ("FAILED","CANCELLED","TIMED_OUT"):
            self.cache.fail(job_id,state="FAILED")
        return result

    def cancel(self,job_id,*,creator_event):
        """Cancellation requires separate authenticated user action."""
        row=self.cache._job(job_id)
        ctx={"operation":"nvp.slate.cancel_lowfi_preview.v1",
             "project_id":row["project_id"],"job_id":job_id,
             "preview_cache_key":row["cache_key"]}
        if self.approve(creator_event,dict(ctx)) is not True:
            raise PermissionError("Preview cancellation was not creator-authorized")
        task_id=self.supervisor._activity_id(job_id)
        task=self.ledger.get_task(task_id)
        if task and task["state"]=="QUEUED":
            self.ledger.cancel_queued(task_id,owner_key=self.dispatcher.owner_key)
            self.cache.fail(job_id,state="FAILED")
            return {"job_id":job_id,"state":"CANCELLED_QUEUED",
                    "worker_started":False}
        if self.supervisor.cancel(job_id):
            return {"job_id":job_id,"state":"CANCEL_REQUESTED",
                    "native_termination_verified":False}
        raise RuntimeError("No active or queued preview job can be cancelled")

    def recover(self):
        """After supervisor crash reconciliation, no replay or false success."""
        return self.cache.recover(self.supervisor)
