"""Cross-feature frozen NVP-PROD-01..04 workflow acceptance (no fake Blender)."""
from pathlib import Path
import tempfile
import unittest
import json
import hashlib
import trimesh

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene,verify_layout
from backend.nvp_world_state import WorldState
from backend.nvp_mesh_assets import MeshAssets
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_blender_acceptance import run_acceptance,blender_available

SCRIPT='''INT. FARMHOUSE - NIGHT

MARA
Where is the stolen key?

BOB
I do not know.
'''

class PipelineAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.studio=Studio(self.path/'movie.sqlite3')
        self.pid=self.studio.create_project('The Key','Story about deception')['id']
        self.sid=self.studio.save_screenplay(self.pid,SCRIPT,0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        self.mara=self.prod.create_asset(self.pid,{'name':'MARA','category':'character','dimensions':[.4,.4,1.7]})
        self.bob=self.prod.create_asset(self.pid,{'name':'BOB','category':'character','dimensions':[.4,.4,1.7]})
        self.table=self.prod.create_asset(self.pid,{'name':'Oak Table','category':'furniture',
             'dimensions':[1.8,.8,.75],'anchors':{'east_edge':[.9,0,.7]}})
        stage=self.prod.stage_scene(self.pid,self.sid,[10,8,3])
        stage=self.prod.add_instance(self.pid,self.sid,self.table['asset_id'],'table',stage['plan_revision'],wall='north')
        stage=self.prod.solve_scene(self.pid,self.sid,stage['plan_revision'])
        self.prod.approve_scene(self.pid,self.sid,stage['plan_revision'])
        self.manifest=self.prod.export_manifest(self.pid,self.sid)
        self.actors={x['name']:x['instance_id'] for x in self.manifest['instances'] if x['category']=='character'}
        self.world=WorldState(self.studio)
        self.mesh=MeshAssets(self.studio)
        self.block=BlockingCamera(self.studio)

    def tearDown(self):self.temp.cleanup()

    def test_complete_offline_production_chain(self):
        scene=trimesh.Scene();scene.add_geometry(trimesh.creation.box(extents=[1.8,.8,.75]))
        payload=scene.export(file_type='glb')
        registered=self.mesh.register(self.pid,self.table['asset_id'],payload,'CC-BY-4.0',
                                      'Original sculptor','https://example.invalid/model')
        self.assertEqual(registered['status'],'registered')
        ai=self.world.propose_ai(self.pid,self.sid,'table','visible',False,0,'dramatic reveal later')
        self.assertEqual(self.world.read(self.pid,self.sid)['fields'],{})
        self.world.decide(self.pid,self.sid,ai['proposal_id'],'reject',0)
        self.world.set_human(self.pid,self.sid,'table','visible',True,0)
        self.assertTrue(self.world.read(self.pid,self.sid)['fields']['table']['visible']['locked'])
        dialog=self.block.dialogue(self.pid,self.sid)
        self.assertEqual(len(dialog['dialogue']),2)
        self.assertFalse(dialog['unresolved_speakers'])
        first=dialog['dialogue'][0]
        self.block.set_dialogue_duration(self.pid,self.sid,first['id'],2.4)
        self.block.set_listeners(self.pid,self.sid,first['id'],[self.actors['BOB']])
        mara=next(item for item in self.manifest['instances'] if item['name']=='MARA')
        goal=[mara['pose']['x']+.5,mara['pose']['y']]
        mark=self.block.add_mark(self.pid,self.sid,self.actors['MARA'],goal,start_s=0,end_s=3)
        self.assertEqual(mark['path']['points'][-1],goal)
        shot=self.block.solve_shot(self.pid,self.sid,[self.actors['MARA']],lens_mm=50)
        self.assertLessEqual(shot['solution']['max_residual'],.02)
        exported=self.mesh.export_bundle(self.pid,self.sid,self.path/'bundle')
        self.assertEqual(exported['meshes'],1)
        self.assertTrue((self.path/'bundle'/'build_scene.py').is_file())
        self.assertTrue((self.path/'bundle'/'licenses.json').is_file())
        self.assertTrue((self.path/'bundle'/'assets'/(registered['sha256']+'.glb')).is_file())
        self.assertTrue(self.mesh.list(self.pid))
        # Database restart must not reassign production actor/asset IDs.
        reopened=BlockingCamera(Studio(self.studio.db_path))
        self.assertEqual(reopened.marks(self.pid,self.sid)[0]['id'],mark['id'])
        self.assertEqual(reopened.cameras(self.pid,self.sid)[0]['id'],shot['id'])
        self.assertEqual(reopened.dialogue(self.pid,self.sid)['dialogue'][0]['listener_instance_ids'],[self.actors['BOB']])
        self.assertTrue(WorldState(Studio(self.studio.db_path)).read(self.pid,self.sid)['fields']['table']['visible']['locked'])

    def test_native_blender_gate_is_never_faked(self):
        result=run_acceptance(self.prod,self.pid,self.sid,self.path/'native')
        expected='passed_blender' if blender_available()['available'] else 'blocked_no_blender'
        self.assertEqual(result['status'],expected,result)
        if result['status']=='passed_blender':
            self.assertGreater(Path(result['blend']).stat().st_size,0)
            self.assertGreater(Path(result['preview']).stat().st_size,0)

    def test_script_change_invalidates_world_camera_and_meshpack(self):
        self.studio.save_screenplay(self.pid,SCRIPT.replace('stolen key','silver key'),1)
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.world.export_manifest(self.pid,self.sid)
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.mesh.export_bundle(self.pid,self.sid,self.path/'bad')
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.block.dialogue(self.pid,self.sid)

if __name__=='__main__':unittest.main()
