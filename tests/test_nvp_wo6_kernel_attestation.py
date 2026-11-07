"""WO6 native Windows kernel Job Object lifecycle and hard-supervisor-exit tests."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_wo6_kernel_attestation import (
    immutable_job_name, persist_windows_job_identity,
    attest_windows_job_stopped)
from backend.nvp_worker_containment import launch_contained


class WindowsWO6KernelRecoveryTests(unittest.TestCase):
    def test_named_job_identity_is_exact_and_unforgeable_by_invalid_task_ids(self):
        task="wo6take_"+"a"*24
        self.assertEqual(immutable_job_name(task),immutable_job_name(task))
        self.assertTrue(immutable_job_name(task).startswith("NVP-WO6-"))
        for value in ("wo6take_../../secret","wo6take_"+"A"*24,
                      "wo6data_"+"b"*23,"other_"+"a"*24):
            with self.assertRaises(ValueError):
                immutable_job_name(value)

    @unittest.skipUnless(os.name=="nt","Actual Windows kernel Job Object required")
    def test_named_job_is_live_until_kernel_closes_real_handle(self):
        task="wo6shot_"+"b"*24
        spec_sha="a"*64
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            name=persist_windows_job_identity(
                folder,task_id=task,spec_sha256=spec_sha,owner="native_host")
            self.assertTrue(attest_windows_job_stopped(
                folder,task_id=task,spec_sha256=spec_sha,owner="native_host"))
            with (folder/"stdout").open("wb") as out, (
                    folder/"stderr").open("wb") as err:
                proc=launch_contained(
                    [sys.executable,"-S","-c","import time; time.sleep(40)"],
                    cwd=str(folder),stdout=out,stderr=err,memory_mb=1024,
                    windows_job_name=name)
                try:
                    self.assertIsNone(proc.poll())
                    self.assertFalse(attest_windows_job_stopped(
                        folder,task_id=task,spec_sha256=spec_sha,owner="native_host"))
                    proc.terminate_tree()
                finally:
                    proc.close()
            for _ in range(30):
                if attest_windows_job_stopped(
                    folder,task_id=task,spec_sha256=spec_sha,owner="native_host"):
                    break
                time.sleep(.1)
            self.assertTrue(attest_windows_job_stopped(
                folder,task_id=task,spec_sha256=spec_sha,owner="native_host"))

    @unittest.skipUnless(os.name=="nt","Actual Windows OS hard-exit proof required")
    def test_true_hard_parent_crash_stops_named_wo6_worker_tree(self):
        task="wo6data_"+"c"*24
        spec_sha="d"*64
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            name=persist_windows_job_identity(
                folder,task_id=task,spec_sha256=spec_sha,owner="native_host")
            marker=folder/"host_spawned"
            host_code=(
                "import os,sys,time;from pathlib import Path;"
                "from backend.nvp_worker_containment import launch_contained;"
                f"root=Path({str(folder)!r});"
                "(root/'stdout').open('wb').close();"
                "(root/'stderr').open('wb').close();"
                "out=(root/'stdout').open('wb');err=(root/'stderr').open('wb');"
                "proc=launch_contained([sys.executable,'-S','-c',"
                "'import time;time.sleep(90)'],"
                f"cwd=str(root),stdout=out,stderr=err,memory_mb=1024,windows_job_name={name!r});"
                f"Path({str(marker)!r}).write_text('worker_in_job');"
                "assert proc.poll() is None;os._exit(29)")
            environment=dict(os.environ)
            environment["PYTHONPATH"]=(
                str(Path(__file__).resolve().parents[1])+os.pathsep+
                environment.get("PYTHONPATH",""))
            host=subprocess.Popen(
                [sys.executable,"-c",host_code],
                cwd=str(folder),env=environment,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                _,errors=host.communicate(timeout=20)
                self.assertEqual(host.returncode,29,errors.decode(errors="replace"))
                self.assertTrue(marker.is_file(),"No real host worker launch evidence")
                for _ in range(80):
                    if attest_windows_job_stopped(
                        folder,task_id=task,spec_sha256=spec_sha,
                        owner="native_host"):
                        break
                    time.sleep(.1)
                self.assertTrue(attest_windows_job_stopped(
                    folder,task_id=task,spec_sha256=spec_sha,owner="native_host"),
                    "Kernel named Job Object survived its last handle close")
            finally:
                if host.poll() is None:
                    host.kill()
                    host.wait(timeout=10)


if __name__=="__main__":
    unittest.main()
