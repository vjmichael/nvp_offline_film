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
        # One original 48k PCM recording belongs to the shared performance,
        # not one independently duplicated soundtrack per camera. This
        # test-only audio is an authored tonal sound source, not a final mix.
        from backend.nvp_data_av_source import RecordedSoundSources
        from tools.nvp_film01_original_30s import _audio_tone
        cls.original_audio=RecordedSoundSources(cls.index).publish(
            cls.pid,"OneThirtySecondOriginalSound",
            _audio_tone(0,seconds=30))
        cls.timeline=TemporalLedger(cls.index).publish(
            cls.pid,"OneThirtySecondTimeline",[
                {"event_id":"OriginalObjectActorsMove","event_kind":"action",
                 "subject_id":"Donut","start_tick":0,
                 "end_tick":30*T,
                 "source_id":"NineCameraOriginalScene","source_revision":1,
                 "payload":{"usd_prim_path":"/World/Donut"}},
                {"event_id":"OneOriginalRoomSound","event_kind":"sound",
                 "subject_id":"RelayCore","start_tick":0,
                 "end_tick":30*T,
                 "source_id":"OneThirtySecondOriginalSound",
                 "source_revision":1,
                 "payload":{"gain":0.5,"original_recorded_pcm":True}},
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
        try:
            existing=bank.verify(self.pid,"TwoWallComparisonCameras",1)
        except KeyError:
            bank.create(self.pid,"TwoWallComparisonCameras",
                world_take_id="OneThirtySecondWorldTake",
                cameras=two,director_event="AUTHORIZE_WALL_SHOT")
        else:
            if existing["cameras"]!=two:
                raise RuntimeError("Cached film camera test fixture differs")
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
                "/World/NVPDirectorCameraRig/NVPDirector_"+camera).IsA(UsdGeom.Camera))
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

    def _original_editorial_bank(self):
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        bank=DirectorCameraBank(self.index,
            verify_director_action=lambda event,scope:
                event=="APPROVE_FILM01O_SOURCE" and
                scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        try:
            original=bank.verify(self.pid,"FullCameraRollOriginalBank",1)
        except KeyError:
            bank.create_standard_nine_preset(
                self.pid,"FullCameraRollOriginalBank",
                original_nine_rig_id="OnePerformanceNineCamBank",
                director_event="APPROVE_FILM01O_SOURCE")
        else:
            if original["camera_count"]!=9:
                raise RuntimeError("Cached nine-camera original source fixture altered")
        return bank

    def test_01o_real_native_film_source_and_original_sound(self):
        from backend.nvp_usd_film01o_original_camera_roll_source import (
            original_camera_roll_source,STAGE,MANIFEST)
        from backend.nvp_usd_film01p_source_multicam_film_conform import (
            _read_pcm_mix_from_original)
        from pxr import Usd
        bank=self._original_editorial_bank()
        folder=self.root/"full_original_source_01o"
        source=original_camera_roll_source(
            self.index,self.pid,"FullCameraRollOriginalBank",
            revision=1,folder=folder)
        self.assertEqual(source["frame_count"],720)
        self.assertEqual(source["camera_count"],9)
        self.assertEqual(len(source["original_frame_evidence"]),720)
        self.assertEqual(len({
            x["original_actor_state_sha256"]
            for x in source["original_frame_evidence"]})>2,True)
        self.assertTrue((folder/STAGE).is_file())
        self.assertTrue((folder/MANIFEST).is_file())
        stage=Usd.Stage.Open(str(folder/STAGE))
        self.assertEqual(stage.GetTimeCodesPerSecond(),24)
        self.assertEqual(stage.GetStartTimeCode(),1)
        self.assertEqual(stage.GetEndTimeCode(),720)
        mix=_read_pcm_mix_from_original(
            self.index,self.pid,"OneThirtySecondWorldTake",
            folder=self.root/"original_audio_mix_stems")
        self.assertEqual(mix["sample_count"],30*48000)
        self.assertEqual(mix["rate_hz"],48000)
        self.assertEqual(len(mix["mixed_original_events"]),1)
        self.assertEqual(
            mix["mixed_original_events"][0]["original_event_gain"],0.5)
        self.assertEqual(mix["clipped_pcm_samples"],0)
        self.assertEqual(self.index.read_revision(
            self.pid,"OneThirtySecondWorldTake",1)["document_sha256"],
            self.world_take["document_sha256"])

    def test_01o_native_resumable_original_camera_chunk(self):
        import os
        import subprocess
        import shutil
        from PIL import Image
        from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
        from backend.nvp_usd_film01o_recoverable_camera_roll_host import (
            RecoverableOriginalCameraRolls)
        blender=os.environ.get("NVP_FILM01O_BLENDER_BIN")
        if not blender:
            self.skipTest("Actual Blender 5.2 required for eight-frame native chunk")
        binary=Path(blender).resolve(strict=True)
        version=subprocess.run([str(binary),"-b","--version"],
            capture_output=True,text=True,check=True,timeout=30
        ).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        bank=self._original_editorial_bank()
        sup=BlenderWorkerSupervisor(self.root/"full_roll_worker_jobs",
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version=version)
        def authorized(event,scope):
            return (event=="APPROVE_EXACT_FRESH_EIGHT_FRAME_RENDER" and
                scope["operation"]=="nvp.render.usd_film01o_chunk.v1" and
                scope["camera_id"]=="Cam_A_wide" and
                scope["start_frame"]==0 and scope["attempt"]==1)
        host=RecoverableOriginalCameraRolls(
            self.index,sup,verify_director_action=authorized,
            prove_process_custody=lambda *_:False)
        result=host.run_chunk(
            self.pid,"FullCameraRollOriginalBank",revision=1,
            camera_id="Cam_A_wide",start=0,attempt=1,
            director_event="APPROVE_EXACT_FRESH_EIGHT_FRAME_RENDER")
        self.assertEqual(result["native_frames_checked"],8)
        self.assertEqual(result["state"],"REVERIFIED_COMPLETED")
        fresh=RecoverableOriginalCameraRolls(
            FilmIndex(Studio(self.db)),
            BlenderWorkerSupervisor(self.root/"full_roll_worker_jobs",
                blender_executable=binary,blender_sha256=sha_file(binary),
                blender_version=version),
            verify_director_action=lambda *_:False,
            prove_process_custody=lambda *_:False)
        previous=fresh.run_chunk(
            self.pid,"FullCameraRollOriginalBank",revision=1,
            camera_id="Cam_A_wide",start=0,attempt=1,
            director_event="IGNORED_FOR_ALREADY_VERIFIED_JOURNAL")
        self.assertEqual(previous["job_id"],result["job_id"])
        self.assertEqual(previous["native_frames_checked"],8)
        with self.assertRaises(PermissionError):
            fresh.run_chunk(
                self.pid,"FullCameraRollOriginalBank",revision=1,
                camera_id="Cam_A_wide",start=8,attempt=1,
                director_event="NO_NEW_APPROVAL")
        artifact=Path(os.environ.get(
            "NVP_FILM01O_ARTIFACT_DIR",
            str(self.root/"verified_original_eight_frames"))).resolve()
        artifact.mkdir(parents=True,exist_ok=True)
        job=sup.root/result["job_id"]
        for frame in range(8):
            picture=job/f"frame_{frame:04d}.png"
            with Image.open(picture) as im:
                self.assertEqual(im.size,(320,180))
                im.verify()
            shutil.copyfile(picture,artifact/picture.name)
        for name in ("audit.json","source.json","source.usda","chunk.json"):
            shutil.copyfile(job/name,artifact/name)
        (artifact/"restart_reverification.json").write_text(
            json.dumps({"job_id":result["job_id"],
                "native_cycles_frames":8,
                "fresh_supervisor_reverified":True,
                "different_chunk_without_authorization_rejected":True,
                "whole_9_camera_30s_film_rendered":False,
                "director_approved":False},indent=2,sort_keys=True),"utf8")

    def _selected_original_edit(self):
        from backend.nvp_usd_film01q_selected_view_edit import OriginalSelectedViewEdit
        self._original_editorial_bank()
        edit=OriginalSelectedViewEdit(self.index,
            verify_director_action=lambda event,scope:
                event=="AUTHORIZE_EXACT_SELECTED_EDIT" and
                scope["operation"]=="nvp.film01q.publish_selected_view_edit.v1")
        # The first 8-frame native job contains a REAL camera cut at frame 4.
        cuts=[
            {"camera_id":"Cam_A_wide","source_in_frame":0,
             "source_out_frame":4,"edit_in_frame":0,
             "edit_out_frame":4},
            {"camera_id":"Cam_B_medium","source_in_frame":4,
             "source_out_frame":720,"edit_in_frame":4,
             "edit_out_frame":720}]
        try:
            old=edit.verify(self.pid,"DataFirstOriginalSelectedShort",1)
        except KeyError:
            edit.create(
                self.pid,"DataFirstOriginalSelectedShort",
                camera_bank_id="FullCameraRollOriginalBank",
                camera_bank_revision=1,cuts=cuts,
                director_event="AUTHORIZE_EXACT_SELECTED_EDIT")
        else:
            self.assertEqual(old["cuts"],cuts)
        return edit

    def test_01q_source_verified_selected_views_without_nine_full_camera_rolls(self):
        from backend.nvp_usd_film01q_selected_view_edit import (
            selected_render_plan,OriginalSelectedViewEdit)
        from backend.nvp_usd_film01o_original_camera_roll_source import (
            original_camera_roll_source)
        edit=self._selected_original_edit()
        source_folder=self.root/"q_selected_frame_source"
        if not source_folder.exists():
            original_camera_roll_source(
                self.index,self.pid,"FullCameraRollOriginalBank",
                revision=1,folder=source_folder)
        wrapped=selected_render_plan(
            self.index,self.pid,"DataFirstOriginalSelectedShort",1,
            original_source_directory=source_folder)
        plan=wrapped["plan"]
        self.assertEqual(plan["selected_final_frame_count"],720)
        self.assertEqual(len(plan["chunks"]),90)
        self.assertFalse(plan["all_original_camera_rolls_required"])
        self.assertEqual(plan["frames"][3]["camera_id"],"Cam_A_wide")
        self.assertEqual(plan["frames"][4]["camera_id"],"Cam_B_medium")
        self.assertEqual(plan["chunks"][0]["camera_ids"],
                         ["Cam_A_wide","Cam_B_medium"])
        self.assertEqual(plan["chunks"][1]["camera_ids"],["Cam_B_medium"])
        self.assertEqual(plan["frames"][0]["original_film_tick"],0)
        self.assertEqual(plan["frames"][-1]["original_film_tick"],719*T//24)
        self.assertEqual(len({
            frame["original_actor_state_sha256"] for frame in plan["frames"]
        })>2,True)
        self.assertEqual(
            plan["original_world_take_sha256"],
            self.world_take["document_sha256"])
        for frame in plan["frames"]:
            self.assertEqual(frame["source_camera_prim"].split("/")[-1][:12],
                             "NVPDirector_")

        # An edit can change viewpoint AFTER original actor performance
        # was captured. Only changed frame-view keys are invalidated.
        updated=[
            {"camera_id":"Cam_A_wide","source_in_frame":0,
             "source_out_frame":8,"edit_in_frame":0,
             "edit_out_frame":8},
            {"camera_id":"Cam_B_medium","source_in_frame":8,
             "source_out_frame":720,"edit_in_frame":8,
             "edit_out_frame":720}]
        edit.revise(
            self.pid,"DataFirstOriginalSelectedShort",
            expected_revision=1,cuts=updated,
            director_event="AUTHORIZE_EXACT_SELECTED_EDIT")
        old=edit.verify(self.pid,"DataFirstOriginalSelectedShort",1)
        new=edit.verify(self.pid,"DataFirstOriginalSelectedShort",2)
        self.assertEqual(old["original_performance_sha256"],
                         new["original_performance_sha256"])
        edited=selected_render_plan(
            self.index,self.pid,"DataFirstOriginalSelectedShort",2,
            original_source_directory=source_folder)["plan"]
        self.assertEqual(
            plan["frames"][4]["original_actor_state_sha256"],
            edited["frames"][4]["original_actor_state_sha256"])
        self.assertNotEqual(plan["frames"][4]["view_cache_sha256"],
                            edited["frames"][4]["view_cache_sha256"])
        self.assertEqual(plan["frames"][8]["view_cache_sha256"],
                         edited["frames"][8]["view_cache_sha256"])
        self.assertEqual(plan["chunks"][1]["source_frames_sha256"],
                         edited["chunks"][1]["source_frames_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid,"OneThirtySecondWorldTake",1)["document_sha256"],
            self.world_take["document_sha256"])

    def test_01q_reject_unauthorized_or_gapped_editorial_source(self):
        from backend.nvp_usd_film01q_selected_view_edit import OriginalSelectedViewEdit
        self._original_editorial_bank()
        edit=OriginalSelectedViewEdit(
            self.index,verify_director_action=lambda *_:False)
        with self.assertRaises(PermissionError):
            edit.create(self.pid,"UnapprovedOriginalEdit",
                camera_bank_id="FullCameraRollOriginalBank",
                camera_bank_revision=1,
                cuts=[{"camera_id":"Cam_A_wide","source_in_frame":0,
                    "source_out_frame":720,"edit_in_frame":0,
                    "edit_out_frame":720}],
                director_event="BROWSER_IMPERSONATED_DIRECTOR")
        with self.assertRaises(RuntimeError):
            edit.create(self.pid,"UnapprovedOriginalEdit",
                camera_bank_id="FullCameraRollOriginalBank",
                camera_bank_revision=1,
                cuts=[{"camera_id":"Cam_A_wide","source_in_frame":0,
                    "source_out_frame":719,"edit_in_frame":0,
                    "edit_out_frame":719}],
                director_event="BROWSER_IMPERSONATED_DIRECTOR")
        with self.assertRaises(PermissionError):
            edit.create(self.pid,"UnapprovedOriginalEdit",
                camera_bank_id="FullCameraRollOriginalBank",
                camera_bank_revision=1,
                cuts=[{"camera_id":"CameraNotInSource","source_in_frame":0,
                    "source_out_frame":720,"edit_in_frame":0,
                    "edit_out_frame":720}],
                director_event="BROWSER_IMPERSONATED_DIRECTOR")

    def test_01q_genuine_cycles_selected_camera_switch_and_recovery(self):
        import os
        import shutil
        import subprocess
        from PIL import Image
        from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
        from backend.nvp_usd_film01q_selected_view_host import ReviewedSelectedViewFilm
        binary=os.environ.get("NVP_FILM01Q_BLENDER_BIN")
        if not binary:
            self.skipTest("Requires official Blender 5.2 to render real selected-view pictures")
        resolved=Path(binary).resolve(strict=True)
        version=subprocess.run([str(resolved),"-b","--version"],
            capture_output=True,text=True,check=True,timeout=30
        ).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        self._selected_original_edit()
        directory=self.root/"selected_real_cycles_jobs"
        supervisor=BlenderWorkerSupervisor(
            directory,blender_executable=resolved,
            blender_sha256=sha_file(resolved),
            blender_version=version)
        host=ReviewedSelectedViewFilm(
            self.index,supervisor,
            verify_director_action=lambda event,scope:
                event=="AUTHORIZE_REAL_SOURCE_SELECTED_EIGHT" and
                scope["operation"]==
                    "nvp.render.usd_film01q_selected_source_chunk.v1" and
                scope["start_frame"]==0 and
                scope["camera_ids"][:5]==[
                    "Cam_A_wide"]*4+["Cam_B_medium"],
            prove_process_custody=lambda *_:False)
        result=host.run_chunk(
            self.pid,"DataFirstOriginalSelectedShort",revision=1,
            start=0,attempt=1,
            director_event="AUTHORIZE_REAL_SOURCE_SELECTED_EIGHT")
        self.assertEqual(result["native_selected_views_rendered"],8)
        self.assertEqual(result["camera_ids"],
                         ["Cam_A_wide"]*4+["Cam_B_medium"]*4)
        # Recreate both trusted source store and host, then verify
        # persisted worker results instead of replaying the authorization.
        reopened=ReviewedSelectedViewFilm(
            FilmIndex(Studio(self.db)),
            BlenderWorkerSupervisor(
                directory,blender_executable=resolved,
                blender_sha256=sha_file(resolved),
                blender_version=version),
            verify_director_action=lambda *_:False,
            prove_process_custody=lambda *_:False)
        recovered=reopened.run_chunk(
            self.pid,"DataFirstOriginalSelectedShort",revision=1,
            start=0,attempt=1,director_event="MUST_NOT_AUTHORIZE_REPLAY")
        self.assertEqual(result["job_id"],recovered["job_id"])
        self.assertEqual(recovered["native_selected_views_rendered"],8)
        with self.assertRaises(PermissionError):
            reopened.run_chunk(
                self.pid,"DataFirstOriginalSelectedShort",revision=1,
                start=8,attempt=1,director_event="NO_FRESH_APPROVAL")
        dest=Path(os.environ.get(
            "NVP_FILM01Q_ARTIFACT_DIR",
            str(self.root/"selected_original_cut_evidence"))).resolve()
        dest.mkdir(parents=True,exist_ok=True)
        job=directory/result["job_id"]
        for i in range(8):
            picture=job/f"frame_{i:04d}.png"
            with Image.open(picture) as img:
                self.assertEqual(img.size,(320,180))
                img.verify()
            shutil.copyfile(picture,dest/picture.name)
        for name in ("audit.json","source.json","source.usda",
                     "chunk.json","plan.json"):
            shutil.copyfile(job/name,dest/name)
        (dest/"source_selected_native_status.json").write_text(
            json.dumps({"genuine_rendered_frames":8,
                        "same_original_actor_performance":True,
                        "actual_two_camera_cut_in_first_chunk":True,
                        "fresh_worker_host_restart_reverified":True,
                        "no_other_camera_roll_rendered":True,
                        "complete_final_30_second_film":False,
                        "director_visual_approval":False},
                       sort_keys=True,indent=2),"utf8")

    def test_01r_actual_lowfi_usd_geometry_and_one_time_source_camera(self):
        from backend.nvp_usd_film01r_lowfi_source import SourceViewpointWorkspace
        self._original_editorial_bank()
        inspector=SourceViewpointWorkspace(self.index)
        catalog=inspector.catalog(self.pid)
        self.assertEqual(catalog["format"],
                         "nvp.usd_film01r.original_world_viewpoint_catalog.v1")
        self.assertTrue(any(
            bank["camera_bank_id"]=="FullCameraRollOriginalBank"
            for bank in catalog["camera_banks"]))
        self.assertTrue(any(
            take["world_take_id"]=="OneThirtySecondWorldTake"
            for take in catalog["original_world_takes"]))
        for frame in (0,360,719):
            report=inspector.snapshot(
                self.pid,"FullCameraRollOriginalBank",1,
                camera_id="Cam_A_wide",frame=frame)
            self.assertEqual(report["format"],
                "nvp.usd_film01r.source_3d_lofi_viewpoint.v1")
            self.assertEqual(report["frame"],frame)
            self.assertEqual(report["original_film_tick"],frame*T//24)
            self.assertEqual(report["native_blender_workers_started"],0)
            self.assertGreater(len(report["objects"]),3)
            self.assertEqual(len(report["camera_world_matrix_rows"]),4)
            self.assertGreater(report["camera_vertical_fov_degrees"],2)
            self.assertTrue(report[
                "preview_is_source_derived_not_final_cycles_image"])
            self.assertTrue(report[
                "original_world_and_actor_performance_unchanged"])
            self.assertGreaterEqual(
                report["total_native_mesh_vertices_sent"],0)
            self.assertGreaterEqual(report["proxy_objects"],0)
            self.assertEqual(len(report["original_actor_ids"]),4)
        with self.assertRaises(PermissionError):
            inspector.snapshot(self.pid,"FullCameraRollOriginalBank",1,
                camera_id="InventedCamera",frame=0)
        self.assertEqual(self.index.read_revision(
            self.pid,"OneThirtySecondWorldTake",1)["document_sha256"],
            self.world_take["document_sha256"])

    def test_01r_true_native_webview_approval_camera_edit_and_denial(self):
        from backend.nvp_wo5_desktop_bridge import TrustedDesktopWO5Bridge
        class ApprovedWindow:
            permitted=True
            def get_current_url(self):
                return "http://127.0.0.1:43112/"
            def create_confirmation_dialog(self,title,text):
                self.last=(title,text)
                return self.permitted
        self._original_editorial_bank()
        window=ApprovedWindow()
        bridge=TrustedDesktopWO5Bridge(
            self.index,origin="http://127.0.0.1:43112")
        bridge._attach_window(window)
        original=self.index.read_revision(
            self.pid,"OneThirtySecondWorldTake",1)["document_sha256"]
        camera={
            "camera_id":"Master","setup":"Wide","framing":"wide",
            "position_m":[0,0,12],"rotation_euler_deg":[0,0,0],
            "focal_length_mm":35,"focus_distance_m":10,
            "clip_range_m":[.01,10000],"move_keys":[],
            "camera_ray_exclusions":[]}
        try:
            created=bridge.film01r_create_bank({
                "project_id":self.pid,
                "camera_bank_id":"R01NativeTestBank",
                "world_take_id":"OneThirtySecondWorldTake",
                "cameras":[camera]})
            self.assertEqual(created["revision"],1)
            report=bridge.film01r_preview({
                "project_id":self.pid,
                "camera_bank_id":"R01NativeTestBank",
                "revision":1,"camera_id":"Master","frame":3})
            self.assertEqual(report["original_film_tick"],3*T//24)
            window.permitted=False
            with self.assertRaises(PermissionError):
                bridge.film01r_revise_bank({
                    "project_id":self.pid,
                    "camera_bank_id":"R01NativeTestBank",
                    "expected_revision":1,
                    "changes":[{"op":"add","camera":{
                        **camera,"camera_id":"Reverse"}}]})
            window.permitted=True
            revised=bridge.film01r_revise_bank({
                "project_id":self.pid,"camera_bank_id":"R01NativeTestBank",
                "expected_revision":1,
                "changes":[{"op":"add","camera":{
                    **camera,"camera_id":"Reverse","position_m":[2,0,12]}}]})
            self.assertEqual(revised["revision"],2)
            self.assertEqual(len(bridge.film01r_catalog(self.pid)[
                "camera_banks"]),2)
            source_cut=[
                {"camera_id":"Master","source_in_frame":0,
                 "source_out_frame":360,"edit_in_frame":0,
                 "edit_out_frame":360},
                {"camera_id":"Reverse","source_in_frame":360,
                 "source_out_frame":720,"edit_in_frame":360,
                 "edit_out_frame":720}]
            saved=bridge.film01r_save_edit({
                "project_id":self.pid,"edit_id":"R01NativeTestEdit",
                "expected_revision":0,
                "camera_bank_id":"R01NativeTestBank",
                "camera_bank_revision":2,"cuts":source_cut})
            self.assertEqual(saved["revision"],1)
            self.assertFalse(saved["original_performance_modified"])
            self.assertEqual(
                bridge.film01r_catalog(self.pid)["edits"][-1]["edit_id"],
                "R01NativeTestEdit")
            self.assertEqual(self.index.read_revision(
                self.pid,"OneThirtySecondWorldTake",1)["document_sha256"],
                original)
            # A foreign browser origin cannot commit new native revisions.
            window.get_current_url=lambda:"http://127.0.0.1:43112/other"
            with self.assertRaises(PermissionError):
                bridge.film01r_save_edit({
                    "project_id":self.pid,"edit_id":"R01Foreign",
                    "expected_revision":0,
                    "camera_bank_id":"R01NativeTestBank",
                    "camera_bank_revision":2,"cuts":source_cut})
        finally:
            bridge._close()

    def test_01r_render_quality_changes_only_view_cache_and_worker_identity(self):
        from backend.nvp_usd_film01r_quality import (
            reviewed_quality,quality_hash)
        from backend.nvp_usd_film01q_selected_view_edit import selected_render_plan
        from backend.nvp_usd_film01q_selected_view_host import chunk_job_id
        from backend.nvp_usd_film01o_original_camera_roll_source import (
            original_camera_roll_source)
        self._selected_original_edit()
        source=self.root/"01r_quality_source"
        if not source.exists():
            original_camera_roll_source(
                self.index,self.pid,"FullCameraRollOriginalBank",
                revision=1,folder=source)
        draft=selected_render_plan(
            self.index,self.pid,"DataFirstOriginalSelectedShort",1,
            original_source_directory=source,render_quality="technical_smoke")
        final=selected_render_plan(
            self.index,self.pid,"DataFirstOriginalSelectedShort",1,
            original_source_directory=source,render_quality="final_720p")
        self.assertEqual(final["plan"]["render_profile"]["resolution_x"],1280)
        self.assertEqual(final["plan"]["render_profile"]["resolution_y"],720)
        self.assertNotEqual(draft["plan_sha256"],final["plan_sha256"])
        self.assertEqual(draft["plan"]["original_performance_sha256"],
                         final["plan"]["original_performance_sha256"])
        self.assertEqual(draft["plan"]["frames"][3]["original_actor_state_sha256"],
                         final["plan"]["frames"][3]["original_actor_state_sha256"])
        self.assertNotEqual(draft["plan"]["frames"][3]["view_cache_sha256"],
                            final["plan"]["frames"][3]["view_cache_sha256"])
        self.assertNotEqual(chunk_job_id(
            draft["plan"]["edit_document_sha256"],0,1,
            draft["plan"]["render_profile_sha256"]),chunk_job_id(
            final["plan"]["edit_document_sha256"],0,1,
            final["plan"]["render_profile_sha256"]))
        with self.assertRaises(ValueError):
            reviewed_quality("unreviewed_GPU_4K")

    def test_01r_real_draft_quality_blender_8_selected_frames(self):
        import os
        import shutil
        import subprocess
        from PIL import Image
        from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
        from backend.nvp_usd_film01q_selected_view_host import ReviewedSelectedViewFilm
        binary=os.environ.get("NVP_FILM01R_BLENDER_BIN")
        if not binary:
            self.skipTest("Actual native Blender 5.2 required for 01R draft-quality proof")
        executable=Path(binary).resolve(strict=True)
        first=subprocess.run(
            [str(executable),"-b","--version"],check=True,
            capture_output=True,text=True,timeout=30).stdout.splitlines()[0]
        self.assertTrue(first.startswith("Blender 5.2."),first)
        self._selected_original_edit()
        root=self.root/"01r_real_draft_jobs"
        supervisor=BlenderWorkerSupervisor(
            root,blender_executable=executable,
            blender_sha256=sha_file(executable),blender_version=first)
        host=ReviewedSelectedViewFilm(
            self.index,supervisor,
            verify_director_action=lambda event,scope:
                event=="APPROVE_EXACT_REAL_DRAFT_01R" and
                scope["operation"]==
                  "nvp.render.usd_film01q_selected_source_chunk.v1" and
                scope["start_frame"]==0 and
                scope["camera_ids"]==["Cam_A_wide"]*4+["Cam_B_medium"]*4 and
                type(scope.get("render_profile_sha256")) is str,
            prove_process_custody=lambda *_:False,
            render_quality="draft_360p")
        result=host.run_chunk(
            self.pid,"DataFirstOriginalSelectedShort",
            revision=1,start=0,attempt=1,
            director_event="APPROVE_EXACT_REAL_DRAFT_01R")
        self.assertEqual(result["native_selected_views_rendered"],8)
        self.assertEqual(result["camera_ids"],
                         ["Cam_A_wide"]*4+["Cam_B_medium"]*4)
        job=supervisor.root/result["job_id"]
        audit=json.loads((job/"audit.json").read_text("utf8"))
        self.assertEqual(audit["render_resolution_x"],640)
        self.assertEqual(audit["render_resolution_y"],360)
        self.assertEqual(audit["render_samples"],16)
        self.assertEqual(audit["native_rendered_frames"],8)
        self.assertTrue(audit["passed"])
        self.assertEqual([x["selected_camera_id"] for x in
                          audit["selected_view_frames"]],
                         ["Cam_A_wide"]*4+["Cam_B_medium"]*4)
        images=[]
        for i in range(8):
            p=job/f"frame_{i:04d}.png"
            with Image.open(p) as image:
                self.assertEqual(image.size,(640,360))
                image.verify()
            images.append(sha_file(p))
        self.assertGreater(len(set(images)),1)
        # Restart cannot silently use a prior approval or a different profile.
        reopened=ReviewedSelectedViewFilm(
            FilmIndex(Studio(self.db)),BlenderWorkerSupervisor(
                root,blender_executable=executable,
                blender_sha256=sha_file(executable),blender_version=first),
            verify_director_action=lambda *_:False,
            prove_process_custody=lambda *_:False,
            render_quality="draft_360p")
        recovered=reopened.run_chunk(
            self.pid,"DataFirstOriginalSelectedShort",
            revision=1,start=0,attempt=1,
            director_event="MUST_NOT_REUSE_PERMISSION")
        self.assertEqual(recovered["job_id"],result["job_id"])
        artifact=Path(os.environ.get(
            "NVP_FILM01R_ARTIFACT_DIR",
            str(self.root/"01r_draft_native_artifacts"))).resolve()
        artifact.mkdir(parents=True,exist_ok=True)
        for i in range(8):
            name=f"frame_{i:04d}.png"
            shutil.copyfile(job/name,artifact/name)
        for name in ("audit.json","source.json","source.usda",
                     "chunk.json","plan.json"):
            shutil.copyfile(job/name,artifact/name)
        (artifact/"01r_native_receipt.json").write_text(json.dumps({
            "actual_selected_view_frames":8,
            "actual_blender_cycles_draft_640x360":True,
            "same_original_performance_for_two_cameras":True,
            "restarted_worker_source_reverified":True,
            "full_30s_film_not_yet_rendered":True,
            "director_visual_acceptance":False},
            sort_keys=True,indent=2),"utf8")

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
