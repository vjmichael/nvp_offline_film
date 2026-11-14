"""Native immutable imported-location geometry/PBR validation."""
from pathlib import Path
import tempfile
import unittest

from pxr import Gf,Sdf,Usd,UsdGeom,UsdShade,Vt
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge


def location(*,invalid=False,external=False):
    layer=Sdf.Layer.CreateAnonymous("independently_authored_location.usda")
    stage=Usd.Stage.Open(layer)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage,"/Asset").GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage,1.)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.Xform.Define(stage,"/Asset/Geometry")
    mesh=UsdGeom.Mesh.Define(stage,"/Asset/Geometry/Hallway")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(-4,-3,0),Gf.Vec3f(4,-3,0),
        Gf.Vec3f(4,3,0),Gf.Vec3f(-4,3,0)]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([4]))
    mesh.GetFaceVertexIndicesAttr().Set(
        Vt.IntArray([0,1,2,99 if invalid else 3]))
    UsdGeom.Xform.Define(stage,"/Asset/Looks")
    mat=UsdShade.Material.Define(stage,"/Asset/Looks/Brick")
    shader=UsdShade.Shader.Define(stage,"/Asset/Looks/Brick/Preview")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(.6,.3,.2))
    shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(.7)
    shader.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(.1)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),"surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
    if external:
        mesh.GetPrim().GetReferences().AddReference("./outside.usda")
    return layer.ExportToString().encode("utf8")


class P1FImportedEnvironmentNative(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="nvp-p1f-location-")
        self.addCleanup(tmp.cleanup)
        studio=Studio(Path(tmp.name)/"studio.sqlite")
        self.pid=studio.create_project("Real Location","")["id"]
        self.index=FilmIndex(studio)
        self.assets=OpenUSDAssetRegistry(self.index)

    def approval(self,event,scope):
        return (event=="approved" and
                scope["operation"]=="nvp.p1f.import_authored_3d_environment.v1")

    def publish(self,asset="hallway",source=None,event="approved"):
        return self.assets.import_environment(
            self.pid,asset,source or location(),
            location_id="LOCATION_Hallway",
            approve_import=self.approval,creator_event=event)

    def test_real_pbr_environment_composed_into_original_scene(self):
        source=location()
        receipt=self.publish(source=source)
        rec,layer=self.assets.open(self.pid,"hallway",1)
        self.assertEqual(rec["document_sha256"],receipt["document_sha256"])
        self.assertEqual(rec["data"]["geometry"]["mesh_count"],1)
        self.assertEqual(rec["data"]["geometry"]["material_count"],1)
        self.assertEqual(self.index.get_blob(
            self.pid,rec["data"]["layer_sha256"]),source)
        scene=OpenUSDSceneBridge(self.index).publish(
            self.pid,"original_location",
            prims=[{"path":"/World/Set","role":"environment","position":[0,0,0]},
                   {"path":"/World/Camera","role":"camera","position":[0,-6,2]}],
            curves=[],native_schemas=True,
            asset_bindings=[{"path":"/World/Set",
                             "asset_id":"hallway","asset_revision":1}])
        result,stage=OpenUSDSceneBridge(self.index).open(
            self.pid,"original_location",1)
        self.assertEqual(result["document_sha256"],scene["document_sha256"])
        self.assertTrue(stage.GetPrimAtPath(
            "/World/Set/Geometry/Hallway").IsA(UsdGeom.Mesh))

    def test_refuse_unreviewed_or_malformed_location(self):
        for name,raw,event in [
            ("bad_topology",location(invalid=True),"approved"),
            ("external_ref",location(external=True),"approved"),
            ("refused",location(),"refused")]:
            with self.assertRaises((ValueError,PermissionError)):
                self.publish(name,raw,event)
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,name)

    def test_do_not_substitute_environment_for_actor(self):
        self.publish()
        with self.assertRaises(ValueError):
            OpenUSDSceneBridge(self.index).publish(
                self.pid,"not_an_actor",
                prims=[{"path":"/World/Actor","role":"actor","position":[0,0,0]},
                       {"path":"/World/Camera","role":"camera","position":[0,0,4]}],
                curves=[],native_schemas=True,
                asset_bindings=[{"path":"/World/Actor",
                                 "asset_id":"hallway","asset_revision":1}])


if __name__=="__main__":
    unittest.main()
