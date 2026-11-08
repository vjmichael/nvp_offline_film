"""WO6-07D: original frozen Take -> human-reviewed advice ->
real PCM sound cue or digital-slate edit with TWO native consents and source SHA.

The model is a deliberately fake advisor in this isolated approval test.
Actual GGUF inference/installed visible model acceptance is separate WO6-07B.
"""
import json
import unittest
from unittest.mock import patch

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_wo6_sound_editorial_decisions import (
    verify_sound_cue,verify_editorial_cut)
from test_nvp_wo6_reviewed_director_shot import (
    OriginalSourceDirectorHandoff)

T=TICKS_PER_SECOND


class RealReviewedSoundAndEditorial(unittest.TestCase):
    def setUp(self):
        OriginalSourceDirectorHandoff.setUp(self)
        self.pcm=RecordedSoundSources(self.index)
        self.recorded=self.pcm.publish(
            self.pid,"AddedSourceFoley",[b"\x19\x12"*48000])
        self.graph=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False).publish_graph(
            self.pid,"DirectorOriginalSlate",scene_id="OriginalScene",
            scene_label="DirectorScene",nodes=[{
                "branch_id":"OriginalTakeBranch","kind":"performance",
                "parent_id":None,"fork_tick":None,
                "group_id":"OriginalGroup","primary":True,
                "take_id":"OriginalTake",
                "source_start_tick":0,"source_end_tick":2*T,
                "shot_id":None,"shot_revision":None,
                "slate":{
                    "scene":"DirectorScene","setup":"A","shot":"Master",
                    "camera":"Camera1","take_number":1,
                    "wild":False,"script_revision":"1",
                    "notes":"Original frozen creator Take",
                },
            }])
        self.original_timeline_sha=self.temporal["document_sha256"]
        self.original_take_sha=self.take_sha

    def proposal(self):
        return OriginalSourceDirectorHandoff.proposal(self)

    def review(self,pid,proposal,action_kind="sound_cue"):
        return OriginalSourceDirectorHandoff.review(
            self,pid,proposal,action_kind=action_kind)

    def request(self,kind,decision_id):
        if kind=="sound_cue":
            source_id="OriginalActions"
            sha=self.original_timeline_sha
            payload={
                "cue_id":"NewHumanFoley",
                "subject_id":"Actor",
                "start_tick":T,"end_tick":2*T,
                "recorded_sound_id":"AddedSourceFoley",
                "recorded_sound_revision":1,
                "recorded_sound_sha256":self.recorded["document_sha256"],
                "first_sample":0,"gain":0.55,
            }
            duration=str(3*T)
            change="revise_sound"
        else:
            source_id="DirectorOriginalSlate"
            sha=self.graph["document_sha256"]
            payload=[
                {"segment_id":"OriginalA","branch_id":"OriginalTakeBranch",
                 "source_in_tick":0,"source_out_tick":T},
                {"segment_id":"OriginalB","branch_id":"OriginalTakeBranch",
                 "source_in_tick":T,"source_out_tick":2*T},
            ]
            duration=None
            change="revise_edit"
        typed={
            "project_id":self.pid,"decision_kind":kind,
            "decision_id":decision_id,
            "source_id":source_id,"source_revision":1,
            "source_sha256":sha,"payload":payload,
            "duration_tick":duration,
            "director_reason":"I selected this original sound or edit independently after discussing the Take.",
        }
        preview=self.bridge.wo6_preview_typed_decision(typed)
        self.assertEqual(preview["status"],
                         "READ_ONLY_TYPED_DECISION_NO_GRANT")
        self.assertFalse(preview["native_worker_authorized"])
        impact=self.bridge.wo6_source_impact({
            "project_id":self.pid,
            "source_id":source_id,"source_revision":1,
            "source_sha256":sha,"change_kind":change,
        })
        self.assertEqual(
            impact["status"],"READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT")
        return {
            **typed,"typed_preview_sha256":preview["typed_preview_sha256"],
            "preview_sha256":impact["preview_sha256"],
        }

    def test_human_reviewed_recorded_pcm_source_cue_two_native_grants(self):
        proposal_id,proposal=self.proposal()
        req=self.request("sound_cue","NewCreatorSoundTimeline")
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_decision({
                **req,"reviewed_proposal_id":proposal_id})
        self.assertEqual(self.window.prompts,[])
        reviewed=self.review(proposal_id,proposal,"sound_cue")
        self.assertFalse(reviewed["native_worker_authorized"])
        self.assertFalse(reviewed["creative_approval_granted"])
        self.window.answers=[True,True]
        with patch.object(self.bridge,"_wo6_result",
                side_effect=lambda task,host:{
                    "queued_task_id":task["task_id"],
                    "state":"QUEUED","native_worker_success_verified":False}):
            queued=self.bridge.wo6_create_decision({
                **req,"reviewed_proposal_id":proposal_id})
        self.assertEqual(len(self.window.prompts),2)
        self.assertEqual(queued["reviewed_ai_proposal_id"],proposal_id)
        self.assertEqual(
            queued["reviewed_model_text_sha256"],proposal["model_text_sha256"])
        native=self.bridge._wo6_data
        task=queued["queued_task_id"]
        spec=json.loads((native.root/task/"task.json").read_text())
        self.assertEqual(spec["director_reason"],req["director_reason"])
        self.assertEqual(
            spec["reviewed_ai_consultation"]["model_text_sha256"],
            proposal["model_text_sha256"])
        self.assertNotIn("suggestion_text",str(spec))
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_decision({
                **req,"reviewed_proposal_id":proposal_id,
                "decision_id":"DuplicateSound"})
        done=native.run_next(timeout_seconds=150,expected_task_id=task)
        self.assertEqual(done["state"],"SUCCEEDED")
        source=self.index.read_revision(self.pid,"OriginalActions",1)
        sound=self.index.read_revision(self.pid,"AddedSourceFoley",1)
        self.assertEqual(source["document_sha256"],self.original_timeline_sha)
        self.assertEqual(sound["document_sha256"],self.recorded["document_sha256"])
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.original_take_sha)
        self.assertEqual(done["decision_sha256"],verify_sound_cue(self.index,spec))
        receipt=json.loads((native.root/task/"receipt.json").read_text())
        self.assertEqual(receipt["reviewed_ai_consultation"],
                         spec["reviewed_ai_consultation"])
        self.assertFalse(receipt["model_approval_accepted"])
        durable=self.bridge.wo6_task_status(self.pid,task)
        self.assertEqual(durable["state"],"SUCCEEDED")
        self.assertEqual(
            durable["reviewed_ai_consultation"]["proposal_id"],proposal_id)

    def test_human_reviewed_original_slate_edit_two_native_grants(self):
        proposal_id,proposal=self.proposal()
        self.review(proposal_id,proposal,"editorial_cut")
        req=self.request("editorial_cut","HumanDirectedAssembledEdit")
        self.window.answers=[True,True]
        with patch.object(self.bridge,"_wo6_result",
                side_effect=lambda task,host:{
                    "queued_task_id":task["task_id"],
                    "state":"QUEUED","native_worker_success_verified":False}):
            queued=self.bridge.wo6_create_decision({
                **req,"reviewed_proposal_id":proposal_id})
        self.assertEqual(len(self.window.prompts),2)
        native=self.bridge._wo6_data
        task=queued["queued_task_id"]
        spec=json.loads((native.root/task/"task.json").read_text())
        self.assertEqual(spec["director_reason"],req["director_reason"])
        done=native.run_next(timeout_seconds=150,expected_task_id=task)
        self.assertEqual(done["state"],"SUCCEEDED")
        self.assertEqual(done["decision_sha256"],verify_editorial_cut(self.index,spec))
        cut=SlateSequenceAssembly(
            DigitalSlateBranches(self.index,verify_editor_action=lambda *_:False),
            verify_editor_action=lambda *_:False).open_edit(
            self.pid,"HumanDirectedAssembledEdit",1)
        self.assertEqual(cut["data"]["duration_tick"],2*T)
        self.assertEqual(len(cut["data"]["segments"]),2)
        self.assertFalse(cut["data"]["render_approved"])
        self.assertEqual(
            self.index.read_revision(self.pid,"DirectorOriginalSlate",1)[
                "document_sha256"],self.graph["document_sha256"])
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.original_take_sha)
        receipt=json.loads((native.root/task/"receipt.json").read_text())
        self.assertEqual(
            receipt["reviewed_ai_consultation"]["model_text_sha256"],
            proposal["model_text_sha256"])

    def test_scene_revision_changed_after_two_approvals_blocks_native_sound_worker(self):
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        proposal_id,proposal=self.proposal()
        self.review(proposal_id,proposal,"sound_cue")
        request=self.request("sound_cue","CanceledDueToRevisedScene")
        self.window.answers=[True,True]
        with patch.object(self.bridge,"_wo6_result",
                side_effect=lambda task,host:{
                    "queued_task_id":task["task_id"],
                    "state":"QUEUED","native_worker_success_verified":False}):
            queued=self.bridge.wo6_create_decision({
                **request,"reviewed_proposal_id":proposal_id})
        task=queued["queued_task_id"]
        OpenUSDSceneBridge(self.index).publish(
            self.pid,"OriginalScene",prims=self.actor_scene,curves=[],
            native_schemas=True,expected_revision=1)
        with self.assertRaises(PermissionError):
            self.bridge._wo6_data.run_next(
                timeout_seconds=150,expected_task_id=task)
        self.assertEqual(
            self.bridge._wo6_ledger.get_task(task)["state"],"INTERRUPTED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"CanceledDueToRevisedScene")
        self.assertEqual(
            self.index.read_revision(self.pid,"OriginalTake",1)[
                "document_sha256"],self.original_take_sha)

    def test_ai_review_refuses_another_take_and_new_source_revision(self):
        proposal_id,proposal=self.proposal()
        self.review(proposal_id,proposal,"sound_cue")
        req=self.request("sound_cue","SoundWonNotCommit")
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_decision({
                **req,"reviewed_proposal_id":proposal_id,
                "source_id":"UnrelatedTimeline"})
        self.assertEqual(self.window.prompts,[])
        # Original Take stays immutable but its source temporal head moves.
        from backend.nvp_temporal_ledger import TemporalLedger
        TemporalLedger(self.index).publish(self.pid,"OriginalActions",[{
            "event_id":"UnrelatedEvent","event_kind":"annotation",
            "subject_id":"Actor","start_tick":0,"end_tick":T,
            "source_id":"OriginalScene","source_revision":1,
            "payload":{"director_note":"New original timeline head"},
        }],duration_tick=3*T,expected_revision=1)
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_decision({
                **req,"reviewed_proposal_id":proposal_id})
        self.assertEqual(self.window.prompts,[])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"SoundWonNotCommit")


if __name__=="__main__":
    unittest.main()
