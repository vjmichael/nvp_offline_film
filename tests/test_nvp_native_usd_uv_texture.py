"""Actual OpenUSD UsdUVTexture + FilmIndex RGB8 PNG source verification.

This tests exact native Film Time, not a fake video texture. No arbitrary
filesystem image path, resolver, FFmpeg or revision of original USD Take.
"""
import io
import unittest

import numpy as np
from PIL import Image
from pxr import UsdShade,UsdGeom
import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_data_av_visual import visual_state
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster


def original_checker():
    image=Image.new("RGB",(8,8))
    for y in range(8):
        for x in range(8):
            image.putpixel((x,y),(255,0,0) if x<4 else (0,255,0))
    out=io.BytesIO()
    image.save(out,format="PNG")
    return out.getvalue()


class OriginalUSDSourceTextureTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.rgb=original_checker()
        self.source={
            "base_color_rgb":[1.,1.,1.],
            "roughness":.7,"metallic":0.,
        }
        self.uvs=[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]
        self.points=[[-1.,-1.,0.],[1.,-1.,0.],
                     [1.,1.,0.],[-1.,1.,0.]]
        self.tris=[[0,1,2],[0,2,3]]
        self.asset=self.assets.publish(
            self.pid,"TexturedMesh",shape="mesh",size_m=2.,
            points=self.points,triangles=self.tris,
            uvs=self.uvs,preview_texture_png=self.rgb,
            preview_material=self.source)
        self.scene.publish(self.pid,"TexturedScene",prims=[
            {"path":"/World/Textured","role":"prop","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,0,5]},
            {"path":"/World/Light","role":"light","position":[0,1,2]},
        ],curves=[],native_schemas=True,asset_bindings=[{
            "path":"/World/Textured","asset_id":"TexturedMesh",
            "asset_revision":1,
        }])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"TexturedShots",scene_id="TexturedScene",
            scene_revision=1,duration_tick=str(fixture.T),
            shots=[{"shot_id":"SourceTextureShot","camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(fixture.T),
                    "pattern":"continuous"}])
        self.take=self.takes.freeze(
            self.pid,"TexturedTake",scene_id="TexturedScene",
            scene_revision=1,timeline_id="TexturedShots",
            timeline_revision=1,sample_ticks=[0],
            creator_event="director_confirms")

    def test_frozen_mesh_has_usd_shader_network_and_linear_uv_image(self):
        reopened,layer=self.assets.open(self.pid,"TexturedMesh",1)
        self.assertEqual(reopened["document_sha256"],
                         self.asset["document_sha256"])
        self.assertEqual(reopened["data"]["uvs"],self.uvs)
        original,stage=self.scene.open(self.pid,"TexturedScene",1)
        shader=UsdShade.Shader(stage.GetPrimAtPath(
            "/World/Textured/Material/BaseColorTexture"))
        reader=UsdShade.Shader(stage.GetPrimAtPath(
            "/World/Textured/Material/SourceUV"))
        self.assertTrue(shader)
        self.assertEqual(shader.GetIdAttr().Get(),"UsdUVTexture")
        self.assertEqual(reader.GetIdAttr().Get(),"UsdPrimvarReader_float2")
        self.assertEqual(shader.GetInput("sourceColorSpace").Get(),"sRGB")
        geometry=stage.GetPrimAtPath("/World/Textured/Geometry")
        uv=UsdGeom.PrimvarsAPI(geometry).GetPrimvar("st").Get()
        self.assertEqual(len(uv),4)
        snap=self.state.evaluate(
            self.pid,"TexturedScene",1,"TexturedShots",1,tick=0)
        actor=next(x for x in visual_state(self.index,self.pid,snap)[
            "objects"] if x["path"]=="/World/Textured")
        self.assertEqual(actor["mesh_uvs"],self.uvs)
        self.assertEqual(actor["source_material"]["source_texture"][
            "blob_sha256"],reopened["data"]["preview_texture"]["blob_sha256"])
        color,receipt=NativeSceneLinearRaster(self.index).render(
            self.pid,"TexturedTake",self.take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertEqual(receipt["verified_original_uv_textured_mesh_count"],1)
        self.assertFalse(receipt["usd_uv_bilinear_linear_srgb_preview_calibrated"])
        self.assertEqual(color.dtype,np.float32)
        # Authored red and green halves must survive exact-time mesh raster.
        self.assertGreater(float(color[:,:,0].max()),0.02)
        self.assertGreater(float(color[:,:,1].max()),0.02)
        self.assertFalse(np.array_equal(color[:,:,0],color[:,:,1]))
        self.assertEqual(self.index.read_revision(
            self.pid,"TexturedTake",1)["document_sha256"],
            self.take["document_sha256"])

    def test_revisions_and_untrusted_image_inputs_fail_closed(self):
        first=self.index.read_revision(
            self.pid,"TexturedMesh",1)["document_sha256"]
        self.assets.publish(
            self.pid,"TexturedMesh",shape="mesh",size_m=2.,
            points=self.points,triangles=self.tris,uvs=self.uvs,
            preview_material=self.source,
            preview_texture_png=self.rgb,expected_revision=1)
        self.assertEqual(self.index.read_revision(
            self.pid,"TexturedMesh",1)["document_sha256"],first)
        self.assertEqual(self.index.read_revision(
            self.pid,"TexturedTake",1)["document_sha256"],
            self.take["document_sha256"])
        for bad in (
            dict(uvs=self.uvs,preview_texture_png=b"NOTPNG"),
            dict(uvs=[[1,2]]*4,preview_texture_png=self.rgb),
            dict(uvs=self.uvs[:-1],preview_texture_png=self.rgb),
            dict(uvs=self.uvs,preview_texture_png="../external.png"),
            dict(uvs=self.uvs,preview_texture_png=None),
        ):
            with self.subTest(bad=repr(bad)[:70]):
                with self.assertRaises(ValueError):
                    self.assets.publish(self.pid,"BadTexture",
                        shape="mesh",size_m=2.,
                        points=self.points,triangles=self.tris,
                        preview_material=self.source,**bad)


if __name__=="__main__":
    unittest.main()
