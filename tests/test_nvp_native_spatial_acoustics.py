"""DA-03B spatial acoustics: orientation and source-asset obstruction."""
import math
import unittest

from backend.nvp_native_spatial_acoustics import (
    spatial_gains,obstruction_gain)


ID=[[1.,0.,0.,0.],[0.,1.,0.,0.],
    [0.,0.,1.,0.],[0.,0.,0.,1.]]
TURNED=[[0.,1.,0.,0.],[-1.,0.,0.,0.],
        [0.,0.,1.,0.],[0.,0.,0.,1.]]


class NativeSpatialAcousticsTests(unittest.TestCase):
    def test_rotated_listener_changes_stereo_field_without_moving_source(self):
        pos=[5.,0.,0.]
        origin=[0.,0.,0.]
        left,right=spatial_gains(pos,origin,ID,1.0)
        self.assertGreater(right,left)
        a,b=spatial_gains(pos,origin,TURNED,1.0)
        self.assertAlmostEqual(a,b,places=7)
        self.assertAlmostEqual(math.hypot(left,right),math.hypot(a,b),places=7)
        self.assertNotEqual((left,right),(a,b))

    def test_only_source_bound_between_solid_obstructs(self):
        obstacle=[{"path":"/World/Wall","center":[5.,0.,0.],
                   "radius":1.,"asset_sha256":"f"*64}]
        blocked=obstruction_gain(
            [0.,0.,0.],[10.,0.,0.],obstacle,
            source_path="/World/Actor",listener_path="/World/Camera")
        self.assertLess(blocked,1.0)
        self.assertEqual(obstruction_gain(
            [0.,0.,0.],[10.,0.,0.],
            [{**obstacle[0],"center":[15.,0.,0.]}],
            source_path="/World/Actor",listener_path="/World/Camera"),1.0)
        self.assertEqual(obstruction_gain(
            [0.,0.,0.],[10.,0.,0.],
            [{**obstacle[0],"path":"/World/Actor"}],
            source_path="/World/Actor",listener_path="/World/Camera"),1.0)

    def test_nonfinite_or_zero_listener_transform_refused(self):
        with self.assertRaises(ValueError):
            spatial_gains([1.,2.,3.],[0.,0.,0.],
                [[0.,0.,0.,0.],*ID[1:]],1.0)
        with self.assertRaises(ValueError):
            spatial_gains([float("inf"),0,0],[0,0,0],ID,1.0)


if __name__=="__main__":
    unittest.main()
