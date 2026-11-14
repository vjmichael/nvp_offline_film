"""PROD-03: licensed GLB ingestion, immutable IDs and portable Blender packaging."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import trimesh

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_mesh_assets import MeshAssets,inspect_glb

SCRIPT='INT. TEST CHAMBER - DAY\n\nA table holds a key.\n'

class MeshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.studio=Studio(self.root/'db.sqlite3')
        self.pid=self.studio.create_project('Mesh film','')['id']
        self.sid=self.studio.save_screenplay(self.pid,SCRIPT,0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        self.mesh=MeshAssets(self.studio)
        self.asset=self.prod.create_asset(self.pid,{'name':'Table','category':'furniture','dimensions':[2,1,.75],
                                                     'anchors':{'front':[0,-.5,.7]}})
        self.blob=self.make_glb((2,1,.75))

    def tearDown(self):self.temp.cleanup()

    @staticmethod
    def make_glb(dimensions):
        scene=trimesh.Scene();scene.add_geometry(trimesh.creation.box(extents=dimensions))
        return scene.export(file_type='glb')

    def stage(self):
        plan=self.prod.stage_scene(self.pid,self.sid,[8,6,3])
        plan=self.prod.add_instance(self.pid,self.sid,self.asset['asset_id'],'table_1',plan['plan_revision'])
        plan=self.prod.solve_scene(self.pid,self.sid,plan['plan_revision'])
        self.prod.approve_scene(self.pid,self.sid,plan['plan_revision'])

    def test_validate_known_mesh_dimensions_and_geometry(self):
        info=inspect_glb(self.blob)
        self.assertEqual(info['mesh_count'],1)
        self.assertEqual(info['dimensions_m'],[2,1,.75])
        self.assertEqual(info['faces'],12)

    def test_register_glb_immutable_with_license_and_restart(self):
        r=self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'CC-BY-4.0','Creator Example','https://example.test/asset')
        self.assertEqual(r['status'],'registered')
        self.assertEqual(r['sha256'],hashlib.sha256(self.blob).hexdigest())
        again=MeshAssets(Studio(self.studio.db_path)).register(self.pid,self.asset['asset_id'],self.blob,'CC-BY-4.0','Creator Example','https://example.test/asset')
        self.assertEqual(again['status'],'already_registered')
        self.assertEqual(len(self.mesh.list(self.pid)),1)

    def test_asset_rights_record_cannot_silently_change(self):
        self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'creator_owned')
        with self.assertRaisesRegex(RuntimeError,'provenance is immutable'):
            self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'CC0-1.0')

    def test_evaluation_only_asset_is_marked_not_commercially_cleared(self):
        self.stage()
        self.mesh.register(self.pid,self.asset['asset_id'],self.blob,
                           'evaluation_only','Research test','local-test')
        info=self.mesh.export_bundle(self.pid,self.sid,self.root/'preview')
        self.assertEqual(info['manifest']['rights_status'],'evaluation_or_unverified_rights')

    def test_asset_geometry_mismatch_must_get_new_identity(self):
        with self.assertRaisesRegex(ValueError,'geometry differs'):
            self.mesh.register(self.pid,self.asset['asset_id'],self.make_glb((1,1,1)),'CC0-1.0')

    def test_different_mesh_reuse_of_asset_id_is_refused(self):
        self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'creator_owned')
        geom=self.make_glb((2.01,1,.75))
        with self.assertRaisesRegex(RuntimeError,'immutable'):
            self.mesh.register(self.pid,self.asset['asset_id'],geom,'creator_owned')

    def test_license_requires_source_and_attribution(self):
        with self.assertRaisesRegex(ValueError,'source and attribution'):
            self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'CC-BY-4.0')
        with self.assertRaisesRegex(ValueError,'Explicit asset license'):
            self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'no_license')

    def test_invalid_glb_header_and_length_refused(self):
        with self.assertRaises(ValueError): inspect_glb(b'bad')
        with self.assertRaises(ValueError): inspect_glb(self.blob[:-1])
        with self.assertRaises(ValueError): inspect_glb(b'\0'*30)

    def test_cross_project_asset_binding_refused(self):
        other=self.studio.create_project('Other','')['id']
        with self.assertRaises(KeyError):
            self.mesh.register(other,self.asset['asset_id'],self.blob,'creator_owned')
        self.assertEqual(self.mesh.list(other),[])

    def test_scene_package_contains_verified_mesh_and_license(self):
        self.stage()
        self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'CC-BY-4.0','Example','https://example.test/model')
        result=self.mesh.export_bundle(self.pid,self.sid,self.root/'bundle')
        self.assertEqual(result['meshes'],1)
        manifest=json.loads((self.root/'bundle'/'manifest.json').read_text())
        self.assertEqual(manifest['format'],'nvp.production.meshpack.v1')
        self.assertEqual(manifest['instances'][0]['mesh']['sha256'],hashlib.sha256(self.blob).hexdigest())
        self.assertEqual((self.root/'bundle'/'licenses.json').read_text().count('CC-BY-4.0'),1)
        script=(self.root/'bundle'/'build_scene.py').read_text()
        ast.parse(script)
        self.assertIn('bpy.ops.import_scene.gltf',script)
        self.assertEqual(len(list((self.root/'bundle'/'assets').glob('*.glb'))),1)

    def test_mesh_bitrot_is_refused(self):
        self.stage()
        info=self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'creator_owned')
        (self.mesh.root/(info['sha256']+'.glb')).write_bytes(b'corrupted')
        with self.assertRaisesRegex(RuntimeError,'corrupted'):
            self.mesh.export_bundle(self.pid,self.sid,self.root/'bundle')

    def test_proxy_only_package_is_explicit(self):
        self.stage()
        result=self.mesh.export_bundle(self.pid,self.sid,self.root/'bundle')
        self.assertEqual(result['meshes'],0)
        self.assertIsNone(result['manifest']['instances'][0]['mesh'])

    def test_unapproved_layout_cannot_be_exported(self):
        self.prod.stage_scene(self.pid,self.sid,[8,6,3])
        with self.assertRaisesRegex(RuntimeError,'approve'):
            self.mesh.export_bundle(self.pid,self.sid,self.root/'bundle')

    def test_content_copy_is_stable_across_second_export(self):
        self.stage()
        self.mesh.register(self.pid,self.asset['asset_id'],self.blob,'creator_owned')
        a=self.mesh.export_bundle(self.pid,self.sid,self.root/'a')
        b=self.mesh.export_bundle(self.pid,self.sid,self.root/'b')
        self.assertEqual(a['manifest']['package_sha256'],b['manifest']['package_sha256'])

if __name__=='__main__':unittest.main()
