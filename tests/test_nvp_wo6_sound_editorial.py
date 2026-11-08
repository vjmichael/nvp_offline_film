"""WO6-07D real PCM source and source-slate edit through existing contained host.

Native worker is REAL, the approval callbacks are test-only OS substitutes.
This does not render/mix recorded sound or complete a film.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

import test_nvp_wo6_native_data_action as original_fixture
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_sound_editorial_decisions import (
    preview_typed_decision,verify_sound_cue,verify_editorial_cut)

T=TICKS_PER_SECOND


class NativeSoundAndSlateFilmTime(unittest.TestCase):
    def setUp(self):
        original_fixture.NativeFilmDecisionAcceptance.setUp(self)
        self.take_sha=self.original["document_sha256"]
        self.timeline_sha=self.index.read_revision(
            self.pid,"actions",1)["document_sha256"]
        self.pcm=RecordedSoundSources(self.index)
        self.pcm.publish(self.pid,"original_recording",
                         [bytes([12,0])*48000])
        self.sound_sha=self.index.read_revision(
            self.pid,"original_recording",1)["document_sha256"]
        self.slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        self.graph=self.slate.publish_graph(
            self.pid,"original_slate",scene_id="world",
            scene_label="SceneOne",nodes=[{
                "branch_id":"root_take",
                "kind":"performance","parent_id":None,"fork_tick":None,
                "group_id":"director_group","primary":True,
                "take_id":"old_take",
                "source_start_tick":0,"source_end_tick":2*T,
                "shot_id":None,"shot_revision":None,
                "slate":{
                    "scene":"SceneOne","setup":"A","shot":"master",
                    "camera":"original","take_number":1,
                    "wild":False,"script_revision":"1","notes":"Original source",
                },
            }])
        self.graph_sha=self.graph["document_sha256"]

    def authored(self,kind,id):
        src="actions" if kind=="sound_cue" else "original_slate"
        sha=self.timeline_sha if kind=="sound_cue" else self.graph_sha
        change="revise_sound" if kind=="sound_cue" else "revise_edit"
        payload=({
            "cue_id":"human_river_sound","subject_id":"Actor",
            "start_tick":T,"end_tick":2*T,
            "recorded_sound_id":"original_recording",
            "recorded_sound_revision":1,
            "recorded_sound_sha256":self.sound_sha,
            "first_sample":0,"gain":0.6,
        } if kind=="sound_cue" else [
            {"segment_id":"intro","branch_id":"root_take",
             "source_in_tick":0,"source_out_tick":T},
            {"segment_id":"middle","branch_id":"root_take",
             "source_in_tick":T,"source_out_tick":2*T},
        ])
        typed={
            "project_id":self.pid,"decision_kind":kind,
            "decision_id":id,"source_id":src,
            "source_revision":1,"source_sha256":sha,
            "payload":payload,
            "duration_tick":str(3*T) if kind=="sound_cue" else None,
        }
        proof=preview_typed_decision(self.index,typed)
        impact=preview_source_impact(
            self.index,self.pid,src,1,sha,change,max_nodes=32)
        self.assertEqual(proof["status"],"READ_ONLY_TYPED_DECISION_NO_GRANT")
        self.assertFalse(proof["native_worker_authorized"])
        self.assertEqual(
            impact["status"],"READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT")
        return {
            "creator_decision_id":"creator_clicked_yes",
            **{k:typed[k] for k in (
                "decision_kind","decision_id","source_id",
                "source_revision","source_sha256","payload","duration_tick")},
            "expected_preview_sha256":impact["preview_sha256"],
            "expected_typed_preview_sha256":proof["typed_preview_sha256"],
        }

    def test_real_native_pcm_derived_sound_timeline_preserves_original_bytes(self):
        original=self.index.read_revision(self.pid,"actions",1)
        source=self.pcm.read(self.pid,"original_recording",1,0,8000)
        req=self.authored("sound_cue","human_sound_timeline")
        queued=self.host.queue_decision(self.scope,**req)
        self.assertEqual(queued["state"],"QUEUED")
        self.assertEqual(len(self.creator_reviews),1)
        self.assertEqual(len(self.native_reviews),1)
        self.assertEqual(self.creator_reviews[0]["decision_kind"],"sound_cue")
        self.assertFalse(self.creator_reviews[0]["no_render_or_release_approval"] is False)
        done=self.host.run_next(
            timeout_seconds=150,expected_task_id=queued["task_id"])
        self.assertEqual(done["state"],"SUCCEEDED")
        self.assertEqual(
            done["decision_sha256"],
            verify_sound_cue(self.index,{
                "project_id":self.pid,
                "decision_kind":"sound_cue",
                "decision_id":"human_sound_timeline",
                "source_id":"actions","source_revision":1,
                "source_sha256":self.timeline_sha,
                "payload":req["payload"],"duration_tick":str(3*T),
            }))
        timeline=TemporalLedger(self.index)
        old=timeline.events_in(
            self.pid,"actions",1,start_tick=0,end_tick=3*T)["events"]
        new=timeline.events_in(
            self.pid,"human_sound_timeline",1,start_tick=0,end_tick=3*T)["events"]
        self.assertEqual(len(old),1)
        self.assertEqual(len(new),2)
        self.assertEqual(new[-1]["source_id"],"original_recording")
        self.assertEqual(new[-1]["payload"]["source_sample_count"],48000)
        self.assertEqual(
            self.index.read_revision(self.pid,"actions",1),original)
        self.assertEqual(
            self.pcm.read(self.pid,"original_recording",1,0,8000),source)
        self.assertEqual(self.index.read_revision(
            self.pid,"old_take",1)["document_sha256"],self.take_sha)
        receipt=json.loads((self.host.root/queued["task_id"]/
                            "receipt.json").read_text())
        self.assertFalse(receipt["model_approval_accepted"])
        self.assertFalse(receipt["film_delivered"])

    def test_real_native_original_slate_two_segment_assembled_editorial_cut(self):
        request=self.authored("editorial_cut","director_assembled_cut")
        queued=self.host.queue_decision(self.scope,**request)
        self.assertEqual(queued["state"],"QUEUED")
        self.assertEqual(self.creator_reviews[0]["decision_kind"],"editorial_cut")
        completed=self.host.run_next(
            timeout_seconds=150,expected_task_id=queued["task_id"])
        self.assertEqual(completed["state"],"SUCCEEDED")
        self.assertEqual(completed["decision_sha256"],verify_editorial_cut(
            self.index,{
                "project_id":self.pid,
                "decision_kind":"editorial_cut",
                "decision_id":"director_assembled_cut",
                "source_id":"original_slate","source_revision":1,
                "source_sha256":self.graph_sha,
                "payload":request["payload"],"duration_tick":None,
            }))
        cut=SlateSequenceAssembly(
            self.slate,verify_editor_action=lambda *_:False).open_edit(
                self.pid,"director_assembled_cut",1)
        self.assertTrue(cut["data"]["explicit_editor_commit"])
        self.assertFalse(cut["data"]["source_performance_modified"])
        self.assertFalse(cut["data"]["render_approved"])
        self.assertEqual(len(cut["data"]["segments"]),2)
        self.assertEqual(cut["data"]["duration_tick"],2*T)
        self.assertEqual(self.index.read_revision(
            self.pid,"old_take",1)["document_sha256"],self.take_sha)
        self.assertEqual(self.index.read_revision(
            self.pid,"original_slate",1)["document_sha256"],self.graph_sha)

    def test_reject_missing_typed_preview_injected_sound_or_mismatched_sha(self):
        request=self.authored("sound_cue","refused_sound_cue")
        variants=[
            {**request,"expected_typed_preview_sha256":"0"*64},
            {**request,"expected_typed_preview_sha256":None},
            {**request,"payload":{**request["payload"],
                                  "recorded_sound_sha256":"0"*64}},
            {**request,"payload":{**request["payload"],
                                  "gain":float("nan")}},
            {**request,"payload":{**request["payload"],
                                  "first_sample":48000}},
            {**request,"payload":{**request["payload"],
                                  "native_worker_authorized":True}},
            {**request,"payload":{**request["payload"],
                                  "start_tick":T+1}},
        ]
        for mutated in variants:
            with self.subTest(fields=mutated),self.assertRaises(
                    (ValueError,PermissionError,RuntimeError)):
                self.host.queue_decision(self.scope,**mutated)
        self.assertEqual(self.creator_reviews,[])
        self.assertEqual(self.native_reviews,[])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"refused_sound_cue")

    def test_source_change_denied_consent_and_forged_edit_branch_fail(self):
        request=self.authored("editorial_cut","refused_cut")
        self.creator_ok=False
        with self.assertRaises(PermissionError):
            self.host.queue_decision(self.scope,**request)
        self.creator_ok=True
        with self.assertRaises((ValueError,PermissionError)):
            self.host.queue_decision(self.scope,**{
                **request,"payload":[{
                    "segment_id":"fake","branch_id":"no_such_branch",
                    "source_in_tick":0,"source_out_tick":T,
                }]})
        self.assertFalse(self.native_reviews)
        self.assertFalse(self.index.read_revision(
            self.pid,"old_take",1)["document_sha256"]!=self.take_sha)


if __name__=="__main__":
    unittest.main()
