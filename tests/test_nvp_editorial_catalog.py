"""SCALE-01 compact editorial catalog: feature-size metadata without frame lists."""
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_editorial_catalog import EditorialCatalog


class EditorialCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(Path(self.temp.name) / "studio.sqlite")
        self.project = self.studio.create_project("Feature", "Long feature")
        self.catalog = EditorialCatalog(self.studio)

    def test_three_hour_edit_seek_and_restart(self):
        pid = self.project["id"]
        # Each item represents a 24-second reference, not 576 frame objects.
        clips = ({"source_id": "take_" + str(i % 40),
                  "source_revision": 1,
                  "source_first_frame": 1,
                  "frame_count": 576} for i in range(450))
        result = self.catalog.publish(
            pid, "feature_edit", 1, fps_num=24, fps_den=1,
            source_manifest_sha256="a" * 64, clips=clips)
        self.assertEqual(result["total_frames"], 259200)
        self.assertEqual(result["clip_count"], 450)
        reopened = EditorialCatalog(Studio(self.studio.db_path))
        page = reopened.clips(pid, "feature_edit", 1,
                              first_frame=259199, limit=2)
        self.assertEqual(len(page["clips"]), 1)
        self.assertEqual(page["clips"][0]["ordinal"], 449)
        self.assertEqual(page["clips"][0]["output_first_frame"], 258625)

    def test_project_isolation_and_immutable_revision(self):
        pid = self.project["id"]
        one = [{"source_id": "take_1", "source_revision": 1,
                "source_first_frame": 1, "frame_count": 2}]
        self.catalog.publish(pid, "edit", 1, fps_num=24, fps_den=1,
                             source_manifest_sha256="b" * 64, clips=one)
        with self.assertRaises(Exception):
            self.catalog.publish(pid, "edit", 1, fps_num=24, fps_den=1,
                                 source_manifest_sha256="b" * 64, clips=one)
        other = self.studio.create_project("Other", "No access")
        with self.assertRaises(KeyError):
            self.catalog.clips(other["id"], "edit", 1)

    def test_failed_publish_rolls_back_all_clips(self):
        pid = self.project["id"]
        bad = [{"source_id": "valid", "source_revision": 1,
                "source_first_frame": 1, "frame_count": 5},
               {"source_id": "invalid", "source_revision": 1,
                "source_first_frame": 0, "frame_count": 3}]
        with self.assertRaises(ValueError):
            self.catalog.publish(pid, "edit_bad", 1, fps_num=24, fps_den=1,
                                 source_manifest_sha256="c" * 64, clips=bad)
        with self.assertRaises(KeyError):
            self.catalog.clips(pid, "edit_bad", 1)

    def test_large_64bit_frames_without_expansion(self):
        pid = self.project["id"]
        self.catalog.publish(pid, "large", 1, fps_num=24000, fps_den=1001,
                             source_manifest_sha256="d" * 64,
                             clips=[{"source_id": "long_take",
                                     "source_revision": 1,
                                     "source_first_frame": 1,
                                     "frame_count": 2**32}])
        page = self.catalog.clips(pid, "large", 1, first_frame=2**32)
        self.assertEqual(page["total_frames"], 2**32)
        self.assertEqual(page["clips"][0]["frame_count"], 2**32)

    def test_reject_overflow(self):
        with self.assertRaises(OverflowError):
            self.catalog.publish(
                self.project["id"], "overflow", 1, fps_num=24, fps_den=1,
                source_manifest_sha256="f" * 64,
                clips=[{"source_id": "take", "source_revision": 1,
                        "source_first_frame": 2**63 - 1,
                        "frame_count": 2}])


if __name__ == "__main__":
    unittest.main()
