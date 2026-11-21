"""SCALE-02B native media metadata, storage-volume and relink contracts."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import (
    SourceMediaInventory, ffprobe_media, normalize_probe,
)


class MetadataNormalizationTests(unittest.TestCase):
    def test_exact_rational_and_color_data(self):
        source = {"streams": [
            {"index": 0, "codec_type": "video", "codec_name": "prores",
             "width": 1920, "height": 1080, "time_base": "1/24000",
             "avg_frame_rate": "24000/1001", "r_frame_rate": "24000/1001",
             "pix_fmt": "yuv422p10le", "color_primaries": "bt709",
             "color_transfer": "bt709"},
            {"index": 1, "codec_type": "audio", "codec_name": "pcm_s24le",
             "time_base": "1/48000", "channels": 2,
             "channel_layout": "stereo", "sample_rate": "48000"}],
            "format": {"format_name": "mov,mp4", "duration": "1.001"}}
        record = normalize_probe(source)
        self.assertEqual(record["streams"][0]["avg_frame_rate"], "24000/1001")
        self.assertEqual(record["streams"][1]["time_base"], "1/48000")
        self.assertFalse(record["decoded_and_verified"])

    def test_invalid_native_metadata_rejected(self):
        with self.assertRaises(RuntimeError):
            normalize_probe({"streams": [{"index": 0, "codec_type": "video",
                                         "width": -1, "height": 1080}]})
        with self.assertRaises(RuntimeError):
            normalize_probe({"streams": [{"index": 0, "codec_type": "video",
                                         "width": 10, "height": 10,
                                         "time_base": "0/0",
                                         "avg_frame_rate": "a/b"}]})


class RealNativeSourceInventoryTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("Real FFmpeg and FFprobe required for native metadata acceptance")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.drive_a = root / "originals"
        self.drive_b = root / "moved"
        self.drive_a.mkdir()
        self.drive_b.mkdir()
        self.studio = Studio(root / "studio.sqlite")
        self.project = self.studio.create_project("Long Film", "Source inventory")
        self.catalog = ExternalMediaCatalog(self.studio)
        self.inventory = SourceMediaInventory(self.catalog)
        self.movie = self.drive_a / "camera.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin",
                        "-f", "lavfi", "-i", "testsrc2=size=128x72:rate=24000/1001",
                        "-t", "1", "-c:v", "mpeg4", "-q:v", "5", "-y", str(self.movie)],
                       check=True, timeout=60)
        self.pid = self.project["id"]
        self.inventory.register_volume(self.pid, "drive_one", self.drive_a,
                                       label="Original Footage")
        self.catalog.register(self.pid, "camera_take_one", self.movie,
                              media_type="video/quicktime")

    def test_real_probe_and_offline_metadata_after_restart(self):
        report = self.inventory.enrich(self.pid, "camera_take_one", "drive_one")
        video = report["media"]["streams"][0]
        self.assertEqual(video["width"], 128)
        self.assertEqual(video["height"], 72)
        self.assertEqual(video["avg_frame_rate"], "24000/1001")
        self.assertFalse(report["media"]["decoded_and_verified"])
        self.movie.unlink()
        fresh = SourceMediaInventory(ExternalMediaCatalog(Studio(self.studio.db_path)))
        state = fresh.describe(self.pid, "camera_take_one")
        self.assertEqual(state["availability"], "OFFLINE")
        self.assertEqual(state["media"]["streams"][0]["width"], 128)

    def test_relink_requires_exact_bytes_and_is_atomic(self):
        self.inventory.enrich(self.pid, "camera_take_one", "drive_one")
        relocated = self.drive_b / self.movie.name
        shutil.copyfile(self.movie, relocated)
        with relocated.open("r+b") as stream:
            stream.seek(100)
            stream.write(b"broken")
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.inventory.relink_volume(self.pid, "drive_one", self.drive_b)
        self.assertEqual(self.inventory.describe(self.pid, "camera_take_one")["availability"],
                         "PRESENT_UNVERIFIED")
        shutil.copyfile(self.movie, relocated)
        result = self.inventory.relink_volume(self.pid, "drive_one", self.drive_b)
        self.assertEqual(result["relinked_assets"], 1)
        self.movie.unlink()
        self.assertEqual(self.catalog.probe(self.pid, "camera_take_one",
                                            verify_bytes=True)["status"], "VERIFIED")

    def test_cross_project_volume_isolation(self):
        other = self.studio.create_project("Second Film", "Separate library")
        with self.assertRaises(KeyError):
            self.inventory.enrich(other["id"], "camera_take_one", "drive_one")
        with self.assertRaises(KeyError):
            self.inventory.describe(other["id"], "camera_take_one")


if __name__ == "__main__":
    unittest.main()
