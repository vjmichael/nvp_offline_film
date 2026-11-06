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
    """Probe an installed native Blender, never accept an executable from JS."""
    path = os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE") or shutil.which("blender")
    if not path:
        return None
    candidate = Path(path).resolve()
    if not candidate.is_file() or candidate.is_symlink():
        return None
    return candidate


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
        self._native_window()
        return {
            "format":"nvp.camera.desktop_capability.v1",
            "native_window":True,
            "blender_discovered":discover_blender() is not None,
            "supports_approved_still":True,
            "supports_cancel":True,
            "source_modified":False,
        }

    def request_camera_still(self, payload):
        """Untrusted JSON -> exact FilmIndex identity -> native OS approval."""
        self._native_window()
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
            }
            if len(self._tickets)>64:
                # Discard only in-memory GUI tokens; never a native job or source.
                oldest=next(iter(self._tickets))
                self._tickets.pop(oldest,None)
            if result["status"]=="QUEUED":
                future=self._executor.submit(host.run_next)
                self._futures[ticket]=future
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
                future=self._futures.get(ticket_id)
                if future is not None and future.done():
                    try:
                        future.result()
                    except Exception:
                        return {"status":"RECOVERY_REQUIRED",
                                "film_master_approved":False}
                row=host.cache._job(item["job_id"])
                if row["state"] in ("FAILED","INTERRUPTED","EVICTED"):
                    return {"status":"FAILED","film_master_approved":False}
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

    def _close(self):
        """Do not lie about native termination; recover on the next launch."""
        self._executor.shutdown(wait=False,cancel_futures=False)
