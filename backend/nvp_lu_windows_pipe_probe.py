"""Source-only Win32 named-pipe server observation for a future signed Lu IPC.

A server PID is *untrusted observation*, not package identity, signed
provenance, a host-issued enrollment, Lu permission or a usable session.
This module NEVER sends Protobuf, reads credentials or enables operations.
Actual signed process-file and publisher validation must happen inside an
installed trusted native broker before any byte exchange.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import sys
from backend.nvp_lu_ipc_v0 import validate_windows_pipe_name

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000


def observe_local_lu_pipe_server(name: str) -> int:
    """Return only kernel-observed PID (no trust); fail closed on any error.

    Caller must independently verify signed installed Lu executable, signer
    revocation/pins, server lifetime, current SID/session, and mutual host HMAC.
    This is NOT an authenticated read-only client.
    """
    validate_windows_pipe_name(name)
    if sys.platform != 'win32':
        raise PermissionError('Only real Windows can observe a named-pipe peer')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
        wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.GetNamedPipeServerProcessId.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.ULONG))
    kernel.GetNamedPipeServerProcessId.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateFileW(name,GENERIC_READ|GENERIC_WRITE,0,None,OPEN_EXISTING,0,None)
    invalid=ctypes.c_void_p(-1).value
    if handle in (None,invalid):
        raise PermissionError('No existing native local Lu pipe endpoint')
    try:
        pid=wintypes.ULONG(0)
        if not kernel.GetNamedPipeServerProcessId(handle,ctypes.byref(pid)) or pid.value<=0:
            raise PermissionError('Windows could not observe genuine pipe server PID')
        return int(pid.value)
    finally:
        kernel.CloseHandle(handle)


def open_authenticated_read_only_session(*_args,**_kwargs):
    """Production-safe denial until trusted native Windows broker is wired.

    No client-picked credential, process ID or EFS/SCM receipt may authorize
    a Lu session. The future implementation must link real OS package and
    signer witnesses to the LuCore named-pipe client and enrolled HMAC key.
    """
    raise PermissionError('Installed signed Lu broker + read-only health session not integrated')
