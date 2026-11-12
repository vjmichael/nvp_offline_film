"""Trusted native microphone input for G06; original PCM, never synthesized audio.

The WebView may request start/finish/cancel for a locally-authorized movie but
can never upload or claim to have recorded original microphone bytes.
Audio comes solely from the desktop host's real OS input device (miniaudio).
The native input uses exact 48 kHz mono PCM16LE samples. The callback's frame
count, not wall clock or a video FPS, is the original sound duration.
Sessions are intentionally bounded. A crashed/incomplete session is never
presented as a valid original or a frozen Take; host restart fails closed.
"""
from __future__ import annotations

import array
import hashlib
import secrets
import sys
import threading
import time

from backend.nvp_g06_filming import RATE,MAX_NATIVE_PCM_SECONDS,G06Filming

MAX_BYTES=RATE*2*MAX_NATIVE_PCM_SECONDS


class NativeMicrophoneSession:
    def __init__(self,project_id,scene_id,actor_id,*,session_grant,
                 device_factory=None):
        self.id=secrets.token_hex(16)
        self.project_id=project_id
        self.scene_id=scene_id
        self.actor_id=actor_id
        self.grant=hashlib.sha256(session_grant.encode("utf8")).digest()
        self.device_factory=device_factory
        self.status="new"
        self.device=None
        self.parts=[]
        self.bytes=0
        self.frames=0
        self.started_at=None
        self.error=None
        self.lock=threading.RLock()
        # G09-C host observations do NOT stand in for hardware ADC timestamps.
        self.started_ns=None
        self.stopped_ns=None
        self.first_callback_ns=None
        self.last_callback_ns=None
        self.chunks=0
        self.peak_abs=0
        self.largest_gap_ns=[]

    def _callback(self):
        samples=yield
        while True:
            with self.lock:
                if self.status=="recording" and self.error is None:
                    try:
                        if type(samples) is not array.array or samples.typecode!="h":
                            raise RuntimeError("Native microphone returned invalid samples")
                        if samples:
                            sample_count=len(samples)
                            raw=samples.tobytes()
                            if sys.byteorder!="little":
                                copy=array.array("h",samples)
                                copy.byteswap()
                                raw=copy.tobytes()
                            if len(raw)!=sample_count*2:
                                raise RuntimeError("Original microphone samples were incomplete")
                            if self.bytes+len(raw)>MAX_BYTES:
                                raise RuntimeError("Original sound reached its 120-second limit")
                            now=time.monotonic_ns()
                            if self.first_callback_ns is None:
                                self.first_callback_ns=now
                            elif self.last_callback_ns is not None:
                                gap=now-self.last_callback_ns
                                self.largest_gap_ns.append(gap)
                                self.largest_gap_ns=sorted(
                                    self.largest_gap_ns,reverse=True)[:30]
                            self.last_callback_ns=now
                            self.chunks+=1
                            self.peak_abs=max(self.peak_abs,
                                max(abs(x) for x in samples))
                            self.parts.append(raw)
                            self.bytes+=len(raw)
                            self.frames+=sample_count
                    except Exception as exc:
                        self.error=exc
            samples=yield

    def begin(self):
        with self.lock:
            if self.status!="new":
                raise RuntimeError("Microphone session was already started")
            try:
                factory=self.device_factory
                if factory is None:
                    from backend.nvp_native_live_take import _capture_device
                    factory=_capture_device
                self.device=factory()
                self.status="recording"
                self.started_ns=time.monotonic_ns()
                callback=self._callback()
                next(callback)
                self.device.start(callback)
                self.started_at=time.monotonic()
            except Exception:
                self.status="failed"
                if self.device:
                    try:self.device.close()
                    except Exception:pass
                raise RuntimeError("The microphone could not start. Check its Windows permission.")
        return {"session_id":self.id,"status":"recording",
                "source":"original_microphone","sample_rate":RATE,
                "max_duration_seconds":MAX_NATIVE_PCM_SECONDS}

    def stop(self):
        with self.lock:
            if self.status!="recording":
                raise RuntimeError("No active microphone recording")
            self.status="stopping"
            device=self.device
        try:
            # Native stop can synchronously flush a last PCM callback.
            # Preserve that tail until after stop returns.
            with self.lock:self.status="recording"
            device.stop()
            device.close()
        except Exception:
            with self.lock:
                self.status="failed"
                self.error=RuntimeError("Could not prove microphone capture stopped")
            raise
        with self.lock:
            self.status="stopped"
            self.stopped_ns=time.monotonic_ns()
            self.device=None
            if self.error is not None:
                raise RuntimeError("The microphone recording was interrupted; do not use it")
            if self.frames<1 or self.bytes!=2*self.frames:
                raise RuntimeError("The microphone did not capture usable original sound")
            return b"".join(self.parts)

    def cancel(self):
        with self.lock:
            if self.status in ("cancelled","finished"):return
            dev=self.device
            self.status="cancelling"
        if dev is not None:
            try:
                dev.stop()
                dev.close()
            except Exception as exc:
                with self.lock:self.status="failed";self.error=exc
                raise RuntimeError("Native microphone shutdown needs attention") from exc
        with self.lock:
            self.device=None
            self.parts.clear()
            self.bytes=0
            self.frames=0
            self.status="cancelled"


class G06NativeRecorder:
    def __init__(self):
        self.lock=threading.RLock()
        self.sessions={}
        self.active=None

    @staticmethod
    def _token(token):
        # No token bytes, auth cookie or key ever leaves the host.
        return token if isinstance(token,str) and len(token)>10 else "local-director-ui"

    def _get(self,project_id,session_id,grant):
        session=self.sessions.get(session_id)
        if (session is None or session.project_id!=project_id or
                not secrets.compare_digest(
                    session.grant,hashlib.sha256(self._token(grant).encode("utf8")).digest())):
            raise PermissionError("The recording does not belong to this movie session")
        return session

    def begin(self,project_id,scene_id,actor_id,grant,audit=None,
              long_recording=False):
        with self.lock:
            if self.active:
                raise RuntimeError("The microphone is already recording for a scene")
            if long_recording:
                # Never downgrade encrypted source to ordinary disk capture.
                if audit is None:
                    raise PermissionError("Director source approval is required")
                from backend.nvp_g06_chunked_capture import NativeLongMicrophoneSession
                current=audit.filming.view(project_id,scene_id)
                if not current["stage_ready"] or not current["work_current"]:
                    raise RuntimeError("Approve this scene before recording original audio")
                session=NativeLongMicrophoneSession(project_id,scene_id,actor_id,
                    session_grant=self._token(grant),
                    studio=audit.filming.g05.g04.studio,
                    stage_sha256=current["stage_sha256"],
                    filming=audit.filming)
            else:
                session=NativeMicrophoneSession(project_id,scene_id,actor_id,
                    session_grant=self._token(grant))
            self.sessions[session.id]=session
            self.active=session.id
        try:
            result=session.begin()
            if audit is not None:audit.begin(session)
            return result
        except Exception:
            try:session.cancel()
            except Exception:pass
            with self.lock:
                self.sessions.pop(session.id,None)
                if self.active==session.id:self.active=None
            raise

    def finish(self,project_id,session_id,grant,filming:G06Filming,audit=None):
        with self.lock:
            session=self._get(project_id,session_id,grant)
            if session.status=="recording":
                raw=session.stop()
            elif session.status=="stopped" and getattr(session,"is_long",False) and session.error is None:
                # Only a stopped, fully committed spool may retry publication.
                raw={"sample_count":session.frames,
                    "original_pcm_sha256":session.stream_sha256}
            elif session.status=="stopped" and session.parts and session.error is None:
                # Retry publication after a recoverable DB error. Original
                # bytes remain unchanged in this host until saved successfully.
                raw=b"".join(session.parts)
            else:
                raise RuntimeError("Recording is no longer available or its sample stream was incomplete")
            if self.active==session.id:self.active=None
        receipt=None
        if audit is not None:
            from backend.nvp_g09c_capture import _receipt
            receipt=_receipt(session,raw)
        if getattr(session,"is_long",False):
            result=session.store.publish(filming,receipt)
        else:
            result=filming.record_native_audio(
                project_id,session.scene_id,session.actor_id,raw,
                capture_receipt=receipt)
        with self.lock:
            session.status="finished"
            session.parts.clear()
            session.bytes=0;session.frames=0
            self.sessions.pop(session.id,None)
        return result

    def cancel(self,project_id,session_id,grant,audit=None):
        with self.lock:
            session=self._get(project_id,session_id,grant)
            session.cancel()
            if audit is not None:audit.cancel(session)
            self.sessions.pop(session_id,None)
            if self.active==session_id:self.active=None
        return {"status":"cancelled","original_audio_published":False}

    def active_sessions(self,project_id,scene_id):
        with self.lock:
            return tuple(sid for sid,s in self.sessions.items()
                         if s.project_id==project_id and
                         s.scene_id==scene_id and s.status in (
                             "recording","stopping","stopped"))

    def cancel_project(self,project_id):
        # Called by trusted host whenever a movie is locked or revoked.
        with self.lock:
            ids=[sid for sid,s in self.sessions.items()
                 if s.project_id==project_id]
            for sid in ids:
                self.sessions[sid].cancel()
                self.sessions.pop(sid,None)
                if self.active==sid:self.active=None
