"""PROD-02..04 API safety regressions: film scoping and approval boundaries."""
import tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
import trimesh
from backend import nvp_api
from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene

SCREEN='INT. ROOM - DAY\n\nMARA\nI can see you.\n\nBOB\nI am here.\n'

class ProdAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.studio=Studio(Path(self.tmp.name)/'db.sqlite')
        self.original=nvp_api.studio;nvp_api.studio=self.studio
        self.client=TestClient(nvp_api.app);self.client.__enter__()
        self.pid=self.studio.create_project('Film','')['id']
        self.sid=self.studio.save_screenplay(self.pid,SCREEN,0)['scenes'][0]['id']
        prod=ProductionScene(self.studio)
        self.asset=prod.create_asset(self.pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.7]})
        prod.create_asset(self.pid,{'name':'BOB','category':'character','dimensions':[.4,.4,1.7]})
        stage=prod.stage_scene(self.pid,self.sid,[8,6,3]);stage=prod.solve_scene(self.pid,self.sid,stage['plan_revision'])
        prod.approve_scene(self.pid,self.sid,stage['plan_revision'])
        self.base=f'/api/projects/{self.pid}/production/scenes/{self.sid}'

    def tearDown(self):
        self.client.__exit__(None,None,None)
        nvp_api.studio=self.original
        self.tmp.cleanup()

    def test_world_edit_and_journal(self):
        world=self.client.get(self.base+'/world');self.assertEqual(world.status_code,200)
        instance=world.json()['manifest']['instances'][0]['instance_id']
        r=self.client.post(self.base+'/world/human',json={'instance_id':instance,'field':'visible','value':False,'expected_revision':0})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['revision'],1)
        self.assertFalse(r.json()['manifest']['instances'][0]['visible'])
        self.assertEqual(len(self.client.get(self.base+'/world/history').json()),1)

    def test_stale_revision_is_409(self):
        instance=self.client.get(self.base+'/world').json()['manifest']['instances'][0]['instance_id']
        self.client.post(self.base+'/world/human',json={'instance_id':instance,'field':'visible','value':False,'expected_revision':0})
        r=self.client.post(self.base+'/world/human',json={'instance_id':instance,'field':'visible','value':True,'expected_revision':0})
        self.assertEqual(r.status_code,409)

    def test_mesh_upload_api_checks_real_glb(self):
        import trimesh
        sc=trimesh.Scene();sc.add_geometry(trimesh.creation.box(extents=(.4,.4,1.7)))
        glb=sc.export(file_type='glb')
        r=self.client.post(f'/api/projects/{self.pid}/production/assets/{self.asset["asset_id"]}/mesh',
                params={'license_code':'creator_owned'},content=glb,headers={'Content-Type':'application/octet-stream'})
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(r.json()['status'],'registered')
        self.assertEqual(len(self.client.get(f'/api/projects/{self.pid}/production/meshes').json()),1)

    def test_too_large_upload_is_413(self):
        r=self.client.post(f'/api/projects/{self.pid}/production/assets/{self.asset["asset_id"]}/mesh',
                params={'license_code':'creator_owned'},content=b'0'*(32*1024*1024+1))
        self.assertEqual(r.status_code,413)

    def test_dialogue_and_camera_api(self):
        data=self.client.get(self.base+'/dialogue').json()
        self.assertEqual(len(data['dialogue']),2)
        world=self.client.get(self.base+'/world').json()
        actor=next(i['instance_id'] for i in world['manifest']['instances'] if i['name']=='MARA')
        r=self.client.post(self.base+'/cameras',json={'subjects':[actor],'lens_mm':50,'shot_size':'medium'})
        self.assertEqual(r.status_code,201,r.text)
        self.assertTrue(r.json()['solution']['fits_all_subjects'])

    def test_bad_project_scope_is_404(self):
        self.assertEqual(self.client.get(self.base.replace(self.pid,'unknown')+'/world').status_code,404)

    def test_actual_blender_availability_is_truthful(self):
        r=self.client.get('/api/production/blender-availability')
        self.assertEqual(r.status_code,200)
        self.assertIn('available',r.json())
        self.assertTrue('version' in r.json() if r.json()['available'] else 'reason' in r.json())

if __name__=='__main__':unittest.main()
