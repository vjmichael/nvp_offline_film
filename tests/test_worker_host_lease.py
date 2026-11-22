"""STACK-02C: real kernel file-lock leases across NVP processes.

No synthetic PID/heartbeat, no mocked file locks. The parent calls a separate
Python process and proves a live host cannot have its journal recovered or run
by another process. The kernel releases ownership after hard os._exit.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_worker_host_lease import WorkerHostLease
from backend.nvp_blender_worker import BlenderWorkerSupervisor, BlenderOperation, sha_file


class WorkerHostLeaseContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.workspace=Path(self.temp.name)/"workers"
        self.workspace.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_real_exclusive_lock_and_release_after_exception(self):
        with WorkerHostLease(self.workspace):
            with self.assertRaisesRegex(RuntimeError,"Another NVP host"):
                with WorkerHostLease(self.workspace): pass
        with self.assertRaisesRegex(ValueError,"expected error"):
            with WorkerHostLease(self.workspace):
                raise ValueError("expected error")
        with WorkerHostLease(self.workspace):
            self.assertTrue((self.workspace/"worker_host.lock").is_file())

    def test_real_second_process_refused_while_first_host_alive(self):
        probe=(
            "from backend.nvp_worker_host_lease import WorkerHostLease;"
            "from pathlib import Path;"
            f"with_path=Path({str(self.workspace)!r});"
            "lease=WorkerHostLease(with_path);lease.__enter__();lease.__exit__(None,None,None)"
        )
        env=dict(os.environ)
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
        with WorkerHostLease(self.workspace):
            second=subprocess.run([sys.executable,"-S","-c",probe],cwd=self.temp.name,
                                  capture_output=True,text=True,timeout=15,env=env)
            self.assertNotEqual(second.returncode,0)
            self.assertIn("Another NVP host owns",second.stderr)
        next_host=subprocess.run([sys.executable,"-S","-c",probe],cwd=self.temp.name,
                                  capture_output=True,text=True,timeout=15,env=env)
        self.assertEqual(next_host.returncode,0,next_host.stderr)

    def test_hard_process_exit_releases_kernel_lock_not_stale_pid_lease(self):
        marker=Path(self.temp.name)/"owner.ready"
        code=(
            "import os,time;from pathlib import Path;"
            "from backend.nvp_worker_host_lease import WorkerHostLease;"
            f"l=WorkerHostLease(Path({str(self.workspace)!r}));l.__enter__();"
            f"Path({str(marker)!r}).write_text('owned');"
            "time.sleep(.8);os._exit(17)"
        )
        env=dict(os.environ)
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
        child=subprocess.Popen([sys.executable,"-S","-c",code],cwd=self.temp.name,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        try:
            for _ in range(100):
                if marker.exists() or child.poll() is not None: break
                time.sleep(.02)
            self.assertTrue(marker.exists(),"Owner failed to acquire journal lease")
            with self.assertRaisesRegex(RuntimeError,"Another NVP host"):
                with WorkerHostLease(self.workspace):pass
            _,errors=child.communicate(timeout=15)
            self.assertEqual(child.returncode,17,errors.decode("utf8",errors="replace"))
            with WorkerHostLease(self.workspace): pass
        finally:
            if child.poll() is None:
                child.kill();child.wait()

    def test_secondary_supervisor_cannot_mark_live_host_worker_interrupted(self):
        binary=Path(sys.executable).resolve()
        first=BlenderWorkerSupervisor(self.workspace,
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version="Blender 5.2.3")
        second=BlenderWorkerSupervisor(self.workspace,
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version="Blender 5.2.3")
        with WorkerHostLease(self.workspace):
            with self.assertRaisesRegex(RuntimeError,"Another NVP host"):
                second.recover_interrupted()
            with self.assertRaisesRegex(RuntimeError,"Another NVP host"):
                second.run(BlenderOperation(
                    job_id="would_be_unapproved",script="missing.py",
                    script_sha256="a"*64,inputs={},outputs={"x.json":"json_audit"},
                    arguments={}))
        self.assertEqual(second.recover_interrupted(),[])
        self.assertEqual(first.recover_interrupted(),[])


if __name__=="__main__":
    unittest.main()
