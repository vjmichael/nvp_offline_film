"""CAM-FX-05A native OpenUSD exact-time rail camera / frozen source tests.

Tests require first-party pxr and real FilmIndex 01E world/actor/PCM plus
02M-H approved district source, not a mocked camera or fake film frames.
The separate full CAM-FX-05 protected Blender/Cycles gate is still open.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import os
import shutil
import subprocess
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_cam_fx05_protected_cycles_host import ReviewedCameraRailCyclesHost
from tempfile import TemporaryDirectory
import json
import unittest

from pxr import Usd,UsdGeom

from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails
from backend.nvp_cam_fx02_usd_camera_layer import camera_rail_path
from backend.nvp_cam_fx05_verified_shot_source import (
    stage_approved_rail_frame,FORMAT,RECEIPT)
from backend.nvp_usd_film01f_blender_host import USD,MANIFEST


def node(tick,x,*,focus=8.0,focal=35.0):
    return {
        "tick":tick,"position_m":[x,-8.,5.],
        "target_m":[0.,0.,1.],
        "tangent_in_mps":[0.,0.,0.],
        "tangent_out_mps":[0.,0.,0.],
        "roll_deg":0.,"focal_length_mm":focal,
        "focus_distance_m":focus,"f_stop":5.6,
        "segment_mode":"hermite","easing":"smoothstep"}


class OriginalCAMFX05RealSourceStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The real 02M-H fixture brings source-only, first-party USD materials,
        # actual ActorID geometry, an original PCM Take and an approved district.
        # It is NOT the native Cycles subprocess acceptance test.
        from test_nvp_usd_film02mh_real_shot_render import (
            OriginalActorDistrictNativeRenderTests)
        cls.fixture=OriginalActorDistrictNativeRenderTests
        cls.fixture.setUpClass()
        cls.index=cls.fixture.index
        cls.pid=cls.fixture.pid
        cls.take=cls.fixture.take_id
        cls.take_sha=cls.fixture.take_sha
        cls.original_actor_pcm_sha=list(cls.fixture.original_actor_take_shas)
        bank=DirectorCameraBank(cls.index,
            verify_director_action=lambda event,scope:
            event=="TEST_FX05_BANK" and
            scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        bank.create(cls.pid,"CAMFX05OriginalBank",
            world_take_id=cls.take,
            cameras=[{
                "camera_id":"CAMFX05SourceCam","setup":"Moving original street",
                "framing":"medium","position_m":[0.,-8.,5.],
                "rotation_euler_deg":[0.,0.,0.],
                "focal_length_mm":35.,"focus_distance_m":8.,
                "clip_range_m":[.01,10000.],
                "move_keys":[],"camera_ray_exclusions":[]}],
            director_event="TEST_FX05_BANK")
        cls.rails=OriginalCameraRails(cls.index,
            verify_director_action=lambda event,scope:
            event=="TEST_FX05_RAIL" and
            scope["operation"]==
            "nvp.cam_fx02.publish_exact_director_camera_rail.v1")
        cls.base={
            "camera_bank_id":"CAMFX05OriginalBank",
            "camera_bank_revision":1,
            "camera_id":"CAMFX05SourceCam",
            "film_start_tick":4*T,"film_end_tick":6*T,
            "technique":"dolly","rail_origin_m":[0.,0.,0.],
            "filmback_mm":[36.,20.25],
            "nodes":[node(4*T,-1.),node(5*T,0.,focus=7.0,focal=45.),
                     node(6*T,1.,focus=6.0,focal=60.)]}
        first=cls.rails.preview(cls.pid,"CAMFX05ReviewedRail",cls.base)
        cls.rails.publish(cls.pid,"CAMFX05ReviewedRail",cls.base,
            expected_revision=0,
            preview_sha256=first["proposal_sha256"],
            director_event="TEST_FX05_RAIL")
        changed=deepcopy(cls.base)
        changed["nodes"][1]["position_m"]=[2.,-8.,5.]
        changed["nodes"][1]["focal_length_mm"]=55.
        second=cls.rails.preview(
            cls.pid,"CAMFX05ReviewedRail",changed,expected_revision=1)
        cls.rails.publish(cls.pid,"CAMFX05ReviewedRail",changed,
            expected_revision=1,
            preview_sha256=second["proposal_sha256"],
            director_event="TEST_FX05_RAIL")

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDownClass()

    def test_two_approved_rail_revisions_different_real_3d_camera_same_actor_and_original_pcm(self):
        frozen_before=self.index.list_objects(self.pid,kind="take")
        with TemporaryDirectory(prefix="nvp-fx05-source-real-") as temp:
            root=Path(temp).resolve()
            results=[]
            for rev in (1,2):
                job=root/("camera"+str(rev))
                job.mkdir()
                staged=stage_approved_rail_frame(
                    self.index,self.pid,"Native02MHBinding1",
                    "CAMFX05ReviewedRail",rev,job)
                evidence=staged["receipt"]
                self.assertEqual(evidence["format"],FORMAT)
                self.assertTrue(evidence["source_camera_matrix_unchanged"])
                self.assertTrue(evidence["original_actor_takes_and_pcm_unchanged"])
                self.assertEqual(evidence["source_film_tick"],5*T)
                self.assertEqual(evidence["original_world_take_sha256"],self.take_sha)
                self.assertFalse(evidence["actual_blender_cycles_pixels"])
                self.assertEqual(staged["native_blender_workers_started"],0)
                self.assertEqual(evidence,json.loads((job/RECEIPT).read_text("utf8")))
                packet=json.loads((job/MANIFEST).read_text("utf8"))
                self.assertEqual(packet,staged["packet"])
                src=Usd.Stage.Open(str(job/USD),load=Usd.Stage.LoadAll)
                rail_path=camera_rail_path("CAMFX05ReviewedRail")
                camera=UsdGeom.Camera.Get(src,rail_path)
                self.assertTrue(camera.GetPrim().IsDefined())
                self.assertTrue(src.GetPrimAtPath(
                    evidence["original_camera_path"]).IsA(UsdGeom.Camera))
                self.assertEqual(camera.GetFocalLengthAttr().Get(
                    Usd.TimeCode(1.0)),45. if rev==1 else 55.)
                self.assertEqual(
                    camera.GetFocalLengthAttr().GetTimeSamples(),[1.0])
                self.assertEqual(src.GetStartTimeCode(),1.)
                self.assertEqual(src.GetEndTimeCode(),1.)
                results.append((evidence,staged))
            first,second=results
            self.assertEqual(
                first[0]["original_02mh_usd_sha256"],
                second[0]["original_02mh_usd_sha256"])
            self.assertEqual(
                first[0]["original_camera_shot_sha256"],
                second[0]["original_camera_shot_sha256"])
            self.assertNotEqual(
                first[0]["derived_with_rail_usd_sha256"],
                second[0]["derived_with_rail_usd_sha256"])
            self.assertNotEqual(
                first[1]["director_camera_sample"]["position_m"],
                second[1]["director_camera_sample"]["position_m"])
        self.assertEqual(self.index.list_objects(self.pid,kind="take"),frozen_before)
        self.assertEqual(self.fixture.original_actor_take_shas,
                         self.original_actor_pcm_sha)

    def test_native_technique_variants_have_exact_camera_matrix_not_just_style_tags(self):
        from backend.nvp_cam_fx02_usd_camera_layer import (
            generate_camera_director_layer,camera_matrix_rows,
            MM_PER_CAMERA_UNIT)
        from backend.nvp_cam_fx01_camera_rails import (
            normalize_rail,evaluate_rail)
        from pxr import Sdf
        cases=("static","dolly","arc","crane","pan_tilt",
               "over_shoulder","rack_focus","dolly_zoom")
        for technique in cases:
            with self.subTest(technique=technique):
                draft=deepcopy(self.base)
                draft["technique"]=technique
                if technique=="static":
                    for item in draft["nodes"]:
                        item["position_m"]=[0.,-8.,5.]
                elif technique in ("arc","over_shoulder"):
                    draft["nodes"][1]["position_m"]=[2.,-6.,5.]
                elif technique=="crane":
                    draft["nodes"][1]["position_m"]=[0.,-8.,7.]
                elif technique=="pan_tilt":
                    draft["nodes"][1]["target_m"]=[1.,0.,2.]
                elif technique=="rack_focus":
                    draft["nodes"][1]["focus_distance_m"]=3.
                elif technique=="dolly_zoom":
                    draft["nodes"][1]["focal_length_mm"]=80.
                normalized=normalize_rail(
                    draft,self.rails.verify(self.pid,
                         "CAMFX05ReviewedRail",1)["source_duration_ticks"])
                layer=generate_camera_director_layer(
                    "CAMFX05Technique"+technique.replace("_","").capitalize(),
                    normalized)
                source=Sdf.Layer.CreateAnonymous("cam-fx05-"+technique+".usda")
                self.assertTrue(source.ImportFromString(layer.decode("utf8")))
                stage=Usd.Stage.Open(source)
                camera=UsdGeom.Camera.Get(stage,
                    camera_rail_path("CAMFX05Technique"+
                        technique.replace("_","").capitalize()))
                self.assertTrue(camera.GetPrim().IsDefined())
                for tick in (4*T,4*T+T//2,5*T,5*T+T//2,6*T):
                    sample=evaluate_rail(normalized,tick)
                    native=UsdGeom.Xformable(camera).GetLocalTransformation(
                        Usd.TimeCode(float(tick)))
                    expected=camera_matrix_rows(sample)
                    for i in range(4):
                        for j in range(4):
                            self.assertAlmostEqual(
                                float(native[i][j]),expected[i][j],places=4)
                    self.assertAlmostEqual(
                        camera.GetFocalLengthAttr().Get(
                            Usd.TimeCode(float(tick)))*MM_PER_CAMERA_UNIT,
                        sample["focal_length_mm"],places=3)

    def test_05b_render_authority_is_separate_from_saved_rail_approval(self):
        with self.assertRaises(TypeError):
            ReviewedCameraRailCyclesHost(
                self.index,object(),verify_director_action=lambda *_:True)
        # Just publishing or previewing a camera rail has never rendered
        # a Cycles frame or produced a Blender worker permission token.
        source=self.rails.verify(self.pid,"CAMFX05ReviewedRail",2)
        self.assertEqual(source["native_cycles_frames_rendered"],0)
        self.assertFalse(source["human_picture_quality_approved"])

    def test_genuine_protected_blender_52_render_and_independent_saved_rail_camera_reopen(self):
        executable=os.environ.get("NVP_CAM_FX05_BLENDER_BIN")
        if not executable:
            self.skipTest("Actual first-party Blender 5.2 native render gate not configured")
        binary=Path(executable).resolve(strict=True)
        version=subprocess.run(
            [str(binary),"-b","--version"],capture_output=True,
            text=True,check=True,timeout=30).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        before=self.index.list_objects(self.pid,kind="take")
        with TemporaryDirectory(prefix="nvp-camfx05-real-native-cycles-") as tmp:
            sup=BlenderWorkerSupervisor(
                Path(tmp)/"protected-jobs",
                blender_executable=binary,
                blender_sha256=sha_file(binary),
                blender_version=version)
            decisions=[]
            def approve(event,scope):
                decisions.append(dict(scope))
                return (event=="TEST_EXACT_CAM_FX05_RENDER" and
                        scope["operation"]==
                        "nvp.cam_fx05.render_reviewed_director_rail_frame.v1")
            host=ReviewedCameraRailCyclesHost(
                self.index,sup,verify_director_action=approve)
            with self.assertRaises(PermissionError):
                host.render(
                    self.pid,"Native02MHBinding1","CAMFX05ReviewedRail",1,
                    job_id="fx05_denied",director_event="OLD_RAIL_GRANT")
            self.assertFalse((sup.root/"fx05_denied").exists())
            with self.assertRaises(KeyError):
                sup.inspect("fx05_denied")
            compared=host.compare_revisions(
                self.pid,"Native02MHBinding1","CAMFX05ReviewedRail",1,2,
                job_a="fx05_move_a",job_b="fx05_move_b",
                director_event="TEST_EXACT_CAM_FX05_RENDER")
            self.assertEqual(compared["format"],
                "nvp.cam_fx05.real_two_revisions_original_source_rail_cycles.v1")
            self.assertEqual(compared["world_take_sha256"],self.take_sha)
            self.assertGreaterEqual(compared["pixels_changed_over_rgb12"],250)
            self.assertTrue(compared["independent_blender_reopen_each"])
            self.assertTrue(compared["original_actor_pcm_unchanged"])
            self.assertEqual(len(decisions),3)
            self.assertNotEqual(decisions[1]["rail_revision_sha256"],
                                decisions[2]["rail_revision_sha256"])
            self.assertEqual(decisions[1]["original_world_take_sha256"],
                             decisions[2]["original_world_take_sha256"])
            for rev,job in ((1,"fx05_move_a"),(2,"fx05_move_b")):
                readback=host.reopen_verified_render(
                    self.pid,"Native02MHBinding1",
                    "CAMFX05ReviewedRail",rev,job)
                self.assertTrue(readback["independent_blender_reopen_verified"])
                self.assertFalse(readback["director_picture_quality_approved"])
                self.assertEqual(readback["picture_sha256"],
                                 sha_file(sup.root/job/"frame.png"))
                self.assertEqual(readback["original_world_take_sha256"],
                                 self.take_sha)
            with self.assertRaises((RuntimeError,PermissionError)):
                host.reopen_verified_render(
                    self.pid,"Native02MHBinding1",
                    "CAMFX05ReviewedRail",2,"fx05_move_a")
            export=os.environ.get("NVP_CAM_FX05_ARTIFACT_DIR")
            if export:
                target=Path(export).resolve()
                target.mkdir(parents=True,exist_ok=True)
                (target/"comparison.json").write_text(
                    json.dumps(compared,sort_keys=True,indent=2),"utf8")
                for rev,job in ((1,"fx05_move_a"),(2,"fx05_move_b")):
                    for name in ("frame.png","scene.blend","source.usda",
                                 "source.json","district.json",
                                 "cam_fx05_rail_source.json","audit.json"):
                        shutil.copyfile(sup.root/job/name,
                                        target/(str(rev)+"_"+name))
                    shutil.copyfile(
                        sup.root/(job+"_reopen")/"audit.json",
                        target/(str(rev)+"_independent_reopen.json"))
            self.assertFalse(compared["human_artistic_approval"])
        self.assertEqual(self.index.list_objects(self.pid,kind="take"),before)
        self.assertEqual(self.fixture.original_actor_take_shas,
                         self.original_actor_pcm_sha)

    def test_stale_unpublished_foreign_time_and_dirty_job_fail_closed(self):
        with TemporaryDirectory(prefix="nvp-fx05-reject-") as temp:
            root=Path(temp).resolve()
            fresh=root/"invalid"
            fresh.mkdir()
            with self.assertRaises((KeyError,PermissionError,RuntimeError)):
                stage_approved_rail_frame(
                    self.index,self.pid,"Native02MHBinding1",
                    "ARevisionNeverPublished",1,fresh)
            self.assertEqual(list(fresh.iterdir()),[])
            source=deepcopy(self.base)
            source["film_start_tick"]=8*T
            source["film_end_tick"]=10*T
            source["nodes"]=[
                node(8*T,-1.),node(9*T,0.),node(10*T,1.)]
            candidate=self.rails.preview(
                self.pid,"CAMFX05WrongShotTime",source)
            self.rails.publish(self.pid,"CAMFX05WrongShotTime",source,
                expected_revision=0,preview_sha256=candidate["proposal_sha256"],
                director_event="TEST_FX05_RAIL")
            with self.assertRaises(PermissionError):
                stage_approved_rail_frame(
                    self.index,self.pid,"Native02MHBinding1",
                    "CAMFX05WrongShotTime",1,fresh)
            self.assertEqual(list(fresh.iterdir()),[])
            (fresh/"foreign.txt").write_text("not native owner",encoding="utf8")
            with self.assertRaises(PermissionError):
                stage_approved_rail_frame(
                    self.index,self.pid,"Native02MHBinding1",
                    "CAMFX05ReviewedRail",1,fresh)
