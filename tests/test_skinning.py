"""PROD-06B: bounded, creator-approved weighted mesh and pose calibration."""
import ast
import json
import math
from pathlib import Path
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_rig_motion import RigMotion
from backend.nvp_skinning import (SkinnedPerformance,SKIN_SCRIPT,SKIN_AUDIT_SCRIPT,
                                  inject_skin_script,run_skin_acceptance)
from backend.nvp_blender_acceptance import blender_available


def make_fixture(root):
    studio=Studio(root/'studio.sqlite')
    pid=studio.create_project('Rigged scene','')['id']
    sid=studio.save_screenplay(pid,'INT. STUDIO - DAY\n\nMARA\nHello.\n',0)['scenes'][0]['id']
    prod=ProductionScene(studio)
    prod.create_asset(pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.65]})
    p=prod.stage_scene(pid,sid,[8,6,3]);p=prod.solve_scene(pid,sid,p['plan_revision'])
    prod.approve_scene(pid,sid,p['plan_revision'])
    actor=next(x['instance_id'] for x in prod.export_manifest(pid,sid)['instances'] if x['category']=='character')
    bc=BlockingCamera(studio)
    cam=bc.solve_shot(pid,sid,[actor]);line=bc.dialogue(pid,sid)['dialogue'][0]
    bc.set_dialogue_duration(pid,sid,line['id'],.5)
    seq=ShotSequence(studio)
    t=seq.create(pid,sid);t=seq.add_shot(pid,sid,cam['id'],120,'single',t['revision'])
    t=seq.place_cue(pid,sid,line['id'],10,t['revision'])
    if t['review']['warnings']:
        t=seq.acknowledge(pid,sid,[x['code'] for x in t['review']['warnings']],t['revision'])
    seq.approve(pid,sid,t['revision'])
    rig=RigMotion(studio)
    clip=rig.register(pid,'Wave','creator_owned',frames=[
        {'frame':0,'joints':{'arm_left':[10,0,0], 'head':[0,0,0]}},
        {'frame':12,'joints':{'arm_left':[70,0,0], 'head':[0,0,10]}},
        {'frame':24,'joints':{'arm_left':[10,0,0], 'head':[0,0,0]}}
    ])['clip_id']
    s=rig.create(pid,sid);s=rig.attach(pid,sid,actor,clip,1,s['revision'])
    rig.approve(pid,sid,s['revision'])
    return studio,pid,sid,actor


class SkinnedPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.studio,self.pid,self.sid,self.actor=make_fixture(self.root)
        self.skin=SkinnedPerformance(self.studio)

    def tearDown(self):self.temp.cleanup()

    def approved(self):
        s=self.skin.create(self.pid,self.sid)
        s=self.skin.calibrate(self.pid,self.sid,self.actor,'arm_left',[10,0,0],[0,0,0],s['revision'])
        return self.skin.approve(self.pid,self.sid,s['revision'])

    def test_session_create_persists_and_needs_approval(self):
        s=self.skin.create(self.pid,self.sid)
        self.assertEqual(s['revision'],0)
        self.assertEqual(s['status'],'draft')
        with self.assertRaisesRegex(RuntimeError,'approved'):
            self.skin.export(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'exists'):
            self.skin.create(self.pid,self.sid)
        other=SkinnedPerformance(Studio(self.studio.db_path))
        self.assertEqual(other.read(self.pid,self.sid)['actors'],s['actors'])

    def test_explicit_neutral_pose_persisted_and_approval_pinned(self):
        result=self.approved()
        self.assertEqual(result['status'],'approved')
        payload=self.skin.export(self.pid,self.sid)
        self.assertEqual(payload['skin']['actors'][0]['calibrations']['arm_left']['source_neutral_deg'],[10.,0.,0.])
        self.assertEqual(payload['skin']['actors'][0]['calibrations']['arm_left']['author'],'director')
        self.assertEqual(len(self.skin.history(self.pid,self.sid)),3)
        reopened=SkinnedPerformance(Studio(self.studio.db_path))
        self.assertEqual(reopened.export(self.pid,self.sid)['skin'],payload['skin'])

    def test_reject_invalid_actor_role_and_vectors(self):
        s=self.skin.create(self.pid,self.sid)
        with self.assertRaises(ValueError):self.skin.calibrate(self.pid,self.sid,self.actor,'tail',[0,0,0],[0,0,0],0)
        with self.assertRaises(KeyError):self.skin.calibrate(self.pid,self.sid,'not-actor','head',[0,0,0],[0,0,0],0)
        for bad in [[0,0],[0,0,181],[float('nan'),0,0],[float('inf'),0,0],[False,0,0], '0 0 0']:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):self.skin.calibrate(self.pid,self.sid,self.actor,'head',bad,[0,0,0],0)
        self.assertEqual(self.skin.read(self.pid,self.sid)['revision'],0)

    def test_cannot_change_approved_or_use_old_revision(self):
        self.skin.create(self.pid,self.sid)
        with self.assertRaises(RuntimeError):
            self.skin.approve(self.pid,self.sid,99)
        session=self.skin.calibrate(self.pid,self.sid,self.actor,'head',[0,0,0],[0,0,0],0)
        with self.assertRaises(RuntimeError):
            self.skin.calibrate(self.pid,self.sid,self.actor,'head',[0,0,0],[0,0,0],0)
        self.skin.approve(self.pid,self.sid,session['revision'])
        with self.assertRaises(RuntimeError):
            self.skin.calibrate(self.pid,self.sid,self.actor,'head',[0,0,0],[0,0,0],2)

    def test_cross_project_skin_cannot_be_read(self):
        self.skin.create(self.pid,self.sid)
        other=self.studio.create_project('Unrelated film','')['id']
        with self.assertRaises(KeyError):self.skin.read(other,self.sid)

    def test_motion_change_invalidates_approved_skin(self):
        self.approved()
        seq=ShotSequence(self.studio)
        s=seq.read(self.pid,self.sid)
        seq.new_revision(self.pid,self.sid,s['revision'])
        with self.assertRaises(RuntimeError):self.skin.export(self.pid,self.sid)

    def test_generator_parses_and_is_deterministic(self):
        self.approved()
        ast.parse(SKIN_SCRIPT)
        ast.parse(SKIN_AUDIT_SCRIPT)
        s=self.skin.blender_script(self.pid,self.sid)
        ast.parse(s)
        self.assertEqual(s,self.skin.blender_script(self.pid,self.sid))
        self.assertIn('NVP_ARMATURE_DEFORM',s)
        self.assertIn('rotation_quaternion=target @ (src.inverted() @ animated)',s)
        with self.assertRaises(RuntimeError):inject_skin_script('not a Blender script',{})

    def test_missing_blender_is_not_a_faked_success(self):
        self.approved()
        result=run_skin_acceptance(self.skin,self.pid,self.sid,self.root/'no_blender',executable='missing-nvp-blender')
        self.assertEqual(result['status'],'blocked_no_blender')
        self.assertTrue(Path(result['script']).is_file())

    def test_native_blender_skin_and_rotation_when_present(self):
        if not blender_available()['available']:
            self.skipTest('Real Blender executable missing')
        self.approved()
        import os
        render=os.environ.get('NVP_BLENDER_AUDIT_ONLY')!='1'
        result=run_skin_acceptance(self.skin,self.pid,self.sid,self.root/'real_blender',render_preview=render)
        self.assertEqual(result['status'],'passed_blender' if render else 'passed_blender_audit_only',result)
        report=json.loads(Path(result['audit']).read_text('utf8'))
        self.assertTrue(report['passed'])
        self.assertTrue(any(x['check'].startswith('real_skin_deformation:') for x in report['checks']))
        self.assertTrue(any(x['check'].startswith('calibrated_pose:') for x in report['checks']))
        self.assertTrue(Path(result['blend']).stat().st_size>0)

if __name__=='__main__':unittest.main()
