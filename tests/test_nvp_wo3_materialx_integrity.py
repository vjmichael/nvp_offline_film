"""WO3 actual OpenUSD/MaterialX socket and independent renderer custody tests.

Use real USD 26.11 and real FilmIndex-authored source PNGs. Nothing here
asserts calibrated Hydra/MaterialX GPU parity without a renderer run.
"""
from io import BytesIO
from pathlib import Path
import unittest
from PIL import Image
from pxr import Sdf,Usd,UsdShade

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_wo2_openpbr import verify_openpbr_texture
from backend.nvp_wo2_pbr_channels import verify_pbr_map_graph
from backend.nvp_wo2_materialx_resolver import resolved_materialx_probe


class WO3NativeMaterialXIntegrity(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        def png(rgb):
            out=BytesIO()
            Image.new("RGB",(2,2),rgb).save(out,format="PNG")
            return out.getvalue()
        self.assets.publish(
            self.pid,"wo3_pbr",shape="mesh",size_m=2.0,
            points=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={
                "base_color_rgb":[.8,.7,.6],"roughness":.5,"metallic":0.},
            texture_png=png((180,150,120)),
            pbr_maps_png={
                "roughness":png((64,64,64)),
                "metallic":png((200,200,200)),
                "emission":png((18,60,220)),
                "normal":png((128,128,255)),
                "opacity":png((255,255,255)),
            })
        self.record,self.layer=self.assets.open(self.pid,"wo3_pbr",1)
        material=self.record["data"]["preview_material"]
        self.texture=material["texture"]
        self.maps=material["pbr_maps"]
        self.sha=self.record["document_sha256"]

    def stage(self):
        # Every attack mutates only a new, disposable USD layer. Never
        # tamper with the project's immutable registered FilmIndex blob.
        _,fresh=self.assets.open(self.pid,"wo3_pbr",1)
        return Usd.Stage.Open(fresh)

    def verify(self,stage):
        path="/Asset/Material"
        material=UsdShade.Material(stage.GetPrimAtPath(path))
        preview=UsdShade.Shader(stage.GetPrimAtPath(path+"/PreviewSurface"))
        openpbr=UsdShade.Shader(stage.GetPrimAtPath(path+"/OpenPBR"))
        self.assertTrue(verify_openpbr_texture(
            stage,path,material,self.texture,.5,0.)["materialx_image_graph_authored"])
        verify_pbr_map_graph(stage,path,preview,openpbr,self.maps)

    @staticmethod
    def shader(stage,name):
        return UsdShade.Shader(stage.GetPrimAtPath("/Asset/Material/"+name))

    def test_all_five_channels_and_base_color_have_exact_native_sources(self):
        self.verify(self.stage())
        self.assertEqual(
            self.assets.open(self.pid,"wo3_pbr",1)[0]["document_sha256"],self.sha)

    def test_alternate_socket_on_existing_approved_node_is_not_trusted(self):
        cases=[
            ("preview roughness socket",
             "PreviewSurface","roughness","Map_Roughness","other",
             Sdf.ValueTypeNames.Float),
            ("OpenPBR metallic socket",
             "OpenPBR","base_metalness","MtlxMap_Metallic","other",
             Sdf.ValueTypeNames.Float),
            ("USD map texcoord socket",
             "Map_Roughness","st","Map_Roughness_UV","other",
             Sdf.ValueTypeNames.Float2),
            ("MaterialX map texcoord socket",
             "MtlxMap_Metallic","texcoord","MtlxMapUV_Metallic","other",
             Sdf.ValueTypeNames.Float2),
            ("normal conversion input socket",
             "MtlxNormalMap","in","MtlxMap_Normal","other",
             Sdf.ValueTypeNames.Color3f),
            ("OpenPBR normal conversion socket",
             "OpenPBR","geometry_normal","MtlxNormalMap","other",
             Sdf.ValueTypeNames.Vector3f),
            ("base image color socket",
             "OpenPBR","base_color","MtlxImage","other",
             Sdf.ValueTypeNames.Color3f),
        ]
        for name,target,target_port,source,source_port,output_type in cases:
            with self.subTest(attack=name):
                stage=self.stage()
                source_node=self.shader(stage,source)
                alternate=source_node.CreateOutput(source_port,output_type)
                self.shader(stage,target).GetInput(target_port).ConnectToSource(
                    alternate)
                with self.assertRaises(RuntimeError):
                    self.verify(stage)
        self.verify(self.stage())

    def test_base_image_file_cannot_be_overridden_by_hidden_usd_connection(self):
        stage=self.stage()
        image=self.shader(stage,"MtlxImage")
        original=image.GetInput("file")
        self.assertEqual(original.Get().path,self.texture["usd_asset_path"])
        upstream=self.shader(stage,"MtlxTexcoord").CreateOutput(
            "untrustedAsset",Sdf.ValueTypeNames.Asset)
        original.ConnectToSource(upstream)
        # The authored literal URI remains unchanged: the new connection,
        # which a renderer could evaluate, must nevertheless be rejected.
        self.assertEqual(original.Get().path,self.texture["usd_asset_path"])
        with self.assertRaises(RuntimeError):
            self.verify(stage)

    def test_extra_connected_source_does_not_hide_behind_first_valid_source(self):
        stage=self.stage()
        target=self.shader(stage,"OpenPBR").GetInput("specular_roughness")
        existing=target.GetAttr().GetConnections()
        self.assertEqual(len(existing),1)
        # A first-source-only validator would still report Roughness and
        # silently overlook the second output path.
        target.GetAttr().AddConnection(Sdf.Path(
            "/Asset/Material/MtlxMap_Metallic.outputs:out"))
        self.assertEqual(len(target.GetAttr().GetConnections()),2)
        with self.assertRaises(RuntimeError):
            self.verify(stage)

    def test_color_filter_uv_and_wrap_tamper_are_rejected(self):
        def rewrite_string(stage,node,port,value):
            self.shader(stage,node).GetInput(port).Set(value)
        cases=[
            ("MaterialX filter","MtlxMap_Roughness","filtertype","linear"),
            ("MaterialX wrap","MtlxMap_Emission","uaddressmode","clamp"),
            ("PreviewSurface wrap","Map_Metallic","wrapS","clamp"),
            ("PreviewSurface source color space","Map_Emission",
             "sourceColorSpace","raw"),
            ("texcoord selection","MtlxMapUV_Roughness","index",1),
            ("USD UV primvar name","Map_Opacity_UV","varname","uv2"),
        ]
        for name,node,port,value in cases:
            with self.subTest(attack=name):
                stage=self.stage()
                rewrite_string(stage,node,port,value)
                with self.assertRaises(RuntimeError):
                    self.verify(stage)
        # Reject source files that look like an original approved node but
        # have been re-pointed to a hostile URI.
        stage=self.stage()
        self.shader(stage,"MtlxMap_Metallic").GetInput("file").Set(
            Sdf.AssetPath("file:///tmp/unapproved.png"))
        with self.assertRaises(RuntimeError):
            self.verify(stage)

    def test_normal_scale_and_bias_cannot_be_connected_over_literals(self):
        # Prior to WO3 the normal transform was checked only via its
        # authored numeric value, which remains after a hostile connection.
        for port in ("scale","bias"):
            with self.subTest(setting=port):
                stage=self.stage()
                source=self.shader(stage,"Map_Normal")
                malicious=source.CreateOutput(
                    "shadow_"+port,Sdf.ValueTypeNames.Float4)
                target=self.shader(stage,"Map_Normal").GetInput(port)
                original=list(target.GetAttr().Get())
                target.ConnectToSource(malicious)
                self.assertEqual(list(target.GetAttr().Get()),original)
                with self.assertRaises(RuntimeError):
                    self.verify(stage)

    def test_unresolved_literal_and_texture_paths_are_not_trusted(self):
        # GetConnectedSource/HasConnectedSource may not see a dangling edge,
        # but USD can resolve the path after subsequent composition.
        for node,setting in (
                ("MtlxMap_Roughness","filtertype"),
                ("MtlxMap_Normal","file"),
                ("MtlxTexcoord","index")):
            with self.subTest(node=node,setting=setting):
                stage=self.stage()
                attribute=self.shader(stage,node).GetInput(setting).GetAttr()
                preserved=attribute.Get()
                attribute.AddConnection(Sdf.Path(
                    "/Asset/Material/Unresolved.outputs:override"))
                self.assertEqual(attribute.Get(),preserved)
                with self.assertRaises(RuntimeError):
                    self.verify(stage)

    def test_resolver_rejects_connected_file_even_with_original_uri(self):
        stage=self.stage()
        shader=self.shader(stage,"MtlxMap_Roughness")
        attribute=shader.GetInput("file").GetAttr()
        uri=attribute.Get()
        attribute.AddConnection(Sdf.Path(
            "/Asset/Material/Unresolved.outputs:shadowFile"))
        self.assertEqual(attribute.Get(),uri)
        with self.assertRaises(PermissionError):
            with resolved_materialx_probe(
                    self.index,self.pid,stage,
                    [self.texture]+list(self.maps.values())):
                self.fail("An upstream file override must never reach Hydra")

    def test_materialx_only_probe_refuses_fallback_only_network(self):
        from backend.nvp_wo3_materialx_integrity import (
            isolate_materialx_only_on_derived_stage)
        original=self.stage()
        snapshot=original.GetRootLayer().ExportToString()
        with resolved_materialx_probe(
                self.index,self.pid,original,
                [self.texture]+list(self.maps.values())) as (derived,_):
            mat=UsdShade.Material(
                derived.GetPrimAtPath("/Asset/Material"))
            # Mutate only a derived layer to simulate a renderer that would
            # fall back to PreviewSurface despite appearing to have OpenPBR.
            mat.GetSurfaceOutput("mtlx").GetAttr().SetConnections([])
            with self.assertRaises(RuntimeError):
                isolate_materialx_only_on_derived_stage(derived)
        self.assertEqual(original.GetRootLayer().ExportToString(),snapshot)

    def test_materialx_only_probe_removes_preview_fallback_on_copy(self):
        from backend.nvp_wo3_materialx_integrity import (
            isolate_materialx_only_on_derived_stage)
        original=self.stage()
        snapshot=original.GetRootLayer().ExportToString()
        path="/Asset/Material"
        source_material=UsdShade.Material(original.GetPrimAtPath(path))
        self.assertEqual(
            len(source_material.GetSurfaceOutput().GetAttr().GetConnections()),1)
        with resolved_materialx_probe(
                self.index,self.pid,original,
                [self.texture]+list(self.maps.values())) as (derived,evidence):
            self.assertTrue(evidence["derived_probe_only"])
            count=isolate_materialx_only_on_derived_stage(derived)
            self.assertEqual(count,1)
            scoped_material=UsdShade.Material(derived.GetPrimAtPath(path))
            self.assertEqual(
                len(scoped_material.GetSurfaceOutput().GetAttr().GetConnections()),0)
            self.assertEqual(
                len(scoped_material.GetSurfaceOutput("mtlx").GetAttr()
                    .GetConnections()),1)
            self.assertEqual(
                len(source_material.GetSurfaceOutput().GetAttr().GetConnections()),1)
        self.assertEqual(original.GetRootLayer().ExportToString(),snapshot)

    def test_materialx_resolver_uses_temporary_source_bytes_only(self):
        stage=self.stage()
        original=stage.GetRootLayer().ExportToString()
        descriptors=[self.texture]+list(self.maps.values())
        with resolved_materialx_probe(self.index,self.pid,stage,descriptors) as (
                scoped,evidence):
            node=self.shader(scoped,"MtlxMap_Roughness")
            path=Path(node.GetInput("file").Get().path)
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(),
                             self.index.get_blob(self.pid,self.maps["roughness"]["sha256"]))
            self.assertEqual(evidence["derived_probe_only"],True)
            self.assertFalse(evidence["independent_hydra_render_accepted"])
        self.assertFalse(path.exists())
        self.assertEqual(stage.GetRootLayer().ExportToString(),original)
        self.assertEqual(self.assets.open(self.pid,"wo3_pbr",1)[0]["document_sha256"],
                         self.sha)

    def test_materialx_resolver_detects_native_post_render_image_mutation(self):
        stage=self.stage()
        descriptors=[self.texture]+list(self.maps.values())
        with self.assertRaisesRegex(RuntimeError,"changed a verified"):
            with resolved_materialx_probe(
                    self.index,self.pid,stage,descriptors) as (copy,_):
                path=Path(self.shader(copy,"MtlxImage").GetInput("file").Get().path)
                path.chmod(0o600)
                path.write_bytes(b"untrusted renderer modification")
        self.assertEqual(self.assets.open(self.pid,"wo3_pbr",1)[0]["document_sha256"],
                         self.sha)

    def test_materialx_resolver_refuses_oversized_post_render_source(self):
        # The native worker cannot force post-render SHA verification to
        # read an arbitrarily inflated image into the host process RAM.
        with self.assertRaisesRegex(RuntimeError,"changed a verified"):
            with resolved_materialx_probe(
                    self.index,self.pid,self.stage(),
                    [self.texture]+list(self.maps.values())) as (copy,_):
                dest=Path(self.shader(copy,"MtlxImage").GetInput(
                    "file").Get().path)
                dest.chmod(0o600)
                with dest.open("ab") as writer:
                    writer.write(b"oversized"*(1024*128))

    def test_materialx_resolver_rejects_unapproved_shader_file_path(self):
        stage=self.stage()
        self.shader(stage,"MtlxImage").GetInput("file").Set(
            Sdf.AssetPath("file:///tmp/foreign.png"))
        with self.assertRaises(PermissionError):
            with resolved_materialx_probe(
                    self.index,self.pid,stage,
                    [self.texture]+list(self.maps.values())):
                self.fail("Renderer must never see an unapproved file")


if __name__=="__main__":
    unittest.main()
