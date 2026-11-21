"""Windows-only real Job Object kill-on-close and descendant lifetime acceptance.

Requires pywin32. This is an actual subprocess tree test, not a mocked handle.
The worker creates a grandchild in a separate new process group; the Windows
Job Object must still terminate that grandchild when the owned job is killed.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_worker_containment import launch_contained


@unittest.skipUnless(os.name == "nt", "Requires actual Windows Job Objects")
class NativeWindowsJobObjectDescendants(unittest.TestCase):
    def test_job_object_kills_independent_grandchild(self):
        import win32api
        import win32con
        import win32event

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pid_file=root/"grandchild.pid"
            grandchild_code=(
                "import os,time,sys;"
                "from pathlib import Path;"
                "Path(sys.argv[1]).write_text(str(os.getpid()));"
                "time.sleep(120)"
            )
            worker_code=(
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c',"+
                    repr(grandchild_code)+",sys.argv[1]],"
                "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP);"
                "time.sleep(120)"
            )
            handle=None
            closed=False
            with (root/"stdout.txt").open("wb") as out, (root/"stderr.txt").open("wb") as err:
                proc=launch_contained([sys.executable,"-c",worker_code,str(pid_file)],
                    cwd=str(root),stdout=out,stderr=err,memory_mb=1024)
                try:
                    deadline=time.monotonic()+20
                    while time.monotonic()<deadline and not pid_file.exists():
                        if proc.poll() is not None:
                            raise RuntimeError("Actual Windows Job Object parent exited early")
                        time.sleep(.05)
                    self.assertTrue(pid_file.exists(),"Grandchild did not start")
                    pid=int(pid_file.read_text())
                    handle=win32api.OpenProcess(win32con.SYNCHRONIZE,False,pid)
                    self.assertEqual(win32event.WaitForSingleObject(handle,0),
                                     win32event.WAIT_TIMEOUT)
                    proc.terminate_tree()
                    self.assertIsNotNone(proc.poll())
                    self.assertEqual(win32event.WaitForSingleObject(handle,15000),
                                     win32event.WAIT_OBJECT_0,
                                     "Child escaped Windows Job Object termination")
                finally:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    if handle is not None:
                        handle.Close()

    def test_job_object_kill_on_close_even_if_parent_alive(self):
        import win32api
        import win32con
        import win32event

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pid_file=root/"grandchild.pid"
            worker_code=(
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c',"
                "'import os,time,sys;from pathlib import Path;"
                "Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(120)',"
                "sys.argv[1]],creationflags=subprocess.CREATE_NEW_PROCESS_GROUP);"
                "time.sleep(120)"
            )
            handle=None
            with (root/"stdout.txt").open("wb") as out, (root/"stderr.txt").open("wb") as err:
                proc=launch_contained([sys.executable,"-c",worker_code,str(pid_file)],
                    cwd=str(root),stdout=out,stderr=err,memory_mb=1024)
                try:
                    deadline=time.monotonic()+20
                    while time.monotonic()<deadline and not pid_file.exists():
                        if proc.poll() is not None:
                            raise RuntimeError("Job Object parent exited before grandchild")
                        time.sleep(.05)
                    self.assertTrue(pid_file.exists())
                    handle=win32api.OpenProcess(win32con.SYNCHRONIZE,
                                                False,int(pid_file.read_text()))
                    # Close the last host-owned Job handle. Windows must terminate
                    # both worker and grandchild via JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
                    proc.close()
                    closed=True
                    self.assertEqual(win32event.WaitForSingleObject(handle,15000),
                                     win32event.WAIT_OBJECT_0)
                finally:
                    if not closed:
                        if proc.poll() is None:
                            proc.terminate_tree()
                        proc.close()
                    if handle is not None:
                        handle.Close()


if __name__ == "__main__":
    unittest.main()
