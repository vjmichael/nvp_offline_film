"""DA-02E: two separately clocked native inputs, no destructive time stretch.

sounddevice / PortAudio supplies inputBufferAdcTime for EACH independent
RawInputStream. A bounded host clock calibration maps stream time onto
one perf_counter_ns timeline. Source PCM bytes are independently spooled
and frozen untouched. The exact-time audience receives a pinned per-source
clock map, not a newly stamped or remixed original recording.

Hardware time is quality-gated: bad callback status, empty/stalled streams,
jumps, unavailable ADC timing, unstable calibration or implausible drift
abort the Take. Independent capture is not equivalent to genlock.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import time

from backend.nvp_data_first_filming import NativeSceneSoundCapture
from backend.nvp_film_index import _id
from backend.nvp_independent_device_sync import (
    DeviceTimeTrack,align_devices,FORMAT as CLOCK_FORMAT,
    RATE,MAX_DURATION_S)
from backend.nvp_native_live_take import (
    NativeLiveSoundSession,FORMAT,MAX_QUEUE,CHUNK_BYTES)


def native_input_devices():
    """Enumerate actual host inputs; no browser-supplied OS path or library."""
    import sounddevice as sd
    devices=sd.query_devices()
    hosts=sd.query_hostapis()
    result=[]
    for number,d in enumerate(devices):
        if int(d["max_input_channels"])<1:continue
        result.append({
            "device_id":number,
            "name":str(d["name"])[:160],
            "host_api":str(hosts[int(d["hostapi"])]["name"])[:80],
            "max_input_channels":int(d["max_input_channels"]),
        })
    return result[:128]


class PortAudioMonoInput:
    def __init__(self,device_id,callback):
        import sounddevice as sd
        if device_id not in [x["device_id"] for x in native_input_devices()]:
            raise ValueError("Selected native input device is no longer available")
        def receive(indata,frames,timing,status):
            adc=timing.inputBufferAdcTime
            if not isinstance(adc,(float,int)) or not (
                    0<adc<float("inf")):
                callback(b"",frames,0,False)
                return
            callback(bytes(indata),int(frames),
                     round(adc*1_000_000_000),not bool(status))
        self.stream=sd.RawInputStream(
            samplerate=RATE,channels=1,dtype="int16",
            device=device_id,blocksize=0,latency="low",
            callback=receive)
    def start(self):self.stream.start()
    def stop(self):self.stream.stop()
    def close(self):self.stream.close()
    @property
    def stream_time_ns(self):
        return round(float(self.stream.time)*1_000_000_000)


class IndependentNativeSoundSession(NativeLiveSoundSession):
    def __init__(self,*args,second_source_id,second_emitter_path,
                 second_event_id,second_subject_id,
                 independent_device_ids,device_factory=None,
                 host_clock_ns=None,**kwargs):
        super().__init__(*args,device_factory=lambda:None,**kwargs)
        for token in (second_source_id,second_event_id,second_subject_id):
            _id(token,"second independent original source")
        if (second_source_id in {
                    self.take_id,self.scene_id,self.camera_id,self.sound_id,
                    self.source_id} or second_event_id==self.event_id or
            second_emitter_path not in self._prim_roles() or
            second_emitter_path==self.emitter_path):
            raise ValueError("Independent original source/emitter identities collide")
        if (type(independent_device_ids) is not list or
            len(independent_device_ids)!=2 or
            any(type(x) is not int or x<0 or x>4096
                for x in independent_device_ids) or
            len(set(independent_device_ids))!=2):
            raise ValueError("Two different native input device IDs required")
        self.device_descriptors=None
        if device_factory is None:
            catalog=native_input_devices()
            known={entry["device_id"]:entry for entry in catalog}
            if not set(independent_device_ids)<=set(known):
                raise RuntimeError("One or both physical sound devices disconnected")
            # Selection scope includes the OS endpoint identity, not merely a
            # transient index that could be reassigned after hot-unplug.
            self.device_descriptors=[
                dict(known[d]) for d in independent_device_ids]
        self.device_ids=independent_device_ids[:]
        self.second_source_id=second_source_id
        self.second_emitter_path=second_emitter_path
        self.second_event_id=second_event_id
        self.second_subject_id=second_subject_id
        # Never open the physical PortAudio stream in the desktop host.
        # Explicit test-only factories are trusted Python dependencies.
        self.input_factory=device_factory
        self.host_clock_ns=host_clock_ns or time.perf_counter_ns
        self.tracks=[DeviceTimeTrack(i) for i in self.device_ids]
        self.devices=[]
        self.queues=[queue.Queue(maxsize=MAX_QUEUE) for _ in range(2)]
        self.workers=[]
        self.spools=[]
        self.written=[0,0]
        self.enqueued=[0,0]
        self.errors=[None,None]
        self.running_calibration=threading.Event()
        self.calibration_worker=None

    def _append_original(self,channel,raw,frames,adc_ns,good):
        if self._state not in ("AUTHORIZING","RECORDING","FINALIZING"):
            return
        if self.errors[channel] is not None:return
        if (not good or type(raw) is not bytes or
            type(frames) is not int or not 1<=frames<=RATE or
            len(raw)!=frames*2):
            self.errors[channel]=RuntimeError(
                "Native independent input overflow or invalid signed16 sample count")
            return
        try:
            self.tracks[channel].add(frames,adc_ns,status_ok=good)
            self.enqueued[channel]+=frames
            if (self.enqueued[channel]>MAX_DURATION_S*RATE or
                len(raw)>CHUNK_BYTES):
                raise RuntimeError("Independent source exceeded bounded original capture")
            # A supervised child is already reaped when its original packets
            # are replayed. Block only that post-custody replay, never the
            # actual PortAudio device callback.
            if self.input_factory is None and self._state=="FINALIZING":
                self.queues[channel].put(raw,timeout=5)
            else:
                self.queues[channel].put_nowait(raw)
        except Exception as exc:
            self.errors[channel]=exc

    def _writer(self,channel):
        try:
            with self.spools[channel].open("xb") as out:
                while True:
                    part=self.queues[channel].get()
                    if part is None:break
                    out.write(part)
                    self.written[channel]+=len(part)//2
                out.flush();os.fsync(out.fileno())
        except Exception as exc:
            self.errors[channel]=exc

    def _calibrator(self):
        try:
            while self.running_calibration.is_set():
                for channel,dev in enumerate(self.devices):
                    # A child-owned ADC clock must be bracketed in that same
                    # supervised child, not against a stale host-side reading.
                    if getattr(dev,"uses_worker_clock",False):
                        continue
                    before=self.host_clock_ns()
                    stream=dev.stream_time_ns
                    after=self.host_clock_ns()
                    self.tracks[channel].calibrate(before,stream,after)
                time.sleep(.20)
        except Exception as exc:
            self.errors[0]=exc

    def begin(self):
        if self._state!="NEW":
            raise RuntimeError("Independent original recording already attempted")
        scope={
            "format":FORMAT,"project_id":self.project_id,
            "take_id":self.take_id,
            "scene_sha256":self.plan["scene_document_sha256"],
            "camera_timeline_sha256":self.plan["document_sha256"],
            "emitter_path":self.emitter_path,"source_id":self.source_id,
            "second_emitter_path":self.second_emitter_path,
            "second_source_id":self.second_source_id,
            "independent_device_ids":self.device_ids[:],
            "independent_device_descriptors":self.device_descriptors,
            "sample_rate":RATE,"max_samples":self.max_samples,
            "independent_device_clock_calibration_required":True,
            "output_is_original_source":True,"flattened_soundtrack":False}
        self._state="AUTHORIZING"
        if self.approve_start(scope) is not True:
            self._state="DENIED"
            raise PermissionError("Creator denied independent microphone devices")
        if self.device_descriptors is not None:
            current={d["device_id"]:d for d in native_input_devices()}
            if any(current.get(d["device_id"])!=d
                   for d in self.device_descriptors):
                self._state="FAILED"
                raise RuntimeError(
                    "Native audio endpoint identity changed during creator approval")
        self._tmp=Path(tempfile.mkdtemp(
            prefix="nvp-live-original-",dir=str(self._journal.root)))
        self._spool=self._tmp/"independent_0.pcm"
        self.spools=[self._spool,self._tmp/"independent_1.pcm"]
        self._journal.begin(self._tmp,scope)
        self.workers=[threading.Thread(
            target=self._writer,args=(i,),daemon=True,
            name="NVP original independent PCM writer") for i in range(2)]
        for worker in self.workers:worker.start()
        try:
            for channel,device_id in enumerate(self.device_ids):
                def callback(raw,frames,adc_ns,good,ch=channel):
                    self._append_original(ch,raw,frames,adc_ns,good)
                if self.input_factory is None:
                    from backend.nvp_device_producer_custody import (
                        SupervisedNativeDevice, scope_sha256)
                    dev=SupervisedNativeDevice(
                        self._tmp, mode="port", max_samples=self.max_samples,
                        scope_digest=scope_sha256(scope),
                        device_id=device_id,
                        device_descriptor=self.device_descriptors[channel],
                        channel=channel)
                    dev._callback=callback
                else:
                    dev=self.input_factory(device_id,callback)
                self.devices.append(dev)
            for dev in self.devices:dev.start()
            self.running_calibration.set()
            self.calibration_worker=threading.Thread(
                target=self._calibrator,
                name="NVP native cross-device clock calibration",daemon=True)
            self.calibration_worker.start()
            self._state="RECORDING"
        except Exception:
            self.cancel()
            raise
        return {**scope,"status":"RECORDING",
                "original_mono_source_count":2,
                "independent_device_clocks_synchronized":"PENDING_CALIBRATION",
                "hardware_genlock":False,
                "source_modified":False}

    def _stop(self,*,require_complete=True):
        # Stop callback producers FIRST, then readers; never put a sentinel
        # into a queue while a native device can still enqueue original PCM.
        faults=[]
        # Stop every device's producer before replaying the original PCM:
        # otherwise one recorder may still be acquiring while its peer is
        # consumed. Both attached workers remain under their OS supervisors.
        if require_complete:
            for dev in self.devices:
                if getattr(dev,"uses_worker_clock",False):
                    try:dev.request_stop()
                    except Exception as exc:faults.append(exc)
        for channel in range(len(self.devices)-1,-1,-1):
            dev=self.devices[channel]
            try:
                if require_complete or not getattr(dev,"uses_worker_clock",False):
                    dev.stop()
                if require_complete and getattr(dev,"uses_worker_clock",False):
                    for anchor in dev.calibration_anchors():
                        self.tracks[channel].calibrate(*anchor)
            except Exception as exc:faults.append(exc)
            try:dev.close()
            except Exception as exc:faults.append(exc)
        self.devices=[]
        self.running_calibration.clear()
        if self.calibration_worker is not None:
            self.calibration_worker.join(timeout=10)
            if self.calibration_worker.is_alive():
                faults.append(RuntimeError("Clock calibration worker survived shutdown"))
            self.calibration_worker=None
        for queue_item in self.queues:
            try:queue_item.put(None,timeout=10)
            except queue.Full as exc:faults.append(exc)
        for worker in self.workers:
            worker.join(timeout=15)
            if worker.is_alive():
                faults.append(RuntimeError("Source PCM writer survived shutdown"))
        if faults:raise RuntimeError("Native original recording shutdown unproven") from faults[0]
        if require_complete and (
            any(self.errors) or
            any(self.written[i]!=self.enqueued[i] for i in range(2))):
            raise RuntimeError("Independent microphone PCM loss or failed OS callback")
        if require_complete:
            for i,path in enumerate(self.spools):
                if path.stat().st_size!=self.written[i]*2 or self.written[i]<1:
                    raise RuntimeError("Independent original audio spool incomplete")

    def _spool_sha(self,path):
        digest=sha256()
        with path.open("rb") as fp:
            while part:=fp.read(CHUNK_BYTES):digest.update(part)
        return digest.hexdigest()

    def finish(self):
        if self._state!="RECORDING":
            raise RuntimeError("No independently clocked original recording active")
        self._state="FINALIZING"
        try:
            self._stop()
            self._count=min(self.written)
            models=[track.seal() for track in self.tracks]
            alignment=align_devices(
                *models,camera_duration_tick=int(self.plan["duration_tick"]))
            hashes=[self._spool_sha(path) for path in self.spools]
            combined=sha256(
                ("independent-v1:"+":".join(hashes)).encode("ascii")
            ).hexdigest()
            # Native source journal is durable but NOT an approved Take.
            self._journal.update(self._tmp,phase="DRAINED",
                                 recorded_samples=min(self.written),
                                 pcm_sha256=combined)
            evidence_id=self.take_id+".DeviceClocks"
            source_doc={**alignment,
                        "original_mono_pcm_sha256":hashes,
                        "source_ids":[self.source_id,self.second_source_id],
                        "native_anchor_evidence":[{
                            "device_id":track.device_id,
                            "adc_stream_anchors":track.anchors,
                            "host_calibration_samples":track.calibrations,
                        } for track in self.tracks],
                        "timing_physically_certified":False,
                        "creator_approved_recording":False}
            evidence=self.index.register_revision(
                self.project_id,evidence_id,"audio",
                source_doc,expected_revision=0)
            recordings=[]
            for i,(source_id,event_id,emitter,subject) in enumerate((
                (self.source_id,self.event_id,self.emitter_path,self.subject_id),
                (self.second_source_id,self.second_event_id,
                 self.second_emitter_path,self.second_subject_id),
            )):
                mapping=alignment["sample_maps"][i]
                def chunks(p=self.spools[i],expected_sha=hashes[i]):
                    digest=sha256()
                    with p.open("rb") as fp:
                        while part:=fp.read(CHUNK_BYTES):
                            if len(part)%2:
                                raise RuntimeError("Invalid original device PCM source")
                            digest.update(part)
                            yield part
                    if digest.hexdigest()!=expected_sha:
                        raise RuntimeError("Independent raw PCM spool changed during freeze")
                recordings.append({
                    "event_id":event_id,"event_kind":"dialogue",
                    "subject_id":subject,"source_id":source_id,
                    "usd_prim_path":emitter,
                    "start_tick":mapping["first_tick"],
                    "end_tick":mapping["last_tick_exclusive"],
                    "gain":1.0,"pcm_chunks":chunks(),
                    "source_sync":mapping,
                    "clock_evidence":{"object_id":evidence_id,
                                      "document_sha256":evidence["document_sha256"]},
                })
            def approve_clock_bound_take(event,scope):
                evidence_scope={
                    **scope,
                    "independent_clock_evidence_sha256":evidence["document_sha256"],
                    "independent_clock_drift_ppm":[
                        model["measured_drift_ppm"] for model in models],
                    "independent_adc_max_residual_ns":[
                        model["max_adc_residual_ns"] for model in models],
                    "independent_original_pcm_unmodified":True,
                    "independent_hardware_genlock":False,
                }
                return self.approve_freeze(event,evidence_scope)
            saved=NativeSceneSoundCapture(
                self.index,approve_take=approve_clock_bound_take).capture(
                self.project_id,self.take_id,
                scene_id=self.scene_id,scene_revision=self.scene_revision,
                camera_timeline_id=self.camera_id,
                camera_timeline_revision=self.camera_revision,
                sound_timeline_id=self.sound_id,
                recordings=recordings)
            self._journal.update(
                self._tmp,phase="FROZEN",
                recorded_samples=min(self.written),
                take_sha256=saved["take_document_sha256"])
            self._state="FROZEN"
            return {
                **saved,"status":"FROZEN_ORIGINAL_LIVE_TAKE",
                "actual_recorded_samples":min(self.written),
                "per_device_samples":self.written[:],
                "original_mono_source_count":2,
                "clock_evidence_sha256":evidence["document_sha256"],
                "drift_ppm":[model["measured_drift_ppm"] for model in models],
                "max_residual_ns":[model["max_adc_residual_ns"] for model in models],
                "independent_device_clocks_synchronized":True,
                "shared_capture_clock":False,"hardware_genlock":False,
                "device_runtime":("supervised_dual_job_cgroup_portaudio"
                                  if self.input_factory is None
                                  else "trusted_injected_test_devices"),
                "source_modified":False}
        except Exception:
            self._state="FAILED"
            raise
        finally:
            if any(w.is_alive() for w in self.workers):
                self._state="RECOVERY_REQUIRED"
            else:self._cleanup()

    def cancel(self):
        if self._state in ("FROZEN","CANCELLED","DENIED"):
            return {"status":self._state,
                    "take_created":self._state=="FROZEN"}
        self._state="CANCELLING"
        try:self._stop(require_complete=False)
        except Exception:
            self._state="FAILED"
            raise
        finally:
            if any(w.is_alive() for w in self.workers):
                self._state="RECOVERY_REQUIRED"
            else:self._cleanup()
        self._state="CANCELLED"
        return {"format":FORMAT,"status":"CANCELLED","take_created":False,
                "source_modified":False}

    @property
    def status(self):
        return {
            "format":FORMAT,"state":self._state,
            "recorded_samples":min(self.written),
            "per_device_samples":self.written[:],
            "clock_calibrations":[len(t.calibrations) for t in self.tracks],
            "adc_anchors":[len(t.anchors) for t in self.tracks],
            "failed":any(self.errors),"flattened_soundtrack":False,
            "independent_device_clock_calibration_required":True}
