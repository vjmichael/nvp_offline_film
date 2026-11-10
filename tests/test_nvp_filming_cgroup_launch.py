"""Contract tests for DA-03 attach-before-exec boundary (no real delegation)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_filming_cgroup_launch import attach_then_exec


class CgroupLaunchContractTests(unittest.TestCase):
    def test_refuses_non_absolute_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                attach_then_exec(Path(tmp), "python", ["python"])

    @unittest.skipUnless(os.name == "posix", "POSIX open flags required")
    def test_attachment_precedes_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp)
            (group / "cgroup.procs").write_bytes(b"")
            with patch("backend.nvp_filming_cgroup_launch._verify_current_process_membership") as verify, patch("backend.nvp_filming_cgroup_launch.os.execv") as execv:
                attach_then_exec(group, "/bin/true", ["/bin/true"])
                verify.assert_called_once_with(group)
                self.assertEqual((group / "cgroup.procs").read_bytes(), b"0")
                execv.assert_called_once_with("/bin/true", ["/bin/true"])

    @unittest.skipUnless(os.name == "posix", "POSIX open flags required")
    def test_unobserved_membership_prevents_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp)
            (group / "cgroup.procs").write_bytes(b"")
            with patch("backend.nvp_filming_cgroup_launch.os.execv") as execv:
                with self.assertRaisesRegex(RuntimeError, "membership"):
                    attach_then_exec(group, "/bin/true", ["/bin/true"])
                execv.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX open flags required")
    def test_missing_attachment_prevents_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("backend.nvp_filming_cgroup_launch.os.execv") as execv:
                with self.assertRaises(OSError):
                    attach_then_exec(Path(tmp), "/bin/true", ["/bin/true"])
                execv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
