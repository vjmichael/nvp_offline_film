"""Frozen external sample provenance and native Blender acceptance gates."""
import ast
import os
import tempfile
import unittest
from pathlib import Path
from tools.nvp_prod06d_fixture import (UPSTREAM_URL, UPSTREAM_GIT_BLOB, UPSTREAM_LICENSE,
    UPSTREAM_CREDIT, NORMALIZE_GLTF, CESIUM_ROLE_MAP, verify_upstream, build_external_fixture)
from backend.nvp_blender_acceptance import blender_available

class ExternalRetargetTests(unittest.TestCase):
    def test_fixed_normalizer_and_seven_manual_roles(self):
        ast.parse(NORMALIZE_GLTF)
        self.assertEqual(len(CESIUM_ROLE_MAP),7)
        self.assertEqual(len(set(CESIUM_ROLE_MAP.values())),7)
        self.assertNotIn('eval(',NORMALIZE_GLTF)

    def test_pinned_asset_with_license_and_attribution(self):
        self.assertEqual(UPSTREAM_LICENSE,'CC-BY-4.0')
        self.assertIn('Cesium',UPSTREAM_CREDIT)
        self.assertIn('/Models/CesiumMan/',UPSTREAM_URL)
        self.assertEqual(len(UPSTREAM_GIT_BLOB),40)
        with self.assertRaises(ValueError):verify_upstream(b'fake')

    def test_native_external_character_when_supplied(self):
        path=os.environ.get('NVP_PROD06D_CESIUMMAN')
        if not path:self.skipTest('Pinned third-party GLB not supplied; separate CI acceptance job requires it')
        if not blender_available()['available']:self.skipTest('Real Blender is not installed in this environment')
        with tempfile.TemporaryDirectory() as temp:
            result=build_external_fixture(Path(temp),Path(path),
                 render_preview=os.environ.get('NVP_BLENDER_AUDIT_ONLY')!='1')
            expected=('passed_blender_audit_only' if os.environ.get('NVP_BLENDER_AUDIT_ONLY')=='1'
                      else 'passed_blender')
            self.assertEqual(result['status'],expected,result)
            self.assertGreater(result['skinned_vertices'],100)
            self.assertGreater(result['joint_count'],7)
            self.assertGreater(result['native']['checks'],20)

if __name__=='__main__':unittest.main()
