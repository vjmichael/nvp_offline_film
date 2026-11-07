"""WO2 Windows GPU-device evidence, without guessing physical acceptance.

Win32 EnumDisplayDevicesW is a native OS enumeration, NOT GPU-frame proof.
A WebGL unmasked-renderer string is another observation, not a trusted
hardware ID; the two must never be conflated or used to fake calibration.
"""
from __future__ import annotations

import os
import platform

FORMAT="nvp.wo2.windows_gpu_adapter_evidence.v1"


def collect_windows_gpu_evidence():
    base={
        "format":FORMAT,
        "platform":platform.system(),
        "source":"Win32.EnumDisplayDevicesW",
        "adapters":[],
        "os_adapter_enumeration_succeeded":False,
        "hardware_gpu_frame_verified":False,
        "installed_webview2_pixel_readback_verified":False,
        "physical_display_calibrated":False,
        "render_delegate_hydra_parity_accepted":False,
    }
    if os.name!="nt":
        return {**base,"status":"NATIVE_WINDOWS_HARDWARE_UNAVAILABLE"}
    import ctypes
    from ctypes import wintypes
    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_=[
            ("cb",wintypes.DWORD),
            ("DeviceName",wintypes.WCHAR*32),
            ("DeviceString",wintypes.WCHAR*128),
            ("StateFlags",wintypes.DWORD),
            ("DeviceID",wintypes.WCHAR*128),
            ("DeviceKey",wintypes.WCHAR*128),
        ]
    enum=ctypes.windll.user32.EnumDisplayDevicesW
    enum.argtypes=[
        wintypes.LPCWSTR,wintypes.DWORD,
        ctypes.POINTER(DISPLAY_DEVICEW),wintypes.DWORD]
    enum.restype=wintypes.BOOL
    adapters=[]
    for i in range(32):
        device=DISPLAY_DEVICEW()
        device.cb=ctypes.sizeof(DISPLAY_DEVICEW)
        if not enum(None,i,ctypes.byref(device),0):
            break
        adapters.append({
            "name":str(device.DeviceString)[:128],
            "active":bool(device.StateFlags&1),
            "primary":bool(device.StateFlags&4),
            "software_name_detected":any(
                word in device.DeviceString.lower()
                for word in ("basic render","warp","software","swiftshader",
                             "remote display")),
        })
    return {**base,"status":(
                "OS_ADAPTERS_ENUMERATED_UNVERIFIED"
                if adapters else "NO_WINDOWS_DISPLAY_ADAPTERS"),
            "adapters":adapters,
            "os_adapter_enumeration_succeeded":bool(adapters)}
