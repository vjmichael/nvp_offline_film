"""Candidate sole-region evidence is NOT proof of shoe sole contact."""
import copy
import unittest
from backend.nvp_foot_sole import analyze_region_observation, SOLE_REGION_SCRIPT

def package():
    return {
        'foot_lock':{'approval_sha':'a'*64,'actors':[{
            'instance_id':'actor','config':{
                'left':{'contact_windows':[[1,2]]},
                'right':{'contact_windows':[[3,4]]}}}]},
        'leg_identity':{'approval_sha':'b'*64,'actors':[{
            'instance_id':'actor','asset_sha256':'c'*64}]}
    }

def observation():
    values=[]
    for frame in range(1,5):
        regions={}
        for side,x in [('left',-.2),('right',.2)]:
            low=-.015 + frame*.001
            regions[side]={'candidate_vertices':12,'minimum_z_m':low,
                           'maximum_z_m':low+.12,
                           'minimum_world_m':[x+frame*.001,0,low]}
        values.append({'frame':frame,'regions':regions})
    return {'format':'nvp.sole_region.native_observation.v1',
            'foot_lock_sha':'a'*64,'leg_identity_sha':'b'*64,
            'actors':{'actor':{'asset_sha256':'c'*64,
                               'contact_frames':[1,2,3,4],
                               'observations':values}}}

class SoleRegionTests(unittest.TestCase):
    def test_valid_report_never_confuses_candidate_for_physical_contact(self):
        r=analyze_region_observation(observation(),package())
        self.assertEqual(r['format'],'nvp.sole_region.candidate_report.v1')
        self.assertIs(r['physical_sole_contact_verified'],False)
        self.assertIs(r['actors']['actor']['left']['sole_physically_verified'],False)
        self.assertAlmostEqual(r['actors']['actor']['left']['min_clearance_m'],-.014)
        self.assertAlmostEqual(r['actors']['actor']['right']['max_candidate_minimum_xy_shift_m'],.001)

    def test_refuses_wrong_approval_asset_frames_and_geometry(self):
        for mode in ('lock_sha','leg_sha','asset','contact_frame','actor',
                     'few_vertices','nan','mismatch_z','unphysical_extents'):
            data=observation()
            actor=data['actors']['actor']
            if mode=='lock_sha':data['foot_lock_sha']='d'*64
            if mode=='leg_sha':data['leg_identity_sha']='d'*64
            if mode=='asset':actor['asset_sha256']='d'*64
            if mode=='contact_frame':actor['contact_frames']=[2,3,4]
            if mode=='actor':data['actors']['foreign']=data['actors'].pop('actor')
            if mode=='few_vertices':actor['observations'][0]['regions']['left']['candidate_vertices']=1
            if mode=='nan':actor['observations'][0]['regions']['left']['minimum_world_m'][0]=float('nan')
            if mode=='mismatch_z':actor['observations'][0]['regions']['left']['minimum_world_m'][2]=10
            if mode=='unphysical_extents':actor['observations'][0]['regions']['left']['maximum_z_m']=-100
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                analyze_region_observation(data,package())

    def test_native_survey_is_read_only(self):
        compile(SOLE_REGION_SCRIPT,'sole-observation.py','exec')
        self.assertIn('ev.to_mesh()',SOLE_REGION_SCRIPT)
        self.assertIn('minimum_world_m',SOLE_REGION_SCRIPT)
        self.assertNotIn('keyframe_insert(',SOLE_REGION_SCRIPT)
        self.assertNotIn('bpy.ops.wm.save_as_mainfile',SOLE_REGION_SCRIPT)
if __name__=='__main__':unittest.main()
