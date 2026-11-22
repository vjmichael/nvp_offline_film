"""NVP-PROD-06E1: independent algebra, contact conservation and refusal tests."""
import copy
import math
import time
import unittest
from backend.nvp_foot_ik import solve_two_bone, solve_biped_foot_plants


def sample_frames(n=4):
    samples=[]
    for t in range(1,n+1):
        offset=.01*(t-1)
        samples.append({'frame':t,
            'left':{'hip':[-.15+offset,0,.9],'ankle':[-.15+offset,0,.01], 'pole':[-.15+offset,.4,.5]},
            'right':{'hip':[.15+offset,0,.9],'ankle':[.15+offset,0,.01], 'pole':[.15+offset,.4,.5]}})
    return samples


def settings(left=None,right=None):
    return {leg:{'thigh_m':.5,'shin_m':.5,'contact_windows':wins}
            for leg,wins in (('left',left if left is not None else [[1,3]]),
                             ('right',right if right is not None else [[2,4]]))}


class AnalyticIKTests(unittest.TestCase):
    def test_two_bone_exact_lengths_and_bend_direction(self):
        result=solve_two_bone((0,0,1),(0,0,.2),(0,1,.7),.5,.5)
        self.assertAlmostEqual(math.dist(result['hip'],result['knee']),.5)
        self.assertAlmostEqual(math.dist(result['knee'],result['ankle']),.5)
        self.assertGreater(result['knee'][1],0)
        self.assertLess(result['length_error_m'],1e-10)
        self.assertGreater(result['knee_flexion_deg'],0)

    def test_near_reach_boundary_without_silent_clamping(self):
        self.assertGreater(solve_two_bone((0,0,1),(0,0,.001),(0,1,0),.5,.5)['knee_flexion_deg'],0)
        for point in ((0,0,0),(0,0,-1),(0,0,1)):
            with self.subTest(point=point),self.assertRaises(ValueError):
                solve_two_bone((0,0,1),point,(0,1,.5),.5,.5)

    def test_degenerate_pole_and_nonfinite_inputs_refused(self):
        for pole in [(0,0,.6), (float('nan'),1,1), (False,0,0)]:
            with self.subTest(pole=pole),self.assertRaises(ValueError):
                solve_two_bone((0,0,1),(0,0,.3),pole,.5,.5)
        for bad in [float('inf'),0,False,11]:
            with self.assertRaises(ValueError):
                solve_two_bone((0,0,1),(0,0,.3),(0,1,.5),bad,.5)

    def test_asymmetric_bones(self):
        result=solve_two_bone((0,0,.8),(0,0,.1),(0,1,.4),.35,.5)
        self.assertAlmostEqual(math.dist(result['hip'],result['knee']),.35)
        self.assertAlmostEqual(math.dist(result['knee'],result['ankle']),.5)


class FootPlantTests(unittest.TestCase):
    def test_independent_two_foot_locks_and_source_immutability(self):
        samples=sample_frames();old=copy.deepcopy(samples)
        result=solve_biped_foot_plants(samples,settings(),approval_sha='a'*64)
        self.assertEqual(samples,old)
        self.assertEqual(result['retarget_approval_sha'],'a'*64)
        left=result['contacts']['left'][0]['ankle_world_m']
        right=result['contacts']['right'][0]['ankle_world_m']
        for i,pose in enumerate(result['frames'],1):
            self.assertEqual(pose['left']['hip'],samples[i-1]['left']['hip'])
            if i<=3:
                self.assertEqual(pose['left']['ankle'],left)
            else:
                self.assertEqual(pose['left']['ankle'],samples[i-1]['left']['ankle'])
            if i>=2:self.assertEqual(pose['right']['ankle'],right)
            else:self.assertEqual(pose['right']['ankle'],samples[i-1]['right']['ankle'])
            for leg in ('left','right'):
                self.assertLess(pose[leg]['length_error_m'],1e-6)
        self.assertEqual(left[-1],0)
        self.assertEqual(right[-1],0)

    def test_unplanted_passthrough(self):
        frames=sample_frames();result=solve_biped_foot_plants(frames,settings([],[]))
        self.assertEqual(result['contacts'],{'left':[],'right':[]})
        for raw,out in zip(frames,result['frames']):
            for leg in ('left','right'):
                self.assertFalse(out[leg]['contact'])
                self.assertEqual(out[leg]['ankle'],raw[leg]['ankle'])

    def test_authority_and_contact_schedule_validation(self):
        for broken in ([[1,3],[3,4]],[[0,1]],[[2,5]],[[3,2]],[[1,2],[1,3]],[[1.0,2]]):
            with self.subTest(windows=broken),self.assertRaises(ValueError):
                solve_biped_foot_plants(sample_frames(),settings(broken,[]))
        with self.assertRaises(ValueError):
            solve_biped_foot_plants(sample_frames(),settings(),approval_sha='FAKE')
        with self.assertRaises(ValueError):
            solve_biped_foot_plants(sample_frames(),{'left':settings()['left']})
        for bad in (float('nan'),False,3):
            with self.assertRaises(ValueError):
                solve_biped_foot_plants(sample_frames(),settings(),max_correction_m=bad)

    def test_dense_frames_and_contacts_not_guessed(self):
        frames=sample_frames();frames[2]['frame']=4
        with self.assertRaisesRegex(ValueError,'consecutive'):
            solve_biped_foot_plants(frames,settings())
        frames=sample_frames();del frames[2]['right']
        with self.assertRaises(ValueError):solve_biped_foot_plants(frames,settings())

    def test_refuse_unreachable_hip_and_unsafe_foot_displacement(self):
        frames=sample_frames();frames[2]['left']['hip']=[4,0,.9]
        with self.assertRaisesRegex(ValueError,'Unreachable'):
            solve_biped_foot_plants(frames,settings())
        frames=sample_frames();frames[2]['left']['ankle']=[2,0,0]
        with self.assertRaisesRegex(ValueError,'correction exceeded'):
            solve_biped_foot_plants(frames,settings())

    def test_full_2400_frame_budget_determinism(self):
        frames=sample_frames(2400)
        # Continuous in-place gait; avoid introducing 24m of unintended root travel.
        for i,frame in enumerate(frames):
            shift=.05*math.sin(i*.05)
            for leg in ('left','right'):
                basis=-.15 if leg=='left' else .15
                frame[leg]['hip'][0]=basis+shift
                frame[leg]['ankle'][0]=basis+shift
                frame[leg]['pole'][0]=basis+shift
        opts=settings([[1,2400]],[[1,2400]])
        start=time.perf_counter();a=solve_biped_foot_plants(frames,opts,max_correction_m=.25)
        elapsed=time.perf_counter()-start
        b=solve_biped_foot_plants(frames,opts,max_correction_m=.25)
        self.assertEqual(a,b)
        self.assertEqual(len(a['frames']),2400)
        print(f'PROD06E1 2400-frame two-leg CPU preflight: {elapsed:.3f}s (informational; no hardware SLA)')

if __name__=='__main__':unittest.main()
