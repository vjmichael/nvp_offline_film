"""WO6-07C real frozen USD -> untrusted model text -> human review ->
two independent native consents -> original source-preserving new shot.

The model is intentionally injected here (not genuine GGUF inference).
A real installed GGUF/React pipeline is separately tested in WO6-07B.
"""
from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_nvp_wo6_scene_tool_context as source_fixture
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_wo6_desktop_bridge import TrustedDesktopWO6Bridge
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides

T=TICKS_PER_SECOND


class Model:
    def complete(self,system,user):
        return ('Consider moving to an 85 mm shot with a tighter frame. '
                'This is untrusted filmmaking advice and not a tool call.')


class Window:
    def __init__(self,answers=None):
        self.answers=list(answers or [])
        self.prompts=[]
        self.url="http://127.0.0.1:43322/"
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self,title,message):
        self.prompts.append((title,message))
        return self.answers.pop(0) if self.answers else False


class OriginalSourceDirectorHandoff(unittest.TestCase):
    def setUp(self):
        source_fixture.NativeSceneCrewContext.setUp(self)
        self.take_sha=self.take["document_sha256"]
        self.home=self.root/"wo6_07c_disposable_native"
        self.env=patch.dict(os.environ,{"NVP_HOME":str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.window=Window()
        self.bridge=TrustedDesktopWO6Bridge(
            self.index,origin="http://127.0.0.1:43322",
            host_factory=lambda _:None,
            director_writer_factory=lambda _:Model())
        self.bridge._attach_window(self.window)
        self.addCleanup(self.bridge._close)

    def proposal(self):
        request={
            "project_id":self.pid,
            "take_id":"OriginalTake","take_sha256":self.take_sha,
            "film_tick":str(T),
            "direction":"Suggest a better original camera shot",
            "model_id":"test-only-model",
        }
        queued=self.bridge.wo6_suggest_from_local_model(request)
        self.assertEqual(queued["state"],"GENERATING")
        for _ in range(200):
            status=self.bridge.wo6_model_proposal_status(
                self.pid,queued["proposal_id"])
            if status["state"]=="READY_FOR_HUMAN_REVIEW":
                return queued["proposal_id"],status["proposal"]
            if status["state"]=="FAILED":
                self.fail("Source-context model advice rejected unexpectedly")
            time.sleep(.02)
        self.fail("Native model thread did not produce advisory text")

    def review(self,proposal_id,proposal,action_kind="camera"):
        return self.bridge.wo6_review_model_proposal({
            "project_id":self.pid,
            "proposal_id":proposal_id,
            "take_id":"OriginalTake","take_sha256":self.take_sha,
            "model_text_sha256":proposal["model_text_sha256"],
            "verified_source_context_sha256":
                proposal["verified_source_context_sha256"],
            "action_kind":action_kind,
        })

    def shot_request(self,proposal_id,shot_id="human_reviewed_camera"):
        scene=self.index.read_revision(self.pid,"OriginalScene",1)
        impact=self.bridge.wo6_source_impact({
            "project_id":self.pid,"source_id":"OriginalScene",
            "source_revision":1,
            "source_sha256":scene["document_sha256"],
            "change_kind":"revise_camera",
        })
        self.assertEqual(
            impact["status"],"READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT")
        return {
            "project_id":self.pid,"action_kind":"camera",
            "shot_id":shot_id,
            "take_id":"OriginalTake","take_sha256":self.take_sha,
            "scene_id":"OriginalScene","scene_revision":1,
            "scene_sha256":scene["document_sha256"],
            "start_tick":0,"end_tick":T,
            "changes":[{
                "path":"/World/Camera",
                "property":"camera_focal_length_mm","value":85.0,
            }],
            "purpose":"framing","continuity_policy":"intentional_cheat",
            "reason":"I independently chose a tighter 85 mm framing after reviewing a model suggestion.",
            "preview_sha256":impact["preview_sha256"],
            "reviewed_proposal_id":proposal_id,
        }

    def test_native_handoff_requires_review_and_two_os_prompts_then_writes_original_preserving_shot(self):
        proposal_id,proposal=self.proposal()
        self.assertEqual(self.window.prompts,[])
        request=self.shot_request(proposal_id)
        # AI generated text alone cannot trigger native worker admission.
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_shot(request)
        self.assertEqual(self.window.prompts,[])
        reviewed=self.review(proposal_id,proposal)
        self.assertEqual(
            reviewed["status"],"HUMAN_SELECTED_AI_CONSULTATION_NO_GRANT")
        self.assertFalse(reviewed["native_worker_authorized"])
        self.assertFalse(reviewed["creative_approval_granted"])
        self.assertEqual(self.window.prompts,[])
        # First native dialog approves independently chosen camera opinions;
        # second dialog approves exactly hashed first-party worker.
        self.window.answers=[True,True]
        with patch.object(self.bridge,"_wo6_result",
                side_effect=lambda task,host: {
                    "queued_task_id":task["task_id"],"state":"QUEUED",
                    "native_worker_success_verified":False}):
            queued=self.bridge.wo6_create_shot(request)
        self.assertEqual(queued["state"],"QUEUED")
        self.assertEqual(queued["reviewed_ai_proposal_id"],proposal_id)
        self.assertEqual(len(self.window.prompts),2)
        self.assertIn("Director approval",self.window.prompts[0][0])
        self.assertIn("Separate native worker",self.window.prompts[1][0])
        self.assertIn(proposal["model_text_sha256"],
                      self.window.prompts[0][1])
        self.assertTrue(
            self.index.read_revision(self.pid,"OriginalTake",1)["data"]["frozen"])
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.take_sha)
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_shot({
                **request,"shot_id":"duplicate_review_request"})
        task_id=queued["queued_task_id"]
        native=self.bridge._wo6_shot
        spec=json.loads((native.root/task_id/"task.json").read_text())
        self.assertEqual(
            spec["reviewed_ai_consultation"]["model_text_sha256"],
            proposal["model_text_sha256"])
        self.assertNotIn("suggestion_text",str(spec))
        done=native.run_next(
            timeout_seconds=150,expected_task_id=task_id)
        self.assertEqual(done["state"],"SUCCEEDED")
        evaluated=OpenUSDShotOverrides(
            self.index,verify_director_action=lambda *_:False).evaluate(
            self.pid,"human_reviewed_camera",1,tick=T//2)
        self.assertEqual(evaluated["shot_document_sha256"],
                         done["shot_document_sha256"])
        native_receipt=json.loads(
            (native.root/task_id/"receipt.json").read_text())
        self.assertEqual(
            native_receipt["reviewed_ai_consultation"]["model_text_sha256"],
            proposal["model_text_sha256"])
        self.assertFalse(native_receipt["model_approval_accepted"])
        durable=self.bridge.wo6_task_status(self.pid,task_id)
        self.assertEqual(durable["state"],"SUCCEEDED")
        self.assertEqual(
            durable["reviewed_ai_consultation"]["proposal_id"],proposal_id)
        self.assertFalse(durable["reviewed_model_text_is_authority"])
        self.assertFalse(evaluated["source_performance_modified"])
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.take_sha)
        self.assertEqual(len(self.window.prompts),2)

    def test_denied_human_os_dialog_leaves_original_and_ai_review_unconsumed(self):
        proposal_id,proposal=self.proposal()
        self.review(proposal_id,proposal)
        request=self.shot_request(proposal_id,shot_id="declined_by_director")
        self.window.answers=[False]
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_shot(request)
        self.assertEqual(len(self.window.prompts),1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"declined_by_director")
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.take_sha)
        # Denial is not an approval, so a separate fresh creator choice
        # may retry through the two native dialogs.
        self.window.answers=[True,False]
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_shot(request)
        self.assertEqual(len(self.window.prompts),3)

    def test_stale_scene_wrong_action_and_mismatched_model_sha_are_refused_before_consent(self):
        proposal_id,proposal=self.proposal()
        with self.assertRaises(PermissionError):
            self.bridge.wo6_review_model_proposal({
                "project_id":self.pid,
                "proposal_id":proposal_id,"take_id":"OriginalTake",
                "take_sha256":self.take_sha,
                "model_text_sha256":"0"*64,
                "verified_source_context_sha256":
                    proposal["verified_source_context_sha256"],
                "action_kind":"camera",
            })
        self.review(proposal_id,proposal)
        request=self.shot_request(proposal_id)
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_shot({
                **request,"action_kind":"lighting"})
        self.assertEqual(self.window.prompts,[])
        OpenUSDSceneBridge(self.index).publish(
            self.pid,"OriginalScene",prims=self.actor_scene,
            curves=[],native_schemas=True,expected_revision=1)
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_shot(request)
        self.assertEqual(self.window.prompts,[])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"human_reviewed_camera")

    def test_review_is_not_automatically_restored_after_desktop_restart(self):
        proposal_id,proposal=self.proposal()
        self.review(proposal_id,proposal)
        self.bridge._close()
        renewed=TrustedDesktopWO6Bridge(
            self.index,origin="http://127.0.0.1:43322",
            host_factory=lambda _:None,
            director_writer_factory=lambda _:Model())
        self.addCleanup(renewed._close)
        renewed._attach_window(Window([True,True]))
        with self.assertRaises(PermissionError):
            renewed.wo6_create_shot(self.shot_request(proposal_id))
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.take_sha)


if __name__=="__main__":
    unittest.main()
