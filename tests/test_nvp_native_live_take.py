"""DA-02: bounded fake microphone acceptance before real hardware CI."""
import array
import tempfile
import unittest

import test_nvp_data_av_native as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_capture_recovery import OriginalCaptureJournal
from backend.nvp_native_live_take import NativeLiveSoundSession
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

T=TICKS_PER_SECOND


class FakeCaptureDevice:
    def __init__(self,*,overrun=False):
        self.gen=None
        self.stopped=False
        self.closed=False
        self.overrun=overrun
    def start(self,gen):
        self.gen=gen
        self.emit(4000)
        if self.overrun:self.emit(50000)
    def emit(self,n):
        self.gen.send(array.array("h",[500]*n))
    def stop(self):self.stopped=True
    def close(self):self.closed=True


class StopFlushCaptureDevice(FakeCaptureDevice):
    def stop(self):
        # Some real capture APIs flush their last device callback during
        # stop. It is still original PCM and must reach the source ledger.
        self.emit(128)
        super().stop()


class LiveTakeMicTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        ExactTimeShotSequence(self.index).publish(
            self.pid,"LiveCamera",scene_id="spatial_world",
            scene_revision=1,duration_tick=str(T),shots=[{
                "shot_id":"LiveShot","camera_path":"/World/ListenerLeft",
                "start_tick":"0","end_tick":str(T),"pattern":"continuous"}])
        self.device=FakeCaptureDevice()
        self.scopes=[]
        self.allowed=True

    def session(self,**changes):
        args=dict(project_id=self.pid,take_id="MicTake001",
            scene_id="spatial_world",scene_revision=1,
            camera_timeline_id="LiveCamera",camera_timeline_revision=1,
            sound_timeline_id="MicEvents001",source_id="MicSignal001",
            emitter_path="/World/Actor",event_id="MicSpeech001",
            subject_id="Emitter",native_approve_start=lambda s:
                self.scopes.append(("start",s)) is None,
            native_approve_freeze=lambda ev,s:
                self.scopes.append(("freeze",s)) is None and self.allowed,
            device_factory=lambda:self.device)
        args.update(changes)
        return NativeLiveSoundSession(self.index,**args)

    def test_live_original_pcm_freezes_3d_scene_without_picture_frames(self):
        mic=self.session()
        self.assertEqual(mic.begin()["status"],"RECORDING")
        receipt=mic.finish()
        self.assertEqual(receipt["status"],"FROZEN_ORIGINAL_LIVE_TAKE")
        self.assertEqual(receipt["actual_recorded_samples"],4000)
        self.assertEqual(receipt["picture_frames_generated"],False)
        self.assertTrue(self.device.stopped)
        self.assertTrue(self.device.closed)
        self.assertEqual([x[0] for x in self.scopes],["start","freeze"])
        engine=FrozenSceneAV(self.index,self.pid,"MicTake001",
            expected_take_sha256=receipt["take_document_sha256"],
            listener_path="/World/ListenerLeft")
        result=engine.audio_window(0,512)
        self.assertIn("MicSpeech001",result["audible_event_ids"])
        self.assertFalse(result["source_modified"])

    def test_freeze_denial_keeps_unapproved_durable_source_evidence(self):
        self.allowed=False
        mic=self.session()
        mic.begin()
        with self.assertRaises(PermissionError):
            mic.finish()
        journal=OriginalCaptureJournal(
            self.studio.db_path.parent/"native-original-capture-recovery")
        evidence=journal.catalog(self.pid)
        self.assertEqual(len(evidence["items"]),1)
        self.assertEqual(evidence["items"][0]["phase"],"FAILED_UNAPPROVED")
        self.assertFalse(evidence["items"][0]["take_approved"])
        self.assertEqual(evidence["items"][0]["durable_sample_count"],4000)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_crash_after_fsync_drain_preserves_source_not_false_take(self):
        mic=self.session()
        mic.begin()
        mic._drain()
        recovered=OriginalCaptureJournal(
            self.studio.db_path.parent/"native-original-capture-recovery"
        ).catalog(self.pid)
        self.assertEqual(recovered["items"][0]["phase"],"DRAINED")
        self.assertFalse(recovered["auto_freeze"])
        self.assertFalse(recovered["auto_delete"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_approved_crash_recovery_saves_only_unattached_pcm_source(self):
        from backend.nvp_data_av_source import RecordedSoundSources
        mic=self.session()
        mic.begin()
        mic._drain()
        journal=OriginalCaptureJournal(
            self.studio.db_path.parent/"native-original-capture-recovery")
        row=journal.catalog(self.pid)["items"][0]
        self.assertTrue(row["recoverable_sealed_mono"])
        decisions=[]
        result=journal.salvage_original_mono_source(
            self.index,self.pid,row["capture_reference"],
            "SalvagedOriginalMic",
            native_creator_approval=lambda scope:
                decisions.append(scope) is None)
        self.assertEqual(result["status"],"RECOVERED_UNATTACHED_ORIGINAL_MONO")
        self.assertFalse(result["created_frozen_take"])
        self.assertEqual(result["recorded_samples"],4000)
        self.assertEqual(RecordedSoundSources(self.index).read(
            self.pid,"SalvagedOriginalMic",1,0,4000),
            (array.array("h",[500]*4000)).tobytes())
        self.assertEqual(decisions[0]["operation"],
                         "nvp.original_sound.salvage_unapproved_pcm.v1")
        self.assertEqual(journal.catalog(self.pid)["items"],[])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_unverified_original_source_recovery_cannot_forge_a_take(self):
        mic=self.session()
        mic.begin()
        mic._drain()
        journal=OriginalCaptureJournal(
            self.studio.db_path.parent/"native-original-capture-recovery")
        reference=journal.catalog(self.pid)["items"][0]["capture_reference"]
        with self.assertRaises(PermissionError):
            journal.salvage_original_mono_source(
                self.index,self.pid,reference,"DeclinedSource",
                native_creator_approval=lambda scope:False)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DeclinedSource",1)
        original=mic._spool.read_bytes()
        mic._spool.write_bytes(original[:-2]+b"\x01\x00")
        with self.assertRaises(RuntimeError):
            journal.salvage_original_mono_source(
                self.index,self.pid,reference,"TamperedSource",
                native_creator_approval=lambda scope:True)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"TamperedSource",1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_native_stop_flush_is_included_in_frozen_sample_source(self):
        self.device=StopFlushCaptureDevice()
        mic=self.session()
        self.assertEqual(mic.begin()["status"],"RECORDING")
        saved=mic.finish()
        self.assertEqual(saved["actual_recorded_samples"],4128)
        self.assertEqual(saved["actual_audio_end_tick"],str(4128*(T//48000)))
        self.assertEqual(self.index.read_revision(
            self.pid,"MicSignal001",1)["data"]["sample_count"],4128)
        self.assertEqual(saved["picture_frames_generated"],False)
        self.assertTrue(self.device.closed)

    def test_cancel_cannot_create_a_live_take(self):
        mic=self.session()
        mic.begin()
        self.assertEqual(mic.cancel()["status"],"CANCELLED")
        self.assertTrue(self.device.closed)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_freeze_denial_never_produces_false_approved_take(self):
        self.allowed=False
        mic=self.session()
        mic.begin()
        with self.assertRaises(PermissionError):
            mic.finish()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_microphone_sample_overrun_cannot_publish_an_original_take(self):
        self.device=FakeCaptureDevice(overrun=True)
        mic=self.session()
        mic.begin()
        self.assertTrue(mic.status["failed"])
        with self.assertRaises(RuntimeError):
            mic.finish()
        self.assertEqual(mic.status["state"],"FAILED")
        self.assertTrue(self.device.closed)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)

    def test_cancellation_after_failed_recording_is_source_safe(self):
        self.device=FakeCaptureDevice(overrun=True)
        mic=self.session()
        mic.begin()
        self.assertEqual(mic.cancel()["status"],"CANCELLED")
        self.assertFalse(mic.status["flattened_soundtrack"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MicTake001",1)


if __name__=="__main__":
    unittest.main()
