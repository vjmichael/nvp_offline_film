"""WO6-06 genuine Windows Job Object identity and hard-crash stopped attestation.

A trusted native host persistently seals the exact unique Job name BEFORE
CreateProcess. The Windows containment launcher assigns a suspended worker to
that named object and applies JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE before
resuming it. On a hard host exit all handles close; the last close kills
the contained process tree. Recovery checks the kernel object, not a stale
PID file, cached flag, merely expired timeout or model-generated receipt.

Linux never uses this Windows guarantee. Delegated cgroup v2 requires its
own positive OS proof; unknown or unverified work remains ACTIVE.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import time

from backend.nvp_approved_tasks import canonical_bytes

FORMAT="nvp.wo6.win_job_generation.v1"
TASK_ID=re.compile(r"wo6(?:take|shot|data)_[0-9a-f]{24}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")


def immutable_job_name(task_id):
    if type(task_id) is not str or not TASK_ID.fullmatch(task_id):
        raise ValueError("Native WO6 task identifier required for kernel job")
    return "NVP-WO6-"+hashlib.sha256(task_id.encode("ascii")).hexdigest()[:32]


def persist_windows_job_identity(folder, *, task_id, spec_sha256, owner):
    """Host-owned generation must be durable before worker can exist."""
    if os.name!="nt":
        raise RuntimeError("Windows kernel identity unavailable on this OS")
    base=Path(folder)
    if (not base.is_absolute() or base.is_symlink() or
            not base.is_dir() or type(owner) is not str or not owner or
            type(spec_sha256) is not str or not SHA.fullmatch(spec_sha256)):
        raise PermissionError("Unsafe native WO6 Job Object generation location")
    document={
        "format":FORMAT,"task_id":task_id,
        "spec_sha256":spec_sha256,"owner":owner,
        "job_name":immutable_job_name(task_id),
        "kernel_proof":"WINDOWS_JOB_OBJECT_KILL_ON_LAST_HANDLE_CLOSE",
        "creator_approval_granted":False,
        "film_delivered":False,
    }
    raw=canonical_bytes(document)
    path=base/"windows_job_identity.json"
    if path.is_symlink() or path.exists():
        raise FileExistsError("A native worker generation cannot be reused")
    with path.open("xb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    return document["job_name"]


def attest_windows_job_stopped(folder, *, task_id, spec_sha256, owner):
    """Probe the actual named NT object. True ONLY if kernel name is absent."""
    if os.name!="nt":
        raise PermissionError("Cannot substitute process-group/PID tests for NT job proof")
    base=Path(folder)
    path=base/"windows_job_identity.json"
    if (not base.is_absolute() or base.is_symlink() or not base.is_dir() or
            path.is_symlink() or not path.is_file()):
        raise PermissionError("Missing durable prelaunch Job Object identity")
    raw=path.read_bytes()
    record=json.loads(raw)
    if (raw!=canonical_bytes(record) or record.get("format")!=FORMAT or
            record.get("task_id")!=task_id or
            record.get("owner")!=owner or
            record.get("spec_sha256")!=spec_sha256 or
            record.get("job_name")!=immutable_job_name(task_id) or
            record.get("kernel_proof")!=
            "WINDOWS_JOB_OBJECT_KILL_ON_LAST_HANDLE_CLOSE"):
        raise PermissionError("Worker generation identity was changed")
    kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
    open_job=kernel32.OpenJobObjectW
    open_job.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR)
    open_job.restype=wintypes.HANDLE
    kernel32.CloseHandle.argtypes=(wintypes.HANDLE,)
    kernel32.CloseHandle.restype=wintypes.BOOL
    ctypes.set_last_error(0)
    handle=open_job(0x0004,False,record["job_name"]) # JOB_OBJECT_QUERY
    if handle:
        kernel32.CloseHandle(handle)
        # An existing host or worker handle can still own live processes.
        return False
    error=ctypes.get_last_error()
    if error==2: # ERROR_FILE_NOT_FOUND: no named job object remains
        return True
    raise PermissionError(
        "Windows kernel Job Object absence not verified; error "+str(error))
