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
    def __init__(self, job, process, pid, release_slot=None, original_journal=None):
        self._job = job
        self._process = process
        self._release_slot = release_slot
        self._original_journal = original_journal
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
        # A release-wide worker slot is retained until ORIGINAL kernel job
        # accounting proves the whole process tree empty. No PID-only
        # clearance, and no early release of the update admission fence.
        if self._job is not None:
            import time
            import win32job
            info = win32job.QueryInformationJobObject(
                self._job, win32job.JobObjectBasicAccountingInformation)
            if info["ActiveProcesses"]:
                win32job.TerminateJobObject(self._job, 13)
            deadline = time.monotonic() + 12.0
            while True:
                info = win32job.QueryInformationJobObject(
                    self._job, win32job.JobObjectBasicAccountingInformation)
                if type(info["ActiveProcesses"]) is int and info["ActiveProcesses"] == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("Windows Job Object still owns live descendants")
                time.sleep(.05)
            self._job.Close()
            self._job = None
        if self._process is not None:
            self._process.Close()
            self._process = None
        if self._original_journal is not None:
            # The actual original Job Object has been closed only after
            # kernel accounting proved no descendants. Never clear a
            # PREPARED/RUNNING crash journal using a stale PID observation.
            self._original_journal.verified_tree_reaped()
            self._original_journal = None
        if self._release_slot is not None:
            self._release_slot.release()
            self._release_slot = None


def launch_contained(command, *, cwd, stdout, stderr, memory_mb=0, linux_cgroup_tree_required=False, private_isolation_required=False, stdin=None, linux_write_spool=None, env=None, windows_appcontainer_required=False, appcontainer_code_roots=(), appcontainer_code_files=()):
    """Trusted host launches pinned absolute executable with OS containment."""
    if not isinstance(command, list) or not command or not Path(command[0]).is_absolute():
        raise ValueError("Containment requires an absolute executable path")
    if type(memory_mb) is not int or not 0 <= memory_mb <= 65536:
        raise ValueError("Invalid OS memory limit")
    if type(linux_cgroup_tree_required) is not bool:
        raise ValueError("Linux whole-tree containment mode must be boolean")
    if linux_write_spool is not None and not linux_cgroup_tree_required:
        raise ValueError("Original-device write sandbox requires strict cgroup custody")
    if type(private_isolation_required) is not bool:
        raise ValueError("Private source isolation mode must be boolean")
    if type(windows_appcontainer_required) is not bool:
        raise ValueError("Windows AppContainer requirement must be boolean")
    if not windows_appcontainer_required and (appcontainer_code_roots or appcontainer_code_files):
        raise PermissionError("AppContainer source grants require real kernel isolation")
    if env is not None and (type(env) is not dict or any(
            type(k) is not str or type(v) is not str or
            "\0" in k or "\0" in v for k,v in env.items())):
        raise ValueError("Invalid native worker environment")
    if windows_appcontainer_required:
        if (os.name!="nt" or linux_cgroup_tree_required or
                private_isolation_required or linux_write_spool is not None):
            raise RuntimeError("Original AppContainer requires an independent Windows kernel boundary")
        # The AppContainer has its own Job; it must ALSO participate in W1-G's
        # shared native-worker release fence and immutable process journal.
        from backend.nvp_w1g_release_gate import (
            WindowsWorkerLifetimeSlot, OriginalWindowsLaunchJournal)
        from backend.nvp_g03_windows_appcontainer import launch_appcontainer
        slot=WindowsWorkerLifetimeSlot().acquire()
        try:
            journal=OriginalWindowsLaunchJournal(command)
            return launch_appcontainer(
                command,cwd=cwd,stdin=stdin,stdout=stdout,stderr=stderr,
                memory_mb=memory_mb,env=env,code_roots=appcontainer_code_roots,
                code_files=appcontainer_code_files,release_slot=slot,
                original_journal=journal)
        except BaseException:
            slot.release()
            raise
    if private_isolation_required:
        if not linux_cgroup_tree_required:
            raise RuntimeError("Private Blender cannot run without kernel whole-tree custody")
        from backend.nvp_worker_private_sandbox import sandbox_command
        # This is a real OS namespace execution contract. A Windows Job Object
        # without AppContainer/WFP is NOT a filesystem/no-egress sandbox.
        command=sandbox_command(command,cwd)["command"]
    if os.name == "nt":
        return _launch_windows(command, cwd=cwd, stdout=stdout, stderr=stderr, memory_mb=memory_mb, stdin=stdin, env=env)
    if sys.platform == "linux":
        if linux_cgroup_tree_required and (stdin is not None or env is not None):
            raise RuntimeError("Delegated Linux worker does not support unreviewed native stdin or environment transport")
        if linux_cgroup_tree_required:
            from backend.nvp_worker_linux_cgroup import launch_cgroup_tree
            return launch_cgroup_tree(command,cwd=cwd,stdout=stdout,stderr=stderr,
                                      memory_mb=memory_mb,linux_write_spool=linux_write_spool)
        shim = Path(__file__).with_name("nvp_worker_linux_launcher.py").resolve()
        command = [sys.executable, str(shim), "--parent", str(os.getpid()),
                   "--memory-mb", str(memory_mb)] + command
        proc = subprocess.Popen(command, cwd=cwd, stdin=stdin if stdin is not None else subprocess.DEVNULL,
                                stdout=stdout, stderr=stderr, env=env, shell=False, close_fds=True,
                                start_new_session=True)
        return LinuxContainedProcess(proc)
    raise RuntimeError("Unsupported OS containment platform")


def _launch_windows(command, *, cwd, stdout, stderr, memory_mb, stdin=None, env=None):
    """Suspended Win32 creation: no Blender instruction runs outside the job."""
    import msvcrt
    import win32job
    import win32process
    import uuid
    from backend.nvp_w1g_release_gate import WindowsWorkerLifetimeSlot, OriginalWindowsLaunchJournal

    # Reserve the release-wide kernel slot BEFORE CreateProcess, so an NSIS
    # mutation cannot pass its all-slots test while this child is starting.
    slot = WindowsWorkerLifetimeSlot().acquire()
    try:
        original_journal=OriginalWindowsLaunchJournal(command)
        return _launch_windows_owned(command, cwd=cwd, stdout=stdout,
                                    stderr=stderr, memory_mb=memory_mb,
                                    slot=slot, stdin=stdin, journal=original_journal, env=env)
    except BaseException:
        slot.release()
        raise


def _launch_windows_owned(command, *, cwd, stdout, stderr, memory_mb, slot, stdin=None, journal=None, env=None):
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
    handles = (msvcrt.get_osfhandle((stdin if stdin is not None else nul).fileno()),
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
        if env is not None:
            flags |= win32process.CREATE_UNICODE_ENVIRONMENT
        ph, th, pid, _ = win32process.CreateProcess(
            command[0], subprocess.list2cmdline(command), None, None,
            True, flags, env, str(cwd), startup)
        try:
            win32job.AssignProcessToJobObject(job, ph)
            if not win32job.IsProcessInJob(ph, job):
                raise RuntimeError("Suspended Blender process not assigned to Job Object")
            if win32process.ResumeThread(th) == 0xFFFFFFFF:
                raise RuntimeError("Contained child could not be resumed")
            # A failure to durably mark RUNNING terminates the original Job,
            # leaving PREPARED as an operator-visible uncertainty blocker.
            journal.started(pid)
            return WindowsJobProcess(job, ph, pid, release_slot=slot,
                                     original_journal=journal)
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
