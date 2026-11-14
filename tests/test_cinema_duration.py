"""CINEMA-01C: source duration is authoritative; any DCP padding is explicit."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch

from backend.nvp_cinema_duration import (
    DURATION_EXACT, DURATION_PAD,
    plan_cinema_duration, validate_duration_contract,
)
from backend.nvp_cinema_essence import _prove_black_tail


class CinemaDurationTests(unittest.TestCase):
    def test_exact_mode_keeps_full_second_take_unchanged(self):
        c = plan_cinema_duration(24, 24)
        self.assertEqual((c["source_frames"], c["dcp_frames"], c["black_tail_frames"]),
                         (24, 24, 0))
        self.assertEqual(c["source_samples_48000"], 48000)
        self.assertEqual(validate_duration_contract(c, 24, 24), c)

    def test_subsecond_take_fails_closed_by_default(self):
        with self.assertRaisesRegex(RuntimeError, "under one second"):
            plan_cinema_duration(16, 24)

    def test_explicit_16_to_24_tail_has_exact_sample_ledger(self):
        c = plan_cinema_duration(16, 24, DURATION_PAD)
        self.assertEqual(c["black_tail_frames"], 8)
        self.assertEqual(c["source_samples_48000"], 32000)
        self.assertEqual(c["dcp_samples_48000"], 48000)
        self.assertEqual(c["status"], "explicit_padded_technical_only")
        self.assertEqual(validate_duration_contract(c, 16, 24), c)

    def test_forbid_open_ended_or_unnecessary_padding(self):
        for count, policy in ((0, DURATION_PAD), (241, DURATION_EXACT)):
            with self.assertRaises(ValueError):
                plan_cinema_duration(count, 24, policy)
        with self.assertRaisesRegex(ValueError, "only valid"):
            plan_cinema_duration(24, 24, DURATION_PAD)
        with self.assertRaises(ValueError):
            plan_cinema_duration(16, 25, DURATION_PAD)
        with self.assertRaises(ValueError):
            plan_cinema_duration(16, 24, "pad_anyway")

    def test_tampered_duration_and_source_receipts_refused(self):
        c = plan_cinema_duration(16, 24, DURATION_PAD)
        for field, forged in (
            ("dcp_frames", 48),
            ("black_tail_frames", 0),
            ("fps", 25),
            ("source_samples_48000", 0),
            ("status", "cinema_ready"),
        ):
            changed = dict(c)
            changed[field] = forged
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "inconsistent"):
                validate_duration_contract(changed, 16, 24)
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            validate_duration_contract(c, 15, 24)


class CinemaBlackTailProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "picture.mxf"
        self.path.write_bytes(b"synthetic placeholder, no real codec proof")
        self.tail = bytes(8 * 2 * 2 * 3)

    def tearDown(self):
        self.temp.cleanup()

    def _call(self, result=None):
        if result is None:
            result = subprocess.CompletedProcess(["ffmpeg"], 0, self.tail, b"")
        with patch("backend.nvp_cinema_essence.subprocess.run", return_value=result) as cmd:
            proof = _prove_black_tail(self.path, 16, 8, [2, 2], "ffmpeg", 25)
        self.assertIn("select=gte", " ".join(cmd.call_args[0][0]))
        return proof

    def test_all_pixels_all_channels_zero_and_byte_count_exact(self):
        p = self._call()
        self.assertEqual(p["decoded_black_bytes"], 96)
        self.assertEqual(p["padded_frames"], 8)
        self.assertEqual(p["status"], "independent_exact_zero_tail")
        self.assertEqual(len(p["rgb_sha256"]), 64)

    def test_nonblack_even_one_channel_rejected(self):
        self.tail = bytes(95) + b"\x01"
        with self.assertRaisesRegex(RuntimeError, "not completely black"):
            self._call()

    def test_partial_or_extra_decoded_frame_rejected(self):
        for b in (bytes(95), bytes(97)):
            with self.subTest(length=len(b)), self.assertRaisesRegex(RuntimeError, "byte count"):
                self._call(subprocess.CompletedProcess([], 0, b, b""))

    def test_decoder_nonzero_and_unsafe_duration_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "decode failed"):
            self._call(subprocess.CompletedProcess([], 1, b"", b"decoder error"))
        with self.assertRaisesRegex(RuntimeError, "unbounded"):
            _prove_black_tail(self.path, 16, 24, [2, 2], "ffmpeg", 25)


if __name__ == "__main__":
    unittest.main()
