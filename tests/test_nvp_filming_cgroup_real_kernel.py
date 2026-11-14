"""DA-03 genuine Linux cgroup-v2 acceptance (opt-in; never simulated).

Run with NVP_TEST_DELEGATED_CGROUP_ROOT set to a host-delegated writable
cgroup-v2 directory. A skipped test is NOT acceptance. No FFmpeg involved.
"""
import os
import pathlib
import subprocess
import sys
import time
import unittest

from backend.nvp_filming_linux_session import launch_linux_filming_session


@unittest.skipUnless(
    sys.platform == "linux" and os.environ.get("NVP_TEST_DELEGATED_CGROUP_ROOT"),
    "requires real host-delegated cgroup-v2 root; skip is NOT acceptance",
)
class RealDelegatedCgroupAcceptance(unittest.TestCase):
    def test_descendant_kill_and_empty_group(self):
        root = pathlib.Path(os.environ["NVP_TEST_DELEGATED_CGROUP_ROOT"])
        # Worker creates a descendant that remains alive until the kernel
        # terminates the entire cgroup. No shell or PID-based kill fallback.
        code = (
            "import subprocess,sys,time;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
            "time.sleep(120)"
        )
        # sys.executable is frequently a symlink (venv, alternatives). The
        # production launcher deliberately refuses symlinked executables.
        # Resolve to the actual interpreter for this real-kernel acceptance.
        interpreter = str(pathlib.Path(sys.executable).resolve(strict=True))
        self.assertTrue(os.access(interpreter, os.X_OK))
        session = launch_linux_filming_session(
            root, interpreter, [interpreter, "-c", code]
        )
        group, worker = session.group, session.child
        try:
            deadline = time.monotonic() + 10
            observed_descendant = False
            while time.monotonic() < deadline:
                members = (group / "cgroup.procs").read_text().split()
                if str(worker.pid) in members and any(pid != str(worker.pid) for pid in members):
                    observed_descendant = True
                    break
                if worker.poll() is not None:
                    self.fail("worker exited before descendant observation")
                time.sleep(0.05)
            self.assertTrue(observed_descendant, "worker PID and separate live descendant not jointly observed in delegated cgroup")
            # Exercise the actual host session's kernel custody and worker
            # reconciliation, not an independent test-only kill shortcut.
            receipt = session.stop_and_verify(timeout=10)
            self.assertIs(receipt["process_tree_custody_verified"], True)
            self.assertIs(receipt["empty_group_verified"], True)
            self.assertIs(receipt["worker_exit_verified"], True)
            self.assertEqual(receipt["scope"], "linux-cgroup-v2")
            self.assertIsNotNone(receipt["worker_returncode"])
            self.assertEqual(worker.returncode, receipt["worker_returncode"])
        finally:
            # Never claim cleanup from a process handle alone. A failed
            # assertion may leave a worker; terminate via cgroup.kill.
            try:
                (group / "cgroup.kill").write_text("1")
            except OSError:
                pass
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                group.rmdir()
            except OSError:
                pass
