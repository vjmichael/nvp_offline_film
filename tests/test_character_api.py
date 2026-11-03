"""PROD-06C API upload budgets, project scope, durable approvals and ZIP handoff."""
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_skinning import SkinnedPerformance
from tests.test_character_assets import synthetic_glb,ROLES
from tests.test_skinning import make_fixture


class RiggedCharacterAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=nvp_api.studio
        self.studio,self.pid,self.sid,self.actor=make_fixture(Path(self.temp.name))
        skin=SkinnedPerformance(self.studio);session=skin.create(self.pid,self.sid)
        skin.approve(self.pid,self.sid,session['revision'])
        nvp_api.studio=self.studio;self.client=TestClient(nvp_api.app)
        self.assets=f'/api/projects/{self.pid}/production/rigged-characters'
        self.scene=f'/api/projects/{self.pid}/production/scenes/{self.sid}/rigged-characters'

    def tearDown(self):
        self.client.close();nvp_api.studio=self.original;self.temp.cleanup()

    def uploaded(self):
        r=self.client.post(self.assets+'?license_code=creator_owned',content=synthetic_glb(),
                           headers={'content-type':'model/gltf-binary'})
        self.assertEqual(r.status_code,201,r.text)
        return r.json()['asset_id']

    def test_import_register_approve_zip_and_history(self):
        aid=self.uploaded()
        self.assertEqual(len(self.client.get(self.assets).json()),1)
        r=self.client.post(self.scene);self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.get(self.scene+'/bundle').status_code,409)
        r=self.client.post(self.scene+'/bind',json={
            'actor_instance_id':self.actor,'character_asset_id':aid,'role_map':{x:x for x in ROLES},
            'expected_revision':r.json()['revision'],'uniform_scale':1})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.post(self.scene+'/approve',json={'expected_revision':r.json()['revision']})
        self.assertEqual(r.status_code,200,r.text)
        data=self.client.get(self.scene+'/bundle')
        self.assertEqual(data.status_code,200,data.text[:180] if data.status_code!=200 else '')
        with ZipFile(BytesIO(data.content)) as z:
            self.assertIn('build_characters.py',z.namelist())
            self.assertIn('licenses.json',z.namelist())
            self.assertEqual(len([x for x in z.namelist() if x.endswith('.glb')]),1)
        self.assertEqual(len(self.client.get(self.scene+'/history').json()),3)

    def test_reject_foreign_ids_missing_license_and_oversized_binary(self):
        r=self.client.post(self.assets+'?license_code=CC-BY-4.0',content=synthetic_glb())
        self.assertEqual(r.status_code,422)
        r=self.client.post(self.assets+'?license_code=creator_owned',content=b'x'* (32*1024*1024+1))
        self.assertEqual(r.status_code,413)
        wrong=self.studio.create_project('Not the film','')['id']
        r=self.client.get(self.assets.replace(self.pid,wrong))
        self.assertEqual(r.json(),[])

    def test_reject_invalid_director_map(self):
        aid=self.uploaded()
        self.client.post(self.scene)
        r=self.client.post(self.scene+'/bind',json={
            'actor_instance_id':self.actor,'character_asset_id':aid,
            'role_map':{'head':'hips'},'expected_revision':0})
        self.assertEqual(r.status_code,422)

if __name__=='__main__':unittest.main()
