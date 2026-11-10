"""DA-03 Linux filming worker: attach to an already host-created cgroup before exec.

This is a *child-side* entry point, not a browser API. The trusted host must
create a private delegated cgroup, retain its ownership handle, and refuse
publication until an independently verified worker/cgroup receipt exists.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def attach_then_exec(group: Path, executable: str, argv: list[str]) -> None:
    """Fail closed if cgroup attachment cannot complete before exec."""
    if sys.platform != "linux":
        raise RuntimeError("Linux cgroup v2 required")
    if not executable or not os.path.isabs(executable):
        raise ValueError("Trusted host must supply an absolute executable")
    if not argv or argv[0] != executable:
        raise ValueError("argv[0] must match the executable")
    # No shell, no PID sourced from a journal, no FFmpeg fallback.
    directory = os.open(group, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open("cgroup.procs", os.O_WRONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            # Writing 0 attaches the *current child* to the private cgroup.
            # The child cannot execute the worker if this write fails.
            if os.write(fd, b"0") != 1:
                raise OSError("Incomplete cgroup.procs attachment")
        finally:
            os.close(fd)
    finally:
        os.close(directory)
    os.execv(executable, argv)


def main() -> int:
    # Intentionally no general CLI: the host must call attach_then_exec with
    # vetted paths, after creating the private group and before publication.
    raise RuntimeError("Host-only launcher; direct CLI use is forbidden")


if __name__ == "__main__":
    sys.exit(main())
