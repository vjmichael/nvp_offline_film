"""STACK-02C2: fail-closed cgroups v2 and genuine detached-grandchild crash.

Unit tests prove the strict API does not fall back. The kernel test is
skipped when the CI/desktop session has NO delegated cgroup controller, and
the acceptance report must then say 'blocked', never full-tree verified.
Set NVP_REQUIRE_REAL_CGROUP=1 on a delegated Linux CI runner to make lack of
kernel delegation a hard acceptance failure.
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
from unittest.mock import patch

from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_linux_cgroup import (
    current_delegated_parent,provision_worker_cgroup,
)
from backend.nvp_worker_cgroup_guardian import validate_owned_leaf

REQUIRED=os.getenv("NVP_REQUIRE_REAL_CGROUP","")=="1"


def is_running(pid):
    p=Path(f"/proc/{pid}/stat")
    if not p.is_file():return False
    try:
        return p.read_text("utf8").rsplit(")",1)[1].split()[0] not in ("Z","X","x")
    except (FileNotFoundError,ProcessLookupError):
        return False


@unittest.skipUnless(sys.platform=="linux","Kernel cgroup test is Linux-only")
class CgroupTreeTests(unittest.TestCase):
    def test_strict_mode_cannot_fallback_to_pdeathsig_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with (root/"out").open("wb") as stdout,(root/"err").open("wb") as stderr:
                with patch("backend.nvp_worker_linux_cgroup.provision_worker_cgroup",
                           side_effect=RuntimeError("No delegated cgroup v2")):
                    with patch("backend.nvp_worker_containment.subprocess.Popen") as forbidden:
                        with self.assertRaisesRegex(RuntimeError,"No delegated cgroup"):
                            launch_contained([sys.executable,"-S","-c","print('forbidden')"],
                                cwd=temp,stdout=stdout,stderr=stderr,memory_mb=1024,
                                linux_cgroup_tree_required=True)
                        forbidden.assert_not_called()

    def test_guardian_refuses_foreign_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/("nvp-worker-"+"a"*32)
            target.mkdir()
            (target/"cgroup.kill").write_text("1")
            (target/"cgroup.events").write_text("populated 0\n")
            with self.assertRaises(RuntimeError):
                validate_owned_leaf(target)

    def _require_delegation(self):
        try:
            test_leaf=provision_worker_cgroup(1024)
            test_leaf.rmdir()
        except (OSError,RuntimeError) as exc:
            reason="No writable delegated cgroup v2 memory/pids subtree: "+str(exc)
            if REQUIRED:
                self.fail(reason)
            self.skipTest(reason)

    def test_real_hard_host_exit_kills_detached_process_grandchild(self):
        self._require_delegation()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ready=root/"descendants.json"
            child_code=(
                "import os,sys,time,subprocess,json;from pathlib import Path;"
                "grandchild=subprocess.Popen([sys.executable,'-S','-c',"
                "'import os,time; os.setsid(); time.sleep(90)'],"
                "start_new_session=True);"
                f"Path({str(ready)!r}).write_text(json.dumps({{'child':os.getpid(),'detached_grandchild':grandchild.pid}}));"
                "time.sleep(90)"
            )
            host_code=(
                "import os,sys,time;from pathlib import Path;"
                "from backend.nvp_worker_containment import launch_contained;"
                f"root=Path({str(root)!r});"
                'o=(root/"stdout").open("wb");e=(root/"stderr").open("wb");'
                f'worker=launch_contained([sys.executable,"-S","-c",{child_code!r}],'
                'cwd=str(root),stdout=o,stderr=e,memory_mb=1024,linux_cgroup_tree_required=True);'
                f'marker=Path({str(ready)!r});'
                '[(time.sleep(.05)) for i in range(200) if not marker.exists()];'
                'assert marker.is_file() and worker.poll() is None;'
                'os._exit(27)'
            )
            env=dict(os.environ)
            env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
            host=subprocess.Popen([sys.executable,"-S","-c",host_code],
                cwd=temp,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            pids={}
            try:
                _,stderr=host.communicate(timeout=28)
                self.assertEqual(host.returncode,27,
                    "Host failed before deliberate crash: "+stderr.decode(errors="replace"))
                pids=json.loads(ready.read_text("utf8"))
                self.assertEqual(set(pids),{"child","detached_grandchild"})
                for _ in range(180):
                    if all(not is_running(pid) for pid in pids.values()):break
                    time.sleep(.1)
                self.assertTrue(all(not is_running(pid) for pid in pids.values()),
                    "Independent cgroup guardian did not kill all detached descendants")
            finally:
                if host.poll() is None:host.kill();host.wait()
                for pid in pids.values():
                    if is_running(pid):
                        try:os.kill(pid,signal.SIGKILL)
                        except ProcessLookupError:pass

    def test_real_full_tree_cleanup_on_normal_worker_exit(self):
        self._require_delegation()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            marker=root/"child.json"
            code=(
                "import subprocess,json,sys,time,os;from pathlib import Path;"
                "p=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)'],"
                "start_new_session=True);"
                f"Path({str(marker)!r}).write_text(json.dumps({{'grandchild':p.pid}}));"
                "sys.exit(0)"
            )
            with (root/"out").open("wb") as out,(root/"err").open("wb") as err:
                proc=launch_contained([sys.executable,"-S","-c",code],cwd=temp,
                    stdout=out,stderr=err,memory_mb=1024,linux_cgroup_tree_required=True)
                try:
                    self.assertEqual(proc.wait(timeout=10),0)
                    self.assertTrue(marker.exists())
                    grandchild=json.loads(marker.read_text("utf8"))["grandchild"]
                finally:
                    proc.close()
                for _ in range(80):
                    if not is_running(grandchild):break
                    time.sleep(.1)
                self.assertFalse(is_running(grandchild),
                    "Detached grandchild remained after successful worker exit")


if __name__=="__main__":
    unittest.main()
