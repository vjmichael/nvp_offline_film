"""SCALE-02 external media registration, offline references and integrity gates."""
import os
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_external_media_catalog import ExternalMediaCatalog


class ExternalMediaCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.studio = Studio(root / "studio.sqlite")
        self.project = self.studio.create_project("Feature", "Large library")
        self.catalog = ExternalMediaCatalog(self.studio)
        self.source = root / "camera.mov"
        # > hash block size; no whole-file read required.
        with self.source.open("wb") as stream:
            stream.write(b"source-file-" * 450000)

    def test_register_reopen_and_verify(self):
        project_id = self.project["id"]
        result = self.catalog.register(project_id, "camera_a", self.source,
                                       media_type="video/quicktime")
        self.assertEqual(result["custody"], "external_source_reference_not_copied")
        self.assertGreater(result["size_bytes"], 4 * 1024 * 1024)
        reopened = ExternalMediaCatalog(Studio(self.studio.db_path))
        self.assertEqual(reopened.probe(project_id, "camera_a")["status"],
                         "PRESENT_UNVERIFIED")
        self.assertEqual(reopened.probe(project_id, "camera_a", verify_bytes=True)["status"],
                         "VERIFIED")

    def test_same_size_tamper_requires_hash_check(self):
        pid = self.project["id"]
        self.catalog.register(pid, "camera_b", self.source, media_type="video/quicktime")
        with self.source.open("r+b") as stream:
            stream.seek(100)
            stream.write(b"XXXXXXXXXX")
            stream.flush()
            os.fsync(stream.fileno())
        self.assertEqual(self.catalog.probe(pid, "camera_b")["status"],
                         "PRESENT_UNVERIFIED")
        self.assertEqual(self.catalog.probe(pid, "camera_b", verify_bytes=True)["status"],
                         "CHANGED")

    def test_offline_source_keeps_index(self):
        pid = self.project["id"]
        self.catalog.register(pid, "camera_c", self.source, media_type="video/quicktime")
        self.source.unlink()
        self.assertEqual(self.catalog.probe(pid, "camera_c")["status"], "OFFLINE")
        self.assertEqual(len(self.catalog.list_assets(pid)), 1)

    def test_cross_project_refusal_and_duplicate(self):
        pid = self.project["id"]
        self.catalog.register(pid, "camera_d", self.source, media_type="video/quicktime")
        other = self.studio.create_project("Other", "No source")
        with self.assertRaises(KeyError):
            self.catalog.probe(other["id"], "camera_d", verify_bytes=True)
        with self.assertRaises(Exception):
            self.catalog.register(pid, "camera_d", self.source, media_type="video/quicktime")

    def test_pagination_and_no_full_media_payload(self):
        pid = self.project["id"]
        for n in range(3):
            self.catalog.register(pid, "camera_" + str(n), self.source,
                                  media_type="video/quicktime")
        page = self.catalog.list_assets(pid, limit=2)
        next_page = self.catalog.list_assets(pid, after_id=page[-1]["asset_id"])
        self.assertEqual(len(page), 2)
        self.assertEqual(len(next_page), 1)
        self.assertNotIn("media_path", page[0])

    def test_symlink_refused(self):
        link = Path(self.temp.name) / "link.mov"
        try:
            link.symlink_to(self.source)
        except OSError:
            self.skipTest("Symlink unavailable")
        with self.assertRaises(ValueError):
            self.catalog.register(self.project["id"], "link", link,
                                  media_type="video/quicktime")


if __name__ == "__main__":
    unittest.main()
