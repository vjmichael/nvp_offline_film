"""Verify PROD-06A API cannot bypass director approval or project-scoped clips."""
import tempfile
from pathlib import Path
import unittest
from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence
from tests.test_rig_motion import BVH

class MotionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        old=nvp_api.studio
        self.old=old
        nvp_api.studio=Studio(Path(self.tmp.name)/'test.sqlite')
        self.client=TestClient(nvp_api.app)
        self.pid=nvp_api.studio.create_project('Api film','')['id']
        self.sid=nvp_api.studio.save_screenplay(self.pid,'INT. STUDIO - DAY\n\nMARA\nHello.\n',0)['scenes'][0]['id']
        prod=ProductionScene(nvp_api.studio)
        prod.create_asset(self.pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.65]})
        p=prod.stage_scene(self.pid,self.sid,[8,6,3]);p=prod.solve_scene(self.pid,self.sid,p['plan_revision']);prod.approve_scene(self.pid,self.sid,p['plan_revision'])
        self.actor=next(x['instance_id'] for x in prod.export_manifest(self.pid,self.sid)['instances'] if x['category']=='character')
        bc=BlockingCamera(nvp_api.studio)
        cam=bc.solve_shot(self.pid,self.sid,[self.actor]);line=bc.dialogue(self.pid,self.sid)['dialogue'][0]
        bc.set_dialogue_duration(self.pid,self.sid,line['id'],0.5)
        seq=ShotSequence(nvp_api.studio)
        s=seq.create(self.pid,self.sid);s=seq.add_shot(self.pid,self.sid,cam['id'],120,'single',s['revision']);s=seq.place_cue(self.pid,self.sid,line['id'],10,s['revision'])
        if s['review']['warnings']:s=seq.acknowledge(self.pid,self.sid,[x['code'] for x in s['review']['warnings']],s['revision'])
        seq.approve(self.pid,self.sid,s['revision'])
        self.prefix=f'/api/projects/{self.pid}/production/scenes/{self.sid}/rig-motion'
    def tearDown(self):
        self.client.close();nvp_api.studio=self.old;self.tmp.cleanup()

    def test_api_bvh_to_approved_blender_script(self):
        r=self.client.post(f'/api/projects/{self.pid}/production/motion-clips/bvh',json={
            'name':'Arm wave','license':'creator_owned','bvh':BVH,
            'mapping':{'hips':'Hips','arm_left':'LeftArm'}})
        self.assertEqual(r.status_code,201,r.text);clip=r.json()['clip_id']
        s=self.client.post(self.prefix);self.assertEqual(s.status_code,201,s.text)
        self.assertEqual(self.client.get(self.prefix+'/blender-script').status_code,409)
        r=self.client.post(self.prefix+'/attach',json={'actor_instance_id':self.actor,'clip_id':clip,'start_frame':1,'expected_revision':0})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.post(self.prefix+'/approve',json={'expected_revision':r.json()['revision']})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.get(self.prefix+'/blender-script')
        self.assertEqual(r.status_code,200,r.text)
        self.assertIn('NVP_RIG_',r.json()['script'])
        self.assertEqual(self.client.get(self.prefix+'/history').status_code,200)

    def test_api_bvh_rejects_malicious_mapping_and_unknown_actor(self):
        r=self.client.post(f'/api/projects/{self.pid}/production/motion-clips/bvh',json={
            'name':'Arm','license':'CC0','bvh':BVH,'mapping':{'fake':'LeftArm'}})
        self.assertEqual(r.status_code,422)
        s=self.client.post(self.prefix)
        self.assertEqual(s.status_code,201,s.text)
        r=self.client.post(self.prefix+'/attach',json={'actor_instance_id':'OTHER','clip_id':'MC_absent','start_frame':1,'expected_revision':0})
        self.assertEqual(r.status_code,404)

if __name__=='__main__':unittest.main()
