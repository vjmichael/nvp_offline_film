"""Independent POST-01F AppContainer/Job/release-fence exit check.

Separate from W1-G's WindowsJobProcess verifier, which intentionally does NOT
accept the AppContainer wrapper. A physical SCM/WFP witness must still prove
no egress, token identity, GPU provenance and installed release ownership.
"""
from __future__ import annotations

from hashlib import sha256
import os


def verified_ltx_appcontainer_exit(proc) -> dict:
    if os.name != "nt":
        raise PermissionError("Real Windows AppContainer kernel evidence required")
    from backend.nvp_g03_windows_appcontainer import AppContainerJobProcess
    from backend.nvp_worker_containment import WindowsJobProcess
    if (type(proc) is not AppContainerJobProcess or
        getattr(proc, "sandbox_identity", None) != "windows-appcontainer-with-zero-network-capabilities" or
        type(getattr(proc, "_worker", None)) is not WindowsJobProcess):
        raise PermissionError("Only original AppContainer-owned Job process is acceptable")
    wrapped = proc._worker
    pid = proc.pid
    if (type(pid) is not int or pid <= 0 or wrapped.pid != pid or
        wrapped._job is None or wrapped._release_slot is None or
        wrapped._original_journal is None or proc.poll() is None or
        not isinstance(getattr(proc, "_sid", None), str) or
        not proc._sid.startswith("S-1-15-2-")):
        raise RuntimeError("Original Windows Job, journal and AppContainer SID required")
    import win32job
    info = win32job.QueryInformationJobObject(
        wrapped._job, win32job.JobObjectBasicAccountingInformation)
    active = info.get("ActiveProcesses")
    if type(active) is not int or active < 0:
        raise RuntimeError("Kernel accounting of AppContainer process tree absent")
    sid_sha = sha256(proc._sid.encode("ascii")).hexdigest()
    # close() independently queries/terminates all descendants and verifies
    # profile inventory, ACL rollback and release-wide Job fence closure.
    # A close() exception blocks picture publication.
    proc.close()
    if (proc._worker is not None or wrapped._job is not None or
        wrapped._release_slot is not None or wrapped._original_journal is not None):
        raise RuntimeError("AppContainer process/release fence did not close cleanly")
    return {
        "format": "nvp.post01f.windows_appcontainer_kernel_exit.v1",
        "worker_pid": pid,
        "appcontainer_sid_sha256": sid_sha,
        "os_provenance": "windows-appcontainer-job-original-release-fence",
        "process_tree_custody_verified": True,
        "kernel_job_tree_reaped": True,
        "appcontainer_profile_cleanup_verified": True,
        "release_fence_closed": True,
        "active_processes_at_worker_exit": active,
    }
