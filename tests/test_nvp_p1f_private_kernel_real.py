"""P1-F genuine Linux kernel adversarial acceptance. NEVER simulate success.

Run only inside systemd's actual delegated cgroup-v2 scope, with
NVP_REQUIRE_REAL_P1F_KERNEL=1. This suite fails hard if kernel delegation,
bubblewrap mount/user/PID/net isolation, cgroup.kill or the out-of-tree
guardian is unavailable. No copied/synthetic cgroup fixture counts.
Existing original tests are run unchanged alongside this suite.
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
from backend.nvp_worker_private_sandbox import (
    prove_private_kernel_boundary,private_os_preflight)
from backend.nvp_worker_linux_cgroup import provision_worker_cgroup

REQUIRED=os.environ.get("NVP_REQUIRE_REAL_P1F_KERNEL")=="1"


def running(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()[0] not in ("Z","X","x")
    except (OSError,IndexError):
        return False


def observe_empty(pids,timeout=16):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if all(not running(pid) for pid in pids):
            return True
        time.sleep(.1)
    return all(not running(pid) for pid in pids)


@unittest.skipUnless(sys.platform=="linux" and REQUIRED,
                     "Real systemd delegated P1-F kernel suite must be explicitly required")
class GenuineP1FKernelContainment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A skipped test is NOT a pass; the strict runner always sets REQUIRED.
        private_os_preflight()
        leaf=provision_worker_cgroup(1024)
        leaf.rmdir()
        if not Path("/usr/bin/python3").is_file():
            raise AssertionError("Actual OS Python ELF worker missing")

    def test_genuine_net_mount_user_namespace_and_delegated_cgroup(self):
        with tempfile.TemporaryDirectory(prefix="p1f-private-kernel-") as temp:
            receipt=prove_private_kernel_boundary(temp)
            self.assertEqual(receipt["contract"],
                             "nvp.p1f.real_kernel_boundary_probe.v1")
            self.assertTrue(receipt["checked"])
            self.assertTrue(receipt["approved_source_read"])
            self.assertTrue(receipt["outside_job_file_hidden"])
            self.assertTrue(receipt["host_loopback_denied"])
            self.assertTrue(receipt["guardian_outside_worker_leaf"])
            self.assertNotEqual(receipt["host_network_namespace"],
                                receipt["worker_network_namespace"])
            self.assertNotEqual(receipt["host_mount_namespace"],
                                receipt["worker_mount_namespace"])
            self.assertFalse(receipt["private_project_staged"])

    def _running_tree(self,root):
        job=root/"reviewed_job"
        job.mkdir()
        sentinel=job/"ready.json"
        # Inside the sandbox, launch an independently detached descendant.
        # stdout marker is written in the exact one-job directory, never
        # outside the host's private namespace. Host kernel cgroup.procs is
        # independently inspected; worker PID namespace PIDs are not trusted.
        code=(
            "import os,subprocess,sys,time,json;"
            "from pathlib import Path;"
            "child=subprocess.Popen(['/usr/bin/python3','-S','-c',"
            "'import os,time;os.setsid();time.sleep(100)'],"
            "start_new_session=False);"
            f"Path({str(sentinel)!r}).write_text(json.dumps({{'ns_pid':os.getpid(),'child_ns_pid':child.pid}}));"
            "time.sleep(100)"
        )
        stdout=(job/"out").open("wb")
        stderr=(job/"err").open("wb")
        try:
            proc=launch_contained(
                ["/usr/bin/python3","-S","-c",code],
                cwd=str(job),stdout=stdout,stderr=stderr,memory_mb=1024,
                linux_cgroup_tree_required=True,
                private_isolation_required=True)
        except BaseException:
            stdout.close();stderr.close();raise
        deadline=time.monotonic()+14
        while time.monotonic()<deadline and not sentinel.exists():
            if proc.poll() is not None:
                raise AssertionError("Private worker exited before descendant ready: "+
                    (job/"err").read_text("utf8",errors="replace")[-4000:])
            time.sleep(.05)
        if not sentinel.is_file():
            proc.terminate_tree();proc.close()
            raise AssertionError("No real private worker descendant spawned")
        leaf=proc.cgroup
        processes={int(x) for x in (leaf/"cgroup.procs").read_text().split()}
        if len(processes)<2:
            proc.terminate_tree();proc.close()
            raise AssertionError("No independent detached descendant in kernel worker cgroup")
        return proc,processes,stdout,stderr

    def test_genuine_cancellation_kills_detached_descendant(self):
        with tempfile.TemporaryDirectory(prefix="p1f-private-cancel-") as temp:
            proc,pids,out,err=self._running_tree(Path(temp))
            leaf=proc.cgroup
            try:
                proc.terminate_tree()
                proc.close()
                self.assertTrue(observe_empty(pids),
                    "Kernel cancellation left a detached Blender descendant")
                self.assertFalse(leaf.exists(),
                    "Guardian failed to remove independently emptied kernel leaf")
            finally:
                out.close();err.close()
                try: proc.close()
                except (RuntimeError,OSError): pass

    def test_genuine_guardian_sigkill_refuses_to_publish_success(self):
        with tempfile.TemporaryDirectory(prefix="p1f-private-guardian-") as temp:
            proc,pids,out,err=self._running_tree(Path(temp))
            try:
                proc._guardian.kill()
                proc._guardian.wait(timeout=5)
                with self.assertRaisesRegex(RuntimeError,"guardian died"):
                    proc.poll()
                self.assertTrue(observe_empty(pids),
                    "Independent guardian loss did not force kernel cgroup.kill")
                # This is intentionally NOT a graceful success receipt.
                with self.assertRaises(RuntimeError):
                    proc.close()
            finally:
                out.close();err.close()
                try: proc.terminate_tree()
                except (OSError,RuntimeError): pass
                try: proc.close()
                except (OSError,RuntimeError): pass

    def test_real_hard_host_exit_kills_all_namespace_descendants(self):
        with tempfile.TemporaryDirectory(prefix="p1f-private-parent-death-") as temp:
            root=Path(temp)
            marker=root/"observed_kernel_tree.json"
            job=root/"reviewed_job"
            job.mkdir()
            ready=job/"ns_ready"
            worker_code=(
                "import os,subprocess,time;"
                "from pathlib import Path;"
                "p=subprocess.Popen(['/usr/bin/python3','-S','-c',"
                "'import os,time;os.setsid();time.sleep(120)']);"
                f"Path({str(ready)!r}).write_text(str(p.pid));"
                "time.sleep(120)"
            )
            host_code=(
                "import os,time,json;"
                "from pathlib import Path;"
                "from backend.nvp_worker_containment import launch_contained;"
                f"job=Path({str(job)!r});"
                "out=(job/'out').open('wb');err=(job/'err').open('wb');"
                f"p=launch_contained(['/usr/bin/python3','-S','-c',{worker_code!r}],"
                "cwd=str(job),stdout=out,stderr=err,memory_mb=1024,"
                "linux_cgroup_tree_required=True,private_isolation_required=True);"
                f"ready=Path({str(ready)!r});"
                "[(time.sleep(.05)) for _ in range(200) if not ready.is_file()];"
                "assert ready.is_file() and p.poll() is None;"
                "leaf=p.cgroup;"
                "pids=[int(v) for v in (leaf/'cgroup.procs').read_text().split()];"
                "assert len(pids)>=2;"
                f"Path({str(marker)!r}).write_text(json.dumps({{'leaf':str(leaf),'pids':pids,'guardian':p._guardian.pid}}));"
                "os._exit(29)"
            )
            env=dict(os.environ)
            env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
            host=subprocess.Popen([sys.executable,"-S","-c",host_code],
                cwd=str(root),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            details={}
            try:
                _,stderr=host.communicate(timeout=35)
                self.assertEqual(host.returncode,29,
                    "Actual host did not crash after kernel worker admission: "+
                    stderr.decode("utf8",errors="replace")[-2500:])
                details=json.loads(marker.read_text("utf8"))
                pids=details["pids"]
                self.assertTrue(observe_empty(pids,timeout=20),
                    "Hard host exit left private namespace descendants alive")
                leaf=Path(details["leaf"])
                deadline=time.monotonic()+12
                while leaf.exists() and time.monotonic()<deadline:
                    time.sleep(.1)
                self.assertFalse(leaf.exists(),
                    "Out-of-tree kernel guardian did not remove worker leaf")
            finally:
                if host.poll() is None:
                    host.kill();host.wait()
                if details:
                    # Cleanup is separate from the acceptance observations;
                    # never count this fallback as successful guardian custody.
                    leaf=Path(details["leaf"])
                    if leaf.is_file() or leaf.is_dir():
                        try:(leaf/"cgroup.kill").write_text("1")
                        except OSError:pass
                    for pid in details["pids"]:
                        if running(pid):
                            try:os.kill(pid,signal.SIGKILL)
                            except ProcessLookupError:pass


if __name__=="__main__":
    unittest.main()
