"""Native-BVH floor contact evidence, sloped triangle and refusal tests."""
import unittest
from backend.nvp_surface_bvh import check_native_bvh_evidence,NATIVE_BVH_SURFACE_SCRIPT


def package():
    return {"plantar_correction":{"approval_sha":"a"*64},
            "plantar":{"approval_sha":"b"*64,
                       "plan":{"surface":{"object_name":"NVP_FLOOR",
                                          "geometry_sha256":"c"*64},
                               "actors":{"actor":{
                                   "left":{"contact_roles":["toe"]},
                                   "right":{"contact_roles":["toe"]},
                                   "max_gap_m":.02,"max_penetration_m":.002}}}},
            "leg_identity":{"actors":[{"instance_id":"actor",
                                       "asset_sha256":"d"*64}]},
            "foot_lock":{"actors":[{"instance_id":"actor",
                                    "config":{"left":{"contact_windows":[[1,2]]},
                                              "right":{"contact_windows":[[3,4]]}}}]}}


def hit(gap,normal_z=1):
    return {"status":"measured","signed_gravity_gap_m":gap,
            "surface_normal_world":[0,0,normal_z],
            "surface_world_m":[0,0,0],"triangle_index":3}

def observation():
    tests={"flat_above":hit(.012),"flat_below":hit(-.009),
           "slope_above":hit(.014,.9781476),"slope_below":hit(-.011,.9781476),
           "slope_outside":{"status":"unsupported_no_surface"},
           "steep_refused":{"status":"unsupported_slope","normal_up":.34}}
    return {
        "format":"nvp.surface.bvh.observation.v1",
        "foot_correction_sha":"a"*64,"plantar_sha":"b"*64,
        "floor_sha":"c"*64,"self_tests":tests,
        "actors":{"actor":{"asset_sha256":"d"*64,
                           "sides":{"left":[{"frame":i,"active_roles":{"toe":hit(.001)}}
                                            for i in [1,2]],
                                    "right":[{"frame":i,"active_roles":{"toe":hit(.0015)}}
                                             for i in [3,4]]}}}
    }

class NativeBVHAudit(unittest.TestCase):
    def test_supported_flat_and_sloped_support_and_real_bilateral_foot(self):
        answer=check_native_bvh_evidence(observation(),package())
        self.assertEqual(answer["status"],"passed_real_character_bvh_geometry_only")
        self.assertEqual(answer["real_active_contact_marker_samples"],4)
        self.assertTrue(answer["slope_queries_verified"])
        self.assertFalse(answer["anatomically_verified_plantar_foot"])

    def test_refuse_forged_or_ambiguous_surface_or_contact(self):
        cases=("wrong_approval","altered_floor","flat_wrong","slope_wrong",
               "outside_passes","steep_passes","source_wrong","frame_missing",
               "sole_gap","unsupported_real_marker","nonfinite","no_right")
        for mode in cases:
            r=observation()
            if mode=="wrong_approval":r["foot_correction_sha"]="X"*64
            if mode=="altered_floor":r["floor_sha"]="?"*64
            if mode=="flat_wrong":r["self_tests"]["flat_above"]["signed_gravity_gap_m"]=-.25
            if mode=="slope_wrong":r["self_tests"]["slope_below"]["surface_normal_world"]=[0,0,.2]
            if mode=="outside_passes":r["self_tests"]["slope_outside"]["status"]="measured"
            if mode=="steep_passes":r["self_tests"]["steep_refused"]["status"]="measured"
            if mode=="source_wrong":r["actors"]["actor"]["asset_sha256"]="0"*64
            if mode=="frame_missing":r["actors"]["actor"]["sides"]["left"].pop()
            if mode=="sole_gap":r["actors"]["actor"]["sides"]["right"][0]["active_roles"]["toe"]["signed_gravity_gap_m"]=.15
            if mode=="unsupported_real_marker":
                r["actors"]["actor"]["sides"]["left"][0]["active_roles"]["toe"]={"status":"unsupported_no_surface"}
            if mode=="nonfinite":
                r["actors"]["actor"]["sides"]["right"][1]["active_roles"]["toe"]["signed_gravity_gap_m"]=float("nan")
            if mode=="no_right":del r["actors"]["actor"]["sides"]["right"]
            with self.subTest(mode=mode),self.assertRaises((RuntimeError,ValueError)):
                check_native_bvh_evidence(r,package())

    def test_fixed_native_bvh_uses_real_triangles_not_proxy_aabb(self):
        compile(NATIVE_BVH_SURFACE_SCRIPT,"native_bvh_surface.py","exec")
        self.assertIn("BVHTree.FromPolygons",NATIVE_BVH_SURFACE_SCRIPT)
        self.assertIn("mesh.calc_loop_triangles()",NATIVE_BVH_SURFACE_SCRIPT)
        self.assertIn("tree.ray_cast(",NATIVE_BVH_SURFACE_SCRIPT)
        self.assertIn("ev.to_mesh()",NATIVE_BVH_SURFACE_SCRIPT)
        self.assertNotIn("bpy.ops.wm.save_as_mainfile",NATIVE_BVH_SURFACE_SCRIPT)
        self.assertNotIn("keyframe_insert(",NATIVE_BVH_SURFACE_SCRIPT)

if __name__=="__main__":unittest.main()
