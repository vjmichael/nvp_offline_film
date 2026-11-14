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
        identity = path.stat()
        worker._group_identity = (identity.st_dev, identity.st_ino)
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

    def test_ambiguous_kernel_events_never_issue_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cgroup.kill").write_text("")
            worker = self._owned(root)
            for events in ("populated 1\npopulated 0\n",
                           "populated 0 extra\n",
                           "populated\n",
                           "populated 0\nmalformed\n"):
                (root / "cgroup.events").write_text(events)
                with self.assertRaises(CgroupCustodyError):
                    worker.stop_and_verify(timeout=1)
                self.assertFalse(worker._consumed)
            self.assertEqual((root / "cgroup.kill").read_text(), "1")

    def test_replaced_group_never_receives_kill_or_exit_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            group = parent / "owned"
            group.mkdir()
            (group / "cgroup.kill").write_text("")
            (group / "cgroup.events").write_text("populated 0\n")
            worker = self._owned(group)
            group.rename(parent / "old")
            group.mkdir()
            (group / "cgroup.kill").write_text("")
            (group / "cgroup.events").write_text("populated 0\\n")
            with self.assertRaises(CgroupCustodyError):
                worker.stop_and_verify(timeout=1)
            self.assertEqual((group / "cgroup.kill").read_text(), "")
            self.assertFalse(worker._consumed)

    def test_control_symlink_cannot_redirect_kernel_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = root / "owned"
            group.mkdir()
            outside = root / "outside"
            outside.write_text("untouched")
            (group / "cgroup.kill").symlink_to(outside)
            (group / "cgroup.events").write_text("populated 0\\n")
            worker = self._owned(group)
            with self.assertRaises(OSError):
                worker.stop_and_verify(timeout=1)
            self.assertEqual(outside.read_text(), "untouched")
            self.assertFalse(worker._consumed)

    def test_ambiguous_kill_write_never_reissues_on_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cgroup.kill").write_text("")
            (root / "cgroup.events").write_text("populated 1\\n")
            worker = self._owned(root)
            attempts = []

            def uncertain_write():
                attempts.append("issued")
                (root / "cgroup.kill").write_text("1")
                raise OSError("write completion uncertain")

            with patch.object(worker, "_request_kill", side_effect=uncertain_write):
                with self.assertRaises(OSError):
                    worker.stop_and_verify(timeout=1)
                (root / "cgroup.events").write_text("populated 0\\n")
                receipt = worker.stop_and_verify(timeout=1)
            self.assertEqual(attempts, ["issued"])
            self.assertTrue(receipt["empty_group_verified"])
            self.assertEqual((root / "cgroup.kill").read_text(), "1")

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


def test_fresh_empty_receipt_refuses_repopulation_and_missing_authority():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "cgroup.events").write_text("populated 0\\n")
        worker = LinuxCgroupCustodyContractTests()._owned(root)
        with unittest.TestCase().assertRaisesRegex(CgroupCustodyError, "No consumed"):
            worker.verify_still_empty()
        worker._consumed = True
        assert worker.verify_still_empty()["empty_group_verified"] is True
        (root / "cgroup.events").write_text("populated 1\\n")
        with unittest.TestCase().assertRaisesRegex(CgroupCustodyError, "no longer empty"):
            worker.verify_still_empty()


def test_fresh_empty_receipt_rejects_ambiguous_kernel_events():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "cgroup.events").write_text("populated 0\\npopulated 1\\n")
        worker = LinuxCgroupCustodyContractTests()._owned(root)
        worker._consumed = True
        with unittest.TestCase().assertRaisesRegex(CgroupCustodyError, "Malformed or duplicate"):
            worker.verify_still_empty()
