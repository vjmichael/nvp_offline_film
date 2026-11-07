"""Batch 3: real frozen USD surface roughness/metallic, not guessed colors."""
from __future__ import annotations

import unittest
import numpy as np
from pxr import UsdShade
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_data_av_visual import visual_state
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster


class NativeUSDMaterialFidelityTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.original={"base_color_rgb":[0.25,0.6,0.8],
                       "roughness":0.18,"metallic":0.86}
        self.material=self.assets.publish(
            self.pid,"BoundMetalMat",shape="cube",size_m=2.,
            preview_material=self.original)
        self.scene.publish(
            self.pid,"MaterialScene",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/Actor","asset_id":"BoundMetalMat",
                "asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"MaterialShots",scene_id="MaterialScene",
            scene_revision=1,duration_tick=str(fixture.T),
            shots=[{"shot_id":"MetalShot","camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(fixture.T),
                    "pattern":"continuous"}])
        self.take=self.takes.freeze(
            self.pid,"MetalTake",scene_id="MaterialScene",
            scene_revision=1,timeline_id="MaterialShots",
            timeline_revision=1,sample_ticks=[0],
            creator_event="director_confirms")

    def test_author_real_usd_shader_and_native_linear_review(self):
        source,layer=self.assets.open(self.pid,"BoundMetalMat",1)
        self.assertEqual(source["data"]["preview_material"][
            "base_color_rgb"],self.original["base_color_rgb"])
        original,stage=self.scene.open(self.pid,"MaterialScene",1)
        material=UsdShade.MaterialBindingAPI(
            stage.GetPrimAtPath("/World/Actor/Geometry")).ComputeBoundMaterial()[0]
        self.assertTrue(material)
        shader=UsdShade.Shader(
            stage.GetPrimAtPath("/World/Actor/Material/PreviewSurface"))
        self.assertEqual(shader.GetIdAttr().Get(),"UsdPreviewSurface")
        self.assertAlmostEqual(float(shader.GetInput("roughness").Get()),.18,4)
        self.assertAlmostEqual(float(shader.GetInput("metallic").Get()),.86,4)
        snap=self.state.evaluate(
            self.pid,"MaterialScene",1,"MaterialShots",1,tick=0)
        view=visual_state(self.index,self.pid,snap)
        actor=next(o for o in view["objects"] if o["path"]=="/World/Actor")
        self.assertEqual(actor["source_material"]["format"],
                         "nvp.original_usd_preview_surface.v1")
        self.assertEqual(actor["source_material"]["roughness"],.18)
        self.assertEqual(actor["source_material"]["metallic"],.86)
        pixels,audit=NativeSceneLinearRaster(self.index).render(
            self.pid,"MetalTake",self.take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertGreater(float(pixels[:,:,:3].max()),0)
        self.assertEqual(pixels.dtype,np.float32)
        self.assertTrue(audit["usd_roughness_metallic_microfacet_evaluated"])
        self.assertFalse(audit["ggx_microfacet_preview_calibrated"])
        self.assertEqual(self.index.read_revision(
            self.pid,"MaterialScene",1)["document_sha256"],
            original["document_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid,"MetalTake",1)["document_sha256"],
            self.take["document_sha256"])

    def test_revisions_do_not_change_old_authored_material(self):
        changed={"base_color_rgb":[.9,.1,.1],
                 "roughness":.95,"metallic":.0}
        self.assets.publish(
            self.pid,"BoundMetalMat",shape="cube",size_m=2.,
            preview_material=changed,expected_revision=1)
        self.assertEqual(self.assets.open(
            self.pid,"BoundMetalMat",1)[0]["data"]["preview_material"][
            "base_color_rgb"],self.original["base_color_rgb"])
        self.assertEqual(self.assets.open(
            self.pid,"BoundMetalMat",2)[0]["data"]["preview_material"][
            "base_color_rgb"],changed["base_color_rgb"])
        self.assertEqual(self.takes.verify_take(
            self.pid,"MetalTake")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        for bad in (
            {"base_color_rgb":[.1,.1,.1],"roughness":2,"metallic":0},
            {"base_color_rgb":[.1,.1,float("nan")],
             "roughness":.2,"metallic":.2},
            {"base_color_rgb":[.1,.1,.1],"roughness":.2,"metallic":0,
             "untrusted_texture_path":"file:///tmp/asset.png"},
        ):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    self.assets.publish(
                        self.pid,"BadMaterial",shape="cube",
                        size_m=2.,preview_material=bad)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"BadMaterial",1)


if __name__=="__main__":unittest.main()
