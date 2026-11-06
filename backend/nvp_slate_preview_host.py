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


def _adapter_for(presentation):
    """Only two explicit NVP-owned signed recipes use ONE native supervisor."""
    if presentation=="blocking":
        from backend import nvp_slate_proxy_recipe as module
        return module
    if presentation=="geometry":
        from backend import nvp_slate06_geometry as module
        return module
    raise ValueError("Unknown trusted OpenUSD presentation mode")


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
                queued_at REAL,
                presentation TEXT NOT NULL DEFAULT 'blocking',
                camera_path TEXT
            )""")
            # Upgrade existing installs without invalidating earlier
            # blocked/queued SLATE-05 native consent records.
            cols={x[1] for x in db.execute(
                "PRAGMA table_info(nvp_slate_preview_consents)")}
            if "presentation" not in cols:
                db.execute("""ALTER TABLE nvp_slate_preview_consents
                    ADD COLUMN presentation TEXT NOT NULL DEFAULT 'blocking'""")
            if "camera_path" not in cols:
                db.execute("""ALTER TABLE nvp_slate_preview_consents
                    ADD COLUMN camera_path TEXT""")
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
            # TaskLedger deliberately yields tuples, not sqlite3.Row.
            names=("approval_id","task_id","project_id","edit_id",
                   "edit_revision","film_tick","quality","cache_key",
                   "ticket_sha256","source_manifest_sha256","spec_sha256",
                   "issued_at","expires_at","revoked_at","queued_at",
                   "presentation","camera_path")
            row=dict(zip(names,row))
            now=time.time()
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=now<=row["expires_at"] or
                row["spec_sha256"]!=digest or
                _digest(document)!=digest or
                document.get("kind")!="blender" or
                document.get("task_id")!=row["task_id"]):
                return False
            adapter=_adapter_for(row["presentation"])
            script=adapter.BLENDER_SCRIPT
            op=BlenderOperation(**document["operation"])
            if (self.supervisor._activity_id(op.job_id)!=row["task_id"] or
                op.script!=SCRIPT_FILE or
                op.script_sha256!=sha(script.encode("utf-8")) or
                op.inputs!={SOURCE_FILE:row["source_manifest_sha256"]} or
                op.outputs!={OUTPUT_FILE:"png"} or
                op.arguments!={"--manifest":SOURCE_FILE,"--preview":OUTPUT_FILE} or
                op.scene is not None or op.gpu_memory_mb!=0):
                return False
            ticket=self.lazy.select(
                row["project_id"],row["edit_id"],row["edit_revision"],
                film_tick=row["film_tick"],quality=row["quality"])
            expected_key=(
                adapter.preview_cache_key(
                    ticket,row["quality"],camera_path=row["camera_path"])
                if row["presentation"]=="geometry" else
                adapter.preview_cache_key(ticket,row["quality"]))
            if (sha(canonical(ticket))!=row["ticket_sha256"] or
                expected_key!=row["cache_key"]):
                return False
            directory=self.supervisor.root/op.job_id
            if (sha_file(directory/SCRIPT_FILE)!=op.script_sha256 or
                sha_file(directory/SOURCE_FILE)!=row["source_manifest_sha256"]):
                return False
            raw=(directory/SOURCE_FILE).read_bytes()
            if len(raw)>128*1024:
                return False
            source=json.loads(raw)
            if (source.get("format")!=adapter.FORMAT or
                source.get("renderer_version")!=adapter.RENDERER_VERSION or
                source.get("worker_script_sha256")!=op.script_sha256 or
                source.get("source_cache_key")!=row["cache_key"] or
                source.get("source_take_sha256")!=ticket["source_take_document_sha256"] or
                source.get("source_shot_sha256")!=ticket["source_shot_document_sha256"] or
                source.get("source_tick")!=ticket["source_tick"] or
                source.get("cache_key")!=ticket["cache_key"] or
                (source.get("width"),source.get("height"))!=adapter.DIMENSIONS[row["quality"]]):
                return False
            if row["presentation"]=="geometry" and (
                source.get("camera",{}).get("path")!=(
                    row["camera_path"] or source.get("camera",{}).get("path")) or
                source.get("final_presentation_approved") is not False):
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
                timeout_seconds=120,strict_linux_cgroup=False,
                presentation="blocking",camera_path=None):
        """Cache hit or EXPLICITLY approved queued preview, never automatic run."""
        if (type(ram_mb) is not int or not 256<=ram_mb<=8192 or
            type(timeout_seconds) is not int or not 1<=timeout_seconds<=600 or
            type(strict_linux_cgroup) is not bool):
            raise ValueError("Invalid bounded preview worker resources")
        adapter=_adapter_for(presentation)
        if presentation=="blocking" and camera_path is not None:
            raise ValueError("Only native geometry previews select a camera")
        if camera_path is not None and (
            type(camera_path) is not str or
            not camera_path.startswith("/World/") or len(camera_path)>240):
            raise ValueError("Invalid source-native camera identity")
        ticket=self.lazy.select(
            project_id,edit_id,revision,film_tick=film_tick,quality=quality)
        if ticket["status"]!="SOURCE_REFERENCE_SELECTED":
            return {"status":ticket["status"],"task_started":False,
                    "source_data_loaded":False,"rendered":False}
        key=(adapter.preview_cache_key(ticket,quality,camera_path=camera_path)
             if presentation=="geometry" else
             adapter.preview_cache_key(ticket,quality))
        present=self.cache.lookup(project_id,key)
        if present:
            return {"status":"CACHE_HIT",**present,
                    "presentation":presentation,"new_task_started":False}
        # One exact source stage on a miss. Geometry has no silent fallback
        # into the less faithful SLATE-05 blocking proxy recipe.
        snapshot=(adapter.capture_geometry(
                    self.index,ticket,camera_path=camera_path)
                  if presentation=="geometry" else
                  adapter.capture_proxy(self.index,ticket))
        doc=adapter.recipe(snapshot,quality)
        doc["source_cache_key"]=key
        raw=canonical(doc)
        if len(raw)>128*1024:
            raise ValueError("Bounded low-fi source proxy recipe exceeded budget")
        if self.cache.lookup(project_id,key):
            return {"status":"CACHE_HIT","cache_key":key,
                    "presentation":presentation,"new_task_started":False}
        job_id="slateprev_"+secrets.token_hex(12)
        jobdir=self.supervisor.root/job_id
        if jobdir.is_symlink():
            raise RuntimeError("Native preview stage escaped workspace")
        jobdir.mkdir(mode=0o700,exist_ok=False)
        try:
            fixed_script=adapter.BLENDER_SCRIPT.encode("utf-8")
            _write_exclusive(jobdir,SCRIPT_FILE,fixed_script)
            _write_exclusive(jobdir,SOURCE_FILE,raw)
            op=BlenderOperation(
                job_id=job_id,script=SCRIPT_FILE,
                script_sha256=sha(fixed_script),
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
                "operation":(
                    "nvp.slate.authorize_openusd_geometry_preview.v1"
                    if presentation=="geometry"
                    else "nvp.slate.authorize_lowfi_preview.v1"),
                "presentation":presentation,
                "camera_path":camera_path,
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
                "output_kind":(
                    "native_openusd_geometry_preview_not_actor_skinning_or_master"
                    if presentation=="geometry" else
                    "lowfi_blocking_proxy_png_not_final_film"),
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
                # Concurrent requests can race for the same source preview.
                # The losing request has no authorization/registered worker,
                # so discard ONLY its inert temporary staging directory.
                shutil.rmtree(jobdir)
                return {"status":pending["status"],"cache_key":key,
                        "presentation":presentation,"task_started":False}
            approval_id="slateprevconsent_"+secrets.token_hex(12)
            start=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO nvp_slate_preview_consents(
                    approval_id,task_id,project_id,edit_id,edit_revision,
                    film_tick,quality,cache_key,ticket_sha256,
                    source_manifest_sha256,spec_sha256,issued_at,expires_at,
                    presentation,camera_path)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (approval_id,exact["task_id"],project_id,edit_id,revision,
                     film_tick,quality,key,sha(canonical(ticket)),sha(raw),
                     spec_sha,start,start+MAX_CONSENT_SECONDS,
                     presentation,camera_path))
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
                "presentation":presentation,"camera_path":camera_path,
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
            with self.ledger._db() as db:
                record=db.execute("""SELECT presentation,camera_path
                    FROM nvp_slate_preview_consents
                    WHERE task_id=?""",
                    (self.supervisor._activity_id(job_id),)).fetchone()
            if record is None:
                raise RuntimeError("Verified native preview lost approval provenance")
            return {**result,"cache_result":{
                **cached,"presentation":record[0],
                "camera_path":record[1],
                "full_character_performance_rendered":False,
                "final_master_approval":False}}
        if result.get("state") in ("FAILED","CANCELLED","TIMED_OUT"):
            self.cache.fail(job_id,state="FAILED")
        return result

    def read_preview_png(self,project_id,cache_key):
        """Trusted desktop bridge reads exactly ONE verified derived PNG.

        The browser must not receive an arbitrary worker file path. Native
        IPC can convert returned PNG bytes to a bounded media object/URL.
        This is image retrieval, not publication or original source editing.
        """
        from backend.nvp_slate_preview_cache import MAX_IMAGE_BYTES
        result=self.cache.lookup(project_id,cache_key)
        if result is None:
            raise KeyError("No independently accepted cached proxy preview")
        file=Path(result["png_path"])
        with file.open("rb") as handle:
            data=handle.read(MAX_IMAGE_BYTES+1)
        if (not data or len(data)>MAX_IMAGE_BYTES or
            sha(data)!=result["image_sha256"]):
            raise RuntimeError("Selected cached PNG changed before native delivery")
        with self.ledger._db() as db:
            row=db.execute("""SELECT presentation,camera_path
                FROM nvp_slate_preview_consents WHERE task_id=?""",
                (self.supervisor._activity_id(result["job_id"]),)).fetchone()
        if row is None or row[0] not in ("blocking","geometry"):
            raise RuntimeError("Cached derivative lost its source-renderer provenance")
        return {
            "format":"nvp.slate.preview_native_delivery.v1",
            "cache_key":cache_key,"project_id":project_id,
            "mime_type":"image/png","png_bytes":data,
            "image_sha256":result["image_sha256"],
            "width":result["width"],"height":result["height"],
            "presentation":row[0],"camera_path":row[1],
            "lowfi_proxy_only":row[0]=="blocking",
            "authored_geometry_preview_only":row[0]=="geometry",
            "skinned_actor_performance_rendered":False,
            "full_film_frame_approved":False,
        }

    def cancel(self,job_id,*,creator_event):
        """Cancellation requires separate authenticated user action."""
        row=self.cache._job(job_id)
        with self.ledger._db() as db:
            consent=db.execute("""SELECT presentation
                FROM nvp_slate_preview_consents WHERE task_id=?""",
                (self.supervisor._activity_id(job_id),)).fetchone()
        if consent is None:
            raise RuntimeError("Preview cancellation source provenance missing")
        ctx={"operation":(
                 "nvp.slate.cancel_openusd_geometry_preview.v1"
                 if consent[0]=="geometry" else
                 "nvp.slate.cancel_lowfi_preview.v1"),
             "presentation":consent[0],
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
        """Independently reconcile worker jobs before any cache publication.

        A QUEUED pre-crash preview is cancelled instead of silently restarted.
        An ACTIVE task's RAM reservation stays for separate host recovery if
        native worker termination cannot be proven.
        """
        if self.supervisor._running:
            raise RuntimeError("Cannot recover while this host owns live preview jobs")
        interrupted=self.supervisor.recover_interrupted()
        results=self.cache.recover(self.supervisor)
        for item in results:
            if item["state"]!="INTERRUPTED":
                continue
            task_id=self.supervisor._activity_id(item["job_id"])
            row=self.ledger.get_task(task_id)
            if row is not None and row["state"]=="QUEUED":
                self.ledger.cancel_queued(
                    task_id,owner_key=self.dispatcher.owner_key)
                item["queued_native_task_cancelled"]=True
        return {
            "native_worker_interrupted_job_ids":interrupted,
            "preview_cache_reconciliation":results,
            "native_jobs_replayed":False,
            "unproven_active_reservations_released":False,
        }
