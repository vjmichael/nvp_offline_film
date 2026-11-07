"""DA-02C: two true synchronized mono sources on ONE native input device.

A two-channel OS audio interface samples both inputs on the same physical
capture clock. We demultiplex the interleaved samples to two independent
original mono PCM source ledgers; there is no mixed track, guessed alignment,
time stretching, FFmpeg, or dependence on video frames.

Two unrelated microphones/sound cards are NOT synchronized by this class.
They require separate timestamp/clock-drift calibration and acceptance.
"""
from __future__ import annotations

import array
import os
from pathlib import Path
import queue
import sys

from backend.nvp_data_first_filming import NativeSceneSoundCapture
from backend.nvp_film_index import _id
from backend.nvp_native_live_take import (
    NativeLiveSoundSession,RATE,CHUNK_BYTES,SAMPLE_TICK,FORMAT)


def _stereo_capture_device():
    import miniaudio
    return miniaudio.CaptureDevice(
        input_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=2,sample_rate=RATE,buffersize_msec=40,
        app_name="NVP Two Original Sources Shared Clock")


class NativeStereoOriginalSession(NativeLiveSoundSession):
    def __init__(self,*args,second_source_id,second_emitter_path,
                 second_event_id,second_subject_id,device_factory=None,**kwargs):
        super().__init__(
            *args,device_factory=device_factory or _stereo_capture_device,**kwargs)
        for x in (second_source_id,second_event_id,second_subject_id):
            _id(x,"secondary original mono source")
        if second_source_id in {
                self.take_id,self.scene_id,self.camera_id,self.sound_id,
                self.source_id} or second_event_id==self.event_id:
            raise ValueError("Original synchronized source and event IDs must differ")
        if (second_emitter_path not in self._prim_roles() or
                second_emitter_path==self.emitter_path):
            raise ValueError("Each original mono stream needs its own authored USD emitter")
        self.second_source_id=second_source_id
        self.second_event_id=second_event_id
        self.second_emitter_path=second_emitter_path
        self.second_subject_id=second_subject_id
        self._left_spool=None
        self._right_spool=None

    def _append(self,samples):
        if self._error is not None or self._state not in (
                "AUTHORIZING","RECORDING","FINALIZING"):
            return
        if (not isinstance(samples,array.array) or
                samples.typecode!="h" or len(samples)%2):
            self._error=RuntimeError("Native stereo source requires aligned PCM16 frames")
            return
        if not samples:return
        # Keep one producer callback and one queue packet per shared-clock
        # read. A queue overrun fails the whole Take, never one channel.
        channel_a=array.array("h",samples[::2])
        channel_b=array.array("h",samples[1::2])
        if sys.byteorder!="little":
            channel_a.byteswap();channel_b.byteswap()
        a,b=channel_a.tobytes(),channel_b.tobytes()
        with self._lock:
            self._total_queued+=len(a)//2
            if len(a)+len(b)>CHUNK_BYTES or self._total_queued>self.max_samples:
                self._error=RuntimeError("Shared-clock original sound exceeds capture bound")
                return
        try:self._queue.put_nowait((a,b))
        except queue.Full:
            self._error=RuntimeError("Shared-clock sound queue overran disk writer")

    def _writer(self):
        try:
            self._left_spool=Path(self._tmp.name)/"source_channel_0.pcm"
            self._right_spool=Path(self._tmp.name)/"source_channel_1.pcm"
            with self._left_spool.open("xb") as left, \
                    self._right_spool.open("xb") as right:
                while True:
                    packet=self._queue.get()
                    if packet is None:break
                    a,b=packet
                    if len(a)!=len(b) or len(a)%2:
                        raise RuntimeError("Stereo original sample frames diverged")
                    left.write(a);right.write(b)
                    self._count+=len(a)//2
                for fp in (left,right):
                    fp.flush();os.fsync(fp.fileno())
        except Exception as exc:
            self._error=exc

    @staticmethod
    def _file_chunks(path):
        with path.open("rb") as fp:
            while data:=fp.read(CHUNK_BYTES):
                if len(data)%2:raise RuntimeError("Partial original PCM sample")
                yield data

    def begin(self):
        result=super().begin()
        return {**result,"native_input_channels":2,
                "original_mono_source_count":2,
                "shared_capture_clock":True,
                "independent_device_clocks_synchronized":False}

    def finish(self):
        if self._state!="RECORDING":
            raise RuntimeError("No live two-channel native filming session")
        self._state="FINALIZING"
        try:
            self._drain()
            if (self._left_spool is None or self._right_spool is None or
                self._left_spool.stat().st_size!=self._right_spool.stat().st_size or
                self._left_spool.stat().st_size!=2*self._count):
                raise RuntimeError("Native shared-clock source channels are incomplete")
            end=self._count*SAMPLE_TICK
            recordings=[]
            for sid,eid,emitter,subject,spool in (
                (self.source_id,self.event_id,self.emitter_path,
                 self.subject_id,self._left_spool),
                (self.second_source_id,self.second_event_id,
                 self.second_emitter_path,self.second_subject_id,self._right_spool),
            ):
                recordings.append({
                    "event_id":eid,"event_kind":"dialogue",
                    "subject_id":subject,"source_id":sid,
                    "usd_prim_path":emitter,
                    "start_tick":0,"end_tick":end,"gain":1.0,
                    "pcm_chunks":self._file_chunks(spool),
                })
            receipt=NativeSceneSoundCapture(
                self.index,approve_take=self.approve_freeze
            ).capture(self.project_id,self.take_id,
                scene_id=self.scene_id,scene_revision=self.scene_revision,
                camera_timeline_id=self.camera_id,
                camera_timeline_revision=self.camera_revision,
                sound_timeline_id=self.sound_id,
                recordings=recordings)
            self._state="FROZEN"
            return {**receipt,"status":"FROZEN_ORIGINAL_LIVE_TAKE",
                    "actual_recorded_samples":self._count,
                    "actual_audio_end_tick":str(end),
                    "native_input_channels":2,
                    "original_mono_source_count":2,
                    "shared_capture_clock":True,
                    "independent_device_clocks_synchronized":False,
                    "device_runtime":"native_miniaudio_stereo_pcm",
                    "source_modified":False}
        except Exception:
            self._state="FAILED"
            raise
        finally:
            if self._worker is None or not self._worker.is_alive():
                self._cleanup()
            else:
                self._state="RECOVERY_REQUIRED"
