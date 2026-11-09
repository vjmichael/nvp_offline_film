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
            ("Wall","cube",1.0,[0.55,0.55,0.55],None),
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
            {"path":"/World/Wall","role":"prop","position":[0,-1,0]},
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

    def test_real_nine_camera_cycles_three_film_times(self):
        import os
        import shutil
        import subprocess
        from PIL import Image
        from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
        from backend.nvp_usd_film01l_blender_smoke_host import (
            ReviewedNineCameraCyclesSmoke)
        executable=os.environ.get("NVP_FILM01L_BLENDER_BIN")
        if not executable:
            self.skipTest("Actual Blender 5.2 required for nine native camera smoke")
        binary=Path(executable).resolve(strict=True)
        version=subprocess.run(
            [str(binary),"-b","--version"],capture_output=True,
            text=True,check=True,timeout=30).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        workers=self.root/"native_nine_camera_supervised"
        supervisor=BlenderWorkerSupervisor(workers,
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version=version)
        host=ReviewedNineCameraCyclesSmoke(
            self.index,supervisor,
            verify_director_action=lambda event,scope:
                event=="APPROVE_NINE_REAL_CAMERA_SMOKE" and
                scope["operation"]==
                    "nvp.render.usd_film01l_ninecam_native_smoke.v1" and
                len(scope["native_camera_shas"])==9)
        result=host.render_smoke(
            self.pid,"OnePerformanceNineCamBank",
            job_prefix="realNineCam",
            director_event="APPROVE_NINE_REAL_CAMERA_SMOKE")
        self.assertEqual(result["rendered_original_cycles_frames"],27)
        self.assertEqual(result["independently_supervised_job_count"],3)
        self.assertFalse(result["all_6480_source_camera_frames_produced"])
        artifact=Path(os.environ.get(
            "NVP_FILM01L_ARTIFACT_DIR",
            str(self.root/"native_nine_camera_images"))).resolve()
        artifact.mkdir(parents=True,exist_ok=True)
        hashes=set()
        for item in result["jobs"]:
            folder=item["job_dir"]
            audit=json.loads((folder/"audit.json").read_text("utf8"))
            self.assertEqual(audit["actual_native_cycles_image_count"],9)
            for row in audit["camera_views"]:
                file=folder/row["rendered_png_file"]
                self.assertEqual(row["rendered_png_sha256"],sha_file(file))
                with Image.open(file) as img:
                    self.assertEqual(img.size,(320,180))
                    img.verify()
                hashes.add(sha_file(file))
                shutil.copyfile(file,artifact/(
                    f"{item['source_frame']:04d}_"+
                    row["rendered_png_file"]))
            for filename in ("scene.blend","audit.json","source.json",
                             "source.usda"):
                shutil.copyfile(folder/filename,artifact/(
                    f"{item['source_frame']:04d}_"+filename))
        self.assertGreaterEqual(len(hashes),9)
        (artifact/"27_native_camera_smoke_summary.json").write_text(
            json.dumps({"source_rig_sha256":result["original_rig_sha256"],
                "same_original_world_take_sha256":
                    result["original_world_take_sha256"],
                "native_supervised_frames":27,
                "independent_native_worker_jobs":3,
                "distinct_rendered_png_shas":len(hashes),
                "complete_nine_roll_movie_produced":False,
                "director_approved":False},indent=2,sort_keys=True),"utf8")

    def test_director_add_remove_reverse_ots_drone_and_inside_wall_camera(self):
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        from pxr import Usd, UsdGeom
        from dataclasses import dataclass
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda event,scope:
                event=="AUTHORIZE_DIRECTOR_CAMERA_EDIT" and
                scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        def new_camera(camera_id,framing,xyz,rotation,lens,*,excludes=None,move=None):
            return {
                "camera_id":camera_id,"setup":"Director virtual scene",
                "framing":framing,"position_m":xyz,
                "rotation_euler_deg":rotation,"focal_length_mm":lens,
                "focus_distance_m":10.0,
                "clip_range_m":[0.001,10000],
                "move_keys":move or [],
                "camera_ray_exclusions":excludes or []}
        original_wide=new_camera(
            "WideFront","wide",[0,-1,12],[0,0,0],24)
        bank.create(self.pid,"DirectorFlexibleBank",
            world_take_id="OneThirtySecondWorldTake",
            cameras=[original_wide],
            director_event="AUTHORIZE_DIRECTOR_CAMERA_EDIT")
        wall="/World/Sets/Stage/Wall"
        extra=[
            new_camera("Reverse","reverse",[-3,-1,-9],[0,180,0],42),
            new_camera("OverShoulder","over shoulder",[2,-2,4],[0,18,0],70),
            new_camera("LowAngle","bottom up",[0,-1,0],[18,0,0],32,
                excludes=[wall]),
            new_camera("Aerial","drone",[-4,5,17],[-30,-10,0],28,
                move=[{"tick":0,"position_m":[-4,5,17],
                       "rotation_euler_deg":[-30,-10,0]},
                      {"tick":30*T,"position_m":[4,8,17],
                       "rotation_euler_deg":[-45,10,0]}])]
        stage=bank.revise(self.pid,"DirectorFlexibleBank",
            expected_revision=1,changes=[{"op":"add","camera":x} for x in extra],
            director_event="AUTHORIZE_DIRECTOR_CAMERA_EDIT")
        self.assertEqual(stage["revision"],2)
        original_source=self.index.read_revision(
            self.pid,"OneThirtySecondWorldTake",1)["document_sha256"]
        before=bank.verify(self.pid,"DirectorFlexibleBank",1)
        after=bank.verify(self.pid,"DirectorFlexibleBank",2)
        self.assertEqual(before["camera_count"],1)
        self.assertEqual(after["camera_count"],5)
        self.assertEqual(before["world_take_sha256"],after["world_take_sha256"])
        self.assertFalse(after["director_camera_geometry_rendered"])
        self.assertFalse(after["director_camera_physical_collision"])
        with bank.open_source_views(self.pid,"DirectorFlexibleBank",2) as state:
            self.assertEqual(len(state["camera_paths"]),5)
            self.assertFalse(state["camera_has_physical_collision"])
            self.assertFalse(state["camera_occlusion_masks_applied_globally"])
            stage=state["stage"]
            for path in state["camera_paths"].values():
                self.assertTrue(stage.GetPrimAtPath(path).IsA(UsdGeom.Camera))
            cam=stage.GetPrimAtPath(state["camera_paths"]["LowAngle"])
            self.assertEqual(
                [float(x) for x in UsdGeom.Xformable(cam).
                 ComputeLocalToWorldTransform(Usd.TimeCode(0)).
                 ExtractTranslation()], [0.0,-1.0,0.0])
            wall_prim=stage.GetPrimAtPath(wall)
            self.assertTrue(wall_prim.IsDefined())
            self.assertNotEqual(wall_prim.GetAttribute("visibility").Get(),
                                "invisible")
        result=bank.revise(self.pid,"DirectorFlexibleBank",
            expected_revision=2,
            changes=[{"op":"remove","camera_id":"OverShoulder"}],
            director_event="AUTHORIZE_DIRECTOR_CAMERA_EDIT")
        self.assertEqual(result["revision"],3)
        self.assertEqual(bank.verify(self.pid,"DirectorFlexibleBank",3)[
                         "camera_count"],4)
        self.assertEqual(bank.verify(self.pid,"DirectorFlexibleBank",2)[
                         "camera_count"],5)
        self.assertEqual(self.index.read_revision(self.pid,
            "OneThirtySecondWorldTake",1)["document_sha256"],original_source)
        fresh=DirectorCameraBank(FilmIndex(Studio(self.db)),
            verify_director_action=lambda *_:False)
        self.assertEqual(fresh.verify(self.pid,"DirectorFlexibleBank",3)[
                         "camera_count"],4)

    def test_optional_nine_camera_preset_can_be_dynamically_extended(self):
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        bank=DirectorCameraBank(self.index,
            verify_director_action=lambda event,scope:
                event=="AUTHORIZE_NINECAM_PRESET" and
                scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        bank.create_standard_nine_preset(
            self.pid,"DirectorNinePresetEditable",
            original_nine_rig_id="OnePerformanceNineCamBank",
            director_event="AUTHORIZE_NINECAM_PRESET")
        data=bank.verify(self.pid,"DirectorNinePresetEditable",1)
        self.assertEqual(data["camera_count"],9)
        self.assertEqual(
            {c["framing"] for c in data["cameras"]},
            {"wide","medium","close"})
        self.assertEqual(len({c["camera_id"] for c in data["cameras"]}),9)
        self.assertEqual(
            data["source_performance_sha256"],
            self.index.read_revision(
                self.pid,"OnePerformanceNineCamBank",1)["data"][
                    "source_performance_sha256"])

    def _native_director_wall_pair(self):
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        bank=DirectorCameraBank(self.index,
            verify_director_action=lambda event,scope:
                event=="AUTHORIZE_WALL_SHOT" and
                scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        wall="/World/Sets/Stage/Wall"
        origin={
            "setup":"Wall comparison","framing":"wide",
            "position_m":[0,-1,7],
            "rotation_euler_deg":[0,0,0],
            "focal_length_mm":35.0,"focus_distance_m":7.0,
            "clip_range_m":[0.01,10000],
            "move_keys":[]}
        two=[
            {"camera_id":"WallNormal","camera_ray_exclusions":[],**origin},
            {"camera_id":"WallGhost","camera_ray_exclusions":[wall],**origin}]
        bank.create(self.pid,"TwoWallComparisonCameras",
            world_take_id="OneThirtySecondWorldTake",
            cameras=two,director_event="AUTHORIZE_WALL_SHOT")
        return bank,wall

    def test_native_director_camera_snapshot_keeps_wall_and_performance(self):
        from backend.nvp_usd_film01n_director_camera_snapshot import (
            stage_original_director_camera_frame,STAGE)
        from pxr import Usd,UsdGeom
        bank,wall=self._native_director_wall_pair()
        result=[]
        for camera in ("WallNormal","WallGhost"):
            root=self.root/("source_director_"+camera)
            packet=stage_original_director_camera_frame(
                self.index,self.pid,"TwoWallComparisonCameras",
                revision=1,camera_id=camera,tick=15*T,folder=root)
            scene=Usd.Stage.Open(str(root/STAGE))
            self.assertTrue(scene.GetPrimAtPath(
                "/World/NVPDirectorCameraRig/"+camera).IsA(UsdGeom.Camera))
            self.assertTrue(scene.GetPrimAtPath(wall).IsDefined())
            self.assertEqual(packet["source"]["original_film_tick"],15*T)
            self.assertTrue(packet["source"]["source_world_visibility_not_modified"])
            self.assertEqual(len(packet["source"]["source_actor_positions"]),4)
            result.append(packet["source"])
        self.assertEqual(result[0]["source_performance_sha256"],
                         result[1]["source_performance_sha256"])
        self.assertEqual(result[0]["source_world_take_sha256"],
                         result[1]["source_world_take_sha256"])
        self.assertEqual(result[0]["source_usd_sha256"],
                         result[1]["source_usd_sha256"])
        self.assertEqual(result[1]["source_camera_ray_exclusions"],[wall])

    def test_real_native_cycles_wall_vs_ghost_camera(self):
        import os
        import subprocess
        import shutil
        from PIL import Image
        from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
        from backend.nvp_usd_film01n_director_camera_host import (
            ReviewedDirectorCameraCycles)
        blender=os.environ.get("NVP_FILM01N_BLENDER_BIN")
        if not blender:
            self.skipTest("Official Blender 5.2 binary only in native integration CI")
        binary=Path(blender).resolve(strict=True)
        version=subprocess.run([str(binary),"-b","--version"],
            capture_output=True,text=True,check=True,timeout=30
        ).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        bank,wall=self._native_director_wall_pair()
        worker=BlenderWorkerSupervisor(
            self.root/"native_director_wall_jobs",
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version=version)
        host=ReviewedDirectorCameraCycles(
            self.index,worker,
            verify_director_action=lambda event,scope:
                event=="AUTHORIZE_WALL_RENDER" and
                scope["operation"]==
                    "nvp.render.usd_film01n_director_camera_views.v1" and
                scope["camera_ids"]==["WallNormal","WallGhost"] and
                scope["per_camera_primary_ray_exclusions"]==[[],[wall]])
        result=host.render_views(
            self.pid,"TwoWallComparisonCameras",revision=1,tick=15*T,
            requests=[
                {"camera_id":"WallNormal","job_id":"realWallNormal"},
                {"camera_id":"WallGhost","job_id":"realWallGhost"}],
            director_event="AUTHORIZE_WALL_RENDER")
        self.assertEqual(result["real_cycles_image_count"],2)
        self.assertFalse(result["full_camera_rolls_rendered"])
        self.assertNotEqual(result["camera_views"][0]["png_sha256"],
                            result["camera_views"][1]["png_sha256"])
        destination=Path(os.environ.get(
            "NVP_FILM01N_ARTIFACT_DIR",
            str(self.root/"actual_blender_camera_wall_artifacts"))).resolve()
        destination.mkdir(parents=True,exist_ok=True)
        for row in result["camera_views"]:
            path=row["job_dir"]/"frame.png"
            with Image.open(path) as img:
                self.assertEqual(img.size,(320,180))
                img.verify()
            audit=json.loads((row["job_dir"]/"audit.json").read_text("utf8"))
            self.assertTrue(audit["per_camera_ray_mask_restored"])
            if row["camera_id"]=="WallGhost":
                self.assertGreater(audit["actual_ray_masked_meshes"],0)
            else:
                self.assertEqual(audit["actual_ray_masked_meshes"],0)
            for name in ("frame.png","scene.blend","audit.json","source.usda",
                         "source.json"):
                shutil.copyfile(row["job_dir"]/name,
                    destination/(row["camera_id"]+"_"+name))
        (destination/"wall_comparison.json").write_text(
            json.dumps({
                "original_film_tick":15*T,
                "source_performance_sha256":result["original_performance_sha256"],
                "source_world_take_sha256":result["original_world_take_sha256"],
                "camera_ids":["WallNormal","WallGhost"],
                "native_cycles_views":2,
                "same_actor_performance":True,
                "distinct_rendered_png_sha256":True,
                "director_visual_approval":False,
                "complete_nine_camera_film":False},
                sort_keys=True,indent=2),"utf8")

    def test_camera_ray_masks_cannot_remove_original_actor(self):
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        bank=DirectorCameraBank(self.index,
            verify_director_action=lambda *_:True)
        proposal={
            "camera_id":"UnreviewedXRay","setup":"behind subject",
            "framing":"detail","position_m":[0,-1,0],
            "rotation_euler_deg":[0,0,0],
            "focal_length_mm":50.0,"focus_distance_m":10.0,
            "clip_range_m":[0.01,1000],"move_keys":[],
            "camera_ray_exclusions":["/World/Sets/Stage/Donut"]}
        with self.assertRaises(PermissionError):
            bank.create(self.pid,"InvalidActorHidingBank",
                world_take_id="OneThirtySecondWorldTake",
                cameras=[proposal],director_event="untrusted")

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
