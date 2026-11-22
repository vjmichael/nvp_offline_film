"""CINEMA-01B picture-evidence unit tests; native tools are mocked.

These tests prove rejection/receipt logic, NOT that a real DCP was produced.
The real DCP-o-matic + FFprobe + FFmpeg gate remains separate.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_cinema_essence import audit_dcp_picture_essence


class DCPPictureEssenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "reel_picture.mxf").write_bytes(b"not-a-real-mxf")
        (self.root / "reel_sound.mxf").write_bytes(b"not-a-real-mxf")
        self.probe_calls = []
        self.decode_calls = []
        self.codec = "jpeg2000"
        self.fps = "24/1"
        self.width = 1998
        self.height = 1080
        self.frames = 16
        self.fail_decode = False

    def tearDown(self):
        self.tmp.cleanup()

    def fake_run(self, args, **kwargs):
        if "-count_frames" in args:
            self.probe_calls.append(list(args))
            video = [] if "sound" in args[-1] else [{
                "codec_type": "video",
                "codec_name": self.codec,
                "width": self.width,
                "height": self.height,
                "r_frame_rate": self.fps,
                "nb_read_frames": str(self.frames),
            }]
            return subprocess.CompletedProcess(args, 0, json.dumps({"streams": video}), "")
        self.decode_calls.append(list(args))
        return subprocess.CompletedProcess(
            args, 1 if self.fail_decode else 0, "",
            "decoder failed" if self.fail_decode else "",
        )

    def audited(self, **changes):
        kw = {"expected_raster": [1998, 1080], "expected_fps": 24,
              "expected_frames": 16}
        kw.update(changes)
        with patch(
            "backend.nvp_cinema_essence.shutil.which", side_effect=lambda n: n
        ), patch("backend.nvp_cinema_essence.subprocess.run", side_effect=self.fake_run):
            return audit_dcp_picture_essence(self.root, **kw)

    def test_one_picture_reel_and_one_sound_reel_produce_bounded_receipt(self):
        audit = self.audited()
        self.assertEqual(audit["total_decoded_frames"], 16)
        self.assertEqual(len(audit["picture_reels"]), 1)
        self.assertEqual(len(self.probe_calls), 2)
        self.assertEqual(len(self.decode_calls), 1)
        self.assertEqual(audit["picture_reels"][0]["codec"], "jpeg2000")
        self.assertIn("technical_only", audit["status"])

    def test_refuses_codec_raster_and_rate_mismatches(self):
        cases = [
            ("codec", "h264", "JPEG 2000"),
            ("width", 2048, "raster"),
            ("fps", "25/1", "frame rate"),
        ]
        for attr, value, error in cases:
            with self.subTest(attr=attr):
                old = getattr(self, attr)
                setattr(self, attr, value)
                try:
                    with self.assertRaisesRegex(RuntimeError, error):
                        self.audited()
                finally:
                    setattr(self, attr, old)

    def test_refuses_extra_or_missing_frames(self):
        self.frames = 17
        with self.assertRaisesRegex(RuntimeError, "beyond"):
            self.audited()
        self.frames = 15
        with self.assertRaisesRegex(RuntimeError, "differs"):
            self.audited()

    def test_refuses_decoder_failure_even_when_probe_looks_correct(self):
        self.fail_decode = True
        with self.assertRaisesRegex(RuntimeError, "decode failed"):
            self.audited()

    def test_refuses_sound_only_and_symlinked_picture(self):
        (self.root / "reel_picture.mxf").unlink()
        with self.assertRaisesRegex(RuntimeError, "lacks independently decoded"):
            self.audited()
        (self.root / "reel_picture.mxf").symlink_to(self.root / "reel_sound.mxf")
        with self.assertRaisesRegex(RuntimeError, "Unsafe MXF path"):
            self.audited()

    def test_no_real_tools_no_false_evidence(self):
        with patch("backend.nvp_cinema_essence.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "requires ffprobe"):
                audit_dcp_picture_essence(
                    self.root, expected_raster=[1998, 1080],
                    expected_fps=24, expected_frames=16,
                )


if __name__ == "__main__":
    unittest.main()
