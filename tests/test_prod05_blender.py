"""Real Blender 5.2+ acceptance: animated proxy movement and camera cuts."""
import ast
import json
import os
import tempfile
from pathlib import Path
import unittest

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence,run_shot_acceptance,SHOTS_AUDIT_SCRIPT
from backend.nvp_blender_acceptance import blender_available


class NativeShotTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.studio=Studio(self.root/'movie.sqlite')
        self.pid=self.studio.create_project('A','')['id']
        self.sid=self.studio.save_screenplay(self.pid,'INT. STUDIO - DAY\n\nMARA\nWelcome.\n',0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        self.prod.create_asset(self.pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.65]})
        p=self.prod.stage_scene(self.pid,self.sid,[8,6,3]);p=self.prod.solve_scene(self.pid,self.sid,p['plan_revision']);self.prod.approve_scene(self.pid,self.sid,p['plan_revision'])
        self.bc=BlockingCamera(self.studio)
        actor=next(x for x in self.prod.export_manifest(self.pid,self.sid)['instances'] if x['category']=='character')
        self.actor=actor
        self.bc.add_mark(self.pid,self.sid,actor['instance_id'],[actor['pose']['x']+.5,actor['pose']['y']],start_s=1,end_s=3)
        cam=self.bc.solve_shot(self.pid,self.sid,[actor['instance_id']])
        line=self.bc.dialogue(self.pid,self.sid)['dialogue'][0]
        self.bc.set_dialogue_duration(self.pid,self.sid,line['id'],.5)
        self.seq=ShotSequence(self.studio)
        start=self.seq.create(self.pid,self.sid)
        start=self.seq.add_shot(self.pid,self.sid,cam['id'],120,'single',start['revision'])
        second=self.bc.solve_shot(self.pid,self.sid,[actor['instance_id']],lens_mm=35)
        # Create a real two-camera sequence; first and second shots cover 60 frames.
        # The second solve changes dependencies: reset the still-empty sequence.
        start=self.seq.reset_draft(self.pid,self.sid,start['revision'])
        start=self.seq.add_shot(self.pid,self.sid,cam['id'],60,'single',start['revision'])
        start=self.seq.add_shot(self.pid,self.sid,second['id'],60,'reaction',start['revision'])
        start=self.seq.place_cue(self.pid,self.sid,line['id'],10,start['revision'])
        if start['review']['warnings']:
            start=self.seq.acknowledge(self.pid,self.sid,[w['code'] for w in start['review']['warnings']],start['revision'])
        self.seq.approve(self.pid,self.sid,start['revision'])

    def tearDown(self):self.t.cleanup()

    def test_native_audit_source_is_python_and_export_is_deterministic(self):
        ast.parse(SHOTS_AUDIT_SCRIPT)
        script=self.seq.blender_script(self.pid,self.sid)
        ast.parse(script)
        self.assertEqual(script,self.seq.blender_script(self.pid,self.sid))
        self.assertIn("marker.camera=obj",script)

    def test_blender_missing_does_not_claim_render(self):
        result=run_shot_acceptance(self.seq,self.pid,self.sid,self.root/'blocked',executable='blender-nvp-does-not-exist')
        self.assertEqual(result['status'],'blocked_no_blender')
        self.assertTrue(Path(result['script']).exists())

    def test_true_native_blender_camera_cut_and_motion(self):
        state=blender_available()
        if not state['available']:
            self.skipTest('Real native Blender not present in this host')
        render=os.environ.get('NVP_BLENDER_AUDIT_ONLY')!='1'
        result=run_shot_acceptance(self.seq,self.pid,self.sid,self.root/'native',render_preview=render)
        self.assertEqual(result['status'],'passed_blender' if render else 'passed_blender_audit_only',result)
        self.assertTrue(Path(result['blend']).stat().st_size>0)
        audit=json.loads(Path(result['audit']).read_text())
        self.assertTrue(audit['passed'])
        self.assertGreaterEqual(result['checks'],8)
        self.assertTrue(any(x['check'].startswith('pose:') for x in audit['checks']))
        if render:self.assertTrue(Path(result['preview']).stat().st_size>0)
        else:self.assertIsNone(result['preview'])

if __name__=='__main__':unittest.main()
