"""PROD-01 acceptance harness distinguishes offline checks from real Blender runs."""
import ast
import os
import json
from pathlib import Path
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blender_acceptance import blender_available,run_acceptance,AUDIT_SCRIPT,run_meshpack_acceptance,MESH_AUDIT_SCRIPT


class BlenderAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.studio=Studio(self.root/'db.sqlite')
        self.pid=self.studio.create_project('Staging','')['id']
        self.sid=self.studio.save_screenplay(self.pid,'INT. SET - DAY\n\nA chair.\n',0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        chair=self.prod.create_asset(self.pid,{
            'name':'Chair','category':'furniture','dimensions':[.5,.5,.9],
            'anchors':{'seat':[0,0,.5]}})
        plan=self.prod.stage_scene(self.pid,self.sid,[8,6,3])
        plan=self.prod.add_instance(self.pid,self.sid,chair['asset_id'],'chair_1',plan['plan_revision'])
        plan=self.prod.solve_scene(self.pid,self.sid,plan['plan_revision'])
        self.prod.approve_scene(self.pid,self.sid,plan['plan_revision'])

    def tearDown(self):self.tmp.cleanup()

    def test_generated_script_and_audit_parse(self):
        ast.parse(AUDIT_SCRIPT)
        ast.parse(self.prod.export_blender_script(self.pid,self.sid))

    def test_absent_blender_is_blocked_not_passed(self):
        result=run_acceptance(self.prod,self.pid,self.sid,self.root/'acceptance',executable='nvp-no-such-blender-binary')
        self.assertEqual(result['status'],'blocked_no_blender')
        self.assertTrue(Path(result['manifest']).is_file())
        self.assertTrue(Path(result['script']).is_file())
        self.assertTrue(Path(result['audit_script']).is_file())
        self.assertEqual(json.loads(Path(result['manifest']).read_text())['instances'][0]['anchors']['seat'],[0,0,.5])
        self.assertFalse((self.root/'acceptance'/'scene.blend').exists())

    def test_blender_probe_is_real_version_probe(self):
        result=blender_available('nvp-this-cannot-exist')
        self.assertFalse(result['available'])
        self.assertIn('reason',result)

    def test_rejection_before_approval_or_scene_edit(self):
        self.studio.save_screenplay(self.pid,'INT. SET - DAY\n\nA red chair.\n',1)
        with self.assertRaisesRegex(RuntimeError,'changed'):
            run_acceptance(self.prod,self.pid,self.sid,self.root/'blocked',executable='nvp-this-cannot-exist')
        self.assertFalse((self.root/'blocked'/'scene.blend').exists())

    def test_meshpack_acceptance_without_native_blender_is_blocked(self):
        from backend.nvp_mesh_assets import MeshAssets
        import trimesh
        assets=MeshAssets(self.studio)
        mesh=trimesh.Scene()
        mesh.add_geometry(trimesh.creation.box(extents=(.5,.5,.9)))
        ident=self.prod.list_assets(self.pid)[0]['asset_id']
        assets.register(self.pid,ident,mesh.export(file_type='glb'),'creator_owned')
        ast.parse(MESH_AUDIT_SCRIPT)
        result=run_meshpack_acceptance(assets,self.pid,self.sid,self.root/'mesh_accept',
                                       executable='nvp-no-such-blender-binary')
        self.assertEqual(result['status'],'blocked_no_blender')
        self.assertEqual(result['meshes'],1)
        self.assertTrue((self.root/'mesh_accept'/'build_scene.py').is_file())
        self.assertFalse((self.root/'mesh_accept'/'meshpack.blend').exists())

    def test_native_meshpack_when_present(self):
        """Verify the actual GLB import, world-space bounds and preview under Blender."""
        check=blender_available()
        if not check['available']:
            self.skipTest('Real Blender executable unavailable')
        from backend.nvp_mesh_assets import MeshAssets
        import trimesh
        assets=MeshAssets(self.studio)
        mesh=trimesh.Scene()
        mesh.add_geometry(trimesh.creation.box(extents=(.5,.5,.9)))
        ident=self.prod.list_assets(self.pid)[0]['asset_id']
        assets.register(self.pid,ident,mesh.export(file_type='glb'),'creator_owned')
        render = os.environ.get('NVP_BLENDER_AUDIT_ONLY') != '1'
        result=run_meshpack_acceptance(assets,self.pid,self.sid,self.root/'native_meshpack',
                                       render_preview=render)
        self.assertEqual(result['status'],
                         'passed_blender' if render else 'passed_blender_audit_only',result)
        self.assertTrue(Path(result['blend']).stat().st_size>0)
        self.assertEqual(result['rendered'],render)
        if render:
            self.assertTrue(Path(result['preview']).stat().st_size>0)
        else:
            self.assertIsNone(result['preview'])
        report=json.loads(Path(result['audit']).read_text())
        self.assertTrue(report['passed'])
        self.assertTrue(any(x['check'].startswith('grounding:') and x['passed']
                            for x in report['checks']))

    def test_native_blender_when_present(self):
        """This test is intentionally skipped, rather than manufacturing render proof."""
        check=blender_available()
        if not check['available']:
            self.skipTest('Real Blender executable unavailable')
        render = os.environ.get('NVP_BLENDER_AUDIT_ONLY') != '1'
        result=run_acceptance(self.prod,self.pid,self.sid,self.root/'native',
                              render_preview=render)
        self.assertEqual(result['status'],
                         'passed_blender' if render else 'passed_blender_audit_only',result)
        self.assertTrue(Path(result['blend']).stat().st_size>0)
        self.assertTrue(Path(result['audit']).stat().st_size>0)
        self.assertEqual(result['rendered'],render)
        if render:
            self.assertTrue(Path(result['preview']).stat().st_size>0)
        else:
            self.assertIsNone(result['preview'])

if __name__=='__main__':unittest.main()
