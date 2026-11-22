"""SCALE-03A: exact source window lookup on genuine native source footage."""
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
from backend.nvp_bound_editorial import BoundEditorialPublisher
from backend.nvp_source_window_preflight import SourceWindowPreflight


class WindowPreflightTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("Native FFmpeg and FFprobe are required")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.studio = Studio(root / "nvp.sqlite")
        self.pid = self.studio.create_project("Film", "Source-window native test")["id"]
        self.index = FilmIndex(self.studio)
        self.catalog = ExternalMediaCatalog(self.studio)
        self.inventory = SourceMediaInventory(self.catalog)
        self.bridge = SourceFilmBridge(self.index, self.inventory)
        self.editor = BoundEditorialPublisher(self.index)
        self.window = SourceWindowPreflight(self.editor, self.bridge)
        self.volume = root / "camera_card"
        self.volume.mkdir()
        self.inventory.register_volume(self.pid, "camera_card", self.volume,
                                       label="Camera card")
        self.sources = {}
        for sid in ("take_a", "take_b"):
            movie = self.volume / (sid + ".mov")
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin",
                            "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24",
                            "-frames:v", "24", "-c:v", "mpeg4", "-q:v", "4",
                            "-y", str(movie)], check=True, timeout=60)
            self.catalog.register(self.pid, sid, movie, media_type="video/quicktime")
            self.inventory.enrich(self.pid, sid, "camera_card")
            self.bridge.register_source_revision(self.pid, sid)
            self.sources[sid] = movie
        self.editor.publish(self.pid, "cut", [
            {"source_id": "take_a", "source_revision": 1,
             "source_first_frame": 7, "frame_count": 12},
            {"source_id": "take_b", "source_revision": 1,
             "source_first_frame": 4, "frame_count": 12},
        ])

    def test_window_across_cut_preserves_source_ranges(self):
        result = self.window.prepare(
            self.pid, "cut", 1, first_frame=9, frame_count=8)
        self.assertEqual(result["frame_count"], 8)
        self.assertEqual([(s["source_id"],s["source_first_frame"],s["frame_count"])
                          for s in result["slices"]],
                         [("take_a",15,4),("take_b",4,4)])
        self.assertEqual(result["source_preflight"], "VERIFIED_AT_PREPARATION")
        self.assertFalse(result["frames_decoded"])
        self.assertFalse(result["creator_approved"])

    def test_end_of_edit_seek_and_bounds(self):
        end = self.window.prepare(
            self.pid, "cut", 1, first_frame=24, frame_count=1)
        self.assertEqual(end["slices"][0]["source_first_frame"], 15)
        with self.assertRaises(ValueError):
            self.window.prepare(self.pid, "cut", 1, first_frame=24, frame_count=2)
        with self.assertRaises(ValueError):
            self.window.prepare(self.pid, "cut", 1, first_frame=1, frame_count=97)

    def test_offline_original_refuses_active_work(self):
        self.sources["take_b"].unlink()
        with self.assertRaises(RuntimeError):
            self.window.prepare(self.pid, "cut", 1, first_frame=11, frame_count=4)
        # Navigating the edit is still possible without card source bytes.
        self.assertEqual(self.editor.clips(self.pid, "cut", 1)["total_frames"],24)

    def test_modified_original_refuses_active_work(self):
        with self.sources["take_a"].open("r+b") as file:
            file.seek(200)
            file.write(b"modified")
        with self.assertRaises(RuntimeError):
            self.window.prepare(self.pid, "cut", 1, first_frame=1, frame_count=2)

    def test_project_isolation(self):
        other = self.studio.create_project("Different film", "No originals")["id"]
        with self.assertRaises(KeyError):
            self.window.prepare(other, "cut", 1, first_frame=1, frame_count=2)

    def test_no_bypass_of_byte_verification(self):
        with self.assertRaises(PermissionError):
            self.window.prepare(self.pid, "cut", 1, first_frame=1, frame_count=2,
                                verify_original_bytes=False)


if __name__ == "__main__":
    unittest.main()
