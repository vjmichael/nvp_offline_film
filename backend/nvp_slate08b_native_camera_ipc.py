"""SLATE-08B: real desktop-only opt-in camera render and delivery bridge.

This object is exposed ONLY via pywebview js_api, never as a FastAPI route.
A browser request is untrusted. The native OS window asks the human to
approve an exact pinned render or cancellation; grants are single-use,
scope-checked in NativeSlatePreviewHost and never passed by JavaScript.

Render execution uses the existing supervised Blender dispatcher and cache.
No new subprocess launcher, file-system path API or arbitrary worker script.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from backend.nvp_camera_workbench import verified_optics, workbench_preview_key
from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_slate_proxy_recipe import canonical
from backend.nvp_slate_preview_cache import MAX_IMAGE_BYTES


@dataclass(frozen=True)
class _NativeGrant:
    token: str


def discover_blender():
    """Find native Blender from trusted host/installed paths, never JS input.

    Windows Blender installers do not normally add blender.exe to PATH.
    Support a verified portable executable beside the installed NVP bundle
    as well as normal Windows Blender Foundation installations. SHA pinning
    and a real version probe are still enforced by build_desktop_camera_host.
    """
    configured = os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE")
    paths=[]
    if configured:
        paths.append(Path(configured))
    if getattr(sys, "frozen", False):
        root=Path(getattr(sys, "_MEIPASS",Path(sys.executable).parent))
        paths.append(root/"blender"/"blender.exe")
        paths.append(Path(sys.executable).parent/"blender"/"blender.exe")
    if os.name=="nt":
        for prefix in (os.environ.get("PROGRAMFILES"),
                       os.environ.get("PROGRAMW6432")):
            if prefix:
                # Finite, expected first-party layout only; no recursive
                # search of user-controlled project directories or drives.
                base=Path(prefix)/"Blender Foundation"
                if base.is_dir() and not base.is_symlink():
                    paths.extend(sorted(base.glob("Blender */blender.exe"),
                                        reverse=True)[:12])
    found=shutil.which("blender")
    if found:
        paths.append(Path(found))
    for candidate in paths:
        if candidate.is_symlink() or not candidate.is_file():
            continue
        resolved=candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


def build_desktop_camera_host(index, callback):
    """Create/recover established host under NVP's own per-user runtime."""
    from backend.nvp_blender_worker import BlenderWorkerSupervisor, sha_file
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_slate_preview_cache import SlatePreviewCache
    from backend.nvp_slate_preview_host import NativeSlatePreviewHost

    blender = discover_blender()
    if blender is None:
        raise RuntimeError("Native Blender unavailable. Install a trusted Blender binary to render stills.")
    try:
        info = subprocess.run(
            [str(blender), "-b", "--version"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, text=True, timeout=15,
        )
        first = info.stdout.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError) as error:
        raise RuntimeError("Native Blender version probe failed") from error
    if not first.startswith("Blender "):
        raise RuntimeError("Selected executable did not report a real Blender version")
    home = Path(os.environ["NVP_HOME"]).resolve() / ".native-camera-runtime"
    if home.is_symlink():
        raise RuntimeError("Native camera runtime cannot be symlinked")
    home.mkdir(parents=True, exist_ok=True)
    ledger = TaskLedger(home / "tasks")
    worker = BlenderWorkerSupervisor(
        home / "workers", blender_executable=blender,
        blender_sha256=sha_file(blender),
        blender_version=first, activity_ledger=ledger)
    cache = SlatePreviewCache(home / "preview-cache")
    host = NativeSlatePreviewHost(
        index, worker, ledger, cache, verify_creator_action=callback)
    # Unproven workers/queued jobs are never silently relaunched or accepted.
    host.recover()
    return host


class TrustedDesktopCameraBridge:
    """Per-WebView native authority. No browser can self-sign an approval."""

    def __init__(self, index: FilmIndex, *, origin, host_factory=None):
        if not isinstance(index, FilmIndex):
            raise TypeError("Actual native FilmIndex required")
        parsed = urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.port is None or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment or parsed.username):
            raise ValueError("Desktop IPC only accepts its own exact loopback origin")
        self.origin = "http://127.0.0.1:" + str(parsed.port)
        self.index = index
        self.window = None
        self._lock = threading.RLock()
        self._grants = {}
        self._tickets = {}
        self._futures = {}
        self._host = None
        self._data_av_controller = None
        self._live_sound_session = None
        self._live_sound_ticket = None
        self._closing = False
        self._host_factory = host_factory or (
            lambda callback: build_desktop_camera_host(index, callback))
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="NVP verified preview")

    def _attach_window(self, window):
        if window is None or not callable(getattr(window,"get_current_url",None))                 or not callable(getattr(window,"create_confirmation_dialog",None)):
            raise TypeError("A real native window with OS confirmation is required")
        if self.window is not None:
            raise RuntimeError("Desktop camera window already attached")
        self.window=window

    def _native_window(self):
        if self._closing:
            raise PermissionError("Desktop camera bridge is shutting down")
        if self.window is None:
            raise PermissionError("No native desktop window attached")
        current=self.window.get_current_url()
        if type(current) is not str:
            raise PermissionError("Desktop origin cannot be verified")
        parsed=urlsplit(current)
        if (parsed.scheme!="http" or parsed.netloc != self.origin.removeprefix("http://")
                or parsed.path!="/" or parsed.query or parsed.fragment):
            raise PermissionError("Native camera IPC refused non-NVP window origin")
        return self.window

    def _ask(self, message):
        return self._native_window().create_confirmation_dialog(
            "NVP — Authorize Native Camera", message) is True

    def _grant(self, exact):
        token=secrets.token_urlsafe(24)
        self._grants[token]=(dict(exact),time.monotonic()+60)
        return _NativeGrant(token)

    def _approve(self, event, context):
        """Consumed by the ORIGINAL NativeSlatePreviewHost authorization gate."""
        if type(event) is not _NativeGrant or type(context) is not dict:
            return False
        with self._lock:
            record=self._grants.pop(event.token,None)
            if record is None:
                return False
            exact,expires=record
            return (time.monotonic()<=expires and all(
                context.get(k)==v for k,v in exact.items()))

    def _get_host(self):
        with self._lock:
            if self._host is None:
                self._host=self._host_factory(self._approve)
            return self._host

    def camera_render_capabilities(self):
        # DA-06: external Blender still capture was part of the retired
        # frame/proxy bridge. NVP now auditions 3D USD directly. Never
        # discover or start a legacy media worker from the active editor.
        self._native_window()
        return {
            "format":"nvp.camera.desktop_capability.v1",
            "native_window":True,
            "blender_discovered":False,
            "supports_approved_still":False,
            "supports_cancel":True,
            "native_data_first_scene":True,
            "legacy_render_retired":True,
            "source_modified":False,
        }

    def request_camera_still(self, payload):
        """Retired external proxy renderer. Data-first scene view is native."""
        self._native_window()
        raise PermissionError(
            "External camera still/proxy worker retired by DA-06; use native "
            "OpenUSD WebGL audition without FFmpeg or frame capture.")
        if type(payload) is not dict or set(payload)!={
                "project_id","source_scene_id","source_scene_revision",
                "source_scene_document_sha256","source_tick","camera_path",
                "lens_settings","source_modified","frozen_take_created"}:
            raise ValueError("Camera request must be a strictly typed source identity")
        pid=_require_pid(payload["project_id"])
        scene_id=_id(payload["source_scene_id"],"native camera scene")
        revision=payload["source_scene_revision"]
        tick=payload["source_tick"]
        camera_path=payload["camera_path"]
        if (type(revision) is not int or not 1<=revision<=1000000
                or type(tick) is not int or not 0<=tick<=1000000000
                or payload["source_modified"] is not False
                or payload["frozen_take_created"] is not False
                or type(camera_path) is not str
                or not camera_path.startswith("/World/") or len(camera_path)>240):
            raise ValueError("Invalid or source-modifying native camera command")
        source=self.index.read_revision(pid,scene_id,revision)
        _sha(payload["source_scene_document_sha256"])
        if (source["kind"]!="scene" or
                source["document_sha256"]!=payload["source_scene_document_sha256"]
                or source["data"].get("prim_roles",{}).get(camera_path)!="camera"):
            raise RuntimeError("Exact authored camera scene has changed or is unavailable")
        settings=verified_optics(payload["lens_settings"])
        key=workbench_preview_key(
            source["document_sha256"],tick,camera_path,settings,"interactive")
        exact={
            "operation":"nvp.camera.authorize_pre_take_still.v1",
            "project_id":pid,"scene_id":scene_id,"scene_revision":revision,
            "scene_document_sha256":source["document_sha256"],
            "source_tick":tick,"camera_path":camera_path,
            "optical_settings_sha256":sha256(canonical(settings)).hexdigest(),
            "preview_cache_key":key,
        }
        # The native user sees the actual source and optics, not generic "Allow".
        message=(
            "Render ONE source-backed Blender Cycles still?\n"
            f"Film: {pid[:8]} · Scene: {scene_id} rev {revision}\n"
            f"Camera: {camera_path} · Film Time: {tick}\n"
            f"{settings['focal_length_mm']} mm, f/{settings['f_stop']}, "
            f"focus {settings['focus_distance_m']} m\n"
            "CPU-only 640×360 preview · bounded resource admission.\n"
            "No original scene, Take, or film master will be changed."
        )
        # Explicit native confirmation must precede renderer request/worker.
        if not self._ask(message):
            return {"status":"DENIED","native_worker_started":False}
        with self._lock:
            grant=self._grant(exact)
            try:
                host=self._get_host()
                result=host.request_camera_workbench(
                    pid,scene_id,revision,source_tick=tick,
                    camera_path=camera_path,settings=settings,
                    quality="interactive",creator_event=grant,
                    ram_mb=2048,timeout_seconds=180)
            finally:
                self._grants.pop(grant.token,None)
            if result["status"] not in ("QUEUED","CACHE_HIT"):
                raise RuntimeError("Native worker request was not admitted or cache-verified")
            ticket=secrets.token_urlsafe(24)
            self._tickets[ticket]={
                "project_id":pid,"scene_id":scene_id,
                "revision":revision,"scene_sha":source["document_sha256"],
                "source_tick":tick,"camera_path":camera_path,
                "settings":settings,"cache_key":key,
                "job_id":result.get("job_id"),"status":result["status"],
                "last_dispatch_at":time.monotonic(),
            }
            if len(self._tickets)>64:
                # Discard only in-memory GUI tokens; never a native job or source.
                oldest=next(iter(self._tickets))
                self._tickets.pop(oldest,None)
            if result["status"]=="QUEUED":
                self._futures[ticket]=self._executor.submit(host.run_next)
            return {
                "format":"nvp.camera.desktop_ticket.v1",
                "status":result["status"],"ticket_id":ticket,
                "scene_document_sha256":source["document_sha256"],
                "source_tick":tick,"camera_path":camera_path,
                "cache_key":key,"frozen_take_created":False,
                "source_modified":False,
            }

    def poll_camera_still(self, ticket_id):
        self._native_window()
        if type(ticket_id) is not str or len(ticket_id)>128:
            raise ValueError("Invalid native camera ticket")
        with self._lock:
            item=self._tickets.get(ticket_id)
            if item is None:
                raise PermissionError("Camera ticket not issued by this desktop session")
            host=self._get_host()
            result=host.cache.lookup(item["project_id"],item["cache_key"])
            if result is None:
                if item["job_id"] is None:
                    # A cache hit can be evicted/tampered before the UI reads
                    # its media; there is no worker to retry via this ticket.
                    return {"status":"RECOVERY_REQUIRED",
                            "film_master_approved":False}
                row=host.cache._job(item["job_id"])
                if row["state"] in ("FAILED","INTERRUPTED","EVICTED"):
                    return {"status":"FAILED","film_master_approved":False}
                if row["state"]=="READY":
                    # A READY record whose physical PNG is not independently
                    # re-readable is not a completed picture.
                    return {"status":"RECOVERY_REQUIRED",
                            "film_master_approved":False}
                future=self._futures.get(ticket_id)
                if future is not None and future.done():
                    try:
                        outcome=future.result()
                    except Exception:
                        # Unknown OS cleanup/receipt status: never release the
                        # reserved memory or fabricate a completed still.
                        return {"status":"RECOVERY_REQUIRED",
                                "film_master_approved":False}
                    if outcome is None or (
                            isinstance(outcome,dict) and (
                                outcome.get("admitted") is False or
                                # Multiple ticket futures can dispatch a
                                # DIFFERENT approved queued job first. The
                                # current job remains pending, not failed.
                                outcome.get("id") != item["job_id"])):
                        # Resource guardian declined this admission. The
                        # durable QUEUED ticket is preserved; throttle attempts
                        # rather than spinning workers or discarding consent.
                        if time.monotonic()-item["last_dispatch_at"]>=5:
                            item["last_dispatch_at"]=time.monotonic()
                            self._futures[ticket_id]=self._executor.submit(
                                host.run_next)
                        return {"status":"QUEUED",
                                "waiting_for_resources":True,
                                "film_master_approved":False}
                    # A worker returned but a verified derivative is absent.
                    # No unchecked output may be surfaced as camera picture.
                    return {"status":"RECOVERY_REQUIRED",
                            "film_master_approved":False}
                return {"status":"QUEUED","film_master_approved":False}
            # The ORIGINAL host independently checks consent, scene SHA,
            # manifest, cache hash, renderer receipt and physical PNG size.
            media=host.read_camera_workbench_png(
                item["project_id"],item["cache_key"])
            if (media["scene_id"]!=item["scene_id"]
                    or media["scene_revision"]!=item["revision"]
                    or media["scene_document_sha256"]!=item["scene_sha"]
                    or media["source_tick"]!=item["source_tick"]
                    or media["camera_path"]!=item["camera_path"]
                    or media["lens_settings"]!=item["settings"]
                    or media["frozen_take_created"] is not False
                    or media["film_master_approved"] is not False):
                raise RuntimeError("Native camera delivery identity mismatch")
            png=media["png_bytes"]
            if (type(png) is not bytes or not 33<=len(png)<=MAX_IMAGE_BYTES
                    or not png.startswith(b"\x89PNG\r\n\x1a\n")
                    or sha256(png).hexdigest()!=media["image_sha256"]):
                raise RuntimeError("Native media delivery failed bounded SHA-256 audit")
            return {
                "status":"READY","format":"nvp.camera.desktop_delivery.v1",
                "scene_document_sha256":media["scene_document_sha256"],
                "source_tick":media["source_tick"],
                "camera_path":media["camera_path"],
                "lens_settings":media["lens_settings"],
                "image_sha256":media["image_sha256"],
                "image_data_url":"data:image/png;base64,"+
                    base64.b64encode(png).decode("ascii"),
                "source_modified":False,
                "frozen_take_created":False,
                "film_master_approved":False,
            }

    def cancel_camera_still(self, ticket_id):
        self._native_window()
        with self._lock:
            item=self._tickets.get(ticket_id)
            if item is None:
                raise PermissionError("Unknown native camera session ticket")
            job_id=item["job_id"]
            if not job_id:
                raise RuntimeError("Cached previews have no active worker to cancel")
            row=self._get_host().cache._job(job_id)
            if row["project_id"]!=item["project_id"] or row["cache_key"]!=item["cache_key"]:
                raise RuntimeError("Native camera cancellation source does not match")
            if row["state"]!="PENDING":
                raise RuntimeError("Only unfinished preview workers can be cancelled")
            if not self._ask(
                    "Cancel this original-scene Blender preview?\n"
                    f"Scene: {item['scene_id']} · Job: {job_id}\n"
                    "No source film data will be erased."):
                return {"status":"DENIED","native_worker_cancelled":False}
            grant=self._grant({
                "operation":"nvp.camera.cancel_pre_take_still.v1",
                "project_id":item["project_id"],
                "scene_id":item["scene_id"],
                "job_id":job_id,"preview_cache_key":item["cache_key"],
            })
            try:
                done=self._get_host().cancel(job_id,creator_event=grant)
            finally:
                self._grants.pop(grant.token,None)
            return {"status":done["state"],"native_worker_cancelled":True}

    # DATA-AV-01: same authenticated native window, wholly distinct from
    # the optional Blender camera still and conventional video preview.
    # The browser cannot provide source media paths or grant its own consent.
    def _data_av(self):
        if self._data_av_controller is None:
            from backend.nvp_data_av_desktop import TrustedDataAVController
            self._data_av_controller=TrustedDataAVController(
                self.index,native_window=self._native_window,
                ask_native=self._ask)
        return self._data_av_controller

    def data_av_texture_mesh_catalog(self,project_id):
        """List eligible original mesh heads without exposing project file paths."""
        with self._lock:
            self._native_window()
            _require_pid(project_id)
            from backend.nvp_openusd_assets import OpenUSDAssetRegistry
            registry=OpenUSDAssetRegistry(self.index)
            result=[]
            for item in self.index.list_objects(project_id,kind="asset")[:128]:
                record,_=registry.open(project_id,item["object_id"],
                                       item["head_revision"])
                doc=record["data"]
                if (doc["shape"]=="mesh" and
                    (doc.get("mesh_uvs") is not None or
                     doc.get("face_uvs") is not None) and
                    doc.get("preview_material") is not None):
                    result.append({
                        "asset_id":item["object_id"],
                        "asset_revision":record["revision"],
                        "asset_document_sha256":record["document_sha256"],
                        "texture_sha256":doc["preview_material"].get(
                            "texture",{}).get("sha256"),
                    })
            return {"format":"nvp.native.texture_mesh_catalog.v1",
                    "assets":result,"original_modified":False}

    def wo2_propose_presentation_look(self,request):
        """Generate an untrusted, non-persistent assistant-facing film look."""
        with self._lock:
            self._native_window()
            if type(request) is not dict or set(request)!={
                "project_id","scene_id","scene_revision","scene_sha256",
                "intent"}:
                raise PermissionError("WO2 proposals require exact USD scene scope")
            from backend.nvp_wo2_presentation_look import (
                OriginalSceneLook,propose_look)
            source=OriginalSceneLook(self.index)._source(
                request["project_id"],request["scene_id"],
                request["scene_revision"],request["scene_sha256"])
            return propose_look(request["intent"],source["data"]["prim_roles"])

    def wo2_approve_presentation_look(self,request):
        """OS-approved, durable presentation revision. No Take source edits."""
        with self._lock:
            self._native_window()
            if type(request) is not dict or set(request)!={
                "project_id","look_id","scene_id","scene_revision",
                "scene_sha256","look","expected_revision"}:
                raise PermissionError("WO2 look publication needs exact source binding")
            from backend.nvp_wo2_presentation_look import OriginalSceneLook
            return OriginalSceneLook(self.index).publish(
                request["project_id"],request["look_id"],
                scene_id=request["scene_id"],
                scene_revision=request["scene_revision"],
                scene_sha256=request["scene_sha256"],
                look=request["look"],
                expected_revision=request["expected_revision"],
                approve=lambda scope:self._ask(
                    "Publish NEW non-destructive OpenUSD presentation look?\\n"
                    +"Scene: "+scope["scene_id"]+" rev "
                    +str(scope["scene_revision"])+"\\n"
                    +"Frozen source SHA-256: "+scope["scene_sha256"]+"\\n"
                    +"Lighting, shadows, reflections, camera, UV and material "
                    +"decisions will be versioned. Original Takes and PNGs "
                    +"will not be modified."))

    def wo2_presentation_look_catalog(self,request):
        """Exact-scene approved decisions, never global model or API inputs."""
        with self._lock:
            self._native_window()
            if type(request) is not dict or set(request)!={
                "project_id","scene_id","scene_revision","scene_sha256"}:
                raise PermissionError("WO2 presentation list needs original source")
            from backend.nvp_wo2_presentation_look import OriginalSceneLook
            return OriginalSceneLook(self.index).catalog(
                request["project_id"],
                scene_id=request["scene_id"],
                scene_revision=request["scene_revision"],
                scene_sha256=request["scene_sha256"])

    def wo2_read_presentation_look(self,request):
        """Read only a version pinned to the displayed OpenUSD source."""
        with self._lock:
            self._native_window()
            if type(request) is not dict or set(request)!={
                "project_id","look_id","revision","scene_sha256"}:
                raise PermissionError("WO2 source-scoped presentation reader required")
            from backend.nvp_wo2_presentation_look import OriginalSceneLook
            return OriginalSceneLook(self.index).open(
                request["project_id"],request["look_id"],
                request["revision"],scene_sha256=request["scene_sha256"])

    def data_av_apply_original_texture(self,request):
        """Create a NEW immutable mesh revision from an approved texture SHA."""
        with self._lock:
            self._native_window()
            base_keys={"project_id","asset_id","asset_revision",
                       "asset_document_sha256","texture_sha256"}
            if type(request) is not dict or set(request) not in (
                    base_keys,base_keys|{"channel"}):
                raise ValueError("Texture application requires exact source revisions")
            channel=request.get("channel","base_color")
            if channel not in ("base_color","roughness","metallic",
                               "emission","normal","opacity"):
                raise ValueError("Only bounded original PBR channels are supported")
            pid=request["project_id"]
            _require_pid(pid)
            aid=request["asset_id"]
            _id(aid,"original reusable mesh ID")
            revision=request["asset_revision"]
            if type(revision) is not int or revision<1:
                raise ValueError("Original mesh revision required")
            _sha(request["asset_document_sha256"])
            digest=_sha(request["texture_sha256"])
            from backend.nvp_openusd_assets import OpenUSDAssetRegistry
            from backend.nvp_native_usd_texture import decode_png
            registry=OpenUSDAssetRegistry(self.index)
            old,_=registry.open(pid,aid,revision)
            if old["document_sha256"]!=request["asset_document_sha256"]:
                raise PermissionError("Requested mesh source revision changed")
            if self.index.read_revision(pid,aid)["revision"]!=revision:
                raise RuntimeError("Original mesh was revised before selection")
            doc=old["data"]
            original_material=doc.get("preview_material")
            if (doc["shape"]!="mesh" or original_material is None or
                (doc.get("mesh_uvs") is None and doc.get("face_uvs") is None)):
                raise ValueError("Only an original source UV mesh may use PNG")
            png=self.index.get_blob(pid,digest)
            width,height,_=decode_png(png)
            if not self._ask(
                "Publish NEW immutable mesh material revision?\n"+
                "Source mesh: "+aid+" revision "+str(revision)+"\n"+
                "Original mesh SHA-256: "+old["document_sha256"]+"\n"+
                "Frozen image SHA-256: "+digest+"\n"+
                "Material channel: "+channel+"\n"+
                "Texture: "+str(width)+" x "+str(height)+"\n"+
                "Existing scene, character and Digital Take revisions remain unchanged."):
                return {"format":"nvp.native.texture_mesh_revision.v1",
                        "status":"DENIED","original_modified":False}
            if self.index.read_revision(pid,aid)["revision"]!=revision:
                raise RuntimeError("Mesh changed while native approval was displayed")
            controls={key:original_material[key] for key in (
                "base_color_rgb","roughness","metallic")}
            from backend.nvp_native_usd_texture import verified_texture
            existing_base=original_material.get("texture")
            base_png=(png if channel=="base_color" else
                      verified_texture(self.index,pid,existing_base)[0]
                      if existing_base else None)
            pbr_pngs={
                name:verified_texture(self.index,pid,descriptor)[0]
                for name,descriptor in original_material.get(
                    "pbr_maps",{}).items()}
            if channel!="base_color":
                pbr_pngs[channel]=png
            published=registry.publish(
                pid,aid,shape="mesh",size_m=doc["size_m"],
                points=doc["points"],triangles=doc["triangles"],
                mesh_uvs=doc.get("mesh_uvs"),face_uvs=doc.get("face_uvs"),
                preview_material=controls,texture_png=base_png,
                pbr_maps_png=(pbr_pngs or None),
                material_slots=(
                    [{key:slot[key] for key in ("faces","base_color_rgb",
                                                "roughness","metallic")}
                     for slot in doc["material_slots"]]
                    if doc.get("material_slots") else None),
                expected_revision=revision)
            return {"format":"nvp.native.texture_mesh_revision.v1",
                    "status":"NEW_SOURCE_REVISION",
                    "asset_id":aid,"asset_revision":published["revision"],
                    "asset_document_sha256":published["document_sha256"],
                    "source_material_channel":channel,
                    "original_modified":False,"ffmpeg_used":False}

    def data_av_import_original_texture(self,project_id):
        """Trusted desktop-only PNG picker. Browser passes no source paths."""
        with self._lock:
            window=self._native_window()
            _require_pid(project_id)
            from webview import FileDialog
            if not callable(getattr(window,"create_file_dialog",None)):
                raise PermissionError("NVP requires a real OS image picker")
            chosen=window.create_file_dialog(
                FileDialog.OPEN,allow_multiple=False,
                file_types=("PNG original textures (*.png)",))
            if not chosen:
                return {"format":"nvp.native.texture_import.v1",
                        "status":"CANCELLED","original_modified":False}
            if len(chosen)!=1:
                raise PermissionError("Original texture import selects one image")
            from backend.nvp_native_usd_texture import import_native_selected_png
            def approve(scope):
                return self._ask(
                    "Import a frozen original PNG texture?\n"+
                    "SHA-256: "+scope["sha256"]+"\n"+
                    "Dimensions: "+str(scope["width"])+" x "+
                        str(scope["height"])+"\n"+
                    "Bytes: "+str(scope["size_bytes"])+"\n"+
                    "NVP will store immutable source bytes in this project.\n"+
                    "No existing scene, rig, Digital Take or presentation changes.")
            result=import_native_selected_png(
                self.index,project_id,chosen[0],approve=approve)
            return {"format":"nvp.native.texture_import.v1",**result}

    def data_av_import_original_audio(self,project_id,source_id):
        """Open a REAL native OS picker. The browser supplies IDs, never paths."""
        self._native_window()
        from backend.nvp_imported_audio import OriginalAudioImport
        from webview import FileDialog
        def selected():
            window=self._native_window()
            if not callable(getattr(window,"create_file_dialog",None)):
                raise PermissionError("No trusted native audio file picker installed")
            chosen=window.create_file_dialog(
                FileDialog.OPEN,allow_multiple=False,
                file_types=("Sound files (*.mp3;*.flac;*.wav;*.ogg)",))
            if not chosen:
                return None
            if len(chosen)!=1:
                raise PermissionError("Only one original audio file may be imported")
            return chosen[0]
        source=OriginalAudioImport(
            self.index,trusted_native_picker=selected
        ).register_from_picker(project_id,source_id)
        data=self.index.read_revision(project_id,source_id,
                                      source["revision"])["data"]
        return {"format":"nvp.data_av.native_audio_import.v1",
                "status":"ORIGINAL_IMPORTED",
                "source_id":source_id,"source_revision":source["revision"],
                "source_document_sha256":source["document_sha256"],
                "original_codec":data["original_codec"],
                "original_media_sha256":data["source_media_sha256"],
                "original_modified":False,
                "soundtrack_flattened":False,"ffmpeg_used":False}

    def data_av_freeze_timed_take(self,request):
        return self._data_av().freeze_exact_camera_take(request)

    def data_av_catalog(self,project_id):
        return self._data_av().catalog(project_id)

    def data_av_binaural_catalog(self,project_id):
        """List only real source-bound IR profiles; never invent measurements."""
        self._native_window()
        _require_pid(project_id)
        from backend.nvp_native_hrir import NativeMeasuredBinauralIR
        profiles=[]
        for row in self.index.list_objects(project_id,kind="audio")[:128]:
            try:
                record=self.index.read_revision(
                    project_id,row["object_id"],1)
                if record["data"].get("format")!=(
                        "nvp.data_av.source_binaural_ir.v1"):
                    continue
                verified=NativeMeasuredBinauralIR(
                    self.index,project_id,row["object_id"],
                    record["document_sha256"])
                profiles.append({
                    "source_id":verified.source_id,
                    "source_document_sha256":verified.source_sha,
                    "measurement_kind":verified.kind,
                    "measured_source_label":record["data"]["measured_source_label"],
                    "calibrated":False,
                })
            except (RuntimeError,ValueError,KeyError):
                continue
        return {"format":"nvp.data_av.binaural_ir_catalog.v1",
                "status":"AVAILABLE","profiles":profiles,
                "ffmpeg_used":False,"cinema_calibration_accepted":False}

    def data_av_begin(self,request):
        return self._data_av().begin(request)

    def data_av_audio_window(self,session_id,first_sample,count):
        return self._data_av().read_audio(session_id,first_sample,count)

    def data_av_original_texture_tile(self,session_id,request):
        """Only a currently approved Take may stream one pinned source tile."""
        self._native_window()
        return self._data_av().read_original_texture_tile(session_id,request)

    def data_av_original_rig_texture_tile(self,session_id,request):
        """Only a frozen scene-authorized actual skinned actor may read PNG."""
        self._native_window()
        return self._data_av().read_original_rig_texture_tile(
            session_id,request)

    def data_av_scene_at(self,session_id,tick):
        return self._data_av().scene_at(session_id,tick)

    def data_av_stop(self,session_id):
        return self._data_av().stop(session_id)



    def data_av_native_aces_policy(self):
        """Exact OpenColorIO display processor pinned to installed library."""
        self._native_window()
        from backend.nvp_native_aces_color import policy
        info,_=policy()
        return info

    def data_av_native_aces_review(self,request):
        """Creator-authorized transient PNG16 derived from real original USD.

        No model-provided image, scene-linear pixel buffer, camera selector,
        local path, color-config text or imported render is accepted.
        """
        self._native_window()
        required={"project_id","take_id","take_sha256",
                  "grade_id","grade_revision","grade_sha256",
                  "film_time_tick","expected_config_sha256"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Native ACES source color request must be exact")
        from backend.nvp_native_color_decisions import NativeColorDecisions
        from backend.nvp_native_aces_color import NativeACESColor,policy
        from backend.nvp_temporal_ledger import TemporalLedger,_int
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        _require_pid(request["project_id"])
        _id(request["take_id"],"original USD Digital Take")
        _id(request["grade_id"],"original source color decision")
        _sha(request["take_sha256"])
        _sha(request["grade_sha256"])
        _sha(request["expected_config_sha256"])
        _int(request["film_time_tick"],"approved Film Time")
        grade=NativeColorDecisions(self.index).read(
            request["project_id"],request["grade_id"],
            request["grade_revision"])
        if (grade["take_id"]!=request["take_id"] or
            grade["take_sha256"]!=request["take_sha256"] or
            grade["document_sha256"]!=request["grade_sha256"]):
            raise RuntimeError("Native ACES grade is not pinned to this frozen Take")
        original=self.index.read_revision(
            request["project_id"],request["take_id"],1)
        data=original["data"]
        if (original["document_sha256"]!=request["take_sha256"] or
            original["kind"]!="take" or data.get("frozen") is not True or
            data.get("format")!="nvp.digital_take.openusd_temporal.v1" or
            request["film_time_tick"]>=data["duration_tick"]):
            raise RuntimeError("Native color preview source Take/time is not frozen")
        active=TemporalLedger(self.index).events_at(
            request["project_id"],data["timeline_id"],
            data["timeline_revision"],tick=request["film_time_tick"],
            event_kind="camera",limit=2)
        if len(active)!=1:
            raise RuntimeError("Color preview needs exactly one original USD shot camera")
        camera=active[0]["payload"].get("usd_prim_path")
        if (type(camera) is not str or not camera.startswith("/World/")):
            raise RuntimeError("Original active camera event has invalid source")
        info,_=policy()
        if info["configuration_sha256"]!=request["expected_config_sha256"]:
            raise RuntimeError("Installed native ACES 2 config changed")
        approved=self._ask(
            "Create a TEMPORARY unmastered ACES 2 SDR review picture?\n"
            f"Original frozen Take: {request['take_id']}\n"
            f"Take SHA: {request['take_sha256']}\n"
            f"Grade SHA: {request['grade_sha256']}\n"
            f"ACES configuration SHA: {info['configuration_sha256']}\n"
            f"Original Film Time tick: {request['film_time_tick']}\n"
            f"Authored USD camera: {camera}\n"
            "The renderer uses source USD geometry/light, not a captured 2D frame.\n"
            "Working color/lights are NOT professionally calibrated.\n"
            "No movie/master, FFmpeg process or source modification.")
        if approved is not True:
            raise PermissionError("Creator declined the native ACES review projection")
        picture,receipt=NativeACESColor(self.index).process_verified_usd_scene(
            request["project_id"],request["take_id"],request["take_sha256"],
            request["grade_id"],request["grade_revision"],
            request["grade_sha256"],
            tick=request["film_time_tick"],camera_path=camera,
            expected_config_sha256=request["expected_config_sha256"])
        if len(picture)>16*1024*1024:
            raise RuntimeError("Bounded native source color picture exceeded limit")
        return {
            **receipt,"png16_base64":base64.b64encode(picture).decode("ascii"),
            "output_mime":"image/png","original_modified":False,
            "saved_picture_files":False,"master_approved":False,
        }

    def data_av_native_color_catalog(self,project_id,take_id,take_sha256):
        """List only source-bound, verified immutable grade revisions."""
        self._native_window()
        _require_pid(project_id)
        _id(take_id,"original Digital Take")
        _sha(take_sha256)
        from backend.nvp_native_color_decisions import NativeColorDecisions
        grades=[]
        grader=NativeColorDecisions(self.index)
        for row in self.index.list_objects(project_id,kind="style")[:128]:
            try:
                plan=grader.read(project_id,row["object_id"])
            except (RuntimeError,ValueError,KeyError):
                continue
            if (plan["take_id"]==take_id and
                    plan["take_sha256"]==take_sha256):
                grades.append({
                    "grade_id":plan["grade_id"],
                    "revision":plan["revision"],
                    "document_sha256":plan["document_sha256"],
                    "parameters":plan["parameters"],
                })
        return {"format":"nvp.data_first.native_grade_catalog.v1",
                "status":"AVAILABLE","grades":grades,"ffmpeg_used":False}

    def data_av_export_native_aces_package(self,request):
        """Creator-approved RGB16 ACES picture + PCM from verified USD Film Time.

        This is an unmastered, no-replace native 2D DERIVATIVE only.
        The OS picker chooses the destination; browser input contains IDs.
        """
        self._native_window()
        required={"project_id","take_id","take_document_sha256",
                  "presentation_id","listener_path","fps_num","fps_den",
                  "aces_color_grade"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Native ACES RGB16 package requires exact source/grade scope")
        from backend.nvp_final_2d_native import Approved2DPackage,OUTPUT_CADENCES
        from backend.nvp_native_cpu_raster import NativeSourceRaster
        from webview import FileDialog
        pid=request["project_id"]
        take=request["take_id"]
        sha=request["take_document_sha256"]
        presentation=request["presentation_id"]
        _require_pid(pid)
        _id(take,"original frozen USD Digital Take")
        _id(presentation,"new color-managed presentation identity")
        _sha(sha)
        if (type(request["fps_num"]) is not int or
            type(request["fps_den"]) is not int or
            (request["fps_num"],request["fps_den"]) not in OUTPUT_CADENCES):
            raise ValueError("Unapproved exact native picture cadence")
        listener=request["listener_path"]
        if type(listener) is not str or not listener.startswith("/World/"):
            raise ValueError("A native authored USD camera is required")
        color=request["aces_color_grade"]
        if type(color) is not dict or set(color)!={
                "grade_id","revision","document_sha256","config_sha256"}:
            raise ValueError("Native ACES package requires source-pinned grade/config")
        for name in ("document_sha256","config_sha256"):
            _sha(color[name])
        original=self.index.read_revision(pid,take,1)
        if original["document_sha256"]!=sha or original["kind"]!="take":
            raise RuntimeError("Original frozen Digital Take identity changed")
        window=self._native_window()
        if not callable(getattr(window,"create_file_dialog",None)):
            raise PermissionError("Trusted OS color package folder chooser unavailable")
        chosen=window.create_file_dialog(FileDialog.FOLDER)
        if not chosen:
            return {"status":"CANCELLED","ffmpeg_used":False,
                    "original_modified":False}
        if type(chosen) not in (list,tuple) or len(chosen)!=1:
            raise PermissionError("Choose one native output directory")
        parent=Path(chosen[0])
        if parent.is_symlink() or not parent.is_dir():
            raise PermissionError("Native destination folder is not trusted")
        def approve_package(scope):
            if (scope.get("take_document_sha256")!=sha or
                scope.get("color_pipeline")!=
                    "ocio_aces2_scene_linear_png16_unmastered" or
                scope.get("color_grade_sha256")!=color["document_sha256"] or
                scope.get("aces_config_sha256")!=color["config_sha256"] or
                scope.get("listener_path")!=listener or
                scope.get("presentation_id")!=presentation or
                scope.get("original_data_immutable") is not True):
                return False
            return self._ask(
                "Publish a NEW ACES 2 SDR 16-bit PNG picture + PCM package?\n"
                f"Frozen USD Take SHA: {sha}\n"
                f"Saved non-destructive color grade SHA: {color['document_sha256']}\n"
                f"OCIO ACES2 config SHA: {color['config_sha256']}\n"
                f"Picture cadence: {scope['fps_num']}/{scope['fps_den']}\n"
                f"Native authored camera/listener: {listener}\n"
                f"Picture count: {scope['frame_count']}\n"
                f"Destination folder: {parent}\n"
                "Original USD and PCM never change. No AVI down-conversion, FFmpeg\n"
                "or professional calibrated DCP/master is produced.")
        primitive=NativeSourceRaster(self.index,pid)
        result=Approved2DPackage(
            self.index,native_creator_approval=approve_package,
            render_png=primitive.render_png).export(
                pid,take,sha,presentation,parent,
                listener_path=listener,
                fps_num=request["fps_num"],fps_den=request["fps_den"],
                aces_color_grade=color,resumable=True)
        if (result["color_pipeline"]!=
                "ocio_aces2_scene_linear_png16_unmastered" or
            result["pixel_bit_depth"]!=16):
            raise RuntimeError("Native approved ACES2 package lost source color")
        return {**result,
                "format":"nvp.native_ocio.approved_source_png16_package.v1",
                "status":"UNMASTERED_ACES2_PNG16_AUDIO_PACKAGE",
                "original_modified":False,"master_approved":False}

    def data_av_cinema_readiness(self,request):
        """Read-only native folder inspection: never make fake DCP deliveries.

        The browser never specifies an OS path, validator binary, mastering
        grant, codec executable or output directory. The native OS folder
        selector gives access to one producer-owned derived package only.
        """
        self._native_window()
        fields={"project_id","take_id","take_document_sha256","target"}
        if type(request) is not dict or set(request)!=fields:
            raise ValueError("Native cinema/HDR readiness requires exact source")
        from webview import FileDialog
        from backend.nvp_native_cinema_master_gate import (
            assess_unmastered_source_package,TARGETS)
        pid=request["project_id"];take=request["take_id"]
        sha=request["take_document_sha256"]
        _require_pid(pid);_id(take,"frozen original Digital Take");_sha(sha)
        if request["target"] not in TARGETS:
            raise ValueError("No verified native output target")
        source=self.index.read_revision(pid,take,1)
        if (source["kind"]!="take" or
            source["document_sha256"]!=sha or
            source["data"].get("frozen") is not True):
            raise RuntimeError("Cinema readiness original Take is not frozen")
        win=self._native_window()
        if not callable(getattr(win,"create_file_dialog",None)):
            raise PermissionError("Native folder selection for source inspection unavailable")
        selected=win.create_file_dialog(FileDialog.FOLDER)
        if not selected:
            return {"format":"nvp.native_data_first.cinema_preflight.v1",
                    "status":"CANCELLED","dcp_delivered":False,
                    "source_original_modified":False,"ffmpeg_used":False}
        if type(selected) not in (tuple,list) or len(selected)!=1:
            raise PermissionError("Select exactly one native original-derived package")
        path=Path(selected[0])
        if path.is_symlink() or not path.is_dir():
            raise PermissionError("Unsafe source-derived color package folder")
        # The OS folder selection alone is not production provenance:
        # require exact immutable FilmIndex producer receipt from the
        # original approved color export, including original Take/grade.
        name=path.name
        if not name.startswith("NVP2D_"):
            raise PermissionError("Native DCP review needs NVP-approved source derivative")
        presentation_id=name[len("NVP2D_"):]
        _id(presentation_id,"NVP-approved original source presentation")
        proof=self.index.read_revision(
            pid,"NativePackage_"+presentation_id,1)
        manifest=path/"manifest.json"
        if (manifest.is_symlink() or not manifest.is_file() or
            manifest.stat().st_size>16*1024*1024):
            raise RuntimeError("No authentic native produced color manifest")
        digest=sha256(manifest.read_bytes()).hexdigest()
        data=proof["data"]
        if (proof["kind"]!="presentation" or
            data.get("format")!="nvp.data_first.native_color_package.v1" or
            data.get("manifest_sha256")!=digest or
            data.get("output_directory_name")!=name or
            data.get("source_take_id")!=take or
            data.get("source_take_sha256")!=sha or
            data.get("original_data_modified") is not False or
            data.get("ffmpeg_used") is not False or
            data.get("dcp_delivered") is not False or
            {"object_id":take,"revision":1,"role":"source_take"}
                not in proof["dependencies"] or
            len(proof["dependencies"])!=2):
            raise RuntimeError("Selected package lacks original native publisher authority")
        original_grade=self.index.read_revision(
            pid,data["color_grade_id"],data["color_grade_revision"])
        if (original_grade["document_sha256"]!=data["color_grade_sha256"] or
            {"object_id":data["color_grade_id"],
             "revision":data["color_grade_revision"],"role":"style"}
                not in proof["dependencies"]):
            raise RuntimeError("Original NVP color decision receipt changed")
        receipt=assess_unmastered_source_package(
            path,target=request["target"],expected_take_sha256=sha)
        if receipt["dcp_delivered"] is not False:
            raise RuntimeError("Unvalidated theatrical package is forbidden")
        return {**receipt,
                "authenticated_native_presentation_sha256":
                    proof["document_sha256"],
                "authenticated_approved_source_derivative":True}

    def data_av_export_native_acescg_exr(self,request):
        """Produce approved source-linear ACEScg RGB32 OpenEXR and PCM.

        Each full-float EXR is a separate, SHA-audited DERIVATIVE. Browser
        JavaScript cannot choose an OS path or synthesize creator consent.
        """
        self._native_window()
        required={"project_id","take_id","take_document_sha256",
                  "presentation_id","listener_path","fps_num","fps_den",
                  "linear_exr_grade"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Exact original source/grade/EXR scope required")
        from backend.nvp_final_2d_native import (
            Approved2DPackage,OUTPUT_CADENCES)
        from backend.nvp_native_cpu_raster import NativeSourceRaster
        from webview import FileDialog
        pid=request["project_id"];take=request["take_id"]
        sha=request["take_document_sha256"]
        presentation=request["presentation_id"]
        _require_pid(pid);_id(take,"original USD Take")
        _id(presentation,"new scene-linear presentation identity")
        _sha(sha)
        if (type(request["fps_num"]) is not int or
            type(request["fps_den"]) is not int or
            (request["fps_num"],request["fps_den"]) not in OUTPUT_CADENCES):
            raise ValueError("Unsupported native ACEScg output cadence")
        listener=request["listener_path"]
        if type(listener) is not str or not listener.startswith("/World/"):
            raise ValueError("Original authored scene camera required")
        color=request["linear_exr_grade"]
        if type(color) is not dict or set(color)!={
            "grade_id","revision","document_sha256","config_sha256"}:
            raise ValueError("Native ACEScg source grade needs exact SHA")
        for key in ("document_sha256","config_sha256"):
            _sha(color[key])
        old=self.index.read_revision(pid,take,1)
        if old["kind"]!="take" or old["document_sha256"]!=sha:
            raise RuntimeError("Original frozen Take changed before approval")
        window=self._native_window()
        if not callable(getattr(window,"create_file_dialog",None)):
            raise PermissionError("Native OS OpenEXR output folder chooser absent")
        picked=window.create_file_dialog(FileDialog.FOLDER)
        if not picked:
            return {"status":"CANCELLED","ffmpeg_used":False,
                    "original_modified":False}
        if type(picked) not in (tuple,list) or len(picked)!=1:
            raise PermissionError("Select exactly one trusted native folder")
        parent=Path(picked[0])
        if parent.is_symlink() or not parent.is_dir():
            raise PermissionError("Native export destination is not trusted")
        def approve(scope):
            if (scope.get("take_document_sha256")!=sha or
                scope.get("presentation_id")!=presentation or
                scope.get("listener_path")!=listener or
                scope.get("color_pipeline")!=
                    "ocio_scene_linear_acescg_exr32_unmastered" or
                scope.get("color_grade_sha256")!=color["document_sha256"] or
                scope.get("aces_config_sha256")!=color["config_sha256"] or
                scope.get("original_data_immutable") is not True):
                return False
            return self._ask(
                "Publish a NEW unmastered ACEScg FLOAT32 OpenEXR + PCM package?\n"
                f"Original frozen USD Take SHA: {sha}\n"
                f"Original creative grade SHA: {color['document_sha256']}\n"
                f"Native OCIO config SHA: {color['config_sha256']}\n"
                f"Film Time cadence: {scope['fps_num']}/{scope['fps_den']}\n"
                f"Original authored USD camera: {listener}\n"
                f"Frames: {scope['frame_count']}\n"
                f"Native folder: {parent}\n"
                "OpenEXR contains native full-float ACEScg scene-linear pixels, "
                "not a completed DCP. No original data changes, FFmpeg, or "
                "automatic picture down-conversion.")
        primitive=NativeSourceRaster(self.index,pid)
        result=Approved2DPackage(
            self.index,native_creator_approval=approve,
            render_png=primitive.render_png).export(
                pid,take,sha,presentation,parent,
                listener_path=listener,
                fps_num=request["fps_num"],fps_den=request["fps_den"],
                linear_exr_grade=color,resumable=True)
        if (result["color_pipeline"]!=
            "ocio_scene_linear_acescg_exr32_unmastered" or
            result["pixel_bit_depth"]!=32 or
            result["picture_format"]!="exr"):
            raise RuntimeError("Native ACEScg interchange was not source-verified")
        return {**result,
                "format":"nvp.native_ocio.approved_acescg_exr32_package.v1",
                "status":"UNMASTERED_SOURCE_ACESCG_EXR32_PCM_PACKAGE",
                "original_modified":False,"master_approved":False}

    def data_av_export_native_avi(self,request):
        """Two native approvals and OS folder choice; browser supplies no path.

        The approved original is a 3D Take. PNG+PCM and the AVI are distinct,
        immutable derivatives, never new capture sources or cinema masters.
        """
        self._native_window()
        required={"project_id","take_id","take_document_sha256",
                  "presentation_id","listener_path","fps_num","fps_den"}
        if type(request) is not dict or set(request) not in (
                required,required|{"color_grade"}):
            raise ValueError("Native delivery needs exactly scoped source IDs")
        from backend.nvp_final_2d_native import Approved2DPackage,OUTPUT_CADENCES
        from backend.nvp_native_cpu_raster import NativeSourceRaster
        from backend.nvp_native_avi_delivery import deliver_avi
        from webview import FileDialog
        pid=request["project_id"]
        take=request["take_id"]
        sha=request["take_document_sha256"]
        presentation=request["presentation_id"]
        _require_pid(pid)
        _id(take,"original Digital Take")
        _id(presentation,"derived presentation identity")
        _sha(sha)
        if (type(request["fps_num"]) is not int or
                type(request["fps_den"]) is not int or
                (request["fps_num"],request["fps_den"]) not in OUTPUT_CADENCES):
            raise ValueError("Unapproved native output cadence")
        listener=request["listener_path"]
        if type(listener) is not str or not listener.startswith("/World/"):
            raise ValueError("A native scene virtual microphone is required")
        window=self._native_window()
        if not callable(getattr(window,"create_file_dialog",None)):
            raise PermissionError("Native OS destination picker is unavailable")
        chosen=window.create_file_dialog(FileDialog.FOLDER)
        if not chosen:
            return {"status":"CANCELLED","ffmpeg_used":False,
                    "original_modified":False}
        if type(chosen) not in (tuple,list) or len(chosen)!=1:
            raise PermissionError("Choose one native output folder")
        parent=Path(chosen[0])
        if parent.is_symlink() or not parent.is_dir():
            raise PermissionError("Native output folder is no longer trusted")
        source=self.index.read_revision(pid,take,1)
        if source["document_sha256"]!=sha:
            raise RuntimeError("Selected original Digital Take changed")
        def approve_package(scope):
            if (scope.get("take_document_sha256")!=sha or
                    scope.get("presentation_id")!=presentation or
                    scope.get("listener_path")!=listener or
                    scope.get("original_data_immutable") is not True):
                return False
            return self._ask(
                "Approve derived native 2D picture and PCM sound?\n"
                f"Original Take: {take}\nSHA-256: {sha}\n"
                f"Presentation: {presentation}\nListener: {listener}\n"
                f"Output folder: {parent}\n"
                f"Color grade SHA-256: {scope['color_grade_sha256']}\n"
                "This is a limited native 640×360 procedural OpenUSD raster,\n"
                "not a cinema-quality final master. Sources remain immutable.")
        render=NativeSourceRaster(self.index,pid)
        package=Approved2DPackage(
            self.index,native_creator_approval=approve_package,
            render_png=render.render_png).export(
                pid,take,sha,presentation,parent,listener_path=listener,
                fps_num=request["fps_num"],fps_den=request["fps_den"],
            color_grade=request.get("color_grade"))
        def approve_movie(scope):
            if scope.get("original_take_sha256")!=sha or (
                    scope.get("source_mutated") is not False):
                return False
            return self._ask(
                "Publish a new native uncompressed AVI + PCM movie?\n"
                f"Original Take SHA-256: {sha}\n"
                f"Approved derived image/audio manifest: {scope['manifest_sha256']}\n"
                f"File: {scope['output_name']}\n"
                f"Color grade SHA-256: {scope['color_grade_sha256']}\n"
                "No FFmpeg or overwrite. This AVI is not a mastered DCP.")
        result=deliver_avi(
            package["directory"],parent/("NVP2D_"+presentation+".avi"),
            expected_take_sha256=sha,approve_delivery=approve_movie)
        return {**result,"picture_audio_package":package["directory"],
                "original_modified":False,"master_approved":False}


    def data_av_live_catalog(self,project_id):
        """Only verified exact-time source camera timelines can be filmed."""
        self._native_window()
        _require_pid(project_id)
        from backend.nvp_exact_time_shots import ExactTimeShotSequence
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        choices=[]
        for row in self.index.list_objects(project_id,kind="temporal")[:128]:
            try:
                record=self.index.read_revision(project_id,row["object_id"])
                plan=ExactTimeShotSequence(self.index).read(
                    project_id,row["object_id"],record["revision"])
                scene,_=OpenUSDSceneBridge(self.index).open(
                    project_id,plan["scene_id"],plan["scene_revision"])
            except (RuntimeError,ValueError,KeyError):
                continue
            sources=sorted(p for p,role in scene["data"]["prim_roles"].items()
                           if role in ("actor","anchor"))
            if sources:
                choices.append({
                    "scene_id":plan["scene_id"],
                    "scene_revision":plan["scene_revision"],
                    "scene_document_sha256":plan["scene_document_sha256"],
                    "camera_timeline_id":plan["timeline_id"],
                    "camera_timeline_revision":plan["revision"],
                    "camera_timeline_document_sha256":plan["document_sha256"],
                    "duration_tick":plan["duration_tick"],
                    "emitters":sources[:64],
                })
        from backend.nvp_capture_recovery import OriginalCaptureJournal
        recovery=OriginalCaptureJournal(
            self.index.studio.db_path.parent/"native-original-capture-recovery")
        unapproved=recovery.catalog(project_id)
        # Optional Windows/Linux PortAudio interface discovery. A machine
        # without PortAudio or real audio hardware retains existing filming.
        try:
            from backend.nvp_native_independent_take import native_input_devices
            independent=native_input_devices()
        except (ImportError,OSError,RuntimeError):
            independent=[]
        return {"format":"nvp.data_av.live_camera_catalog.v1",
                "status":"AVAILABLE","camera_timelines":choices,
                "independent_audio_inputs":independent,
                "independent_audio_available":len(independent)>=2,
                "independent_clock_hardware_accepted":False,
                "unapproved_capture_recovery":unapproved["items"],
                "recovery_automatic_freeze":False,
                "ffmpeg_used":False}

    def data_av_live_recover_original(self,request):
        """Consent-gated recovery of a durable mono source, never a Take."""
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","capture_reference","new_source_id"}:
            raise ValueError("Original microphone salvage requires exact source scope")
        from backend.nvp_capture_recovery import OriginalCaptureJournal
        with self._lock:
            if self._live_sound_session is not None:
                raise RuntimeError("Stop live recording before reconciling captured signal")
            journal=OriginalCaptureJournal(
                self.index.studio.db_path.parent/"native-original-capture-recovery")
            return journal.salvage_original_mono_source(
                self.index,request["project_id"],
                request["capture_reference"],request["new_source_id"],
                native_creator_approval=lambda scope:self._ask(
                    "RECOVER verified original microphone PCM as UNATTACHED sound source?\n"
                    f"Recovery reference: {scope['capture_reference']}\n"
                    f"New source: {scope['new_source_id']}\n"
                    f"Original PCM SHA-256: {scope['pcm_sha256']}\n"
                    f"Recorded samples: {scope['recorded_samples']}\n"
                    "This does NOT freeze a Digital Take or create a soundtrack. "
                    "The original staged recording remains separately preserved."))

    def data_av_live_begin(self,request):
        """Start a real OS microphone; no browser-provided executable/path."""
        self._native_window()
        mono={
            "project_id","take_id","scene_id","scene_revision",
            "camera_timeline_id","camera_timeline_revision",
            "sound_timeline_id","source_id","emitter_path",
            "event_id","subject_id"}
        dual=mono|{"second_source_id","second_emitter_path",
                   "second_event_id","second_subject_id"}
        separate=dual|{"independent_device_ids"}
        if type(request) is not dict or set(request) not in (
                mono,dual,separate):
            raise ValueError("Native microphone source identity/sync scope invalid")
        from backend.nvp_native_live_take import NativeLiveSoundSession
        if set(request)==separate:
            from backend.nvp_native_independent_take import IndependentNativeSoundSession
            recorder_class=IndependentNativeSoundSession
            extra={k:request[k] for k in separate-mono}
        elif set(request)==dual:
            from backend.nvp_native_stereo_take import NativeStereoOriginalSession
            recorder_class=NativeStereoOriginalSession
            extra={k:request[k] for k in dual-mono}
        else:
            recorder_class=NativeLiveSoundSession
            extra={}
        with self._lock:
            if self._live_sound_session is not None:
                raise RuntimeError("Native microphone capture already in progress")
            def start(scope):
                return self._ask(
                    "START real microphone capture into ORIGINAL Digital Take?\n"
                    f"Take: {scope['take_id']}\n"
                    f"Scene SHA-256: {scope['scene_sha256']}\n"
                    f"Camera Film Time SHA-256: {scope['camera_timeline_sha256']}\n"
                    f"Source emitter: {scope['emitter_path']}\n"
                    f"At most {scope['max_samples']//48000} seconds at 48 kHz.\n"
                    + (("Two physically independent original 48-kHz mono devices.\n"
                        "Native ADC timestamps + drift correction must pass; "
                        "original PCM is never retimed.\n"
                        f"Device IDs: {scope['independent_device_ids']}\n"
                        f"Verified native endpoints: {scope.get('independent_device_descriptors')}\n")
                        if "independent_device_ids" in scope else
                        ("Two original mono sources on one shared-clock stereo interface.\n"
                         if extra else "One original mono audio source.\n"))
                    + "This records original source PCM only. No picture movie,\n"
                    "FFmpeg, flattened soundtrack, or master is produced.")
            def freeze(event,scope):
                return self._ask(
                    "FREEZE this exact 3D scene and recorded original sound?\n"
                    f"Take: {scope['take_id']}\n"
                    f"Scene SHA-256: {scope['scene_document_sha256']}\n"
                    f"Events SHA-256: {scope['timeline_document_sha256']}\n"
                    + (("Independent clock proof SHA: "+
                        scope["independent_clock_evidence_sha256"]+"\n"+
                        "Measured device drift (ppm): "+
                        str(scope["independent_clock_drift_ppm"])+"\n"+
                        "Worst ADC timing residuals (ns): "+
                        str(scope["independent_adc_max_residual_ns"])+"\n"+
                        "No hardware genlock. Both original PCM sources stay untouched.\n")
                       if scope.get("independent_original_pcm_unmodified") is True
                       else "")
                    + "This seals an immutable Digital Take, not a movie export.")
            session=recorder_class(
                self.index,project_id=request["project_id"],
                take_id=request["take_id"],scene_id=request["scene_id"],
                scene_revision=request["scene_revision"],
                camera_timeline_id=request["camera_timeline_id"],
                camera_timeline_revision=request["camera_timeline_revision"],
                sound_timeline_id=request["sound_timeline_id"],
                source_id=request["source_id"],
                emitter_path=request["emitter_path"],
                event_id=request["event_id"],
                subject_id=request["subject_id"],
                native_approve_start=start,native_approve_freeze=freeze,
                **extra)
            started=session.begin()
            ticket=secrets.token_urlsafe(32)
            self._live_sound_session=session
            self._live_sound_ticket=ticket
            return {**started,"session_id":ticket}

    def data_av_live_status(self,session_id):
        self._native_window()
        with self._lock:
            if (type(session_id) is not str or
                    session_id!=self._live_sound_ticket or
                    self._live_sound_session is None):
                raise PermissionError("Unrecognized native recording session")
            return self._live_sound_session.status

    def data_av_live_finish(self,session_id,freeze):
        self._native_window()
        with self._lock:
            if (type(session_id) is not str or
                    session_id!=self._live_sound_ticket or
                    self._live_sound_session is None or
                    type(freeze) is not bool):
                raise PermissionError("Unknown live source capture or action")
            session=self._live_sound_session
            try:
                return session.finish() if freeze else session.cancel()
            finally:
                self._live_sound_session=None
                self._live_sound_ticket=None

    def _close(self):
        """Stop accepting JS requests and cancel this window's active workers.

        OS process-tree cleanup remains the responsibility of the original
        supervisor. We wait for its final receipt rather than reporting that
        a mere cancellation signal proved process termination.
        """
        with self._lock:
            if self._closing:
                return
            self._closing=True
            if self._data_av_controller is not None:
                self._data_av_controller.close()
            if self._live_sound_session is not None:
                self._live_sound_session.cancel()
                self._live_sound_session=None
                self._live_sound_ticket=None
            host=self._host
            tickets=list(self._tickets.values())
        if host is not None:
            for item in tickets:
                job=item.get("job_id")
                if not job:
                    continue
                try:
                    # Native application exit is host lifetime cleanup, not a
                    # new creator editing command or Take authorization.
                    host.supervisor.cancel(job)
                except (RuntimeError,ValueError,KeyError):
                    # Interrupted/unproven jobs remain in the journal and
                    # must fail closed at next host recovery.
                    pass
        self._executor.shutdown(wait=True,cancel_futures=True)
