"""SCALE-03C: real NVP-owned index, B-frames, no rehash on interactive seeks.

Native acceptance; no FFMS2 and no mocked frame decodes.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

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
from backend.nvp_native_frame_index import NVPFrameIndex, stamp
from backend.nvp_indexed_preview import extract


class NativeOwnedIndexTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.fail("Actual FFmpeg and FFprobe required for NVP native frame-index acceptance")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = self.root / "camera_sd"
        self.card.mkdir()
        self.movie = self.card / "long_gop.mov"
        subprocess.run([
            self.ffmpeg, "-hide_banner", "-v", "error", "-nostdin",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24000/1001",
            "-frames:v", "150", "-c:v", "mpeg4", "-bf", "2",
            "-g", "24", "-q:v", "3", "-y", str(self.movie),
        ], check=True, timeout=60)
        self.studio = Studio(self.root / "studio.sqlite")
        self.pid = self.studio.create_project("Film", "NVP-owned index")["id"]
        self.catalog = ExternalMediaCatalog(self.studio)
        self.inventory = SourceMediaInventory(self.catalog)
        self.index = FilmIndex(self.studio)
        self.bridge = SourceFilmBridge(self.index, self.inventory)
        self.editor = BoundEditorialPublisher(self.index)
        self.preflight = SourceWindowPreflight(self.editor, self.bridge)
        self.inventory.register_volume(self.pid, "sd_card", self.card, label="Original SD")
        self.catalog.register(self.pid, "camera_take", self.movie,
                              media_type="video/quicktime")
        self.inventory.enrich(self.pid, "camera_take", "sd_card")
        self.bridge.register_source_revision(self.pid, "camera_take")
        self.sha = self.catalog.list_assets(self.pid)[0]["sha256"]
        self.cache = NVPFrameIndex(self.root / "index_cache",
                                   ffprobe=Path(self.ffprobe))

    def test_bframes_index_and_fast_seek_without_original_rehash(self):
        with patch("backend.nvp_external_media_catalog._read_and_hash",
                   side_effect=AssertionError("Original SHA must not run during preview")):
            cold = self.cache.ensure(self.pid, "camera_take", self.sha, self.movie)
            self.assertEqual(cold["frame_count"], 150)
            self.assertEqual(cold["status"], "CREATED_SOURCE_STAMP_UNVERIFIED")
            warm = self.cache.ensure(self.pid, "camera_take", self.sha, self.movie)
            self.assertEqual(warm["status"], "REUSED_SOURCE_STAMP_UNVERIFIED")
            wanted = self.cache.window(
                self.pid, "camera_take", self.sha, self.movie,
                first_zero=129, count=6)
            self.assertLess(wanted["seek_anchor"]["ordinal"], 129)
            dest = self.root / "preview"
            dest.mkdir()
            result = extract(
                self.cache, ffmpeg=Path(self.ffmpeg),
                project=self.pid, asset="camera_take",
                source_sha=self.sha, source=self.movie,
                first_zero=129, count=6, first_output=17,
                output_dir=dest)
        self.assertFalse(result["source_sha_verified_this_operation"])
        self.assertEqual(result["status"], "DECODED_REVIEW_SOURCE_UNVERIFIED")
        self.assertEqual([r["source_frame_zero"] for r in result["frames"]],
                         list(range(129, 135)))
        self.assertEqual([r["pts"] for r in result["frames"]],
                         [r["pts"] for r in wanted["frames"]])

    def test_same_size_change_invalidates_stamp_but_not_provenance_claim(self):
        self.cache.ensure(self.pid, "camera_take", self.sha, self.movie)
        with self.movie.open("r+b") as stream:
            stream.seek(120)
            stream.write(b"NVPCHANGED")
        with self.assertRaises(RuntimeError):
            self.cache.ensure(self.pid, "camera_take", self.sha, self.movie)
        # This check is deliberately expensive and belongs to a custody gate,
        # not to interactive scrubbing or the preview index lookup.
        self.assertEqual(self.catalog.probe(
            self.pid, "camera_take", verify_bytes=True)["status"], "CHANGED")

    def test_fast_preview_and_verified_full_are_distinct(self):
        self.editor.publish(self.pid, "cut01", [
            {"source_id": "camera_take", "source_revision": 1,
             "source_first_frame": 20, "frame_count": 12}])
        with patch("backend.nvp_external_media_catalog._read_and_hash",
                   side_effect=AssertionError("Unexpected whole-source SHA")):
            plan = self.preflight.prepare(
                self.pid, "cut01", 1, first_frame=4,
                frame_count=3, integrity_policy="preview")
        self.assertEqual(plan["source_preflight"],
                         "PRESENT_UNVERIFIED_PREVIEW_ONLY")
        strong = self.preflight.prepare(
            self.pid, "cut01", 1, first_frame=4, frame_count=3)
        self.assertEqual(strong["source_preflight"], "VERIFIED_AT_PREPARATION")

    def test_native_approved_indexed_window_restart_and_receipt_tamper(self):
        self.editor.publish(self.pid, "cut01", [
            {"source_id": "camera_take", "source_revision": 1,
             "source_first_frame": 110, "frame_count": 12},
            {"source_id": "camera_take", "source_revision": 1,
             "source_first_frame": 10, "frame_count": 12},
        ], fps_num=24000, fps_den=1001)
        ledger = TaskLedger(
            self.root / "ledger",
            sampler=lambda: ResourceSnapshot(1, 32768, 25000, 0, ()))
        host = NativeSourceWindowHost(
            self.preflight, ledger, self.root / "native_jobs",
            verify_creator_action=lambda event, scope: event == "creator_yes",
            decoder_backend="nvp_index",
            ffprobe_path=Path(self.ffprobe),
            index_cache_root=self.root / "index_cache")
        with patch("backend.nvp_external_media_catalog._read_and_hash",
                   side_effect=AssertionError("Preview should not hash whole original")):
            ticket = host.stage_and_approve(
                self.pid, "cut01", 1, first_frame=10, frame_count=6,
                destination=self.root / "review",
                creator_event="creator_yes", ram_mb=1024)
            self.assertEqual(ticket["state"], "QUEUED")
            result = host.run_next(timeout_seconds=120)
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertEqual(result["source_integrity"], "UNVERIFIED_FAST_PREVIEW")
        receipt = json.loads((self.root / "review" / "review_receipt.json").read_bytes())
        self.assertEqual(receipt["decoder_backend"], "nvp_sqlite_index_v1")
        self.assertFalse(receipt["source_sha_rehashed"])
        self.assertEqual([x["source_frame_zero"] for x in receipt["frames"]],
                         [118,119,120,9,10,11])
        self.assertEqual(host.verify_completed(ticket["task_id"])["frames"], 6)
        self.movie.unlink()
        self.assertEqual(host.verify_completed(ticket["task_id"])["frames"], 6)
        receipt_file = self.root / "review" / "review_receipt.json"
        receipt["frames"][0]["source_frame_zero"] += 1
        receipt_file.write_text(json.dumps(receipt, sort_keys=True,
                                           separators=(",", ":")))
        with self.assertRaises(RuntimeError):
            host.verify_completed(ticket["task_id"])

    def test_index_rejects_foreign_project(self):
        self.cache.ensure(self.pid, "camera_take", self.sha, self.movie)
        with self.assertRaises(ValueError):
            self.cache.ensure("bad-id", "camera_take", self.sha, self.movie)


if __name__ == "__main__":
    unittest.main()
