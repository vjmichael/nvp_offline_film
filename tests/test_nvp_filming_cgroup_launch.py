"""Contract tests for DA-03 attach-before-exec boundary (no real delegation)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_filming_cgroup_launch import attach_then_exec


class CgroupLaunchContractTests(unittest.TestCase):
    def test_host_refuses_unavailable_worker_before_spawning(self):
        from backend.nvp_filming_cgroup_launch import launch_attached_worker
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing-worker")
            with patch("subprocess.Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    launch_attached_worker(Path(tmp), missing, [missing])
                spawn.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX symlink semantics required")
    def test_host_refuses_symlinked_worker_and_group_before_spawning(self):
        from backend.nvp_filming_cgroup_launch import launch_attached_worker
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "worker"
            worker.write_text("#!/bin/sh\\nexit 0\\n")
            worker.chmod(0o700)
            linked_worker = root / "worker-link"
            linked_worker.symlink_to(worker)
            group = root / "group"
            group.mkdir()
            linked_group = root / "group-link"
            linked_group.symlink_to(group, target_is_directory=True)
            with patch("subprocess.Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    launch_attached_worker(group, str(linked_worker), [str(linked_worker)])
                with self.assertRaisesRegex(ValueError, "symlink"):
                    launch_attached_worker(linked_group, str(worker), [str(worker)])
                spawn.assert_not_called()

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
                verify.assert_called_once()
                self.assertIsInstance(verify.call_args.args[0], int)
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
    def test_membership_uses_pinned_directory_after_path_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp) / "group"
            group.mkdir()
            (group / "cgroup.procs").write_bytes(b"")
            moved = Path(tmp) / "moved"
            def replace_group_and_verify(directory):
                group.rename(moved)
                group.mkdir()
                (group / "cgroup.procs").write_text(str(os.getpid()))
                # Reopened path would observe the attacker-controlled replacement;
                # pinned descriptor must still read the original empty mock file.
                from backend.nvp_filming_cgroup_launch import _verify_current_process_membership
                _verify_current_process_membership(directory)
            with patch("backend.nvp_filming_cgroup_launch._verify_current_process_membership", side_effect=replace_group_and_verify), patch("backend.nvp_filming_cgroup_launch.os.execv") as execv:
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
