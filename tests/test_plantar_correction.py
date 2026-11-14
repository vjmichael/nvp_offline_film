"""PROD06E2C3: contact infeasibility, approval guards and independent audits."""
import copy
import math
import tempfile
import unittest
from pathlib import Path

from backend.nvp_plantar_correction import (
    PlantarCorrectionPlan,solve_vertical_contact,validate_correction_config)
from backend.nvp_plantar_blender import (
    PLANTAR_CORRECTION_BUILD,PLANTAR_CORRECTION_SNAPSHOT,compare_correction_audits)
from backend.nvp_studio import Studio
from backend.nvp_production_scene import digest


def source():
    return {
      "take":{"shots":[{"start_frame":1,"stop_frame":4}]},
      "foot_lock":{"approval_sha":"a"*64,"actors":[{
          "instance_id":"actor","config":{
              "left":{"contact_windows":[[1,1]],"pole_offset_actor_m":[0,.4,0]},
              "right":{"contact_windows":[[2,2]],"pole_offset_actor_m":[0,.4,0]}
          }}]},
      "leg_identity":{"approval_sha":"b"*64,"actors":[{"instance_id":"actor","asset_sha256":"c"*64}]},
      "plantar":{"approval_sha":"p"*64,"plan":{
          "surface":{"object_name":"NVP_FLOOR","geometry_sha256":"d"*64},
          "actors":{"actor":{
              "left":{"contact_roles":["toe"],"mesh_name":"RealMesh","markers":{"heel":1,"ball":2,"toe":3}},
              "right":{"contact_roles":["toe"],"mesh_name":"RealMesh","markers":{"heel":10,"ball":11,"toe":12}},
              "max_penetration_m":.002,"max_gap_m":.02,"max_slide_m":.012}}}}
    }


def proposal():
    return {"actors":{"actor":{"max_ankle_delta_m":.025,
                                 "max_iterations":6,"target_clearance_m":.001,
                                 "max_joint_delta_deg":50.}}}


def snap(mode):
    frames={}
    identity=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
    for frame in range(1,4):
        frame_id=str(frame)
        frame_data={"cameras":{"shot_camera":{"world":identity[:],"lens":35.}},
          "actors":{"actor":{"root":identity[:],"rig":identity[:],
             "legs":{side:{"hip_rotation":[1.,0.,0.,0.],
                           "knee_rotation":[1.,0.,0.,0.],
                           "upper_local_m":.26,"lower_local_m":.27}
                     for side in ("left","right")}}}}
        frames[frame_id]=frame_data
    if mode=="output":
        frames["1"]["actors"]["actor"]["legs"]["left"]["hip_rotation"]=[.98,.02,0,0]
        frames["2"]["actors"]["actor"]["legs"]["right"]["knee_rotation"]=[.98,.02,0,0]
    return {"format":"nvp.plantar.correction.snapshot.v1",
            "mode":mode,"approved_lock_sha":"a"*64,
            "approved_correction_sha":"x"*64,
            "cuts":[[1,"shot_camera"]],"frames":frames}


def audited():
    pkg=source()
    pkg["plantar_correction"]={"format":"nvp.plantar.correction.approved.v1",
                                  "approval_sha":"x"*64,"plan":proposal()}
    return pkg


def compare(before=None,after=None,corrected_contact=True):
    return compare_correction_audits(
      before if before is not None else snap("baseline"),
      after if after is not None else snap("output"),
      {"format":"nvp.plantar.correction.bake.v1","approval_sha":"x"*64},
      audited(),
      {"approved_plantar_sha":"p"*64,"contact_meets_configured_tolerances":False},
      {"approved_plantar_sha":"p"*64,"contact_meets_configured_tolerances":corrected_contact})


class BoundedContactMath(unittest.TestCase):
    def test_real_toe_penetration_has_small_feasible_correction(self):
        d=solve_vertical_contact({"toe":-.006823},.002,.02,.025,.001)
        self.assertAlmostEqual(d,.007823)
        self.assertTrue(-.002<=-.006823+d<=.02)

    def test_contradictory_heel_ball_toe_cannot_share_translation(self):
        with self.assertRaisesRegex(RuntimeError,"cannot share"):
            solve_vertical_contact({"heel":.11314,"ball":.07396,"toe":-.006823},
                                   .002,.02,.025,.001)

    def test_refuse_invalid_evidence_or_budgets(self):
        samples=[
            ({"toe":float("nan")},.002,.02,.025,.001),
            ({"unknown":0},.002,.02,.025,.001),
            ({},.002,.02,.025,.001),
            ({"toe":-5},.002,.02,.025,.001),
            ({"toe":.1},.002,.02,.025,.001),
            ({"toe":0},.002,.02,-1,.001),
            ({"toe":0},.002,.02,.025,.04),
        ]
        for gaps,p,g,max_move,target in samples:
            with self.subTest(input=gaps),self.assertRaises((RuntimeError,ValueError)):
                solve_vertical_contact(gaps,p,g,max_move,target)


class CorrectionApproval(unittest.TestCase):
    def test_exact_plan_contract(self):
        self.assertEqual(validate_correction_config(proposal(),source())["actors"]["actor"]["max_iterations"],6)
        for mutation in ("other_actor","missing_limit","too_many_iterations","nan_clearance",
                         "angle_above_limit","bad_delta"):
            x=proposal()
            row=x["actors"]["actor"]
            if mutation=="other_actor":x["actors"]["foreign"]=row
            if mutation=="missing_limit":del row["max_ankle_delta_m"]
            if mutation=="too_many_iterations":row["max_iterations"]=25
            if mutation=="nan_clearance":row["target_clearance_m"]=float("nan")
            if mutation=="angle_above_limit":row["max_joint_delta_deg"]=100
            if mutation=="bad_delta":row["max_ankle_delta_m"]=1.
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                validate_correction_config(x,source())

    def test_creator_authorization_and_durable_dependency_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio=Studio(Path(tmp)/"project.sqlite")
            pid=studio.create_project("Foot study","Test film")["id"]
            package=source()
            class Fixed(PlantarCorrectionPlan):
                def _context(self,p,s):
                    if p!=pid or s!="scene":raise KeyError("Foreign film")
                    return package,digest([package["plantar"],package["foot_lock"],
                                           package["leg_identity"],package["take"]])
            svc=Fixed(studio)
            r=svc.create(pid,"scene")
            with self.assertRaises(RuntimeError):svc.approve(pid,"scene",0)
            r=svc.configure(pid,"scene",proposal(),r["revision"])
            with self.assertRaises(RuntimeError):svc.configure(pid,"scene",proposal(),0)
            r=svc.approve(pid,"scene",r["revision"])
            self.assertEqual(r["status"],"approved")
            self.assertFalse(svc.export(pid,"scene")["plantar_correction"]["anatomical_sole_certified"])
            other=Fixed(Studio(studio.db_path))
            self.assertEqual(other.read(pid,"scene")["approval_sha"],r["approval_sha"])
            package["plantar"]["approval_sha"]="altered"
            self.assertTrue(other.read(pid,"scene")["stale"])
            with self.assertRaises(RuntimeError):other.export(pid,"scene")


class NativeComparison(unittest.TestCase):
    def test_independent_after_reopen_accepts_only_changed_contact_poses(self):
        r=compare()
        self.assertEqual(r["status"],"passed_native_marker_floor_correction_only")
        self.assertFalse(r["source_plantar_contact"])
        self.assertTrue(r["corrected_marker_contact"])
        self.assertFalse(r["anatomical_sole_certified"])
        self.assertGreater(r["protected_noncontact_leg_frames"],0)
        self.assertGreater(r["changed_contact_leg_frames"],0)

    def test_failure_if_contact_still_penetrates(self):
        with self.assertRaisesRegex(RuntimeError,"contact"):
            compare(corrected_contact=False)

    def test_failure_if_camera_root_noncontact_or_length_change(self):
        for mode in ("camera","root","noncontact","length","extra_frame","cut"):
            after=snap("output")
            if mode=="camera":after["frames"]["1"]["cameras"]["shot_camera"]["lens"]=36.
            if mode=="root":after["frames"]["1"]["actors"]["actor"]["root"][12]=.1
            if mode=="noncontact":after["frames"]["3"]["actors"]["actor"]["legs"]["left"]["knee_rotation"][1]=.03
            if mode=="length":after["frames"]["2"]["actors"]["actor"]["legs"]["right"]["upper_local_m"]+=.005
            if mode=="extra_frame":after["frames"]["999"]=after["frames"]["1"]
            if mode=="cut":after["cuts"]=[[1,"unknown"]]
            with self.subTest(mode=mode),self.assertRaises(RuntimeError):
                compare(after=after)

    def test_native_programs_parse_and_use_only_actual_pose_ik(self):
        compile(PLANTAR_CORRECTION_BUILD,"native_plantar_bake.py","exec")
        compile(PLANTAR_CORRECTION_SNAPSHOT,"native_independent_snapshot.py","exec")
        self.assertIn("turn_bone",PLANTAR_CORRECTION_BUILD)
        self.assertIn("rig.pose.bones",PLANTAR_CORRECTION_BUILD)
        self.assertIn("geom_points",PLANTAR_CORRECTION_BUILD)
        self.assertIn("bpy.ops.wm.save_as_mainfile",PLANTAR_CORRECTION_BUILD)
        self.assertNotIn("actor.keyframe_insert(",PLANTAR_CORRECTION_BUILD)
        self.assertNotIn("bpy.ops.wm.save_as_mainfile",PLANTAR_CORRECTION_SNAPSHOT)


if __name__=="__main__":
    unittest.main()
