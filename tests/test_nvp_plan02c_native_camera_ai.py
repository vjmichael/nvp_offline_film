"""PLAN-02-C canonical original Take rail/AI source contract (no mocked GGUF claim)."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

import test_nvp_data_av_native as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_plan02c_rails import (
    CanonicalSourceRails,normalize_rail,evaluate_rail)
from backend.nvp_plan02c_model_advice import generate_source_camera_advice
from backend.nvp_wo6_verified_local_model import FORMAT as MODEL_FORMAT
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


class FakeCompletionContract:
    """Parser contract only; this is NOT a real GGUF smoke or weight proof."""
    def __init__(self,start,end,model_id="mock-contract-only"):
        self.model_id=model_id
        self.start=start
        self.end=end
        self.retime=False
        self.bad_receipt=False
        self.completion_receipt=None

    def complete_camera_candidate(self,system,user,schema):
        assert "source_observation" in user
        assert schema["properties"]["nodes"]["maxItems"]==4
        nodes=[]
        for tick,pos in ((self.start,[0.,0.,0.]),
                         (self.end+1 if self.retime else self.end,
                          [0.5,0.,0.])):
            nodes.append({"tick":tick,"position_m":pos,
                "target_m":[0.,3.,0.],"roll_deg":0.,
                "focal_length_mm":35.,"focus_distance_m":3.})
        text=json.dumps({"technique":"dolly","nodes":nodes},
                        separators=(",",":"))
        self.completion_receipt={
            "format":MODEL_FORMAT,"selected_model_id":self.model_id,
            "provider_reported_model_id":(
                "forged-gguf" if self.bad_receipt else self.model_id),
            "generated_text_sha256":sha256(text.encode()).hexdigest(),
            "provider_reported_completion_tokens":40,
            "native_worker_authorized":False,
            "provider_self_report_not_attestation":True}
        return text


class CanonicalDirectorRailTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.approvals=[]
        self.native_allow=True
        self.plan=ExactTimeShotSequence(self.index).publish(
            self.pid,"PLAN02CSourceCamera",
            scene_id="spatial_world",scene_revision=1,
            duration_tick=str(2*T),
            shots=[{"shot_id":"SourceShot","camera_path":"/World/ListenerLeft",
                    "start_tick":"0","end_tick":str(2*T),
                    "pattern":"continuous"}])
        class Window:
            def __init__(this):this.url="http://127.0.0.1:7777/"
            def get_current_url(this):return this.url
            def create_confirmation_dialog(this,title,message):
                self.approvals.append((title,message))
                return self.native_allow
        self.bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        self.bridge._attach_window(Window())
        self.addCleanup(self.bridge._close)
        catalog=self.bridge.plan02c_catalog(self.pid)
        self.assertEqual(catalog["format"],
                         "nvp.plan02c.canonical_camera_source_catalog.v1")
        self.assertTrue(catalog["sources"])
        chosen=next(row for row in catalog["sources"]
                    if row["camera_timeline_id"]=="PLAN02CSourceCamera")
        self.spec=deepcopy(chosen["suggested_unapproved_rail_spec"])
        self.spec["camera_id"]="DirectorTestCam"
        self.rail="DirectorRail001"
        self.service=CanonicalSourceRails(
            self.index,approve=lambda scope:
                self.approvals.append(("backend",scope)) is None and
                self.native_allow)

    def preview(self,raw=None):
        return self.service.preview(
            self.pid,self.rail,raw or self.spec,expected_revision=0)

    def test_real_openusd_layer_preview_and_one_use_os_rail_approval(self):
        original=self.index.read_revision(
            self.pid,"frozen_audio_take",1)["document_sha256"]
        sound=self.sound.read(self.pid,"mic_signal",1,0,100)
        trial=self.bridge.plan02c_preview({
            "project_id":self.pid,"rail_id":self.rail,
            "expected_revision":0,"rail_spec":self.spec})
        self.assertFalse(trial["director_approved"])
        self.assertFalse(trial["native_worker_authorized"])
        self.assertGreaterEqual(len(trial["source_film_time_samples"]),2)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.rail,1)
        saved=self.bridge.plan02c_publish({
            "project_id":self.pid,"rail_id":self.rail,
            "expected_revision":0,"rail_spec":self.spec,
            "preview_sha256":trial["proposal_sha256"]})
        self.assertEqual(saved["format"],
            "nvp.plan02c.director_approved_rail_receipt.v1")
        self.assertFalse(saved["renderer_worker_authorized"])
        self.service.verify(self.pid,self.rail,1)
        self.assertEqual(
            self.index.read_revision(
                self.pid,"frozen_audio_take",1)["document_sha256"],original)
        self.assertEqual(self.sound.read(self.pid,"mic_signal",1,0,100),sound)
        self.assertEqual(len(self.approvals),1)
        with self.assertRaises(PermissionError):
            self.bridge.plan02c_publish({
                "project_id":self.pid,"rail_id":self.rail,
                "expected_revision":0,"rail_spec":self.spec,
                "preview_sha256":trial["proposal_sha256"]})
        self.assertEqual(len(self.approvals),1)

    def test_refusal_stale_preview_and_cross_source_are_fail_closed(self):
        trial=self.preview()
        self.native_allow=False
        with self.assertRaises(PermissionError):
            self.bridge.plan02c_publish({
                "project_id":self.pid,"rail_id":self.rail,
                "expected_revision":0,"rail_spec":self.spec,
                "preview_sha256":trial["proposal_sha256"]})
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.rail,1)
        self.native_allow=True
        revised=deepcopy(self.spec)
        revised["nodes"][1]["focal_length_mm"]=50.
        with self.assertRaises(PermissionError):
            self.bridge.plan02c_publish({
                "project_id":self.pid,"rail_id":self.rail,
                "expected_revision":0,"rail_spec":revised,
                "preview_sha256":trial["proposal_sha256"]})
        forged=deepcopy(self.spec)
        forged["take_document_sha256"]="0"*64
        with self.assertRaises(PermissionError):self.preview(forged)
        forged=deepcopy(self.spec)
        forged["film_end_tick"]=2*T+1
        with self.assertRaises(ValueError):self.preview(forged)
        forged=deepcopy(self.spec)
        forged["creator_approved"]=True
        with self.assertRaises(ValueError):self.preview(forged)

    def test_exact_film_time_source_rail_interpolation_not_frame_clock(self):
        rail=normalize_rail(self.spec,3*T)
        a=evaluate_rail(rail,0)
        b=evaluate_rail(rail,1234567)
        self.assertEqual(a["film_tick"],0)
        self.assertEqual(b["film_tick"],1234567)
        self.assertEqual(b["technique"],"static")
        self.assertFalse(b["source_performance_edited"])
        invalid=deepcopy(self.spec)
        invalid["nodes"][0]["position_m"][0]=99999.
        invalid["nodes"][1]["position_m"][0]=-99999.
        with self.assertRaises(ValueError):self.preview(invalid)

    def test_contract_only_model_advice_stays_unapproved_without_publishing(self):
        w=FakeCompletionContract(0,self.spec["film_end_tick"])
        advice=generate_source_camera_advice(
            self.service,self.pid,self.spec,
            direction="Gentle camera dolly near original actor",
            model_id=w.model_id,writer=w)
        self.assertEqual(advice["status"],"UNAPPROVED_SOURCE_CAMERA_ADVICE")
        self.assertFalse(advice["human_authorization_granted"])
        self.assertFalse(advice["actual_gguf_weights_verified"])
        self.assertFalse(advice["rail_published"])
        self.assertEqual(advice["proposed_rail_spec"]["film_end_tick"],
                         self.spec["film_end_tick"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.rail,1)
        w.retime=True
        with self.assertRaises(ValueError):
            generate_source_camera_advice(
                self.service,self.pid,self.spec,direction="No retiming",
                model_id=w.model_id,writer=w)
        w.retime=False;w.bad_receipt=True
        with self.assertRaises(PermissionError):
            generate_source_camera_advice(
                self.service,self.pid,self.spec,direction="Check forged source",
                model_id=w.model_id,writer=w)

    def test_disposable_real_model_retry_never_waives_source_or_receipt_failures(self):
        # No neural text is mocked as genuine GGUF in this contract test.
        from tools.nvp_plan02c_real_gguf import retryable_model_rejection
        self.assertTrue(retryable_model_rejection(
            ValueError("Camera look-at may not coincide with its position")))
        self.assertTrue(retryable_model_rejection(
            ValueError("AI cannot retime frozen source Film Time boundaries")))
        self.assertFalse(retryable_model_rejection(
            ValueError("Original Take SHA changed during model generation")))
        self.assertFalse(retryable_model_rejection(
            PermissionError("Creator refused native model execution")))
        self.assertFalse(retryable_model_rejection(
            RuntimeError("Model token/receipt identity changed")))

    def test_model_request_needs_distinct_native_human_approval(self):
        import unittest.mock as mock
        w=FakeCompletionContract(0,self.spec["film_end_tick"])
        request={"project_id":self.pid,"rail_id":self.rail,
                 "expected_revision":0,"rail_spec":self.spec,
                 "model_id":w.model_id,"direction":"Original shot dolly"}
        with mock.patch(
                "backend.nvp_plan02c_desktop.verified_writer_for",
                return_value=w) as writer:
            self.native_allow=False
            with self.assertRaises(PermissionError):
                self.bridge.plan02c_model_candidate(request)
            writer.assert_not_called()
            self.native_allow=True
            result=self.bridge.plan02c_model_candidate(request)
            self.assertTrue(result["model_request_human_approved"])
            self.assertFalse(result["rail_publication_human_approved"])
            self.assertFalse(result["rail_published"])
        self.assertEqual(len(self.approvals),2)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.rail,1)


if __name__=="__main__":
    unittest.main()
