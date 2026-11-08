"""USD-FILM-01C: REAL native lazy world source and FilmIndex texture resolution.

Proof deliberately distinguishes scene metadata reopen from actual USD source
Flatten, and verifies staged PNGs/UsdShade references have immutable SHA
content and cannot point outside NVP's temporary project-scoped source set.
"""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import unittest

from pxr import Sdf, Usd, UsdGeom, UsdShade
from PIL import Image

from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_usd_film01c_texture import (
    derive_texture_resolved_layer, write_verified_texture_files,
)
from backend.nvp_native_usd_texture import PREFIX
from test_nvp_usd_film01_world import NativeFilmWorld01


def png_bytes():
    out = BytesIO()
    im = Image.new("RGB",(16,16),(114,72,35))
    im.save(out,format="PNG")
    return out.getvalue()


def grayscale_png_bytes():
    out=BytesIO()
    Image.new("RGB",(16,16),(90,90,90)).save(out,format="PNG")
    return out.getvalue()


class USDFilm01CLazyResolution(unittest.TestCase):
    def setUp(self):
        original = NativeFilmWorld01("test_real_lazy_scene_payloads_and_original_authored_camera")
        original.setUp()
        self.addCleanup(original.tmp.cleanup)
        self.baseline = original

    def test_initial_world_open_does_not_flatten_any_source_scene(self):
        b=self.baseline
        b.publish()
        # The patch breaks the ACTUAL source scene opener, not a mocked USD
        # library. A genuinely lazy world session may still reopen trusted
        # FilmIndex document metadata, but not source USD scenes themselves.
        with patch.object(OpenUSDSceneBridge,"open",
                          side_effect=AssertionError("eager source USD Flatten")):
            with OpenUSDWorldComposer(b.index).open(b.pid,"TownWorld",1) as world:
                r=world.receipt()
                self.assertEqual(r["eager_original_scene_flatten_count"],0)
                self.assertEqual(r["materialized_scene_set_names"],[])
                self.assertEqual(r["loaded_set_names"],[])
                self.assertLess(r["initial_eager_source_count"],
                                r["source_registry_entry_count"])
                self.assertFalse(world.stage.GetPrimAtPath(
                    "/World/Sets/Outside/StageActor").IsValid())
                self.assertGreater(r["source_staging_bytes"],0)
                self.assertFalse(r["usd_delegates_or_pixels_rendered"])

    def test_on_demand_materialization_only_one_set_then_restart(self):
        b=self.baseline
        source=b.publish()
        with patch.object(OpenUSDSceneBridge,"open",
                side_effect=AssertionError("sealed USD layer cache must not re-flatten")):
            with b.world.open(b.pid,"TownWorld",1) as world:
                before=world.receipt()
                self.assertEqual(before["materialized_scene_set_names"],[])
                self.assertEqual(before["sha_verified_cached_set_loads"],0)
                world.load(["Outside"])
                during=world.receipt()
                self.assertEqual(during["sha_verified_cached_set_loads"],1)
                self.assertEqual(during["eager_original_scene_flatten_count"],0)
                self.assertEqual(during["materialized_scene_set_names"],["Outside"])
                self.assertEqual(during["loaded_set_names"],["Outside"])
                self.assertGreater(
                    during["source_staging_bytes"],before["source_staging_bytes"])
                self.assertTrue(world.stage.GetPrimAtPath(
                    "/World/Sets/Outside/Camera").IsA(UsdGeom.Camera))
                self.assertFalse(world.stage.GetPrimAtPath(
                    "/World/Sets/Inside").IsLoaded())
                world.unload(["Outside"])
                self.assertEqual(world.receipt()["loaded_set_names"],[])
        # No later load of the cached set is allowed to trigger any original
        # source scene Flatten even with its first-stage cache populated.
        during=world.load_receipts[-1]
        self.assertEqual(during["operation"],"unload")

        # Reopening same source world after dropping the session must NOT
        # unexpectedly persist lazy-set choices in the original FilmIndex.
        from backend.nvp_studio import Studio
        from backend.nvp_film_index import FilmIndex
        reopen=OpenUSDWorldComposer(FilmIndex(Studio(b.db)))
        with reopen.open(b.pid,"TownWorld",1) as again:
            self.assertEqual(again.receipt()["materialized_scene_set_names"],[])
            self.assertEqual(again.record["document_sha256"],
                             source["document_sha256"])
            again.load(["Inside"])
            self.assertTrue(again.stage.GetPrimAtPath(
                "/World/Sets/Inside/InteriorCamera").IsA(UsdGeom.Camera))
            self.assertFalse(again.stage.GetPrimAtPath(
                "/World/Sets/Outside").IsLoaded())

    def test_original_png_and_pbr_source_shader_materialize_only_in_private_stage(self):
        b=self.baseline
        original_png=png_bytes()
        roughness_png=grayscale_png_bytes()
        b.assets.publish(
            b.pid,"TexturedTile",shape="mesh",size_m=1,
            points=[[0.,0.,0.],[.8,0.,0.],[0.,.8,0.]],
            triangles=[[0,1,2]],
            mesh_uvs=[[0.,0.],[1.,0.],[0.,1.]],
            preview_material={
                "base_color_rgb":[.6,.5,.3],
                "roughness":.4,"metallic":.1,
            },
            texture_png=original_png,
            pbr_maps_png={"roughness":roughness_png},
        )
        # Put the original exact source into a SCENE as well as an ordinary
        # background prop: only the prop image is eagerly staged at first.
        b.scenes.publish(
            b.pid,"TexturedInterior",native_schemas=True,
            prims=[{"path":"/World/Wall","role":"prop",
                    "position":[0,0,0]}],curves=[],
            asset_bindings=[{
                "path":"/World/Wall","asset_id":"TexturedTile",
                "asset_revision":1,
            }])
        sets=[*b.sets,{
            "name":"Textured","scene_id":"TexturedInterior","scene_revision":1,
        }]
        props=[*b.props,{
            "name":"TexturedProp","asset_id":"TexturedTile",
            "asset_revision":1,
            "load":"reference","position_m":[2,1,0],
        }]
        b.publish(sets=sets,props=props)
        original,before_layer=b.assets.open(b.pid,"TexturedTile",1)
        original_file=UsdShade.Shader(
            Usd.Stage.Open(before_layer).GetPrimAtPath(
                "/Asset/Material/Texture")).GetInput("file").GetAttr().Get()
        original_path=str(original_file.path)
        self.assertTrue(original_path.startswith(PREFIX))
        with b.world.open(b.pid,"TownWorld",1) as world:
            initial=world.receipt()
            self.assertEqual(initial["materialized_scene_set_names"],[])
            # Read the actual private stage under the authentic reference,
            # not a synthetic pixel or browser placeholder.
            shader=UsdShade.Shader(world.stage.GetPrimAtPath(
                "/World/Props/TexturedProp/Material/Texture"))
            real_uri=str(shader.GetInput("file").GetAttr().Get().path)
            self.assertEqual(real_uri,
                "../textures/"+sha256(original_png).hexdigest()+".png")
            mtlx=UsdShade.Shader(world.stage.GetPrimAtPath(
                "/World/Props/TexturedProp/Material/MtlxMap_Roughness"))
            self.assertEqual(
                str(mtlx.GetInput("file").GetAttr().Get().path),
                "../textures/"+sha256(roughness_png).hexdigest()+".png")
            self.assertFalse(
                real_uri.startswith("/home/") or real_uri.startswith("file:"))
            world.load(["Textured"])
            self.assertEqual(world.receipt()["materialized_scene_set_names"],
                             ["Textured"])
            source_shader=UsdShade.Shader(world.stage.GetPrimAtPath(
                "/World/Sets/Textured/Wall/Material/Texture"))
            self.assertEqual(
                str(source_shader.GetInput("file").GetAttr().Get().path),
                real_uri)
            self.assertFalse(world.receipt()["usd_delegates_or_pixels_rendered"])
        after,_=b.assets.open(b.pid,"TexturedTile",1)
        self.assertEqual(original["document_sha256"],
                         after["document_sha256"])
        self.assertEqual(original_path,
                         str(UsdShade.Shader(
                            Usd.Stage.Open(before_layer).GetPrimAtPath(
                                "/Asset/Material/Texture")).
                            GetInput("file").GetAttr().Get().path))

    def test_unapproved_external_texture_assetpath_and_symlink_refused(self):
        b=self.baseline
        stage=Usd.Stage.CreateInMemory("nvp_bad_texture.usda")
        geom=UsdGeom.Xform.Define(stage,"/Asset")
        stage.SetDefaultPrim(geom.GetPrim())
        shader=UsdShade.Shader.Define(stage,"/Asset/Unsafe")
        shader.CreateIdAttr("UsdUVTexture")
        shader.CreateInput("file",Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath("/home/other-project/unsafe.png"))
        record={
            "kind":"asset","data":{"preview_material":None}
        }
        with self.assertRaises(PermissionError):
            derive_texture_resolved_layer(
                b.index,b.pid,stage,
                source_kind="asset",source_record=record)
        import tempfile
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            external=root/"external.png"
            external.write_bytes(b"not-the-right-source")
            target = root/(sha256(png_bytes()).hexdigest()+".png")
            try:
                target.symlink_to(external)
            except OSError:
                # Symlink creation on Windows often requires an additional
                # OS privilege; the unsafe AssetPath test above remains real.
                return
            with self.assertRaises(PermissionError):
                write_verified_texture_files(
                    root,{sha256(png_bytes()).hexdigest():png_bytes()})


if __name__=="__main__":
    unittest.main()
