"""Linux OS worker launch shim: parent-death signal set before execv Blender.

PR_SET_PDEATHSIG kills the immediate child when its supervising thread dies.
It is not a full descendant cgroup; retain separate cancellation and audits.
"""
from __future__ import annotations
import ctypes
import os
import resource
import signal
import sys

PR_SET_PDEATHSIG = 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 6 or argv[0] != "--parent" or argv[2] != "--memory-mb":
        raise SystemExit("Invalid internal containment command")
    parent_pid = int(argv[1])
    memory_mb = int(argv[3])
    if parent_pid <= 1 or not 0 <= memory_mb <= 65536:
        raise SystemExit("Invalid parent or memory limit")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_PDEATHSIG failed")
    if os.getppid() != parent_pid:
        raise SystemExit("Supervisor vanished before parent-death guard")
    if memory_mb:
        cap = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    executable = argv[4]
    if not os.path.isabs(executable) or not os.path.isfile(executable):
        raise SystemExit("Unpinned executable path")
    os.execv(executable, argv[4:])


if __name__ == "__main__":
    main()
