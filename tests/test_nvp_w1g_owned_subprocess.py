"""W1-G: original legacy runtime subprocesses own actual Windows release slots.

Native CI exercises real Job isolation; non-Windows executions are source
compatibility tests and never certify production cgroup custody.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from backend.nvp_w1g_release_gate import WindowsReleaseMutationGate


class OwnedLegacySubprocessTests(unittest.TestCase):
    def test_bounded_stdin_stdout_and_text_capture(self):
        with TemporaryDirectory() as td:
            r=run_owned_subprocess(
                [sys.executable,"-S","-c",
                 "import sys; b=sys.stdin.buffer.read();sys.stdout.buffer.write(b[::-1])"],
                cwd=td,input=b"OriginalPCM",capture_output=True,timeout=20)
            self.assertEqual((r.returncode,r.stdout,r.stderr),(0,b"MCPlanigirO",b""))
            t=run_owned_subprocess(
                [sys.executable,"-S","-c","print('native inspected')"],
                cwd=td,capture_output=True,text=True,check=True,timeout=20)
            self.assertIn("native inspected",t.stdout)

    def test_no_shell_or_unbounded_or_interactive_input(self):
        for kw in ({"timeout":0},{"timeout":float("inf")},
                   {"timeout":True},{"capture_output":True,"stdout":subprocess.PIPE},
                   {"stdin":subprocess.PIPE},{"input":b"a","stdin":subprocess.DEVNULL}):
            with self.subTest(kw=repr(kw)):
                with self.assertRaises((ValueError,TypeError)):
                    run_owned_subprocess([sys.executable],**kw)
        with self.assertRaises(ValueError):
            run_owned_subprocess("python -c 'untrusted'")

    @unittest.skipUnless(os.name=="nt","Real Windows original Job admission only")
    def test_real_windows_worker_blocks_release_mutation_and_clears_registry(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            with patch("backend.nvp_w1g_release_gate.release_gate_path",
                       return_value=root/"original-workers.lock"):
                results=[]
                errors=[]
                def worker():
                    try:
                        results.append(run_owned_subprocess(
                            [sys.executable,"-S","-c","import time;time.sleep(3);print('done')"],
                            cwd=td,capture_output=True,text=True,timeout=20))
                    except BaseException as exc:
                        errors.append(exc)
                thread=threading.Thread(target=worker)
                thread.start()
                denied=False
                try:
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline and thread.is_alive():
                        registry=root/"legacy-jobs"
                        if registry.exists() and list(registry.glob("*.pending")):
                            try:
                                with WindowsReleaseMutationGate():
                                    pass
                            except PermissionError:
                                denied=True
                                break
                        time.sleep(.025)
                    self.assertTrue(denied,"Original legacy worker never fenced release")
                finally:
                    thread.join(timeout=25)
                self.assertFalse(thread.is_alive())
                self.assertFalse(errors,repr(errors))
                self.assertEqual(results[0].returncode,0)
                self.assertEqual(list((root/"legacy-jobs").iterdir()),[])
                with WindowsReleaseMutationGate() as gate:
                    self.assertTrue(gate.held)

    @unittest.skipUnless(os.name=="nt","Actual Windows failure journal and owner release gate")
    def test_failed_original_tool_leaves_marker_and_denies_owner_upgrade(self):
        from tools.nvp_w1g_production_authority import WindowsReleaseWorkerStopEvidence
        from tools.nvp_w1g_nsis_recovery import _digest,_program
        from test_nvp_e2e01e_package_guard import make_pe
        with TemporaryDirectory() as td:
            root=Path(td)
            program=root/"Programs"/"NVP"
            program.mkdir(parents=True)
            make_pe(program/"NVP.exe")
            (program/"nvp-alpha-install.marker").write_bytes(b"NVP-ALPHA-INSTALL-v1")
            domains={k:root/"runtime"/k for k in WindowsReleaseWorkerStopEvidence.REQUIRED_DOMAINS}
            for folder in domains.values():
                folder.mkdir(parents=True)
            with patch("backend.nvp_w1g_release_gate.release_gate_path",
                       return_value=root/"original-workers.lock"):
                result=run_owned_subprocess(
                    [sys.executable,"-S","-c","import sys;sys.exit(17)"],
                    cwd=td,capture_output=True,timeout=20)
                self.assertEqual(result.returncode,17)
                markers=list((root/"legacy-jobs").glob("*.pending"))
                self.assertEqual(len(markers),1)
                owner=WindowsReleaseWorkerStopEvidence(program,worker_workspaces=domains)
                with owner.transaction():
                    with self.assertRaisesRegex(PermissionError,"Unreconciled original legacy"):
                        owner(_digest(_program(program)))
                # Only this disposable fixture may simulate a human independent
                # reconciliation by explicitly removing its own fake marker.
                markers[0].unlink()
                with owner.transaction():
                    self.assertTrue(owner(_digest(_program(program)))["release_wide_launch_fence_verified"])


if __name__=="__main__":
    unittest.main()
