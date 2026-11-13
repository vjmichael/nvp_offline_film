"""DA-02/03: trusted live microphone capture into an immutable 3D Take.

The microphone is an original *sound signal*, not the source of picture
or a flattened movie. The event and original OpenUSD world use exact
Film Time. Only the native host can choose the device and approve start,
freeze or cancellation; browser/model inputs contain IDs, never paths.
A bounded callback queue is drained to disk off the realtime audio thread.

Miniaudio's default capture device produces mono signed16 48-kHz samples.
A fake device factory is injectable only by the trusted Python constructor
for isolated tests, never through the pywebview bridge.
"""
from __future__ import annotations

import array
from hashlib import sha256
import os
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import threading

from backend.nvp_capture_recovery import OriginalCaptureJournal
from backend.nvp_data_first_filming import NativeSceneSoundCapture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.data_av.live_mic_take.v1"
RATE=48000
SAMPLE_TICK=TICKS_PER_SECOND//RATE
CHUNK_BYTES=1024*1024
MAX_SECONDS=600
MAX_QUEUE=24


def _capture_device():
    import miniaudio
    return miniaudio.CaptureDevice(
        input_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,sample_rate=RATE,buffersize_msec=40,
        app_name="NVP Original Sound Capture")


class NativeLiveSoundSession:
    def __init__(self,index:FilmIndex,*,project_id,take_id,
                 scene_id,scene_revision,
                 camera_timeline_id,camera_timeline_revision,
                 sound_timeline_id,source_id,emitter_path,
                 event_id,subject_id,
                 native_approve_start,native_approve_freeze,
                 device_factory=None,native_pcm_auditor=None):
        if not isinstance(index,FilmIndex):
            raise TypeError("Live recording requires original FilmIndex")
        if not callable(native_approve_start) or not callable(native_approve_freeze):
            raise TypeError("Native OS capture and freeze confirmations required")
        _require_pid(project_id)
        for value in (take_id,scene_id,camera_timeline_id,
                      sound_timeline_id,source_id,event_id,subject_id):
            _id(value,"native filming identity")
        if len({take_id,scene_id,camera_timeline_id,sound_timeline_id,
                source_id})!=5:
            raise ValueError("Source, scene, camera and take IDs cannot collide")
        self.index=index
        self.project_id=project_id
        self.take_id=take_id
        self.scene_id=scene_id
        self.scene_revision=scene_revision
        self.camera_id=camera_timeline_id
        self.camera_revision=camera_timeline_revision
        self.sound_id=sound_timeline_id
        self.source_id=source_id
        self.emitter_path=emitter_path
        self.event_id=event_id
        self.subject_id=subject_id
        self.approve_start=native_approve_start
        self.approve_freeze=native_approve_freeze
        self.device_factory=device_factory or _capture_device
        if native_pcm_auditor is not None:
            from backend.nvp_p1a_original_capture_worker_bridge import OriginalMicrophoneNativeWorkerAudit
            if type(native_pcm_auditor) is not OriginalMicrophoneNativeWorkerAudit:
                raise TypeError("Host-only compiled original microphone worker audit required")
        self.native_pcm_auditor=native_pcm_auditor
        self._sealed_original_sha=None
        self.plan=ExactTimeShotSequence(index).read(
            project_id,camera_timeline_id,camera_timeline_revision)
        if (self.plan["scene_id"]!=scene_id or
                self.plan["scene_revision"]!=scene_revision or
                emitter_path not in self._prim_roles()):
            raise RuntimeError("Microphone source not bound to verified authored scene")
        self.max_samples=min(int(self.plan["duration_tick"])//SAMPLE_TICK,
                             MAX_SECONDS*RATE)
        if self.max_samples<1:
            raise ValueError("No finite exact-time microphone capture interval")
        self._state="NEW"
        self._queue=queue.Queue(maxsize=MAX_QUEUE)
        self._worker=None
        self._device=None
        self._tmp=None
        self._spool=None
        self._count=0
        self._error=None
        self._total_queued=0
        self._lock=threading.Lock()
        # This is trusted host storage beside the existing project DB,
        # never a browser/model-supplied recovery path. Interrupted PCM
        # remains unapproved and inspectable after process loss.
        self._journal=OriginalCaptureJournal(
            index.studio.db_path.parent/"native-original-capture-recovery")

    def _prim_roles(self):
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        scene,_=OpenUSDSceneBridge(self.index).open(
            self.project_id,self.scene_id,self.scene_revision)
        if scene["document_sha256"]!=self.plan["scene_document_sha256"]:
            raise RuntimeError("Original camera scene SHA changed")
        return scene["data"]["prim_roles"]

    def _append(self,samples):
        # Device stop() can synchronously flush a final valid PCM callback.
        # FINALIZING remains writable until stop() returns, after which the
        # writer's sentinel is queued. Silently dropping tail samples there
        # would violate the exact sound-source sample ledger.
        if self._error is not None or self._state not in (
                "AUTHORIZING","RECORDING","FINALIZING"):
            return
        if not isinstance(samples,array.array) or samples.typecode!="h":
            self._error=RuntimeError("Capture callback returned non-PCM16 frames")
            return
        if not samples:return
        raw=samples.tobytes()
        if sys.byteorder!="little":
            converted=array.array("h",samples)
            converted.byteswap()
            raw=converted.tobytes()
        with self._lock:
            self._total_queued+=len(raw)//2
            if (len(raw)>CHUNK_BYTES or
                    self._total_queued>self.max_samples):
                self._error=RuntimeError("Native microphone exceeded source bound")
                return
        try:self._queue.put_nowait(raw)
        except queue.Full:
            self._error=RuntimeError("Microphone queue overran disk writer")
            # Never drop samples and silently approve a discontinuous Take.

    def _callback(self):
        samples=yield
        while True:
            self._append(samples)
            samples=yield

    def _writer(self):
        try:
            with self._spool.open("xb") as out:
                while True:
                    packet=self._queue.get()
                    if packet is None:break
                    out.write(packet)
                    self._count+=len(packet)//2
                out.flush();os.fsync(out.fileno())
        except Exception as exc:
            self._error=exc

    def begin(self):
        if self._state!="NEW":raise RuntimeError("Live capture already attempted")
        scope={"format":FORMAT,"project_id":self.project_id,
               "take_id":self.take_id,"camera_timeline_sha256":
                    self.plan["document_sha256"],
               "scene_sha256":self.plan["scene_document_sha256"],
               "emitter_path":self.emitter_path,
               "source_id":self.source_id,
               "sample_rate":RATE,"max_samples":self.max_samples,
               "output_is_original_source":True,
               "flattened_soundtrack":False}
        self._state="AUTHORIZING"
        if self.approve_start(dict(scope)) is not True:
            self._state="DENIED"
            raise PermissionError("Native microphone capture was not approved")
        self._tmp=Path(tempfile.mkdtemp(
            prefix="nvp-live-original-",dir=str(self._journal.root)))
        self._spool=self._tmp/"recording.pcm"
        try:
            if self.native_pcm_auditor is not None and os.name=="nt":
                # Device PCM is not allowed to begin in plaintext scratch
                # when the production compiled-worker audit is enabled.
                from backend.nvp_w1g_encrypted_source import require_efs_stage
                require_efs_stage(self._tmp)
            self._journal.begin(self._tmp,scope)
        except Exception:
            shutil.rmtree(self._tmp)
            self._tmp=None
            self._state="FAILED"
            raise
        self._worker=threading.Thread(
            target=self._writer,name="NVP trusted PCM spool",daemon=True)
        self._worker.start()
        try:
            self._device=self.device_factory()
            generator=self._callback()
            next(generator)
            self._device.start(generator)
            self._state="RECORDING"
        except Exception:
            self.cancel()
            raise
        return {**scope,"status":"RECORDING","source_modified":False}

    def _stop_device(self):
        dev=self._device
        self._device=None
        if dev is not None:
            try:dev.stop()
            finally:dev.close()

    def _drain(self):
        # Stop device first: no callback may enqueue once writer sees sentinel.
        self._stop_device()
        if self._worker is not None:
            self._queue.put(None,timeout=10)
            self._worker.join(timeout=15)
            if self._worker.is_alive():
                raise RuntimeError("Source PCM writer failed durable shutdown")
            self._worker=None
        if self._error is not None:
            raise RuntimeError("Original recording cannot be frozen") from self._error
        if self._count<1 or self._count!=self._total_queued:
            raise RuntimeError("Recorded microphone samples are incomplete")
        # The worker has closed and fsynced the source bytes. This is only
        # evidence of a durable sound signal, never Take approval.
        if self.native_pcm_auditor is not None and os.name=="nt":
            from backend.nvp_w1g_encrypted_source import verify_efs_inputs
            verify_efs_inputs(self._tmp,("recording.pcm",))
        self._sealed_original_sha=self._source_checksum()
        self._journal.update(
            self._tmp,phase="DRAINED",recorded_samples=self._count,
            pcm_sha256=self._sealed_original_sha)

    def _source_checksum(self):
        h=sha256()
        with self._spool.open("rb") as source:
            while data:=source.read(CHUNK_BYTES):h.update(data)
        return h.hexdigest()

    def _chunks(self):
        digest=sha256()
        with self._spool.open("rb") as source:
            while part:=source.read(CHUNK_BYTES):
                if len(part)%2:raise RuntimeError("Non-PCM source spool")
                digest.update(part)
                yield part
        if (self._sealed_original_sha is not None and
            digest.hexdigest()!=self._sealed_original_sha):
            raise RuntimeError("Original microphone PCM changed during Take publication")

    def finish(self):
        if self._state!="RECORDING":
            raise RuntimeError("No active native microphone recording")
        self._state="FINALIZING"
        try:
            self._drain()
            end=self._count*SAMPLE_TICK
            native_audit=None
            if self.native_pcm_auditor is not None:
                native_audit=self.native_pcm_auditor.verify_original_spool(
                    project_id=self.project_id,take_id=self.take_id,
                    source_id=self.source_id,scene_id=self.scene_id,
                    scene_document_sha256=self.plan["scene_document_sha256"],
                    camera_timeline_document_sha256=self.plan["document_sha256"],
                    subject_id=self.subject_id,emitter_path=self.emitter_path,
                    source_path=self._spool,recorded_samples=self._count,
                    original_pcm_sha256=self._sealed_original_sha,
                    start_tick=0,end_tick=end)
            recorded=NativeSceneSoundCapture(
                self.index,approve_take=self.approve_freeze,
                protected_spool_root=(
                    self._tmp if native_audit is not None and os.name=="nt"
                    else None))
            receipt=recorded.capture(
                self.project_id,self.take_id,
                scene_id=self.scene_id,scene_revision=self.scene_revision,
                camera_timeline_id=self.camera_id,
                camera_timeline_revision=self.camera_revision,
                sound_timeline_id=self.sound_id,
                recordings=[{
                    "event_id":self.event_id,"event_kind":"dialogue",
                    "subject_id":self.subject_id,
                    "source_id":self.source_id,
                    "usd_prim_path":self.emitter_path,
                    "start_tick":0,"end_tick":end,
                    "gain":1.0,"pcm_chunks":self._chunks(),
                }],native_capture_audits=(
                    [native_audit] if native_audit is not None else None))
            self._journal.update(
                self._tmp,phase="FROZEN",recorded_samples=self._count,
                take_sha256=receipt["take_document_sha256"])
            self._state="FROZEN"
            return {**receipt,"status":"FROZEN_ORIGINAL_LIVE_TAKE",
                    "actual_recorded_samples":self._count,
                    "actual_audio_end_tick":str(end),
                    "device_runtime":"native_miniaudio_pcm",
                    "compiled_capture_worker_audit":native_audit,
                    "compiled_worker_is_device_recorder":False,
                    "source_modified":False}
        except Exception:
            self._state="FAILED"
            raise
        finally:
            if self._worker is None or not self._worker.is_alive():
                self._cleanup()
            else:
                # Do not delete a spool still owned by the recorder thread.
                self._state="RECOVERY_REQUIRED"

    def _cleanup(self):
        if self._worker is not None and self._worker.is_alive():
            self._state="RECOVERY_REQUIRED"
            raise RuntimeError("Cannot remove live source spool while writer remains active")
        if self._tmp is not None:
            if self._state in ("FAILED","RECOVERY_REQUIRED"):
                # Do not destroy original partial audio on a process or
                # freeze failure. The journal never marks it as a Take.
                try:self._journal.update(self._tmp,
                    phase="FAILED_UNAPPROVED",recorded_samples=self._count)
                except (OSError,RuntimeError,ValueError):
                    pass  # Preserve the spool even if its receipt is corrupt.
                return
            if self._state=="CANCELLING":
                self._journal.update(self._tmp,phase="CANCELLED",
                                     recorded_samples=self._count)
            elif self._state!="FROZEN":
                raise RuntimeError("Cannot discard unapproved original PCM")
            shutil.rmtree(self._tmp)
            self._tmp=None

    def cancel(self):
        if self._state in ("CANCELLED","FROZEN","DENIED"):
            return {"status":self._state,"take_created":self._state=="FROZEN"}
        self._state="CANCELLING"
        try:
            self._stop_device()
            if self._worker is not None:
                self._queue.put(None,timeout=10)
                self._worker.join(timeout=15)
                if self._worker.is_alive():
                    raise RuntimeError("Cannot prove native microphone worker terminated")
                self._worker=None
        finally:
            if self._worker is None or not self._worker.is_alive():
                self._cleanup()
            else:
                self._state="RECOVERY_REQUIRED"
        if self._state=="RECOVERY_REQUIRED":
            raise RuntimeError("Native recorder cleanup requires host reconciliation")
        self._state="CANCELLED"
        return {"format":FORMAT,"status":"CANCELLED",
                "take_created":False,"source_modified":False}

    @property
    def status(self):
        return {"format":FORMAT,"state":self._state,
                "recorded_samples":self._count,
                "max_samples":self.max_samples,
                "failed":self._error is not None,
                "flattened_soundtrack":False}
