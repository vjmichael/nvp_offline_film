"""USD-02C native tests: time-sampled actor/camera/light data stays frozen."""
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_presentation import OpenUSDPresentationPlanner

T=TICKS_PER_SECOND


class PerformanceChannelNativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/"nvp.sqlite")
        self.pid=self.studio.create_project("USD channels","Time state")["id"]
        self.index=FilmIndex(self.studio)
        self.scene=OpenUSDSceneBridge(self.index)
        self.ledger=TemporalLedger(self.index)
        self.state=OpenUSDTimeState(self.index)
        self.take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda action,scope:
            action=="director_yes" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,1,-5]},
            {"path":"/World/Light","role":"light","position":[2,5,0]},
        ]
        self.channel_inputs=[
            {"path":"/World/Actor","property":"face.smile",
             "samples":[{"tick":0,"value":0.0},{"tick":2*T,"value":1.0}]},
            {"path":"/World/Actor","property":"joint.head_yaw_degrees",
             "samples":[{"tick":0,"value":-30.0},
                        {"tick":2*T,"value":30.0}]},
            {"path":"/World/Camera","property":"camera.focal_length_mm",
             "samples":[{"tick":0,"value":35.0},
                        {"tick":2*T,"value":85.0}]},
            {"path":"/World/Light","property":"light.intensity",
             "samples":[{"tick":0,"value":100.0},
                        {"tick":2*T,"value":300.0}]},
        ]
        self.scene.publish(
            self.pid,"usd_scene",prims=self.prims,curves=[],
            performance_channels=self.channel_inputs)
        self.index.register_revision(
            self.pid,"performance_source","performance",
            {"format":"nvp.test.perf.v1","subject":"Actor"},expected_revision=0)
        self.ledger.publish(self.pid,"timeline",[{
            "event_id":"expression_change","event_kind":"expression",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"performance_source","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor","emotion":"happy"},
        }],duration_tick=3*T)

    def test_composed_attribute_values_at_exact_time(self):
        record,stage=self.scene.open(self.pid,"usd_scene",1)
        self.assertEqual(record["data"]["layer_order"],
                         ["parameters","motion","layout"])
        self.assertEqual(len(record["data"]["performance_channels"]),4)
        for layer in stage.GetLayerStack():
            if "parameters" in layer.identifier:
                self.assertAlmostEqual(float(layer.timeCodesPerSecond),float(T))
        snapshot=self.state.evaluate(
            self.pid,"usd_scene",1,"timeline",1,tick=T)
        values={p["property"]:p["value"]
                for p in snapshot["performance_channels"]}
        self.assertAlmostEqual(values["face.smile"],0.5)
        self.assertAlmostEqual(values["joint.head_yaw_degrees"],0.0)
        self.assertAlmostEqual(values["camera.focal_length_mm"],60.0)
        self.assertAlmostEqual(values["light.intensity"],200.0)
        self.assertEqual([x["event_id"] for x in snapshot["active_events"]],
                         ["expression_change"])
        self.assertFalse(snapshot["rendered_frames"])
        self.assertEqual(
            OpenUSDTimeState(FilmIndex(Studio(self.studio.db_path))).evaluate(
                self.pid,"usd_scene",1,"timeline",1,tick=T)["snapshot_sha256"],
            snapshot["snapshot_sha256"])

    def test_take_freezes_channel_evidence_across_scene_revision(self):
        self.take.freeze(self.pid,"freeze_channels",scene_id="usd_scene",
                         scene_revision=1,timeline_id="timeline",
                         timeline_revision=1,sample_ticks=[0,T,2*T],
                         creator_event="director_yes")
        frozen=self.index.read_revision(self.pid,"freeze_channels",1)
        self.assertEqual(len(frozen["data"]["performance_channels"]),4)
        original_sha=frozen["data"]["parameter_layer_sha256"]
        self.assertEqual(self.take.verify_take(
            self.pid,"freeze_channels")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        changed=[]
        for track in self.channel_inputs:
            item={"path":track["path"],"property":track["property"],
                  "samples":[dict(k) for k in track["samples"]]}
            if item["property"]=="face.smile":
                item["samples"][-1]["value"]=0.0
            changed.append(item)
        self.scene.publish(self.pid,"usd_scene",prims=self.prims,curves=[],
                           performance_channels=changed,expected_revision=1)
        old=self.index.read_revision(self.pid,"usd_scene",1)["data"]
        new=self.index.read_revision(self.pid,"usd_scene",2)["data"]
        self.assertEqual(old["parameter_layer_sha256"],original_sha)
        self.assertNotEqual(new["parameter_layer_sha256"],original_sha)
        self.assertEqual(self.take.verify_take(
            self.pid,"freeze_channels")["status"],"VERIFIED_FROZEN_DATA_TAKE")

    def test_same_frozen_channels_for_24_and_60fps_style_plans(self):
        self.take.freeze(self.pid,"freeze_styles",scene_id="usd_scene",
                         scene_revision=1,timeline_id="timeline",
                         timeline_revision=1,sample_ticks=[0,T,2*T],
                         creator_event="director_yes")
        self.index.register_revision(self.pid,"style_a","style",
                                     {"name":"realism"},expected_revision=0)
        self.index.register_revision(self.pid,"style_b","style",
                                     {"name":"stylized"},expected_revision=0)
        planner=OpenUSDPresentationPlanner(self.index)
        common=dict(project_id=self.pid,take_id="freeze_styles",
                    start_tick=T,end_tick=2*T)
        a=planner.prepare(**common,style_id="style_a",style_revision=1,
                          fps_num=24,fps_den=1)
        b=planner.prepare(**common,style_id="style_b",style_revision=1,
                          fps_num=60,fps_den=1)
        self.assertEqual(len(a["presentation_samples"]),24)
        self.assertEqual(len(b["presentation_samples"]),60)
        self.assertEqual(a["frozen_take_document_sha256"],
                         b["frozen_take_document_sha256"])
        self.assertNotEqual(a["style_document_sha256"],
                            b["style_document_sha256"])
        self.assertEqual(
            a["presentation_samples"][0]["performance_channels"],
            b["presentation_samples"][0]["performance_channels"])
        self.assertFalse(a["frames_rendered"])
        self.assertFalse(b["frames_rendered"])

    def test_wrong_roles_duplicate_keys_and_nonfinite_samples_fail(self):
        bad=[
            {"path":"/World/Light","property":"face.smile",
             "samples":[{"tick":0,"value":0.0},{"tick":T,"value":1.0}]}
        ]
        with self.assertRaises(ValueError):
            self.scene.publish(self.pid,"bad_role",prims=self.prims,curves=[],
                               performance_channels=bad)
        with self.assertRaises(ValueError):
            self.scene.publish(self.pid,"duplicate",prims=self.prims,curves=[],
                               performance_channels=self.channel_inputs[:1]*2)
        oversized=[{"path":"/World/Actor","property":"face.smile",
                    "samples":[{"tick":0,"value":0.0},
                               {"tick":T,"value":float("nan")}]}]
        with self.assertRaises(ValueError):
            self.scene.publish(self.pid,"not_finite",prims=self.prims,curves=[],
                               performance_channels=oversized)

    def test_legacy_two_layer_scenes_remain_openable(self):
        scene=self.scene.publish(self.pid,"old_format",
                                 prims=self.prims,curves=[])
        stored=self.index.read_revision(self.pid,"old_format",1)["data"]
        self.assertEqual(stored["layer_order"],["motion","layout"])
        self.assertEqual(self.scene.open(
            self.pid,"old_format",1)[0]["document_sha256"],
            scene["document_sha256"])


if __name__=="__main__":
    unittest.main()
