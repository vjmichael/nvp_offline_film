"""Windows native CreateProcessW suspended-first worker containment.

The codec is created CREATE_SUSPENDED, then assigned to a KILL_ON_JOB_CLOSE
Job Object by the caller *before* ResumeThread. A failed admission/assignment
terminates the still-suspended child. No cmd.exe, PowerShell, shell or FFmpeg.

This uses a STARTUPINFOEXW restricted HANDLE_LIST of only three duplicate
standard handles. Windows native CI must prove the handle allowlist. A
separately protected installed service identity remains an external gate.
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
EXTENDED_STARTUPINFO_PRESENT=0x00080000
PROC_THREAD_ATTRIBUTE_HANDLE_LIST=0x00020002
DUPLICATE_SAME_ACCESS=0x00000002
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

class STARTUPINFOEXW(ctypes.Structure):
    _fields_=[("StartupInfo",STARTUPINFOW),
              ("lpAttributeList",ctypes.c_void_p)]


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
        ctypes.POINTER(STARTUPINFOEXW),
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
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.DuplicateHandle.argtypes=[
        wintypes.HANDLE,wintypes.HANDLE,wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,wintypes.BOOL,
        wintypes.DWORD]
    kernel.DuplicateHandle.restype=wintypes.BOOL
    kernel.InitializeProcThreadAttributeList.argtypes=[
        ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t)]
    kernel.InitializeProcThreadAttributeList.restype=wintypes.BOOL
    kernel.UpdateProcThreadAttribute.argtypes=[
        ctypes.c_void_p,wintypes.DWORD,ctypes.c_size_t,
        ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,
        ctypes.c_void_p]
    kernel.UpdateProcThreadAttribute.restype=wintypes.BOOL
    kernel.DeleteProcThreadAttributeList.argtypes=[ctypes.c_void_p]
    kernel.DeleteProcThreadAttributeList.restype=None
    executable=str(executable)
    if not os.path.isabs(executable) or not os.path.isfile(executable):
        raise PermissionError("SHA-reviewed absolute native codec executable required")
    command=ctypes.create_unicode_buffer(
        subprocess.list2cmdline([executable,*argv]))
    environ=ctypes.create_unicode_buffer(
        "\0".join(f"{k}={v}" for k,v in sorted(env.items(),
                  key=lambda pair:pair[0].upper()))+"\0\0")
    flags=(CREATE_SUSPENDED|CREATE_NEW_PROCESS_GROUP|
           CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW|
           EXTENDED_STARTUPINFO_PRESENT)
    # Duplicate ONLY stdin/stdout/stderr as inheritable handles. The Windows
    # HANDLE_LIST explicitly excludes every other inheritable host handle,
    # even when a parent plugin or thread created one earlier.
    originals=[msvcrt.get_osfhandle(f.fileno()) for f in
               (stdin,stdout,stderr)]
    current=kernel.GetCurrentProcess()
    duplicates=[]
    attr_buffer=None
    attr_initialized=False
    try:
        for original in originals:
            copied=wintypes.HANDLE()
            if not kernel.DuplicateHandle(
                    current,wintypes.HANDLE(original),current,
                    ctypes.byref(copied),0,True,DUPLICATE_SAME_ACCESS):
                raise OSError(ctypes.get_last_error(),"DuplicateHandle failed")
            duplicates.append(copied)
        allowed=(wintypes.HANDLE*len(duplicates))(*[
            h.value for h in duplicates])
        length=ctypes.c_size_t()
        kernel.InitializeProcThreadAttributeList(None,1,0,ctypes.byref(length))
        if length.value==0:
            raise OSError(ctypes.get_last_error(),
                          "Native attribute-list size unavailable")
        attr_buffer=ctypes.create_string_buffer(length.value)
        pointer=ctypes.cast(attr_buffer,ctypes.c_void_p)
        if not kernel.InitializeProcThreadAttributeList(
                pointer,1,0,ctypes.byref(length)):
            raise OSError(ctypes.get_last_error(),
                          "InitializeProcThreadAttributeList failed")
        attr_initialized=True
        if not kernel.UpdateProcThreadAttribute(
                pointer,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                ctypes.cast(allowed,ctypes.c_void_p),
                ctypes.sizeof(allowed),None,None):
            raise OSError(ctypes.get_last_error(),
                          "Restricted STARTUPINFOEX HANDLE_LIST failed")
        start=STARTUPINFOEXW()
        start.StartupInfo.cb=ctypes.sizeof(STARTUPINFOEXW)
        start.StartupInfo.dwFlags=STARTF_USESTDHANDLES
        start.StartupInfo.hStdInput=duplicates[0]
        start.StartupInfo.hStdOutput=duplicates[1]
        start.StartupInfo.hStdError=duplicates[2]
        start.lpAttributeList=pointer
        process=PROCESS_INFORMATION()
        success=kernel.CreateProcessW(
            executable,command,None,None,True,flags,ctypes.cast(
                environ,ctypes.c_void_p),str(cwd),
            ctypes.byref(start),ctypes.byref(process))
        if not success:
            raise OSError(ctypes.get_last_error(),
                          "Suspended restricted CreateProcessW failed")
        return SuspendedWindowsProcess(
            process.hProcess,process.hThread,process.dwProcessId,kernel)
    finally:
        if attr_initialized:
            kernel.DeleteProcThreadAttributeList(
                ctypes.cast(attr_buffer,ctypes.c_void_p))
        for handle in duplicates:
            kernel.CloseHandle(handle)
