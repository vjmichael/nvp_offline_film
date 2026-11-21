"""PROD-06A: BVH/parser safety, approved clips, stale-state and native rig verification."""
import ast
import json
import os
import tempfile
from pathlib import Path
import unittest

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_rig_motion import (RigMotion, parse_bvh, parse_authored, RIG_SCRIPT,
                                    MOTION_AUDIT_SCRIPT, run_motion_acceptance)
from backend.nvp_blender_acceptance import blender_available

BVH='''HIERARCHY
ROOT Hips
{
 OFFSET 0 0 0
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT LeftArm
 {
  OFFSET 1 0 1
  CHANNELS 3 Zrotation Xrotation Yrotation
  End Site { OFFSET 0 0 1 }
 }
}
MOTION
Frames: 3
Frame Time: 0.0416666666666667
0 0 0 0 0 0  0 0 0
0 0 0 0 0 0  0 25 0
0 0 0 0 0 0  0 50 0
'''


def motion_samples():
    return [{'frame':0,'joints':{'arm_left':[0,0,0],'head':[0,0,0]}},
            {'frame':12,'joints':{'arm_left':[60,0,0],'head':[0,0,15]}},
            {'frame':24,'joints':{'arm_left':[0,0,0],'head':[0,0,0]}}]


class RigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.studio=Studio(self.root/'studio.sqlite')
        self.pid=self.studio.create_project('Rig scene','')['id']
        self.sid=self.studio.save_screenplay(self.pid,'INT. STUDIO - DAY\n\nMARA\nHello.\n',0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        self.prod.create_asset(self.pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.65]})
        s=self.prod.stage_scene(self.pid,self.sid,[8,6,3]);s=self.prod.solve_scene(self.pid,self.sid,s['plan_revision'])
        self.prod.approve_scene(self.pid,self.sid,s['plan_revision'])
        self.bc=BlockingCamera(self.studio)
        self.actor=next(x['instance_id'] for x in self.prod.export_manifest(self.pid,self.sid)['instances'] if x['category']=='character')
        camera=self.bc.solve_shot(self.pid,self.sid,[self.actor])
        dialogue=self.bc.dialogue(self.pid,self.sid)['dialogue'][0]
        self.bc.set_dialogue_duration(self.pid,self.sid,dialogue['id'],.5)
        self.take=ShotSequence(self.studio)
        plan=self.take.create(self.pid,self.sid)
        plan=self.take.add_shot(self.pid,self.sid,camera['id'],120,'single',plan['revision'])
        plan=self.take.place_cue(self.pid,self.sid,dialogue['id'],10,plan['revision'])
        if plan['review']['warnings']:
            plan=self.take.acknowledge(self.pid,self.sid,[x['code'] for x in plan['review']['warnings']],plan['revision'])
        self.take.approve(self.pid,self.sid,plan['revision'])
        self.rig=RigMotion(self.studio)

    def tearDown(self):self.tmp.cleanup()

    def make_clip(self):
        return self.rig.register(self.pid,'Greeting','creator_owned',frames=motion_samples())['clip_id']

    def prepared(self):
        clip=self.make_clip()
        session=self.rig.create(self.pid,self.sid)
        session=self.rig.attach(self.pid,self.sid,self.actor,clip,1,session['revision'])
        self.rig.approve(self.pid,self.sid,session['revision'])
        return clip

    def test_authored_roundtrip_approval_and_restart(self):
        clip=self.prepared()
        package=self.rig.export(self.pid,self.sid)
        self.assertEqual(package['motion']['clips'][clip]['frames'][1]['joints']['arm_left']['euler_deg'][0],60)
        second=RigMotion(Studio(self.studio.db_path))
        self.assertEqual(second.export(self.pid,self.sid)['motion'],package['motion'])
        self.assertEqual(second.read(self.pid,self.sid)['status'],'approved')
        self.assertTrue(second.history(self.pid,self.sid))

    def test_sourced_bvh_with_explicit_mapping(self):
        clip=self.rig.register(self.pid,'Imported arm','CC0',bvh=BVH,mapping={'hips':'Hips','arm_left':'LeftArm'})
        self.assertTrue(clip['root_translation_ignored'])
        self.assertEqual(clip['sample_count'],3)
        data=parse_bvh(BVH,{'arm_left':'LeftArm'})
        self.assertEqual(data['frames'][2]['joints']['arm_left'],{'euler_deg':[50.,0.,0.],'order':'ZXY'})

    def test_missing_bvh_bone_refused(self):
        with self.assertRaisesRegex(ValueError,'absent'):
            parse_bvh(BVH,{'arm_right':'DoesNotExist'})

    def test_bad_bvh_channel_count_refused(self):
        with self.assertRaisesRegex(ValueError,'channel count mismatch'):
            parse_bvh(BVH[:-4],{'hips':'Hips'})

    def test_duplicate_source_mapping_refused(self):
        with self.assertRaisesRegex(ValueError,'distinct'):
            parse_bvh(BVH,{'hips':'Hips','spine':'Hips'})

    def test_nonfinite_rotations_refused(self):
        src=BVH.replace('0 25 0','0 nan 0')
        with self.assertRaisesRegex(ValueError,'Out-of-range'):
            parse_bvh(src,{'arm_left':'LeftArm'})

    def test_bvh_source_budget_refused(self):
        with self.assertRaisesRegex(ValueError,'1 MiB'):
            parse_bvh('a'*1000001,{'hips':'Hips'})

    def test_authoring_rejects_invalid_role_and_unsafe_angles(self):
        for sample in [ [{'frame':0,'joints':{'other':[0,0,0]}},{'frame':1,'joints':{'other':[0,0,0]}}],
                        [{'frame':0,'joints':{'head':[float('nan'),0,0]}},{'frame':1,'joints':{'head':[0,0,0]}}] ]:
            with self.assertRaises(ValueError):parse_authored(sample)

    def test_no_cross_project_clip_usage(self):
        other=self.studio.create_project('Another film','')['id']
        with self.assertRaises(KeyError):
            with self.studio._connection() as db:self.rig._clip(db,other,self.make_clip())

    def test_not_approved_cannot_export(self):
        self.rig.create(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'not approved'):
            self.rig.export(self.pid,self.sid)

    def test_duplicate_session_refused(self):
        self.rig.create(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'exists'):
            self.rig.create(self.pid,self.sid)

    def test_revision_conflict_and_actor_scope(self):
        clip=self.make_clip();session=self.rig.create(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'revision'):
            self.rig.attach(self.pid,self.sid,self.actor,clip,1,42)
        with self.assertRaises(KeyError):
            self.rig.attach(self.pid,self.sid,'not-in-scene',clip,1,session['revision'])
        self.assertEqual(self.rig.read(self.pid,self.sid)['revision'],0)

    def test_overlapping_clips_refused(self):
        clip=self.make_clip();session=self.rig.create(self.pid,self.sid)
        session=self.rig.attach(self.pid,self.sid,self.actor,clip,1,session['revision'])
        with self.assertRaisesRegex(ValueError,'overlap'):
            self.rig.attach(self.pid,self.sid,self.actor,clip,10,session['revision'])

    def test_motion_exceeds_take_refused(self):
        clip=self.make_clip();session=self.rig.create(self.pid,self.sid)
        with self.assertRaisesRegex(ValueError,'exceeds'):
            self.rig.attach(self.pid,self.sid,self.actor,clip,119,session['revision'])

    def test_approval_requires_real_segment(self):
        session=self.rig.create(self.pid,self.sid)
        with self.assertRaisesRegex(ValueError,'No motion segments'):
            self.rig.approve(self.pid,self.sid,session['revision'])

    def test_cannot_edit_approved(self):
        clip=self.prepared();session=self.rig.read(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'approved'):
            self.rig.attach(self.pid,self.sid,self.actor,clip,48,session['revision'])

    def test_underlying_take_changed_blocks_export(self):
        self.prepared()
        plan=self.take.read(self.pid,self.sid)
        self.take.new_revision(self.pid,self.sid,plan['revision'])
        with self.assertRaisesRegex(RuntimeError,'approved'):
            self.rig.export(self.pid,self.sid)

    def test_blender_script_determinism_and_parse(self):
        self.prepared()
        ast.parse(RIG_SCRIPT);ast.parse(MOTION_AUDIT_SCRIPT)
        s=self.rig.blender_script(self.pid,self.sid)
        ast.parse(s)
        self.assertEqual(s,self.rig.blender_script(self.pid,self.sid))
        self.assertIn('NVP_RIG_',s)
        self.assertIn('pose.keyframe_insert',s)

    def test_no_native_blender_is_blocked(self):
        self.prepared()
        result=run_motion_acceptance(self.rig,self.pid,self.sid,self.root/'blocked',executable='missing-nvp-blender')
        self.assertEqual(result['status'],'blocked_no_blender')
        self.assertTrue(Path(result['script']).is_file())
        self.assertFalse((self.root/'blocked'/'motion.blend').exists())

    def test_real_native_blender_rig_and_keyframes(self):
        self.prepared()
        if not blender_available()['available']:
            self.skipTest('Real Blender unavailable')
        render=os.environ.get('NVP_BLENDER_AUDIT_ONLY')!='1'
        result=run_motion_acceptance(self.rig,self.pid,self.sid,self.root/'native',render_preview=render)
        self.assertEqual(result['status'],'passed_blender' if render else 'passed_blender_audit_only',result)
        self.assertGreaterEqual(result['checks'],10)
        self.assertTrue(Path(result['blend']).stat().st_size>0)
        audit=json.loads(Path(result['audit']).read_text())
        self.assertTrue(audit['passed'])
        self.assertTrue(any(c['check'].startswith('pose:') for c in audit['checks']))

if __name__=='__main__':unittest.main()
