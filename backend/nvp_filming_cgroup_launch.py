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
    if Path(executable).is_symlink():
        raise ValueError("Trusted worker executable must not be a symlink")
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
    # Reject missing/non-executable worker paths before spawning the bootstrap.
    # The child still enforces attach-before-exec; this is not an exec receipt.
    worker = Path(executable)
    if worker.is_symlink() or not worker.is_file() or not os.access(worker, os.X_OK):
        raise ValueError("Trusted worker executable is unavailable or not executable")
    if not Path(group).is_absolute() or Path(group).is_symlink():
        raise ValueError("Host-owned cgroup path must be absolute and not a symlink")
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


def create_private_group_and_launch(
    delegated_root: Path, executable: str, argv: list[str]
):
    """Create a private cgroup-v2 leaf before launching an attached child.

    Caller owns the returned group and must retain it for independent custody,
    restart reconciliation and eventual removal. A process handle is not a
    publication receipt. The delegated root must be provisioned by the OS/host.
    """
    import secrets

    if sys.platform != "linux":
        raise RuntimeError("Linux cgroup v2 required")
    root = Path(delegated_root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Delegated root must be an absolute non-symlink path")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # A real cgroup-v2 delegation exposes these kernel controls. Refuse
        # ordinary directories and cgroup-v1 roots rather than silently falling back.
        for control in ("cgroup.controllers", "cgroup.procs"):
            fd = os.open(control, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(fd)
        name = "nvp-film-" + secrets.token_hex(16)
        os.mkdir(name, mode=0o700, dir_fd=directory)
        group = root / name
        try:
            # A successful mkdir is not evidence of a usable custody leaf.
            # Validate all kernel controls required for attach and subsequent
            # independent kill/empty-group observation before spawning.
            leaf = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                for control in ("cgroup.procs", "cgroup.kill", "cgroup.events"):
                    control_fd = os.open(control, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=leaf)
                    os.close(control_fd)
            finally:
                os.close(leaf)
            child = launch_attached_worker(group, executable, argv)
        except BaseException:
            # Never remove a group that might contain a running process.
            # Failed bootstrap/exec after Popen must be reconciled by custody.
            try:
                os.rmdir(name, dir_fd=directory)
            except OSError:
                pass
            raise
        return group, child
    finally:
        os.close(directory)

def main() -> int:
    # Intentionally no general CLI: the host must call attach_then_exec with
    # vetted paths, after creating the private group and before publication.
    raise RuntimeError("Host-only launcher; direct CLI use is forbidden")


if __name__ == "__main__":
    sys.exit(main())
