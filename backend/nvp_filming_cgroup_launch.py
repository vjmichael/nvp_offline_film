"""DA-03 Linux filming worker: attach to an already host-created cgroup before exec.

This is a *child-side* entry point, not a browser API. The trusted host must
create a private delegated cgroup, retain its ownership handle, and refuse
publication until an independently verified worker/cgroup receipt exists.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _verify_current_process_membership(directory: int) -> None:
    """Require a fresh cgroup.procs observation of this exact child PID."""
    fd = os.open("cgroup.procs", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        with os.fdopen(fd, "r", encoding="ascii") as stream:
            members = stream.read(1024 * 1024)
    except UnicodeError as exc:
        raise RuntimeError("Invalid cgroup membership observation") from exc
    if str(os.getpid()) not in members.split():
        raise RuntimeError("Child cgroup membership not independently observed")


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
        # Keep the same pinned cgroup directory descriptor for attachment and
        # membership observation; pathname replacement cannot switch groups.
        _verify_current_process_membership(directory)
        os.execv(executable, argv)
    finally:
        os.close(directory)



def launch_attached_worker(group: Path, executable: str, argv: list[str]):
    """Host-side launch through the child attach-before-exec gate.

    The host must create and retain ownership of the private cgroup first.
    This returns a live process, NOT a custody/publication receipt. The
    independent LinuxFilmingCgroup stop-and-verify gate remains mandatory.
    """
    import subprocess

    if sys.platform != "linux":
        raise RuntimeError("Linux cgroup v2 required")
    if not executable or not os.path.isabs(executable):
        raise ValueError("Absolute trusted worker executable required")
    if not argv or argv[0] != executable:
        raise ValueError("Worker argv[0] must match executable")
    if not Path(group).is_absolute():
        raise ValueError("Host-owned cgroup path must be absolute")
    # The Python child invokes the same fail-closed attach_then_exec gate.
    # No preexec_fn (unsafe in a threaded desktop host), shell or fallback.
    bootstrap = (
        "import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "from backend.nvp_filming_cgroup_launch import attach_then_exec; "
        "from pathlib import Path; "
        "attach_then_exec(Path(sys.argv[2]), sys.argv[3], sys.argv[3:])"
    )
    return subprocess.Popen(
        [sys.executable, "-c", bootstrap, str(Path(__file__).resolve().parent.parent), str(group), *argv],
        shell=False,
        close_fds=True,
    )

def main() -> int:
    # Intentionally no general CLI: the host must call attach_then_exec with
    # vetted paths, after creating the private group and before publication.
    raise RuntimeError("Host-only launcher; direct CLI use is forbidden")


if __name__ == "__main__":
    sys.exit(main())
