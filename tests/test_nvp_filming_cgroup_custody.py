"""Contract tests only; real delegated cgroup and descendant tests remain OS gates."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_filming_cgroup_custody import LinuxFilmingCgroup, CgroupCustodyError


class LinuxCgroupCustodyContractTests(unittest.TestCase):
    def _owned(self, path):
        worker = LinuxFilmingCgroup.__new__(LinuxFilmingCgroup)
        worker._group = path
        worker._consumed = False
        return worker

    def test_rejects_bad_deadlines_without_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cgroup.kill").write_text("")
            worker = self._owned(root)
            for value in (0, -1, float("nan"), float("inf"), True, 61):
                with self.assertRaises(ValueError):
                    worker.stop_and_verify(timeout=value)
            self.assertEqual((root / "cgroup.kill").read_text(), "")

    def test_empty_group_receipt_is_one_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cgroup.kill").write_text("")
            (root / "cgroup.events").write_text("populated 0\nfrozen 0\n")
            worker = self._owned(root)
            receipt = worker.stop_and_verify(timeout=1)
            self.assertTrue(receipt["process_tree_custody_verified"])
            self.assertEqual((root / "cgroup.kill").read_text(), "1")
            with self.assertRaises(CgroupCustodyError):
                worker.stop_and_verify(timeout=1)

    def test_timeout_retry_does_not_reissue_cgroup_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cgroup.kill").write_text("")
            (root / "cgroup.events").write_text("populated 1\n")
            worker = self._owned(root)
            with patch("backend.nvp_filming_cgroup_custody.time.sleep", return_value=None):
                with self.assertRaises(CgroupCustodyError):
                    worker.stop_and_verify(timeout=0.001)
            self.assertEqual((root / "cgroup.kill").read_text(), "1")
            # A retry after timeout must only recheck kernel custody state.
            (root / "cgroup.kill").write_text("sentinel")
            (root / "cgroup.events").write_text("populated 0\n")
            receipt = worker.stop_and_verify(timeout=1)
            self.assertTrue(receipt["empty_group_verified"])
            self.assertEqual((root / "cgroup.kill").read_text(), "sentinel")
            with self.assertRaises(CgroupCustodyError):
                worker.stop_and_verify(timeout=1)

    def test_still_populated_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cgroup.kill").write_text("")
            (root / "cgroup.events").write_text("populated 1\n")
            worker = self._owned(root)
            with patch("backend.nvp_filming_cgroup_custody.time.sleep", return_value=None):
                with self.assertRaises(CgroupCustodyError):
                    worker.stop_and_verify(timeout=0.001)
            self.assertFalse(worker._consumed)


if __name__ == "__main__":
    unittest.main()
