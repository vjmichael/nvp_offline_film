"""Kernel-backed no-clobber and recovery evidence, including collision behavior."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.nvp_wo3_atomic_publish import atomic_publish_directory


class AtomicExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.stage = self.root / ".nvp-wo3-stage"
        self.stage.mkdir()
        (self.stage / "CPL.xml").write_bytes(b"good")
        self.dst = self.root / "DCP_final"

    def test_native_no_replace_commits_whole_directory(self):
        if sys.platform not in ("linux", "win32"):
            self.skipTest("No approved OS no-replace primitive")
        result = atomic_publish_directory(self.stage, self.dst)
        self.assertEqual(result["status"], "ATOMIC_NO_REPLACE_PROMOTED")
        self.assertEqual((self.dst / "CPL.xml").read_bytes(), b"good")
        self.assertFalse(self.stage.exists())
        self.assertFalse(result["power_loss_durability_certified"])

    def test_existing_empty_or_nonempty_destination_is_never_replaced(self):
        for populated in (False, True):
            with self.subTest(populated=populated):
                target = self.root / ("occupied_" + str(populated))
                target.mkdir()
                if populated:
                    (target / "owned").write_bytes(b"creator")
                with self.assertRaises(FileExistsError):
                    atomic_publish_directory(self.stage, target)
                self.assertTrue(self.stage.exists())
                self.assertTrue(target.exists())
                if populated:
                    self.assertEqual((target / "owned").read_bytes(), b"creator")

    def test_linked_destination_is_rejected(self):
        target = self.root / "linked"
        try:
            target.symlink_to(self.stage, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink privilege on host")
        with self.assertRaises(PermissionError):
            atomic_publish_directory(self.stage, target)

    def test_must_be_same_approved_parent(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(PermissionError):
            atomic_publish_directory(self.stage, other / "output")

    def test_kernel_collision_even_if_precheck_races(self):
        if sys.platform != "linux":
            self.skipTest("Linux renameat2 test")
        # An adversarial writer creates the destination after the advisory
        # precheck. The kernel must fail, not replace that directory.
        orig_exists = Path.exists
        target = self.dst
        calls = {"count": 0}
        def adversarial_exists(path):
            if path == target and calls["count"] == 0:
                calls["count"] += 1
                target.mkdir()
                (target / "owner").write_text("keep")
                return False
            return orig_exists(path)
        with patch.object(Path, "exists", adversarial_exists):
            with self.assertRaises(FileExistsError):
                atomic_publish_directory(self.stage, target)
        self.assertEqual((target / "owner").read_text(), "keep")
        self.assertTrue(self.stage.exists())


if __name__ == "__main__":
    unittest.main()
