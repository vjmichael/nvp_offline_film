"""PROD-06D unit and persistence acceptance, no installed Blender required."""
import ast
import json
import math
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_skinning import SkinnedPerformance
from backend.nvp_character_assets import CharacterAssets
from backend.nvp_retarget import (RetargetCalibration, DEFAULT_LIMITS, change_rest_frame,
                                   valid_quat, RETARGET_SCRIPT, RETARGET_AUDIT_SCRIPT,
                                   run_retarget_acceptance, inject_retarget_script)
from tests.test_character_assets import synthetic_glb, ROLES
from tests.test_skinning import make_fixture


class RestMathTests(unittest.TestCase):
    def test_identical_rest_does_not_change_rotation(self):
        q=(math.cos(math.pi/8),math.sin(math.pi/8),0,0)
        got=change_rest_frame(q,(1,0,0,0),(1,0,0,0))
        self.assertAlmostEqual(got[0],q[0]);self.assertAlmostEqual(got[1],q[1])

    def test_right_angle_rest_frame_rotates_axis(self):
        half=math.sqrt(.5); q=(half,half,0,0)
        result=change_rest_frame(q,(1,0,0,0),(half,0,0,half))
        self.assertAlmostEqual(abs(result[2]),half,places=6)
        self.assertAlmostEqual(abs(result[1]),0,places=6)

    def test_quaternion_normalization_and_invalid_inputs(self):
        self.assertAlmostEqual(valid_quat((2,0,0,0))[0],1)
        for q in [(0,0,0,0),[0,0,0],[float('nan'),0,0,0],[False,0,0,0],None]:
            with self.subTest(q=q),self.assertRaises(ValueError):valid_quat(q)

    def test_code_templates_are_parseable(self):
        ast.parse(RETARGET_SCRIPT);ast.parse(RETARGET_AUDIT_SCRIPT)
        with self.assertRaises(RuntimeError):inject_retarget_script('unrecognized',{})


class RetargetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.studio,self.pid,self.sid,self.actor=make_fixture(self.root)
        skin=SkinnedPerformance(self.studio);s=skin.create(self.pid,self.sid)
        skin.approve(self.pid,self.sid,s['revision'])
        char=CharacterAssets(self.studio)
        asset=char.register(self.pid,synthetic_glb(),'creator_owned')
        s=char.create(self.pid,self.sid)
        s=char.bind(self.pid,self.sid,self.actor,asset['asset_id'],{r:r for r in ROLES},s['revision'])
        char.approve(self.pid,self.sid,s['revision'])
        self.service=RetargetCalibration(self.studio)

    def tearDown(self):self.temp.cleanup()

    def approved(self):
        session=self.service.create(self.pid,self.sid)
        return self.service.approve(self.pid,self.sid,session['revision'])

    def test_create_has_explicit_defaults_and_needs_approval(self):
        s=self.service.create(self.pid,self.sid)
        self.assertEqual(s['status'],'draft')
        self.assertEqual(s['actors'][0]['contact_frames'],[1])
        self.assertEqual(s['actors'][0]['joint_limits_deg'],DEFAULT_LIMITS)
        with self.assertRaisesRegex(RuntimeError,'approved'):
            self.service.export(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'exists'):self.service.create(self.pid,self.sid)

    def test_configure_requires_all_bones_and_fresh_revision(self):
        s=self.service.create(self.pid,self.sid)
        options=dict(joint_limits_deg={**DEFAULT_LIMITS,'arm_left':110},contact_frames=[1],
                     contact_tolerance_m=.12,max_ground_penetration_m=.05)
        s=self.service.configure(self.pid,self.sid,self.actor,s['revision'],**options)
        self.assertEqual(s['revision'],1)
        with self.assertRaises(RuntimeError):
            self.service.configure(self.pid,self.sid,self.actor,0,**options)
        s=self.service.approve(self.pid,self.sid,s['revision'])
        self.assertEqual(s['status'],'approved')
        with self.assertRaises(RuntimeError):self.service.configure(self.pid,self.sid,self.actor,2,**options)

    def test_invalid_or_spoofed_approval_settings(self):
        self.service.create(self.pid,self.sid)
        args=dict(joint_limits_deg=DEFAULT_LIMITS,contact_frames=[1],
                  contact_tolerance_m=.1,max_ground_penetration_m=.05)
        for broken in [{**args,'joint_limits_deg':{}},
                       {**args,'joint_limits_deg':{**DEFAULT_LIMITS,'hips':float('nan')}},
                       {**args,'joint_limits_deg':{**DEFAULT_LIMITS,'hips':False}},
                       {**args,'contact_frames':[1,1]},
                       {**args,'contact_frames':[-1]},
                       {**args,'contact_frames':[999999]},
                       {**args,'contact_tolerance_m':float('inf')},
                       {**args,'max_ground_penetration_m':1}]:
            with self.subTest(broken=broken),self.assertRaises(ValueError):
                self.service.configure(self.pid,self.sid,self.actor,0,**broken)

    def test_cross_project_refuses_and_reload_persists(self):
        self.approved()
        other=self.studio.create_project('Elsewhere','')['id']
        with self.assertRaises(KeyError):self.service.read(other,self.sid)
        reopened=RetargetCalibration(Studio(self.studio.db_path))
        self.assertEqual(reopened.export(self.pid,self.sid)['retarget'],self.service.export(self.pid,self.sid)['retarget'])
        self.assertEqual(len(reopened.history(self.pid,self.sid)),2)

    def test_approved_bundle_contains_full_provenance(self):
        self.approved()
        pkg=self.service.export(self.pid,self.sid)
        self.assertEqual(pkg['retarget']['format'],'nvp.retarget.approved.v1')
        self.assertEqual(pkg['character']['rights_status'],'creator_declared_not_independently_verified')
        path=self.root/'pack'
        self.service.export_bundle(self.pid,self.sid,path)
        self.assertTrue((path/'retarget.json').is_file())
        self.assertTrue((path/'licenses.json').is_file())
        self.assertTrue(any((path/'assets').glob('*.glb')))
        source=(path/'build_retargeted.py').read_text()
        ast.parse(source)
        self.assertIn('NVP_CHARACTER_RIG_',source)
        self.assertIn('alignment_quat',source)

    def test_changes_to_approved_take_invalidate_export(self):
        self.approved()
        from backend.nvp_shot_sequence import ShotSequence
        seq=ShotSequence(self.studio)
        current=seq.read(self.pid,self.sid)
        seq.new_revision(self.pid,self.sid,current['revision'])
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)

    def test_missing_blender_is_blocked_not_success(self):
        self.approved()
        result=run_retarget_acceptance(self.service,self.pid,self.sid,self.root/'native',executable='definitely-no-blender-executable')
        self.assertEqual(result['status'],'blocked_no_blender')
        self.assertTrue((self.root/'native'/'retarget.json').exists())

if __name__=='__main__':unittest.main()
