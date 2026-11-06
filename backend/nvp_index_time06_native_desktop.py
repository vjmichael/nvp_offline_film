"""INDEX-TIME-06: trusted installed-desktop import and source-frame still.

Only pywebview js_api exposes this class. FastAPI retains read-only imported
Film Time routes. Browser JS cannot supply media paths, executable paths,
native approval receipts, worker IDs, destination paths or arbitrary scripts.

Imported original video stays on the chosen native volume. A fresh FilmIndex
source revision and NVP-owned frame index anchor a *first provisional*
out-exclusive Film Time clip for visual inspection. The last source frame is
not guessed; all source frames remain in the separate complete source index.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import sys
import threading
import time
from urllib.parse import urlsplit

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex, _require_pid
from backend.nvp_index_time05_desktop_read import FilmTimeDesktopRead
from backend.nvp_temporal_ledger import MAX_TICK

CAP_FORMAT="nvp.index_time06.native_capability.v1"
IMPORT_FORMAT="nvp.index_time06.native_import.v1"
TICKET_FORMAT="nvp.index_time06.preview_ticket.v1"
PREVIEW_FORMAT="nvp.index_time06.verified_png.v1"
PNG_MAGIC=b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES=12*1024*1024
FILE_TYPES=("Video footage (*.mp4;*.mov;*.mkv;*.webm)",)
MEDIA_TYPES={
    ".mp4":"video/mp4", ".mov":"video/quicktime",
    ".mkv":"video/x-matroska", ".webm":"video/webm",
}


def discover_video_tools():
    """Host-controlled bundled executables first; no JS-specified binary.

    Packaging may stage a vetted ffmpeg/ffprobe pair at ffmpeg/ beneath the
    frozen app directory or PyInstaller data root. Fallback supports the
    already-installed tools without requiring command-line operation.
    """
    names=("ffmpeg.exe","ffprobe.exe") if os.name=="nt" else ("ffmpeg","ffprobe")
    roots=[]
    if getattr(sys,"frozen",False):
        roots.extend((Path(getattr(sys,"_MEIPASS",Path(sys.executable).parent)),
                      Path(sys.executable).parent))
    for root in roots:
        paths=(root/"ffmpeg"/names[0],root/"ffmpeg"/names[1])
        if all(p.is_file() and not p.is_symlink() for p in paths):
            return tuple(p.resolve() for p in paths)
    paths=tuple(shutil.which(x) for x in ("ffmpeg","ffprobe"))
    if all(paths):
        pair=tuple(Path(p) for p in paths)
        if all(p.is_file() and not p.is_symlink() for p in pair):
            return tuple(p.resolve() for p in pair)
    return None


class _Consent:
    def __init__(self,token):
        self.token=token


class TrustedFootageDesktop:
    """One window's native authority, event-bound approvals and review jobs."""
    def __init__(self,studio:Studio,*,origin,tools=None,host_factory=None):
        if not isinstance(studio,Studio):
            raise TypeError("Actual NVP Studio required")
        parsed=urlsplit(origin)
        if (parsed.scheme!="http" or parsed.hostname!="127.0.0.1"
            or parsed.port is None or parsed.path not in ("","/")
            or parsed.query or parsed.fragment or parsed.username):
            raise ValueError("Trusted footage IPC requires exact loopback origin")
        self.origin="http://127.0.0.1:"+str(parsed.port)
        self.studio=studio
        self.window=None
        self.root=studio.db_path.resolve().parent/".native-source-review"
        if self.root.is_symlink():
            raise RuntimeError("Native source review root cannot be a symlink")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.index_root=self.root/"indexes"
        self.tools=tuple(Path(p).resolve() for p in tools) if tools else discover_video_tools()
        self.reader=FilmTimeDesktopRead(
            studio,ffprobe_path=self.tools[1] if self.tools else None,
            index_root=self.index_root)
        self._lock=threading.RLock()
        self._import_lock=threading.Lock()
        self._approvals={}
        self._tickets={}
        self._host=None
        self._assembler=None
        self._review_playback=None
        self._assembly_lock=threading.Lock()
        self._host_factory=host_factory
        self._executor=ThreadPoolExecutor(
            max_workers=1,thread_name_prefix="NVP source still")
        self._closed=False

    def _attach_window(self,window):
        for method in ("get_current_url","create_confirmation_dialog",
                       "create_file_dialog"):
            if not callable(getattr(window,method,None)):
                raise TypeError("Native window must provide OS file/consent dialogs")
        if self.window is not None:
            raise RuntimeError("Native source window cannot be rebound")
        self.window=window

    def _window(self):
        if self._closed or self.window is None:
            raise PermissionError("Native footage window is unavailable")
        parsed=urlsplit(self.window.get_current_url() or "")
        if (parsed.scheme!="http" or
            parsed.netloc!=self.origin.removeprefix("http://") or
            parsed.path not in ("","/") or parsed.query or parsed.fragment):
            raise PermissionError("Native IPC denied a different web origin")
        return self.window

    def _confirm(self,content):
        return self._window().create_confirmation_dialog(
            "NVP — Approve Source Operation",content) is True

    def _grant(self,scope):
        event=_Consent(secrets.token_urlsafe(24))
        self._approvals[event.token]=(dict(scope),time.monotonic()+60)
        return event

    def _approve(self,event,scope):
        if type(event) is not _Consent or type(scope) is not dict:
            return False
        with self._lock:
            record=self._approvals.pop(event.token,None)
            return record is not None and time.monotonic()<=record[1] and (
                scope==record[0])

    def _requirements(self):
        if not self.tools or any(not p.is_file() or p.is_symlink()
                                 for p in self.tools):
            raise RuntimeError(
                "NVP could not find its trusted native FFmpeg/FFprobe tools")
        return self.tools

    def video_import_capabilities(self):
        try:return self._video_import_capabilities()
        except Exception:
            return {"format":CAP_FORMAT,"native_window":False,
                    "native_dialog":False,"video_tools_available":False}

    def _video_import_capabilities(self):
        self._window()
        return {
            "format":CAP_FORMAT,"native_window":True,
            "native_dialog":True,
            "video_tools_available":bool(self.tools and all(
                p.is_file() and not p.is_symlink() for p in self.tools)),
            "can_import_original":True,"can_approve_preview":True,
            "can_edit_assembly":True,
            "can_review_assembly_frames":True,
            "original_source_path_to_browser":False,
        }

    def pick_and_import_footage(self,project_id):
        try:return self._pick_and_import_footage(project_id)
        except Exception:
            # Exceptions from pywebview JS API can expose Python tracebacks
            # and original absolute paths. Native errors remain native.
            return {"format":IMPORT_FORMAT,"status":"FAILED",
                    "error_code":"NATIVE_IMPORT_FAILED",
                    "original_modified":False}

    def _pick_and_import_footage(self,project_id):
        """OS picker -> user-approved local original -> immutable source.

        No path or volume root is returned to JS, including if an index
        creation or FilmIndex commit fails midway. Import is serialized to
        avoid two simultaneous OS pickers in the same desktop window.
        """
        self._window()
        _require_pid(project_id)
        self.studio.get_project(project_id)
        _,ffprobe=self._requirements()
        if not self._import_lock.acquire(blocking=False):
            raise RuntimeError("Native footage import already in progress")
        try:
            chosen=self._window().create_file_dialog(
                allow_multiple=False,file_types=FILE_TYPES)
            if not chosen:
                return {"format":IMPORT_FORMAT,"status":"CANCELLED",
                        "original_modified":False}
            if len(chosen)!=1 or type(chosen[0]) is not str:
                raise ValueError("Select exactly one original video")
            file=Path(chosen[0])
            if (not file.is_absolute() or file.suffix.lower() not in MEDIA_TYPES
                or file.is_symlink() or not file.is_file() or
                any(p.is_symlink() for p in file.parents)):
                raise ValueError("Native source must be a local supported regular video")
            size=file.stat().st_size
            if not 0<size<=2**40:
                raise ValueError("Original video exceeds the supported source size")
            if not self._confirm(
                "Register and index this ORIGINAL video without moving it?\n"+
                "File: "+file.name+"\n"+
                "Bytes: "+str(size)+"\n"+
                "NVP will hash and inspect the source using native FFprobe.\n"+
                "An initial source-backed Film Time edit will be created.\n"+
                "The original file will not be modified or copied."):
                return {"format":IMPORT_FORMAT,"status":"DENIED",
                        "original_modified":False}
            from backend.nvp_external_media_catalog import ExternalMediaCatalog
            from backend.nvp_source_media_inventory import SourceMediaInventory
            from backend.nvp_source_film_bridge import SourceFilmBridge
            from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
            from backend.nvp_native_frame_index import NVPFrameIndex
            index=FilmIndex(self.studio)
            catalog=ExternalMediaCatalog(self.studio)
            inventory=SourceMediaInventory(catalog)
            bridge=SourceFilmBridge(index,inventory)
            src="footage_"+secrets.token_hex(12)
            vol="volume_"+secrets.token_hex(12)
            edit="sourcecut_"+secrets.token_hex(12)
            inventory.register_volume(project_id,vol,file.parent,label="Imported footage")
            catalog.register(project_id,src,file,media_type=MEDIA_TYPES[file.suffix.lower()])
            inventory.enrich(project_id,src,vol,ffprobe=str(ffprobe))
            original=bridge.register_source_revision(project_id,src)
            indexed=NVPFrameIndex(self.index_root,ffprobe=ffprobe)
            info=indexed.ensure(project_id,src,original["data"]["content_sha256"],file)
            if info["frame_count"]<2:
                raise RuntimeError(
                    "At least two measured video frames are required for an exact out-exclusive clip")
            # Last indexed source frame has no measured next-frame boundary.
            # Keep it in the original index; do not invent a display interval.
            out=info["frame_count"]-1
            publisher=FilmTimeEditorialPublisher(index,bridge,indexed)
            published=publisher.publish(project_id,edit,[{
                "source_id":src,"source_revision":original["revision"],
                "source_in_frame_zero":0,
                "source_out_frame_zero":out,
                "film_in_tick":0,"rounding":"nearest",
            }])
            if bridge.resolve_source(project_id,src,original["revision"],
                                     verify_bytes=True)["availability"]!="VERIFIED":
                raise RuntimeError("Original bytes changed during import; discard the preview edit")
            return {
                "format":IMPORT_FORMAT,"status":"IMPORTED",
                "project_id":project_id,
                "source_id":src,"source_revision":original["revision"],
                "source_document_sha256":original["document_sha256"],
                "edit_id":edit,"edit_revision":published["revision"],
                "edit_document_sha256":published["document_sha256"],
                "indexed_source_frames":str(info["frame_count"]),
                "placed_frames":str(out),"last_source_frame_unplaced":True,
                "original_modified":False,"original_copied":False,
                "source_hash_verified_at_import":True,
                "film_master_approved":False,
            }
        finally:
            self._import_lock.release()

    def _get_host(self):
        with self._lock:
            if self._host is None:
                self._requirements()
                if self._host_factory is not None:
                    self._host=self._host_factory(self._approve)
                else:
                    from backend.nvp_film_time_window_host import NativeFilmTimeWindowHost
                    from backend.nvp_film_time_window_preflight import FilmTimeWindowPreflight
                    from backend.nvp_resource_ledger import TaskLedger
                    self.reader._seek_resolver()
                    self._host=NativeFilmTimeWindowHost(
                        FilmTimeWindowPreflight(self.reader._publisher),
                        TaskLedger(self.root/"tasks"),self.root/"jobs",
                        verify_creator_action=self._approve,
                        ffmpeg_path=self.tools[0],ffprobe_path=self.tools[1],
                        index_root=self.index_root)
            return self._host

    def request_source_frame_preview(self,request):
        try:return self._request_source_frame_preview(request)
        except Exception:
            return {"format":TICKET_FORMAT,"status":"FAILED",
                    "error_code":"SOURCE_PREVIEW_REFUSED",
                    "film_master_approved":False}

    def _request_source_frame_preview(self,request):
        """Untrusted exact source selection -> scoped OS consent -> worker."""
        self._window()
        if type(request) is not dict or set(request)!={
            "project_id","edit_id","edit_revision",
            "edit_document_sha256","source_tick",
            "source_frame_zero","source_pts"}:
            raise ValueError("Exact indexed source identity required")
        pid=request["project_id"]
        _require_pid(pid)
        revision=request["edit_revision"]
        if type(revision) is not int or not 1<=revision<=1000000:
            raise ValueError("Invalid original edit revision")
        tick_str=request["source_tick"]
        if (type(tick_str) is not str or not tick_str.isascii()
            or not tick_str.isdecimal() or len(tick_str)>19):
            raise ValueError("Exact Film Time must be a decimal string")
        tick=int(tick_str)
        if tick>MAX_TICK:
            raise ValueError("Film Time exceeds native 64-bit limit")
        self._requirements()
        selected=self.reader.seek(
            pid,request["edit_id"],revision,
            expected_edit_sha256=request["edit_document_sha256"],tick=tick)
        if (selected["status"]!="INDEXED_SOURCE_FRAME_SELECTED"
            or selected["source_frame_zero"]!=request["source_frame_zero"]
            or selected["source_pts"]!=request["source_pts"]):
            raise RuntimeError("Selected source frame/PTS changed before native approval")
        host=self._get_host()
        preflight=host.preflight
        scope_args={
            "project_id":pid,"edit_id":request["edit_id"],
            "revision":revision,"clip_ordinal":selected["clip_ordinal"],
            "first_zero":int(selected["source_frame_zero"]),
            "count":1,"mode":"preview",
        }
        plan=preflight.prepare(**scope_args)
        if (plan["edit_document_sha256"]!=request["edit_document_sha256"]
            or plan["frames"][0]["source_pts"]!=int(selected["source_pts"])
            or plan["frames"][0]["film_time_tick"]!=int(selected["frame_film_start_tick"])):
            raise RuntimeError("Live native review preflight disagrees with selected source")
        ticket=secrets.token_urlsafe(24)
        output=self.root/"outputs"
        output.mkdir(mode=0o700,exist_ok=True)
        dest=output/("preview_"+ticket)
        owner={
            "operation":"nvp.native.film_time.review.v1",
            "project_id":pid,"edit_id":request["edit_id"],
            "edit_revision":revision,"edit_document_sha256":request["edit_document_sha256"],
            "clip_ordinal":selected["clip_ordinal"],
            "first_zero":int(selected["source_frame_zero"]),
            "frame_count":1,
            "film_first_tick":int(selected["frame_film_start_tick"]),
            "film_last_tick":int(selected["frame_film_start_tick"]),
            "mode":"preview","destination":str(dest),"ram_mb":1024,
            "source_integrity":plan["source_integrity"],
            "final_master":False,
        }
        if not self._confirm(
            "Decode ONE original source frame for an UNAPPROVED picture study?\n"+
            "Film edit: "+request["edit_id"]+" rev "+str(revision)+"\n"+
            "Source: "+selected["source_id"]+" frame "+selected["source_frame_zero"]+
            " · PTS "+selected["source_pts"]+"\n"+
            "Film Time: "+str(tick)+" ticks\n"+
            "NVP will use a contained CPU FFmpeg worker.\n"+
            "Original untouched; not approved picture or final master."):
            return {"format":TICKET_FORMAT,"status":"DENIED","worker_started":False}
        with self._lock:
            if self._closed:raise PermissionError("Desktop window is shutting down")
            grant=self._grant(owner)
            try:
                queued=host.stage_and_approve(
                    **scope_args,destination=dest,creator_event=grant,
                    ram_mb=1024,duration_s=1800)
            finally:
                self._approvals.pop(grant.token,None)
            if queued["state"]!="QUEUED":
                raise RuntimeError("Native source review was not admitted to the durable queue")
            item={
                "task_id":queued["task_id"],"project_id":pid,
                "edit_id":request["edit_id"],"revision":revision,
                "edit_sha":request["edit_document_sha256"],
                "source_tick":str(tick),"source_frame_zero":selected["source_frame_zero"],
                "source_pts":selected["source_pts"],
                "stop":threading.Event(),
                "future":None,"dispatched_at":time.monotonic(),
                "cancelled":False,
            }
            self._tickets[ticket]=item
            item["future"]=self._executor.submit(
                host.run_next,timeout_seconds=180,
                should_cancel=lambda: item["stop"].is_set() or self._closed)
            if len(self._tickets)>64:
                oldest=next(iter(self._tickets))
                self._tickets.pop(oldest,None)
            return {
                "format":TICKET_FORMAT,"status":"QUEUED",
                "ticket_id":ticket,"project_id":pid,
                "edit_document_sha256":request["edit_document_sha256"],
                "source_tick":str(tick),"source_frame_zero":selected["source_frame_zero"],
                "worker_started":False,"film_master_approved":False,
            }

    def poll_source_frame_preview(self,ticket):
        try:return self._poll_source_frame_preview(ticket)
        except Exception:
            return {"format":PREVIEW_FORMAT,"status":"RECOVERY_REQUIRED",
                    "film_master_approved":False}

    def _poll_source_frame_preview(self,ticket):
        self._window()
        if type(ticket) is not str or not 1<=len(ticket)<=128:
            raise ValueError("Invalid local native preview ticket")
        with self._lock:
            item=self._tickets.get(ticket)
            if item is None:
                raise PermissionError("Unknown or expired native source preview ticket")
            host=self._get_host()
            task=item["task_id"]
            state=host.ledger.get_task(task)
            if state is None:
                raise RuntimeError("Durable native review task missing")
            if item["cancelled"] and state["state"] in ("SUCCEEDED","CANCELLED","FAILED"):
                return {"format":PREVIEW_FORMAT,"status":"CANCELLED",
                        "film_master_approved":False}
            if state["state"]=="SUCCEEDED":
                proof=host.verify_completed(task)
                row=host._row(task)
                sealed=host._plan(task,row)
                frame=sealed["frames"][0]
                if (proof["status"]!="VERIFIED_UNAPPROVED_FILM_TIME_REVIEW"
                    or proof["approved_final"] is not False
                    or sealed["edit_document_sha256"]!=item["edit_sha"]
                    or frame["source_frame_zero"]!=int(item["source_frame_zero"])
                    or frame["source_pts"]!=int(item["source_pts"])
                    or frame["film_time_tick"]>int(item["source_tick"])):
                    raise RuntimeError("Native receipt is not the selected original source")
                path=Path(row["destination"])/"review_000000001.png"
                if (path.is_symlink() or not path.is_file() or
                    path.stat().st_size>MAX_PNG_BYTES):
                    raise RuntimeError("Native preview PNG exceeds bounded IPC or is unavailable")
                media=path.read_bytes()
                if (not media.startswith(PNG_MAGIC) or len(media)<33 or
                    len(media)>MAX_PNG_BYTES):
                    raise RuntimeError("Native preview returned invalid PNG bytes")
                width,height=struct.unpack(">II",media[16:24])
                if not (0<width<=8192 and 0<height<=8192):
                    raise RuntimeError("Unbounded native preview image dimensions")
                receipt=json.loads((Path(row["destination"])/"review_receipt.json").read_bytes())
                if sha256(media).hexdigest()!=receipt["frames"][0]["sha256"]:
                    raise RuntimeError("Native PNG changed after receipt validation")
                return {
                    "format":PREVIEW_FORMAT,"status":"READY",
                    "project_id":item["project_id"],"edit_id":item["edit_id"],
                    "edit_revision":item["revision"],
                    "edit_document_sha256":item["edit_sha"],
                    "source_tick":item["source_tick"],
                    "source_frame_zero":item["source_frame_zero"],
                    "source_pts":item["source_pts"],
                    "image_data_url":"data:image/png;base64,"+
                        base64.b64encode(media).decode("ascii"),
                    "png_sha256":sha256(media).hexdigest(),
                    "source_integrity":proof["source_integrity"],
                    "original_modified":False,"film_master_approved":False,
                }
            if state["state"] in ("FAILED","INTERRUPTED","CANCELLED"):
                return {
                    "format":PREVIEW_FORMAT,
                    "status":"CANCELLED" if item["cancelled"] else "RECOVERY_REQUIRED",
                    "film_master_approved":False,
                }
            future=item["future"]
            if future.done() and state["state"]=="QUEUED":
                try: result=future.result()
                except Exception:
                    return {"format":PREVIEW_FORMAT,
                            "status":"RECOVERY_REQUIRED","film_master_approved":False}
                if (result is None or
                    (isinstance(result,dict) and
                     (result.get("admitted") is False or
                      result.get("task_id")!=task))):
                    if time.monotonic()-item["dispatched_at"]>=3:
                        item["dispatched_at"]=time.monotonic()
                        item["future"]=self._executor.submit(
                            host.run_next,timeout_seconds=180,
                            should_cancel=lambda: item["stop"].is_set() or self._closed)
                else:
                    return {"format":PREVIEW_FORMAT,
                            "status":"RECOVERY_REQUIRED","film_master_approved":False}
            return {"format":PREVIEW_FORMAT,"status":"QUEUED",
                    "film_master_approved":False}

    def cancel_source_frame_preview(self,ticket):
        try:return self._cancel_source_frame_preview(ticket)
        except Exception:
            return {"status":"FAILED","film_master_approved":False}

    def _cancel_source_frame_preview(self,ticket):
        self._window()
        with self._lock:
            item=self._tickets.get(ticket)
            if item is None:
                raise PermissionError("Native source ticket not issued to this window")
            task=item["task_id"]
        if not self._confirm(
            "Cancel the current source-frame preview?\n"+
            "The approved original remains unchanged; contained worker shutdown"+
            " is journaled before reservations are released."):
            return {"status":"DENIED"}
        with self._lock:
            item["cancelled"]=True
            item["stop"].set()
            host=self._get_host()
            state=host.ledger.get_task(task)
            if state and state["state"]=="QUEUED":
                try:
                    host.revoke_queued(task)
                except RuntimeError:
                    pass  # Worker won the admission lease; token is set.
        return {"status":"CANCELLATION_REQUESTED","ticket_id":ticket}

    def _get_assembler(self):
        if self._assembler is None:
            from backend.nvp_index_time07_assembly import IndexedFootageAssembler
            self.reader._seek_resolver()
            self._assembler=IndexedFootageAssembler(self.reader._publisher)
        return self._assembler

    @staticmethod
    def _assembly_request(request,*,commit=False):
        required={"project_id","edit_id","edit_revision",
                  "edit_document_sha256","change"}
        if commit:required.add("plan_sha256")
        if type(request) is not dict or set(request)!=required:
            raise ValueError("Exact source edit and single typed operation required")
        _require_pid(request["project_id"])
        return request

    def preview_footage_assembly(self,request):
        try:
            self._window()
            scope=self._assembly_request(request)
            assembler=self._get_assembler()
            plan=assembler.prepare(
                scope["project_id"],scope["edit_id"],
                scope["edit_revision"],scope["edit_document_sha256"],
                scope["change"])
            # Executable publisher arguments never leave the native host.
            plan.pop("_commit_placements",None)
            return plan
        except Exception:
            return {"format":"nvp.index_time07.assembly_plan.v1",
                    "status":"REFRESH_REQUIRED",
                    "code":"INVALID_OR_CHANGED_EDITORIAL_SOURCE",
                    "original_sources_modified":False}

    def save_footage_assembly(self,request):
        try:
            self._window()
            scope=self._assembly_request(request,commit=True)
            if not self._assembly_lock.acquire(blocking=False):
                return {"format":"nvp.index_time07.assembly_plan.v1",
                        "status":"BUSY","original_sources_modified":False}
            try:
                assembler=self._get_assembler()
                return assembler.commit(
                    scope["project_id"],scope["edit_id"],
                    scope["edit_revision"],scope["edit_document_sha256"],
                    scope["change"],scope["plan_sha256"],
                    confirm=lambda message:self._confirm(message))
            finally:
                self._assembly_lock.release()
        except Exception:
            # pywebview exceptions must not expose original media paths.
            return {"format":"nvp.index_time07.assembly_plan.v1",
                    "status":"REFRESH_REQUIRED",
                    "code":"SOURCE_EDITORIAL_COMMIT_REFUSED",
                    "original_sources_modified":False}

    def _get_review_playback(self):
        with self._lock:
            if self._review_playback is None:
                from backend.nvp_index_time08_playback import NativeAssemblyReview
                self._review_playback=NativeAssemblyReview(self)
            return self._review_playback

    def start_assembly_review(self,request):
        try:return self._get_review_playback().start(request)
        except Exception:
            return {"format":"nvp.index_time08.original_assembly_review.v1",
                    "status":"REFRESH_REQUIRED","original_modified":False,
                    "master_approved":False}

    def poll_assembly_review(self,ticket):
        try:return self._get_review_playback().poll(ticket)
        except Exception:
            return {"format":"nvp.index_time08.original_assembly_review.v1",
                    "status":"RECOVERY_REQUIRED","original_modified":False,
                    "master_approved":False}

    def get_assembly_review_frame(self,ticket,index):
        try:return self._get_review_playback().frame(ticket,index)
        except Exception:
            return {"format":"nvp.index_time08.original_assembly_review.v1",
                    "status":"RECOVERY_REQUIRED","original_modified":False,
                    "master_approved":False}

    def cancel_assembly_review(self,ticket):
        try:return self._get_review_playback().cancel(ticket)
        except Exception:
            return {"format":"nvp.index_time08.original_assembly_review.v1",
                    "status":"RECOVERY_REQUIRED","original_modified":False,
                    "master_approved":False}

    def _close(self):
        with self._lock:
            if self._closed:return
            self._closed=True
            for item in self._tickets.values():
                item["cancelled"]=True
                item["stop"].set()
        # A real worker is stopped by the original contained executor and
        # durable TaskLedger. Never report a mere kill signal as proof.
        # Stop the playback pipeline first; no approved video decoder may
        # outlive the desktop window while we wait for a still-frame worker.
        if self._review_playback is not None:
            self._review_playback.close()
        self._executor.shutdown(wait=True,cancel_futures=False)
