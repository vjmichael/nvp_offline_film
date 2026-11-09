"""P0-F-01 disposable installed Windows native OS-dialog test driver.

TEST-ONLY: sends explicit Yes/No to a genuine *same-process* Windows modal
message box in the throwaway --smoke-window mode. This is not real director
consent and MUST NEVER be called by the production WebView/AI bridge.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

TITLE="NVP — Approve Original Building World"
WM_COMMAND=0x0111
IDYES=6
IDNO=7


def drive_one_dialog(choice, *, timeout_seconds=25):
    if os.name!="nt" or sys.platform!="win32":
        raise RuntimeError("Only actual Windows native desktop dialog can be driven")
    if choice not in ("yes","no"):
        raise ValueError("Only test-owned explicit yes/no dialog choice")
    if not 1<=timeout_seconds<=60:
        raise ValueError("Bounded test modal window timeout required")
    user32=ctypes.WinDLL("user32",use_last_error=True)
    user32.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p]
    user32.FindWindowW.restype=ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes=[
        ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype=ctypes.c_ulong
    user32.PostMessageW.argtypes=[
        ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    user32.PostMessageW.restype=ctypes.c_int
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        hwnd=user32.FindWindowW("#32770",TITLE)
        if hwnd:
            pid=ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value!=os.getpid():
                raise PermissionError("Refusing to click another app's modal dialog")
            code=IDYES if choice=="yes" else IDNO
            if not user32.PostMessageW(hwnd,WM_COMMAND,code,0):
                raise OSError(ctypes.get_last_error(),
                              "Could not deliver Windows modal control")
            return {"dialog_title":TITLE,"os_process_id":pid.value,
                    "choice":choice,"real_native_windows_dialog_observed":True,
                    "human_director_consent":False}
        time.sleep(.05)
    raise TimeoutError("No genuine own-process NVP native confirmation dialog")


def start_disposable_dialog_driver(choice,*,timeout_seconds=25):
    """Starts one scoped test thread; caller MUST join/verify its receipt."""
    record={"receipt":None,"error":None}
    def worker():
        try:
            record["receipt"]=drive_one_dialog(
                choice,timeout_seconds=timeout_seconds)
        except BaseException as exc:
            record["error"]=exc
    thread=threading.Thread(
        target=worker,name="NVP-P0F01-test-only-Windows-modal-driver",
        daemon=True)
    thread.start()
    return thread,record


def finish_disposable_dialog_driver(thread,record,*,timeout_seconds=30):
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError("NVP test modal driver did not complete")
    if record["error"] is not None:
        raise record["error"]
    if not record["receipt"] or record["receipt"][
            "human_director_consent"] is not False:
        raise RuntimeError("No native test dialog receipt")
    return record["receipt"]
