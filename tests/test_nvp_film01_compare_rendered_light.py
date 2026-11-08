"""FILM01 creative look comparison refuses incomplete real source films."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_film01_original_30s import (
    write_original_30s_source,render_original_30s_review)
from tools.nvp_film01_compare_rendered_light import compare_native_light_versions


class FullOriginalRenderComparisonGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.root=Path(cls.temp.name).resolve()
        cls.source=cls.root/"short-original"
        write_original_30s_source(cls.source,approve_test_only=True)
        cls.baseline=cls.root/"only-six-original-frames.zip"
        cls.virtual=cls.root/"six-virtual-original-frames.zip"
        render_original_30s_review(cls.source,cls.baseline,max_frames=6)
        render_original_30s_review(
            cls.source,cls.virtual,max_frames=6,apply_virtual_fx=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_two_real_six_frame_openusd_renders_cannot_impersonate_comparable_complete_30s(self):
        dest=self.root/"fake-passing-look-contact.png"
        with self.assertRaises(PermissionError):
            compare_native_light_versions(
                self.baseline,self.virtual,dest,
                self.root/"fake-passing-look-report.json")
        self.assertFalse(dest.exists())

    def test_missing_second_original_render_is_not_replaced_with_dummy_frame(self):
        dest=self.root/"missing-version-contact.png"
        with self.assertRaises(FileNotFoundError):
            compare_native_light_versions(
                self.baseline,self.root/"not-rendered.zip",dest,
                self.root/"missing-report.json")
        self.assertFalse(dest.exists())


if __name__=="__main__":
    unittest.main()
