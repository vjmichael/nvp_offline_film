"""STACK-02B actual OS tests: a hard host exit must kill the worker.

These are *not* mocks. The actual Blender application is exercised separately.
On Linux the parent-death guarantee covers the direct child only. On Windows
the Job Object also covers descendants until its last handle closes.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from backend.nvp_worker_containment import launch_contained


def running(pid):
    if sys.platform == "linux":
        info=Path(f"/proc/{pid}/stat")
        if not info.exists():
            return False
        try:
            state=info.read_text().rsplit(")",1)[1].split()[0]
            return state not in ("Z","X","x")
        except FileNotFoundError:
            return False
    if os.name == "nt":
        import pywintypes, win32api, win32con, win32event
        try:
            handle=win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION | win32con.SYNCHRONIZE,False,pid)
        except pywintypes.error:
            return False
        try:
            return win32event.WaitForSingleObject(handle,0) == win32event.WAIT_TIMEOUT
        finally:
            handle.Close()
    raise RuntimeError("Unsupported test OS")


class KernelContainmentTests(unittest.TestCase):
    def test_actual_contained_worker_cancellation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with (root/"stdout").open("wb") as out,(root/"stderr").open("wb") as err:
                proc=launch_contained([sys.executable,"-S","-c","import time; time.sleep(60)"],
                    cwd=temp,stdout=out,stderr=err,memory_mb=1024)
                try:
                    self.assertIsNone(proc.poll())
                    self.assertTrue(running(proc.pid))
                    proc.terminate_tree()
                    self.assertIsNotNone(proc.poll())
                finally:
                    proc.close()

    def test_actual_hard_supervisor_exit_kills_running_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ready=root/"ready.json"
            child_code=(
                "import os,json,time; from pathlib import Path; "
                f"Path({str(ready)!r}).write_text(json.dumps({{'pid':os.getpid()}}));"
                "time.sleep(60)"
            )
            host_code=(
                "import os,sys,time; from pathlib import Path; "
                "from backend.nvp_worker_containment import launch_contained; "
                f"root=Path({temp!r}); "
                'out=(root/"out.log").open("wb");err=(root/"err.log").open("wb");'
                f'child=launch_contained([sys.executable,"-S","-c",{child_code!r}],'
                'cwd=str(root),stdout=out,stderr=err,memory_mb=1024);'
                f'marker=Path({str(ready)!r});'
                '[(time.sleep(.05)) for i in range(200) if not marker.exists()];'
                'assert marker.exists() and child.poll() is None, "child failed to start";'
                'os._exit(19)'
            )
            env=dict(os.environ)
            env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
            host=subprocess.Popen([sys.executable,"-c",host_code],
                cwd=temp,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                _,error=host.communicate(timeout=25)
                self.assertEqual(host.returncode,19,error.decode("utf8",errors="replace"))
                self.assertTrue(ready.exists())
                pid=json.loads(ready.read_text())["pid"]
                for _ in range(120):
                    if not running(pid): break
                    time.sleep(.1)
                self.assertFalse(running(pid),"Kernel did not stop worker after real host crash")
            finally:
                if host.poll() is None:
                    host.kill();host.wait()
                if ready.exists() and sys.platform=="linux":
                    import signal
                    pid=json.loads(ready.read_text())["pid"]
                    if running(pid):
                        try: os.killpg(pid,signal.SIGKILL)
                        except ProcessLookupError: pass

    @unittest.skipUnless(os.name == "nt", "Windows Job Object descendant contract")
    def test_windows_job_closure_kills_child_and_grandchild(self):
        # A *real* descendant is created by the worker, then the supervising
        # host exits via os._exit without invoking close/cancellation.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            marker=root/"tree.json"
            child_code=(
                "import os,json,time,subprocess,sys; from pathlib import Path;"
                "gc=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(90)']);"
                f"Path({str(marker)!r}).write_text(json.dumps({{'child':os.getpid(),'grandchild':gc.pid}}));"
                "time.sleep(90)"
            )
            host_code=(
                "import os,sys,time; from pathlib import Path;"
                "from backend.nvp_worker_containment import launch_contained;"
                f"root=Path({temp!r});"
                'out=(root/"treeout").open("wb");err=(root/"treeerr").open("wb");'
                f'worker=launch_contained([sys.executable,"-S","-c",{child_code!r}],'
                'cwd=str(root),stdout=out,stderr=err,memory_mb=1024);'
                f'marker=Path({str(marker)!r});'
                '[(time.sleep(.05)) for i in range(200) if not marker.exists()];'
                'assert marker.exists() and worker.poll() is None;os._exit(19)'
            )
            env=dict(os.environ)
            env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
            host=subprocess.Popen([sys.executable,"-c",host_code],cwd=temp,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                _,error=host.communicate(timeout=25)
                self.assertEqual(host.returncode,19,error.decode("utf8",errors="replace"))
                pids=json.loads(marker.read_text())
                for _ in range(100):
                    if all(not running(pid) for pid in pids.values()):
                        break
                    time.sleep(.1)
                self.assertTrue(all(not running(pid) for pid in pids.values()),
                    "Closing supervisor Job Object did not kill the entire real process tree")
            finally:
                if host.poll() is None:
                    host.kill();host.wait()
                if marker.exists():
                    for pid in json.loads(marker.read_text()).values():
                        if running(pid):
                            subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],
                                capture_output=True,timeout=12,check=False)

    def test_kernel_memory_limit_prevents_oversized_allocation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            code=("import sys\ntry:\n x=bytearray(1600*1024*1024);"
                  " sys.exit(43)\nexcept MemoryError:\n sys.exit(42)\n")
            with (root/"out").open("wb") as out,(root/"err").open("wb") as err:
                proc=launch_contained([sys.executable,"-S","-c",code],
                    cwd=temp,stdout=out,stderr=err,memory_mb=1024)
                try:
                    exitcode=proc.wait(timeout=20)
                    self.assertNotEqual(exitcode,43,"Allocation exceeded kernel memory limit")
                finally:
                    proc.close()


if __name__=="__main__":
    unittest.main()
