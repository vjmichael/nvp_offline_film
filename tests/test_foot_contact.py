"""PROD-06E2B: bounded authored contacts and independent comparison guardrails.

Mocks in plan-state tests are intentionally only domain-service test doubles.
They are NOT real Blender/approved-character acceptance; the separately pinned
native external humanoid acceptance is tested in CI.
"""
import ast
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_foot_contact import FootLockPlan,check_side,validate_actor
from backend.nvp_foot_blender import (FOOTLOCK_BUILD,FOOTLOCK_AUDIT,
                                     independently_compare)
from tests.test_skinning import make_fixture
from tools.nvp_prod06e2b_fixture import fixture_actor_settings


class ContactSchemaTests(unittest.TestCase):
    def test_valid_two_side_windows(self):
        p=validate_actor(fixture_actor_settings(),120)
        self.assertEqual(p['left']['contact_windows'],[[1,12]])
        self.assertEqual(p['right']['contact_windows'],[[13,25]])
        self.assertEqual(p['max_ankle_slide_m'],.012)

    def test_reject_concurrent_or_missing_side(self):
        cfg=fixture_actor_settings()
        del cfg['right']
        with self.assertRaises(ValueError):validate_actor(cfg,120)

    def test_out_of_order_overlap_and_beyond_take(self):
        cases=[[[1,12],[12,20]],[[13,25],[1,11]],[[0,2]],[[1,121]],
               [[10,9]],[[True,2]],[[1,3.0]]]
        for windows in cases:
            with self.subTest(windows=windows),self.assertRaises(ValueError):
                check_side({**fixture_actor_settings()['left'],
                            'contact_windows':windows},max_frame=120)

    def test_reject_ambiguous_pole_and_invalid_targets(self):
        for bad in [[0,0,0],[0,.001,0],[float('nan'),.2,0],
                    [0,.2,float('inf')],['x',.2,0], [False,.2,0], [0,.2]]:
            with self.subTest(value=bad),self.assertRaises(ValueError):
                check_side({**fixture_actor_settings()['left'],
                            'pole_offset_actor_m':bad},max_frame=120)
        with self.assertRaises(ValueError):
            check_side({**fixture_actor_settings()['left'],
                        'anchor_pull_to_hip_m':.07},max_frame=120)

    def test_bounded_correction_sliding_and_no_implicit_soles(self):
        for key,value in [('max_ankle_correction_m',.4),
                          ('max_ankle_slide_m',.0),
                          ('max_ankle_slide_m',float('nan')),
                          ('max_ankle_correction_m',False)]:
            cfg=fixture_actor_settings();cfg[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_actor(cfg,120)

    def test_native_fixed_scripts_parse_with_no_model_code(self):
        ast.parse(FOOTLOCK_BUILD)
        ast.parse(FOOTLOCK_AUDIT)
        self.assertIn('solve(hip,local_target,local_pole,thigh,shin)',FOOTLOCK_BUILD)
        self.assertIn('bone.keyframe_insert',FOOTLOCK_BUILD)
        self.assertIn('bpy.ops.wm.save_as_mainfile',FOOTLOCK_BUILD)
        self.assertIn('sc.frame_set(n)',FOOTLOCK_AUDIT)


class ContactApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.studio,self.pid,self.sid,self.actor=make_fixture(Path(self.tmp.name))
        self.service=FootLockPlan(self.studio)
        self.pkg={'leg_identity':{'ik_authorized':False,'approval_sha':'a'*64,
                                  'retarget_dependency_sha':'b'*64,
                                  'actors':[{'instance_id':self.actor}]},
                  'retarget':{'approval_sha':'c'*64},
                  'character':{'approval_sha':'d'*64},
                  'take':{'shots':[{'stop_frame':121}]}}
        self.source=(self.pkg,'e'*64)
        self.stub=patch.object(FootLockPlan,'_source',return_value=self.source)
        self.stub.start()
    def tearDown(self):
        self.stub.stop()
        self.tmp.cleanup()

    def test_no_export_without_authored_approval(self):
        p=self.service.create(self.pid,self.sid)
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)
        with self.assertRaises(RuntimeError):self.service.approve(self.pid,self.sid,p['revision'])
        p=self.service.configure(self.pid,self.sid,self.actor,fixture_actor_settings(),p['revision'])
        with self.assertRaises(RuntimeError):self.service.configure(self.pid,self.sid,self.actor,fixture_actor_settings(),0)
        self.assertEqual(p['revision'],1)
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)
        self.service.approve(self.pid,self.sid,p['revision'])
        exported=self.service.export(self.pid,self.sid)['foot_lock']
        self.assertEqual(exported['leg_identity_approval_sha'],'a'*64)
        self.assertEqual(exported['identity_sha'],'e'*64)
        self.assertEqual(exported['actors'][0]['instance_id'],self.actor)

    def test_upstream_identity_stale_refuses_export(self):
        p=self.service.create(self.pid,self.sid)
        p=self.service.configure(self.pid,self.sid,self.actor,fixture_actor_settings(),p['revision'])
        p=self.service.approve(self.pid,self.sid,p['revision'])
        with patch.object(FootLockPlan,'_source',return_value=(self.pkg,'f'*64)):
            self.assertTrue(self.service.read(self.pid,self.sid)['stale'])
            with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)

    def test_persistence_and_cross_project_refusal(self):
        p=self.service.create(self.pid,self.sid)
        p=self.service.configure(self.pid,self.sid,self.actor,fixture_actor_settings(),p['revision'])
        fresh=FootLockPlan(Studio(self.studio.db_path))
        self.assertEqual(fresh.read(self.pid,self.sid)['actors'],p['actors'])
        other=self.studio.create_project('Unrelated','')['id']
        with self.assertRaises(KeyError):fresh.read(other,self.sid)
        with self.assertRaises(KeyError):
            fresh.configure(self.pid,self.sid,'foreign_actor',fixture_actor_settings(),1)


def synthetic_audit_pair():
    root=[1.,0,0,0,0,1.,0,0,0,0,1.,0,0,0,0,1.]
    m={'hip':[0,0,1], 'knee':[0,0,.6], 'ankle':[0,0,.2], 'toe':[0,.1,.2],
       'segment_lengths_local_m':[.4,.4],
       'rotations':{'hip':[1.,0,0,0],'knee':[1.,0,0,0]}}
    frame={'root':{'person':root[:]},'camera':{'camera':{'matrix':root[:],'lens_mm':50.}},
           'legs':{'person':{'left':copy.deepcopy(m),'right':copy.deepcopy(m)}}}
    baseline={'passed':True,'mode':'baseline','cut_markers':[[1,'camera']],
              'frames':{'1':copy.deepcopy(frame),'2':copy.deepcopy(frame)}}
    after=copy.deepcopy(baseline);after['mode']='output'
    after['frames']['1']['legs']['person']['left']['rotations']['hip'][0]=.98
    after['frames']['2']['legs']['person']['left']['rotations']['hip'][0]=.98
    pkg={'foot_lock':{'actors':[{'instance_id':'person','config':{
         'left':{'anchor_pull_to_hip_m':0.},
         'right':{'anchor_pull_to_hip_m':0.},
         'max_ankle_slide_m':.01}}]}}
    anchors={'left':[{'start':1,'end':2,'ankle_target_world_m':[0,0,.2]}],
             'right':[]}
    bake={'actors':{'person':{'anchors':anchors}}}
    return baseline,after,bake,pkg


class IndependentEvidenceComparisonTests(unittest.TestCase):
    def test_valid_unchanged_root_camera_bone_lengths(self):
        b,a,p,pkg=synthetic_audit_pair()
        r=independently_compare(b,a,p,pkg)
        self.assertEqual(r['status'],'passed_native_ankle_lock_only')

    def test_reject_root_movement_and_camera_change(self):
        for change in ('root','camera','cuts'):
            b,a,p,pkg=synthetic_audit_pair()
            if change=='root':a['frames']['2']['root']['person'][12]=.1
            if change=='camera':a['frames']['2']['camera']['camera']['lens_mm']=52
            if change=='cuts':a['cut_markers']=[]
            with self.subTest(change=change),self.assertRaises(ValueError):
                independently_compare(b,a,p,pkg)

    def test_reject_sliding_and_length_change(self):
        for change in ('slide','bone'):
            b,a,p,pkg=synthetic_audit_pair()
            if change=='slide':a['frames']['2']['legs']['person']['left']['ankle'][0]=.1
            if change=='bone':a['frames']['2']['legs']['person']['left']['segment_lengths_local_m'][0]=.5
            with self.subTest(change=change),self.assertRaises(ValueError):
                independently_compare(b,a,p,pkg)

    def test_refuse_unpermitted_pose_change_in_noncontact_window(self):
        b,a,p,pkg=synthetic_audit_pair()
        a['frames']['2']['legs']['person']['right']['rotations']['knee'][0]=.5
        with self.assertRaises(ValueError):independently_compare(b,a,p,pkg)


if __name__=='__main__':unittest.main()
