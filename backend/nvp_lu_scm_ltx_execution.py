"""NVP Lu-connected LTX: original SCM-only execution and read-only exit scope.

Source checks do not attest an installed service. A fixed signed CNG receipt
and independent Lu worker-stop verifier are mandatory beyond this boundary.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import sys

from backend.nvp_post01f_scm_cng_v2 import KERNEL_FORMAT

_JOB = re.compile(r"ltx_[0-9a-f]{24}\Z")
_PROJECT = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset((
    "format", "job_id", "project_id", "plan_sha256",
    "worker_pid", "appcontainer_sid_sha256", "scm_owned_job",
    "scm_service_custody_verified", "kernel_job_tree_reaped",
    "release_fence_closed",
))


def require_installed_scm_stage(runtime_root: Path, *,
                                max_memory_mb: int, timeout_s: int,
                                scm_owned_launch, scm_owned_cancel) -> None:
    """Forbid a second Python Job or caller-selected stage for borrowed Lu VRAM."""
    if os.name != "nt" or sys.platform != "win32":
        raise PermissionError("Lu GPU lease needs installed Windows SCM custody")
    if not callable(scm_owned_launch) or not callable(scm_owned_cancel):
        raise PermissionError("Original installed SCM start/stop authority is required")
    # Native broker is hard-pinned to this machine-known-folder stage.
    from backend.nvp_post01f_installed_receipt_transport import (
        _program_data, _attributes, _FILE_ATTRIBUTE_DIRECTORY,
    )
    parent = _program_data()
    for part in ("NVP", "POST01F", "ApprovedJobs"):
        parent = parent / part
        # Native GetFileAttributesW refuses junction/reparse points, not
        # merely Python symbolic links on the final directory.
        if not (_attributes(parent) & _FILE_ATTRIBUTE_DIRECTORY):
            raise PermissionError("Original installed SCM stage directory missing")
    fixed = parent
    root = Path(runtime_root)
    if (not root.is_absolute() or root != fixed or root.is_symlink() or
            root.resolve(strict=True) != fixed.resolve(strict=True)):
        raise PermissionError("Lu-linked LTX must use exact protected SCM ApprovedJobs stage")
    # Source limits must not diverge from the fixed original C++ SCM broker.
    if max_memory_mb != 24576 or timeout_s != 3600:
        raise PermissionError("SCM-connected LTX memory/deadline differs from native broker")


def verify_original_scm_kernel_result(native: dict, *, job_id: str,
                                      project_id: str, plan_sha256: str) -> dict:
    """Validate shape before independent signer verification, never as proof."""
    if (type(native) is not dict or set(native) != _FIELDS or
            type(job_id) is not str or not _JOB.fullmatch(job_id) or
            type(project_id) is not str or not _PROJECT.fullmatch(project_id) or
            type(plan_sha256) is not str or not _SHA.fullmatch(plan_sha256) or
            native.get("format") != KERNEL_FORMAT or
            native.get("job_id") != job_id or
            native.get("project_id") != project_id or
            native.get("plan_sha256") != plan_sha256 or
            type(native.get("worker_pid")) is not int or native["worker_pid"] <= 0 or
            type(native.get("appcontainer_sid_sha256")) is not str or
            not _SHA.fullmatch(native["appcontainer_sid_sha256"]) or
            any(native.get(k) is not True for k in (
                "scm_owned_job", "scm_service_custody_verified",
                "kernel_job_tree_reaped", "release_fence_closed"))):
        raise PermissionError("Foreign or unverified original SCM Job identity")
    # This is NOT signature verification. The installed CNG/EFS receipt channel
    # independently authenticates job/plan/PID/SID before picture acceptance.
    return dict(native)
