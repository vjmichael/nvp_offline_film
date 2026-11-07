"""WO2 A–E: source-preserving OpenUSD derived looks and MaterialX parity."""
from io import BytesIO
import unittest
from PIL import Image
from pxr import Usd,UsdShade

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_wo2_presentation_look import (
    OriginalSceneLook,default_look)
from backend.nvp_wo2_derived_usd_look import derived_look_stage


class WO2DerivedUSDLookAcceptance(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        data=BytesIO()
        Image.new("RGB",(2,2),(190,120,50)).save(data,format="PNG")
        png=data.getvalue()
        scalar=BytesIO()
        Image.new("RGB",(2,2),(120,120,120)).save(
            scalar,format="PNG")
        roughness_png=scalar.getvalue()
        self.assets.publish(
            self.pid,"look_mesh",shape="mesh",size_m=2.,
            points=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={"base_color_rgb":[.8,.7,.6],
                              "roughness":.3,"metallic":0.},
            texture_png=png,
            pbr_maps_png={"roughness":roughness_png})
        self.scene.publish(
            self.pid,"look_world",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{
                "path":"/World/Actor","asset_id":"look_mesh",
                "asset_revision":1}])
        self.original,self.stage=self.scene.open(self.pid,"look_world",1)
        self.source_layer=self.stage.GetRootLayer().ExportToString()
        self.look=default_look()
        self.look["materials"]["/World/Actor"]={
            "opacity":.85,"transmission":.65,
            "ior":1.48,"thickness_m":.02}
        self.look["textures"]["transforms"]["/World/Actor"]={
            "roughness":{"repeat":[2,3],"offset":[.25,.1],
                         "rotation_deg":32.},
            "base_color":{"repeat":[1.5,1.5],"offset":[.05,.15],
                          "rotation_deg":0.},
        }

    def test_bound_physical_material_and_both_uv_contexts_are_derived(self):
        look=OriginalSceneLook(self.index).publish(
            self.pid,"VerifiedLook",scene_id="look_world",
            scene_revision=1,scene_sha256=self.original["document_sha256"],
            look=self.look,approve=lambda _:True)
        self.assertEqual(look["status"],"PRESENTATION_REVISION_APPROVED")
        derived,evidence=derived_look_stage(
            self.stage,self.original,self.look)
        self.assertTrue(evidence["original_source_unchanged"])
        self.assertEqual(evidence["uv_transform_count"],2)
        self.assertGreaterEqual(evidence["material_count"],1)
        self.assertTrue(derived.GetPrimAtPath(
            "/World/WO2PresentationRig/Key"))
        self.assertTrue(derived.GetPrimAtPath(
            "/World/WO2PresentationRig/Environment"))
        shaders=[UsdShade.Shader(prim) for prim in derived.Traverse()
                 if prim.IsA(UsdShade.Shader)]
        pbr=next(node for node in shaders if node.GetIdAttr().Get()==
                 "ND_open_pbr_surface_surfaceshader")
        self.assertAlmostEqual(
            float(pbr.GetInput("transmission_weight").GetAttr().Get()),.65,5)
        self.assertAlmostEqual(
            float(pbr.GetInput("specular_ior").GetAttr().Get()),1.48,5)
        transforms=[node for node in shaders if node.GetIdAttr().Get()==
                    "UsdTransform2d"]
        mtlx=[node for node in shaders if node.GetIdAttr().Get()==
              "ND_UsdTransform2d"]
        self.assertEqual(len(transforms),2)
        self.assertEqual(len(mtlx),2)
        self.assertEqual(self.stage.GetRootLayer().ExportToString(),
                         self.source_layer)
        original_again,_=self.scene.open(self.pid,"look_world",1)
        self.assertEqual(original_again["document_sha256"],
                         self.original["document_sha256"])

    def test_invalid_original_shader_target_fails_instead_of_guessing(self):
        self.look["textures"]["transforms"]["/World/Actor"]["normal"]={
            "repeat":[1,1],"offset":[0,0],"rotation_deg":0}
        with self.assertRaises(RuntimeError):
            derived_look_stage(self.stage,self.original,self.look)
        self.assertEqual(self.stage.GetRootLayer().ExportToString(),
                         self.source_layer)


if __name__=="__main__":
    unittest.main()
