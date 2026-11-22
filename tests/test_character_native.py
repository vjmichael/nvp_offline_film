"""PROD-06C native smoke: one real skinned GLB, reload, and evaluated deformation."""
import ast
import tempfile
import unittest
from pathlib import Path
from backend.nvp_blender_acceptance import blender_available
from tools.nvp_prod06c_fixture import EXPORT_CHARACTER_GLTF,build_fixture

class NativeCharacterTests(unittest.TestCase):
    def test_exporter_is_a_fixed_parseable_script(self):
        ast.parse(EXPORT_CHARACTER_GLTF)

    def test_real_blender_rig_round_trip_when_available(self):
        if not blender_available()['available']:
            self.skipTest('Native Blender not installed; GitHub Actions runs this separately')
        with tempfile.TemporaryDirectory() as td:
            import os
            render=os.environ.get('NVP_BLENDER_AUDIT_ONLY')!='1'
            result=build_fixture(Path(td),render_preview=render)
            target='passed_blender' if render else 'passed_blender_audit_only'
            self.assertEqual(result['status'],target,result)
            self.assertGreater(result['native']['checks'],10)
            self.assertGreater(result['import']['skinned_vertices'],100)

if __name__=='__main__':unittest.main()
