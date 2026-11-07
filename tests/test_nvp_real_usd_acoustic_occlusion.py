"""DA-03C: real SHA-verified USD mesh occlusion, not bounding-sphere fiction.

Ray triangle tests use original typed FilmIndex/OpenUSD procedural geometry
without any frame renderer, codec, HRTF dataset or external executable.
"""
import unittest

from backend.nvp_native_spatial_acoustics import (
    verified_occluders,obstruction_gain)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T

from test_nvp_openusd_reusable_assets import NativeUSD02Integration


class RealNativeAcousticGeometry(unittest.TestCase):
    def setUp(self):
        NativeUSD02Integration.setUp(self)
        self.wall=self.assets.publish(
            self.pid,"source_wall_mesh",shape="mesh",size_m=2.,
            points=[[0,-1,-1],[0,1,-1],[0,1,1],[0,-1,1]],
            triangles=[[0,1,2],[0,2,3]])
        self.scene.publish(self.pid,"sound_world",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[10,0,0]},
            {"path":"/World/Wall","role":"environment","position":[5,0,0]},
        ],curves=[{"path":"/World/Wall","samples":[
            {"tick":0,"position":[5,0,0]},
            {"tick":2*T,"position":[5,6,0]},
        ]}],asset_bindings=[{
            "path":"/World/Wall","asset_id":"source_wall_mesh","asset_revision":1
        }])

    def test_mesh_ray_blocks_only_when_original_triangle_intersects(self):
        first=self.state.evaluate(
            self.pid,"sound_world",1,"event_timeline",1,tick=0)
        later=self.state.evaluate(
            self.pid,"sound_world",1,"event_timeline",1,tick=T)
        wall0=verified_occluders(self.index,self.pid,first)
        wall1=verified_occluders(self.index,self.pid,later)
        self.assertEqual(len(wall0),1)
        self.assertEqual(wall0[0]["asset_sha256"],
                         self.wall["document_sha256"])
        self.assertTrue(wall0[0]["source_geometry_exact"])
        self.assertEqual(len(wall0[0]["triangles"]),2)
        scope={"source_path":"/World/Actor","listener_path":"/World/Camera"}
        blocked=obstruction_gain([0,0,0],[10,0,0],wall0,**scope)
        unblocked=obstruction_gain([0,0,0],[10,0,0],wall1,**scope)
        self.assertLess(blocked,1.)
        self.assertEqual(unblocked,1.)
        self.assertEqual(self.index.read_revision(
            self.pid,"source_wall_mesh",1)["document_sha256"],
            self.wall["document_sha256"])

    def test_bounding_sphere_cannot_invent_mesh_intersection(self):
        # Ray intersects a large spherical bound, but not these actual
        # three authored source-space triangle vertices.
        wall=[{"path":"/World/Wall","center":[5,0,0],
               "radius":5.,
               "triangles":[((5,2,-1),(5,3,-1),(5,2,1))]}]
        gain=obstruction_gain([0,0,0],[10,0,0],wall,
            source_path="/World/Actor",listener_path="/World/Camera")
        self.assertEqual(gain,1.)


if __name__=="__main__":
    unittest.main()
