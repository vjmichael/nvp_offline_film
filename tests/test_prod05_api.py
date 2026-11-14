"""NVP-PROD-05 API: approvals, input validation, stable source evidence."""
import unittest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene

class ShotSequenceAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.studio=Studio(Path(self.tmp.name)/'db.sqlite')
        self.old=nvp_api.studio;nvp_api.studio=self.studio
        self.client=TestClient(nvp_api.app);self.client.__enter__()
        self.pid=self.studio.create_project('Movie','')['id']
        self.sid=self.studio.save_screenplay(self.pid,'INT. ROOM - DAY\n\nMARA\nYes.\n',0)['scenes'][0]['id']
        prod=ProductionScene(self.studio)
        prod.create_asset(self.pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.7]})
        p=prod.stage_scene(self.pid,self.sid,[8,6,3]);p=prod.solve_scene(self.pid,self.sid,p['plan_revision']);prod.approve_scene(self.pid,self.sid,p['plan_revision'])
        self.base=f'/api/projects/{self.pid}/production/scenes/{self.sid}'
        actor=next(x['instance_id'] for x in prod.export_manifest(self.pid,self.sid)['instances'] if x['name']=='MARA')
        self.cam=self.client.post(self.base+'/cameras',json={'subjects':[actor]}).json()['id']
        self.line=self.client.get(self.base+'/dialogue').json()['dialogue'][0]['id']
        self.client.post(self.base+'/dialogue/'+self.line+'/duration',json={'duration_s':1.0})

    def tearDown(self):
        self.client.__exit__(None,None,None);nvp_api.studio=self.old;self.tmp.cleanup()

    def test_full_api_approval_and_script_download(self):
        self.assertEqual(self.client.get(self.base+'/sequence').status_code,404)
        r=self.client.post(self.base+'/sequence');self.assertEqual(r.status_code,201,r.text)
        rev=r.json()['revision']
        r=self.client.post(self.base+'/sequence/shots',json={'camera_id':self.cam,'frames':72,'expected_revision':rev})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.post(self.base+'/sequence/cues/'+self.line,json={'start_frame':1,'expected_revision':r.json()['revision']})
        self.assertEqual(r.status_code,200,r.text)
        state=r.json()
        self.assertFalse(state['review']['errors'])
        self.assertFalse(state['review']['warnings'])
        r=self.client.post(self.base+'/sequence/approve',json={'expected_revision':state['revision']})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.get(self.base+'/sequence/package').status_code,200)
        source=self.client.get(self.base+'/sequence/blender-script')
        self.assertEqual(source.status_code,200,source.text)
        self.assertIn('timeline_markers',source.json()['script'])
        self.assertGreaterEqual(len(self.client.get(self.base+'/sequence/history').json()),4)

    def test_conflicting_mutations_and_unapproved_export_blocked(self):
        r=self.client.post(self.base+'/sequence').json()
        self.assertEqual(self.client.get(self.base+'/sequence/package').status_code,409)
        self.assertEqual(self.client.post(self.base+'/sequence/shots',json={'camera_id':self.cam,'frames':24,'expected_revision':100}).status_code,409)
        self.assertEqual(self.client.post(self.base+'/sequence/shots',json={'camera_id':'unknown','frames':24,'expected_revision':0}).status_code,422)
        self.assertEqual(self.client.post(self.base+'/sequence/shots',json={'camera_id':self.cam,'frames':0,'expected_revision':0}).status_code,422)

    def test_cross_project_isolation(self):
        self.client.post(self.base+'/sequence')
        other=self.studio.create_project('Other','')['id']
        self.assertEqual(self.client.get(self.base.replace(self.pid,other)+'/sequence').status_code,404)

if __name__=='__main__':unittest.main()
