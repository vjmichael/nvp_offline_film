"""Windows native CreateProcessW suspended-first worker containment.

The codec is created CREATE_SUSPENDED, then assigned to a KILL_ON_JOB_CLOSE
Job Object by the caller *before* ResumeThread. A failed admission/assignment
terminates the still-suspended child. No cmd.exe, PowerShell, shell or FFmpeg.

This is a native Windows implementation; CI must prove it on real Windows.
Installer/service identity, restricted token and process handle allowlist
remain independent release gates.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time

CREATE_SUSPENDED=0x00000004
CREATE_NEW_PROCESS_GROUP=0x00000200
CREATE_UNICODE_ENVIRONMENT=0x00000400
CREATE_NO_WINDOW=0x08000000
STARTF_USESTDHANDLES=0x00000100
WAIT_TIMEOUT=0x00000102
WAIT_OBJECT_0=0

class STARTUPINFOW(ctypes.Structure):
    _fields_=[
        ("cb",wintypes.DWORD),("lpReserved",wintypes.LPWSTR),
        ("lpDesktop",wintypes.LPWSTR),("lpTitle",wintypes.LPWSTR),
        ("dwX",wintypes.DWORD),("dwY",wintypes.DWORD),
        ("dwXSize",wintypes.DWORD),("dwYSize",wintypes.DWORD),
        ("dwXCountChars",wintypes.DWORD),("dwYCountChars",wintypes.DWORD),
        ("dwFillAttribute",wintypes.DWORD),("dwFlags",wintypes.DWORD),
        ("wShowWindow",wintypes.WORD),("cbReserved2",wintypes.WORD),
        ("lpReserved2",ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput",wintypes.HANDLE),
        ("hStdOutput",wintypes.HANDLE),
        ("hStdError",wintypes.HANDLE)
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_=[("hProcess",wintypes.HANDLE),
              ("hThread",wintypes.HANDLE),
              ("dwProcessId",wintypes.DWORD),
              ("dwThreadId",wintypes.DWORD)]


class SuspendedWindowsProcess:
    def __init__(self,handle,thread,pid,kernel):
        self._handle=handle
        self._thread=thread
        self.pid=int(pid)
        self._kernel=kernel
        self.returncode=None
        self.resumed=False
        self.assignment_before_execution=False

    def resume_after_job_assignment(self):
        if self._thread is None or self.resumed:
            raise PermissionError("Native worker must resume exactly once")
        if self._kernel.ResumeThread(self._thread)==0xFFFFFFFF:
            raise OSError(ctypes.get_last_error(),"ResumeThread failed")
        self.resumed=True
        self.assignment_before_execution=True
        self._kernel.CloseHandle(self._thread)
        self._thread=None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        outcome=self._kernel.WaitForSingleObject(self._handle,0)
        if outcome==WAIT_TIMEOUT:
            return None
        if outcome!=WAIT_OBJECT_0:
            raise OSError(ctypes.get_last_error(),"WaitForSingleObject failed")
        result=wintypes.DWORD()
        if not self._kernel.GetExitCodeProcess(self._handle,ctypes.byref(result)):
            raise OSError(ctypes.get_last_error(),"GetExitCodeProcess failed")
        self.returncode=int(result.value)
        return self.returncode

    def wait(self,timeout=None):
        if self.poll() is not None:
            return self.returncode
        millis=0xFFFFFFFF if timeout is None else max(0,int(timeout*1000))
        outcome=self._kernel.WaitForSingleObject(self._handle,millis)
        if outcome==WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired(str(self.pid),timeout)
        return self.poll()

    def kill(self):
        if self.poll() is None:
            if not self._kernel.TerminateProcess(self._handle,1):
                raise OSError(ctypes.get_last_error(),"TerminateProcess failed")

    def close(self):
        if self._thread is not None:
            self._kernel.CloseHandle(self._thread)
            self._thread=None
        if self._handle is not None:
            self._kernel.CloseHandle(self._handle)
            self._handle=None


def create_suspended_native_worker(executable,argv,*,cwd,env,stdin,stdout,stderr):
    if sys.platform!="win32":
        raise NotImplementedError("Windows kernel process launch only")
    import msvcrt
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateProcessW.argtypes=[
        wintypes.LPCWSTR,wintypes.LPWSTR,
        ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL,wintypes.DWORD,
        ctypes.c_void_p,wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION)]
    kernel.CreateProcessW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[
        wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.ResumeThread.argtypes=[wintypes.HANDLE]
    kernel.ResumeThread.restype=wintypes.DWORD
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.TerminateProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    executable=str(executable)
    if not os.path.isabs(executable) or not os.path.isfile(executable):
        raise PermissionError("SHA-reviewed absolute native codec executable required")
    command=ctypes.create_unicode_buffer(
        subprocess.list2cmdline([executable,*argv]))
    environ=ctypes.create_unicode_buffer(
        "\0".join(f"{k}={v}" for k,v in sorted(env.items(),
                  key=lambda pair:pair[0].upper()))+"\0\0")
    flags=(CREATE_SUSPENDED|CREATE_NEW_PROCESS_GROUP|
           CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW)
    # Temporary file handles are non-inheritable by default. Mark only
    # these three required standard streams inheritable during CreateProcess.
    # True restricted handle-list inheritance is a later OS security gate.
    handles=[msvcrt.get_osfhandle(f.fileno()) for f in
             (stdin,stdout,stderr)]
    original=[os.get_handle_inheritable(h) for h in handles]
    for h in handles:os.set_handle_inheritable(h,True)
    start=STARTUPINFOW()
    start.cb=ctypes.sizeof(STARTUPINFOW)
    start.dwFlags=STARTF_USESTDHANDLES
    start.hStdInput=handles[0]
    start.hStdOutput=handles[1]
    start.hStdError=handles[2]
    process=PROCESS_INFORMATION()
    try:
        success=kernel.CreateProcessW(
            executable,command,None,None,True,flags,ctypes.cast(
                environ,ctypes.c_void_p),str(cwd),
            ctypes.byref(start),ctypes.byref(process))
        if not success:
            raise OSError(ctypes.get_last_error(),"Suspended CreateProcessW failed")
        return SuspendedWindowsProcess(
            process.hProcess,process.hThread,process.dwProcessId,kernel)
    finally:
        for h,old in zip(handles,original):
            os.set_handle_inheritable(h,old)
