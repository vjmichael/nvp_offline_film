"""Native supervised codec process ownership for WO4 LF02/LF04.

No shell or arbitrary browser command. Executables are SHA-pinned
ApprovedCodecBinary instances. All subprocess stdout/stderr is streamed to
private bounded files, not held in RAM. Explicit cancellation/timeout kills
the Linux process group or Windows Job Object process tree; no silent fallback
to killing only the direct child if job ownership cannot be established.

Windows job assignment occurs just after process creation, not atomically:
a child could theoretically spawn before assignment. Installed-app native
containment acceptance and a suspended-start broker remain OPEN.
"""
from __future__ import annotations
from hashlib import sha256
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary

MAX_ARG=240
MAX_ARGS=32
MAX_TIMEOUT=14400
MAX_LOG_BYTES=1024*1024
POLL_SECONDS=0.05

class WorkerCancelled(InterruptedError): pass
class WorkerTimeout(TimeoutError): pass


def _windows_job(proc):
    """Assign a kill-on-close Job Object to the process; fail closed."""
    from ctypes import wintypes
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    SIZE_T=ctypes.c_size_t
    class BASIC(ctypes.Structure):
        _fields_=[
            ("PerProcessUserTimeLimit",ctypes.c_int64),
            ("PerJobUserTimeLimit",ctypes.c_int64),
            ("LimitFlags",wintypes.DWORD),
            ("MinimumWorkingSetSize",SIZE_T),
            ("MaximumWorkingSetSize",SIZE_T),
            ("ActiveProcessLimit",wintypes.DWORD),
            ("Affinity",SIZE_T),
            ("PriorityClass",wintypes.DWORD),
            ("SchedulingClass",wintypes.DWORD)]
    class COUNTERS(ctypes.Structure):
        _fields_=[("ReadOperationCount",ctypes.c_uint64),
                  ("WriteOperationCount",ctypes.c_uint64),
                  ("OtherOperationCount",ctypes.c_uint64),
                  ("ReadTransferCount",ctypes.c_uint64),
                  ("WriteTransferCount",ctypes.c_uint64),
                  ("OtherTransferCount",ctypes.c_uint64)]
    class EXTENDED(ctypes.Structure):
        _fields_=[("BasicLimitInformation",BASIC),
                  ("IoInfo",COUNTERS),
                  ("ProcessMemoryLimit",SIZE_T),
                  ("JobMemoryLimit",SIZE_T),
                  ("PeakProcessMemoryUsed",SIZE_T),
                  ("PeakJobMemoryUsed",SIZE_T)]
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[
        wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.SetInformationJobObject.restype=wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype=wintypes.BOOL
    kernel.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.TerminateJobObject.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    job=kernel.CreateJobObjectW(None,None)
    if not job:
        raise OSError(ctypes.get_last_error(),"CreateJobObject failed")
    try:
        settings=EXTENDED()
        settings.BasicLimitInformation.LimitFlags=0x00002000 # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job,9,ctypes.byref(settings),
                                              ctypes.sizeof(settings)):
            raise OSError(ctypes.get_last_error(),"SetInformationJobObject failed")
        if not kernel.AssignProcessToJobObject(job,int(proc._handle)):
            raise OSError(ctypes.get_last_error(),"AssignProcessToJobObject failed")
        return job,kernel
    except BaseException:
        kernel.CloseHandle(job)
        raise


def _terminate_tree(proc,job=None):
    if sys.platform=="win32":
        if job is not None:
            handle,kernel=job
            kernel.TerminateJobObject(handle,1)
        elif proc.poll() is None:
            proc.kill() # only for setup failure, no tree-containment claim
    elif proc.poll() is None:
        try:
            os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_supervised_codec(codec,argv,*,workdir,check_cancel,
                         timeout=3600,after_start=None,read_stdout=False):
    if not isinstance(codec,ApprovedCodecBinary):
        raise PermissionError("Native SHA-reviewed executable required")
    if (type(argv) not in (tuple,list) or not 1<=len(argv)<=MAX_ARGS or
            any(type(arg) is not str or not 0<len(arg)<=MAX_ARG
                or "\x00" in arg for arg in argv) or
            not callable(check_cancel) or
            type(timeout) not in (float,int) or not 1<=timeout<=MAX_TIMEOUT):
        raise ValueError("Bounded trusted codec arguments and timeout required")
    root=Path(workdir)
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir()):
        raise PermissionError("Native private workdir required")
    codec.check()
    root=root.resolve(strict=True)
    # A job-specific directory must be privately provisioned by the host,
    # never chosen from a web request.
    env={"PATH":str(codec.executable.parent),
         "SYSTEMROOT":os.environ.get("SYSTEMROOT",""),
         "HOME":str(root),"TMP":str(root),"TEMP":str(root)}
    flags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform=="win32" else 0
    job=None
    proc=None
    with tempfile.TemporaryFile(dir=root) as stdout, tempfile.TemporaryFile(dir=root) as stderr:
        started=time.monotonic()
        try:
            proc=subprocess.Popen(
                [str(codec.executable),*argv],cwd=str(root),env=env,
                shell=False,stdin=subprocess.DEVNULL,stdout=stdout,
                stderr=stderr,start_new_session=(sys.platform!="win32"),
                creationflags=flags)
            if sys.platform=="win32":
                job=_windows_job(proc)
            if after_start is not None:
                after_start(proc.pid)
            while proc.poll() is None:
                if check_cancel():
                    raise WorkerCancelled("Explicit approved production cancellation")
                if time.monotonic()-started>timeout:
                    raise WorkerTimeout("Native codec timed out")
                time.sleep(POLL_SECONDS)
            # Evaluate cancellation even if worker exited simultaneously.
            if check_cancel():
                raise WorkerCancelled("Production cancellation at codec boundary")
            if proc.returncode!=0:
                stderr.seek(0)
                reason=stderr.read(512).decode("utf-8","replace").replace("\x00","")
                raise RuntimeError(
                    f"Pinned {codec.product} exited {proc.returncode}: {reason}")
            stdout.seek(0)
            stderr.seek(0)
            stdout_head=stdout.read(MAX_LOG_BYTES)
            stderr_head=stderr.read(MAX_LOG_BYTES)
            codec.check()
            return {**({"stdout":stdout_head[:65536]} if read_stdout else {}),
                    "status":"NATIVE_PROCESS_EXITED_ZERO",
                    "codec_sha256":codec.sha256,
                    "exit_code":0,
                    "stdout_prefix_sha256":sha256(stdout_head).hexdigest(),
                    "stderr_prefix_sha256":sha256(stderr_head).hexdigest(),
                    "diagnostic_bytes_bounded":True,
                    "elapsed_seconds":round(time.monotonic()-started,4),
                    "process_group_supervised":True,
                    "windows_assignment_race_eliminated":False,
                    "ffmpeg_used":False}
        except BaseException:
            if proc is not None:
                _terminate_tree(proc,job)
            raise
        finally:
            if proc is not None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _terminate_tree(proc,job)
                    proc.wait(timeout=5)
            if sys.platform!="win32" and proc is not None:
                # Kill surviving codec-spawned grandchildren even when the
                # wrapper itself returned success. A successful parent exit
                # is not proof the entire native process group exited.
                try:
                    os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if job is not None:
                handle,kernel=job
                kernel.CloseHandle(handle)
