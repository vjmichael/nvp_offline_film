"""USD-02D real OpenUSD camera, lighting and skeletal animation acceptance."""
import tempfile
import unittest
from pathlib import Path

from pxr import Usd, UsdGeom, UsdLux, UsdSkel

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_presentation import OpenUSDPresentationPlanner

T=TICKS_PER_SECOND


class NativeUsd02D(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/"film.sqlite")
        self.pid=self.studio.create_project("Native USD Film World","")["id"]
        self.film=FilmIndex(self.studio)
        self.scenes=OpenUSDSceneBridge(self.film)
        self.events=TemporalLedger(self.film)
        self.state=OpenUSDTimeState(self.film)
        self.capture=OpenUSDTakeCapture(
            self.film,verify_creator_action=lambda action,scope:
            action=="director_accepts" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,1,-5]},
            {"path":"/World/Light","role":"light","position":[3,4,0]},
        ]
        self.channels=[
            {"path":"/World/Actor","property":"face.smile",
             "samples":[{"tick":0,"value":0.0},
                        {"tick":2*T,"value":1.0}]},
            {"path":"/World/Camera","property":"camera.focal_length_mm",
             "samples":[{"tick":0,"value":35.0},
                        {"tick":2*T,"value":85.0}]},
            {"path":"/World/Camera","property":"camera.focus_distance_m",
             "samples":[{"tick":0,"value":2.0},
                        {"tick":2*T,"value":8.0}]},
            {"path":"/World/Light","property":"light.intensity",
             "samples":[{"tick":0,"value":100.0},
                        {"tick":2*T,"value":300.0}]},
            {"path":"/World/Light","property":"light.temperature_kelvin",
             "samples":[{"tick":0,"value":3000.0},
                        {"tick":2*T,"value":5000.0}]},
        ]
        self.rig=[
            {"path":"/World/Actor","joints":["Root","Root/Hand"],
             "samples":[
                 {"tick":0,"translations":[[0,0,0],[0,0,0]]},
                 {"tick":2*T,"translations":[[0,0,0],[2,0,0]]},
             ]},
        ]
        self.scenes.publish(
            self.pid,"real_scene",prims=self.prims,curves=[],
            performance_channels=self.channels,native_schemas=True,
            skeletal_rigs=self.rig)
        self.film.register_revision(
            self.pid,"acting_source","performance",
            {"format":"nvp.unit.actor.v1","actor":"Actor"},expected_revision=0)
        self.events.publish(self.pid,"action_timeline",[{
            "event_id":"raise_hand","event_kind":"gesture",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"acting_source","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor","action":"raise_hand"}
        }],duration_tick=3*T)

    def test_real_native_usd_camera_light_and_units(self):
        record,stage=self.scenes.open(self.pid,"real_scene",1)
        self.assertEqual(record["data"]["native_schema_version"],
                         "nvp.usd.camera_sphere_light.v1")
        self.assertEqual(record["data"]["layer_order"],
                         ["skeletons","parameters","motion","layout"])
        self.assertAlmostEqual(float(stage.GetTimeCodesPerSecond()),float(T))
        for layer in stage.GetLayerStack():
            if "parameters" in layer.identifier or "skeletons" in layer.identifier:
                self.assertAlmostEqual(float(layer.timeCodesPerSecond),float(T))
        self.assertTrue(stage.GetPrimAtPath("/World/Camera").IsA(UsdGeom.Camera))
        self.assertTrue(stage.GetPrimAtPath("/World/Light").IsA(UsdLux.SphereLight))
        self.assertTrue(stage.GetPrimAtPath(
            "/World/Actor/Rig/Skeleton").IsA(UsdSkel.Skeleton))
        self.assertAlmostEqual(UsdGeom.GetStageMetersPerUnit(stage),1.0)
        cam=UsdGeom.Camera(stage.GetPrimAtPath("/World/Camera"))
        # At metersPerUnit=1, 35mm focal is 0.35 native camera units.
        self.assertAlmostEqual(float(cam.GetFocalLengthAttr().Get(
            Usd.TimeCode(0))),0.35,places=4)
        snap=self.state.evaluate(
            self.pid,"real_scene",1,"action_timeline",1,tick=T)
        properties={r["schema"]:r for r in snap["native_scene_schemas"]}
        self.assertAlmostEqual(
            properties["UsdGeom.Camera"]["focal_length_mm"],60.0,places=3)
        self.assertAlmostEqual(
            properties["UsdGeom.Camera"]["focus_distance_m"],5.0,places=3)
        self.assertAlmostEqual(
            properties["UsdLux.SphereLight"]["intensity"],200.0,places=3)
        self.assertAlmostEqual(
            properties["UsdLux.SphereLight"]["temperature_kelvin"],
            4000.0,places=2)
        self.assertTrue(
            properties["UsdLux.SphereLight"]["temperature_enabled"])
        self.assertFalse(snap["rendered_frames"])

    def test_camera_motion_does_not_replace_native_camera_type(self):
        motion=[{"path":"/World/Camera","samples":[
            {"tick":0,"position":[0,1,-5]},
            {"tick":2*T,"position":[2,1,-5]}]}]
        self.scenes.publish(
            self.pid,"camera_move_scene",prims=self.prims,curves=motion,
            performance_channels=self.channels,native_schemas=True,
            skeletal_rigs=self.rig)
        _,stage=self.scenes.open(self.pid,"camera_move_scene",1)
        self.assertTrue(stage.GetPrimAtPath(
            "/World/Camera").IsA(UsdGeom.Camera))
        mid=self.scenes.evaluate(
            self.pid,"camera_move_scene",1,path="/World/Camera",tick=T)
        self.assertAlmostEqual(mid["world_translation"][0],1.0,places=4)
        self.assertAlmostEqual(
            float(UsdGeom.Camera(stage.GetPrimAtPath(
                "/World/Camera")).GetFocalLengthAttr().Get(Usd.TimeCode(float(T)))),
            0.6,places=4)

    def test_native_skeleton_joint_motion_is_time_sampled(self):
        half=self.state.evaluate(
            self.pid,"real_scene",1,"action_timeline",1,tick=T)
        skeleton=half["skeletal_pose"][0]
        self.assertEqual(skeleton["joint_count"],2)
        positions={j["joint"]:j["skeleton_translation"]
                   for j in skeleton["joints"]}
        self.assertAlmostEqual(positions["Root/Hand"][0],1.0,places=4)
        self.assertFalse(skeleton["mesh_deformation_rendered"])
        reread=OpenUSDTimeState(FilmIndex(Studio(self.studio.db_path)))
        self.assertEqual(
            reread.evaluate(self.pid,"real_scene",1,"action_timeline",1,
                            tick=T)["snapshot_sha256"],
            half["snapshot_sha256"])

    def test_frozen_take_and_two_presentations_preserve_schema_motion(self):
        self.capture.freeze(
            self.pid,"take_real_usd",scene_id="real_scene",scene_revision=1,
            timeline_id="action_timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="director_accepts")
        taken=self.film.read_revision(self.pid,"take_real_usd",1)
        self.assertIsNotNone(taken["data"]["skeleton_layer_sha256"])
        self.assertIsNotNone(taken["data"]["parameter_layer_sha256"])
        self.assertEqual(self.capture.verify_take(
            self.pid,"take_real_usd")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.film.register_revision(
            self.pid,"style_real","style",
            {"format":"nvp.style.v1","profile":"realistic"},expected_revision=0)
        self.film.register_revision(
            self.pid,"style_animated","style",
            {"format":"nvp.style.v1","profile":"stylized"},expected_revision=0)
        planner=OpenUSDPresentationPlanner(self.film)
        common=dict(project_id=self.pid,take_id="take_real_usd",
                    start_tick=T,end_tick=2*T)
        a=planner.prepare(**common,style_id="style_real",style_revision=1,
                          fps_num=24,fps_den=1)
        b=planner.prepare(**common,style_id="style_animated",style_revision=1,
                          fps_num=60,fps_den=1)
        self.assertEqual(len(a["presentation_samples"]),24)
        self.assertEqual(len(b["presentation_samples"]),60)
        self.assertEqual(a["frozen_take_document_sha256"],
                         b["frozen_take_document_sha256"])
        self.assertEqual(a["presentation_samples"][0]["skeletal_pose"],
                         b["presentation_samples"][0]["skeletal_pose"])
        self.assertEqual(a["presentation_samples"][0]["native_scene_schemas"],
                         b["presentation_samples"][0]["native_scene_schemas"])
        self.assertFalse(a["frames_rendered"])
        self.assertFalse(b["frames_rendered"])

    def test_new_revision_keeps_old_take_unchanged(self):
        self.capture.freeze(
            self.pid,"take_previous",scene_id="real_scene",scene_revision=1,
            timeline_id="action_timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="director_accepts")
        revised=[dict(item) for item in self.channels]
        revised[1]=dict(revised[1])
        revised[1]["samples"]=[{"tick":0,"value":20.0},
                               {"tick":2*T,"value":40.0}]
        self.scenes.publish(
            self.pid,"real_scene",prims=self.prims,curves=[],
            performance_channels=revised,native_schemas=True,
            skeletal_rigs=self.rig,expected_revision=1)
        self.assertNotEqual(
            self.film.read_revision(self.pid,"real_scene",1)["document_sha256"],
            self.film.read_revision(self.pid,"real_scene",2)["document_sha256"])
        self.assertEqual(self.capture.verify_take(
            self.pid,"take_previous")["status"],"VERIFIED_FROZEN_DATA_TAKE")

    def test_invalid_rig_topology_and_non_actor_rig_refused(self):
        from backend.nvp_openusd_skeleton import validate_rigs
        with self.assertRaises(ValueError):
            validate_rigs({"role_camera":"camera"},[{
                "path":"role_camera","joints":["Root"],
                "samples":[{"tick":0,"translations":[[0,0,0]]},
                           {"tick":T,"translations":[[0,0,0]]}],
            }])
        with self.assertRaises(ValueError):
            validate_rigs({"/World/Actor":"actor"},[{
                "path":"/World/Actor","joints":["Root/Hand","Root"],
                "samples":[{"tick":0,"translations":[[0,0,0],[0,0,0]]},
                           {"tick":T,"translations":[[0,0,0],[0,0,0]]}],
            }])


if __name__=="__main__":
    unittest.main()
