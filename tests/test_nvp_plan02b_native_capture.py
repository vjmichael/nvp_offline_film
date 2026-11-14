"""PLAN-02-B trusted host never accepts browser approval as a Take grant."""
import unittest
import test_nvp_data_av_native as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_native_capture_desktop import TrustedNativeOriginalCapture
from backend.nvp_temporal_ledger import TICKS_PER_SECOND


class FakeDevice:
    def __init__(self):
        self.callback=None
        self.stopped=False
        self.closed=False
    def start(self,callback):
        import array
        self.callback=callback
        callback.send(array.array("h",[450]*10000))
    def stop(self):self.stopped=True
    def close(self):self.closed=True


class NativeCaptureHostTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.plan=ExactTimeShotSequence(self.index).publish(
            self.pid,"CaptureCameraSource",scene_id="spatial_world",
            scene_revision=1,duration_tick=str(TICKS_PER_SECOND),
            shots=[{"shot_id":"PrimaryCamera","camera_path":"/World/ListenerLeft",
                "start_tick":"0","end_tick":str(TICKS_PER_SECOND),
                "pattern":"continuous"}])
        self.allowed=True
        self.calls=[]
        self.device=FakeDevice()
        def ask(message):
            self.calls.append(message)
            return self.allowed
        self.trusted=TrustedNativeOriginalCapture(
            self.index,native_window=lambda:None,ask_native=ask,
            single_device_factory=lambda:self.device)
        self.addCleanup(self.trusted.close)
        self.request={
            "project_id":self.pid,"take_id":"RecordedTake",
            "scene_id":"spatial_world","scene_revision":1,
            "scene_document_sha256":self.index.read_revision(
                self.pid,"spatial_world",1)["document_sha256"],
            "camera_timeline_id":"CaptureCameraSource",
            "camera_timeline_revision":1,
            "camera_timeline_document_sha256":self.plan["document_sha256"],
            "sound_timeline_id":"RecordedTimeline",
            "source_id":"OriginalMicSignal","emitter_path":"/World/Actor",
            "event_id":"OriginalMicEvent","subject_id":"OriginalActor"}

    def test_original_device_requires_separate_start_and_freeze_dialogs(self):
        started=self.trusted.begin(self.request)
        self.assertEqual(started["status"],"RECORDING")
        self.assertFalse(started["original_pcm_durable"])
        self.assertEqual(len(self.calls),1)
        result=self.trusted.finish()
        self.assertEqual(result["status"],"FROZEN_ORIGINAL_LIVE_TAKE")
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.trusted.status()["status"],"IDLE")
        rec=self.index.read_revision(self.pid,"RecordedTake",1)
        self.assertEqual(rec["document_sha256"],result["take_document_sha256"])
        self.assertFalse(result["picture_frames_generated"])
        self.assertTrue(self.device.stopped and self.device.closed)

    def test_denied_start_never_opens_device_or_creates_take(self):
        self.allowed=False
        with self.assertRaises(PermissionError):
            self.trusted.begin(self.request)
        self.assertIsNone(self.device.callback)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RecordedTake",1)

    def test_stale_original_scene_and_camera_sha_rejected_without_consent(self):
        for key in ("scene_document_sha256","camera_timeline_document_sha256"):
            with self.subTest(key=key):
                bad={**self.request,key:"0"*64}
                with self.assertRaises(PermissionError):
                    self.trusted.begin(bad)
                self.assertEqual(len(self.calls),0)

    def test_cancel_and_close_cannot_freeze_unapproved_take(self):
        self.trusted.begin(self.request)
        stopped=self.trusted.cancel()
        self.assertEqual(stopped["status"],"CANCELLED")
        self.assertEqual(len(self.calls),1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RecordedTake",1)
        self.trusted.close()
        with self.assertRaises(PermissionError):
            self.trusted.begin(self.request)

    def test_second_session_blocked_and_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            self.trusted.begin({**self.request,"creator_approved":True})
        self.trusted.begin(self.request)
        with self.assertRaises(RuntimeError):
            self.trusted.begin(self.request)
        self.assertEqual(len(self.calls),1)

    def test_freeze_denial_keeps_no_approved_take(self):
        self.trusted.begin(self.request)
        self.allowed=False
        with self.assertRaises(PermissionError):
            self.trusted.finish()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RecordedTake",1)
        self.assertEqual(self.trusted.status()["status"],"IDLE")
        self.assertTrue(self.trusted.interrupted(self.pid)["items"])


if __name__=="__main__":
    unittest.main()
