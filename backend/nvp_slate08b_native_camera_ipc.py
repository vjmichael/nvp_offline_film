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
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
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
        info = run_owned_subprocess(
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

    def __init__(self, index: FilmIndex, *, origin, host_factory=None,
                 native_capture_auditor=None):
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
        if native_capture_auditor is not None:
            from backend.nvp_p1a_original_capture_worker_bridge import (
                OriginalMicrophoneNativeWorkerAudit)
            if type(native_capture_auditor) is not OriginalMicrophoneNativeWorkerAudit:
                raise TypeError("Only an original host-provisioned native capture audit may be attached")
        # Host-only injection, never accepted as a browser-supplied capture
        # field or an inferred developer-compiled worker release approval.
        self._native_capture_auditor=native_capture_auditor
        self._original_capture_controller = None
        self._edited_export = None
        self._p1f_export = None
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
        required={"project_id","edit_id","edit_revision",
                  "presentation_id","listener_path"}
        if (type(request) is not dict or
            set(request) not in (required,required|{"playable_preview"}) or
            ("playable_preview" in request and
             type(request["playable_preview"]) is not bool)):
            raise ValueError("Native film export requires an exact typed source/preview request")
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
            if self._p1f_export is not None and not self._p1f_export["future"].done():
                raise RuntimeError("Stop the current original film chunk before a 30-second export")
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
            from backend.nvp_int02_cycles_renderer import build_native_cycles_renderer
            requested=dict(request)
            assembly=self._edited_assembly()
            cancel=threading.Event()
            progress={"stage":"queued","count":0}
            ticket=secrets.token_urlsafe(32)
            cycles_renderer=[None]
            # A whole-film export may take minutes, so do NOT block JS IPC.
            # One native owner worker thread; cancellation is cooperative,
            # staged files are removed without publishing an edited master.
            def perform():
                def update(stage,value):
                    with self._lock:
                        progress.update(stage=stage,count=value)
                def cycles_frame(**kwargs):
                    if cancel.is_set():
                        raise InterruptedError("Creator cancelled native render")
                    if cycles_renderer[0] is None:
                        if self._ask(
                            "NVP must stage exact-time original USD for "+
                            "a supervised Blender Cycles worker. NVP now REQUIRES "+
                            "Windows EFS encryption, including verified encryption "+
                            "of every newly created source file, before any "+
                            "original USD is written. If EFS or key access is "+
                            "unavailable the render is REFUSED, not downgraded "+
                            "to plaintext. The resulting picture/PCM derivative "+
                            "is intentionally UNENCRYPTED outside the original "+
                            "project home. Authorize this exact staging?") is not True:
                            raise PermissionError("Native creator declined plaintext Cycles staging")
                        cycles_renderer[0]=build_native_cycles_renderer(
                            self.index,requested["project_id"],plaintext_consent=True)
                        with self._lock:
                            if self._edited_export is not None and self._edited_export["ticket"]==ticket:
                                self._edited_export["cycles_renderer"]=cycles_renderer[0]
                    return cycles_renderer[0].render_png(**kwargs)
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
                        "Picture engine: OS-CONTAINED Blender Cycles, 1920x1080.\n"+
                        "This remains an unaccepted production render candidate, NOT a cinema master.\n"+
                        "Original USD Takes and editorial revision remain unchanged."),
                    render_png=cycles_frame,
                    cancelled=cancel.is_set,progress=update)
                produced=adapter.export(
                    requested["project_id"],requested["edit_id"],
                    requested["edit_revision"],requested["presentation_id"],
                    derived,listener_path=requested["listener_path"])
                if requested.get("playable_preview") is not True:
                    return produced
                # The source-bound PNG/WAV is independently committed
                # before the optional, separately approved playable view.
                # A refusal must not misreport or erase that verified film.
                from backend.nvp_int02_playable_preview import export_playable_edited_avi
                try:
                    preview=export_playable_edited_avi(
                        assembly,requested["project_id"],requested["edit_id"],
                        requested["edit_revision"],produced["directory"],
                        approve=lambda scope:self._ask(
                            "Create an optional playable single-file AVI from "
                            "the independently VERIFIED 720-frame edit?\n"
                            "Edit SHA: "+scope["edit_sha256"]+"\n"
                            "Source manifest SHA: "+scope["derivative_manifest_sha256"]+"\n"
                            "Destination: "+scope["output_directory"]+"\n"
                            "Video is LOSSY 24fps MJPEG; audio is the original-derived "
                            "48kHz PCM16, without FFmpeg. Output is UNENCRYPTED.\n"
                            "This is NOT an approved cinema master, Dolby mix "
                            "or a source Take. Grant separate one-use export approval?"),
                        cancelled=cancel.is_set,progress=update)
                except PermissionError:
                    return {**produced,"playable_preview_status":"DECLINED_NOT_PUBLISHED"}
                except InterruptedError:
                    return {**produced,"playable_preview_status":"CANCELLED_NOT_PUBLISHED"}
                return {**produced,"playable_preview_status":"PLAYABLE_PREVIEW_VERIFIED",
                        "playable_preview":preview}
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
            renderer=job.get("cycles_renderer")
            if renderer is not None:
                renderer.cancel_active()
        return {"format":"nvp.int02.native_edited_export_ticket.v1",
                "status":"CANCELLATION_REQUESTED_NOT_VERIFIED",
                "original_modified":False,"master_approved":False}

    # P1-D true non-destructive creator source cut assembly.
    # The UI can supply only bounded original segment IDs, source graph refs
    # and integer Film Time cuts. Source scenes/Takes/shot layers are frozen.
    def data_av_film_stage_graph_catalog(self,project_id):
        self._native_window()
        pid=_require_pid(project_id)
        from backend.nvp_digital_slate_branches import (
            DigitalSlateBranches,GRAPH_FORMAT)
        directory=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        graphs=[]
        for row in self.index.list_objects(pid,kind="presentation")[:256]:
            source=self.index.read_revision(
                pid,row["object_id"],row["head_revision"])
            if source["data"].get("format")!=GRAPH_FORMAT:
                continue
            verified=directory.open_graph(
                pid,source["object_id"],source["revision"])
            graphs.append({
                "graph_id":verified["object_id"],
                "graph_revision":verified["revision"],
                "graph_sha256":verified["document_sha256"],
                "scene_id":verified["data"]["scene_id"],
                "branches":[{
                    "branch_id":item["branch_id"],
                    "kind":item["kind"],
                    "take_id":item["take_id"],
                    "shot_id":item["shot_id"],
                    "source_start_tick":str(item["source_start_tick"]),
                    "source_end_tick":str(item["source_end_tick"]),
                    "group_id":item["group_id"],
                    "original_default":item["primary"]}
                    for item in verified["data"]["nodes"]]
            })
        return {"format":"nvp.p1d.native_original_source_graph_catalog.v1",
                "project_id":pid,"graphs":graphs,
                "original_source_modified":False,
                "active_cut_changed":False}

    def data_av_film_stage_edit_draft(self,request):
        self._native_window()
        required={"project_id","graph_id","graph_revision","segments"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Original source cut draft requires an exact slate")
        verified=self._edited_assembly().preview(
            request["project_id"],request["graph_id"],
            request["graph_revision"],request["segments"])
        return {
            "format":"nvp.p1d.native_source_cut_draft.v1",
            "project_id":request["project_id"],
            "graph_id":verified["graph_id"],
            "graph_sha256":verified["graph_document_sha256"],
            "source_segment_sha256":verified["draft_sha256"],
            "normalized_original_segments_sha256":sha256(json.dumps(
                verified["segments"],sort_keys=True,separators=(",",":"),
                ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest(),
            "duration_tick":str(verified["duration_tick"]),
            "segment_count":len(verified["segments"]),
            "draft_uncommitted":True,
            "original_source_modified":False,
            "render_approved":False}

    def data_av_film_stage_edit_commit(self,request):
        self._native_window()
        required={"project_id","graph_id","graph_revision","edit_id",
                  "segments","expected_revision"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Source film edit commit requires exact typed source segments")
        from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
        from backend.nvp_digital_slate_branches import DigitalSlateBranches
        original=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        editor=SlateSequenceAssembly(original,
            verify_editor_action=lambda event,scope:self._ask(
                "Approve a NEW immutable non-destructive original film cut?\n"+
                "Project: "+scope["project_id"]+"\n"+
                "Source slate: "+scope["graph_id"]+" rev "+
                str(scope["graph_revision"])+"\n"+
                "Exact frozen graph SHA: "+scope["graph_document_sha256"]+"\n"+
                "Unique edit ID: "+scope["edit_id"]+"\n"+
                "Original source segments SHA: "+scope["ordered_segment_sha256"]+"\n"+
                "Full Film Time ticks: "+str(scope["duration_tick"])+"\n"+
                "No source Take is rewritten, no automatic retime, "
                "no sound or render/master approval."))
        rec=editor.commit(
            request["project_id"],request["edit_id"],
            graph_id=request["graph_id"],
            graph_revision=request["graph_revision"],
            segments=request["segments"],
            expected_revision=request["expected_revision"],
            editor_event="native_creator")
        reopened=editor.open_edit(
            request["project_id"],rec["object_id"],rec["revision"])
        return {"format":"nvp.p1d.native_original_cut_commit_receipt.v1",
                "status":"IMMUTABLE_EDIT_SOURCE_COMMITTED",
                "edit_id":rec["object_id"],"revision":rec["revision"],
                "edit_sha256":rec["document_sha256"],
                "source_segments_sha256":reopened["data"]["ordered_segment_sha256"],
                "duration_tick":str(reopened["data"]["duration_tick"]),
                "source_modified":False,"render_approved":False}

    # P1-D/E/P2: original creator-facing director's source stages.
    # Strict, reviewed finite methods; no native filesystem path or
    # human-approval token is accepted from the webview.
    def _film_continuity(self):
        from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
        return NativeEditorialContinuity(
            self._edited_assembly(),verify_director_action=lambda *_:False)

    def _film_schedule(self,approval=None):
        from backend.nvp_p2_longform_source_plan import NativeLongformFilmPlan
        assembly=self._edited_assembly()
        from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
        continuity=NativeEditorialContinuity(
            assembly,verify_director_action=lambda *_:False)
        return NativeLongformFilmPlan(
            assembly,continuity,
            verify_creator_action=approval or (lambda *_:False))

    def data_av_film_stage_catalog(self,project_id):
        self._native_window()
        pid=_require_pid(project_id)
        assembly=self._edited_assembly()
        edits=[]
        for row in self.index.list_objects(pid,kind="edit")[:64]:
            rec=assembly.open_edit(pid,row["object_id"],row["head_revision"])
            data=rec["data"]
            # Creator can choose only actual USD cameras/listeners shared
            # across source Takes in this committed non-destructive edit.
            source_roles={}
            camera_choices=None
            listener_choices=None
            for segment in data["segments"]:
                take_id=segment["source_take_id"]
                if take_id not in source_roles:
                    take=self.index.read_revision(pid,take_id,1)
                    if take["document_sha256"]!=segment["source_take_document_sha256"]:
                        raise RuntimeError("Source Take SHA changed in film source catalog")
                    doc=take["data"]
                    scene=self.index.read_revision(
                        pid,doc["scene_id"],doc["scene_revision"])
                    if scene["document_sha256"]!=doc["scene_document_sha256"]:
                        raise RuntimeError("Authentic camera/source scene changed")
                    source_roles[take_id]=scene["data"]["prim_roles"]
                roles=source_roles[take_id]
                cameras={path for path,role in roles.items() if role=="camera"}
                listeners={path for path,role in roles.items()
                           if role in ("camera","anchor","actor")}
                camera_choices=(cameras if camera_choices is None
                                else camera_choices & cameras)
                listener_choices=(listeners if listener_choices is None
                                  else listener_choices & listeners)
            edits.append({
                "edit_id":rec["object_id"],"edit_revision":rec["revision"],
                "edit_sha256":rec["document_sha256"],
                "duration_tick":str(data["duration_tick"]),
                "cameras":sorted(camera_choices or set())[:32],
                "listeners":sorted(listener_choices or set())[:32],
                "segments":[{"segment_id":s["segment_id"],
                             "source_take_id":s["source_take_id"],
                             "source_take_sha256":s["source_take_document_sha256"],
                             "source_shot_id":s["source_shot_id"]}
                            for s in data["segments"]][:500]})
        dialogue=[]
        for row in self.index.list_objects(pid,kind="dialogue")[:128]:
            rec=self.index.read_revision(pid,row["object_id"],row["head_revision"])
            doc=rec["data"]
            if doc.get("format")!="nvp.p1bc.actor_original_dialogue.v1":
                continue
            dialogue.append({
                "dialogue_id":rec["object_id"],"revision":rec["revision"],
                "dialogue_sha256":rec["document_sha256"],
                "actor_id":doc["actor_id"],"take_id":doc["source_take_id"]})
        continuity=[]
        plans=[]
        actor_mixes=[]
        for row in self.index.list_objects(pid,kind="presentation")[:256]:
            rec=self.index.read_revision(pid,row["object_id"],row["head_revision"])
            fmt=rec["data"].get("format")
            if fmt=="nvp.p1d.director_edit_continuity.v1":
                self._film_continuity().open(pid,rec["object_id"],rec["revision"])
                continuity.append({
                    "continuity_id":rec["object_id"],"revision":rec["revision"],
                    "continuity_sha256":rec["document_sha256"],
                    "edit_id":rec["data"]["edit_id"],
                    "edit_sha256":rec["data"]["edit_document_sha256"],
                    "review_status":rec["data"]["review_status"]})
            elif fmt=="nvp.p2.original_film_longform_source_schedule.v1":
                self._film_schedule().open(pid,rec["object_id"],rec["revision"])
                plans.append({"plan_id":rec["object_id"],"revision":rec["revision"],
                              "plan_sha256":rec["document_sha256"],
                              "source_edit_sha256":rec["data"]["edit_document_sha256"],
                              "total_chunks":rec["data"]["total_chunks"],
                              "total_frames":rec["data"]["total_frames"],
                              "longform":rec["data"]["is_thirty_minute_longform"]})
            elif fmt=="nvp.p1e.actor_owned_dry_spatial_bus.v1":
                from backend.nvp_p1e_actor_spatial_bus import NativeActorSpatialBus
                NativeActorSpatialBus(
                    self.index,verify_director_action=lambda *_:False).open(
                    pid,rec["object_id"],rec["revision"])
                actor_mixes.append({
                    "mix_id":rec["object_id"],"revision":rec["revision"],
                    "mix_sha256":rec["document_sha256"],
                    "take_id":rec["data"]["take_id"],
                    "take_sha256":rec["data"]["take_document_sha256"],
                    "listener_path":rec["data"]["listener_path"],
                    "actor_ids":[r["actor_id"] for r in rec["data"]["routes"]],
                })
        return {"format":"nvp.p1def.p2.native_source_stage_catalog.v1",
                "project_id":pid,"edits":edits,"original_dialogue":dialogue,
                "continuity":continuity,"longform_plans":plans,
                "actor_spatial_mixes":actor_mixes,
                "source_modified":False,"export_authorized":False,
                "film_master_approved":False}

    def data_av_film_stage_director_commit(self,request):
        self._native_window()
        required={"project_id","continuity_id","edit_id",
                  "edit_revision","cues","expected_revision"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Director editing requires exact source and segment cue IDs")
        from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
        editor=NativeEditorialContinuity(
            self._edited_assembly(),verify_director_action=lambda event,scope:
            self._ask(
                "Approve one immutable, non-destructive SOURCE CUT review?\n"
                "Project: "+scope["project_id"]+"\n"
                "Director review: "+scope["continuity_id"]+"\n"
                "Edit SHA: "+scope["edit_document_sha256"]+"\n"
                "All segment cues SHA: "+scope["cues_sha256"]+"\n"
                "Continuity: "+scope["review_status"]+"\n"
                "This changes no frozen Take and grants NO export or film master."))
        rec=editor.publish(
            request["project_id"],request["continuity_id"],
            edit_id=request["edit_id"],edit_revision=request["edit_revision"],
            cues=request["cues"],expected_revision=request["expected_revision"],
            creator_event="native_director")
        return {"format":"nvp.p1d.native_director_commit_receipt.v1",
                "status":"ORIGINAL_EDIT_REVIEW_COMMITTED",
                "continuity_id":rec["object_id"],"revision":rec["revision"],
                "document_sha256":rec["document_sha256"],
                "original_source_modified":False,"export_approved":False}

    def data_av_film_stage_actor_bus_commit(self,request):
        self._native_window()
        required={"project_id","mix_id","take_id","listener_path",
                  "routes","expected_revision"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Actor spatial mix needs exact source dialogue routes")
        from backend.nvp_p1e_actor_spatial_bus import NativeActorSpatialBus
        mixer=NativeActorSpatialBus(
            self.index,verify_director_action=lambda event,scope:self._ask(
                "Approve the source ActorID-owned dry stereo bus?\n"
                "Take SHA: "+scope["take_document_sha256"]+"\n"
                "Original dialogue route digest: "+scope["routes_sha256"]+"\n"
                "Listener: "+scope["listener_path"]+"\n"
                "This is NOT a generated voice, HRTF or approved sound master."))
        rec=mixer.publish(
            request["project_id"],request["mix_id"],
            take_id=request["take_id"],listener_path=request["listener_path"],
            routes=request["routes"],expected_revision=request["expected_revision"],
            creator_event="native_director")
        return {"format":"nvp.p1e.native_actor_bus_receipt.v1",
                "status":"SOURCE_DIALOGUE_BUS_COMMITTED",
                "mix_id":rec["object_id"],"revision":rec["revision"],
                "document_sha256":rec["document_sha256"],
                "sound_master_approved":False,"original_pcm_modified":False}

    def data_av_film_stage_longform_publish(self,request):
        self._native_window()
        required={"project_id","plan_id","continuity_id","continuity_revision",
                  "listener_path","camera_path","expected_revision"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Longform source plan requires exact director intent")
        planner=self._film_schedule(
            approval=lambda event,scope:self._ask(
                "Index a source-only original film schedule?\n"
                "Continuity SHA: "+scope["continuity_sha256"]+"\n"
                "Original edited film SHA: "+scope["edit_sha256"]+"\n"
                "All finite source chunks digest: "+scope["chunk_manifest_sha256"]+"\n"
                "Duration Film Time ticks: "+scope["duration_tick"]+"\n"
                "Only a plan. No footage has been generated; no production "
                "worker, installation or film master is authorized."))
        rec=planner.publish(
            request["project_id"],request["plan_id"],
            continuity_id=request["continuity_id"],
            continuity_revision=request["continuity_revision"],
            listener_path=request["listener_path"],
            camera_path=request["camera_path"],
            expected_revision=request["expected_revision"],
            creator_event="native_creator")
        reopened=planner.open(request["project_id"],request["plan_id"],rec["revision"])
        return {"format":"nvp.p2.native_longform_source_plan_receipt.v1",
                "status":"SOURCE_ONLY_LONGFORM_PLAN_INDEXED",
                "plan_id":rec["object_id"],"revision":rec["revision"],
                "document_sha256":rec["document_sha256"],
                "total_frames":reopened["data"]["total_frames"],
                "total_chunks":reopened["data"]["total_chunks"],
                "is_thirty_minute_longform":reopened["data"]["is_thirty_minute_longform"],
                "rendered_frames":0,"film_master_approved":False}

    def data_av_film_stage_longform_page(self,request):
        self._native_window()
        required={"project_id","plan_id","revision","first_index","limit"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Longform page needs exact original source cursor")
        return self._film_schedule().page(
            request["project_id"],request["plan_id"],request["revision"],
            first_index=request["first_index"],limit=request["limit"])

    def data_av_film_stage_longform_audit_page(self,request):
        self._native_window()
        required={"project_id","plan_id","revision","first_index","limit"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Longform derivative audit needs a bounded source page")
        from pathlib import Path
        import os
        home=Path(os.environ["NVP_HOME"])
        if home.is_symlink() or not home.is_dir():
            raise RuntimeError("Native source project home not verified")
        derived=home.parent/"Exports"
        if derived.is_symlink() or not derived.is_dir():
            # No creator-approved picture chunk has been published yet.
            page=self._film_schedule().page(
                request["project_id"],request["plan_id"],request["revision"],
                first_index=request["first_index"],limit=request["limit"])
            return {"format":"nvp.p2.original_film_longform_source_schedule.v1",
                    "status":"NO_VERIFIED_DERIVATIVE_OUTPUT_PARENT",
                    "plan_sha256":page["plan_sha256"],
                    "verified_chunks":[],
                    "missing_chunks":[x["chunk_id"] for x in page["chunks"]],
                    "full_film_master_approved":False}
        return self._film_schedule().reconcile_page(
            request["project_id"],request["plan_id"],request["revision"],
            output_parent=derived,first_index=request["first_index"],
            limit=request["limit"])

    # P1-F: one bounded actor/director-approved original picture+PCM chunk.
    # This production path uses the same existing Windows Job/Linux delegated
    # cgroup supervisor as INT-02C, never a new privileged script runner.
    def data_av_film_stage_chunk_preflight(self,request):
        self._native_window()
        required={"project_id","continuity_id","continuity_revision",
                  "first_frame","frame_count","listener_path","camera_path",
                  "actor_mix_id","actor_mix_revision"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Finite original picture chunk needs exact source metadata")
        from backend.nvp_p1f_sustained_delivery import NativeSustainedPictureSound
        from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
        assembly=self._edited_assembly()
        native=NativeSustainedPictureSound(
            assembly,NativeEditorialContinuity(
                assembly,verify_director_action=lambda *_:False),
            native_creator_approval=lambda *_:False,
            render_png=lambda **_:None)
        return native.preflight(
            request["project_id"],request["continuity_id"],
            request["continuity_revision"],first_frame=request["first_frame"],
            frame_count=request["frame_count"],
            listener_path=request["listener_path"],camera_path=request["camera_path"],
            actor_mix_id=request["actor_mix_id"],
            actor_mix_revision=request["actor_mix_revision"])

    def data_av_film_stage_chunk_begin(self,request):
        self._native_window()
        required={"project_id","continuity_id","continuity_revision",
                  "chunk_id","first_frame","frame_count","listener_path",
                  "camera_path","actor_mix_id","actor_mix_revision"}
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Original P1-F source render requires one finite typed chunk")
        _require_pid(request["project_id"])
        _id(request["chunk_id"],"original picture and PCM chunk identity")
        source={k:v for k,v in request.items() if k!="chunk_id"}
        # Even an invalid request may not consume a grant or create a worker.
        plan=self.data_av_film_stage_chunk_preflight(source)
        from pathlib import Path
        import os
        with self._lock:
            if self._closing:
                raise PermissionError("Creator closed the native picture/sound workspace")
            if (self._p1f_export is not None and
                not self._p1f_export["future"].done()):
                raise RuntimeError("One protected picture/sound chunk at a time")
            if (self._edited_export is not None and
                not self._edited_export["future"].done()):
                raise RuntimeError("Finish or cancel the active 30-second export first")
            if (self._data_av_controller is not None and
                self._data_av_controller._active is not None):
                raise RuntimeError("Stop source audio audition before native film export")
            if (self._original_capture_controller is not None and
                self._original_capture_controller._active is not None):
                raise RuntimeError("Finish native sound capture before authoring derivative")
            home=Path(os.environ["NVP_HOME"])
            if home.is_symlink() or not home.is_dir():
                raise RuntimeError("Trusted original project home unavailable")
            derived=home.parent/"Exports"
            if (home.parent.is_symlink() or derived.is_symlink() or
                derived==home or home in derived.parents):
                raise PermissionError("Plaintext derivatives may not share encrypted source home")
            derived.mkdir(mode=0o700,exist_ok=True)
            if (derived/("P1F_"+request["chunk_id"])).exists():
                raise FileExistsError("Original film chunk ID already exists")
            cancel=threading.Event()
            progress={"stage":"QUEUED_NATIVE_AUTHORIZATION","picture_frames":0}
            ticket=secrets.token_urlsafe(32)
            requested=dict(request)
            cycles_renderer=[None]
            def perform():
                from backend.nvp_p1f_sustained_delivery import NativeSustainedPictureSound
                from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
                from backend.nvp_int02_cycles_renderer import build_native_cycles_renderer
                assembly=self._edited_assembly()
                continuity=NativeEditorialContinuity(
                    assembly,verify_director_action=lambda *_:False)

                def cycles_frame(**kwargs):
                    if cancel.is_set():
                        raise InterruptedError("Creator cancelled finite picture worker")
                    if cycles_renderer[0] is None:
                        if self._ask(
                            "An original OpenUSD source frame requires supervised "
                            "Blender Cycles with Windows EFS or verified protected "
                            "native source staging. NVP refuses any plaintext "
                            "fallback for protected originals. The OUTPUT PNG/WAV "
                            "derivative is intentionally UNENCRYPTED, separate "
                            "from source project storage. Approve this single "
                            "finite original picture worker?") is not True:
                            raise PermissionError("Creator refused exact protected Cycles source staging")
                        cycles_renderer[0]=build_native_cycles_renderer(
                            self.index,requested["project_id"],
                            plaintext_consent=True)
                        with self._lock:
                            if (self._p1f_export is not None and
                                self._p1f_export["ticket"]==ticket):
                                self._p1f_export["cycles_renderer"]=cycles_renderer[0]
                    result=cycles_renderer[0].render_png(**kwargs)
                    with self._lock:
                        progress["stage"]="RENDERING_ORIGINAL_CYCLES"
                        progress["picture_frames"]+=1
                    return result
                exporter=NativeSustainedPictureSound(
                    assembly,continuity,
                    native_creator_approval=lambda scope:self._ask(
                        "Publish ONE source-bound picture+PCM derivative chunk?\n"+
                        "Project: "+scope["project_id"]+"\n"+
                        "Chunk: "+scope["chunk_id"]+"\n"+
                        "Original source plan SHA: "+scope["plan_sha256"]+"\n"+
                        "Output: "+scope["output_directory"]+"\n"+
                        "Finite frames: "+str(scope["frames"])+"\n"+
                        "Requires a new confirmation for every later chunk. "+
                        "No source changes, film master or production install authority."),
                    render_png=cycles_frame,cancelled=cancel.is_set)
                with self._lock:
                    progress["stage"]="AWAITING_CREATOR_OR_RENDER"
                return exporter.export_chunk(
                    requested["project_id"],requested["continuity_id"],
                    requested["continuity_revision"],requested["chunk_id"],
                    derived,first_frame=requested["first_frame"],
                    frame_count=requested["frame_count"],
                    listener_path=requested["listener_path"],
                    camera_path=requested["camera_path"],
                    actor_mix_id=requested["actor_mix_id"],
                    actor_mix_revision=requested["actor_mix_revision"])
            future=self._executor.submit(perform)
            self._p1f_export={"ticket":ticket,"future":future,"cancel":cancel,
                              "progress":progress,"project_id":request["project_id"]}
            return {"format":"nvp.p1f.native_source_chunk_ticket.v1",
                    "status":"QUEUED_NATIVE_APPROVAL","ticket":ticket,
                    "source_plan_sha256":sha256(json.dumps(
                        plan,sort_keys=True,separators=(",",":")).encode("ascii")
                        ).hexdigest(),"frame_count":request["frame_count"],
                    "original_modified":False,"film_master_approved":False}

    def data_av_film_stage_chunk_poll(self,ticket):
        self._native_window()
        with self._lock:
            job=self._p1f_export
            if type(ticket) is not str or job is None or job["ticket"]!=ticket:
                raise PermissionError("Unknown native picture/sound source ticket")
            future=job["future"]
            progress=dict(job["progress"])
        if not future.done():
            return {"format":"nvp.p1f.native_source_chunk_ticket.v1",
                    "status":"RUNNING_OR_AWAITING_NATIVE_APPROVAL",
                    "progress":progress,"original_modified":False,
                    "film_master_approved":False}
        try:
            result=future.result()
        except (PermissionError,InterruptedError) as exc:
            return {"format":"nvp.p1f.native_source_chunk_ticket.v1",
                    "status":"REFUSED_OR_INTERRUPTED",
                    "reason":str(exc)[:250],"original_modified":False,
                    "film_master_approved":False}
        except BaseException as exc:
            return {"format":"nvp.p1f.native_source_chunk_ticket.v1",
                    "status":"FAILED_UNVERIFIED","reason":str(exc)[:250],
                    "original_modified":False,"film_master_approved":False}
        return {"format":"nvp.p1f.native_source_chunk_ticket.v1",
                "status":"INDEPENDENT_SOURCE_CHUNK_VERIFIED_NOT_MASTER",
                "receipt":result,"original_modified":False,
                "film_master_approved":False}

    def data_av_film_stage_chunk_cancel(self,ticket):
        self._native_window()
        with self._lock:
            job=self._p1f_export
            if type(ticket) is not str or job is None or job["ticket"]!=ticket:
                raise PermissionError("Unknown source render cancellation ticket")
            job["cancel"].set()
            worker=job.get("cycles_renderer")
            if worker is not None:worker.cancel_active()
        return {"format":"nvp.p1f.native_source_chunk_ticket.v1",
                "status":"CANCELLATION_REQUESTED_NOT_VERIFIED",
                "original_modified":False,"film_master_approved":False}

    # P1-B: convert registered original GLB bytes, not browser-uploaded
    # arbitrary USD or executable model/texture paths.
    def data_av_actor_asset_catalog(self,project_id):
        self._native_window()
        pid=_require_pid(project_id)
        from backend.nvp_character_assets import CharacterAssets
        from backend.nvp_p1bc_glb_character import (
            ImportedCharacterSources,extract_original_glb_skin)
        store=CharacterAssets(self.index.studio)
        source=ImportedCharacterSources(self.index)
        assets=[]
        unsupported=[]
        for registered in store.list(pid)[:64]:
            record,raw=source._registered(pid,registered["asset_id"])
            if sha256(raw).hexdigest()!=registered["sha256"]:
                raise RuntimeError("Native GLB registry source bytes changed")
            try:
                decoded=extract_original_glb_skin(raw)
            except ValueError as exc:
                # Unsupported complex GLB remains available in the old
                # CharacterAssets workflow; no proxy mesh is substituted.
                unsupported.append({
                    "character_asset_id":registered["asset_id"],
                    "reason":str(exc)[:200]})
                continue
            assets.append({
                "character_asset_id":registered["asset_id"],
                "original_glb_sha256":registered["sha256"],
                "license":registered["license"],
                "attribution":registered["attribution"],
                # The originating file path remains native-host private.
                "vertex_count":decoded["original_vertex_count"],
                "joint_count":len(decoded["joints"]),
                "joints":decoded["joints"],
                "facial_targets":[v["name"] for v in
                                  decoded["skin"].get("facial_targets",[])]})
        return {"format":"nvp.p1bc.native_original_character_assets.v1",
                "project_id":pid,"assets":assets,"unsupported":unsupported,
                "source_material_approximated":False,
                "source_bytes_modified":False,
                "redistribution_rights_independently_verified":False}

    def data_av_actor_scene_cast(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","scene_id","cast","camera_height"}:
            raise ValueError("Native 3D actor casting requires a bounded typed scene plan")
        from backend.nvp_p1bc_scene_cast import NativeActorSceneCasting
        director=NativeActorSceneCasting(
            self.index,verify_director_action=lambda event,scope:self._ask(
                "Create one immutable authored OpenUSD scene with real "
                "source GLB skinned characters?\n"
                "Project: "+scope["project_id"]+"\n"
                "New scene: "+scope["scene_id"]+"\n"
                "Full actor/rig/motion cast digest: "+scope["creator_cast_sha256"]+"\n"
                "Original GLB SHAs:\n"+", ".join(scope["source_glb_shas"])+"\n"
                "Camera height: "+str(scope["camera_height"])+" metres\n"
                "Original source bytes remain unchanged. This is NOT an "
                "approved movie Take or finished picture."))
        result=director.publish(
            request["project_id"],request["scene_id"],
            cast=request["cast"],camera_height=request["camera_height"],
            creator_event="native_creator")
        return {**result,
                "format":"nvp.p1bc.native_actor_scene_cast_receipt.v1",
                "status":"AUTHORITATIVE_ACTOR_SCENE_PUBLISHED"}
    # P1-B/C: typed native ActorID/scene/skinned-rig/original-voice actions.
    # These are not FastAPI routes or arbitrary scene file selectors.
    def data_av_actor_cast(self,project_id):
        self._native_window()
        pid=_require_pid(project_id)
        from backend.nvp_p1bc_actor_registry import ActorDirectory, ACTOR_FORMAT
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        from backend.nvp_temporal_ledger import TemporalLedger
        from backend.nvp_data_av_source import RecordedSoundSources
        actors=ActorDirectory(self.index,verify_director_action=lambda *_:False)
        roster=[]
        for row in self.index.list_objects(pid,kind="actor")[:64]:
            actor=actors.open(pid,row["object_id"],1)
            roster.append({"actor_id":actor["object_id"],
                           "actor_sha256":actor["document_sha256"],
                           "display_name":actor["data"]["display_name"]})
        films=[]
        take_reader=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:False)
        for row in self.index.list_objects(pid,kind="take")[:32]:
            record=self.index.read_revision(pid,row["object_id"],1)
            doc=record["data"]
            if (record["kind"]!="take" or
                doc.get("format")!="nvp.digital_take.openusd_temporal.v1" or
                doc.get("frozen") is not True or
                not doc.get("actor_bindings")):
                continue
            take_reader.verify_take(pid,row["object_id"])
            source,stage=OpenUSDSceneBridge(self.index).open(
                pid,doc["scene_id"],doc["scene_revision"])
            if source["document_sha256"]!=doc["scene_document_sha256"]:
                raise RuntimeError("Actor source USD changed during cast catalog")
            cast={a["actor_id"]:a for a in source["data"]["actor_bindings"]}
            active=TemporalLedger(self.index).events_in(
                pid,doc["timeline_id"],doc["timeline_revision"],
                start_tick=0,end_tick=doc["duration_tick"],limit=500)
            if active.get("next_cursor") is not None:
                raise RuntimeError("Partial original dialogue source cannot become a cast catalog")
            cues=[]
            for event in active["events"]:
                if event["event_kind"]!="dialogue":
                    continue
                actor=cast.get(event["subject_id"])
                if actor is None or event["payload"].get("usd_prim_path")!=actor["path"]:
                    continue
                original=RecordedSoundSources(self.index).describe(
                    pid,event["source_id"],event["source_revision"])
                if original["document_sha256"]!=event["source_document_sha256"]:
                    raise RuntimeError("Original cast PCM source changed")
                cues.append({"event_id":event["event_id"],
                             "actor_id":actor["actor_id"],
                             "usd_prim_path":actor["path"],
                             "start_tick":str(event["start_tick"]),
                             "end_tick":str(event["end_tick"]),
                             "original_pcm_sha256":original["document_sha256"]})
                if len(cues)>128:
                    raise RuntimeError("Native actor dialogue catalog too large")
            films.append({"take_id":record["object_id"],
                          "take_sha256":record["document_sha256"],
                          "cast":source["data"]["actor_bindings"],
                          "original_dialogue":cues})
        return {"format":"nvp.p1bc.native_actor_cast.v1",
                "project_id":pid,"actors":roster,"takes":films,
                "sources_immutable":True,"voices_synthesized":False}

    def data_av_actor_register(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","actor_id","display_name"}:
            raise ValueError("Only one typed original ActorID identity may be registered")
        from backend.nvp_p1bc_actor_registry import ActorDirectory
        directory=ActorDirectory(self.index,verify_director_action=
            lambda event,scope:self._ask(
                "Register one permanent project ActorID?\n"
                "ActorID: "+scope["actor_id"]+"\n"
                "Name: "+request["display_name"]+"\n"
                "Profile SHA: "+scope["profile_sha256"]+"\n"
                "Identity cannot be guessed from a glTF filename, future "
                "voice model, or dialogue text."))
        record=directory.register(
            request["project_id"],request["actor_id"],
            display_name=request["display_name"],creator_event="native_creator")
        return {"format":"nvp.p1bc.native_actor_registration.v1",
                "status":"ACTOR_ID_REGISTERED",
                "actor_id":record["object_id"],
                "actor_sha256":record["document_sha256"],
                "source_modified":False,"voice_synthesized":False}

    def data_av_actor_dialogue_bind(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","dialogue_id","actor_id","take_id","event_id"}:
            raise ValueError("Original ActorID dialogue requires exact source identities")
        from backend.nvp_p1bc_actor_registry import ActorDialogueDirector
        director=ActorDialogueDirector(self.index,verify_director_action=
            lambda event,scope:self._ask(
                "Bind an EXISTING recorded original dialogue event to "
                "one authoritative ActorID?\n"
                "ActorID: "+scope["actor_id"]+"\n"
                "Original Take SHA: "+scope["source_take_sha256"]+"\n"
                "Exact event/voice intent: "+scope["dialogue_intent_sha256"]+"\n"
                "This does NOT synthesize speech, animate lips, or approve a master."))
        record=director.bind(
            request["project_id"],request["dialogue_id"],
            actor_id=request["actor_id"],take_id=request["take_id"],
            event_id=request["event_id"],creator_event="native_creator")
        return {"format":"nvp.p1bc.native_original_dialogue.v1",
                "status":"ORIGINAL_DIALOGUE_BOUND",
                "dialogue_id":record["object_id"],
                "dialogue_sha256":record["document_sha256"],
                "take_modified":False,"voice_synthesized":False}

    def data_av_actor_dialogue_at(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","dialogue_id","revision","tick"}:
            raise ValueError("Original actor dialogue read requires exact identity/time")
        tick=request["tick"]
        if (type(tick) is not str or len(tick)>19 or not tick.isascii()
            or not tick.isdecimal()):
            raise ValueError("Film Time must be exact nonnegative integer ticks")
        from backend.nvp_p1bc_actor_registry import ActorDialogueDirector
        result=ActorDialogueDirector(
            self.index,verify_director_action=lambda *_:False).at(
            request["project_id"],request["dialogue_id"],
            request["revision"],int(tick))
        return {"format":"nvp.p1bc.native_original_dialogue_tick.v1",
                "result":result,"source_modified":False,
                "film_master_approved":False}

    # PLAN-02-B: original microphone capture (not retired camera still IPC).
    def _original_capture(self):
        if self._original_capture_controller is None:
            from backend.nvp_native_capture_desktop import TrustedNativeOriginalCapture
            self._original_capture_controller=TrustedNativeOriginalCapture(
                self.index,native_window=self._native_window,
                ask_native=lambda message: (
                    self._native_window().create_confirmation_dialog(
                        "NVP — Authorize Original Sound",message) is True),
                native_pcm_auditor=self._native_capture_auditor)
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
                renderer=self._edited_export.get("cycles_renderer")
                if renderer is not None:
                    renderer.cancel_active()
            if self._p1f_export is not None:
                self._p1f_export["cancel"].set()
                renderer=self._p1f_export.get("cycles_renderer")
                if renderer is not None:
                    renderer.cancel_active()
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
