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

from backend.nvp_filming_cgroup_launch import create_private_group_and_launch


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
        group, worker = create_private_group_and_launch(
            root, interpreter, [interpreter, "-c", code]
        )
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
            (group / "cgroup.kill").write_text("1")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                fields = dict(
                    line.split() for line in (group / "cgroup.events").read_text().splitlines()
                )
                if fields.get("populated") == "0":
                    break
                time.sleep(0.05)
            else:
                self.fail("kernel did not attest empty cgroup after cgroup.kill")
            worker.wait(timeout=5)
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
