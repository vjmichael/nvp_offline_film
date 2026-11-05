"""E2E-01D OS-native worker termination acceptance.

Real executable / real descendant processes, not mocked launch_contained.
Windows: a Job Object must kill a grandchild both on explicit termination and
after its direct worker exits and the host closes the job handle.
Linux: ordinary process-group containment must kill an attached child tree.
Strict Linux cgroup-v2 mode must fail closed without delegation; do not imply
that PDEATHSIG alone kills detached grandchildren.

No GUI, media mock or director authorization is involved in this OS gate.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_worker_containment import launch_contained

SLEEP_SECONDS=90
WAIT_SECONDS=12
WORKER_CODE=r"""
import os, pathlib, subprocess, sys, time
root=pathlib.Path(sys.argv[1])
mode=sys.argv[2]
child=subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"],
    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,close_fds=True,
    start_new_session=(mode=="detached"))
(root/"descendant.pid").write_text(str(child.pid),encoding="ascii")
(root/"worker.ready").write_text(str(os.getpid()),encoding="ascii")
if mode=="parent_exits":
    sys.exit(0)
time.sleep(90)
"""


def pid_running(pid):
    if os.name=="nt":
        kernel=ctypes.windll.kernel32
        handle=kernel.OpenProcess(0x00100000,False,pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle,0)==0x00000102
        finally:
            kernel.CloseHandle(handle)
    path=Path("/proc")/str(pid)/"stat"
    if path.exists():
        try:
            # A zombie is no longer an executing worker.
            return path.read_text().split(") ",1)[1][0] not in ("Z","X")
        except (OSError,IndexError):
            return False
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False


def kill_unowned(pid):
    if not pid or not pid_running(pid):
        return
    if os.name=="nt":
        kernel=ctypes.windll.kernel32
        handle=kernel.OpenProcess(0x0001|0x00100000,False,pid)
        if handle:
            try:
                kernel.TerminateProcess(handle,15)
                kernel.WaitForSingleObject(handle,5000)
            finally:
                kernel.CloseHandle(handle)
    else:
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass


def wait_until(predicate,limit=WAIT_SECONDS):
    until=time.monotonic()+limit
    while time.monotonic()<until:
        if predicate():
            return True
        time.sleep(.05)
    return predicate()


class NativeWorkerTermination(unittest.TestCase):
    def _start(self,root,mode):
        from backend.nvp_worker_containment import launch_contained
        stdout=(root/"stdout.log").open("wb")
        stderr=(root/"stderr.log").open("wb")
        try:
            proc=launch_contained(
                [str(Path(sys.executable).resolve()),"-c",WORKER_CODE,
                 str(root),mode],cwd=str(root),stdout=stdout,stderr=stderr,
                 memory_mb=0,linux_cgroup_tree_required=False)
        except BaseException:
            stdout.close();stderr.close()
            raise
        return proc,stdout,stderr

    def _probe(self,mode):
        with tempfile.TemporaryDirectory(prefix="nvp-real-terminate-") as directory:
            root=Path(directory)
            proc=None
            descendant=None
            stdout=stderr=None
            try:
                proc,stdout,stderr=self._start(root,mode)
                self.assertTrue(wait_until(lambda:(root/"worker.ready").is_file()),
                                "Real worker never entered execution")
                descendant=int((root/"descendant.pid").read_text("ascii"))
                self.assertTrue(pid_running(descendant),"Descendant did not start")
                if mode=="parent_exits":
                    self.assertEqual(proc.wait(timeout=WAIT_SECONDS),0)
                    if os.name=="nt":
                        # The grandchild survives its parent until the job
                        # closes. This is the kill-on-close security property.
                        self.assertTrue(pid_running(descendant))
                    proc.close()
                else:
                    self.assertIsNone(proc.poll())
                    proc.terminate_tree()
                    proc.close()
                self.assertTrue(wait_until(lambda:not pid_running(descendant)),
                                "Native OS containment left a descendant alive")
            finally:
                if proc is not None:
                    try:
                        if proc.poll() is None:
                            proc.terminate_tree()
                        proc.close()
                    except BaseException:
                        pass
                kill_unowned(descendant)
                if stdout:stdout.close()
                if stderr:stderr.close()

    def test_os_termination_kills_direct_worker_and_descendant(self):
        self._probe("running")

    @unittest.skipUnless(os.name=="nt","Job Object kill-on-close is Windows-specific")
    def test_windows_job_close_kills_grandchild_after_worker_exits(self):
        self._probe("parent_exits")

    @unittest.skipUnless(sys.platform=="linux","Linux cgroup v2 only")
    def test_real_cgroup_kill_includes_detached_session_child(self):
        from backend.nvp_worker_linux_cgroup import current_delegated_parent
        try:
            current_delegated_parent()
        except RuntimeError as exc:
            self.skipTest("Real delegated cgroup v2 required: "+str(exc))
        with tempfile.TemporaryDirectory(prefix="nvp-cgroup-real-") as directory:
            root=Path(directory)
            proc=None
            descendant=None
            try:
                with (root/"stdout.log").open("wb") as out,(
                     root/"stderr.log").open("wb") as err:
                    proc=launch_contained(
                        [str(Path(sys.executable).resolve()),"-c",WORKER_CODE,
                         str(root),"detached"],cwd=str(root),
                        stdout=out,stderr=err,memory_mb=512,
                        linux_cgroup_tree_required=True)
                    self.assertTrue(wait_until(
                        lambda:(root/"worker.ready").is_file()),
                        "Delegated native worker failed to execute")
                    descendant=int((root/"descendant.pid").read_text("ascii"))
                    self.assertTrue(pid_running(descendant))
                    # This detached descendant is not in the worker PGID.
                    self.assertNotEqual(os.getpgid(descendant),proc.pid)
                    proc.terminate_tree()
                    proc.close()
                    self.assertTrue(wait_until(lambda:not pid_running(descendant)),
                                    "Kernel cgroup.kill left detached worker alive")
            finally:
                if proc is not None:
                    try:
                        if proc.poll() is None:
                            proc.terminate_tree()
                        proc.close()
                    except BaseException:
                        pass
                kill_unowned(descendant)

    @unittest.skipUnless(sys.platform=="linux","Linux cgroup v2 only")
    def test_strict_cgroup_requires_real_delegated_kernel_scope(self):
        from backend.nvp_worker_linux_cgroup import current_delegated_parent
        try:
            delegated=current_delegated_parent()
        except RuntimeError:
            # No fake fallback to process groups for strict requirements.
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                with (root/"out").open("wb") as out,(root/"err").open("wb") as err:
                    with self.assertRaises(RuntimeError):
                        launch_contained([str(Path(sys.executable).resolve()),
                            "-c","pass"],cwd=str(root),stdout=out,stderr=err,
                            memory_mb=512,linux_cgroup_tree_required=True)
        else:
            self.assertTrue(delegated.is_dir())
            self.assertTrue((delegated/"cgroup.controllers").is_file())


if __name__=="__main__":
    unittest.main()
