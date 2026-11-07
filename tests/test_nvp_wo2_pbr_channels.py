"""WO2 genuine multi-channel USD/MaterialX original PBR source regression."""
from io import BytesIO
import unittest
from PIL import Image
from pxr import Usd,UsdShade

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_data_av_visual import visual_state
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster


class OriginalPBRChannelAcceptance(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)

    @staticmethod
    def png(rgb):
        buffer=BytesIO()
        Image.new("RGB",(2,2),rgb).save(buffer,format="PNG")
        return buffer.getvalue()

    def publish(self,*,revision=0,maps=None):
        return self.assets.publish(
            self.pid,"pbr_mesh",shape="mesh",size_m=2.,
            expected_revision=revision,
            points=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={
                "base_color_rgb":[.8,.7,.6],
                "roughness":.5,"metallic":0.},
            texture_png=self.png((180,150,120)),
            pbr_maps_png=maps)

    def test_all_four_original_channels_have_verified_usd_graphs(self):
        maps={
            "roughness":self.png((64,64,64)),
            "metallic":self.png((200,200,200)),
            "emission":self.png((18,60,220)),
            "normal":self.png((128,128,255)),
        }
        original=self.publish(maps=maps)
        rec,layer=self.assets.open(self.pid,"pbr_mesh",1)
        descriptors=rec["data"]["preview_material"]["pbr_maps"]
        self.assertEqual(set(descriptors),set(maps))
        stage=Usd.Stage.Open(layer)
        preview=UsdShade.Shader(stage.GetPrimAtPath(
            "/Asset/Material/PreviewSurface"))
        for channel,expected in (
            ("roughness","roughness"),("metallic","metallic"),
            ("emission","emissiveColor"),("normal","normal"),
        ):
            shader=UsdShade.Shader(stage.GetPrimAtPath(
                "/Asset/Material/Map_"+channel.capitalize()))
            self.assertEqual(shader.GetIdAttr().Get(),"UsdUVTexture")
            self.assertEqual(str(shader.GetInput("file").GetAttr().Get().path),
                             descriptors[channel]["usd_asset_path"])
            source=preview.GetInput(expected).GetConnectedSource()
            self.assertEqual(str(source[0].GetPrim().GetPath()),
                             str(shader.GetPrim().GetPath()))
            mtlx=UsdShade.Shader(stage.GetPrimAtPath(
                "/Asset/Material/MtlxMap_"+channel.capitalize()))
            self.assertIn(mtlx.GetIdAttr().Get(),
                          ("ND_image_float","ND_image_color3"))
            if channel=="normal":
                self.assertEqual(list(shader.GetInput(
                    "scale").GetAttr().Get()),[2.,2.,2.,1.])
                self.assertEqual(list(shader.GetInput(
                    "bias").GetAttr().Get()),[-1.,-1.,-1.,0.])
        self.scene.publish(
            self.pid,"pbr_scene",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/Actor","asset_id":"pbr_mesh",
                "asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"pbr_shots",scene_id="pbr_scene",scene_revision=1,
            duration_tick=str(fixture.T),shots=[{
                "shot_id":"pbr","camera_path":"/World/Camera",
                "start_tick":"0","end_tick":str(fixture.T),
                "pattern":"continuous"}])
        take=self.takes.freeze(
            self.pid,"pbr_take",scene_id="pbr_scene",scene_revision=1,
            timeline_id="pbr_shots",timeline_revision=1,
            sample_ticks=[0],creator_event="director_confirms")
        snap=self.state.evaluate(
            self.pid,"pbr_scene",1,"pbr_shots",1,tick=0)
        view=visual_state(self.index,self.pid,snap)
        actor=next(o for o in view["objects"] if o["path"]=="/World/Actor")
        material=actor["source_material"]
        self.assertEqual(set(material["pbr_map_transports"]),set(maps))
        pixels,receipt=NativeSceneLinearRaster(self.index).render(
            self.pid,"pbr_take",take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertGreater(float(pixels[:,:,:3].max()),0.)
        self.assertGreater(receipt["source_uv_texture_rasterized_triangles"],0)
        self.publish(revision=1,maps={
            **maps,"roughness":self.png((255,255,255))})
        old=self.assets.open(self.pid,"pbr_mesh",1)[0]
        later=self.assets.open(self.pid,"pbr_mesh",2)[0]
        self.assertEqual(old["document_sha256"],original["document_sha256"])
        self.assertNotEqual(later["document_sha256"],original["document_sha256"])

    def test_hostile_channels_and_untrusted_map_inputs_fail_closed(self):
        png=self.png((128,128,255))
        for bad in (
            {"arbitrary_shader":png},
            {"normal":b"not_png"},
            {"roughness":png,"metallic":png,
             "normal":png,"emission":png,"extra":png},
        ):
            with self.subTest(bad=list(bad)):
                with self.assertRaises((ValueError,RuntimeError)):
                    self.publish(maps=bad)
        with self.assertRaises(ValueError):
            self.assets.publish(
                self.pid,"pbr_without_uv",shape="mesh",size_m=2.,
                points=[[0,0,0],[1,0,0],[0,1,0]],
                triangles=[[0,1,2]],
                preview_material={"base_color_rgb":[1,1,1],
                                  "roughness":.5,"metallic":.0},
                pbr_maps_png={"normal":png})


if __name__=="__main__":
    unittest.main()
