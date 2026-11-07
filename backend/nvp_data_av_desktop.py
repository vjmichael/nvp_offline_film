"""DATA-AV-01: native-window-only authorization for FFmpeg-free USD sound.

No FastAPI route, arbitrary filename, external media permission, model tool
or browser-provided worker path exists here. A real OS confirmation binds
one frozen Digital Take SHA, listener, exact bounded source time region;
opaque session IDs never persist after restart or window close.
"""
from __future__ import annotations

import secrets
import threading
import time

from backend.nvp_data_av_scene import FrozenSceneAV,MAX_SAMPLES
from backend.nvp_data_av_usd import spatial_audio_at
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.data_av.native_session.v1"
RATE=48000
CLOCK_TICK=TICKS_PER_SECOND//RATE
MAX_APPROVED_SAMPLES=4*3600*RATE
MAX_SESSIONS=1
SESSION_SECONDS=4*3600


class TrustedDataAVController:
    def __init__(self,index:FilmIndex,*,native_window,ask_native):
        if not isinstance(index,FilmIndex) or not callable(native_window) or not callable(ask_native):
            raise TypeError("FilmIndex and real native-window callbacks required")
        self.index=index
        self._window=native_window
        self._ask=ask_native
        self._lock=threading.RLock()
        self._active=None
        self._closed=False

    def _guard(self):
        if self._closed:
            raise PermissionError("Native data playback is closed")
        self._window()

    def catalog(self,project_id):
        self._guard()
        _require_pid(project_id)
        result=[]
        for row in self.index.list_objects(project_id,kind="take")[:128]:
            rec=self.index.read_revision(project_id,row["object_id"],1)
            data=rec["data"]
            if (rec["kind"]!="take" or
                data.get("format")!="nvp.digital_take.openusd_temporal.v1" or
                data.get("frozen") is not True):
                continue
            scene=self.index.read_revision(
                project_id,data["scene_id"],data["scene_revision"])
            choices=[p for p,role in scene["data"].get("prim_roles",{}).items()
                     if role in ("camera","anchor","actor")]
            if choices:
                result.append({
                    "take_id":row["object_id"],
                    "take_document_sha256":rec["document_sha256"],
                    "duration_tick":str(data["duration_tick"]),
                    "listeners":sorted(choices)[:64],
                })
        return {"format":FORMAT,"status":"AVAILABLE",
                "takes":result,"ffmpeg_runtime_required":False,
                "native_scene_data":True}

    def begin(self,request):
        self._guard()
        if (type(request) is not dict or set(request)!={
            "project_id","take_id","take_document_sha256",
            "listener_path","first_sample","direction"}):
            raise ValueError("Exact source identity and listener required")
        pid=request["project_id"];_require_pid(pid)
        take=request["take_id"];_id(take,"source Digital Take")
        sha=request["take_document_sha256"];_sha(sha)
        listener=request["listener_path"]
        start=request["first_sample"]
        direction=request["direction"]
        if direction not in ("forward","reverse"):
            raise ValueError("Unknown native source playback direction")
        if type(start) is not int or start<0:
            raise ValueError("Invalid requested source sample")
        with self._lock:
            if self._active is not None:
                raise RuntimeError("Stop prior native audition before a new approval")
            before=self.index.read_revision(pid,take,1)
            if before["document_sha256"]!=sha:
                raise PermissionError("Outdated frozen Digital Take")
            total=before["data"]["duration_tick"]//CLOCK_TICK
            if start>=total or (direction=="reverse" and start==0):
                raise ValueError("Requested sound time past source end")
            approved_first=(start if direction=="forward"
                            else max(0,start-MAX_APPROVED_SAMPLES))
            approved_last=(min(total,start+MAX_APPROVED_SAMPLES)
                           if direction=="forward" else start)
            if approved_last<=approved_first:
                raise ValueError("Native audio approval window is empty")
            # Consent covers only one frozen Take, one listener and a finite
            # Film Time segment. There is no approval for media export.
            if not self._ask(
                "Audition native 3D sound from exact frozen Digital Take?\n"+
                "Take: "+take+"\n"+
                "SHA-256: "+sha+"\n"+
                "Listener: "+str(listener)+"\n"+
                "First source sample: "+str(start)+" (48 kHz)\n"+
                "Direction: "+direction+"\n"+
                "Up to four hours. Output: bounded temporary device buffers.\n"+
                "Original scene, performance and sound sources remain frozen.\n"+
                "No FFmpeg, new WAV/BWF recording or flattened film master.\n"+
                "Stop immediately revokes further native audio reads."):
                return {"format":FORMAT,"status":"DENIED",
                        "original_modified":False,"master_approved":False}
            if self.index.read_revision(pid,take,1)["document_sha256"]!=sha:
                raise RuntimeError("Take changed while native consent was displayed")
            session=FrozenSceneAV(
                self.index,pid,take,
                expected_take_sha256=sha,listener_path=listener)
            ticket=secrets.token_urlsafe(32)
            self._active={
                "id":ticket,"session":session,"pid":pid,
                "first":approved_first,"last":approved_last,
                "expires":time.monotonic()+SESSION_SECONDS,
            }
            return {"format":FORMAT,"status":"READY",
                    "session_id":ticket,
                    "take_document_sha256":sha,
                    "listener_path":listener,
                    "first_sample":start,"direction":direction,
                    "approved_first_sample":approved_first,
                    "last_sample_exclusive":approved_last,
                    "sample_rate":RATE,
                    "ffmpeg_runtime_required":False,
                    "original_modified":False,"master_approved":False}

    def _session(self,ticket):
        self._guard()
        if type(ticket) is not str:
            raise PermissionError("Native audition ticket is opaque")
        state=self._active
        if (state is None or state["id"]!=ticket or
            time.monotonic()>=state["expires"]):
            raise PermissionError("Expired or revoked creator-audition ticket")
        return state

    def read_audio(self,ticket,first_sample,count):
        with self._lock:
            state=self._session(ticket)
            if (type(first_sample) is not int or
                type(count) is not int or not 1<=count<=MAX_SAMPLES or
                first_sample<state["first"] or
                first_sample+count>state["last"]):
                raise PermissionError("Native audio request outside creator grant")
            result=state["session"].audio_window(first_sample,count)
            if result["take_document_sha256"]!=state["session"].take[
                "document_sha256"]:
                raise RuntimeError("Native audio result changed source identity")
            return {**result,"session_id":ticket}

    def scene_at(self,ticket,tick):
        with self._lock:
            state=self._session(ticket)
            if (type(tick) is not int or
                tick<state["first"]*CLOCK_TICK or
                tick>=state["last"]*CLOCK_TICK):
                raise PermissionError("Scene query outside creator-approved Film Time")
            source=state["session"]
            snapshot=source.snapshot(tick)
            from backend.nvp_data_av_visual import visual_state
            visual=visual_state(self.index,state["pid"],snapshot)
            overlay=spatial_audio_at(
                self.index,state["pid"],
                source.data["scene_id"],source.data["scene_revision"],
                source.data["timeline_id"],source.data["timeline_revision"],tick)
            return {
                "format":FORMAT,"status":"SCENE_READY",
                "session_id":ticket,
                "take_document_sha256":source.take["document_sha256"],
                "scene":snapshot,"spatial_audio":overlay,
                "visual":visual,
                "original_modified":False,"master_approved":False,
            }

    def freeze_exact_camera_take(self,request):
        """Freeze only a verified exact-time scene+camera event revision.

        A browser can request a freeze but cannot impersonate creator approval:
        the exact scene/timeline SHA scope goes through the real OS dialogue
        inside the Take publisher's own authorization callback.
        """
        self._guard()
        from backend.nvp_exact_time_shots import ExactTimeShotSequence
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        if type(request) is not dict or set(request)!={
            "project_id","take_id","scene_id","scene_revision",
            "scene_document_sha256","timeline_id","timeline_revision",
            "timeline_document_sha256"}:
            raise ValueError("Exact Film Time Take freeze requires pinned source IDs")
        with self._lock:
            if self._active is not None:
                raise PermissionError("Stop ongoing native audition before freezing another Take")
            pid=request["project_id"]
            _require_pid(pid)
            tid=request["take_id"]
            _id(tid,"new immutable Digital Take")
            scene_id=request["scene_id"]
            timeline_id=request["timeline_id"]
            for key in ("scene_document_sha256","timeline_document_sha256"):
                _sha(request[key])
            native=ExactTimeShotSequence(self.index)
            plan=native.read(pid,timeline_id,request["timeline_revision"])
            if (plan["scene_id"]!=scene_id or
                plan["scene_revision"]!=request["scene_revision"] or
                plan["scene_document_sha256"]!=request["scene_document_sha256"] or
                plan["document_sha256"]!=request["timeline_document_sha256"]):
                raise RuntimeError("Creator-selected exact-time source revision changed")
            checkpoints=native.checkpoints(pid,timeline_id,
                                           request["timeline_revision"])
            secret=secrets.token_urlsafe(32)
            confirmed=[False]
            def native_approval(event,scoped):
                if event!=secret or confirmed[0]:
                    return False
                confirmed[0]=True
                if (scoped.get("project_id")!=pid or
                    scoped.get("take_id")!=tid or
                    scoped.get("scene_document_sha256")!=
                        request["scene_document_sha256"] or
                    scoped.get("timeline_document_sha256")!=
                        request["timeline_document_sha256"]):
                    return False
                return self._ask(
                    "Freeze EXACT immutable Digital Take from authored 3D world?\\n"+
                    "Take ID: "+tid+"\\n"+
                    "3D scene SHA-256: "+scoped["scene_document_sha256"]+"\\n"+
                    "Film Time event SHA-256: "+scoped["timeline_document_sha256"]+"\\n"+
                    "Duration ticks: "+str(scoped["duration_tick"])+"\\n"+
                    "This action freezes the scene and shot observations only.\\n"+
                    "No original is changed, no picture frames/movie/audio master are generated.")
            saved=OpenUSDTakeCapture(
                self.index,verify_creator_action=native_approval).freeze(
                    pid,tid,scene_id=scene_id,
                    scene_revision=request["scene_revision"],
                    timeline_id=timeline_id,
                    timeline_revision=request["timeline_revision"],
                    sample_ticks=checkpoints,
                    creator_event=secret)
            return {"format":FORMAT,"status":"FROZEN_DATA_FIRST_TAKE",
                    "take_id":tid,
                    "take_document_sha256":saved["document_sha256"],
                    "scene_document_sha256":plan["scene_document_sha256"],
                    "timeline_document_sha256":plan["document_sha256"],
                    "exact_film_time":True,"frame_based_capture":False,
                    "original_modified":False,"master_approved":False}

    def stop(self,ticket):
        with self._lock:
            state=self._session(ticket)
            state["session"].close()
            self._active=None
            return {"format":FORMAT,"status":"STOPPED",
                    "original_modified":False,"master_approved":False}

    def close(self):
        with self._lock:
            self._closed=True
            if self._active is not None:
                self._active["session"].close()
                self._active=None
