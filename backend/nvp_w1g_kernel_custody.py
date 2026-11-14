"""W1-G independent actual OS worker-tree cleanup witness.

No PID-only or user-provided Boolean can substitute for this check.
Windows: keep the job HANDLE open until the kernel reports zero active
processes, terminate descendants if needed, then close it. Linux: the
existing guardian kills its delegated cgroup and removes the leaf; require
a successful guardian exit and that the actual cgroup leaf disappeared.
"""
from __future__ import annotations

import os
from pathlib import Path
import time


def verified_native_worker_exit(proc):
    if os.name == "nt":
        from backend.nvp_worker_containment import WindowsJobProcess
        if type(proc) is not WindowsJobProcess or proc._job is None:
            raise RuntimeError("Kernel-owned Windows Job Object handle required")
        import win32job
        job = proc._job
        if proc.poll() is None:
            raise RuntimeError("Windows native worker itself has not exited")
        # The child may exit while its grandchildren remain running.
        # Kill-on-close alone does not establish a synchronous cleanup.
        accounting = win32job.QueryInformationJobObject(
            job, win32job.JobObjectBasicAccountingInformation)
        active = accounting["ActiveProcesses"]
        if type(active) is not int or active < 0:
            raise RuntimeError("Windows kernel job accounting unavailable")
        if active:
            win32job.TerminateJobObject(job, 12)
        deadline = time.monotonic() + 12.0
        while True:
            accounting = win32job.QueryInformationJobObject(
                job, win32job.JobObjectBasicAccountingInformation)
            if accounting["ActiveProcesses"] == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Windows kernel did not prove job process tree empty")
            time.sleep(0.05)
        pid = proc.pid
        proc.close()
        return {
            "os_provenance": "windows-job-object",
            "worker_pid": pid,
            "process_tree_custody_verified": True,
            "active_processes_at_close": 0,
            "kernel_wait_terminated_descendants": bool(active),
        }

    if os.name == "posix":
        from backend.nvp_worker_linux_cgroup import CgroupTreeProcess, CGROUP_MOUNT
        if type(proc) is not CgroupTreeProcess:
            raise RuntimeError("Strict delegated cgroup-v2 tree custody required")
        leaf = Path(proc.cgroup)
        mount = CGROUP_MOUNT.resolve()
        if (leaf.is_symlink() or not leaf.resolve().is_relative_to(mount) or
            not leaf.name.startswith("nvp-worker-") or
            not (leaf/"cgroup.events").is_file()):
            raise RuntimeError("Cannot verify original delegated Linux worker cgroup")
        if proc.poll() is None:
            raise RuntimeError("Native Linux worker itself has not exited")
        pid = proc.pid
        proc.close()  # Waits for original guardian to cgroup.kill+remove leaf.
        if (proc._guardian.returncode != 0 or leaf.exists() or leaf.is_symlink()):
            raise RuntimeError("Linux kernel/guardian cannot establish empty worker subtree")
        return {
            "os_provenance": "linux-cgroup-v2",
            "worker_pid": pid,
            "process_tree_custody_verified": True,
            "guardian_exit_verified": True,
            "cgroup_leaf_removed": True,
        }
    raise RuntimeError("Unsupported OS for protected native worker kernel receipt")
