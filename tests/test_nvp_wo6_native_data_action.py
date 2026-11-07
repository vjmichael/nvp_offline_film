"""WO6-05 real data-first color and authored camera-sequence OS execution."""
from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest

from backend.nvp_ai_read_host import TrustedReadScope, NativeAiReadHost
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_film_index import FilmIndex
from backend.nvp_native_color_decisions import NativeColorDecisions
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_data_action import NativeFilmDecisionHost

T=TICKS_PER_SECOND
GRADE={
    "exposure_stops":0.25,"contrast":1.1,"saturation":0.9,
    "temperature_kelvin":5600.,"tint_magenta_green":0.,
}


class NativeFilmDecisionAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.studio=Studio(root/"studio.sqlite3")
        self.pid=self.studio.create_project("Film Time and color native approvals","")["id"]
        self.index=FilmIndex(self.studio)
        self.scenes=OpenUSDSceneBridge(self.index)
        self.scenes.publish(self.pid,"world",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,2,-5]},
        ],curves=[{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":2*T,"position":[10,0,0]},
        ]}])
        self.index.register_revision(self.pid,"performance","performance",
                                     {"format":"wo6.test.performance"})
        TemporalLedger(self.index).publish(self.pid,"actions",[{
            "event_id":"move","event_kind":"action",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"performance","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor"},
        }],duration_tick=3*T)
        self.original=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:True).freeze(
                self.pid,"old_take",scene_id="world",scene_revision=1,
                timeline_id="actions",timeline_revision=1,
                sample_ticks=[0,T],creator_event="human")
        self.scope=TrustedReadScope("human_creator",self.pid,"turn_1")
        self.creator_ok=True
        self.host_ok=True
        self.creator_reviews=[]
        self.native_reviews=[]
        def creator(decision,creative):
            self.creator_reviews.append(creative)
            return (self.creator_ok and decision=="creator_clicked_yes" and
                    creative["no_original_take_or_scene_mutation"] is True and
                    creative["no_render_or_release_approval"] is True and
                    creative["typed_authoring_payload"] is not None)
        def native(scope,sha,doc):
            self.native_reviews.append((scope,sha))
            return self.host_ok and scope==self.scope
        self.ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
            time.time(),32768,24576,0.0,()))
        self.host=NativeFilmDecisionHost(
            self.index,self.ledger,(root/"work").absolute(),
            confirm_creator=creator,authorize_native=native)

    def _request(self,kind,id):
        src="old_take" if kind=="color" else "world"
        source=self.index.read_revision(self.pid,src,1)
        change="revise_color" if kind=="color" else "revise_camera"
        preview=preview_source_impact(
            self.index,self.pid,src,1,source["document_sha256"],
            change,max_nodes=32)
        seq=[
            {"shot_id":"master","camera_path":"/World/Camera",
             "start_tick":"0","end_tick":str(T),"pattern":"master"},
            {"shot_id":"reaction","camera_path":"/World/Camera",
             "start_tick":str(T+T//4),"end_tick":str(2*T),
             "pattern":"reaction"},
        ]
        return {
            "creator_decision_id":"creator_clicked_yes",
            "decision_kind":kind,"decision_id":id,"source_id":src,
            "source_revision":1,"source_sha256":source["document_sha256"],
            "payload":GRADE if kind=="color" else seq,
            "duration_tick":None if kind=="color" else str(3*T),
            "expected_preview_sha256":preview["preview_sha256"],
        }

    def test_real_native_grade_and_camera_cut_sequence_preserve_source(self):
        original_sha=self.original["document_sha256"]
        for kind in ("color","camera_sequence"):
            name="new_"+kind
            task=self.host.queue_decision(self.scope,**self._request(kind,name))
            self.assertEqual(task["state"],"QUEUED")
            self.assertFalse(task["native_worker_started"])
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,name)
            accepted=self.host.run_next(timeout_seconds=150)
            self.assertEqual(accepted["state"],"SUCCEEDED")
            self.assertFalse(accepted["film_delivered"])
            if kind=="color":
                output=NativeColorDecisions(self.index).read(self.pid,name,1)
                self.assertEqual(output["parameters"],GRADE)
                self.assertFalse(output["rendered_frames"])
                self.assertFalse(output["flat_master_approved"])
            else:
                output=ExactTimeShotSequence(self.index).read(self.pid,name,1)
                self.assertEqual(output["shots"][1]["gap_before_tick"],str(T//4))
                self.assertFalse(output["video_frames_created"])
                self.assertEqual(output["scene_document_sha256"],
                                 self.index.read_revision(
                                     self.pid,"world",1)["document_sha256"])
            self.assertEqual(accepted["decision_sha256"],
                             output["document_sha256"])
            self.assertEqual(
                self.ledger.get_task(task["task_id"])["state"],"SUCCEEDED")
            self.assertEqual(self.index.read_revision(
                self.pid,"old_take",1)["document_sha256"],original_sha)
        self.assertEqual(len(self.creator_reviews)>1,True)
        self.assertEqual(len(self.native_reviews)>1,True)

    def test_grants_revocation_bad_fields_and_ai_call_rejected(self):
        request=self._request("color","unapproved_grade")
        self.creator_ok=False
        with self.assertRaises(PermissionError):
            self.host.queue_decision(self.scope,**request)
        self.creator_ok=True
        self.host_ok=False
        with self.assertRaises(PermissionError):
            self.host.queue_decision(self.scope,**request)
        self.host_ok=True
        with self.assertRaises(ValueError):
            self.host.queue_decision(self.scope,**{
                **request,"payload":{**GRADE,"contrast":float("nan")}})
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"unapproved_grade")
        queued=self.host.queue_decision(self.scope,**request)
        self.host_ok=False
        with self.assertRaises(PermissionError):
            self.host.run_next()
        self.assertEqual(
            self.ledger.get_task(queued["task_id"])["state"],"QUEUED")
        read=NativeAiReadHost(self.studio,authorize_read=lambda *_:True)
        self.assertNotIn(
            "nvp.film.author_data_decision.v1",
            [c["id"] for c in read.catalog()["capabilities"]])

    def test_new_editorial_camera_sequence_denies_stale_source(self):
        pending=self.host.queue_decision(
            self.scope,**self._request("camera_sequence","new_cuts"))
        self.scenes.publish(
            self.pid,"world",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,2,-5]},
            ],curves=[],expected_revision=1)
        with self.assertRaises(PermissionError):
            self.host.run_next()
        self.assertEqual(
            self.ledger.get_task(pending["task_id"])["state"],"INTERRUPTED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"new_cuts")


if __name__=="__main__":
    unittest.main()
