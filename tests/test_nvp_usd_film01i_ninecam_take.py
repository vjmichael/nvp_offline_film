"""USD-FILM-01I true pxr source: one performing 30s scene, nine native cameras.

The fixture creates ORIGINAL FilmIndex assets, an actor scene/Take and world
Take; it does not fake Blender/Cycles pixels or label them a completed movie.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pxr import Usd, UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_story_bible import StoryBible
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND as T
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01d_shot_working_set import FilmWorldShotPlanner
from backend.nvp_usd_film01e_world_take import OpenUSDWorldTakeCapture
from backend.nvp_usd_film01i_ninecam_take import (
    OriginalNineCameraFilmSet,OriginalFilmPerformanceSampler,GRID)

class NineCameraOriginalFilmSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix="nvp-usd-film01i-nine-")
        cls.root=Path(cls.tmp.name).resolve()
        cls.db=cls.root/"film.sqlite3"
        cls.studio=Studio(cls.db)
        cls.pid=cls.studio.create_project(
            "Nine camera original filmmaking source",
            "One actor performance; three angles times three framings")["id"]
        cls.index=FilmIndex(cls.studio)
        assets=OpenUSDAssetRegistry(cls.index)
        from backend.nvp_film01_donut_actor import original_donut_mesh
        mesh=original_donut_mesh(
            major_radius=0.95,minor_radius=0.32,
            major_segments=36,minor_segments=14)
        source_assets=(
            ("Donut","mesh",1.4,[0.72,0.53,0.33],mesh),
            ("Box","cube",0.8,[0.15,0.76,0.30],None),
            ("Sphere","sphere",0.6,[0.25,0.42,0.95],None),
            ("Craft","cube",1.0,[0.83,0.62,0.22],None),
        )
        bindings=[]
        for name,shape,size,color,geometry in source_assets:
            extras = ({
                "points":geometry["mesh_points"],
                "triangles":geometry["mesh_triangles"],
                "face_uvs":geometry["mesh_face_uvs"]
            } if geometry else {})
            assets.publish(cls.pid,name,shape=shape,size_m=size,
                preview_material={"base_color_rgb":color,
                                  "roughness":0.37,"metallic":0.15},**extras)
            bindings.append({"path":"/World/"+name,"asset_id":name,
                             "asset_revision":1})
        poses=[
            {"path":"/World/Donut","role":"actor","position":[0,-1,0]},
            {"path":"/World/Box","role":"actor","position":[-2,-1,-2.2]},
            {"path":"/World/Sphere","role":"actor","position":[0,-1,-4]},
            {"path":"/World/Craft","role":"actor","position":[-6,0,0]},
            {"path":"/World/Light","role":"light","position":[2,3,5]},
        ]
        curves=[
            {"path":"/World/Donut","samples":[
                {"tick":0,"position":[0,-1,0]},
                {"tick":30*T,"position":[0.2,-1,0]}]},
            {"path":"/World/Box","samples":[
                {"tick":0,"position":[-2,-1,-2.2]},
                {"tick":15*T,"position":[0,-1,-2.2]},
                {"tick":30*T,"position":[3,-1,-2.2]}]},
            {"path":"/World/Sphere","samples":[
                {"tick":0,"position":[0,-1,-4]},
                {"tick":15*T,"position":[0,-1,0]},
                {"tick":30*T,"position":[0,-1,2.2]}]},
            {"path":"/World/Craft","samples":[
                {"tick":0,"position":[-6,0,0]},
                {"tick":30*T,"position":[-2,0,0]}]},
        ]
        specs=[]
        centers=(
            ("A",[0,-1,12],[0,0,0]),
            ("B",[6,-1,11],[0,28,0]),
            ("C",[-6,-1,11],[0,-28,0]),
        )
        lens={"wide":24,"medium":50,"close":85}
        cls.camera_paths={}
        for angle,center,direction in centers:
            for framing in ("wide","medium","close"):
                key=(angle,framing)
                path=f"/World/Cameras/Cam_{angle}_{framing}"
                cls.camera_paths[key]=path
                offset={"wide":-0.2,"medium":0,"close":0.2}[framing]
                poses.append({
                    "path":path,"role":"camera",
                    "position":[center[0],center[1]+offset,center[2]]})
                specs.append({
                    "path":path,"rotation_euler_deg":direction,
                    "focal_length_mm":lens[framing],
                    "focus_distance_m":11.0})
        cls.scene=OpenUSDSceneBridge(cls.index).publish(
            cls.pid,"NineCameraOriginalScene",prims=poses,
            curves=curves,native_schemas=True,asset_bindings=bindings,
            native_camera_specs=specs)
        scene_record,stage=OpenUSDSceneBridge(cls.index).open(
            cls.pid,"NineCameraOriginalScene",1)
        cls.assertTrueStatic(len(scene_record["data"]["native_camera_settings"])==9)
        for angle,framing in GRID:
            path=cls.camera_paths[(angle,framing)]
            if not stage.GetPrimAtPath(path).IsA(UsdGeom.Camera):
                raise RuntimeError("Nine native original camera prims not authored")
        cls.timeline=TemporalLedger(cls.index).publish(
            cls.pid,"OneThirtySecondTimeline",[
                {"event_id":"OriginalObjectActorsMove","event_kind":"action",
                 "subject_id":"Donut","start_tick":0,
                 "end_tick":30*T,
                 "source_id":"NineCameraOriginalScene","source_revision":1,
                 "payload":{"usd_prim_path":"/World/Donut"}},
                {"event_id":"NineCamerasRecordOriginalEvent","event_kind":"camera",
                 "subject_id":"NineCameraDirector","start_tick":0,
                 "end_tick":30*T,
                 "source_id":"NineCameraOriginalScene","source_revision":1,
                 "payload":{"original_multicam_source":True}},
            ],duration_tick=30*T)
        cls.scene_take=OpenUSDTakeCapture(cls.index,
            verify_creator_action=lambda event,scope:
                event=="AUTHORIZE_NINECAM_TEST" and
                scope["operation"]=="nvp.freeze.usd_temporal_take.v1").freeze(
                    cls.pid,"OneThirtySecondSourceTake",
                    scene_id="NineCameraOriginalScene",scene_revision=1,
                    timeline_id="OneThirtySecondTimeline",timeline_revision=1,
                    sample_ticks=[0,10*T,20*T,29*T],
                    creator_event="AUTHORIZE_NINECAM_TEST")
        bible=StoryBible(cls.studio)
        actors=ProductionBibleActors(cls.studio)
        cls.actor_ids={}
        for name in ("Donut","Box","Sphere","Craft"):
            actor=bible.create_entity(cls.pid,"character","Original "+name)
            aid=actor["id"]
            cls.actor_ids[name]=aid
            actors.link(cls.pid,aid,role="actor_prim",
                source_family="filmindex",
                target_id="OneThirtySecondSourceTake",
                target_revision=1,actor_prim_path="/World/"+name,
                expected_actor_revision=actors.actor(cls.pid,aid)["bible_revision"],
                director_note="One continuous 30s original object-actor performance")
        if len(actors.require_complete_cast(
                cls.pid,"OneThirtySecondSourceTake")["actor_id_by_prim"])!=4:
            raise RuntimeError("Original native cast incomplete")
        cls.world=OpenUSDWorldComposer(cls.index).publish(
            cls.pid,"OneContinuousNineCamWorld",
            sets=[{"name":"Stage","scene_id":"NineCameraOriginalScene",
                   "scene_revision":1}],
            props=[],variants=[],instancers=[])
        planner=FilmWorldShotPlanner(cls.index)
        cls.camera_shots=[]
        for angle,framing in GRID:
            shot_id=f"OriginalCam_{angle}_{framing}"
            planner.publish(
                cls.pid,shot_id,world_id="OneContinuousNineCamWorld",
                world_revision=1,camera_set="Stage",
                camera_prim=cls.camera_paths[(angle,framing)],
                sample_ticks=[0,10*T,20*T,29*T],
                required_sets=["Stage"],max_loaded_sets=1)
            cls.camera_shots.append({
                "angle":angle,"framing":framing,
                "shot_id":shot_id,"shot_revision":1})
        cls.world_take=OpenUSDWorldTakeCapture(cls.index,
            verify_creator_action=lambda event,scope:
                event=="AUTHORIZE_NINECAM_TEST" and
                scope["operation"]=="nvp.freeze.usd_film01e_world_take.v1").freeze(
                    cls.pid,"OneThirtySecondWorldTake",
                    world_id="OneContinuousNineCamWorld",
                    world_revision=1,shot_id="OriginalCam_A_wide",
                    shot_revision=1,scene_takes=[{
                        "set":"Stage","take_id":"OneThirtySecondSourceTake",
                        "take_sha256":cls.scene_take["document_sha256"]}],
                    creator_event="AUTHORIZE_NINECAM_TEST")
        cls.registry=OriginalNineCameraFilmSet(cls.index,
            verify_creator_action=lambda event,scope:
                event=="AUTHORIZE_NINECAM_TEST" and
                scope["operation"]==
                    "nvp.capture.usd_film01i_nine_original_cameras.v1" and
                len(scope["camera_shot_shas"])==9)
        cls.rig=cls.registry.publish(
            cls.pid,"OnePerformanceNineCamBank",
            world_take_id="OneThirtySecondWorldTake",
            camera_shots=cls.camera_shots,
            creator_event="AUTHORIZE_NINECAM_TEST")

    @staticmethod
    def assertTrueStatic(value):
        if not value:
            raise AssertionError("Native camera setting count mismatch")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_original_nine_cam_lenses_and_angles_survive_native_usd_reopen(self):
        report=self.registry.verify(self.pid,"OnePerformanceNineCamBank")
        self.assertEqual(report["camera_count"],9)
        data=self.index.read_revision(
            self.pid,"OnePerformanceNineCamBank",1)["data"]
        self.assertEqual(len(data["cameras"]),9)
        self.assertEqual(data["full_camera_coverage_frames"],6480)
        self.assertEqual([x["focal_length_mm"] for x in data["cameras"][:3]],
                         [24.0,50.0,85.0])
        self.assertEqual(
            len({tuple(x["rotation_euler_deg"]) for x in data["cameras"]}),3)
        self.assertEqual(
            data["source_scene_take_sha256"],self.scene_take["document_sha256"])
        self.assertFalse(data["native_render_frames_produced"])
        self.assertFalse(data["film_master_created"])

    def test_one_shared_actor_performance_at_all_camera_cut_boundaries(self):
        with OriginalFilmPerformanceSampler(
                self.index,self.pid,"OnePerformanceNineCamBank") as sampler:
            hashes=[]
            for i in (0,239,240,479,480,719):
                observed=sampler.frame(i)
                self.assertEqual(observed["frame"],i)
                self.assertEqual(len(
                    observed["nine_synchronized_original_camera_views"]),9)
                self.assertEqual(len({c["original_actor_state_sha256"] for c in
                    observed["nine_synchronized_original_camera_views"]}),1)
                self.assertEqual(observed["source_actor_count"],4)
                hashes.append(observed["source_actor_state_sha256"])
            self.assertGreater(len(set(hashes)),3)
        self.assertEqual(
            self.index.read_revision(
                self.pid,"OneThirtySecondSourceTake",1)["document_sha256"],
            self.scene_take["document_sha256"])

    def test_genuine_original_720_frame_blender_animation_stage(self):
        from backend.nvp_usd_film01k_blender_animation_build import (
            author_original_blender_animation,STAGE)
        from pxr import Usd
        output=self.root/"derived_720_frame_nine_original_cameras"
        proof=author_original_blender_animation(
            self.index,self.pid,"OnePerformanceNineCamBank",folder=output)
        self.assertEqual(proof["source_camera_count"],9)
        self.assertEqual(proof["original_frame_count_per_camera"],720)
        self.assertEqual(len(proof["original_actor_state_per_frame"]),720)
        self.assertEqual(len(proof["native_actor_reopen_checkpoints"]),7)
        self.assertGreater(proof["original_native_animated_attributes_resampled"],0)
        self.assertTrue(proof["original_film_source_unchanged"])
        self.assertFalse(proof["renderer_frames_created"])
        stage=Usd.Stage.Open(str(output/STAGE))
        self.assertEqual(stage.GetFramesPerSecond(),24.0)
        self.assertEqual(stage.GetStartTimeCode(),1.)
        self.assertEqual(stage.GetEndTimeCode(),720.)

    def test_native_camera_rejects_nonphysical_focal_length(self):
        camera="/World/TestCamera"
        with self.assertRaises(ValueError):
            OpenUSDSceneBridge(self.index).publish(
                self.pid,"InvalidForeignCameraLens",
                prims=[{"path":camera,"role":"camera","position":[0,0,9]}],
                curves=[],native_schemas=True,
                native_camera_specs=[{"path":camera,
                    "rotation_euler_deg":[0,0,0],
                    "focal_length_mm":0,
                    "focus_distance_m":9}])

    def test_camera_swap_and_wrong_scene_are_not_new_source_performances(self):
        forged=deepcopy(self.camera_shots)
        forged[1]["shot_id"]=forged[0]["shot_id"]
        with self.assertRaises((ValueError,PermissionError)):
            self.registry._prepare(
                self.pid,"OneThirtySecondWorldTake",forged)
        forged=deepcopy(self.camera_shots)
        forged[1]["framing"]="wide"
        with self.assertRaises(ValueError):
            self.registry._prepare(
                self.pid,"OneThirtySecondWorldTake",forged)

    def test_original_source_reopens_from_sqlite_and_sha_ledger(self):
        reopened=FilmIndex(Studio(self.db))
        report=OriginalNineCameraFilmSet(
            reopened,verify_creator_action=lambda *_:False).verify(
                self.pid,"OnePerformanceNineCamBank")
        self.assertEqual(report["rig_sha256"],self.rig["document_sha256"])
        with OriginalFilmPerformanceSampler(
                reopened,self.pid,"OnePerformanceNineCamBank") as original:
            state=original.frame(719)
            self.assertEqual(state["original_film_tick"],719*T//24)

if __name__=="__main__":
    unittest.main()
