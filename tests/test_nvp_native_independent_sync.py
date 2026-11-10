"""DA-02E source-clock sync: drift, latency, real wrapper, and Take integrity.

The native fake adapter exercises TWO independent queues/streams with
distinct ADC time bases. Physical Windows/Linux audio-card loopback
acceptance is still required before promising certified sample accuracy.
"""
from __future__ import annotations
import struct
import threading
import time
import unittest

import test_nvp_native_live_take as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_independent_device_sync import (
    DeviceTimeTrack,align_devices,interpolated_window,FORMAT as CLOCK_FORMAT,
    RATE)
from backend.nvp_native_independent_take import IndependentNativeSoundSession
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_data_av_scene import FrozenSceneAV


class SourceClockModelTests(unittest.TestCase):
    def track(self,device,ppm,offset):
        t=DeviceTimeTrack(device)
        # Stream-clock calibration offsets map two unrelated backend
        # timebases to a common monotonic host epoch.
        for _ in range(12):
            t.calibrate(1_000_000_000_000,
                        1_000_000_000_000-offset,1_000_000_000_500)
        for index in range(10):
            first=index*12000
            ns=5_000_000_000+round(
                first*1e9/RATE*(1+ppm/1_000_000))
            t.add(12000,ns)
        return t

    def test_two_drifting_stream_clocks_align_without_pcm_rewrite(self):
        a=self.track(10,150,800_000_000).seal()
        b=self.track(11,-220,920_000_000).seal()
        self.assertEqual(a["device_id"],10)
        self.assertAlmostEqual(a["measured_drift_ppm"],150,delta=1)
        self.assertAlmostEqual(b["measured_drift_ppm"],-220,delta=1)
        both=align_devices(a,b,camera_duration_tick=20*T)
        maps=both["sample_maps"]
        self.assertEqual(len(maps),2)
        self.assertGreater(maps[1]["first_tick"],maps[0]["first_tick"])
        self.assertNotEqual(
            maps[0]["sample_period_tick_num"],
            maps[1]["sample_period_tick_num"])
        self.assertTrue(both["original_pcm_unmodified"])
        self.assertFalse(both["hardware_genlocked"])
        self.assertFalse(both["timing_validated_in_installed_hardware"])

    def test_adc_jump_and_bad_calibration_reject_forged_sync(self):
        out=self.track(10,150,800_000_000)
        out.anchors[4]=(out.anchors[4][0],
                        out.anchors[4][1]+10_000_000,
                        out.anchors[4][2])
        with self.assertRaises(RuntimeError):
            out.seal()
        out=self.track(10,150,800_000_000)
        out.calibrations[-1]=(out.calibrations[-1][0]+20_000_000,200)
        with self.assertRaises(RuntimeError):
            out.seal()
        out=DeviceTimeTrack(12)
        with self.assertRaises(RuntimeError):
            out.add(128,1000,status_ok=False)

    def test_seek_safe_drift_resampling_is_derived_only(self):
        original=struct.pack("<"+"h"*300,
                             *(min(32767,i*100) for i in range(300)))
        model={"first_tick":0,
               "sample_period_tick_num":147014700000,
               "sample_period_tick_den":1_000_000}
        def reader(first,count):
            return original[2*first:2*(first+count)]
        all_samples=interpolated_window(
            reader,300,model,0,128,
            ticks_per_output_sample=T//RATE)
        first=interpolated_window(
            reader,300,model,0,64,
            ticks_per_output_sample=T//RATE)
        second=interpolated_window(
            reader,300,model,64*(T//RATE),64,
            ticks_per_output_sample=T//RATE)
        self.assertEqual(all_samples,first+second)
        self.assertEqual(original,reader(0,300))


class FakeIndependentADCDevice:
    def __init__(self,device_id,callback):
        self.device_id=device_id
        self.callback=callback
        self.offset=600_000_000+device_id*7_000_000
        self.ppm=120 if device_id==10 else -170
        self.started=False
        self.stopped=False
        self.closed=False
        self.worker=None
    @property
    def stream_time_ns(self):
        return time.perf_counter_ns()-self.offset
    def start(self):
        self.started=True
        first=time.perf_counter_ns()-self.offset-18_000_000
        def run():
            # 12 original callback buffers over 3 seconds.
            for i in range(12):
                if self.stopped:break
                until=first+self.offset+round(
                    i*12000*1e9/RATE*(1+self.ppm/1e6))+18_000_000
                while time.perf_counter_ns()<until and not self.stopped:
                    time.sleep(.003)
                if self.stopped:break
                value=200 if self.device_id==10 else -300
                samples=struct.pack("<"+"h"*12000,*([value]*12000))
                adc=first+round(
                    i*12000*1e9/RATE*(1+self.ppm/1e6))
                self.callback(samples,12000,adc,True)
        self.worker=threading.Thread(target=run,daemon=True)
        self.worker.start()
    def stop(self):
        self.stopped=True
        if self.worker is not None:self.worker.join(timeout=6)
    def close(self):self.closed=True


class NativeIndependentDeviceTakeTests(unittest.TestCase):
    def setUp(self):
        fixture.LiveTakeMicTests.setUp(self)
        ExactTimeShotSequence(self.index).publish(
            self.pid,"LongIndependentCamera",
            scene_id="spatial_world",scene_revision=1,
            duration_tick=str(8*T),shots=[{
                "shot_id":"LongOriginalTake",
                "camera_path":"/World/ListenerLeft",
                "start_tick":"0","end_tick":str(8*T),
                "pattern":"continuous"}])
        self.native_devices=[]
        self.approvals=[]
        self.take=None

    def session(self,**changes):
        args=dict(
            project_id=self.pid,take_id="DualIndependentTake",
            scene_id="spatial_world",scene_revision=1,
            camera_timeline_id="LongIndependentCamera",
            camera_timeline_revision=1,
            sound_timeline_id="DualIndependentEvents",
            source_id="IndependentSoundA",
            emitter_path="/World/Actor",event_id="IndependentVoiceA",
            subject_id="Actor",second_source_id="IndependentSoundB",
            second_emitter_path="/World/ListenerRight",
            second_event_id="IndependentVoiceB",
            second_subject_id="Anchor",
            independent_device_ids=[10,11],
            native_approve_start=lambda scope:
                self.approvals.append(("start",scope)) is None,
            native_approve_freeze=lambda event,scope:
                self.approvals.append(("freeze",scope)) is None,
            device_factory=self._factory)
        args.update(changes)
        return IndependentNativeSoundSession(self.index,**args)

    def _factory(self,device_id,callback):
        obj=FakeIndependentADCDevice(device_id,callback)
        self.native_devices.append(obj)
        return obj

    def test_two_real_distinct_native_streams_freeze_clock_proof_and_unmodified_sources(self):
        session=self.session()
        begin=session.begin()
        self.assertEqual(begin["status"],"RECORDING")
        self.assertEqual(begin["independent_device_clocks_synchronized"],
                         "PENDING_CALIBRATION")
        # The dummy streams produce timestamps against a deliberately
        # independent, drifted ADC timebase and share no device callback.
        time.sleep(3.3)
        done=session.finish()
        self.assertEqual(done["status"],"FROZEN_ORIGINAL_LIVE_TAKE")
        self.assertTrue(done["independent_device_clocks_synchronized"])
        self.assertEqual(done["original_mono_source_count"],2)
        self.assertEqual(done["per_device_samples"],[144000,144000])
        self.assertGreater(abs(done["drift_ppm"][0]-done["drift_ppm"][1]),200)
        self.assertEqual([x[0] for x in self.approvals],["start","freeze"])
        self.assertTrue(all(x.stopped and x.closed for x in self.native_devices))
        evidence=self.index.read_revision(self.pid,"DualIndependentTake.DeviceClocks",1)
        self.assertEqual(evidence["document_sha256"],
                         done["clock_evidence_sha256"])
        self.assertEqual(evidence["data"]["format"],CLOCK_FORMAT)
        self.assertEqual(len(evidence["data"]["native_anchor_evidence"]),2)
        for sid,value in (("IndependentSoundA",200),
                          ("IndependentSoundB",-300)):
            rec=self.index.read_revision(self.pid,sid,1)
            self.assertEqual(rec["data"]["sample_count"],144000)
            block=self.sound.read(self.pid,sid,1,0,32)
            self.assertEqual(struct.unpack("<"+"h"*32,block),
                             (value,)*32)
        freeze=FrozenSceneAV(self.index,self.pid,"DualIndependentTake",
            expected_take_sha256=done["take_document_sha256"],
            listener_path="/World/ListenerLeft")
        w=freeze.audio_window(12000,512)
        self.assertIn("IndependentVoiceA",w["audible_event_ids"])
        self.assertIn("IndependentVoiceB",w["audible_event_ids"])
        self.assertFalse(w["source_modified"])
        self.assertFalse(w["film_master_approved"])

    def test_creator_discard_stops_both_inputs_without_clock_qualification(self):
        session=self.session()
        session.begin()
        receipt=session.cancel()
        self.assertEqual(receipt["status"],"CANCELLED")
        self.assertFalse(receipt["take_created"])
        self.assertTrue(all(dev.closed for dev in self.native_devices))
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DualIndependentTake",1)

    def test_bad_clock_evidence_never_publishes_a_take(self):
        clock=self.session()
        clock.begin()
        # Too short for offset/drift qualification.
        with self.assertRaises(RuntimeError):
            clock.finish()
        self.assertTrue(all(x.closed for x in self.native_devices))
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DualIndependentTake",1)
        from backend.nvp_capture_recovery import OriginalCaptureJournal
        journal=OriginalCaptureJournal(
            self.studio.db_path.parent/"native-original-capture-recovery")
        candidate=journal.catalog(self.pid)["items"]
        self.assertEqual(len(candidate),1)
        self.assertFalse(candidate[0]["take_approved"])
        self.assertFalse(candidate[0]["recoverable_sealed_mono"])


if __name__=="__main__":
    unittest.main()
