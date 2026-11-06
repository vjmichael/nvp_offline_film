"""PROD-04 frozen metric-space pinhole conformance, not raster/Blender quality.

Ground truth target for each test is an explicitly requested normalized screen
position. Independent reprojection is checked against the solver's measured
residual; difficult two-shots must report their residual instead of hiding it.
"""
import math
import unittest
from backend.nvp_blocking_camera import solve_camera,project


def scene(positions):
    return {'room_m':[12,10,4], 'instances':[
        {'instance_id':f'actor_{i}','name':f'Actor {i}', 'category':'character',
         'dimensions':[.5,.5,1.7],
         'pose':{'asset_id':f'asset_{i}','x':xy[0],'y':xy[1],'z':0,'rotation':0}}
        for i,xy in enumerate(positions)]}


class CameraConformance(unittest.TestCase):
    def test_fifteen_fixed_single_subject_cases(self):
        for xy in [(3,3),(6,5),(9,7),(3,7),(9,3)]:
            for lens in (24,35,50):
                with self.subTest(xy=xy,lens=lens):
                    result=solve_camera(scene([xy]),['actor_0'],
                                      lens_mm=lens,shot_size='medium',
                                      desired_positions=[[.38,.52]])
                    observed=project([*xy,1.7*.86],
                                     result['position_m'],result['look_at_m'],lens)
                    residual=math.dist(observed,[.38,.52])
                    self.assertAlmostEqual(residual,result['max_residual'],delta=2e-6)
                    self.assertLessEqual(residual,.015)
                    self.assertTrue(result['fits_all_subjects'])

    def test_multi_subject_compromise_not_falsely_marked_exact(self):
        stages=[((4,4),(6,4)),((4,4),(6,6)),((3,3),(9,7))]
        for coords in stages:
            with self.subTest(coords=coords):
                result=solve_camera(scene(coords),['actor_0','actor_1'],lens_mm=35,
                                    desired_positions=[[.38,.52],[.62,.52]])
                observed=[project([*xy,1.7*.86],result['position_m'],result['look_at_m'],35)
                          for xy in coords]
                residuals=[math.dist(p,t) for p,t in zip(observed,[[.38,.52],[.62,.52]])]
                self.assertAlmostEqual(max(residuals),result['max_residual'],delta=2e-6)
                self.assertGreaterEqual(result['max_residual'],0)
        self.assertGreater(result['max_residual'],.03) # physically difficult two-hander

if __name__=='__main__':unittest.main()
