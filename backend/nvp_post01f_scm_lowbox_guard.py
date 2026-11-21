"""Native-only SCM LTX child check before spawning its fixed media codecs.

This is an additional *self-denial* defense. The installer-owned SCM service
must still own the caller's AppContainer SID, WFP block filters, non-breakaway
Job Object, and one-use source/result authorization. Successful token/Job
inspection cannot independently prove SCM ownership or authenticate a film.
"""
from __future__ import annotations

import os


def require_current_scm_lowbox_job() -> None:
    """Refuse uncontained Windows media children before CreateProcess.

    A child launched from SCM's no-breakaway Job cannot escape that Job; its
    lowbox process token and WFP package constraints must remain inherited.
    The enclosing native SCM service verifies this independently and signs
    only after the entire Job tree has drained. No developer/test bypass.
    """
    if os.name != 'nt':
        return  # Unix is never an installed LTX worker; portable media tests only.
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE,
                                      ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.HANDLE)]
    security.OpenProcessToken.restype = wintypes.BOOL
    security.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD)]
    security.GetTokenInformation.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    proc = kernel.GetCurrentProcess()
    assigned = wintypes.BOOL(0)
    if not kernel.IsProcessInJob(proc, None, ctypes.byref(assigned)) or not assigned.value:
        raise PermissionError('LTX codec refused: SCM worker has no Windows Job Object')
    token = wintypes.HANDLE()
    if not security.OpenProcessToken(proc, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
        raise PermissionError('LTX codec refused: worker token cannot be inspected')
    try:
        is_lowbox = wintypes.DWORD()
        returned = wintypes.DWORD()
        # TOKEN_INFORMATION_CLASS::TokenIsAppContainer = 29
        if (not security.GetTokenInformation(token, 29, ctypes.byref(is_lowbox),
                   ctypes.sizeof(is_lowbox), ctypes.byref(returned))
                or returned.value != ctypes.sizeof(is_lowbox) or is_lowbox.value != 1):
            raise PermissionError('LTX codec refused: parent is not an AppContainer')
    finally:
        kernel.CloseHandle(token)
