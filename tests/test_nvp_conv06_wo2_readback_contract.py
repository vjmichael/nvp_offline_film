"""CONV-01/06: exact historical WO2 source validators, not renderer admission.

Preserve native USD source-only material/texture contracts across branch
convergence. This does not authorize the deliberately restricted legacy
asset publisher, a model worker, external image path, or a film master.
"""
from __future__ import annotations

import unittest
from pxr import Usd,UsdGeom,UsdShade

from backend.nvp_wo2_openpbr import (
    author_openpbr_scalar,verify_openpbr_scalar,NODE_ID)
from backend.nvp_wo2_material_slots import normalize_material_slots
from backend.nvp_wo2_pbr_channels import publish_pbr_maps


class OriginalWO2SourceReadback(unittest.TestCase):
    def test_original_openpbr_scalar_reopens_and_rejects_tampered_source(self):
        stage=Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage,"/Asset")
        material=UsdShade.Material.Define(stage,"/Asset/Material")
        rgb=[0.2,0.4,0.6]
        author_openpbr_scalar(
            stage,"/Asset/Material",material,rgb,0.55,0.1)
        self.assertEqual(UsdShade.Shader(
            stage.GetPrimAtPath("/Asset/Material/OpenPBR")
        ).GetIdAttr().Get(),NODE_ID)
        text=stage.GetRootLayer().ExportToString()
        layer=Usd.Stage.CreateInMemory()
        self.assertTrue(layer.GetRootLayer().ImportFromString(text))
        reopened=UsdShade.Material(
            layer.GetPrimAtPath("/Asset/Material"))
        evidence=verify_openpbr_scalar(
            layer,"/Asset/Material",reopened,rgb,0.55,0.1)
        self.assertTrue(evidence["materialx_source_verified"])
        self.assertFalse(evidence["hydra_renderer_parity_proven"])
        source=UsdShade.Shader(
            layer.GetPrimAtPath("/Asset/Material/OpenPBR"))
        source.GetInput("base_metalness").Set(0.9)
        with self.assertRaises(RuntimeError):
            verify_openpbr_scalar(
                layer,"/Asset/Material",reopened,rgb,0.55,0.1)

    def test_original_face_subsets_cannot_overlap_or_escape_source_mesh(self):
        first={
            "faces":[0,1],"base_color_rgb":[0.2,0.4,0.6],
            "roughness":0.5,"metallic":0.0}
        self.assertEqual(
            normalize_material_slots([first],3)[0]["faces"],[0,1])
        for hostile in (
            [{**first,"faces":[0,1,1]}],
            [first,{**first,"faces":[1,2]}],
            [{**first,"faces":[3]}],
            [{**first,"roughness":float("nan")}],
            [{**first,"external_file":"../untrusted.png"}],
        ):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    normalize_material_slots(hostile,3)

    def test_original_pbr_authority_refuses_external_paths_and_unbound_uv(self):
        with self.assertRaises(ValueError):
            publish_pbr_maps(
                None,"not-a-project",{"file":"file:///tmp/a.png"},
                has_uv=True)
        with self.assertRaises(ValueError):
            publish_pbr_maps(
                None,"not-a-project",{"roughness":b"not-an-image"},
                has_uv=False)


if __name__=="__main__":
    unittest.main()
