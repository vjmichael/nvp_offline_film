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
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nvp_camera_preview_consents(
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                scene_id TEXT NOT NULL,
                scene_revision INTEGER NOT NULL,
                scene_document_sha256 TEXT NOT NULL,
                source_tick INTEGER NOT NULL,
                camera_path TEXT NOT NULL,
                quality TEXT NOT NULL,
                settings_json TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                source_manifest_sha256 TEXT NOT NULL,
                spec_sha256 TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL
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
                return self._camera_approval_check(approval_id,digest,document)
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

    def _camera_approval_check(self,approval_id,digest,document):
        """Validate a PRE-TAKE scene, not a counterfeit frozen-Take receipt."""
        try:
            from backend.nvp_camera_workbench import (
                verified_optics,workbench_preview_key)
            with self.ledger._db() as db:
                r=db.execute("""SELECT * FROM nvp_camera_preview_consents
                    WHERE approval_id=?""",(approval_id,)).fetchone()
            if r is None:
                return False
            names=("approval_id","task_id","project_id","scene_id",
                   "scene_revision","scene_document_sha256","source_tick",
                   "camera_path","quality","settings_json","cache_key",
                   "source_manifest_sha256","spec_sha256",
                   "issued_at","expires_at","revoked_at")
            row=dict(zip(names,r))
            if (row["revoked_at"] is not None or
                not row["issued_at"]<=time.time()<=row["expires_at"] or
                row["spec_sha256"]!=digest or _digest(document)!=digest or
                document.get("kind")!="blender" or
                document.get("task_id")!=row["task_id"]):
                return False
            script=_adapter_for("geometry").BLENDER_SCRIPT
            op=BlenderOperation(**document["operation"])
            if (self.supervisor._activity_id(op.job_id)!=row["task_id"] or
                op.script!=SCRIPT_FILE or
                op.script_sha256!=sha(script.encode("utf8")) or
                op.inputs!={SOURCE_FILE:row["source_manifest_sha256"]} or
                op.outputs!={OUTPUT_FILE:"png"} or
                op.arguments!={"--manifest":SOURCE_FILE,"--preview":OUTPUT_FILE} or
                op.scene is not None or op.gpu_memory_mb!=0):
                return False
            scene=self.index.read_revision(
                row["project_id"],row["scene_id"],row["scene_revision"])
            if (scene["kind"]!="scene" or
                scene["document_sha256"]!=row["scene_document_sha256"]):
                return False
            optics=verified_optics(json.loads(row["settings_json"]))
            if workbench_preview_key(
                    scene["document_sha256"],row["source_tick"],
                    row["camera_path"],optics,row["quality"])!=row["cache_key"]:
                return False
            directory=self.supervisor.root/op.job_id
            if (sha_file(directory/SCRIPT_FILE)!=op.script_sha256 or
                sha_file(directory/SOURCE_FILE)!=row["source_manifest_sha256"]):
                return False
            raw=(directory/SOURCE_FILE).read_bytes()
            if len(raw)>128*1024:
                return False
            doc=json.loads(raw)
            if (doc.get("format")!=_adapter_for("geometry").FORMAT or
                doc.get("source_kind")!="pre_take_scene_not_frozen_take" or
                doc.get("source_scene_document_sha256")!=scene["document_sha256"] or
                doc.get("source_scene_id")!=row["scene_id"] or
                doc.get("source_scene_revision")!=row["scene_revision"] or
                doc.get("source_take_sha256") is not None or
                doc.get("source_tick")!=row["source_tick"] or
                doc.get("camera",{}).get("path")!=row["camera_path"] or
                doc.get("source_cache_key")!=row["cache_key"] or
                doc.get("optical_settings")!=optics or
                doc.get("worker_script_sha256")!=op.script_sha256 or
                doc.get("final_presentation_approved") is not False):
                return False
            pending=self.cache._job(op.job_id)
            if (pending["state"]!="PENDING" or
                pending["cache_key"]!=row["cache_key"] or
                pending["source_sha256"]!=scene["document_sha256"] or
                pending["recipe_sha256"]!=row["source_manifest_sha256"]):
                return False
            return True
        except (OSError,KeyError,ValueError,RuntimeError,TypeError,
                PermissionError,IndexError,AttributeError):
            return False

    def _before_worker(self,task_id,document):
        with self.ledger._db() as db:
            row=db.execute("""SELECT approval_id FROM nvp_slate_preview_consents
                WHERE task_id=?""",(task_id,)).fetchone()
            if row is None:
                row=db.execute("""SELECT approval_id FROM nvp_camera_preview_consents
                    WHERE task_id=?""",(task_id,)).fetchone()
        if row is None or not self._approval_check(
                row[0],_digest(document),document):
            raise PermissionError("Native source preview, consent or resource spec changed")

    def source_camera_choices(self,project_id,edit_id,revision,*,film_tick):
        """Fast UI camera-picker data: no USD stage or image generation."""
        ticket=self.lazy.select(
            project_id,edit_id,revision,film_tick=film_tick,
            quality="thumbnail")
        if ticket["status"]!="SOURCE_REFERENCE_SELECTED":
            return {"status":ticket["status"],"cameras":[],"usd_loaded":False}
        take=self.index.read_revision(
            project_id,ticket["source_take_id"],ticket["source_take_revision"])
        scene=self.index.read_revision(
            project_id,take["data"]["scene_id"],take["data"]["scene_revision"])
        if scene["document_sha256"]!=take["data"]["scene_document_sha256"]:
            raise RuntimeError("Native camera list references modified film source")
        if scene["data"].get("native_schema_version") is None:
            return {
                "status":"NATIVE_CAMERAS_NOT_AUTHORED","cameras":[],
                "source_take_sha256":ticket["source_take_document_sha256"],
                "usd_loaded":False,"picture_generated":False,
            }
        cameras=[
            {"path":path,"label":path.rsplit("/",1)[-1]}
            for path,role in sorted(scene["data"]["prim_roles"].items())
            if role=="camera"]
        return {
            "status":"SOURCE_CAMERA_CHOICES",
            "cameras":cameras,
            "source_take_sha256":ticket["source_take_document_sha256"],
            "source_shot_sha256":ticket["source_shot_document_sha256"],
            "source_tick":ticket["source_tick"],
            "usd_loaded":False,"picture_generated":False,
            "shot_visibility_verified":False,
        }

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

    def request_camera_workbench(self,project_id,scene_id,scene_revision,*,
                                 source_tick,camera_path,settings,
                                 quality="interactive",creator_event,
                                 ram_mb=2048,timeout_seconds=180,
                                 strict_linux_cgroup=False):
        """Native preview of one authored SCENE before ANY Take is frozen.

        A cache hit needs neither scene load nor creator authorization. A
        miss stages the SAME first-party Cycles worker as SLATE-06, with
        distinct scene+optics consent, and one immutable FilmIndex scene.
        """
        from backend.nvp_camera_workbench import (
            verified_optics,workbench_preview_key,capture_workbench_still)
        from backend.nvp_film_index import _require_pid,_id
        from backend.nvp_temporal_ledger import _int
        _require_pid(project_id)
        _id(scene_id,"workbench scene")
        _int(scene_revision,"source scene revision",minimum=1)
        _int(source_tick,"source time",maximum=2**53-1)
        if (type(ram_mb) is not int or not 256<=ram_mb<=8192 or
            type(timeout_seconds) is not int or not 1<=timeout_seconds<=600 or
            type(strict_linux_cgroup) is not bool):
            raise ValueError("Invalid native workbench resource budget")
        settings=verified_optics(settings)
        source=self.index.read_revision(project_id,scene_id,scene_revision)
        if source["kind"]!="scene":
            raise RuntimeError("Only original authored native scene is previewable")
        key=workbench_preview_key(
            source["document_sha256"],source_tick,
            camera_path,settings,quality)
        cached=self.cache.lookup(project_id,key)
        if cached:
            return {**cached,"status":"CACHE_HIT",
                    "presentation":"pre_take_camera",
                    "source_scene_document_sha256":source["document_sha256"],
                    "source_data_modified":False,"new_task_started":False}
        doc=capture_workbench_still(
            self.index,project_id,scene_id,scene_revision,
            tick=source_tick,camera_path=camera_path,
            settings=settings,quality=quality)
        if doc["source_scene_document_sha256"]!=source["document_sha256"]:
            raise RuntimeError("Pre-Take scene changed before authored lens preview")
        doc["source_cache_key"]=key
        raw=canonical(doc)
        if len(raw)>128*1024:
            raise RuntimeError("Pre-Take source optics exceeded trusted worker manifest limit")
        job_id="nvp_cam_"+secrets.token_hex(12)
        jobdir=self.supervisor.root/job_id
        jobdir.mkdir(mode=0o700,exist_ok=False)
        try:
            from backend.nvp_slate06_geometry import BLENDER_SCRIPT
            script=BLENDER_SCRIPT.encode("utf8")
            _write_exclusive(jobdir,SCRIPT_FILE,script)
            _write_exclusive(jobdir,SOURCE_FILE,raw)
            op=BlenderOperation(
                job_id=job_id,script=SCRIPT_FILE,
                script_sha256=sha(script),
                inputs={SOURCE_FILE:sha(raw)},
                outputs={OUTPUT_FILE:"png"},
                arguments={"--manifest":SOURCE_FILE,"--preview":OUTPUT_FILE},
                timeout_seconds=timeout_seconds,memory_limit_mb=ram_mb,
                gpu_memory_mb=0,gpu_device_id=None,
                require_linux_cgroup_v2=strict_linux_cgroup)
            self.supervisor._validate(op)
            spec=_spec(self.supervisor,op)
            spec_sha=_digest(spec)
            context={
                "operation":"nvp.camera.authorize_pre_take_still.v1",
                "project_id":project_id,
                "scene_id":scene_id,"scene_revision":scene_revision,
                "scene_document_sha256":source["document_sha256"],
                "source_tick":source_tick,"camera_path":camera_path,
                "optical_settings_sha256":sha(canonical(settings)),
                "preview_cache_key":key,
                "source_manifest_sha256":sha(raw),
                "worker_script_sha256":sha(script),
                "worker_spec_sha256":spec_sha,
                "job_id":job_id,
                "requested_ram_mb":ram_mb,
                "output_kind":"pre_take_native_optics_png_not_frozen_take",
                "frozen_take_created":False,"film_master_approved":False,
            }
            if self.approve(creator_event,dict(context)) is not True:
                raise PermissionError("Director did not authorize source-scoped pre-Take preview")
            reserved=self.cache.reserve(
                project_id,key,job_id=job_id,
                source_sha256=source["document_sha256"],
                recipe_sha256=sha(raw),
                width=doc["width"],height=doc["height"])
            if reserved["status"]!="PENDING":
                shutil.rmtree(jobdir)
                return {"status":reserved["status"],"cache_key":key,
                        "presentation":"pre_take_camera",
                        "new_task_started":False}
            approval_id="cam_preview_"+secrets.token_hex(12)
            now=time.time()
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO nvp_camera_preview_consents(
                    approval_id,task_id,project_id,scene_id,scene_revision,
                    scene_document_sha256,source_tick,camera_path,quality,
                    settings_json,cache_key,source_manifest_sha256,
                    spec_sha256,issued_at,expires_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (approval_id,spec["task_id"],project_id,
                     scene_id,scene_revision,source["document_sha256"],
                     source_tick,camera_path,quality,
                     json.dumps(settings,sort_keys=True,separators=(",",":")),
                     key,sha(raw),spec_sha,now,now+600))
                db.commit()
            try:
                self.dispatcher.enqueue(
                    op,approval_id=approval_id,lane="interactive")
            except Exception:
                self.cache.fail(job_id,state="FAILED")
                raise
            return {
                "status":"QUEUED",
                "presentation":"pre_take_camera",
                "job_id":job_id,"task_id":spec["task_id"],
                "cache_key":key,"approval_id":approval_id,
                "source_scene_document_sha256":source["document_sha256"],
                "frozen_take_created":False,
                "source_scene_modified":False,
                "picture_generated":False,
                "film_master_approved":False,
            }
        except BaseException:
            with self.ledger._db() as db:
                consent=db.execute("""SELECT 1 FROM nvp_camera_preview_consents
                    WHERE task_id=?""",
                    (self.supervisor._activity_id(job_id),)).fetchone()
            if consent is None:
                shutil.rmtree(jobdir,ignore_errors=True)
            raise

    def read_camera_workbench_png(self,project_id,cache_key):
        """Only the approved pre-Take preview can return a scene-optical PNG."""
        result=self.cache.lookup(project_id,cache_key)
        if result is None:
            raise KeyError("No verified director camera still is ready")
        task_id=self.supervisor._activity_id(result["job_id"])
        with self.ledger._db() as db:
            row=db.execute("""SELECT scene_id,scene_revision,
                scene_document_sha256,source_tick,camera_path,settings_json,
                source_manifest_sha256 FROM nvp_camera_preview_consents
                WHERE project_id=? AND cache_key=? AND task_id=?""",
                (project_id,cache_key,task_id)).fetchone()
        if row is None:
            raise RuntimeError("Preview cache lacks its original pre-Take consent")
        scene=self.index.read_revision(project_id,row[0],row[1])
        from backend.nvp_camera_workbench import (
            verified_optics,workbench_preview_key)
        optics=verified_optics(json.loads(row[5]))
        if (scene["document_sha256"]!=row[2] or
            workbench_preview_key(row[2],row[3],row[4],optics,
                 "thumbnail" if (result["width"],result["height"])==(320,180)
                 else "interactive" if (result["width"],result["height"])==(640,360)
                 else "inspection")!=cache_key):
            raise RuntimeError("Original scene or lens identity changed after rendering")
        source=self.supervisor.root/result["job_id"]/SOURCE_FILE
        if source.is_symlink() or not source.is_file() or (
                sha_file(source)!=row[6]):
            raise RuntimeError("Original lens manifest differs from approved recipe")
        from backend.nvp_slate_preview_cache import MAX_IMAGE_BYTES
        image=Path(result["png_path"]).read_bytes()
        if len(image)>MAX_IMAGE_BYTES or sha(image)!=result["image_sha256"]:
            raise RuntimeError("Published pre-Take optics PNG failed independent verification")
        return {
            "format":"nvp.camera.pre_take_preview_delivery.v1",
            "presentation":"pre_take_camera",
            "scene_id":row[0],"scene_revision":row[1],
            "scene_document_sha256":row[2],
            "source_tick":row[3],"camera_path":row[4],
            "lens_settings":optics,
            "png_bytes":image,"mime_type":"image/png",
            "image_sha256":result["image_sha256"],
            "width":result["width"],"height":result["height"],
            "source_scene_modified":False,
            "frozen_take_created":False,
            "film_master_approved":False,
        }

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
                with self.ledger._db() as db:
                    live=db.execute("""SELECT camera_path FROM nvp_camera_preview_consents
                        WHERE task_id=?""",
                        (self.supervisor._activity_id(job_id),)).fetchone()
                if live is None:
                    raise RuntimeError("Verified native preview lost approval provenance")
                return {**result,"cache_result":{
                    **cached,"presentation":"pre_take_camera",
                    "camera_path":live[0],
                    "frozen_take_created":False,
                    "final_master_approval":False}}
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
            row=db.execute("""SELECT presentation,camera_path,
                edit_id,edit_revision,film_tick,quality,ticket_sha256,
                source_manifest_sha256
                FROM nvp_slate_preview_consents WHERE task_id=?""",
                (self.supervisor._activity_id(result["job_id"]),)).fetchone()
        if row is None or row[0] not in ("blocking","geometry"):
            raise RuntimeError("Cached derivative lost its source-renderer provenance")
        mode,camera,edit_id,revision,film_tick,quality,ticket_sha,manifest_sha=row
        ticket=self.lazy.select(
            project_id,edit_id,revision,film_tick=film_tick,quality=quality)
        if (ticket["status"]!="SOURCE_REFERENCE_SELECTED" or
            sha(canonical(ticket))!=ticket_sha):
            raise RuntimeError("Cached derivative no longer matches original editor source")
        from backend.nvp_slate06_geometry import MAX_SOURCE_BYTES
        original=self.supervisor.root/result["job_id"]/SOURCE_FILE
        if original.is_symlink() or not original.is_file() or (
                original.stat().st_size>MAX_SOURCE_BYTES):
            raise RuntimeError("Verified preview source recipe is absent or unbounded")
        source_raw=original.read_bytes()
        if sha(source_raw)!=manifest_sha:
            raise RuntimeError("Verified preview fidelity manifest changed")
        source=json.loads(source_raw)
        adapter=_adapter_for(mode)
        if (source.get("format")!=adapter.FORMAT or
            source.get("source_cache_key")!=cache_key or
            source.get("source_take_sha256")!=ticket["source_take_document_sha256"] or
            source.get("source_shot_sha256")!=ticket["source_shot_document_sha256"] or
            source.get("source_tick")!=ticket["source_tick"] or
            (source.get("width"),source.get("height"))!=(
                result["width"],result["height"])):
            raise RuntimeError("Published PNG and source fidelity contract disagree")
        return {
            "format":"nvp.slate.preview_native_delivery.v1",
            "cache_key":cache_key,"project_id":project_id,
            "mime_type":"image/png","png_bytes":data,
            "image_sha256":result["image_sha256"],
            "width":result["width"],"height":result["height"],
            "edit_document_sha256":ticket["edit_document_sha256"],
            "segment_id":ticket["segment_id"],
            "source_take_sha256":ticket["source_take_document_sha256"],
            "source_shot_sha256":ticket["source_shot_document_sha256"],
            "source_tick":ticket["source_tick"],
            "presentation":mode,"camera_path":camera,
            "unmeshed_actors":source.get("unmeshed_actors",[]),
            "skeletal_rig_count":source.get("skeletal_rig_count",0),
            "lowfi_proxy_only":mode=="blocking",
            "authored_geometry_preview_only":mode=="geometry",
            "usd_material_networks_evaluated":False,
            "usd_light_photometry_exact":False,
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
            with self.ledger._db() as db:
                camera=db.execute("""SELECT scene_id FROM nvp_camera_preview_consents
                    WHERE task_id=?""",
                    (self.supervisor._activity_id(job_id),)).fetchone()
            if camera is None:
                raise RuntimeError("Preview cancellation source provenance missing")
            ctx={
                "operation":"nvp.camera.cancel_pre_take_still.v1",
                "project_id":row["project_id"],
                "scene_id":camera[0],
                "job_id":job_id,"preview_cache_key":row["cache_key"],
            }
            if self.approve(creator_event,dict(ctx)) is not True:
                raise PermissionError("Pre-Take render cancellation was not authorized")
            task_id=self.supervisor._activity_id(job_id)
            task=self.ledger.get_task(task_id)
            if task and task["state"]=="QUEUED":
                self.ledger.cancel_queued(task_id,owner_key=self.dispatcher.owner_key)
                self.cache.fail(job_id,state="FAILED")
                return {"job_id":job_id,"state":"CANCELLED_QUEUED",
                        "native_worker_started":False}
            if self.supervisor.cancel(job_id):
                return {"job_id":job_id,"state":"CANCEL_REQUESTED",
                        "native_termination_verified":False}
            raise RuntimeError("No active pre-Take still can be cancelled")
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
