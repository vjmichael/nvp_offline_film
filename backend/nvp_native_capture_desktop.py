"""PLAN-02-B: creator-owned native original-sound capture controller.

OS dialogs and project source revision checks live in the first-party host.
Browser/UI data is always untrusted; it cannot grant recording or freeze.
All original PCM belongs to the separate durable capture spool and FilmIndex.
No FFmpeg, intermediate soundtrack/master, arbitrary executable/path, or
replay of an old OS approval.
"""
from __future__ import annotations

import threading
from backend.nvp_film_index import FilmIndex,_require_pid,_sha
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_capture_recovery import OriginalCaptureJournal

FORMAT="nvp.data_av.native_capture_session.v1"
BASE_FIELDS=frozenset((
    "project_id","take_id","scene_id","scene_revision",
    "scene_document_sha256","camera_timeline_id",
    "camera_timeline_revision","camera_timeline_document_sha256",
    "sound_timeline_id","source_id","emitter_path","event_id","subject_id"))
DUAL_FIELDS=frozenset((
    "independent_device_ids","second_source_id","second_emitter_path",
    "second_event_id","second_subject_id"))


class TrustedNativeOriginalCapture:
    """One active recording per trusted desktop process, never one per model."""

    def __init__(self,index:FilmIndex,*,native_window,ask_native,
                 single_device_factory=None,dual_device_factory=None):
        if not isinstance(index,FilmIndex) or not callable(native_window) or not callable(ask_native):
            raise TypeError("Actual FilmIndex and trusted native-window confirmation required")
        self.index=index
        self.native_window=native_window
        self.ask_native=ask_native
        # Factories are host-only test/sealed adapter dependencies, never
        # accepted from a JavaScript request or remembered authorization.
        self.single_device_factory=single_device_factory
        self.dual_device_factory=dual_device_factory
        self._lock=threading.RLock()
        self._active=None
        self._closed=False

    def _guard(self):
        if self._closed:
            raise PermissionError("Native original-capture controller is closed")
        self.native_window()

    def _source(self,request):
        if type(request) is not dict or set(request) not in (
                BASE_FIELDS,BASE_FIELDS|DUAL_FIELDS):
            raise ValueError("Capture requires exact original source IDs and optional dual device identities")
        pid=request["project_id"]
        _require_pid(pid)
        if type(request["scene_revision"]) is not int or type(request["camera_timeline_revision"]) is not int:
            raise ValueError("Original revisions must be exact integers")
        _sha(request["scene_document_sha256"])
        _sha(request["camera_timeline_document_sha256"])
        source=self.index.read_revision(pid,request["scene_id"],request["scene_revision"])
        if source["kind"]!="scene" or source["document_sha256"]!=request["scene_document_sha256"]:
            raise PermissionError("Original scene source identity changed")
        shots=ExactTimeShotSequence(self.index).read(
            pid,request["camera_timeline_id"],request["camera_timeline_revision"])
        if (shots["scene_id"]!=request["scene_id"] or
            shots["scene_revision"]!=request["scene_revision"] or
            shots["scene_document_sha256"]!=request["scene_document_sha256"] or
            shots["document_sha256"]!=request["camera_timeline_document_sha256"]):
            raise PermissionError("Original camera Film Time plan is stale or foreign")
        return pid,source,shots

    def devices(self):
        """Read-only OS enumeration; failure does not invent valid endpoints."""
        self._guard()
        from backend.nvp_native_independent_take import native_input_devices
        return {"format":FORMAT,"input_devices":native_input_devices(),
                "physical_clock_acceptance":False,"source_modified":False}

    def begin(self,request):
        self._guard()
        with self._lock:
            if self._active is not None:
                raise RuntimeError("A native original recording already owns this desktop")
            pid,scene,shots=self._source(request)
            keys=set(request)
            dual=keys==BASE_FIELDS|DUAL_FIELDS
            from backend.nvp_native_live_take import NativeLiveSoundSession
            from backend.nvp_native_independent_take import IndependentNativeSoundSession
            session_class=IndependentNativeSoundSession if dual else NativeLiveSoundSession
            described="two independent native audio devices" if dual else "one native microphone"
            expected_scene=scene["document_sha256"]
            expected_camera=shots["document_sha256"]
            def consent_start(scope):
                if (scope.get("project_id")!=pid or
                    scope.get("take_id")!=request["take_id"] or
                    scope.get("scene_sha256")!=expected_scene or
                    scope.get("camera_timeline_sha256")!=expected_camera or
                    scope.get("source_id")!=request["source_id"]):
                    return False
                return self.ask_native(
                    "Start recording ORIGINAL immutable film sound?\n"
                    "Project: "+pid+"\nTake: "+request["take_id"]+
                    "\nScene SHA: "+expected_scene+
                    "\nCamera Film Time SHA: "+expected_camera+
                    "\nInput: "+described+"\n"
                    "No model or browser authority; no soundtrack or movie export.")
            def consent_freeze(event,scope):
                if (scope.get("operation")!="nvp.freeze.usd_temporal_take.v1" or
                    scope.get("project_id")!=pid or
                    scope.get("take_id")!=request["take_id"] or
                    scope.get("scene_document_sha256")!=expected_scene):
                    return False
                return self.ask_native(
                    "Freeze a NEW original Digital Take from recorded source?\n"
                    "Project: "+pid+"\nTake: "+request["take_id"]+
                    "\nScene SHA: "+expected_scene+
                    "\nCombined original event SHA: "+str(scope.get("timeline_document_sha256"))+
                    "\nPreserve original audio and scene; do not master a film.")
            kwargs={key:request[key] for key in BASE_FIELDS
                    if key not in ("scene_document_sha256","camera_timeline_document_sha256")}
            kwargs.update(index=self.index,
                native_approve_start=consent_start,
                native_approve_freeze=consent_freeze)
            if dual:
                for key in DUAL_FIELDS:kwargs[key]=request[key]
                if self.dual_device_factory is not None:
                    kwargs["device_factory"]=self.dual_device_factory
            elif self.single_device_factory is not None:
                kwargs["device_factory"]=self.single_device_factory
            session=session_class(**kwargs)
            started=session.begin()
            self._active=session
            return {"format":FORMAT,"status":started["status"],
                    "take_id":request["take_id"],
                    "scene_document_sha256":expected_scene,
                    "camera_timeline_document_sha256":expected_camera,
                    "capture_mode":"dual_independent_adc" if dual else "native_mono",
                    "original_pcm_durable":False,"original_modified":False,
                    "human_freeze_approval_required":True,
                    "physical_hardware_acceptance":False}

    def status(self):
        self._guard()
        with self._lock:
            if self._active is None:
                return {"format":FORMAT,"status":"IDLE",
                        "original_modified":False}
            return {"format":FORMAT,**self._active.status,
                    "original_modified":False}

    def finish(self):
        self._guard()
        with self._lock:
            if self._active is None:
                raise RuntimeError("No creator-authorized microphone recording exists")
            session=self._active
            try:
                result=session.finish()
                return {"format":FORMAT,**result,
                        "physical_hardware_acceptance":False}
            finally:
                # Durable original spool/journal owns unapproved failures;
                # never auto-restart or reuse a consumed recording authority.
                self._active=None

    def cancel(self):
        self._guard()
        with self._lock:
            if self._active is None:
                return {"format":FORMAT,"status":"IDLE","take_created":False}
            session=self._active
            try:
                return {"format":FORMAT,**session.cancel()}
            finally:
                self._active=None

    def interrupted(self,project_id):
        self._guard()
        _require_pid(project_id)
        return OriginalCaptureJournal(
            self.index.studio.db_path.parent/"native-original-capture-recovery"
        ).catalog(project_id)

    def close(self):
        """Native window exit cancels only owned recording; no auto-freeze."""
        with self._lock:
            if self._closed:return
            self._closed=True
            session=self._active
            self._active=None
            if session is not None:
                try:session.cancel()
                except (RuntimeError,ValueError,OSError):
                    # Preserve sealed/partial original PCM for explicit
                    # creator recovery; never report a frozen Take.
                    pass
