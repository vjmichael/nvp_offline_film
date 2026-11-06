"""SCALE-03B: genuine FFmpeg review-window extraction under native resource custody."""
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
from backend.nvp_source_window_decode import verify_review_window
from backend.nvp_source_window_native_host import NativeSourceWindowHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot


class RealSourceWindowNativeContracts(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("Real FFmpeg and FFprobe required for native acceptance")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.studio = Studio(self.root / "studio.sqlite")
        self.pid = self.studio.create_project("Short", "Native sources")["id"]
        self.index = FilmIndex(self.studio)
        self.catalog = ExternalMediaCatalog(self.studio)
        self.inventory = SourceMediaInventory(self.catalog)
        self.bridge = SourceFilmBridge(self.index, self.inventory)
        self.publisher = BoundEditorialPublisher(self.index)
        self.preflight = SourceWindowPreflight(self.publisher, self.bridge)
        self.ledger = TaskLedger(
            self.root / "ledger",
            sampler=lambda: ResourceSnapshot(1, 32768, 25000, 0, ()))
        self.host = NativeSourceWindowHost(
            self.preflight, self.ledger, self.root / "jobs",
            verify_creator_action=lambda event, scope: event == "creator_ok")
        self.volume = self.root / "camera_card"
        self.volume.mkdir()
        self.inventory.register_volume(self.pid, "card", self.volume,
                                       label="Original camera SD")
        self.source = self.volume / "shot.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin",
                        "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24",
                        "-frames:v", "24", "-c:v", "mpeg4", "-q:v", "4",
                        "-y", str(self.source)], check=True, timeout=60)
        self.catalog.register(self.pid, "original01", self.source,
                              media_type="video/quicktime")
        self.inventory.enrich(self.pid, "original01", "card")
        self.bridge.register_source_revision(self.pid, "original01")
        self.publisher.publish(self.pid, "cut01", [
            {"source_id": "original01", "source_revision": 1,
             "source_first_frame": 7, "frame_count": 6},
            {"source_id": "original01", "source_revision": 1,
             "source_first_frame": 2, "frame_count": 5},
        ])

    def stage(self, *, destination=None, creator_event="creator_ok"):
        return self.host.stage_and_approve(
            self.pid, "cut01", 1, first_frame=4, frame_count=5,
            destination=destination or self.root / "review",
            creator_event=creator_event, ram_mb=1024)

    def test_real_contained_two_clip_window_with_restart_verification(self):
        job = self.stage()
        self.assertEqual(job["state"], "QUEUED")
        self.assertFalse(job["native_worker_started"])
        result = self.host.run_next(timeout_seconds=120)
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertEqual(result["frames"], 5)
        pngs = list((self.root / "review").glob("review_*.png"))
        self.assertEqual(len(pngs), 5)
        self.assertEqual(self.ledger.get_task(job["task_id"])["reserved"], 0)
        reopened = NativeSourceWindowHost(
            SourceWindowPreflight(
                BoundEditorialPublisher(FilmIndex(Studio(self.studio.db_path))),
                SourceFilmBridge(
                    FilmIndex(Studio(self.studio.db_path)),
                    SourceMediaInventory(
                        ExternalMediaCatalog(Studio(self.studio.db_path))))),
            TaskLedger(self.root / "ledger",
                       sampler=lambda: ResourceSnapshot(1,32768,25000,0,())),
            self.root / "jobs",
            verify_creator_action=lambda event, scope: False)
        check = reopened.verify_completed(job["task_id"])
        self.assertEqual(check["status"], "VERIFIED_UNAPPROVED_SOURCE_REVIEW")
        plan_file = self.root / "jobs" / job["task_id"] / "window_plan.json"
        original_plan = plan_file.read_bytes()
        plan_file.write_bytes(b"{}")
        with self.assertRaises(RuntimeError):
            reopened.verify_completed(job["task_id"])
        plan_file.write_bytes(original_plan)
        frame = self.root / "review" / "review_000000004.png"
        frame.write_bytes(b"altered")
        with self.assertRaises(RuntimeError):
            reopened.verify_completed(job["task_id"])

    def test_revoked_or_invalid_creator_event_cannot_queue(self):
        with self.assertRaises(PermissionError):
            self.stage(creator_event="not_creator")
        self.assertIsNone(self.host.run_next())

    def test_offline_media_refused_before_approval(self):
        self.source.unlink()
        with self.assertRaises(RuntimeError):
            self.stage()
        self.assertFalse((self.root / "review").exists())

    def test_tamper_between_queue_and_worker_refuses_execution(self):
        job = self.stage()
        with self.source.open("r+b") as stream:
            stream.seek(120)
            stream.write(b"changed")
        with self.assertRaises(RuntimeError):
            self.host.run_next(timeout_seconds=120)
        state = self.ledger.get_task(job["task_id"])
        self.assertNotEqual(state["state"], "SUCCEEDED")
        self.assertFalse((self.root / "review").exists())


if __name__ == "__main__":
    unittest.main()
