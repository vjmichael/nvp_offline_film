"""PROD-06E2B1 contact intent and staged-pose refusal regressions."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.nvp_foot_contact import FootContactPlan, validate_contacts
from backend.nvp_staged_pose import analyze_staged_pose, STAGED_POSE_SURVEY_SCRIPT
from backend.nvp_production_scene import digest
from backend.nvp_studio import Studio

SIDES={
    'left':{'contact_windows':[[1,2]],'knee_pole_direction_world':[0,1,0],
            'ankle_to_surface_m':.075,'surface_z_m':0.,
            'max_ankle_correction_m':.15},
    'right':{'contact_windows':[[3,3]],'knee_pole_direction_world':[0,1,0],
             'ankle_to_surface_m':.075,'surface_z_m':0.,
             'max_ankle_correction_m':.15},
}

class ContactIntentTests(unittest.TestCase):
    def test_bilateral_pole_and_stance_validation(self):
        out=validate_contacts(SIDES,1,3)
        self.assertEqual(out['left']['contact_windows'],[[1,2]])
        self.assertEqual(out['right']['contact_windows'],[[3,3]])
        self.assertAlmostEqual(sum(x*x for x in out['left']['knee_pole_direction_world']),1.)

    def test_reject_bad_windows_missing_sides_or_invalid_poles(self):
        mutations=[
            {'left':SIDES['left']},
            {**SIDES,'left':{**SIDES['left'],'contact_windows':[[1,4]]}},
            {**SIDES,'left':{**SIDES['left'],'contact_windows':[[2,3],[1,2]]}},
            {**SIDES,'left':{**SIDES['left'],'knee_pole_direction_world':[0,0,0]}},
            {**SIDES,'left':{**SIDES['left'],'knee_pole_direction_world':[float('nan'),0,0]}},
            {**SIDES,'left':{**SIDES['left'],'ankle_to_surface_m':2}},
            {**SIDES,'left':{**SIDES['left'],'max_ankle_correction_m':.7}},
            {**SIDES,'left':{**SIDES['left'],'contact_windows':[]},
             'right':{**SIDES['right'],'contact_windows':[]}},
            {**SIDES,'right':{**SIDES['right'],'extra':'unapproved'}},
        ]
        for bad in mutations:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_contacts(bad,1,3)

    def test_durable_approval_revision_and_dependency_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            studio=Studio(Path(temporary)/'studio.sqlite')
            pid=studio.create_project('Example','Narrative')['id']
            sid='SC_FAKE_FOR_ISOLATED_LEDGER_TEST'
            package={'take':{'shots':[{'start_frame':1,'stop_frame':4}]},
                     'leg_identity':{'approval_sha':'a'*64}}
            class FrozenFixture(FootContactPlan):
                def _context(self,p,s):
                    if p!=pid or s!=sid:raise KeyError('Other project/scene')
                    return package,digest(package),1,3
            service=FrozenFixture(studio)
            row=service.create(pid,sid)
            self.assertEqual(row['revision'],0)
            with self.assertRaises(RuntimeError):
                service.approve(pid,sid,0)
            row=service.configure(pid,sid,'actorA',SIDES,0) if row['plan']['actors'] else None
            # A genuine actor roster is required in production; the isolated
            # empty fixture must not allow empty project approval.
            if row is None:
                with self.assertRaises(RuntimeError):
                    service.approve(pid,sid,0)
            with self.assertRaises(RuntimeError):
                service.export(pid,sid)
            self.assertEqual(FrozenFixture(Studio(studio.db_path)).read(pid,sid)['status'],'draft')

def staged_package():
    return {
        'take':{'shots':[{'start_frame':1,'stop_frame':4}]},
        'retarget':{'approval_sha':'b'*64},
        'leg_identity':{
            'approval_sha':'a'*64,
            'actors':[{'instance_id':'actorA','asset_sha256':'c'*64,
                       'mapping':{
                           'left':{'hip':'l1','knee':'l2','ankle':'l3','toe':'l4'},
                           'right':{'hip':'r1','knee':'r2','ankle':'r3','toe':'r4'}}}]}
    }

def staged_report():
    legs={}
    for side,x in (('left',-.18),('right',.18)):
        legs[side]={'hip':[x,0,1.],'knee':[x,0,.7],
                    'ankle':[x,0,.4],'toe':[x,.1,.35]}
    sample={'frame':1,'legs':legs,
            'actor_root_world_m':[0,0,0],'rig_world_scale':[1,1,1]}
    return {'format':'nvp.staged_pose.observation.v1',
            'leg_approval_sha':'a'*64,'retarget_approval_sha':'b'*64,
            'blender_version':'synthetic only','frames':[1],
            'actors':{'actorA':{'asset_sha256':'c'*64,'samples':[sample]}}}

class StagedPoseTests(unittest.TestCase):
    def test_staged_lengths_are_world_scale_and_source_pinned(self):
        report=analyze_staged_pose(staged_report(),staged_package())
        self.assertEqual(report['format'],'nvp.staged_pose.validated.v1')
        self.assertAlmostEqual(report['actors']['actorA'][0]['legs']['left']['upper_m'],.3)
        self.assertFalse(report['ik_applied'])

    def test_refuse_mismatched_sha_or_unverified_geometry(self):
        for mutation in ('leg_sha','foreign_asset','unbounded_scale','duplicate_frames',
                         'degenerate_thigh','wrong_actor','bad_root'):
            report=staged_report()
            if mutation=='leg_sha':report['leg_approval_sha']='f'*64
            if mutation=='foreign_asset':report['actors']['actorA']['asset_sha256']='d'*64
            if mutation=='unbounded_scale':
                report['actors']['actorA']['samples'][0]['rig_world_scale']=[1000.,1.,1.]
            if mutation=='duplicate_frames':report['frames']=[1,1]
            if mutation=='degenerate_thigh':
                leg=report['actors']['actorA']['samples'][0]['legs']['left']
                leg['knee']=leg['hip']
            if mutation=='wrong_actor':report['actors']['intruder']=report['actors'].pop('actorA')
            if mutation=='bad_root':report['actors']['actorA']['samples'][0]['actor_root_world_m']=[0,float('inf'),0]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                analyze_staged_pose(report,staged_package())

    def test_blender_script_observes_but_does_not_key_ik(self):
        compile(STAGED_POSE_SURVEY_SCRIPT,'native-pose-survey','exec')
        self.assertIn('rig.matrix_world@bone.head',STAGED_POSE_SURVEY_SCRIPT)
        self.assertNotIn('keyframe_insert(',STAGED_POSE_SURVEY_SCRIPT)
        self.assertNotIn('bpy.ops.wm.save_as_mainfile',STAGED_POSE_SURVEY_SCRIPT)

if __name__=='__main__':unittest.main()
