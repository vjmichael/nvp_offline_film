"""FILM01 full-film native QC smoke refuses incomplete and counterfeit originals.

These native smoke tests author REAL frozen OpenUSD Takes and REAL source
PNG/PCM. They deliberately render six frames only to test the strong
30-second completeness guard. Full 720 acceptance is a separate job.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_film01_original_30s import (
    write_original_30s_source,render_original_30s_review)
from tools.nvp_film01_native_visual_audio_qc import inspect_original_nvp_film


class OriginalVisualSoundQC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.root=Path(cls.temp.name).resolve()
        cls.source=cls.root/"original_filming_project"
        cls.orig=write_original_30s_source(
            cls.source,approve_test_only=True)
        cls.partial=cls.root/"real_six_source_frames.zip"
        render_original_30s_review(
            cls.source,cls.partial,max_frames=6)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_six_frame_openusd_smoke_cannot_pass_as_30_second_film(self):
        output=self.root/"fake-full-qc.json"
        with self.assertRaises(PermissionError):
            inspect_original_nvp_film(self.partial,output)
        self.assertFalse(output.exists())

    def test_unverified_partial_six_frame_films_cannot_pass_even_with_expected_receipts(self):
        partial_copy=self.root/"missing-original-media.zip"
        partial_copy.write_bytes(b"ZIP_NOT_RENDERED")
        with self.assertRaises(Exception):
            inspect_original_nvp_film(
                partial_copy,self.root/"invalid-original-output.json")

    def test_disallow_bypassing_full_720_requirement(self):
        with self.assertRaises(PermissionError):
            inspect_original_nvp_film(
                self.partial,self.root/"not-full.json",require_complete=False)


if __name__=="__main__":
    unittest.main()
