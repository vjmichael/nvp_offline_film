"""W1-G legacy rigging/Blender execution shares the real Windows release gate."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender
from backend.nvp_w1g_release_gate import WindowsReleaseMutationGate


class ContainedLegacyBlenderLaunch(unittest.TestCase):
    def test_native_bounded_output_and_result(self):
        with tempfile.TemporaryDirectory() as td:
            result=run_trusted_blender(
                [sys.executable,"-S","-c","print('original Blender adapter output')"],
                cwd=td,timeout=20)
            self.assertEqual(result.returncode,0)
            self.assertIn("original Blender adapter output",result.stdout)
            self.assertEqual(result.stderr,"")

    @unittest.skipUnless(os.name=="nt","Windows Job Object native acceptance")
    def test_release_upgrade_denied_while_legacy_worker_executes(self):
        with tempfile.TemporaryDirectory() as td:
            result=[]
            errors=[]
            def work():
                try:
                    result.append(run_trusted_blender(
                        [sys.executable,"-S","-c","import time;time.sleep(3);print('reaped')"],
                        cwd=td,timeout=20))
                except BaseException as exc:
                    errors.append(exc)
            thread=threading.Thread(target=work)
            thread.start()
            observed=False
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline and thread.is_alive():
                    try:
                        with WindowsReleaseMutationGate():
                            pass
                    except PermissionError:
                        observed=True
                        break
                    time.sleep(.03)
                self.assertTrue(observed,"Trusted Blender worker never held original kernel slot")
            finally:
                thread.join(timeout=25)
            self.assertFalse(thread.is_alive(),"Legacy Blender worker failed bounded cleanup")
            self.assertFalse(errors,repr(errors))
            self.assertEqual(result[0].returncode,0)
            with WindowsReleaseMutationGate() as gate:
                self.assertTrue(gate.held)

    def test_rejects_shell_string_unbounded_timeout_and_output_flags(self):
        with tempfile.TemporaryDirectory() as td:
            for kw in (
                {"command":"shell"} if False else {"timeout":0},
                {"timeout":True},
                {"timeout":100000},
                {"capture_output":False},
                {"text":False},
                {"check":True},
            ):
                with self.assertRaises(ValueError):
                    run_trusted_blender([sys.executable],cwd=td,**kw)
            with self.assertRaises(ValueError):
                run_trusted_blender("python -c 'unsafe'",cwd=td)


if __name__=="__main__":
    unittest.main()
