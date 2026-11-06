"""SCALE-03C: native FFMS2 index reuse, frame seek and approved contained review.

These are REAL C-ABI and video decode tests. They fail instead of silently
falling back to FFmpeg when the pinned FFMS2 library is unavailable.
"""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import unittest

from backend.nvp_ffms2_native import FFMS2, sha_file, MAX_FFMS_FRAME
from backend.nvp_ffms2_index_cache import FFMS2SourceIndex
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_bound_editorial import BoundEditorialPublisher
from backend.nvp_source_window_preflight import SourceWindowPreflight
from backend.nvp_source_window_native_host import NativeSourceWindowHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot


class FFMS2IndexedNative(unittest.TestCase):
    def setUp(self):
        name = os.environ.get("NVP_FFMS2_LIBRARY")
        if not name or not Path(name).is_absolute() or not Path(name).is_file():
            self.fail("Native FFMS2 acceptance requires absolute NVP_FFMS2_LIBRARY")
        for exe in ("ffmpeg", "ffprobe"):
            if not shutil.which(exe):
                self.fail("Native FFMS2 acceptance requires " + exe)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ffms_path = Path(name)
        self.ffms = FFMS2(self.ffms_path)
        self.volume = self.root / "camera_sd"
        self.volume.mkdir()
        self.source = self.volume / "camera.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin",
                        "-f", "lavfi", "-i", "testsrc2=size=192x108:rate=24",
                        "-frames:v", "120", "-c:v", "mpeg4", "-g", "12",
                        "-q:v", "4", "-y", str(self.source)],
                       check=True, timeout=60)
        self.sha = sha_file(self.source)
        self.studio = Studio(self.root / "studio.sqlite")
        self.pid = self.studio.create_project("FFMS2", "Indexed footage")["id"]
        self.cache = FFMS2SourceIndex(self.ffms, self.root / "index-cache")

    def test_create_reuse_and_random_access_near_end(self):
        start = time.perf_counter()
        result = self.cache.get_or_create(self.pid, "take01", self.source, self.sha)
        first_seconds = time.perf_counter() - start
        self.assertEqual(result["status"], "VERIFIED_CREATED")
        self.assertEqual(result["num_frames"], 120)
        self.assertEqual(result["source_sha256"], self.sha)
        self.assertNotIn(str(self.volume), result["index_path"])
        self.assertTrue(Path(result["index_path"]).is_file())

        reused = self.cache.get_or_create(self.pid, "take01", self.source, self.sha)
        self.assertEqual(reused["status"], "VERIFIED_REUSED")
        self.assertEqual(result["index_sha256"], reused["index_sha256"])

        with self.ffms.open_video(self.source, reused["index_path"]) as video:
            first = video.frame_metadata(0)
            last = video.frame_metadata(119)
            self.assertGreaterEqual(last["pts"], first["pts"])
            self.assertEqual(last["frame_zero"], 119)
            self.assertGreater(video.meta["time_base_den"], 0)
            first_png = self.root / "first.png"
            last_png = self.root / "last.png"
            video.save_png(0, first_png)
            video.save_png(119, last_png)
        self.assertEqual(first_png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(last_png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertNotEqual(sha_file(first_png), sha_file(last_png))
        print("FFMS2 first-index-seconds=", round(first_seconds, 3),
              "reused-index-file=", result["index_size_bytes"])

    def test_same_size_original_tamper_invalidates_cached_index(self):
        self.cache.get_or_create(self.pid, "take01", self.source, self.sha)
        with self.source.open("r+b") as src:
            src.seek(200)
            src.write(b"NVPCHANGE")
        with self.assertRaisesRegex(RuntimeError, "differs"):
            self.cache.get_or_create(self.pid, "take01", self.source, self.sha)

    def test_index_manifest_tamper_and_32bit_frame_bounds(self):
        result = self.cache.get_or_create(self.pid, "take01", self.source, self.sha)
        json_path = Path(result["index_path"]).with_suffix(".json")
        manifest = json.loads(json_path.read_bytes())
        manifest["source_sha256"] = "0" * 64
        json_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.cache.get_or_create(self.pid, "take01", self.source, self.sha)
        with self.ffms.open_video(self.source, result["index_path"]) as reader:
            with self.assertRaises(ValueError):
                reader.save_png(MAX_FFMS_FRAME, self.root / "invalid.png")

    def test_native_creator_approved_indexed_review_window(self):
        index = FilmIndex(self.studio)
        sources = ExternalMediaCatalog(self.studio)
        inv = SourceMediaInventory(sources)
        bridge = SourceFilmBridge(index, inv)
        edit = BoundEditorialPublisher(index)
        inv.register_volume(self.pid, "card", self.volume, label="SD Card")
        sources.register(self.pid, "take01", self.source, media_type="video/quicktime")
        inv.enrich(self.pid, "take01", "card")
        source = bridge.register_source_revision(self.pid, "take01")
        edit.publish(self.pid, "scene_cut", [
            {"source_id": "take01", "source_revision": 1,
             "source_first_frame": 112, "frame_count": 5},
            {"source_id": "take01", "source_revision": 1,
             "source_first_frame": 4, "frame_count": 5},
        ])
        ledger = TaskLedger(
            self.root / "ledger",
            sampler=lambda: ResourceSnapshot(1,32768,25000,0,()))
        host = NativeSourceWindowHost(
            SourceWindowPreflight(edit, bridge), ledger, self.root / "jobs",
            verify_creator_action=lambda event, _: event == "creator_yes",
            decoder_backend="ffms2", ffms2_library=self.ffms_path,
            ffms2_cache_root=self.root / "index-cache")
        ticket = host.stage_and_approve(
            self.pid, "scene_cut", 1, first_frame=3, frame_count=6,
            destination=self.root / "review", creator_event="creator_yes",
            ram_mb=1024)
        self.assertEqual(ticket["state"], "QUEUED")
        done = host.run_next(timeout_seconds=120)
        self.assertEqual(done["state"], "SUCCEEDED")
        self.assertEqual(done["frames"], 6)
        receipt = json.loads((self.root / "review" / "review_receipt.json").read_bytes())
        self.assertEqual(receipt["decoder_backend"], "ffms2")
        self.assertEqual([f["frame"] for f in receipt["frames"]], [3,4,5,6,7,8])
        self.assertEqual([f["source_frame_zero"] for f in receipt["frames"]],
                         [113,114,115,3,4,5])
        self.assertEqual({f["index_sha256"] for f in receipt["frames"]},
                         {self.cache.get_or_create(
                             self.pid, "take01", self.source, self.sha)["index_sha256"]})
        self.assertEqual(ledger.get_task(ticket["task_id"])["reserved"], 0)
        self.assertEqual(host.verify_completed(ticket["task_id"])["frames"], 6)
        plan = self.root / "jobs" / ticket["task_id"] / "window_plan.json"
        original = plan.read_bytes()
        plan.write_bytes(b"{}")
        with self.assertRaises(RuntimeError):
            host.verify_completed(ticket["task_id"])
        plan.write_bytes(original)
        self.source.unlink()
        # A missing original may not be processed; metadata and completed
        # output receipt nevertheless remain available.
        self.assertEqual(host.verify_completed(ticket["task_id"])["frames"], 6)
        self.assertEqual(source["revision"], 1)

    def test_no_silent_fallback_when_ffms2_not_configured(self):
        sources = ExternalMediaCatalog(self.studio)
        inv = SourceMediaInventory(sources)
        index = FilmIndex(self.studio)
        editor = BoundEditorialPublisher(index)
        bridge = SourceFilmBridge(index, inv)
        ledger = TaskLedger(
            self.root / "other_ledger",
            sampler=lambda: ResourceSnapshot(1,32768,25000,0,()))
        with self.assertRaises(RuntimeError):
            NativeSourceWindowHost(
                SourceWindowPreflight(editor, bridge), ledger,
                self.root / "no-engine", verify_creator_action=lambda *_: True,
                decoder_backend="ffms2")


if __name__ == "__main__":
    unittest.main()
