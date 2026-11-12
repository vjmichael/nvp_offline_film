"""Actual Win32 release gate and worker Job Object custody acceptance.

Linux only checks refusal; Windows executes original kernel file-range locks,
suspended CreateProcess, Job accounting and release-mutation exclusion. These
tests use a throwaway CI Windows runner, NOT an authorized owner upgrade.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from backend.nvp_w1g_release_gate import (
    WindowsReleaseMutationGate, WindowsWorkerLifetimeSlot,
)
from backend.nvp_worker_containment import launch_contained


class ReleaseWideKernelFence(unittest.TestCase):
    def test_no_kernel_claim_on_non_windows(self):
        if os.name=="nt":
            self.skipTest("Real Windows tests cover native admission")
        with self.assertRaises(RuntimeError):
            WindowsReleaseMutationGate()
        with self.assertRaises(RuntimeError):
            WindowsWorkerLifetimeSlot()

    @unittest.skipUnless(os.name=="nt","Genuine Windows byte-range locks")
    def test_two_independent_workers_block_upgrade_until_both_close(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            processes=[]
            try:
                for i in (1,2):
                    with (root/f"out-{i}").open("wb") as out, (
                            root/f"err-{i}").open("wb") as err:
                        proc=launch_contained(
                            [sys.executable,"-S","-c","import time;time.sleep(45)"],
                            cwd=td,stdout=out,stderr=err,memory_mb=512)
                    processes.append(proc)
                    self.assertIsNone(proc.poll())
                    self.assertIsNotNone(proc._release_slot)
                self.assertNotEqual(processes[0]._release_slot.slot,
                                    processes[1]._release_slot.slot)
                with self.assertRaises(PermissionError):
                    with WindowsReleaseMutationGate():
                        self.fail("Live Job Objects cannot permit program mutation")
                processes[0].terminate_tree()
                processes[0].close()
                with self.assertRaises(PermissionError):
                    with WindowsReleaseMutationGate():
                        self.fail("The second independent job is still running")
                processes[1].terminate_tree()
                processes[1].close()
                with WindowsReleaseMutationGate() as gate:
                    self.assertTrue(gate.held)
                    with self.assertRaises(PermissionError):
                        WindowsWorkerLifetimeSlot().acquire()
                worker=WindowsWorkerLifetimeSlot().acquire()
                worker.release()
            finally:
                for p in processes:
                    try:
                        if p._job is not None:
                            p.terminate_tree()
                        p.close()
                    except Exception:
                        pass

    @unittest.skipUnless(os.name=="nt","Native release-wide domain verification")
    def test_all_five_native_domains_and_interrupted_journal_gate(self):
        import sqlite3
        from tools.nvp_w1g_production_authority import WindowsReleaseWorkerStopEvidence
        from tools.nvp_w1g_nsis_recovery import _digest, _program
        from test_nvp_e2e01e_package_guard import make_pe
        with TemporaryDirectory() as td:
            root=Path(td)
            active=root/"Programs"/"NVP"
            active.mkdir(parents=True)
            make_pe(active/"NVP.exe")
            (active/"nvp-alpha-install.marker").write_bytes(b"NVP-ALPHA-INSTALL-v1")
            domains={name:root/"Runtime"/name
                     for name in WindowsReleaseWorkerStopEvidence.REQUIRED_DOMAINS}
            for path in domains.values():
                path.mkdir(parents=True)
            witness=WindowsReleaseWorkerStopEvidence(active,worker_workspaces=domains)
            original=_digest(_program(active))
            with witness.transaction():
                proof=witness(original)
                self.assertTrue(proof["release_wide_launch_fence_verified"])
                self.assertTrue(proof["complete_worker_domain_roster_verified"])
            journal=domains["filming"]/"worker_jobs.sqlite3"
            with sqlite3.connect(journal) as db:
                db.execute("CREATE TABLE worker_jobs (state TEXT NOT NULL)")
                db.execute("INSERT INTO worker_jobs(state) VALUES ('INTERRUPTED')")
            with witness.transaction():
                with self.assertRaisesRegex(PermissionError,"Unreconciled"):
                    witness(original)
            journal.unlink()
            # Every OS-owned process may have exited, yet missing domain
            # declarations must NEVER be promoted as complete release custody.
            incomplete={k:v for k,v in domains.items() if k!="audio"}
            with self.assertRaisesRegex(PermissionError,"All five"):
                WindowsReleaseWorkerStopEvidence(active,worker_workspaces=incomplete)

    @unittest.skipUnless(os.name=="nt","Real guardian-host kill-on-close and kernel file locks")
    def test_hard_host_death_frees_gate_only_after_job_kernel_close(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            marker=root/"original-worker.json"
            child_code=(
                "import os,json,time;from pathlib import Path;"
                f"Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid()}}));"
                "time.sleep(60)"
            )
            host_code=(
                "import os,sys,time;from pathlib import Path;"
                "from backend.nvp_worker_containment import launch_contained;"
                f"root=Path({td!r});"
                'out=(root/"out").open("wb");err=(root/"err").open("wb");'
                f"p=launch_contained([sys.executable,'-S','-c',{child_code!r}],"
                "cwd=str(root),stdout=out,stderr=err,memory_mb=512);"
                f"m=Path({str(marker)!r});"
                "[(time.sleep(.05)) for i in range(200) if not m.exists()];"
                "assert m.exists() and p.poll() is None;"
                "os._exit(81)"
            )
            env=dict(os.environ)
            env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
            host=subprocess.Popen(
                [sys.executable,"-c",host_code],cwd=td,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                _,error=host.communicate(timeout=25)
                self.assertEqual(host.returncode,81,error.decode("utf8","replace"))
                self.assertTrue(marker.exists(),"Original worker never started")
                from test_worker_containment import running
                pid=json.loads(marker.read_text())["pid"]
                for _ in range(100):
                    if not running(pid):
                        break
                    time.sleep(.1)
                self.assertFalse(running(pid),"Original Job Object orphan survived host death")
                # The crashed process's release slot must have been released
                # by the Windows kernel, not a stale PID/timestamp.
                with WindowsReleaseMutationGate() as gate:
                    self.assertTrue(gate.held)
            finally:
                if host.poll() is None:
                    host.kill();host.wait()


if __name__=="__main__":
    unittest.main()
