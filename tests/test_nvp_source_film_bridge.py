"""SCALE-02C: FilmIndex original source custody across removable-media moves."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge


class SourceFilmBridgeNativeTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("Real native FFmpeg and FFprobe required")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.original = root / "card_a"
        self.moved = root / "card_b"
        self.original.mkdir()
        self.moved.mkdir()
        self.studio = Studio(root / "studio.sqlite")
        self.pid = self.studio.create_project("Film", "Card source")["id"]
        self.catalog = ExternalMediaCatalog(self.studio)
        self.inventory = SourceMediaInventory(self.catalog)
        self.index = FilmIndex(self.studio)
        self.bridge = SourceFilmBridge(self.index, self.inventory)
        self.source = self.original / "shot.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin",
                        "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24",
                        "-t", "0.5", "-c:v", "mpeg4", "-q:v", "5", "-y", str(self.source)],
                       check=True, timeout=60)
        self.inventory.register_volume(self.pid, "card01", self.original, label="Camera SD")
        self.catalog.register(self.pid, "shot_original", self.source,
                              media_type="video/quicktime")
        self.inventory.enrich(self.pid, "shot_original", "card01")

    def test_publish_immutable_hash_and_reopen_offline(self):
        rec = self.bridge.register_source_revision(self.pid, "shot_original")
        self.assertEqual(rec["revision"], 1)
        self.assertEqual(rec["kind"], "asset")
        self.assertEqual(rec["dependencies"], [])
        source = self.bridge.resolve_source(self.pid, "shot_original", verify_bytes=True)
        self.assertEqual(source["availability"], "VERIFIED")
        self.assertTrue(source["verified_bytes"])
        self.source.unlink()
        reopened = SourceFilmBridge(
            FilmIndex(Studio(self.studio.db_path)),
            SourceMediaInventory(ExternalMediaCatalog(Studio(self.studio.db_path))))
        offline = reopened.resolve_source(self.pid, "shot_original")
        self.assertEqual(offline["availability"], "OFFLINE")
        self.assertEqual(offline["source_sha256"], rec["data"]["content_sha256"]
                         if "data" in rec else source["source_sha256"])
        self.assertFalse(offline["verified_bytes"])

    def test_relocate_keeps_same_authoritative_revision(self):
        initial = self.bridge.register_source_revision(self.pid, "shot_original")
        shutil.copyfile(self.source, self.moved / self.source.name)
        self.inventory.relink_volume(self.pid, "card01", self.moved)
        self.source.unlink()
        result = self.bridge.resolve_source(self.pid, "shot_original", verify_bytes=True)
        self.assertEqual(result["film_document_sha256"], initial["document_sha256"])
        self.assertEqual(result["availability"], "VERIFIED")
        with self.assertRaisesRegex(RuntimeError, "already published"):
            self.bridge.register_source_revision(self.pid, "shot_original")

    def test_changed_bytes_not_allowed_for_new_publication(self):
        with self.source.open("r+b") as stream:
            stream.seek(100)
            stream.write(b"corrupt")
        with self.assertRaisesRegex(RuntimeError, "SHA verification"):
            self.bridge.register_source_revision(self.pid, "shot_original")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "shot_original")

    def test_project_isolation(self):
        self.bridge.register_source_revision(self.pid, "shot_original")
        other = self.studio.create_project("Other film", "No camera media")["id"]
        with self.assertRaises(KeyError):
            self.bridge.resolve_source(other, "shot_original")

    def test_requires_same_studio_database(self):
        other = Studio(Path(self.tmp.name) / "different.sqlite")
        with self.assertRaises(ValueError):
            SourceFilmBridge(FilmIndex(other), self.inventory)


if __name__ == "__main__":
    unittest.main()
