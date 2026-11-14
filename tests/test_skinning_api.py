"""PROD-06B API cannot bypass project-scoped and director-approved skinning."""
import tempfile
from pathlib import Path
import unittest
from fastapi.testclient import TestClient
from backend import nvp_api
from tests.test_skinning import make_fixture


class SkinApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=nvp_api.studio
        self.studio,self.pid,self.sid,self.actor=make_fixture(Path(self.tmp.name))
        nvp_api.studio=self.studio
        self.client=TestClient(nvp_api.app)
        self.root=f'/api/projects/{self.pid}/production/scenes/{self.sid}/skinning'

    def tearDown(self):
        self.client.close();nvp_api.studio=self.old;self.tmp.cleanup()

    def test_approval_gates_blender_export(self):
        r=self.client.post(self.root);self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.get(self.root+'/blender-script').status_code,409)
        r=self.client.post(self.root+'/calibrate',json={
            'actor_instance_id':self.actor,'role':'arm_left',
            'source_neutral_deg':[10,0,0],'target_neutral_deg':[0,0,0],
            'expected_revision':r.json()['revision']})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.post(self.root+'/approve',json={'expected_revision':r.json()['revision']})
        self.assertEqual(r.status_code,200,r.text)
        script=self.client.get(self.root+'/blender-script')
        self.assertEqual(script.status_code,200,script.text)
        self.assertIn('NVP_WEIGHTED_GEOMETRY',script.json()['script'])
        self.assertEqual(len(self.client.get(self.root+'/history').json()),3)

    def test_bad_actor_and_invalid_pose_rejected(self):
        self.client.post(self.root)
        r=self.client.post(self.root+'/calibrate',json={
            'actor_instance_id':'fake','role':'head',
            'source_neutral_deg':[0,0,0],'target_neutral_deg':[0,0,0],
            'expected_revision':0})
        self.assertEqual(r.status_code,404)
        r=self.client.post(self.root+'/calibrate',json={
            'actor_instance_id':self.actor,'role':'head',
            'source_neutral_deg':[200,0,0],'target_neutral_deg':[0,0,0],
            'expected_revision':0})
        self.assertEqual(r.status_code,422)

    def test_cross_project_access_refused(self):
        self.client.post(self.root)
        another=self.studio.create_project('Second film','')['id']
        path=self.root.replace(self.pid,another)
        r=self.client.get(path)
        self.assertEqual(r.status_code,404)

if __name__=='__main__': unittest.main()
