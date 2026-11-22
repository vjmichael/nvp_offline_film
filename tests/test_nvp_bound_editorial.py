"""SCALE-02C: real FilmIndex source-bound editorial timeline contracts."""
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_bound_editorial import BoundEditorialPublisher


class BoundEditorialNativeTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("Actual FFmpeg and FFprobe are required")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.studio = Studio(root / "studio.sqlite")
        self.pid = self.studio.create_project("Long-form", "Indexed originals")["id"]
        self.index = FilmIndex(self.studio)
        self.catalog = ExternalMediaCatalog(self.studio)
        self.inventory = SourceMediaInventory(self.catalog)
        self.bridge = SourceFilmBridge(self.index, self.inventory)
        self.publisher = BoundEditorialPublisher(self.index)
        self.volume = root / "camera_sd"
        self.volume.mkdir()
        self.inventory.register_volume(self.pid, "camera", self.volume, label="SD Originals")
        self.movie = self.volume / "source.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi",
                        "-i", "testsrc2=size=96x64:rate=24", "-t", "1",
                        "-c:v", "mpeg4", "-q:v", "5", "-y", str(self.movie)],
                       check=True, timeout=60)
        self.catalog.register(self.pid, "take01", self.movie,
                              media_type="video/quicktime")
        self.inventory.enrich(self.pid, "take01", "camera")
        self.source = self.bridge.register_source_revision(self.pid, "take01")

    def clip(self, first=1, count=12, source="take01", revision=1):
        return {"source_id": source, "source_revision": revision,
                "source_first_frame": first, "frame_count": count}

    def test_immutable_source_binding_and_restart_offline(self):
        result = self.publisher.publish(self.pid, "edit1", [self.clip(), self.clip(7, 6)])
        self.assertEqual(result["revision"], 1)
        movie = self.index.read_revision(self.pid, "edit1", 1)
        self.assertFalse(movie["data"]["creator_approved"])
        self.assertEqual(movie["data"]["total_frames"], 18)
        self.assertEqual(movie["data"]["clip_count"], 2)
        page = self.publisher.clips(self.pid, "edit1", 1, first_frame=15)
        self.assertEqual(len(page["clips"]), 1)
        self.assertEqual(page["clips"][0]["ordinal"], 1)
        self.assertEqual(page["clips"][0]["source_document_sha256"],
                         self.source["document_sha256"])
        self.assertEqual(self.index.direct_dependents(self.pid, "take01", 1),
                         [{"object_id": "edit1", "revision": 1}])
        self.assertEqual(self.index.impact(self.pid, "take01", 1),
                         [{"object_id": "edit1", "revision": 1}])
        self.assertEqual(self.publisher.verify_revision(
            self.pid, "edit1", 1)["status"], "VERIFIED_INDEXED_SOURCE_BINDINGS")
        self.movie.unlink()
        reopened_studio = Studio(self.studio.db_path)
        fresh_index = FilmIndex(reopened_studio)
        fresh = BoundEditorialPublisher(fresh_index)
        self.assertEqual(fresh.clips(self.pid, "edit1", 1)["clips"][0][
                         "source_document_sha256"], self.source["document_sha256"])

    def test_many_clips_do_not_hit_filmindex_128_edge_cap(self):
        result = self.publisher.publish(
            self.pid, "many", (self.clip() for _ in range(450)))
        doc = self.index.read_revision(self.pid, "many", 1)
        self.assertEqual(doc["data"]["clip_count"], 450)
        self.assertEqual(doc["data"]["total_frames"], 5400)
        self.assertEqual(self.publisher.clips(
            self.pid, "many", 1, first_frame=5395)["clips"][0]["ordinal"], 449)
        self.assertEqual(self.index.direct_dependents(self.pid, "take01", 1),
                         [{"object_id": "many", "revision": 1}])

    def test_invalid_source_and_wrong_revision_fail_closed(self):
        with self.assertRaises(KeyError):
            self.publisher.publish(self.pid, "wrong", [self.clip(revision=2)])
        with self.assertRaises(RuntimeError):
            self.publisher.publish(self.pid, "outside", [self.clip(19, 12)])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "wrong")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "outside")

    def test_atomic_failure_does_not_publish_partial_edit(self):
        self.publisher.publish(self.pid, "edit_conflict", [self.clip()])
        with self.assertRaises(RuntimeError):
            self.publisher.publish(self.pid, "edit_conflict", [self.clip()],
                                   expected_revision=0)
        self.assertEqual(self.index.read_revision(self.pid, "edit_conflict")["revision"], 1)
        with self.studio._connection() as db:
            total = db.execute("""SELECT COUNT(*) FROM scale_editorial_clips
                WHERE project_id=? AND edit_id=?""",
                (self.pid, "edit_conflict")).fetchone()[0]
        self.assertEqual(total, 1)

    def test_cross_project_rejected_and_source_offline_planning(self):
        self.movie.unlink()
        result = self.publisher.publish(self.pid, "offline_edit", [self.clip()])
        self.assertEqual(result["revision"], 1)
        other = self.studio.create_project("Other", "Separate")["id"]
        with self.assertRaises(KeyError):
            self.publisher.publish(other, "alien_edit", [self.clip()])
        with self.assertRaises(KeyError):
            self.index.read_revision(other, "alien_edit")

    def test_altered_binding_is_detected_by_full_audit(self):
        self.publisher.publish(self.pid, "alter", [self.clip(), self.clip(2, 4)])
        with self.studio._connection() as db:
            db.execute("""UPDATE scale_editorial_source_bindings
                SET source_document_sha256=?
                WHERE project_id=? AND edit_id=? AND revision=1 AND ordinal=1""",
                ("f" * 64, self.pid, "alter"))
        with self.assertRaises(RuntimeError):
            self.publisher.verify_revision(self.pid, "alter", 1)
        with self.assertRaises(RuntimeError):
            self.publisher.clips(self.pid, "alter", 1)

    def test_crash_after_guard_inserts_rolls_back_all_rows(self):
        original = self.index.register_revision

        def crash_after_guard(*args, **kwargs):
            guard = kwargs["precommit_guard"]

            def simulate_kill_boundary(db):
                guard(db)
                raise RuntimeError("injected SQLite publication failure")

            kwargs["precommit_guard"] = simulate_kill_boundary
            return original(*args, **kwargs)

        with mock.patch.object(self.index, "register_revision",
                               side_effect=crash_after_guard):
            with self.assertRaisesRegex(RuntimeError, "injected SQLite"):
                self.publisher.publish(self.pid, "crash_edit", [self.clip()])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "crash_edit")
        with self.studio._connection() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM scale_editorial_revisions
                WHERE project_id=? AND edit_id=?""",
                (self.pid, "crash_edit")).fetchone()[0], 0)
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM scale_editorial_clips
                WHERE project_id=? AND edit_id=?""",
                (self.pid, "crash_edit")).fetchone()[0], 0)
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM scale_editorial_source_bindings
                WHERE project_id=? AND edit_id=?""",
                (self.pid, "crash_edit")).fetchone()[0], 0)

    def test_duplicate_source_version_disallowed(self):
        self.publisher.publish(self.pid, "first", [self.clip()])
        with self.assertRaises(RuntimeError):
            self.publisher.publish(self.pid, "invalid", [self.clip(1, 5)],
                                   fps_num=25, fps_den=1)


if __name__ == "__main__":
    unittest.main()
