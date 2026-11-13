"""STACK-02C2: strict delegated Linux cgroup v2 worker-tree containment.

This module does not create cgroups in arbitrary systemd-managed directories.
It uses only the kernel-reported *current* host cgroup, which must already be
delegated to NVP (e.g. Delegate=yes in a systemd service/scope). The worker
joins its dedicated leaf before exec, descendants inherit that leaf, and an
independent guardian outside the leaf writes cgroup.kill if the host dies.

No cgroup delegation -> fail closed. No detached-process cleanup assertion
based only on PR_SET_PDEATHSIG, process groups, or a simulated cgroup tree.
"""
from __future__ import annotations

import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

CGROUP_MOUNT = Path("/sys/fs/cgroup")
PREFIX = "nvp-worker-"


def current_cgroup_relative(pid="self"):
    source=Path(f"/proc/{pid}/cgroup")
    for row in source.read_text("utf8").splitlines():
        if row.startswith("0::"):
            relative=row[3:]
            if not relative.startswith("/") or ".." in Path(relative).parts:
                raise RuntimeError("Invalid kernel cgroup v2 membership")
            return relative
    raise RuntimeError("Linux unified cgroup v2 is not available")


def current_delegated_parent():
    """Use systemd's own delegation marker, NEVER a guessed systemd path.

    DelegateSubgroup= may place the host inside a child of the delegated
    scope. We may create NVP leaves under that *scope* (the marked ancestor),
    not under the host's process-filled subgroup.
    """
    mount=CGROUP_MOUNT.resolve()
    if not (mount/"cgroup.controllers").is_file():
        raise RuntimeError("No unified cgroup v2 kernel mount")
    current=(mount/current_cgroup_relative().lstrip("/")).resolve()
    if not current.is_relative_to(mount):
        raise RuntimeError("Kernel cgroup path escapes mounted hierarchy")
    for candidate in (current,*current.parents):
        if not candidate.is_relative_to(mount):
            break
        try:
            delegated=os.getxattr(candidate,"user.delegate")==b"1"
        except (OSError,AttributeError):
            delegated=False
        if delegated:
            if not os.access(candidate,os.W_OK|os.X_OK):
                raise RuntimeError("Systemd cgroup delegation is not writable by NVP")
            return candidate
    raise RuntimeError("No systemd Delegate=yes cgroup v2 scope found for NVP worker")


def provision_worker_cgroup(memory_mb, pids_max=128):
    """Require existing controller delegation; never change a parent cgroup."""
    if type(memory_mb) is not int or not 256<=memory_mb<=65536:
        raise ValueError("Strict cgroup memory cap must be 256..65536 MiB")
    if type(pids_max) is not int or not 16<=pids_max<=2048:
        raise ValueError("Strict cgroup process cap must be 16..2048")
    parent=current_delegated_parent()
    required={"memory","pids"}
    available=set((parent/"cgroup.controllers").read_text("ascii").split())
    if not required.issubset(available):
        raise RuntimeError("Delegated scope does not expose memory and pids controllers")
    enabled=set((parent/"cgroup.subtree_control").read_text("ascii").split())
    missing=required-enabled
    if missing:
        # Changing subtree_control inside the scope delegated to NVP is
        # permitted by systemd's single-writer contract. If systemd did
        # not place host tasks in DelegateSubgroup, the kernel will refuse
        # enabling domain controllers; NVP fails closed.
        try:
            (parent/"cgroup.subtree_control").write_text(
                " ".join("+"+item for item in sorted(missing)),encoding="ascii")
        except OSError as exc:
            raise RuntimeError("Cannot enable delegated cgroup memory/pids; configure DelegateSubgroup= for the host") from exc
        enabled=set((parent/"cgroup.subtree_control").read_text("ascii").split())
        if not required.issubset(enabled):
            raise RuntimeError("Kernel did not enable delegated memory/pids controllers")
    name=PREFIX+uuid.uuid4().hex
    path=parent/name
    try:
        path.mkdir(mode=0o700)
    except OSError as exc:
        raise RuntimeError("No writable NVP cgroup subtree; systemd Delegate=yes required") from exc
    try:
        for required in ("cgroup.kill","cgroup.procs","memory.max","pids.max","cgroup.events"):
            if not (path/required).is_file():
                raise RuntimeError(f"Delegated cgroup controller unavailable: {required}")
        (path/"memory.max").write_text(str(memory_mb*1024*1024),"ascii")
        (path/"pids.max").write_text(str(pids_max),"ascii")
        if int((path/"memory.max").read_text("ascii").strip())!=memory_mb*1024*1024:
            raise RuntimeError("Kernel cgroup memory cap was not applied")
        if int((path/"pids.max").read_text("ascii").strip())!=pids_max:
            raise RuntimeError("Kernel cgroup process cap was not applied")
        return path
    except Exception:
        try: path.rmdir()
        except OSError: pass
        raise


def _read_ready(fd,timeout,description):
    readable,_,_=select.select([fd],[],[],timeout)
    if not readable or os.read(fd,1)!=b"1":
        raise RuntimeError(description+" did not confirm kernel containment")


def cgroup_kill(path):
    (path/"cgroup.kill").write_text("1","ascii")


class CgroupTreeProcess:
    """One NVP Blender child and out-of-tree guardian, under one host lease."""
    def __init__(self,worker,guardian,watch_write,cgroup):
        self._worker=worker
        self._guardian=guardian
        self._watch_write=watch_write
        self.cgroup=Path(cgroup)
        self.pid=worker.pid

    @property
    def returncode(self):
        return self._worker.returncode

    def poll(self):
        if self._guardian.poll() is not None and self._worker.poll() is None:
            try: cgroup_kill(self.cgroup)
            finally: raise RuntimeError("Cgroup guardian died while Blender worker was still active")
        return self._worker.poll()

    def wait(self,timeout=None):
        return self._worker.wait(timeout=timeout)

    def terminate_tree(self):
        # cgroup.kill includes descendants even if they detached from the
        # original Blender process group or session.
        cgroup_kill(self.cgroup)
        self._worker.wait(timeout=15)

    def close(self):
        # Close the one host-held watch pipe. Guardian sees EOF when host
        # exits via os._exit as well; it kills all leftover descendants.
        if self._watch_write is not None:
            os.close(self._watch_write)
            self._watch_write=None
        try:
            self._guardian.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:cgroup_kill(self.cgroup)
            finally:raise RuntimeError("Cgroup guardian failed to finish cleanup")
        if self._guardian.returncode:
            raise RuntimeError("Cgroup guardian failed to prove worker-tree cleanup")
        if self._worker.poll() is None:
            self._worker.wait(timeout=15)


def launch_cgroup_tree(command,*,cwd,stdout,stderr,memory_mb,linux_write_spool=None):
    """Start guardian FIRST, and only launch Blender after guardian READY."""
    if sys.platform!="linux" or os.name!="posix":
        raise RuntimeError("Linux kernel cgroup v2 mode is unavailable on this OS")
    if not command or not Path(command[0]).is_absolute():
        raise ValueError("Pinned worker executable must be absolute")
    if linux_write_spool is not None:
        source=Path(linux_write_spool)
        if (not source.is_absolute() or source.is_symlink() or
            not source.is_dir() or
            not source.name.startswith("nvp-live-original-")):
            raise PermissionError("Cannot authorize an arbitrary Linux worker write scope")
    target=provision_worker_cgroup(memory_mb)
    watch_r,watch_w=os.pipe()
    ready_r,ready_w=os.pipe()
    guardian=None
    worker=None
    try:
        guardian_path=Path(__file__).with_name("nvp_worker_cgroup_guardian.py").resolve()
        guardian=subprocess.Popen([
            sys.executable,"-S",str(guardian_path),
            "--cgroup",str(target),"--watch-fd",str(watch_r),
            "--ready-fd",str(ready_w)],
            cwd=str(cwd),stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=stderr,
            start_new_session=True,close_fds=True,pass_fds=(watch_r,ready_w))
        os.close(watch_r);watch_r=None
        os.close(ready_w);ready_w=None
        _read_ready(ready_r,10,"Cgroup guardian")
        os.close(ready_r);ready_r=None
        if guardian.poll() is not None:
            raise RuntimeError("Cgroup guardian exited before worker launch")
        admitted_r,admitted_w=os.pipe()
        try:
            write_scope=(["--landlock-spool",str(Path(linux_write_spool).resolve(strict=True))]
                         if linux_write_spool is not None else [])
            shim=Path(__file__).with_name("nvp_worker_linux_launcher.py").resolve()
            actual=[sys.executable,"-S",str(shim),
                    "--parent",str(os.getpid()),"--memory-mb","0",
                    "--cgroup-dir",str(target),"--ready-fd",str(admitted_w),
                    *write_scope,*command]
            worker=subprocess.Popen(actual,cwd=str(cwd),stdin=subprocess.DEVNULL,
                                    stdout=stdout,stderr=stderr,close_fds=True,
                                    start_new_session=True,pass_fds=(admitted_w,))
            os.close(admitted_w);admitted_w=None
            _read_ready(admitted_r,10,"Blender process cgroup admission")
        finally:
            os.close(admitted_r)
            if admitted_w is not None: os.close(admitted_w)
        return CgroupTreeProcess(worker,guardian,watch_w,target)
    except Exception:
        if worker is not None and worker.poll() is None:
            try:worker.kill();worker.wait(timeout=5)
            except (OSError,subprocess.TimeoutExpired): pass
        if watch_w is not None:
            os.close(watch_w)
        if watch_r is not None: os.close(watch_r)
        if ready_r is not None: os.close(ready_r)
        if ready_w is not None: os.close(ready_w)
        if guardian is not None:
            try:guardian.wait(timeout=10)
            except subprocess.TimeoutExpired: guardian.kill();guardian.wait()
        try:cgroup_kill(target)
        except OSError: pass
        try:target.rmdir()
        except OSError: pass
        raise
