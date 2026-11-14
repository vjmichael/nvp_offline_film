"""Finite full-body twist/bone-axis review, no synthetic render/rights claim."""
import math
import unittest

from backend.nvp_p1f_bone_axis_motion import retarget_reviewed_full_body_motion
from backend.nvp_p1f_full_body_retarget import ROLES, audit_full_body_rest_pose
from test_nvp_p1f_full_body_retarget_native import full_body_glb, ROLE_MAP

IDENTITY = [1., 0., 0., 0.]


class FullBodyBoneAxisMotionMathTests(unittest.TestCase):
    def setUp(self):
        self.rest = audit_full_body_rest_pose(full_body_glb(), ROLE_MAP)
        self.source_rest = {role: list(IDENTITY) for role in ROLES}
        self.target_rest = {role: list(IDENTITY) for role in ROLES}
        self.motion = {role: list(IDENTITY) for role in ROLES}

    def apply(self):
        return retarget_reviewed_full_body_motion(
            self.rest,
            original_actor_id="ACT_OriginalLead",
            original_actor_document_sha256="a"*64,
            original_take_document_sha256="b"*64,
            original_source_tick=7056000000,
            source_rest_wxyz=self.source_rest,
            target_rest_wxyz=self.target_rest,
            source_motion_delta_wxyz=self.motion,
            original_root_translation_m=[0., 0., 1.])

    def test_correct_full_body_identity_and_immutable_original_motion_hash(self):
        result = self.apply()
        self.assertEqual(set(result["retargeted_delta_wxyz"]), set(ROLES))
        self.assertEqual(result["retargeted_delta_wxyz"]["foot_l"], IDENTITY)
        self.assertEqual(result["source_tick"], 7056000000)
        self.assertEqual(len(result["source_evidence_sha256"]), 64)
        self.assertEqual(self.apply(), result)
        self.assertFalse(result["original_usd_rest_and_animation_independently_verified"])
        self.assertFalse(result["actual_mesh_deformation_verified"])
        self.assertFalse(result["worker_authorized"])

    def test_bone_rest_twist_rotates_motion_axis_without_changing_angle(self):
        c = math.sqrt(.5)
        # Source arm rest frame identity, target rest rotated 90 degrees Z.
        self.target_rest["upper_arm_l"] = [c, 0., 0., c]
        self.motion["upper_arm_l"] = [c, c, 0., 0.]  # source X rotation
        result = self.apply()
        q = result["retargeted_delta_wxyz"]["upper_arm_l"]
        self.assertAlmostEqual(q[0], c, places=8)
        self.assertAlmostEqual(q[1], 0., places=8)
        self.assertAlmostEqual(abs(q[2]), c, places=8)
        self.assertAlmostEqual(q[3], 0., places=8)
        self.assertNotEqual(q, self.motion["upper_arm_l"])
        self.assertEqual(result["retargeted_delta_wxyz"]["foot_r"], IDENTITY)

    def test_reject_missing_role_nonunit_twist_nan_tick_and_unreviewed_rest(self):
        self.motion.pop("thigh_l")
        with self.assertRaisesRegex(ValueError, "11 roles"):
            self.apply()
        self.motion["thigh_l"] = [1., 0., 0., 0.]
        self.target_rest["head"] = [2., 0., 0., 0.]
        with self.assertRaisesRegex(ValueError, "normalized"):
            self.apply()
        self.target_rest["head"] = [1., 0., 0., 0.]
        self.motion["head"] = [float("nan"), 0., 0., 0.]
        with self.assertRaisesRegex(ValueError, "finite"):
            self.apply()
        self.motion["head"] = [1., 0., 0., 0.]
        self.rest["glb_inverse_bind_rest_verified"] = False
        with self.assertRaisesRegex(ValueError, "complete GLB"):
            self.apply()


if __name__ == "__main__":
    unittest.main()
