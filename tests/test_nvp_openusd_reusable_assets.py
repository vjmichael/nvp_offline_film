"""USD-02: native reusable USD assets and time-addressable scene evaluation.

Real pxr/Usd reference arcs are required; no mocked scene graph permitted.
"""
import tempfile
import unittest
from pathlib import Path

from pxr import Usd, UsdGeom
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_time_state import OpenUSDTimeState

T = TICKS_PER_SECOND


class NativeUSD02Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "studio.sqlite"
        self.studio = Studio(self.db)
        self.pid = self.studio.create_project(
            "NVP USD reusable actors", "Frozen performances")["id"]
        self.index = FilmIndex(self.studio)
        self.assets = OpenUSDAssetRegistry(self.index)
        self.scene = OpenUSDSceneBridge(self.index)
        self.ledger = TemporalLedger(self.index)
        self.state = OpenUSDTimeState(self.index)
        self.takes = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda event, scope:
            event == "director_confirms" and
            scope.get("operation") == "nvp.freeze.usd_temporal_take.v1")
        self.assets.publish(self.pid, "body_geometry",
                            shape="cube", size_m=2)
        self.assets.publish(self.pid, "face_geometry",
                            shape="sphere", size_m=1)
        self.prims = [
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/PropA","role":"prop","position":[3,0,0]},
            {"path":"/World/PropB","role":"prop","position":[6,0,0]},
        ]
        self.curves = [{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":2*T,"position":[10,0,0]},
        ]}]
        self.bindings = [
            {"path":"/World/Actor","asset_id":"body_geometry","asset_revision":1},
            {"path":"/World/PropA","asset_id":"face_geometry","asset_revision":1},
            {"path":"/World/PropB","asset_id":"face_geometry","asset_revision":1},
        ]
        self.scene.publish(self.pid,"scene_reusable",prims=self.prims,
                           curves=self.curves,asset_bindings=self.bindings)
        self.index.register_revision(
            self.pid,"performance_authority","performance",
            {"format":"nvp.test.performance","actor":"Actor"},expected_revision=0)
        self.ledger.publish(self.pid,"event_timeline",[{
            "event_id":"actor_walks","event_kind":"action",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"performance_authority","source_revision":1,
            "payload":{"verb":"walk","usd_prim_path":"/World/Actor"}
        }],duration_tick=3*T)

    def test_two_instances_of_one_asset_compose_from_original_source(self):
        original,stage = self.scene.open(self.pid,"scene_reusable",1)
        self.assertEqual(len(original["data"]["asset_bindings"]),3)
        for path in ("/World/PropA/Geometry","/World/PropB/Geometry"):
            self.assertTrue(stage.GetPrimAtPath(path).IsDefined())
            self.assertTrue(stage.GetPrimAtPath(path).IsA(UsdGeom.Sphere))
        self.assertTrue(stage.GetPrimAtPath(
            "/World/Actor/Geometry").IsA(UsdGeom.Cube))
        self.assertEqual(
            self.index.direct_dependents(self.pid,"face_geometry",1),
            [{"object_id":"scene_reusable","revision":1}])

    def test_state_at_one_second_is_data_and_reopens_after_restart(self):
        result = self.state.evaluate(
            self.pid,"scene_reusable",1,"event_timeline",1,tick=T)
        actor = next(x for x in result["objects"]
                     if x["path"]=="/World/Actor")
        self.assertAlmostEqual(actor["world_translation"][0],5,places=5)
        self.assertEqual(actor["semantic_role"],"actor")
        self.assertEqual(len(actor["world_matrix"]),4)
        self.assertEqual(
            [x["event_id"] for x in result["active_events"]],
            ["actor_walks"])
        self.assertFalse(result["rendered_frames"])
        other=OpenUSDTimeState(FilmIndex(Studio(self.db)))
        rebuilt=other.evaluate(
            self.pid,"scene_reusable",1,"event_timeline",1,tick=T)
        self.assertEqual(rebuilt["snapshot_sha256"],result["snapshot_sha256"])

    def test_frozen_take_pins_assets_when_new_revision_is_published(self):
        freeze=self.takes.freeze(
            self.pid,"immutable_take",scene_id="scene_reusable",
            scene_revision=1,timeline_id="event_timeline",
            timeline_revision=1,sample_ticks=[0,T,2*T],
            creator_event="director_confirms")
        take=self.index.read_revision(self.pid,"immutable_take",1)
        self.assertEqual(len(take["data"]["asset_bindings"]),3)
        self.assertEqual(self.takes.verify_take(
            self.pid,"immutable_take")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assets.publish(self.pid,"face_geometry",
                            shape="sphere",size_m=4,expected_revision=1)
        newer = [dict(x) for x in self.bindings]
        for item in newer:
            if item["asset_id"]=="face_geometry":
                item["asset_revision"]=2
        self.scene.publish(self.pid,"scene_reusable",prims=self.prims,
                           curves=self.curves,asset_bindings=newer,
                           expected_revision=1)
        self.assertNotEqual(
            self.scene.open(self.pid,"scene_reusable",1)[0]["document_sha256"],
            self.scene.open(self.pid,"scene_reusable",2)[0]["document_sha256"])
        self.assertEqual(self.takes.verify_take(
            self.pid,"immutable_take")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        # Still references frozen original radius, not the newer geometry.
        _,old_stage=self.scene.open(self.pid,"scene_reusable",1)
        _,new_stage=self.scene.open(self.pid,"scene_reusable",2)
        old=UsdGeom.Sphere(old_stage.GetPrimAtPath(
            "/World/PropA/Geometry")).GetRadiusAttr().Get()
        new=UsdGeom.Sphere(new_stage.GetPrimAtPath(
            "/World/PropA/Geometry")).GetRadiusAttr().Get()
        self.assertAlmostEqual(old,0.5)
        self.assertAlmostEqual(new,2.0)

    def test_bad_asset_scope_and_invalid_event_scene_targets_rejected(self):
        stranger=self.studio.create_project("Separate film","")["id"]
        with self.assertRaises(KeyError):
            self.assets.open(stranger,"face_geometry",1)
        with self.assertRaises(ValueError):
            self.scene.publish(
                self.pid,"bad_external",prims=self.prims,curves=[],
                asset_bindings=[{"path":"/World/Actor",
                                 "asset_id":"body_geometry","asset_revision":1,
                                 "file_path":"/tmp/untrusted.usda"}])
        with self.assertRaises(ValueError):
            self.scene.publish(
                self.pid,"duplicate_binding",prims=self.prims,curves=[],
                asset_bindings=[self.bindings[0],self.bindings[0]])
        with self.assertRaises(PermissionError):
            self.takes.freeze(
                self.pid,"no_permission_take",scene_id="scene_reusable",
                scene_revision=1,timeline_id="event_timeline",
                timeline_revision=1,sample_ticks=[0,T],
                creator_event="model_invented_approval")
        self.ledger.publish(self.pid,"bad_event_timeline",[{
            "event_id":"target_missing","event_kind":"action",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"performance_authority","source_revision":1,
            "payload":{"usd_prim_path":"/World/NotInScene"}
        }],duration_tick=3*T)
        with self.assertRaises(RuntimeError):
            self.state.evaluate(
                self.pid,"scene_reusable",1,"bad_event_timeline",1,tick=T)


if __name__ == "__main__":
    unittest.main()
