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
        self._futures = {}
        self._host = None
        self._data_av_controller = None
        self._original_capture_controller = None
        self._edited_export = None
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


    # INT-02: committed non-destructive slate edit -> bounded original-film
    # derivative, never a public HTTP route or JS-authorized filesystem path.
    def _edited_assembly(self):
        from backend.nvp_digital_slate_branches import DigitalSlateBranches
        from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
        # Read-only opening of a previously human-committed edit. Neither
        # callback can be used to publish a new edit or choose a cut.
        slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda event,scope:False)
        return SlateSequenceAssembly(
            slate,verify_editor_action=lambda event,scope:False)

    def data_av_edited_30s_catalog(self,project_id):
        self._native_window()
        _require_pid(project_id)
        from backend.nvp_int02_edited_film import NativeEditedFilm30s
        adapter=NativeEditedFilm30s(
            self._edited_assembly(),
            native_creator_approval=lambda scope:False,
            render_png=lambda **kw:None)
        rows=[]
        for obj in self.index.list_objects(project_id,kind="edit")[:128]:
            try:
                plan=adapter.preflight(project_id,obj["object_id"],
                                       obj["head_revision"])
                listener_choices=None
                for seg in plan["segments"]:
                    take=self.index.read_revision(project_id,seg["source_take_id"],1)
                    data=take["data"]
                    scene=self.index.read_revision(
                        project_id,data["scene_id"],data["scene_revision"])
                    if scene["document_sha256"]!=data["scene_document_sha256"]:
                        raise RuntimeError("Frozen edited scene identity changed")
                    possible={p for p,kind in scene["data"]["prim_roles"].items()
                              if kind=="camera"}
                    listener_choices=(possible if listener_choices is None
                                      else listener_choices & possible)
                listeners=sorted(listener_choices or set())[:32]
                if listeners:
                    rows.append({
                        "edit_id":plan["edit_id"],
                        "edit_revision":plan["edit_revision"],
                        "edit_sha256":plan["edit_sha256"],
                        "segment_count":len(plan["segments"]),
                        "listeners":listeners})
            except (KeyError,ValueError,TypeError,RuntimeError):
                continue
            if len(rows)>=32:
                break
        return {"format":"nvp.int02.native_edited_catalog.v1",
                "project_id":project_id,"edits":rows,
                "source_modified":False,"master_approved":False}

    def data_av_edited_30s_preflight(self,project_id,edit_id,edit_revision):
        self._native_window()
        from backend.nvp_int02_edited_film import NativeEditedFilm30s
        # The preview does not require a renderer or approval capability.
        adapter=NativeEditedFilm30s(
            self._edited_assembly(),
            native_creator_approval=lambda scope:False,
            render_png=lambda **kw:None)
        return adapter.preflight(project_id,edit_id,edit_revision)

    def data_av_edited_30s_begin(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","edit_id","edit_revision",
                "presentation_id","listener_path"}:
            raise ValueError("Native film export requires exact committed edit identity")
        _require_pid(request["project_id"])
        _id(request["edit_id"],"committed film edit")
        _id(request["presentation_id"],"unique derived film output")
        if type(request["edit_revision"]) is not int or request["edit_revision"]<1:
            raise ValueError("Invalid committed edit revision")
        listener=request["listener_path"]
        if type(listener) is not str or not listener.startswith("/World/") or len(listener)>240:
            raise ValueError("Native film listener must be an authored USD object")
        with self._lock:
            if self._closing:
                raise PermissionError("Native desktop is closing")
            if self._edited_export is not None and not self._edited_export["future"].done():
                raise RuntimeError("Stop or finish the previous edited film before a new export")
            if (self._data_av_controller is not None and
                self._data_av_controller._active is not None):
                raise RuntimeError("Stop active source audition before edited film export")
            if (self._original_capture_controller is not None and
                self._original_capture_controller._active is not None):
                raise RuntimeError("Finish original sound capture before edited film export")
            import os
            from pathlib import Path
            home=Path(os.environ["NVP_HOME"])
            if home.is_symlink() or not home.is_dir():
                raise RuntimeError("Trusted native project home unavailable")
            # A user-authorized plaintext delivery must NOT be placed
            # inside the original project's potentially encrypted home.
            # The source and output roots remain disjoint.
            derived=home.parent/"Exports"
            if (home.parent.is_symlink() or derived.is_symlink() or
                derived==home or home in derived.parents):
                raise PermissionError("Edited plaintext export cannot share protected original storage")
            derived.mkdir(mode=0o700,exist_ok=True)
            from backend.nvp_int02_edited_film import NativeEditedFilm30s
            from backend.nvp_native_cpu_raster import NativeSourceRaster
            requested=dict(request)
            assembly=self._edited_assembly()
            raster=NativeSourceRaster(self.index,requested["project_id"])
            cancel=threading.Event()
            progress={"stage":"queued","count":0}
            ticket=secrets.token_urlsafe(32)
            # A whole-film export may take minutes, so do NOT block JS IPC.
            # One native owner worker thread; cancellation is cooperative,
            # staged files are removed without publishing an edited master.
            def perform():
                def update(stage,value):
                    with self._lock:
                        progress.update(stage=stage,count=value)
                adapter=NativeEditedFilm30s(
                    assembly,native_creator_approval=lambda scope:self._ask(
                        "Export exact committed 30-second edited film?\n"+
                        "Project: "+scope["project_id"]+"\n"+
                        "Edit: "+scope["edit_id"]+" rev "+
                            str(scope["edit_revision"])+"\n"+
                        "Edit SHA-256: "+scope["edit_sha256"]+"\n"+
                        "Source sequence SHA-256: "+scope["segment_sha256"]+"\n"+
                        "Output: "+scope["output_directory"]+"\n"+
                        "720 native picture samples + 1,440,000 original PCM samples.\n"+
                        "IMPORTANT: this EXPORT is an UNENCRYPTED PNG/WAV derivative\n"+
                        "outside the original project store; protect its files yourself.\n"+
                        "It is NOT a production cinema master.\n"+
                        "Original USD Takes and editorial revision remain unchanged."),
                    render_png=raster.render_png,
                    cancelled=cancel.is_set,progress=update)
                return adapter.export(
                    requested["project_id"],requested["edit_id"],
                    requested["edit_revision"],requested["presentation_id"],
                    derived,listener_path=requested["listener_path"])
            future=self._executor.submit(perform)
            self._edited_export={"ticket":ticket,"future":future,
                                 "cancel":cancel,"progress":progress,
                                 "project_id":request["project_id"]}
            return {"format":"nvp.int02.native_edited_export_ticket.v1",
                    "status":"QUEUED_NATIVE_APPROVAL","ticket":ticket,
                    "original_modified":False,"master_approved":False}

    def data_av_edited_30s_poll(self,ticket):
        self._native_window()
        with self._lock:
            job=self._edited_export
            if type(ticket) is not str or job is None or job["ticket"]!=ticket:
                raise PermissionError("Unknown edited film export ticket")
            future=job["future"]
            progress=dict(job["progress"])
        if not future.done():
            return {"format":"nvp.int02.native_edited_export_ticket.v1",
                    "status":"RUNNING_OR_AWAITING_NATIVE_APPROVAL",
                    "progress":progress,"original_modified":False,
                    "master_approved":False}
        try:
            finished=future.result()
        except (PermissionError,InterruptedError) as error:
            return {"format":"nvp.int02.native_edited_export_ticket.v1",
                    "status":"REFUSED_OR_INTERRUPTED",
                    "reason":str(error)[:250],"original_modified":False,
                    "master_approved":False}
        except BaseException as error:
            return {"format":"nvp.int02.native_edited_export_ticket.v1",
                    "status":"FAILED_UNVERIFIED",
                    "reason":str(error)[:250],"original_modified":False,
                    "master_approved":False}
        return {"format":"nvp.int02.native_edited_export_ticket.v1",
                "status":"DERIVED_VERIFIED_NOT_MASTER",
                "receipt":finished,"original_modified":False,
                "master_approved":False}

    def data_av_edited_30s_cancel(self,ticket):
        self._native_window()
        with self._lock:
            job=self._edited_export
            if type(ticket) is not str or job is None or job["ticket"]!=ticket:
                raise PermissionError("Unknown edited film cancellation ticket")
            job["cancel"].set()
        return {"format":"nvp.int02.native_edited_export_ticket.v1",
                "status":"CANCELLATION_REQUESTED_NOT_VERIFIED",
                "original_modified":False,"master_approved":False}

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
            if self._edited_export is not None:
                self._edited_export["cancel"].set()
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
