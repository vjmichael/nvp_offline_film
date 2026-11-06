"""NVP STACK-02C3: real OS memory measurements and conservative heavy-task admission.

Do not invent GPU free memory, assume model auto-unloads, or call VRAM a
general RAM pool. DXGI reports a per-process OS budget, Linux AMD DRM and
optional NVIDIA NVML report driver-global VRAM. Unknown => GPU job queued.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import ctypes
import math
import os
import re
import sys
import time

MIB=1024*1024


@dataclass(frozen=True)
class GPUResource:
    device_id: str
    name: str
    source: str
    budget_mb: int
    used_mb: int
    globally_measured: bool

    @property
    def free_mb(self):
        return max(0,self.budget_mb-self.used_mb)


@dataclass(frozen=True)
class ResourceSnapshot:
    sampled_at: float
    ram_total_mb: int | None
    ram_available_mb: int | None
    memory_psi_full10: float | None
    gpus: tuple[GPUResource,...]
    warnings: tuple[str,...]=()

    def public(self):
        d=asdict(self)
        d["gpus"]=[{**asdict(g),"free_mb":g.free_mb} for g in self.gpus]
        return d


def _linux_ram():
    values={}
    for line in Path("/proc/meminfo").read_text("ascii").splitlines():
        m=re.match(r"^(MemTotal|MemAvailable):\s+(\d+)\s+kB$",line)
        if m:values[m.group(1)]=int(m.group(2))//1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise OSError("Kernel RAM telemetry missing")
    return values["MemTotal"],values["MemAvailable"]


def _linux_pressure():
    try:
        row=next(x for x in Path("/proc/pressure/memory").read_text("ascii").splitlines()
                 if x.startswith("full "))
        m=re.search(r"avg10=([0-9.]+)",row)
        return float(m.group(1)) if m else None
    except (OSError,ValueError,StopIteration,AttributeError):
        return None


def _windows_ram():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_=[("dwLength",ctypes.c_ulong),("dwMemoryLoad",ctypes.c_ulong),
                  ("ullTotalPhys",ctypes.c_ulonglong),("ullAvailPhys",ctypes.c_ulonglong),
                  ("ullTotalPageFile",ctypes.c_ulonglong),("ullAvailPageFile",ctypes.c_ulonglong),
                  ("ullTotalVirtual",ctypes.c_ulonglong),("ullAvailVirtual",ctypes.c_ulonglong),
                  ("ullAvailExtendedVirtual",ctypes.c_ulonglong)]
    x=MEMORYSTATUSEX();x.dwLength=ctypes.sizeof(x)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(x)):
        raise OSError("GlobalMemoryStatusEx failed")
    return x.ullTotalPhys//MIB,x.ullAvailPhys//MIB


def _linux_amd_gpus():
    result=[]
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        t=card/"device"/"mem_info_vram_total"
        u=card/"device"/"mem_info_vram_used"
        if not t.is_file() or not u.is_file():continue
        try:
            total=int(t.read_text().strip())//MIB
            used=int(u.read_text().strip())//MIB
            if 0<total<=1048576 and 0<=used<=total:
                result.append(GPUResource(card.name,"AMD "+card.name,
                    "linux_drm_amdgpu_global",total,used,True))
        except (OSError,ValueError):pass
    return result


def _nvml_gpus():
    try:import pynvml
    except ImportError:return []
    try:
        pynvml.nvmlInit()
        result=[]
        for i in range(min(pynvml.nvmlDeviceGetCount(),16)):
            h=pynvml.nvmlDeviceGetHandleByIndex(i)
            m=pynvml.nvmlDeviceGetMemoryInfo(h)
            name=pynvml.nvmlDeviceGetName(h)
            if isinstance(name,bytes):name=name.decode("utf8",errors="replace")
            total=int(m.total)//MIB;used=int(m.used)//MIB
            if total>0 and 0<=used<=total:
                result.append(GPUResource(f"nvidia:{i}",str(name)[:100],
                    "nvml_global",total,used,True))
        return result
    except Exception:return []
    finally:
        try:pynvml.nvmlShutdown()
        except Exception:pass


def _windows_dxgi_gpus():
    """Thin ctypes wrapper for IDXGIAdapter3.QueryVideoMemoryInfo(LOCAL).

    QueryVideoMemoryInfo.Budget/CurrentUsage describe THIS PROCESS budget
    and use, not globally measured free VRAM. NVP reserves extra headroom
    and labels this limited sensor honestly in the UI.
    """
    if sys.platform!="win32":return []
    from uuid import UUID
    class GUID(ctypes.Structure):
        _fields_=[("Data1",ctypes.c_uint32),("Data2",ctypes.c_uint16),
                  ("Data3",ctypes.c_uint16),("Data4",ctypes.c_ubyte*8)]
        @classmethod
        def parse(cls,text):
            return cls.from_buffer_copy(UUID(text).bytes_le)
    class INFO(ctypes.Structure):
        _fields_=[("Budget",ctypes.c_uint64),("CurrentUsage",ctypes.c_uint64),
                  ("AvailableForReservation",ctypes.c_uint64),
                  ("CurrentReservation",ctypes.c_uint64)]
    class DESC(ctypes.Structure):
        _fields_=[("Description",ctypes.c_wchar*128),("VendorId",ctypes.c_uint),
                  ("DeviceId",ctypes.c_uint),("SubSysId",ctypes.c_uint),
                  ("Revision",ctypes.c_uint),("DedicatedVideoMemory",ctypes.c_size_t),
                  ("DedicatedSystemMemory",ctypes.c_size_t),
                  ("SharedSystemMemory",ctypes.c_size_t),
                  ("AdapterLuid",ctypes.c_int64),("Flags",ctypes.c_uint)]
    def fn(ptr,index,result,*argtypes):
        table=ctypes.cast(ptr,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method=ctypes.WINFUNCTYPE(result,ctypes.c_void_p,*argtypes)(table[index])
        return lambda *args:method(ptr,*args)
    def release(ptr):
        if ptr:fn(ptr,2,ctypes.c_ulong)()
    dxgi=ctypes.WinDLL("dxgi.dll")
    create=dxgi.CreateDXGIFactory1
    create.argtypes=[ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
    create.restype=ctypes.c_long
    factory=ctypes.c_void_p()
    if create(ctypes.byref(GUID.parse("770AAE78-F26F-4DBA-A829-253C83D1B387")),
              ctypes.byref(factory))<0:return []
    result=[]
    try:
        for index in range(16):
            adapter=ctypes.c_void_p()
            if fn(factory,12,ctypes.c_long,ctypes.c_uint,
                  ctypes.POINTER(ctypes.c_void_p))(index,ctypes.byref(adapter))<0:break
            try:
                desc=DESC()
                if fn(adapter,10,ctypes.c_long,ctypes.POINTER(DESC))(ctypes.byref(desc))<0:continue
                if not desc.DedicatedVideoMemory or desc.Flags&2:continue
                advanced=ctypes.c_void_p()
                if fn(adapter,0,ctypes.c_long,ctypes.POINTER(GUID),
                      ctypes.POINTER(ctypes.c_void_p))(
                          ctypes.byref(GUID.parse("645967A4-1392-4310-A798-8053CE3E93FD")),
                          ctypes.byref(advanced))<0:continue
                try:
                    info=INFO()
                    if fn(advanced,14,ctypes.c_long,ctypes.c_uint,
                          ctypes.c_uint,ctypes.POINTER(INFO))(0,0,ctypes.byref(info))>=0:
                        if 0<info.Budget<2**60:
                            result.append(GPUResource(f"dxgi:{index}",
                                desc.Description.strip()[:100],
                                "windows_dxgi_process_budget",
                                int(info.Budget//MIB),int(info.CurrentUsage//MIB),False))
                finally:release(advanced)
            finally:release(adapter)
    finally:release(factory)
    return result


def collect_resources():
    warnings=[];total=available=None
    try:
        if sys.platform=="linux":total,available=_linux_ram()
        elif sys.platform=="win32":total,available=_windows_ram()
        else:warnings.append("Unsupported RAM sensor OS")
    except Exception:warnings.append("RAM availability could not be verified")
    gpus=[]
    try:
        if sys.platform=="linux":gpus.extend(_linux_amd_gpus())
        elif sys.platform=="win32":gpus.extend(_windows_dxgi_gpus())
        gpus.extend(_nvml_gpus())
    except Exception:warnings.append("GPU memory telemetry unavailable")
    if not gpus:warnings.append("No verified GPU memory budget; GPU work will queue")
    return ResourceSnapshot(time.time(),total,available,
        _linux_pressure() if sys.platform=="linux" else None,
        tuple(gpus),tuple(warnings))


def _bounded_int(x):
    return type(x) is int and 0<=x<=65536


@dataclass(frozen=True)
class AdmissionRequest:
    task_id:str
    kind:str
    title:str
    ram_mb:int
    gpu_mb:int=0
    device_id:str|None=None

    def __post_init__(self):
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}",self.task_id)
            or self.kind not in ("blender","ai_loading","ai_running","ai_unloading",
                                 "compositing","encoding","other")
            or not isinstance(self.title,str) or not 1<=len(self.title)<=120
            or not _bounded_int(self.ram_mb) or not self.ram_mb
            or not _bounded_int(self.gpu_mb)
            or self.gpu_mb>0 and not self.device_id
            or self.device_id is not None and
                not re.fullmatch(r"[A-Za-z0-9:_.-]{1,64}",self.device_id)):
            raise ValueError("Invalid trusted NVP memory request")


def decide_admission(snapshot:ResourceSnapshot,request:AdmissionRequest,
                     reserved_ram_mb=0,reserved_gpu_mb=0):
    if not _bounded_int(reserved_ram_mb) or not _bounded_int(reserved_gpu_mb):
        raise ValueError("Invalid resource reservation")
    if snapshot.ram_total_mb is None or snapshot.ram_available_mb is None:
        return False,"RAM availability cannot be verified",{"ram_margin_mb":None,"gpu_margin_mb":None}
    margin_ram=max(2048,math.ceil(snapshot.ram_total_mb*.20))
    if snapshot.memory_psi_full10 is not None and snapshot.memory_psi_full10>=5:
        return False,"Memory stalls detected; NVP is holding heavy work",{"ram_margin_mb":margin_ram,"gpu_margin_mb":None}
    if snapshot.ram_available_mb-reserved_ram_mb-request.ram_mb<margin_ram:
        return False,f"Waiting for RAM headroom (keep {margin_ram} MiB free)",{"ram_margin_mb":margin_ram,"gpu_margin_mb":None}
    margin_gpu=None
    if request.gpu_mb:
        gpu=next((g for g in snapshot.gpus if g.device_id==request.device_id),None)
        if gpu is None:
            return False,"Selected GPU memory budget unknown; job not started",{"ram_margin_mb":margin_ram,"gpu_margin_mb":None}
        margin_gpu=max(1024,math.ceil(gpu.budget_mb*.20))
        if gpu.free_mb-reserved_gpu_mb-request.gpu_mb<margin_gpu:
            return False,"Waiting for GPU memory headroom",{"ram_margin_mb":margin_ram,"gpu_margin_mb":margin_gpu}
    return True,"Safe within currently measured budget",{"ram_margin_mb":margin_ram,"gpu_margin_mb":margin_gpu}


def emergency_pressure(snapshot:ResourceSnapshot,*,gpu_device=None):
    """Two consecutive samples required by caller before terminating own work."""
    if snapshot.ram_total_mb is None or snapshot.ram_available_mb is None:
        return "RAM sensor failed during heavy work"
    if snapshot.ram_available_mb<max(1024,math.ceil(snapshot.ram_total_mb*.08)):
        return "Critical RAM pressure; stopping NVP worker to protect desktop"
    if snapshot.memory_psi_full10 is not None and snapshot.memory_psi_full10>=15:
        return "Critical memory stall pressure; stopping NVP worker"
    if gpu_device:
        gpu=next((g for g in snapshot.gpus if g.device_id==gpu_device),None)
        if gpu is None:return "GPU budget sensor failed during GPU work"
        if gpu.free_mb<max(512,math.ceil(gpu.budget_mb*.08)):
            return "GPU budget critically low; stopping NVP GPU work"
    return None
