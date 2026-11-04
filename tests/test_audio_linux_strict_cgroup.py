"""AUDIO Linux strict containment: explicit fail-closed and guardian tests.

The real delegated cgroup test runs only when the host has genuine systemd
delegation; a skip is NOT production acceptance.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_linux_cgroup import current_delegated_parent


@unittest.skipUnless(sys.platform=="linux", "Linux strict-cgroup gate")
class StrictLinuxAudioWorker(unittest.TestCase):
    def test_no_delegation_fails_closed_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.devnull,"wb") as sink:
                with patch("backend.nvp_worker_linux_cgroup.current_delegated_parent",
                           side_effect=RuntimeError("No delegation")):
                    with self.assertRaisesRegex(RuntimeError,"No delegation"):
                        launch_contained([sys.executable,"-c","print('should not run')"],
                            cwd=tmp,stdout=sink,stderr=sink,memory_mb=512,
                            linux_cgroup_tree_required=True)

    def test_guardian_kills_detached_descendant_after_host_crash(self):
        try:
            current_delegated_parent()
        except (OSError,RuntimeError) as exc:
            if os.environ.get("NVP_REQUIRE_DELEGATED_CGROUP")=="1":
                self.fail("Required strict guardian acceptance environment unavailable: "+str(exc))
            self.skipTest("No actual delegated cgroup available: "+str(exc))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            # A separate host process launches an actual kernel-contained
            # worker whose grandchild escapes the process group via setsid.
            # os._exit simulates a host death without running finally/close.
            host_code="""
import os,sys,time,subprocess
from pathlib import Path
from backend.nvp_worker_containment import launch_contained
root=Path(sys.argv[1])
child_code=(
    "import os,time;from pathlib import Path;"
    "os.setsid();Path("+repr(str(root/"grandchild.ready"))+").write_text(str(os.getpid()));"
    "time.sleep(120)"
)
worker_code="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(child_code)+"]);time.sleep(120)"
with (root/'out.log').open('wb') as out, (root/'err.log').open('wb') as err:
    proc=launch_contained([sys.executable,'-c',worker_code],cwd=str(root),
        stdout=out,stderr=err,memory_mb=512,linux_cgroup_tree_required=True)
    (root/'cgroup').write_text(str(proc.cgroup))
    deadline=time.monotonic()+12
    while not (root/'grandchild.ready').exists() and time.monotonic()<deadline:
        time.sleep(.05)
    if not (root/'grandchild.ready').exists():
        os._exit(80)
    os._exit(79)
"""
            env=os.environ.copy()
            repo=Path(__file__).resolve().parents[1]
            env["PYTHONPATH"]=str(repo)
            host=subprocess.run([sys.executable,"-c",host_code,str(root)],
                cwd=repo,env=env,timeout=30,capture_output=True)
            self.assertEqual(host.returncode,79,host.stderr.decode(errors="replace"))
            group=Path((root/"cgroup").read_text())
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                try:
                    status=(group/"cgroup.events").read_text()
                    if "populated 0" in status:
                        break
                except FileNotFoundError:
                    # Guardian may already have removed an empty cgroup.
                    break
                time.sleep(.1)
            else:
                self.fail("Guardian left detached descendant in cgroup")
            self.assertTrue((root/"grandchild.ready").exists())


if __name__=="__main__":
    unittest.main()
