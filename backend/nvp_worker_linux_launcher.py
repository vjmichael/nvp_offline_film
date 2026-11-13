"""Linux direct-child PDEATHSIG shim, with optional strict cgroup admission.

A strict worker joins its own kernel cgroup v2 leaf *before* execv. Every
descendant inherits the leaf, while the out-of-tree guardian owns cgroup.kill.
No application-level PID polling is substituted for cgroup membership.
"""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import resource
import signal
import sys

PR_SET_PDEATHSIG=1


def _membership():
    for row in Path("/proc/self/cgroup").read_text("utf8").splitlines():
        if row.startswith("0::"):
            return row[3:]
    raise RuntimeError("Unified Linux cgroup membership unavailable")


def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if len(argv)<5 or argv[0]!="--parent" or argv[2]!="--memory-mb":
        raise SystemExit("Invalid internal containment command")
    parent_pid=int(argv[1])
    memory_mb=int(argv[3])
    if parent_pid<=1 or not 0<=memory_mb<=65536:
        raise SystemExit("Invalid parent or memory limit")

    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG,signal.SIGKILL,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),"PR_SET_PDEATHSIG failed")
    if os.getppid()!=parent_pid:
        raise SystemExit("Supervisor vanished before parent-death guard")

    index=4
    if len(argv)>=9 and argv[index]=="--cgroup-dir":
        target=Path(argv[index+1]).resolve(strict=True)
        if argv[index+2]!="--ready-fd":
            raise SystemExit("Missing cgroup membership confirmation FD")
        ready_fd=int(argv[index+3])
        if ready_fd<3:
            raise SystemExit("Invalid kernel admission ready descriptor")
        current=_membership()
        own=(Path("/sys/fs/cgroup")/current.lstrip("/")).resolve()
        delegated=target.parent
        try:
            supported=os.getxattr(delegated,"user.delegate")==b"1"
        except (OSError,AttributeError):
            supported=False
        if (not own.is_relative_to(delegated) or not supported or
            not target.name.startswith("nvp-worker-") or
            len(target.name)!=len("nvp-worker-")+32):
            raise SystemExit("Worker cgroup not inside host's delegated systemd scope")
        # Move THIS shim before exec. Forked Blender descendants inherit
        # membership even after setsid() or a new process group.
        (target/"cgroup.procs").write_text(str(os.getpid()),encoding="ascii")
        expected="/"+target.relative_to(Path("/sys/fs/cgroup")).as_posix()
        if _membership()!=expected:
            raise RuntimeError("Kernel did not confirm worker cgroup admission")
        os.write(ready_fd,b"1")
        os.close(ready_fd)
        index+=4

    # The device-only write fence must be applied BEFORE the recording
    # executable starts, while the original guardian is outside this fence.
    # A worker in the cgroup can otherwise escape by writing an ancestor
    # cgroup.procs in a same-UID delegated scope.
    if index < len(argv) and argv[index]=="--landlock-spool":
        if index+2>=len(argv):
            raise SystemExit("Missing original source spool or executable")
        from nvp_worker_linux_landlock import restrict_native_producer_writes
        restrict_native_producer_writes(argv[index+1])
        index+=2
    if memory_mb:
        cap=memory_mb*1024*1024
        resource.setrlimit(resource.RLIMIT_AS,(cap,cap))
    if index>=len(argv):
        raise SystemExit("No worker executable")
    executable=argv[index]
    if not os.path.isabs(executable) or not os.path.isfile(executable):
        raise SystemExit("Unpinned executable path")
    os.execv(executable,argv[index:])


if __name__=="__main__":
    main()
