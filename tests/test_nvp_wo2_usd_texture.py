"""WO2 original USD PNG shader graph, blob authority and raster integration."""
from __future__ import annotations

from io import BytesIO
from PIL import Image
from pxr import Usd, UsdShade
import unittest
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_native_usd_texture import (
    decode_png, publish_texture, verified_texture, texture_transport)
from backend.nvp_data_av_visual import visual_state
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster


class WO2NativeTextureTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)

    def _png(self, rgb=(255,32,16)):
        image=Image.new("RGB",(2,2),rgb)
        buff=BytesIO()
        image.save(buff,format="PNG")
        return buff.getvalue()

    def _mesh(self, *, texture, revision=0):
        return self.assets.publish(
            self.pid,"textured_mesh",shape="mesh",size_m=2.,
            expected_revision=revision,
            points=[[-1.,-1.,0.],[1.,-1.,0.],[1.,1.,0.],[-1.,1.,0.]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0.,0.],[1.,0.],[1.,1.],[0.,1.]],
            preview_material={"base_color_rgb":[.8,.7,.6],
                              "roughness":.45,"metallic":.1},
            texture_png=texture)

    def test_disposable_materialx_resolver_keeps_original_usd_frozen(self):
        from pathlib import Path
        from backend.nvp_wo2_materialx_resolver import resolved_materialx_probe
        original_png=self._png()
        asset=self._mesh(texture=original_png)
        rec,layer=self.assets.open(self.pid,"textured_mesh",1)
        original=Usd.Stage.Open(layer)
        before=original.GetRootLayer().ExportToString()
        descriptor=rec["data"]["preview_material"]["texture"]
        transient_path=None
        with resolved_materialx_probe(
                self.index,self.pid,original,[descriptor]) as (stage,evidence):
            self.assertFalse(evidence["original_layer_mutated"])
            self.assertFalse(evidence["independent_hydra_render_accepted"])
            node=UsdShade.Shader(stage.GetPrimAtPath(
                "/Asset/Material/MtlxImage"))
            transient_path=Path(node.GetInput("file").GetAttr().Get().path)
            self.assertTrue(transient_path.is_file())
            self.assertEqual(transient_path.read_bytes(),original_png)
            source=UsdShade.Shader(original.GetPrimAtPath(
                "/Asset/Material/MtlxImage"))
            self.assertEqual(str(source.GetInput("file").GetAttr().Get().path),
                             descriptor["usd_asset_path"])
        self.assertFalse(transient_path.exists())
        self.assertEqual(original.GetRootLayer().ExportToString(),before)
        self.assertEqual(self.index.read_revision(
            self.pid,"textured_mesh",1)["document_sha256"],
            asset["document_sha256"])
        with self.assertRaises((KeyError,RuntimeError)):
            resolved_materialx_probe(
                self.index,self.pid,original,[
                    {**descriptor,"sha256":"0"*64,
                     "usd_asset_path":"nvp-blob://texture/"+"0"*64}
                ]).__enter__()

    def test_stable_blob_and_genuine_usd_texture_connections(self):
        png=self._png()
        self._mesh(texture=png)
        rec,layer=self.assets.open(self.pid,"textured_mesh",1)
        mat=rec["data"]["preview_material"]
        desc=mat["texture"]
        self.assertEqual(verified_texture(self.index,self.pid,desc)[0],png)
        packet=texture_transport(self.index,self.pid,desc)
        self.assertEqual(packet["sha256"],desc["sha256"])
        self.assertTrue(packet["png_base64"].startswith("iVBORw0KGgo"))
        self.assertEqual(packet["gpu_reference_uv"],
                         [[.125,.125],[.875,.125],[.125,.875],[.875,.875]])
        self.assertEqual(len(packet["gpu_reference_rgb"]),4)
        self.assertEqual(packet["gpu_reference_rgb"][0],[255,32,16])
        stage=Usd.Stage.Open(layer)
        tex=UsdShade.Shader(
            stage.GetPrimAtPath("/Asset/Material/Texture"))
        self.assertEqual(tex.GetIdAttr().Get(),"UsdUVTexture")
        self.assertEqual(str(tex.GetInput("file").Get().path),
                         desc["usd_asset_path"])
        rgb=UsdShade.Shader(
            stage.GetPrimAtPath("/Asset/Material/PreviewSurface")
        ).GetInput("diffuseColor").GetConnectedSource()
        self.assertEqual(rgb[1],"rgb")
        self.assertEqual(str(rgb[0].GetPrim().GetPath()),
                         "/Asset/Material/Texture")
        mtlx=UsdShade.Shader(stage.GetPrimAtPath(
            "/Asset/Material/OpenPBR"))
        image=UsdShade.Shader(stage.GetPrimAtPath(
            "/Asset/Material/MtlxImage"))
        coords=UsdShade.Shader(stage.GetPrimAtPath(
            "/Asset/Material/MtlxTexcoord"))
        self.assertEqual(mtlx.GetIdAttr().Get(),
            "ND_open_pbr_surface_surfaceshader")
        self.assertEqual(image.GetIdAttr().Get(),"ND_image_color3")
        self.assertEqual(coords.GetIdAttr().Get(),"ND_texcoord_vector2")
        self.assertEqual(str(image.GetInput("file").GetAttr().Get().path),
                         desc["usd_asset_path"])
        self.assertEqual(image.GetInput("file").GetAttr().GetColorSpace(),
                         "srgb_texture")
        self.assertEqual(
            str(mtlx.GetInput("base_color").GetConnectedSource()[0]
                .GetPrim().GetPath()),"/Asset/Material/MtlxImage")
        self.assertTrue(UsdShade.Material(stage.GetPrimAtPath(
            "/Asset/Material")).GetSurfaceOutput("mtlx").HasConnectedSource())
        self.scene.publish(
            self.pid,"texture_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{"path":"/World/Actor",
                             "asset_id":"textured_mesh",
                             "asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"texture_shots",scene_id="texture_scene",
            scene_revision=1,duration_tick=str(fixture.T),
            shots=[{"shot_id":"tex_shot",
                    "camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(fixture.T),
                    "pattern":"continuous"}])
        take=self.takes.freeze(
            self.pid,"texture_take",scene_id="texture_scene",
            scene_revision=1,timeline_id="texture_shots",
            timeline_revision=1,sample_ticks=[0],
            creator_event="director_confirms")
        snap=self.state.evaluate(
            self.pid,"texture_scene",1,"texture_shots",1,tick=0)
        view=visual_state(self.index,self.pid,snap)
        surface=view["objects"][0]["source_material"]
        self.assertEqual(surface["texture_transport"]["sha256"],desc["sha256"])
        image,receipt=NativeSceneLinearRaster(self.index).render(
            self.pid,"texture_take",take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertGreater(receipt["source_uv_texture_rasterized_triangles"],0)
        self.assertGreater(float(image[:,:,:3].max()),0)
        self.assertFalse(receipt["texture_shading_matches_hydra"])
        self._mesh(texture=self._png((20,255,90)),revision=1)
        old,_=self.assets.open(self.pid,"textured_mesh",1)
        new,_=self.assets.open(self.pid,"textured_mesh",2)
        self.assertEqual(old["document_sha256"],rec["document_sha256"])
        self.assertNotEqual(old["document_sha256"],new["document_sha256"])
        self.assertEqual(self.takes.verify_take(
            self.pid,"texture_take")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.scene.publish(
            self.pid,"texture_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,expected_revision=1,
            asset_bindings=[{"path":"/World/Actor",
                             "asset_id":"textured_mesh",
                             "asset_revision":2}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"texture_shots_v2",scene_id="texture_scene",
            scene_revision=2,duration_tick=str(fixture.T),
            shots=[{"shot_id":"tex_new",
                    "camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(fixture.T),
                    "pattern":"continuous"}])
        later=self.takes.freeze(
            self.pid,"texture_take_v2",scene_id="texture_scene",
            scene_revision=2,timeline_id="texture_shots_v2",
            timeline_revision=1,sample_ticks=[0],
            creator_event="director_confirms")
        new_image,new_receipt=NativeSceneLinearRaster(self.index).render(
            self.pid,"texture_take_v2",later["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertNotEqual(
            receipt["scene_linear_rgba_sha256"],
            new_receipt["scene_linear_rgba_sha256"])
        self.assertNotEqual(image.tobytes(),new_image.tobytes())
        # Repeating the old Take still samples its original source pixels.
        old_again,old_receipt=NativeSceneLinearRaster(self.index).render(
            self.pid,"texture_take",take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertEqual(old_receipt["scene_linear_rgba_sha256"],
                         receipt["scene_linear_rgba_sha256"])
        self.assertEqual(old_again.tobytes(),image.tobytes())


    def test_trusted_native_picker_approval_and_symlink_refusal(self):
        import tempfile
        from pathlib import Path
        from backend.nvp_native_usd_texture import import_native_selected_png
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/"original.png"
            original.write_bytes(self._png())
            approvals=[]
            result=import_native_selected_png(
                self.index,self.pid,original,
                approve=lambda scope:(approvals.append(scope) or True))
            self.assertEqual(result["status"],"ORIGINAL_TEXTURE_IMPORTED")
            self.assertEqual(result["texture"]["sha256"],
                             approvals[0]["sha256"])
            self.assertEqual(verified_texture(
                self.index,self.pid,result["texture"])[0],
                original.read_bytes())
            denied=import_native_selected_png(
                self.index,self.pid,original,approve=lambda _:False)
            self.assertEqual(denied["status"],"DENIED")
            link=Path(tmp)/"untrusted.png"
            try:
                link.symlink_to(original)
            except (OSError,NotImplementedError):
                pass
            else:
                with self.assertRaises(PermissionError):
                    import_native_selected_png(
                        self.index,self.pid,link,approve=lambda _:True)
            with self.assertRaises(PermissionError):
                import_native_selected_png(
                    self.index,self.pid,Path("relative.png"),
                    approve=lambda _:True)

    def test_full_size_png_retains_original_sha_with_derived_viewport_lod(self):
        from hashlib import sha256
        from base64 import b64decode
        image=Image.new("RGB",(1024,512),(135,60,205))
        buffer=BytesIO()
        image.save(buffer,format="PNG")
        original=buffer.getvalue()
        descriptor=publish_texture(self.index,self.pid,original)
        self.assertEqual((descriptor["width"],descriptor["height"]),
                         (1024,512))
        packet=texture_transport(self.index,self.pid,descriptor)
        self.assertTrue(packet["derived_preview"])
        self.assertEqual((packet["width"],packet["height"]),(512,256))
        self.assertEqual((packet["original_width"],packet["original_height"]),
                         (1024,512))
        preview=b64decode(packet["png_base64"])
        self.assertEqual(packet["preview_sha256"],sha256(preview).hexdigest())
        self.assertNotEqual(packet["preview_sha256"],descriptor["sha256"])
        self.assertEqual(verified_texture(
            self.index,self.pid,descriptor)[0],original)
        self.assertEqual(descriptor["sha256"],sha256(original).hexdigest())

    def test_reject_invalid_png_or_unbound_texture_mesh(self):
        for bad in (b"not a png",b"",b"\x89PNG\r\n\x1a\ncorrupt"):
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError,OSError)):
                    decode_png(bad)
        translucent=Image.new("RGBA",(1,1),(255,0,0,100))
        alpha_bytes=BytesIO()
        translucent.save(alpha_bytes,format="PNG")
        with self.assertRaises(ValueError):
            decode_png(alpha_bytes.getvalue())
        with self.assertRaises(ValueError):
            self.assets.publish(
                self.pid,"bad_texture",shape="cube",size_m=2.,
                preview_material={"base_color_rgb":[1,1,1],
                                  "roughness":.5,"metallic":0},
                texture_png=self._png())
        self._mesh(texture=self._png())
        doc=self.assets.open(self.pid,"textured_mesh",1)[0]["data"][
            "preview_material"]["texture"]
        for changed in ({**doc,"usd_asset_path":"file:///etc/passwd"},
                        {**doc,"sha256":"0"*64},
                        {**doc,"color_space":"unknown"}):
            with self.subTest(changed=changed):
                with self.assertRaises((RuntimeError,KeyError)):
                    verified_texture(self.index,self.pid,changed)


if __name__=="__main__":
    unittest.main()
