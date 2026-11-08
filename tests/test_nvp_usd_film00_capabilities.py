"""USD-FILM-00 actual OpenUSD native capability report acceptance tests.

Tests execute real pxr/USD (no mocks). They do NOT demand that optional
Hydra/UsdVol/UsdPhysics/UsdMedia or Blender executables exist in usd-core.
Any missing optional schema is explicit evidence, NOT silently accepted.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_usd_film00_probe import CORE, FORMAT, run_audit, sha


class NativeUsdFilm00Inventory(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = self.root / "blender_fixture.usda"
        self.report = run_audit(self.root, fixture=self.fixture)

    def test_native_required_author_read_roundtrip_is_real(self):
        self.assertEqual(self.report["format"], FORMAT)
        self.assertEqual(self.report["status"], "NATIVE_PROBES_EXECUTED")
        for name in CORE:
            with self.subTest(feature=name):
                self.assertEqual(
                    self.report["features"][name]["status"], "PASS",
                    self.report["features"][name])
                self.assertTrue(self.report["features"][name]["level"])
        self.assertTrue(self.report["required_source_baseline_passed"])

    def test_capabilities_cannot_be_confused_with_renderer_or_visual_quality(self):
        self.assertFalse(self.report["renderer_verified"])
        self.assertFalse(self.report["blender_verified"])
        self.assertFalse(self.report["hydra_delegate_render_verified"])
        self.assertFalse(self.report["materialx_renderer_parity_verified"])
        self.assertFalse(self.report["photorealism_verified"])
        self.assertFalse(self.report["nvp_source_indexed_asset_resolver_verified"])
        self.assertEqual(
            self.report["features"]["skeletal_blendshapes"]["level"],
            "AUTHOR_SAVE_REOPEN")
        self.assertEqual(
            self.report["features"]["usdpreview_material"]["level"],
            "AUTHOR_SAVE_REOPEN_UNBOUND_SHADER")
        self.assertIn("limits", self.report["features"]["references_and_payloads"])

    def test_optional_schema_only_feature_cannot_be_reported_as_simulated(self):
        for name in (
            "physics_rigid_body", "volume_schema", "spatial_audio_schema",
            "render_settings_schema",
        ):
            with self.subTest(name=name):
                item = self.report["features"][name]
                self.assertIn(item["status"], ("PASS", "NOT_AVAILABLE", "FAIL"))
                if item["status"] == "PASS":
                    self.assertEqual(item["level"], "SCHEMA_AUTHOR_SAVE_REOPEN")
                    self.assertIn("no physics", item["limits"])
        for name, item in self.report["optional_module_imports"].items():
            self.assertIn(item["status"], ("IMPORTABLE_ONLY", "NOT_AVAILABLE"))
            if item["status"] == "IMPORTABLE_ONLY":
                self.assertFalse(item["render_execution_verified"])

    def test_source_usd_fixture_is_actual_reopenable_native_geometry(self):
        from pxr import Usd, UsdGeom, UsdLux
        source = self.report["features"]["native_blender_fixture"]
        self.assertEqual(source["status"], "PASS", source)
        self.assertEqual(source["sha256"], sha(self.fixture))
        stage = Usd.Stage.Open(str(self.fixture))
        self.assertTrue(stage.GetPrimAtPath("/World/ProbeMesh").IsA(UsdGeom.Mesh))
        self.assertTrue(stage.GetPrimAtPath("/World/Camera").IsA(UsdGeom.Camera))
        self.assertTrue(stage.GetPrimAtPath("/World/Light").IsA(UsdLux.SphereLight))
        self.assertEqual(len(UsdGeom.Mesh(
            stage.GetPrimAtPath("/World/ProbeMesh")).GetPointsAttr().Get()), 4)


if __name__ == "__main__":
    unittest.main()
