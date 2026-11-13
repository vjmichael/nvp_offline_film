"""PLAN-02-B trusted host never accepts browser approval as a Take grant."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import test_nvp_data_av_native as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_native_capture_desktop import TrustedNativeOriginalCapture
from backend.nvp_p1a_original_capture_worker_bridge import OriginalMicrophoneNativeWorkerAudit
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

    def _native_audit_controller(self,callback):
        # Isolated host-injected audit fixture. Actual ProtectedNativeWorker
        # compiler/job/cgroup evidence is tested separately; never invented.
        native_auditor=object.__new__(OriginalMicrophoneNativeWorkerAudit)
        controller=TrustedNativeOriginalCapture(
            self.index,native_window=lambda:None,
            ask_native=lambda message: self.calls.append(
                "FREEZE" if message.startswith("Freeze") else "START") or True,
            single_device_factory=lambda:self.device,
            native_pcm_auditor=native_auditor)
        self.addCleanup(controller.close)
        return native_auditor,controller

    def test_compiled_capture_audit_precedes_original_take_freeze(self):
        calls=[]
        def audit(self_auditor,**kwargs):
            calls.append(("AUDIT",kwargs["original_pcm_sha256"],
                          kwargs["recorded_samples"],kwargs["source_id"]))
            return {"format":"test-only-native-capture-audit",
                    "all_window_results_and_os_custody_verified":True,
                    "device_capture_implemented_by_compiled_worker":False}
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                OriginalMicrophoneNativeWorkerAudit,
                "verify_original_spool",new=audit))
            if __import__("os").name=="nt":
                # Only native EFS fixture; this is NOT actual physical
                # encryption acceptance on the developer's Windows machine.
                stack.enter_context(patch(
                    "backend.nvp_w1g_encrypted_source.require_efs_stage"))
                stack.enter_context(patch(
                    "backend.nvp_w1g_encrypted_source.verify_efs_inputs"))
                stack.enter_context(patch(
                    "backend.nvp_data_first_filming.require_efs_stage"))
                stack.enter_context(patch(
                    "backend.nvp_data_first_filming.verify_efs_inputs"))
            _,controller=self._native_audit_controller(audit)
            controller.begin(self.request)
            result=controller.finish()
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][2],10000)
        self.assertEqual(calls[0][3],"OriginalMicSignal")
        self.assertEqual(result["status"],"FROZEN_ORIGINAL_LIVE_TAKE")
        self.assertTrue(result["compiled_capture_worker_audit"][
            "all_window_results_and_os_custody_verified"])
        self.assertFalse(result["compiled_worker_is_device_recorder"])
        self.assertEqual(self.index.read_revision(
            self.pid,"RecordedTake",1)["document_sha256"],
            result["take_document_sha256"])
        self.assertEqual(self.calls,["START","FREEZE"])

    def test_failed_compiled_audit_keeps_original_pcm_unapproved(self):
        def reject(self_auditor,**kwargs):
            raise PermissionError("First-party native capture custody refused")
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                OriginalMicrophoneNativeWorkerAudit,
                "verify_original_spool",new=reject))
            if __import__("os").name=="nt":
                stack.enter_context(patch(
                    "backend.nvp_w1g_encrypted_source.require_efs_stage"))
                stack.enter_context(patch(
                    "backend.nvp_w1g_encrypted_source.verify_efs_inputs"))
            _,controller=self._native_audit_controller(reject)
            controller.begin(self.request)
            with self.assertRaisesRegex(PermissionError,"custody refused"):
                controller.finish()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"OriginalMicSignal",1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RecordedTake",1)
        self.assertEqual(self.calls,["START"])
        self.assertTrue(controller.interrupted(self.pid)["items"])

    @unittest.skipUnless(__import__("os").name=="nt",
                         "Windows EFS source-at-rest gate")
    def test_windows_efs_refusal_never_opens_microphone_or_creates_take(self):
        auditor,controller=self._native_audit_controller(None)
        with patch("backend.nvp_w1g_encrypted_source.require_efs_stage",
                   side_effect=PermissionError(
                       "Original recording directory has no genuine Windows EFS")):
            with self.assertRaisesRegex(PermissionError,"genuine Windows EFS"):
                controller.begin(self.request)
        self.assertIsNone(self.device.callback)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RecordedTake",1)

    @unittest.skipUnless(__import__("os").name=="nt",
                         "Windows second-stage EFS inheritance gate")
    def test_windows_take_spool_efs_refusal_preserves_unapproved_take(self):
        def audit(self_auditor,**kwargs):
            return {"format":"test-only-original-native-audit",
                    "all_window_results_and_os_custody_verified":True}
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                OriginalMicrophoneNativeWorkerAudit,
                "verify_original_spool",new=audit))
            stack.enter_context(patch(
                "backend.nvp_w1g_encrypted_source.require_efs_stage"))
            stack.enter_context(patch(
                "backend.nvp_w1g_encrypted_source.verify_efs_inputs"))
            stack.enter_context(patch(
                "backend.nvp_data_first_filming.require_efs_stage"))
            stack.enter_context(patch(
                "backend.nvp_data_first_filming.verify_efs_inputs",
                side_effect=PermissionError("Take PCM spool is not EFS-encrypted")))
            _,controller=self._native_audit_controller(audit)
            controller.begin(self.request)
            with self.assertRaisesRegex(PermissionError,"not EFS-encrypted"):
                controller.finish()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RecordedTake",1)
        self.assertTrue(controller.interrupted(self.pid)["items"])

    def test_browser_request_cannot_inject_a_fake_native_audit(self):
        with self.assertRaises(TypeError):
            TrustedNativeOriginalCapture(
                self.index,native_window=lambda:None,
                ask_native=lambda _:True,native_pcm_auditor=object())
        with self.assertRaises(ValueError):
            self.trusted.begin({**self.request,
                                "native_pcm_auditor":{"approved":True}})

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
