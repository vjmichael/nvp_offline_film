"""Original GLB hierarchy audit and independently measured foot/terrain numeric gates.

These fixtures are public synthetic and are explicitly not professional rights,
actual Blender-deformed foot measurements or private film-release acceptance.
"""
import json
import struct
import unittest

from backend.nvp_p1f_full_body_retarget import (
    ROLES, audit_full_body_rest_pose, audit_measured_foot_contact,
)
from test_character_assets import synthetic_glb

ROLE_MAP = {
    "hips": "hips", "spine": "spine", "head": "head",
    "upper_arm_l": "arm_left", "upper_arm_r": "arm_right",
    "thigh_l": "leg_left", "shin_l": "shin_left", "foot_l": "foot_left",
    "thigh_r": "leg_right", "shin_r": "shin_right", "foot_r": "foot_right",
}


def full_body_glb(mutation=None):
    """Upgrade the 7-joint synthetic GLB to a genuine 11-node parented rest hierarchy."""
    original = synthetic_glb()
    size = struct.unpack_from("<I", original, 12)[0]
    doc = json.loads(original[20:20+size])
    raw = bytearray(original[20+size+8:])
    nodes = doc["nodes"]
    def pose(i, xyz, children=None):
        nodes[i]["translation"] = xyz
        if children:
            nodes[i]["children"] = children
    pose(0, [0., 1., 0.], [1, 5, 6])
    pose(1, [0., .4, 0.], [2, 3, 4])
    pose(2, [0., .3, 0.])
    pose(3, [-.4, 0., 0.])
    pose(4, [.4, 0., 0.])
    pose(5, [-.16, -.45, 0.], [8])
    pose(6, [.16, -.45, 0.], [10])
    nodes.extend([
        {"name": "shin_left", "translation": [0., -.4, 0.], "children": [9]},
        {"name": "foot_left", "translation": [0., -.13, .16]},
        {"name": "shin_right", "translation": [0., -.4, 0.], "children": [11]},
        {"name": "foot_right", "translation": [0., -.13, .16]},
    ])
    doc["skins"][0]["joints"] += [8, 9, 10, 11]
    doc["scenes"][0]["nodes"] = [0, 7]
    matrix_accessor = doc["skins"][0]["inverseBindMatrices"]
    matrix_view = doc["accessors"][matrix_accessor]["bufferView"]
    doc["accessors"][matrix_accessor]["count"] = 11
    doc["bufferViews"][matrix_view]["byteLength"] += 16 * 4 * 4
    raw.extend(struct.pack("<64f", *([1.] * 64)))
    # Replace the synthetic all-ones matrices with authentic inverse rest
    # transforms, matching the exact source hierarchy and mesh bind frame.
    rest_world = {
        0: (0., 1., 0.),
        1: (0., 1.4, 0.),
        2: (0., 1.7, 0.),
        3: (-.4, 1.4, 0.),
        4: (.4, 1.4, 0.),
        5: (-.16, .55, 0.),
        6: (.16, .55, 0.),
        8: (-.16, .15, 0.),
        9: (-.16, .02, .16),
        10: (.16, .15, 0.),
        11: (.16, .02, .16),
    }
    ibm_start = doc["bufferViews"][matrix_view]["byteOffset"]
    for ordinal, joint in enumerate(doc["skins"][0]["joints"]):
        x, y, z = rest_world[joint]
        mat = [1., 0., 0., 0.,
               0., 1., 0., 0.,
               0., 0., 1., 0.,
               -x, -y, -z, 1.]
        struct.pack_into("<16f", raw, ibm_start+ordinal*64, *mat)
    doc["buffers"][0]["byteLength"] = len(raw)
    if mutation:
        mutation(doc)
    data = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    data += b" " * (-len(data) % 4)
    packet = (struct.pack("<II", len(data), 0x4e4f534a) + data +
              struct.pack("<II", len(raw), 0x004e4942) + raw)
    return b"glTF" + struct.pack("<II", 2, 12+len(packet)) + packet


def measured_frame(t, left_stance, right_stance, left_x=-.16, right_x=.16):
    def foot(x, stance):
        z = .004 if stance else .10
        return {"sole": [x, 0., z], "ground": [x, 0., 0.],
                "normal": [0., 0., 1.], "stance": stance}
    return {"frame": t, "feet": {
        "left": foot(left_x, left_stance),
        "right": foot(right_x, right_stance),
    }}


class FullBodyRestAndFootTests(unittest.TestCase):
    def test_real_glb_hierarchy_has_bounded_bone_axes_and_no_fake_render_proof(self):
        result = audit_full_body_rest_pose(full_body_glb(), ROLE_MAP)
        self.assertEqual(set(result["role_to_joint"]), set(ROLES))
        self.assertEqual(len(result["axis_corrections"]), 10)
        self.assertGreater(result["axis_corrections"]["shin_l"]["bone_length_m"], .3)
        self.assertTrue(result["glb_inverse_bind_rest_verified"])
        self.assertEqual(result["source_to_stage_axes"], "glTF_Yup_to_OpenUSD_Zup_(x,-z,y)")
        self.assertAlmostEqual(result["source_joint_positions_m"]["foot_l"][2], .02)
        self.assertFalse(result["full_body_deformation_verified"])
        self.assertFalse(result["usd_rest_pose_equivalence_verified"])
        self.assertFalse(result["rendered_performance_verified"])
        for axis in result["axis_corrections"].values():
            self.assertAlmostEqual(sum(n*n for n in axis["correction_wxyz"]), 1., places=6)

    def test_reject_incomplete_parented_mirrored_crossed_and_zero_length_bones(self):
        cases = [
            (lambda d: d["scenes"][0].update({"nodes": [7]})),
            (lambda d: d["nodes"][6].update({"translation": [-.16, -.45, 0.]})),
            (lambda d: d["nodes"][8].update({"translation": [0., 0., 0.]})),
            (lambda d: d["nodes"][2].update({"children": [0]})),
            (lambda d: d["nodes"][3].update({"scale": [-1, 1, 1]})),
            (lambda d: d["nodes"][6].update({"children": [10, 9]})),
        ]
        for edit in cases:
            with self.subTest(edit=cases.index(edit)):
                with self.assertRaises(ValueError):
                    audit_full_body_rest_pose(full_body_glb(edit), ROLE_MAP)
        with self.assertRaises(ValueError):
            audit_full_body_rest_pose(full_body_glb(), {"hips": "hips"})
        with self.assertRaises(ValueError):
            audit_full_body_rest_pose(full_body_glb(), ROLE_MAP,
                                      meters_per_source_unit=float("nan"))
        with self.assertRaises(ValueError):
            audit_full_body_rest_pose(synthetic_glb(), ROLE_MAP)
        # Source still passes glTF structural inspection: actual inverse
        # bind floats disagree with rest pose, so full-body proof refuses.
        wrong = bytearray(full_body_glb())
        json_len = struct.unpack_from("<I", wrong, 12)[0]
        doc = json.loads(wrong[20:20+json_len])
        acc = doc["accessors"][doc["skins"][0]["inverseBindMatrices"]]
        start = (20 + json_len + 8 +
                 doc["bufferViews"][acc["bufferView"]]["byteOffset"])
        struct.pack_into("<f", wrong, start+12*4, 0.5)
        with self.assertRaisesRegex(ValueError, "Inverse binds"):
            audit_full_body_rest_pose(bytes(wrong), ROLE_MAP)

    def test_original_frame_sole_ground_slope_and_stance_validation(self):
        samples = [
            measured_frame(10, True, False),
            measured_frame(11, True, True),
            measured_frame(12, False, True),
            measured_frame(13, False, False),
        ]
        result = audit_measured_foot_contact(
            samples, ground_source_sha256="f"*64)
        self.assertEqual(result["first_frame"], 10)
        self.assertEqual(result["stance_frames"], {"left": 2, "right": 2})
        self.assertTrue(result["numeric_contact_contract_passed"])
        self.assertFalse(result["blender_evaluated_mesh_verified"])
        self.assertFalse(result["private_worker_authorized"])

        from copy import deepcopy
        broken = deepcopy(samples)
        broken[1]["feet"]["left"]["sole"][0] += .1
        with self.assertRaisesRegex(ValueError, "slides"):
            audit_measured_foot_contact(broken, ground_source_sha256="f"*64)
        broken = deepcopy(samples)
        broken[1]["feet"]["left"]["sole"][2] = -.03
        with self.assertRaisesRegex(ValueError, "penetrates"):
            audit_measured_foot_contact(broken, ground_source_sha256="f"*64)
        broken = deepcopy(samples)
        broken[2]["feet"]["right"]["sole"][2] = .1
        with self.assertRaisesRegex(ValueError, "hovers"):
            audit_measured_foot_contact(broken, ground_source_sha256="f"*64)
        broken = deepcopy(samples)
        broken[2]["frame"] = 11
        with self.assertRaisesRegex(ValueError, "gapped"):
            audit_measured_foot_contact(broken, ground_source_sha256="f"*64)
        broken = deepcopy(samples)
        broken[1]["feet"]["left"]["normal"] = [0., 0., -1.]
        with self.assertRaisesRegex(ValueError, "normal"):
            audit_measured_foot_contact(broken, ground_source_sha256="f"*64)
        with self.assertRaises(ValueError):
            audit_measured_foot_contact(samples, ground_source_sha256="bad")


if __name__ == "__main__":
    unittest.main()
