"""SEC-06 independent native Linux ancestor-migration containment gate.

This is an actual kernel experiment, not a mocked cgroup or a setsid-only
test. The test intentionally attempts an adversarial write to the original
delegated ancestor and original host subgroup cgroup.procs. Any migration blocks release.

Run ONLY in an explicitly delegated cgroup-v2 runner. A missing scope,
skipped test or unavailable kernel evidence is NOT acceptance. The attempted
grandchild has a bounded lifetime and an independent direct-PID cleanup path,
even if it escapes the worker leaf.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_linux_cgroup import (
    CGROUP_MOUNT, current_delegated_parent, current_cgroup_relative,
)


@unittest.skipUnless(sys.platform == "linux", "Real Linux cgroup-v2 required")
class IndependentAncestorMigrationGate(unittest.TestCase):
    def test_descendant_cannot_migrate_into_delegated_ancestor(self):
        if os.environ.get("NVP_REQUIRE_DELEGATED_CGROUP") != "1":
            self.fail("SEC-06 requires explicit genuine delegated cgroup acceptance")
        try:
            ancestor = current_delegated_parent()
        except (RuntimeError, OSError) as error:
            self.fail("SEC-06 native delegated cgroup unavailable: " + str(error))
        self.assertTrue((ancestor / "cgroup.procs").is_file())
        self.assertTrue((ancestor / "cgroup.controllers").is_file())
        # An EBUSY ancestor does not exclude movement into a writable host
        # subgroup, which also lies outside the worker's killed leaf.
        host_group=(CGROUP_MOUNT/current_cgroup_relative().lstrip("/")).resolve()
        self.assertTrue(host_group.is_relative_to(ancestor.resolve()))
        self.assertNotEqual(host_group, ancestor.resolve(),
                            "SEC-06 requires delegated host subgroup")
        self.assertTrue((host_group/"cgroup.procs").is_file())

        with tempfile.TemporaryDirectory(prefix="nvp-sec06-ancestor-") as td:
            root = Path(td)
            report = root / "ancestor-attempt.json"
            grandchild = r"""
import json, os, sys, time
from pathlib import Path
targets=(("ancestor",Path(sys.argv[1])),("host_subgroup",Path(sys.argv[2])))
report=Path(sys.argv[3])
attempts=[]
for label,target in targets:
    before=Path("/proc/self/cgroup").read_text("utf8")
    error=None
    try:
        target.write_text(str(os.getpid()),encoding="ascii")
    except OSError as exc:
        error={"errno":exc.errno,"type":type(exc).__name__}
    after=Path("/proc/self/cgroup").read_text("utf8")
    attempts.append({"target":label,"before":before,"after":after,
                     "migration_write_succeeded":error is None,"error":error})
report.write_text(json.dumps({"pid":os.getpid(),"attempts":attempts},
                             sort_keys=True),encoding="utf8")
time.sleep(20)
"""
            worker = (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c',"
                + repr(grandchild) +
                ",sys.argv[1],sys.argv[2],sys.argv[3]],start_new_session=True);"
                "time.sleep(30)"
            )
            pid = None
            proc = None
            with (root / "stdout.log").open("wb") as out, (
                root / "stderr.log").open("wb") as err:
                try:
                    proc = launch_contained(
                        [sys.executable, "-c", worker,
                         str(ancestor / "cgroup.procs"), str(host_group / "cgroup.procs"), str(report)],
                        cwd=str(root), stdout=out, stderr=err,
                        memory_mb=512, linux_cgroup_tree_required=True)
                    leaf = Path(proc.cgroup).resolve(strict=True)
                    self.assertEqual(leaf.parent, ancestor.resolve(strict=True))
                    expected = "0::/" + leaf.relative_to(CGROUP_MOUNT).as_posix()
                    deadline = time.monotonic() + 12
                    while not report.exists() and time.monotonic() < deadline:
                        if proc.poll() is not None:
                            self.fail("SEC-06 worker exited before ancestor attempt")
                        time.sleep(0.05)
                    self.assertTrue(report.is_file(),
                                    "No real descendant ancestor-migration receipt")
                    observed = json.loads(report.read_text("utf8"))
                    pid = observed.get("pid")
                    self.assertIs(type(pid), int)
                    self.assertGreater(pid, 1)
                    attempts=observed["attempts"]
                    self.assertEqual([a["target"] for a in attempts],
                                     ["ancestor","host_subgroup"])
                    print("SEC-06 Linux native ancestor and host migration:",
                          json.dumps(observed,sort_keys=True),flush=True)
                    for attempt in attempts:
                        self.assertIn(expected,attempt["before"].splitlines(),
                                      "Worker escaped leaf before "+attempt["target"])
                        self.assertFalse(attempt["migration_write_succeeded"],
                                         "SEC-06 BLOCKER: worker escaped into "+attempt["target"])
                        self.assertEqual(attempt["after"],attempt["before"],
                                         "SEC-06 BLOCKER: migration at "+attempt["target"])
                        self.assertIsNotNone(attempt["error"],
                                             "Missing kernel refusal at "+attempt["target"])
                finally:
                    # If migration succeeded, leaf cgroup.kill cannot be
                    # assumed to reach the escaped child. Signal the exact
                    # independently observed PID before guardian cleanup.
                    if type(pid) is int and pid > 1:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if proc is not None:
                        try:
                            if proc.poll() is None:
                                proc.terminate_tree()
                        finally:
                            proc.close()


if __name__ == "__main__":
    unittest.main()
