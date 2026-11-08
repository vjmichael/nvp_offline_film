"""WO3 bounded verdict tests only: these receipts are synthetic and do NOT
constitute real Hydra or calibrated color execution evidence. The mandatory
real Storm job is tests/test_nvp_wo3_real_hydra_color.py.
"""
import unittest

from backend.nvp_wo3_hydra_color_fidelity import (
    verify_relative_hydra_swatch_response)


def sample(color, *, scene, image, context="dual", isolated=False):
    return {
        "status":"HYDRA_FRAME_RENDERED",
        "real_independent_frame_rendered":True,
        "derived_source_scope":True,
        "physical_display_calibrated":False,
        "renderer":"Storm",
        "material_context_probe":context,
        "renderer_executable_sha256":"1"*64,
        "rendered_rgb_sha256":image*64,
        "scene_document_sha256":scene*64,
        "derived_render_layer_sha256":"e"*64,
        "rendered_center_patch_pixels":4096,
        "rendered_center_patch_mean_rgb8":color,
        "materialx_only_terminal_isolated":isolated,
    }


class RelativeHydraColorVerdictContract(unittest.TestCase):
    def setUp(self):
        self.red=sample([210.,10.,10.],scene="a",image="c")
        self.blue=sample([10.,10.,210.],scene="b",image="d")

    def test_two_distinct_native_receipts_support_only_relative_color(self):
        result=verify_relative_hydra_swatch_response(self.red,self.blue)
        self.assertTrue(result["dual_context_relative_color_response_verified"])
        self.assertFalse(result["materialx_openpbr_shading_parity_verified"])
        self.assertFalse(result["absolute_reference_color_accuracy_verified"])
        self.assertFalse(result["theatrical_color_accepted"])
        self.assertGreater(
            result["between_rendered_swatches_delta_e76_assuming_srgb"],25)

    def test_context_isolation_requires_explicit_both_sides(self):
        self.red.update(material_context_probe="mtlx_only",
                        materialx_only_terminal_isolated=True)
        self.blue.update(material_context_probe="mtlx_only",
                         materialx_only_terminal_isolated=True)
        verdict=verify_relative_hydra_swatch_response(
            self.red,self.blue,required_context="mtlx_only")
        self.assertTrue(verdict["materialx_only_relative_color_response_verified"])
        self.blue["materialx_only_terminal_isolated"]=False
        with self.assertRaises(AssertionError):
            verify_relative_hydra_swatch_response(
                self.red,self.blue,required_context="mtlx_only")

    def test_refuse_grayscale_wrong_renderer_and_false_pixel_claim(self):
        cases=[
            ("grayscale",{"rendered_center_patch_mean_rgb8":[100,100,100]}),
            ("renderer",{"renderer":"Embree"}),
            ("no image",{"real_independent_frame_rendered":False}),
            ("no source",{"derived_source_scope":False}),
            ("no hash",{"derived_render_layer_sha256":None}),
        ]
        for name,patch in cases:
            with self.subTest(case=name):
                damaged=dict(self.red,**patch)
                with self.assertRaises(AssertionError):
                    verify_relative_hydra_swatch_response(damaged,self.blue)

    def test_refuse_pixel_replay_and_unpinned_different_renderer(self):
        with self.assertRaises(AssertionError):
            verify_relative_hydra_swatch_response(
                self.red,dict(self.blue,rendered_rgb_sha256="c"*64))
        with self.assertRaises(AssertionError):
            verify_relative_hydra_swatch_response(
                self.red,dict(self.blue,renderer_executable_sha256="2"*64))


if __name__=="__main__":
    unittest.main()
