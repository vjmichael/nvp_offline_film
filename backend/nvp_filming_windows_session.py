"""DA-03/W1-G original filming session: genuine Windows Job custody + release fence.

The retired OwnedFilmingWorker only attested a *direct Popen child*. Production
Windows recording must use launch_windows_filming_session, which holds the
original filming journal's kernel WorkerHostLease plus central release-wide
lifetime slot and the original suspended/assigned Windows Job Object.

Freeze/publish owns the session's exclusive host lease until the source
snapshot and immutable Take are committed or rejected; never reconstruct
permission from a persisted PID, prior Job handle, or synthetic receipt.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import subprocess
import time

from backend.nvp_worker_containment import WindowsJobProcess, launch_contained
from backend.nvp_worker_host_lease import WorkerHostLease


class WindowsFilmingSession:
    def __init__(self, process: WindowsJobProcess, owner_lease: WorkerHostLease):
        if os.name != "nt":
            raise RuntimeError("Native original Windows filming requires Windows kernel")
        if (type(process) is not WindowsJobProcess or
            process._job is None or
            process._release_slot is None or
            type(owner_lease) is not WorkerHostLease or owner_lease.fd is None):
            raise TypeError("Original Job Object, live release slot and filming lease required")
        self.process=process
        self.owner_lease=owner_lease
        self._stopped=False
        self._closed=False

    def stop_and_verify(self, *, timeout=5.0):
        if self._closed or self._stopped:
            raise RuntimeError("Original Windows filming stop receipt was already consumed")
        if (type(timeout) not in (int,float) or
            type(timeout) is bool or
            not math.isfinite(timeout) or
            not 0 < timeout <= 60):
            raise ValueError("Bounded positive original filming stop timeout required")
        import win32job
        import win32process
        started=time.monotonic()
        proc=self.process
        # The retained original Job handle, not a PID or an injected bool,
        # is the only authority to stop *every* original recording descendant.
        if proc._job is None:
            raise RuntimeError("Original filming Windows Job Object was revoked")
        if proc.poll() is None:
            win32job.TerminateJobObject(proc._job,13)
        remaining=max(0.0,timeout-(time.monotonic()-started))
        try:
            code=proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Original filming direct-child reap timeout") from exc
        info=win32job.QueryInformationJobObject(
            proc._job,win32job.JobObjectBasicAccountingInformation)
        if (type(info.get("ActiveProcesses")) is not int or
            info["ActiveProcesses"]!=0):
            raise RuntimeError("Original Windows filming still owns live descendants")
        proc.close()  # Also re-verifies Job accounting before slot release.
        if time.monotonic()-started>timeout:
            raise RuntimeError("Original filming kernel/reap deadline exceeded")
        self._stopped=True
        return {
            "scope":"windows-job-object",
            "process_tree_custody_verified":True,
            "active_windows_jobs":0,
            "empty_group_verified":True,
            "worker_exit_verified":True,
            "worker_pid":proc.pid,
            "worker_returncode":code,
            "release_wide_launch_fence_verified":True,
            "original_film_publication_committed":False,
        }

    def close(self):
        if self._closed:
            return
        # Never drop the publication lease while a worker is alive. A
        # failed kill must leave the release/admission lock held; external
        # upgrade is refused until the original host is crashed/reconciled.
        if self.process._job is not None:
            self.process.close()
        self._closed=True
        self.owner_lease.__exit__(None,None,None)

    def __enter__(self):
        return self

    def __exit__(self,kind,value,trace):
        self.close()
        return False


def launch_windows_filming_session(workspace:Path, command:list[str], *,
                                   cwd:Path, stdout, stderr,
                                   memory_mb:int=1024) -> WindowsFilmingSession:
    if os.name!="nt":
        raise RuntimeError("Production original Windows filming requires actual Windows")
    if (type(command) is not list or not command or
        any(type(x) is not str for x in command) or
        not Path(command[0]).is_absolute() or
        Path(command[0]).is_symlink() or
        type(memory_mb) is not int or
        not 128<=memory_mb<=32768):
        raise PermissionError("Pinned absolute original recording worker executable required")
    root=Path(workspace)
    if not root.is_dir() or root.is_symlink():
        raise PermissionError("Original filming journal workspace unavailable")
    lease=WorkerHostLease(root)
    lease.__enter__()
    try:
        proc=launch_contained(command,cwd=str(cwd),stdout=stdout,
                              stderr=stderr,memory_mb=memory_mb)
        try:
            return WindowsFilmingSession(proc,lease)
        except BaseException:
            proc.close()
            raise
    except BaseException:
        lease.__exit__(None,None,None)
        raise
