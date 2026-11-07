"""DA-04: real, bounded, content-addressed OpenUSD mesh-to-live-view parity.

This tests real OpenUSD points/faces composition and the same immutable
scene topology consumed by native 3D WebGL and limited 2D CPU raster.
It does not imply skeletal animation, texture or final cinema acceptance.
"""
import unittest
from io import BytesIO

from PIL import Image
from pxr import UsdGeom
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_data_av_visual import visual_state
from backend.nvp_native_cpu_raster import NativeSourceRaster

T=fixture.T


class RealSourceMeshTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.points=[[-1.,-1.,0.],[1.,-1.,0.],[0.,1.,0.]]
        self.triangles=[[0,1,2]]
        self.geometry=self.assets.publish(
            self.pid,"meshed_actor",shape="mesh",size_m=2.,
            points=self.points,triangles=self.triangles)
        self.scene.publish(
            self.pid,"mesh_scene",prims=[
                {"path":"/World/MeshActor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/MeshActor","asset_id":"meshed_actor",
                "asset_revision":1,
            }])
        self.ledger.publish(self.pid,"mesh_events",[{
            "event_id":"pose","event_kind":"action","subject_id":"Actor",
            "start_tick":0,"end_tick":T,
            "source_id":"performance_authority","source_revision":1,
            "payload":{"usd_prim_path":"/World/MeshActor"},
        }],duration_tick=T)

    def test_verified_mesh_composes_and_native_renderer_consumes_same_data(self):
        asset,layer=self.assets.open(self.pid,"meshed_actor",1)
        self.assertEqual(asset["document_sha256"],self.geometry["document_sha256"])
        scene,stage=self.scene.open(self.pid,"mesh_scene",1)
        self.assertTrue(stage.GetPrimAtPath("/World/MeshActor/Geometry")
                        .IsA(UsdGeom.Mesh))
        snapshot=self.state.evaluate(
            self.pid,"mesh_scene",1,"mesh_events",1,tick=0)
        view=visual_state(self.index,self.pid,snapshot)
        mesh=next(o for o in view["objects"] if o["path"]=="/World/MeshActor")
        self.assertFalse(mesh["gizmo_only"])
        self.assertEqual(mesh["shape"],"mesh")
        self.assertEqual(mesh["mesh_triangles"],self.triangles)
        self.assertEqual(mesh["mesh_points"],self.points)
        renderer=NativeSourceRaster(self.index,self.pid)
        png=renderer.render_png(
            scope={"scene_document_sha256":snapshot["scene_document_sha256"]},
            tick=0,camera_path="/World/Camera",
            source_snapshot=snapshot)
        with Image.open(BytesIO(png)) as picture:
            self.assertEqual(picture.size,(640,360))
            self.assertGreater(max(picture.getextrema()[0]),0)

    def test_malformed_mesh_refused_without_source_publication(self):
        with self.assertRaises(ValueError):
            self.assets.publish(
                self.pid,"invalid_mesh",shape="mesh",size_m=2.,
                points=self.points,triangles=[[0,2,20]])
        with self.assertRaises(ValueError):
            self.assets.publish(
                self.pid,"invalid_mesh",shape="mesh",size_m=2.,
                points=[[float("nan"),0,0],*self.points[1:]],
                triangles=self.triangles)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"invalid_mesh",1)


if __name__=="__main__":
    unittest.main()
