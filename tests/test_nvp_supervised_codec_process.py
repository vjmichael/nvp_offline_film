"""WO4 native process-tree containment tests; real Python child processes."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sys
import time
import unittest

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_supervised_codec_process import (
    WorkerCancelled,WorkerTimeout,run_supervised_codec)


class NativeCodecWorkerProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        exe=Path(sys.executable).resolve(strict=True)
        # Only in this test: the signed test interpreter occupies a controlled
        # codec identity. Real production uses actual pinned OpenJPEG/CineCert.
        self.codec=ApprovedCodecBinary(
            exe,sha256=digest_file(exe),product="OpenJPEG-opj_compress")

    def test_actual_child_returns_bounded_receipt(self):
        result=run_supervised_codec(
            self.codec,["-c","print('codec-worker-result')"],
            workdir=self.root,check_cancel=lambda:False,timeout=5,
            read_stdout=True)
        self.assertEqual(result["exit_code"],0)
        self.assertIn(b"codec-worker-result",result["stdout"])
        self.assertTrue(result["process_group_supervised"])

    @unittest.skipUnless(sys.platform=="win32",
                         "Genuine Windows kernel containment test only")
    def test_child_is_in_job_before_first_code_instruction(self):
        script=(
            "import ctypes;"
            "from ctypes import wintypes;"
            "k=ctypes.WinDLL('kernel32',use_last_error=True);"
            "k.GetCurrentProcess.restype=wintypes.HANDLE;"
            "k.IsProcessInJob.argtypes=[wintypes.HANDLE,wintypes.HANDLE,"
            "ctypes.POINTER(wintypes.BOOL)];"
            "result=wintypes.BOOL();"
            "assert k.IsProcessInJob(k.GetCurrentProcess(),None,"
            "ctypes.byref(result));"
            "print('INSIDE_JOB_BEFORE_FIRST_INSTRUCTION' "
            "if result.value else 'NOT_IN_JOB')"
        )
        probe=self.root/"win_job_probe.py"
        probe.write_text(script)
        record=run_supervised_codec(
            self.codec,[str(probe)],workdir=self.root,
            check_cancel=lambda:False,timeout=8,read_stdout=True)
        self.assertIn(b"INSIDE_JOB_BEFORE_FIRST_INSTRUCTION",record["stdout"])
        self.assertTrue(record["windows_assignment_race_eliminated"])
        self.assertTrue(record["process_group_supervised"])

    @unittest.skipUnless(sys.platform=="win32",
                         "Genuine Windows inheritance security test only")
    def test_unlisted_inheritable_handle_cannot_reach_codec(self):
        # A numeric HANDLE in a child may be *reused* for an unrelated
        # object (including Python startup handles). GetHandleInformation
        # alone falsely reports a leak in that case. Prove inheritance by
        # attempting to WRITE a unique marker into the parent's exact pipe,
        # then observing the actual parent-side pipe bytes.
        import ctypes
        from ctypes import wintypes
        import msvcrt
        import secrets
        read_fd,write_fd=os.pipe()
        try:
            unlisted=msvcrt.get_osfhandle(write_fd)
            os.set_handle_inheritable(unlisted,True)
            marker=secrets.token_bytes(24)
            probe=self.root/"probe_no_handle_leak.py"
            probe.write_text(
                "import ctypes,sys\\n"
                "from ctypes import wintypes\\n"
                "k=ctypes.WinDLL('kernel32',use_last_error=True)\\n"
                "k.WriteFile.argtypes=[wintypes.HANDLE,ctypes.c_void_p,"
                "wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]\\n"
                "k.WriteFile.restype=wintypes.BOOL\\n"
                "payload=bytes.fromhex(sys.argv[2])\\n"
                "buf=ctypes.create_string_buffer(payload)\\n"
                "written=wintypes.DWORD()\\n"
                "ok=k.WriteFile(wintypes.HANDLE(int(sys.argv[1])),buf,"
                "len(payload),ctypes.byref(written),None)\\n"
                "print('NUMERIC_HANDLE_WRITABLE' if ok and "
                "written.value==len(payload) else "
                "'NUMERIC_HANDLE_NOT_WRITABLE',flush=True)\\n")
            record=run_supervised_codec(
                self.codec,[str(probe),str(unlisted),marker.hex()],
                workdir=self.root,check_cancel=lambda:False,
                timeout=8,read_stdout=True)
            self.assertIn(b"NUMERIC_HANDLE_",record["stdout"])
            kernel=ctypes.WinDLL("kernel32",use_last_error=True)
            kernel.PeekNamedPipe.argtypes=[
                wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,
                ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p]
            kernel.PeekNamedPipe.restype=wintypes.BOOL
            readable=msvcrt.get_osfhandle(read_fd)
            available=wintypes.DWORD()
            self.assertTrue(kernel.PeekNamedPipe(
                wintypes.HANDLE(readable),None,0,None,
                ctypes.byref(available),None))
            actual=os.read(read_fd,available.value) if available.value else b""
            self.assertNotIn(marker,actual,
                "Unlisted parent pipe was writable by contained codec child")
            # Positive control: this must really be the pipe we inspected.
            os.write(write_fd,b"HOST_ONLY_CONTROL")
            self.assertTrue(kernel.PeekNamedPipe(
                wintypes.HANDLE(readable),None,0,None,
                ctypes.byref(available),None))
            self.assertEqual(os.read(read_fd,available.value),b"HOST_ONLY_CONTROL")
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_native_cancel_kills_process_promptly(self):
        start=time.monotonic()
        with self.assertRaises(WorkerCancelled):
            run_supervised_codec(
                self.codec,["-c","import time;time.sleep(30)"],
                workdir=self.root,
                check_cancel=lambda:time.monotonic()-start>0.3,
                timeout=10)
        self.assertLess(time.monotonic()-start,5)

    def test_timeout_kills_hung_native_worker(self):
        start=time.monotonic()
        with self.assertRaises(WorkerTimeout):
            run_supervised_codec(
                self.codec,["-c","import time;time.sleep(30)"],
                workdir=self.root,check_cancel=lambda:False,timeout=1)
        self.assertLess(time.monotonic()-start,5)

    def test_spawned_child_tree_is_terminated_with_native_parent(self):
        script=self.root/"spawn_native_child.py"
        child_script=(
            "import subprocess,sys,time,pathlib\n"
            "p=subprocess.Popen([sys.executable,'-c',"
            "'import time;time.sleep(60)'])\n"
            "pathlib.Path('spawned.pid').write_text(str(p.pid))\n"
            "time.sleep(60)\n")
        script.write_text(child_script)
        start=time.monotonic()
        def check():
            file=self.root/"spawned.pid"
            return file.is_file() and time.monotonic()-start>0.4
        with self.assertRaises(WorkerCancelled):
            run_supervised_codec(self.codec,[str(script)],workdir=self.root,
                                 check_cancel=check,timeout=8)
        self.assertTrue((self.root/"spawned.pid").is_file())
        child_pid=int((self.root/"spawned.pid").read_text())
        # Windows Job Object and Linux process-group termination can leave a
        # transient POSIX zombie; check whether any child remains *running*.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if os.name=="nt":
                import ctypes
                kernel=ctypes.WinDLL("kernel32",use_last_error=True)
                kernel.OpenProcess.restype=ctypes.c_void_p
                proc=kernel.OpenProcess(0x1000,False,child_pid)
                if not proc:
                    break
                code=ctypes.c_ulong()
                still=kernel.GetExitCodeProcess(
                    ctypes.c_void_p(proc),ctypes.byref(code))
                kernel.CloseHandle(ctypes.c_void_p(proc))
                if not still or code.value!=259: # STILL_ACTIVE
                    break
            else:
                file=Path(f"/proc/{child_pid}/stat")
                if not file.exists() or file.read_text().split(") ")[1][0]=="Z":
                    break
            time.sleep(0.05)
        else:
            self.fail("Native cancelled process tree left a live child")

if __name__=="__main__":
    unittest.main()
