"""Retarget calibration endpoint and ZIP tests: REST cannot bypass approvals."""
import unittest,tempfile
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_retarget import DEFAULT_LIMITS

class RetargetAPITests(unittest.TestCase):
    def setUp(self):
        from tests.test_retarget import RetargetTests
        self.case=RetargetTests('test_create_has_explicit_defaults_and_needs_approval')
        self.case.setUp()
        self.original=nvp_api.studio
        nvp_api.studio=self.case.studio
        self.client=TestClient(nvp_api.app)
        self.url=f'/api/projects/{self.case.pid}/production/scenes/{self.case.sid}/retarget'

    def tearDown(self):
        self.client.close();nvp_api.studio=self.original;self.case.tearDown()

    def test_rejected_export_and_approval_flow(self):
        self.assertEqual(self.client.get(self.url+'/bundle').status_code,404)
        r=self.client.post(self.url);self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.get(self.url+'/bundle').status_code,409)
        r=self.client.post(self.url+'/configure',json={
            'actor_instance_id':self.case.actor,'expected_revision':0,
            'joint_limits_deg':{**DEFAULT_LIMITS,'head':65},
            'contact_frames':[1],'contact_tolerance_m':.09,
            'max_ground_penetration_m':.09})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['revision'],1)
        self.assertEqual(self.client.post(self.url+'/approve',json={'expected_revision':0}).status_code,409)
        r=self.client.post(self.url+'/approve',json={'expected_revision':1})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(self.client.get(self.url+'/history').json()),3)
        data=self.client.get(self.url+'/bundle')
        self.assertEqual(data.status_code,200,data.text[:200] if data.status_code!=200 else '')
        with ZipFile(BytesIO(data.content)) as z:
            self.assertIn('build_retargeted.py',z.namelist())
            self.assertIn('retarget.json',z.namelist())
            self.assertTrue(any(s.endswith('.glb') for s in z.namelist()))

    def test_api_rejects_unknown_actor_and_infinite_settings(self):
        self.client.post(self.url)
        body={'actor_instance_id':'outsider','expected_revision':0,
              'joint_limits_deg':DEFAULT_LIMITS,'contact_frames':[1],
              'contact_tolerance_m':.1,'max_ground_penetration_m':.05}
        self.assertEqual(self.client.post(self.url+'/configure',json=body).status_code,404)
        self.assertEqual(self.client.post(self.url+'/configure',json={**body,'contact_frames':[99,1]}).status_code,422)
        self.assertEqual(self.client.get(self.url).status_code,200)

if __name__=='__main__':unittest.main()
