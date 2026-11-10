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

from backend.nvp_plan02c_desktop import NativePlan02CCameraActions
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


class TrustedDesktopCameraBridge(NativePlan02CCameraActions):
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
        self._plan04_active = None
        self._futures = {}
        self._host = None
        self._data_av_controller = None
        self._original_capture_controller = None
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
            "supports_cancel":False,
            "native_data_first_scene":True,
            "legacy_render_retired":True,
            "source_modified":False,
        }

    def request_camera_still(self, payload):
        """DA-06: retired external camera worker cannot be reauthorized."""
        self._native_window()
        raise PermissionError(
            "External camera still/proxy worker retired by DA-06; use native "
            "OpenUSD scene audition. No legacy ticket can be minted.")

    def poll_camera_still(self, ticket_id):
        """DA-06: historical ticket may not expose a stale native PNG."""
        self._native_window()
        raise PermissionError(
            "External camera still/proxy worker retired by DA-06; "
            "historical camera tickets cannot be polled.")

    def cancel_camera_still(self, ticket_id):
        """DA-06: there is no active legacy still worker to cancel."""
        self._native_window()
        raise PermissionError(
            "External camera still/proxy worker retired by DA-06; "
            "no legacy camera cancellation authority remains.")

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

    def data_av_begin(self,request):
        return self._data_av().begin(request)

    def data_av_audio_window(self,session_id,first_sample,count):
        return self._data_av().read_audio(session_id,first_sample,count)

    def data_av_scene_at(self,session_id,tick):
        return self._data_av().scene_at(session_id,tick)

    def data_av_stop(self,session_id):
        return self._data_av().stop(session_id)

    # PLAN-02-B: original microphone capture (not retired camera still IPC).
    def _original_capture(self):
        if self._original_capture_controller is None:
            from backend.nvp_native_capture_desktop import TrustedNativeOriginalCapture
            self._original_capture_controller=TrustedNativeOriginalCapture(
                self.index,native_window=self._native_window,
                ask_native=lambda message: (
                    self._native_window().create_confirmation_dialog(
                        "NVP — Authorize Original Sound",message) is True))
        return self._original_capture_controller

    def data_av_capture_catalog(self,project_id):
        self._native_window()
        from backend.nvp_exact_time_shots import ExactTimeShotSequence
        pid=_require_pid(project_id)
        exact=ExactTimeShotSequence(self.index)
        timelines=[]
        for row in self.index.list_objects(pid,kind="temporal")[:128]:
            try:plan=exact.read(pid,row["object_id"],row["head_revision"])
            except (KeyError,ValueError,RuntimeError):continue
            scene=self.index.read_revision(
                pid,plan["scene_id"],plan["scene_revision"])
            if scene["document_sha256"]!=plan["scene_document_sha256"]:
                raise RuntimeError("Original source camera catalog changed")
            roles=scene["data"].get("prim_roles",{})
            emitters=sorted(roles,key=lambda p:(
                roles[p]!="actor",roles[p]=="camera",p))
            if not emitters:continue
            timelines.append({
                "timeline_id":plan["timeline_id"],
                "revision":plan["revision"],
                "document_sha256":plan["document_sha256"],
                "scene_id":plan["scene_id"],
                "scene_revision":plan["scene_revision"],
                "scene_document_sha256":plan["scene_document_sha256"],
                "duration_tick":plan["duration_tick"],
                "emitter_paths":emitters[:64]})
            if len(timelines)>=32:break
        return {"format":"nvp.data_av.original_capture_catalog.v1",
                "project_id":pid,"timelines":timelines,
                "source_modified":False,
                "creator_approval_not_granted":True}

    def data_av_capture_devices(self):
        self._native_window()
        return self._original_capture().devices()

    def data_av_capture_begin(self,request):
        self._native_window()
        return self._original_capture().begin(request)

    def data_av_capture_status(self):
        self._native_window()
        return self._original_capture().status()

    def data_av_capture_finish(self):
        self._native_window()
        return self._original_capture().finish()

    def data_av_capture_cancel(self):
        self._native_window()
        return self._original_capture().cancel()

    def data_av_capture_interrupted(self,project_id):
        self._native_window()
        return self._original_capture().interrupted(project_id)

    def plan03_render_original_once(self,request):
        """Real installed creator-triggered frozen USD -> contained PNG.

        The browser cannot supply a worker executable, filesystem location,
        Python code, approval answer or resource budget. Each click must
        obtain a NEW genuine OS source review and a SEPARATE OS launch review.
        This is not a FilmIndex publication, 2D source or cinema master.
        """
        self._native_window()
        if self._closing or type(request) is not dict or set(request)!={
                "project_id","selection","selection_sha256","tick"}:
            raise PermissionError("Exact source-only trusted render request required")
        from backend.nvp_film_index import _require_pid
        from backend.nvp_plan03_original_render_host import NativeOriginalSceneRender
        from backend.nvp_plan02d_render_queue import APPROVED
        import base64
        import secrets
        import tempfile
        from pathlib import Path
        pid=_require_pid(request["project_id"])
        selection=request["selection"]
        tick=request["tick"]
        sha=request["selection_sha256"]
        if type(tick) is not int or type(sha) is not str:
            raise PermissionError("Exact original source time and selection SHA required")
        queue=self._plan02d()
        job_id="Plan03SourceRender_"+secrets.token_hex(16)
        queued=queue.enqueue(pid,job_id,selection)
        if queued["selection_sha256"]!=sha:
            raise PermissionError("Source changed before native OS review")
        reviewed=queue.review(pid,job_id,queued["revision"])
        if reviewed["status"]!=APPROVED:
            return {"status":"NATIVE_SOURCE_REVIEW_REFUSED",
                    "original_source_modified":False,
                    "render_worker_started":False}
        # Only one fixed trusted native raster worker is ever launched.
        # Nothing in this path takes an executable, script or output path
        # from JavaScript/model output.
        workspace=(Path(tempfile.gettempdir()).resolve()/
                   "nvp-original-render-derivatives")
        def native_review(scope):
            if self._closing or scope.get("operation")!=(
                    "nvp.plan03.render_original_source_once.v1"):
                return False
            return self._ask(
                "Launch ONE OS-contained original OpenUSD picture render?\\n"+
                "Take SHA: "+scope["take_document_sha256"]+
                "\\nSelection SHA: "+scope["selection_sha256"]+
                "\\nOriginal Film Time tick: "+str(scope["source_tick"])+
                "\\nRAM limit: "+str(scope["memory_mb"])+" MiB"+
                "\\nNo original source modification, FFmpeg or cinema master.")
        try:
            worker=NativeOriginalSceneRender(
                self.index,queue,workspace=workspace,
                ask_native=native_review,memory_mb=1024)
            result=worker.render_once(
                pid,job_id,reviewed["revision"],sha,tick,timeout=90)
            if (result.get("status")!="DERIVED_OPENUSD_IMAGE_ONLY" or
                    result.get("worker_process_tree_custody_verified") is not True or
                    result.get("original_source_immutable") is not True):
                raise RuntimeError("Independent kernel worker report was not accepted")
            png=Path(result["derived_image_path"]).read_bytes()
            if len(png)!=result["png_bytes"] or len(png)>12_000_000:
                raise RuntimeError("Verified derivative changed before UI delivery")
            return {
                "format":"nvp.plan03.trusted_original_scene_render_result.v1",
                "status":"VERIFIED_DERIVED_OS_CONTAINED_PNG",
                "png_sha256":result["png_sha256"],
                "png_base64":base64.b64encode(png).decode("ascii"),
                "source_tick":tick,
                "source_take_sha256":result["take_document_sha256"],
                "native_worker_custody":result["custody_mode"],
                "original_source_modified":False,
                "film_master_approved":False,
            }
        except Exception as exc:
            # Do not leak OS process path, source home, or worker trace into
            # a webview. The trusted local host retains private diagnostics.
            raise RuntimeError("Original scene native worker not accepted; inspect NVP host diagnostics") from exc

    def _begin_plan04(self,project_id,selection_sha256):
        with self._lock:
            if self._plan04_active is not None:
                raise PermissionError("A native Cycles production is already active")
            stop=threading.Event()
            self._plan04_active={
                "project_id":project_id,
                "selection_sha256":selection_sha256,
                "stop":stop,
            }
            return stop

    def _end_plan04(self,stop):
        with self._lock:
            if self._plan04_active is not None and self._plan04_active["stop"] is stop:
                self._plan04_active=None

    def plan04_cancel_cycles(self,request):
        """Cancellation is exact to this window's active original selection."""
        self._native_window()
        if type(request) is not dict or set(request)!={"project_id","selection_sha256"}:
            raise PermissionError("Cancellation requires an exact active source selection")
        pid=_require_pid(request["project_id"])
        selection=_sha(request["selection_sha256"])
        with self._lock:
            active=self._plan04_active
            if (active is None or active["project_id"]!=pid or
                    active["selection_sha256"]!=selection):
                return {"status":"NO_MATCHING_ACTIVE_CYCLES_RENDER",
                        "worker_exit_verified":False}
            active["stop"].set()
        return {"status":"CANCELLATION_REQUESTED_AWAIT_SUPERVISOR",
                "worker_exit_verified":False}

    def plan04_render_cycles_once(self,request):
        """Installed NVP source-bound Blender/Cycles, with TWO real OS reviews.

        Program paths and hashes originate solely in the native host
        configuration (NVP_BLENDER_EXE/SHA256/VERSION), never JavaScript or a
        model. The flat js_api receives only a frozen selected Take/time.
        Separate source and execution OS confirmations are fresh and one-use.
        """
        self._native_window()
        if self._closing or type(request) is not dict or set(request)!={
                "project_id","selection","selection_sha256","tick"}:
            raise PermissionError("Exact original source scope required")
        from backend.nvp_film_index import _require_pid
        from backend.nvp_plan02d_render_queue import APPROVED
        from backend.nvp_plan04_original_cycles import OriginalCyclesProduction
        from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
        from backend.nvp_resource_ledger import TaskLedger
        from pathlib import Path
        import base64
        import os
        import re
        import secrets

        pid=_require_pid(request["project_id"])
        tick=request["tick"]
        sha=request["selection_sha256"]
        if type(tick) is not int or tick<0 or type(sha) is not str or not re.fullmatch(
                "[0-9a-f]{64}",sha):
            raise ValueError("Exact Film Time and verified selection SHA required")
        # The creator configures these in the installed native host. The web
        # page never supplies a process path, hash, Blender script or output.
        exe_path=os.environ.get("NVP_BLENDER_EXE","")
        expected_sha=os.environ.get("NVP_BLENDER_SHA256","")
        expected_version=os.environ.get("NVP_BLENDER_VERSION","")
        executable=Path(exe_path) if exe_path else Path(".")
        if (not executable.is_absolute() or executable.is_symlink() or
                not executable.is_file() or
                not re.fullmatch("[0-9a-f]{64}",expected_sha) or
                not expected_version.startswith("Blender ") or
                len(expected_version)>80):
            raise RuntimeError("Trusted Blender installation is not configured/pinned")
        if sha_file(executable)!=expected_sha:
            raise PermissionError("Native Blender binary changed since configured SHA")
        from backend.nvp_plan02d_source_selection import ExactSourceWindowSelector
        candidate=ExactSourceWindowSelector(self.index).preview(
            pid,request["selection"])
        if candidate["selection_sha256"]!=sha:
            raise PermissionError("Original source changed before OS approval")

        cancel_event=self._begin_plan04(pid,sha)
        try:
            queue=self._plan02d()
            job_id="Plan04Cycles_"+secrets.token_hex(16)
            queued=queue.enqueue(pid,job_id,request["selection"])
            reviewed=queue.review(pid,job_id,queued["revision"])
            if cancel_event.is_set():
                raise InterruptedError("Creator cancelled pending native Cycles approval")
            if reviewed["status"]!=APPROVED:
                return {"status":"NATIVE_SOURCE_REVIEW_REFUSED",
                        "original_source_modified":False,"render_worker_started":False}
            # Keep independent source books outside OS worker-journal subtree.
            workspace=Path(os.environ.get("LOCALAPPDATA") or
                str(Path.home()/ "AppData"/"Local"))/"NVPProductionWorkers"
            ledger=TaskLedger(workspace/"resources")
            supervisor=BlenderWorkerSupervisor(
                workspace/"cycles",blender_executable=executable,
                blender_sha256=expected_sha,blender_version=expected_version,
                activity_ledger=ledger)
            def second_os_confirmation(scope):
                if (self._closing or scope.get("operation")!=
                        "nvp.plan04.openusd_cycles_build_and_independent_reopen.v1"):
                    return False
                return self._ask(
                    "Launch ONE native Blender/Cycles source render and independent reopen?\\n"+
                    "Original Take SHA: "+scope["take_sha256"]+
                    "\\nOriginal scene SHA: "+scope["scene_sha256"]+
                    "\\nBlender binary SHA: "+scope["blender_binary_sha256"]+
                    "\\nOriginal Film Time tick: "+str(scope["source_tick"])+
                    "\\nThe original OpenUSD/PCM stays immutable. No film export.")
            try:
                result=OriginalCyclesProduction(
                    self.index,queue,supervisor,
                    ask_native=second_os_confirmation,
                    cancel_event=cancel_event).render_once(
                    pid,job_id,reviewed["revision"],sha,tick)
                if (result["status"]!="REAL_BLENDER_CYCLES_AND_INDEPENDENT_REOPEN_VERIFIED"
                        or not result["original_scene_take_immutable_after_restart_reopen"]):
                    raise RuntimeError("Real Blender/Cycles independent source check failed")
                png=supervisor.root/result["build_job_id"]/"derived_cycles.png"
                if png.is_symlink() or not png.is_file() or png.stat().st_size>12_000_000:
                    raise RuntimeError("Bounded Cycles PNG missing or replaced")
                # Check the exact bytes delivered across the WebView boundary,
                # not an earlier file hash separated from a fresh read by TOCTOU.
                picture=png.read_bytes()
                import hashlib
                if (not picture or len(picture)>12_000_000 or
                        hashlib.sha256(picture).hexdigest()!=result["derived_png_sha256"]):
                    raise RuntimeError("Delivered Cycles PNG differs from verified worker receipt")
                if cancel_event.is_set():
                    raise InterruptedError("Creator cancelled before derived picture delivery")
                return {
                    "format":"nvp.plan04.trusted_os_blender_cycles_result.v1",
                    "status":result["status"],
                    "png_base64":base64.b64encode(picture).decode("ascii"),
                    "png_sha256":result["derived_png_sha256"],
                    "take_sha256":result["take_sha256"],
                    "scene_sha256":result["scene_sha256"],
                    "source_tick":tick,
                    "engine":"CYCLES_CPU",
                    "independently_reopened":True,
                    "original_source_modified":False,
                    "final_film_published":False,
                }
            except (PermissionError,RuntimeError):
                # Include only a bounded error category in WebView. Native worker
                # journal and private stderr remain in the host-owned workspace.
                raise RuntimeError(
                    "Native Blender/Cycles execution was refused or not accepted; check NVP worker journal")

        except InterruptedError:
            return {"status":"NATIVE_CYCLES_CANCELLED_NO_PUBLICATION",
                    "original_source_modified":False,
                    "film_master_published":False,
                    "worker_exit_verified":False}
        finally:
            self._end_plan04(cancel_event)

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
            if self._plan04_active is not None:
                self._plan04_active["stop"].set()
            if self._data_av_controller is not None:
                self._data_av_controller.close()
            if self._original_capture_controller is not None:
                self._original_capture_controller.close()
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
