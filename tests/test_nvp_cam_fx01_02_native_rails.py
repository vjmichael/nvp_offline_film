"""CAM-FX-01/02 genuine FilmIndex, 01E ActorID Take and native OpenUSD.

No fake pxr stage, no unverified Cycles pixels and no implied physical
director consent; fixtures inject explicit test-only authorizations.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import math
import unittest

from pxr import Usd,UsdGeom

from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_cam_fx01_camera_rails import (
    OriginalCameraRails,normalize_rail,evaluate_rail,MAX_SPEED_MPS)
from backend.nvp_cam_fx02_usd_camera_layer import (
    open_approved_camera_layer,film_time_samples,
    camera_matrix_rows,camera_rail_path)

def node(tick,position,target,*,mode="hermite",ease="smoothstep",
         focal=35,focus=8,roll=0,aperture=5.6):
    return {
        "tick":tick,
        "position_m":position,
        "target_m":target,
        "tangent_in_mps":[0,0,0],
        "tangent_out_mps":[0,0,0],
        "roll_deg":roll,
        "focal_length_mm":focal,
        "focus_distance_m":focus,
        "f_stop":aperture,
        "segment_mode":mode,"easing":ease,
    }


class OriginalCAMFX01And02NativeRailTests(unittest.TestCase):
    def setUp(self):
        # Import only within fixture so discovery does not run the underlying
        # original 01E TestCase a second time as our own class.
        from test_nvp_usd_film01e_world_take import (
            OriginalWorldCinematicTakeTests)
        fixture=OriginalWorldCinematicTakeTests(
            "test_world_take_binds_actual_actor_and_original_pcm_without_new_voice")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.link_actor()
        fixture.freeze()
        self.fx=fixture
        self.pid=fixture.b.pid
        self.index=fixture.b.index
        self.original_world_take=self.index.read_revision(
            self.pid,"WorldStreetTake",1)["document_sha256"]
        self.original_scene_take=self.index.read_revision(
            self.pid,"OriginalStreetTake",1)["document_sha256"]
        self.original_camera_shot=self.index.read_revision(
            self.pid,"StreetWorldShot",1)["document_sha256"]
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda event,scope:
            event=="TEST_DIRECTOR_CAMERA_BANK" and
            scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        self.bank=bank.create(
            self.pid,"OriginalShotRailsBank",
            world_take_id="WorldStreetTake",
            cameras=[{
                "camera_id":"FilmRailCam","setup":"Street track",
                "framing":"medium","position_m":[0,-8,3],
                "rotation_euler_deg":[0,0,0],
                "focal_length_mm":35,
                "focus_distance_m":8,
                "clip_range_m":[.01,10000],
                "move_keys":[],"camera_ray_exclusions":[],
            }],director_event="TEST_DIRECTOR_CAMERA_BANK")
        self.decisions=[]
        def approve(event,scope):
            self.decisions.append(dict(scope))
            return (event=="TEST_AUTHORIZE_EXACT_RAIL" and
                scope["operation"]==
                "nvp.cam_fx02.publish_exact_director_camera_rail.v1")
        self.rails=OriginalCameraRails(
            self.index,verify_director_action=approve)

    def spec(self):
        return {
            "camera_bank_id":"OriginalShotRailsBank",
            "camera_bank_revision":1,
            "camera_id":"FilmRailCam",
            "film_start_tick":0,
            "film_end_tick":2*T,
            "technique":"dolly",
            "rail_origin_m":[100.,30.,1.],
            "filmback_mm":[36.,20.25],
            "nodes":[
                node(0,[0.,-8.,2.],[0.,0.,1.]),
                node(T,[0.,-7.,2.5],[0.,0.,1.],
                     focal=45,focus=7.5,aperture=4.0),
                node(2*T,[0.,-6.,3.],[0.,0.,1.],
                     focal=60,focus=6.,aperture=2.8),
            ],
        }

    def test_exact_original_time_hermite_dolly_native_usd_and_frozen_actors(self):
        spec=self.spec()
        clean=normalize_rail(spec,2*T)
        self.assertEqual(clean["nodes"][0]["tick"],0)
        self.assertEqual(clean["nodes"][2]["tick"],2*T)
        self.assertEqual(evaluate_rail(clean,0)["position_m"],[100,-8+30,3.])
        self.assertEqual(evaluate_rail(clean,T)["focal_length_mm"],45.)
        midpoint=evaluate_rail(clean,T//2)
        self.assertGreater(midpoint["position_m"][1],22.)
        self.assertLess(midpoint["position_m"][1],23.)
        self.assertTrue(math.isfinite(midpoint["f_stop"]))
        self.assertTrue(len(film_time_samples(clean))>=49)
        receipt=self.rails.preview(
            self.pid,"OriginalCameraRailOne",spec)
        self.assertFalse(receipt["director_creative_approval_granted"])
        self.assertEqual(receipt["world_take_sha256"],self.original_world_take)
        self.assertEqual(receipt["native_blender_workers_started"],0)
        with self.assertRaises(PermissionError):
            self.rails.publish(
                self.pid,"OriginalCameraRailOne",spec,
                expected_revision=0,
                preview_sha256=receipt["proposal_sha256"],
                director_event="INVALID_MODEL_RESPONSE")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"OriginalCameraRailOne",1)
        record=self.rails.publish(
            self.pid,"OriginalCameraRailOne",spec,
            expected_revision=0,preview_sha256=receipt["proposal_sha256"],
            director_event="TEST_AUTHORIZE_EXACT_RAIL")
        self.assertEqual(record["revision"],1)
        self.assertEqual(record["source_usd_layer_sha256"],
                         receipt["rail_layer_sha256"])
        self.assertEqual(self.rails.verify(
            self.pid,"OriginalCameraRailOne",1)["rail_layer_sha256"],
            receipt["rail_layer_sha256"])
        with open_approved_camera_layer(
                self.index,self.pid,"OriginalCameraRailOne",1) as stage:
            self.assertEqual(stage["format"],
                "nvp.cam_fx02.native_immutable_stronger_director_camera_layer.v1")
            self.assertEqual(stage["camera_path"],
                camera_rail_path("OriginalCameraRailOne"))
            usd=UsdGeom.Camera.Get(stage["stage"],stage["camera_path"])
            self.assertTrue(usd)
            self.assertGreater(len(stage["native_verified_time_samples"]),48)
            self.assertAlmostEqual(
                float(usd.GetFocalLengthAttr().Get(Usd.TimeCode(float(T))))*100,45,places=4)
            self.assertTrue(stage["original_actor_takes_pcm_unchanged"])
            self.assertTrue(stage["source_world_root_layer_unchanged"])
            self.assertEqual(stage["native_cycles_frames_rendered"],0)
        self.assertEqual(self.index.read_revision(
            self.pid,"WorldStreetTake",1)["document_sha256"],
            self.original_world_take)
        self.assertEqual(self.index.read_revision(
            self.pid,"OriginalStreetTake",1)["document_sha256"],
            self.original_scene_take)
        self.assertEqual(self.index.read_revision(
            self.pid,"StreetWorldShot",1)["document_sha256"],
            self.original_camera_shot)
        self.assertEqual(self.index.read_revision(
            self.pid,"OriginalShotRailsBank",1)["document_sha256"],
            self.bank["document_sha256"])

    def test_revise_camera_rail_preserves_previous_native_layer_and_source(self):
        initial=self.spec()
        p1=self.rails.preview(self.pid,"EditableRail",initial)
        self.rails.publish(
            self.pid,"EditableRail",initial,
            expected_revision=0,preview_sha256=p1["proposal_sha256"],
            director_event="TEST_AUTHORIZE_EXACT_RAIL")
        revised=deepcopy(initial)
        revised["technique"]="crane"
        revised["nodes"][1]["position_m"]=[0.,-7.,4.]
        revised["nodes"][2]["position_m"]=[0.,-6.,5.]
        revised["nodes"][1]["focus_distance_m"]=6.
        p2=self.rails.preview(self.pid,"EditableRail",revised,
                              expected_revision=1)
        self.assertNotEqual(p1["rail_layer_sha256"],p2["rail_layer_sha256"])
        with self.assertRaises(PermissionError):
            self.rails.publish(self.pid,"EditableRail",revised,
                expected_revision=1,preview_sha256=p1["proposal_sha256"],
                director_event="TEST_AUTHORIZE_EXACT_RAIL")
        second=self.rails.publish(
            self.pid,"EditableRail",revised,expected_revision=1,
            preview_sha256=p2["proposal_sha256"],
            director_event="TEST_AUTHORIZE_EXACT_RAIL")
        self.assertEqual(second["revision"],2)
        self.assertEqual(self.rails.verify(
            self.pid,"EditableRail",1)["rail_layer_sha256"],
            p1["rail_layer_sha256"])
        self.assertEqual(self.rails.verify(
            self.pid,"EditableRail",2)["rail_layer_sha256"],
            p2["rail_layer_sha256"])
        with open_approved_camera_layer(
                self.index,self.pid,"EditableRail",1) as old:
            old_pos=UsdGeom.Xformable(old["stage"].GetPrimAtPath(
                old["camera_path"])).GetLocalTransformation(
                    Usd.TimeCode(float(T))).ExtractTranslation()
            old_sha=old["rail_layer_sha256"]
        with open_approved_camera_layer(
                self.index,self.pid,"EditableRail",2) as new:
            new_pos=UsdGeom.Xformable(new["stage"].GetPrimAtPath(
                new["camera_path"])).GetLocalTransformation(
                    float(T)).ExtractTranslation()
            self.assertNotEqual(float(old_pos[2]),float(new_pos[2]))
            self.assertNotEqual(old_sha,new["rail_layer_sha256"])
        with self.assertRaises(RuntimeError):
            self.rails.publish(self.pid,"EditableRail",revised,
                expected_revision=1,preview_sha256=p2["proposal_sha256"],
                director_event="TEST_AUTHORIZE_EXACT_RAIL")
        self.assertEqual(self.index.read_revision(
            self.pid,"OriginalStreetTake",1)["document_sha256"],
            self.original_scene_take)

    def test_exact_native_camera_orientation_and_original_up_axis(self):
        spec=self.spec()
        sample=evaluate_rail(normalize_rail(spec,2*T),T//2)
        matrix=camera_matrix_rows(sample)
        # Basis row vectors are right-handed and keep USD -Z as forward.
        x,y,z=matrix[:3]
        self.assertAlmostEqual(sum(v*v for v in x[:3]),1.,places=5)
        self.assertAlmostEqual(sum(v*v for v in y[:3]),1.,places=5)
        self.assertAlmostEqual(sum(v*v for v in z[:3]),1.,places=5)
        self.assertAlmostEqual(sum(x[i]*z[i] for i in range(3)),0,places=5)
        self.assertEqual(matrix[3][:3],sample["position_m"])

    def test_invalid_speed_focus_tick_target_and_unapproved_camera_are_rejected(self):
        base=self.spec()
        corruptions=[
            ("nodes",lambda s:s["nodes"][1].update(
                {"target_m":[0.,-7.,2.5]})),
            ("nodes",lambda s:s["nodes"][1].update(
                {"focal_length_mm":float("nan")})),
            ("nodes",lambda s:s["nodes"][1].update(
                {"tick":s["nodes"][0]["tick"]})),
            ("nodes",lambda s:s["nodes"][0].update(
                {"position_m":[-MAX_SPEED_MPS*100,0,0]})),
            ("nodes",lambda s:s["nodes"][1].update(
                {"focus_distance_m":-1})),
            ("camera_id",lambda s:s.update({"camera_id":"NotInSourceBank"})),
            ("technique",lambda s:s.update({"technique":"AI_USER_SCRIPT"})),
            ("filmback_mm",lambda s:s.update({"filmback_mm":[36,float("inf")]})),
            ("film_end_tick",lambda s:s.update({"film_end_tick":99*T})),
        ]
        for field,damage in corruptions:
            with self.subTest(field=field,damage=damage):
                candidate=deepcopy(base)
                damage(candidate)
                with self.assertRaises((ValueError,PermissionError)):
                    self.rails.preview(self.pid,"UnsafeRail",candidate)
        self.assertEqual(self.decisions,[])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"UnsafeRail",1)

if __name__=="__main__":
    unittest.main()
