"""P1-F real native OpenUSD UV+PBR production source and rights/texture denial."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from pxr import Gf,Sdf,Usd,UsdGeom,UsdShade,Vt

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_p1f_reviewed_pbr_materials import P1FReviewedPBRMaterials


RIGHTS={"basis":"creator_owned","holder":"Creator Studio",
        "license_identifier":"original-rights-record-2026",
        "allowed_uses":["render","derivative","distribution"]}
EVIDENCE=(b"Original material authored in studio for picture production. "
          b"Creator explicitly approves rendering, derivatives and distribution "
          b"of these precise original texture source bytes in NVP.\n")


def original_uv_location(*,no_uv=False):
    layer=Sdf.Layer.CreateAnonymous("original_authored_set.usda")
    stage=Usd.Stage.Open(layer)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage,"/Asset").GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage,1.)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.Xform.Define(stage,"/Asset/Geometry")
    mesh=UsdGeom.Mesh.Define(stage,"/Asset/Geometry/Wall")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(-3,-1,0),Gf.Vec3f(3,-1,0),
        Gf.Vec3f(3,-1,4),Gf.Vec3f(-3,-1,4)]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([4]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0,1,2,3]))
    if not no_uv:
        p=UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "st",Sdf.ValueTypeNames.TexCoord2fArray,UsdGeom.Tokens.vertex)
        p.Set(Vt.Vec2fArray([
            Gf.Vec2f(0,0),Gf.Vec2f(1,0),
            Gf.Vec2f(1,1),Gf.Vec2f(0,1)]))
    UsdGeom.Xform.Define(stage,"/Asset/Looks")
    material=UsdShade.Material.Define(stage,"/Asset/Looks/Brick")
    shader=UsdShade.Shader.Define(stage,"/Asset/Looks/Brick/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(.53,.24,.17))
    shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(.65)
    shader.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(.05)
    material.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(),"surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return layer.ExportToString().encode("utf8")


def png(mode,color,dimension=64):
    image=Image.new(mode,(dimension,dimension),color)
    stream=BytesIO()
    image.save(stream,format="PNG")
    return stream.getvalue()


class ReviewedNativePBRMaterials(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="nvp-p1f-review-pbr-")
        self.addCleanup(tmp.cleanup)
        self.studio=Studio(Path(tmp.name)/"studio.sqlite")
        self.pid=self.studio.create_project("Original set textures","")["id"]
        self.index=FilmIndex(self.studio)
        self.assets=OpenUSDAssetRegistry(self.index)
        self.materials=P1FReviewedPBRMaterials(self.index)
        self.maps={
            "baseColor":png("RGB",(123,65,42)),
            "roughness":png("L",179),
            "metallic":png("L",13),
            "normal":png("RGB",(128,128,255)),
        }

    def import_location(self,*,no_uv=False):
        return self.assets.import_environment(
            self.pid,"original_set",original_uv_location(no_uv=no_uv),
            location_id="LOCATION_SourceSet",
            creator_event="owner_pressed_approve",
            approve_import=lambda event,scope:
                event=="owner_pressed_approve"
                and scope["operation"]=="nvp.p1f.import_authored_3d_environment.v1")

    def accept(self,event,scope):
        return (event=="owner_approved_exact_maps" and
                scope["operation"]=="nvp.p1f.import_reviewed_pbr_texture_set.v1"
                and scope["material_path"]=="/Asset/Looks/Brick"
                and scope["rights_evidence_sha256"]==sha256(EVIDENCE).hexdigest()
                and scope["environment_id"]=="original_set"
                and set(scope["textures"])==set(self.maps))

    def publish(self,material_id="original_brick",**kwargs):
        return self.materials.publish(
            self.pid,material_id,
            environment_id="original_set",environment_revision=1,
            material_path="/Asset/Looks/Brick",
            textures=self.maps,rights=RIGHTS,rights_evidence=EVIDENCE,
            approve_import=self.accept,
            creator_event="owner_approved_exact_maps",**kwargs)

    def test_genuine_usd_uv_and_four_png_rights_review_survives_restart(self):
        self.import_location()
        response=self.publish()
        record=self.materials.open(self.pid,"original_brick")
        self.assertEqual(record["document_sha256"],response["document_sha256"])
        self.assertEqual(record["dependencies"],[{
            "object_id":"original_set","revision":1,"role":"asset"}])
        doc=record["data"]
        self.assertFalse(doc["private_worker_authorized"])
        self.assertFalse(doc["whole_film_delivered"])
        self.assertFalse(doc["rights_document_verified"])
        self.assertEqual(doc["bindings"][0]["mesh_path"],
                         "/Asset/Geometry/Wall")
        self.assertEqual(doc["bindings"][0]["uv_count"],4)
        self.assertEqual(doc["textures"]["normal"]["mode"],"RGB")
        reopened=P1FReviewedPBRMaterials(FilmIndex(self.studio))
        record2=reopened.open(self.pid,"original_brick")
        self.assertEqual(record2["document_sha256"],record["document_sha256"])
        for slot,original in self.maps.items():
            self.assertEqual(reopened.original_texture_bytes(
                self.pid,"original_brick",slot),original)
        self.assertEqual(self.index.get_blob(
            self.pid,doc["rights_evidence_sha256"]),EVIDENCE)

    def test_invalid_source_rights_and_textures_denied_before_revision(self):
        self.import_location()
        cases=[
            ("no_base",{"textures":{"normal":self.maps["normal"]}}),
            ("not_png",{"textures":{"baseColor":b"not a png"*40}}),
            ("wrong_dimensions",{"textures":{
                "baseColor":self.maps["baseColor"],"normal":png("RGB",(128,128,255),32)}}),
            ("not_rgb_normal",{"textures":{
                "baseColor":self.maps["baseColor"],"normal":png("L",127)}}),
            ("wrong_rights",{"rights":{**RIGHTS,"allowed_uses":["render"]}}),
            ("no_license",{"rights_evidence":b"no"}),
            ("no_approval",{"creator_event":"refused"}),
            ("outside_material",{"material_path":"/Outside/Look"}),
        ]
        for identity,change in cases:
            with self.subTest(identity=identity):
                values={
                    "environment_id":"original_set","environment_revision":1,
                    "material_path":"/Asset/Looks/Brick",
                    "textures":self.maps,"rights":RIGHTS,"rights_evidence":EVIDENCE,
                    "approve_import":self.accept,
                    "creator_event":"owner_approved_exact_maps",
                }
                values.update(change)
                with self.assertRaises((ValueError,PermissionError)):
                    self.materials.publish(self.pid,identity,**values)
                with self.assertRaises(KeyError):
                    self.index.read_revision(self.pid,identity)

    def test_uv_must_be_authored_and_source_cannot_be_replayed(self):
        self.import_location(no_uv=True)
        with self.assertRaisesRegex(ValueError,"UV"):
            self.publish()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"original_brick")

    def test_replay_denied_and_tampered_blob_refuses_cold_reopen(self):
        self.import_location()
        self.publish()
        with self.assertRaises(RuntimeError):
            self.publish()
        record=self.materials.open(self.pid,"original_brick")
        sha=record["data"]["textures"]["baseColor"]["sha256"]
        path=self.index._blob_path(self.pid,sha)
        path.write_bytes(b"tampered original texture")
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            self.materials.open(self.pid,"original_brick")


if __name__=="__main__":
    unittest.main()
