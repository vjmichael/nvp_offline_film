"""STACK-02B: OS worker containment using existing kernel/process APIs.

Windows: pywin32 CREATE_SUSPENDED -> memory-limited Job Object -> assign ->
ResumeThread. Kill-on-close prevents child/grandchild escape if NVP crashes.
Linux: PR_SET_PDEATHSIG via exec shim; kills direct child on supervising
thread/process death. Does not imply orphaned grandchildren are killed.
Linux RLIMIT_AS caps virtual address space, not physical RSS or VRAM.
Containment API errors fail closed; there is no uncontained Popen fallback.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


class LinuxContainedProcess:
    def __init__(self, proc):
        self._proc = proc
        self.pid = proc.pid

    @property
    def returncode(self):
        return self._proc.returncode

    def poll(self):
        return self._proc.poll()

    def wait(self, timeout=None):
        return self._proc.wait(timeout=timeout)

    def terminate_tree(self):
        if self.poll() is None:
            import signal
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.wait(timeout=15)

    def close(self):
        if self.poll() is None:
            self.terminate_tree()


class WindowsJobProcess:
    def __init__(self, job, process, pid):
        self._job = job
        self._process = process
        self.pid = pid
        self.returncode = None

    def poll(self):
        import win32event
        import win32process
        if self.returncode is not None:
            return self.returncode
        if win32event.WaitForSingleObject(self._process, 0) == win32event.WAIT_OBJECT_0:
            code = win32process.GetExitCodeProcess(self._process)
            self.returncode = code if code < 0x80000000 else code - 0x100000000
        return self.returncode

    def wait(self, timeout=None):
        import win32event
        millis = win32event.INFINITE if timeout is None else max(0, min(int(timeout * 1000), 0xFFFFFFFE))
        if win32event.WaitForSingleObject(self._process, millis) != win32event.WAIT_OBJECT_0:
            raise subprocess.TimeoutExpired("Windows Job Object child", timeout)
        return self.poll()

    def terminate_tree(self):
        import win32job
        if self._job is not None:
            win32job.TerminateJobObject(self._job, 13)
        self.wait(timeout=15)

    def close(self):
        # Kill-on-close applies even if the direct Blender process has exited
        # and grandchildren still exist in the same job.
        if self._job is not None:
            self._job.Close()
            self._job = None
        if self._process is not None:
            self._process.Close()
            self._process = None


def launch_contained(command, *, cwd, stdout, stderr, memory_mb=0, linux_cgroup_tree_required=False,
                     linux_write_spool=None):
    """Trusted host launches pinned absolute executable with OS containment."""
    if not isinstance(command, list) or not command or not Path(command[0]).is_absolute():
        raise ValueError("Containment requires an absolute executable path")
    if type(memory_mb) is not int or not 0 <= memory_mb <= 65536:
        raise ValueError("Invalid OS memory limit")
    if type(linux_cgroup_tree_required) is not bool:
        raise ValueError("Linux whole-tree containment mode must be boolean")
    if linux_write_spool is not None and not linux_cgroup_tree_required:
        raise ValueError("Original-device write sandbox requires strict cgroup custody")
    if os.name == "nt":
        return _launch_windows(command, cwd=cwd, stdout=stdout, stderr=stderr, memory_mb=memory_mb)
    if sys.platform == "linux":
        if linux_cgroup_tree_required:
            from backend.nvp_worker_linux_cgroup import launch_cgroup_tree
            return launch_cgroup_tree(command,cwd=cwd,stdout=stdout,stderr=stderr,
                                      memory_mb=memory_mb,linux_write_spool=linux_write_spool)
        shim = Path(__file__).with_name("nvp_worker_linux_launcher.py").resolve()
        command = [sys.executable, str(shim), "--parent", str(os.getpid()),
                   "--memory-mb", str(memory_mb)] + command
        proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=stdout, stderr=stderr, shell=False, close_fds=True,
                                start_new_session=True)
        return LinuxContainedProcess(proc)
    raise RuntimeError("Unsupported OS containment platform")


def _launch_windows(command, *, cwd, stdout, stderr, memory_mb):
    """Suspended Win32 creation: no Blender instruction runs outside the job."""
    import msvcrt
    import win32job
    import win32process
    import uuid

    job = win32job.CreateJobObject(None, "NVP-Worker-"+uuid.uuid4().hex)
    info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    basic = info["BasicLimitInformation"]
    basic["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if memory_mb:
        basic["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
        info["JobMemoryLimit"] = memory_mb * 1024 * 1024
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)

    nul = open("NUL", "rb", buffering=0)
    handles = (msvcrt.get_osfhandle(nul.fileno()),
               msvcrt.get_osfhandle(stdout.fileno()),
               msvcrt.get_osfhandle(stderr.fileno()))
    previous = [os.get_handle_inheritable(h) for h in handles]
    try:
        for h in handles:
            os.set_handle_inheritable(h, True)
        startup = win32process.STARTUPINFO()
        startup.dwFlags |= win32process.STARTF_USESTDHANDLES
        startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
        flags = win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW
        ph, th, pid, _ = win32process.CreateProcess(
            command[0], subprocess.list2cmdline(command), None, None,
            True, flags, None, str(cwd), startup)
        try:
            win32job.AssignProcessToJobObject(job, ph)
            if not win32job.IsProcessInJob(ph, job):
                raise RuntimeError("Suspended Blender process not assigned to Job Object")
            if win32process.ResumeThread(th) == 0xFFFFFFFF:
                raise RuntimeError("Contained child could not be resumed")
            return WindowsJobProcess(job, ph, pid)
        except BaseException:
            try:
                win32job.TerminateJobObject(job, 13)
            except Exception:
                pass
            ph.Close()
            raise
        finally:
            th.Close()
    except BaseException:
        job.Close()
        raise
    finally:
        for handle, inheritable in zip(handles, previous):
            os.set_handle_inheritable(handle, inheritable)
        nul.close()
