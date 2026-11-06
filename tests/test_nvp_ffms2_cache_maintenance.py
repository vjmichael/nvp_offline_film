"""SCALE-03C: FFMS2 version upgrade notices; no native DLL required."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.nvp_ffms2_index_maintenance import FFMS2IndexMaintenance


PROJECT = "a" * 32
SOURCE = "b" * 64
DLL1 = "1" * 64
DLL2 = "2" * 64


class CacheUpgradeContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "NVP-cache"
        self.first = FFMS2IndexMaintenance(
            self.root, engine_version=0x05000000, library_sha256=DLL1)
        self.new = FFMS2IndexMaintenance(
            self.root, engine_version=0x05010000, library_sha256=DLL2)

    def test_upgrade_warning_is_not_source_corruption(self):
        original = Path(self.temp.name) / "source.mov"
        original.write_bytes(b"original-camera-data-never-touched")
        self.assertEqual(self.new.inspect(PROJECT, "take_a", SOURCE)["status"],
                         "NOT_INDEXED_OR_LEGACY_CACHE")
        self.first.mark_index_verified(PROJECT, "take_a", SOURCE)
        state = self.new.inspect(PROJECT, "take_a", SOURCE)
        self.assertEqual(state["status"], "REINDEX_REQUIRED")
        self.assertFalse(state["ready"])
        self.assertEqual(state["notice"]["code"], "VIDEO_INDEX_VERSION_CHANGED")
        self.assertIn("safe", state["notice"]["message"].lower())
        self.assertEqual(original.read_bytes(), b"original-camera-data-never-touched")
        self.new.mark_index_verified(PROJECT, "take_a", SOURCE)
        self.assertEqual(self.new.inspect(PROJECT, "take_a", SOURCE)["status"],
                         "INDEX_VERSION_MATCH_UNVERIFIED")
        self.assertEqual(original.read_bytes(), b"original-camera-data-never-touched")

    def test_cross_project_and_revision_isolation(self):
        self.first.mark_index_verified(PROJECT, "take_a", SOURCE)
        self.assertEqual(self.new.inspect("c" * 32, "take_a", SOURCE)["status"],
                         "NOT_INDEXED_OR_LEGACY_CACHE")
        self.assertEqual(self.new.inspect(PROJECT, "take_a", "e" * 64)["status"],
                         "NOT_INDEXED_OR_LEGACY_CACHE")
        self.assertEqual(self.new.inspect(PROJECT, "take_b", SOURCE)["status"],
                         "NOT_INDEXED_OR_LEGACY_CACHE")

    def test_tampered_marker_fails_closed_without_damaging_media(self):
        self.first.mark_index_verified(PROJECT, "take_a", SOURCE)
        marker = self.first._marker(PROJECT, "take_a", SOURCE)
        record = json.loads(marker.read_bytes())
        record["source_sha256"] = "f" * 64
        marker.write_text(json.dumps(record), encoding="utf8")
        self.assertEqual(self.new.inspect(PROJECT, "take_a", SOURCE)["status"],
                         "INDEX_METADATA_INVALID")

    def test_invalid_identity_rejected(self):
        with self.assertRaises(ValueError):
            self.new.inspect("not-a-project", "take_a", SOURCE)


if __name__ == "__main__":
    unittest.main()
