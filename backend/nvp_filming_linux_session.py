"""Host-only DA-03 Linux filming process-tree session.

This joins the private cgroup launcher to the independent kernel custody gate.
It does not grant publication authority or reconstruct custody after restart.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from backend.nvp_filming_cgroup_launch import create_private_group_and_launch
from backend.nvp_filming_cgroup_custody import LinuxFilmingCgroup


@dataclass
class LinuxFilmingSession:
    group: Path
    child: subprocess.Popen
    custody: LinuxFilmingCgroup

    def stop_and_verify(self, *, timeout: float = 5.0) -> dict:
        """Kill the entire cgroup before waiting on the direct child."""
        receipt = self.custody.stop_and_verify(timeout=timeout)
        if (not isinstance(receipt, dict)
                or receipt.get("process_tree_custody_verified") is not True
                or receipt.get("empty_group_verified") is not True
                or receipt.get("scope") != "linux-cgroup-v2"):
            raise RuntimeError("Kernel custody did not return an affirmative Linux empty-tree receipt")
        try:
            self.child.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Cgroup empty but owned worker exit unverified") from exc
        if self.child.returncode is None:
            raise RuntimeError("Worker wait returned without an exit status")
        return {**receipt, "worker_exit_verified": True,
                "worker_returncode": self.child.returncode}


def launch_linux_filming_session(delegated_root: Path, executable: str,
                                 argv: list[str]) -> LinuxFilmingSession:
    """Create and retain host-owned launch and tree-custody handles.

    A successful return is not an attach/exec receipt and never permits
    publishing a frozen Take. On custody construction failure, refuse to
    abandon a potentially live worker without a kernel cleanup attempt.
    """
    group, child = create_private_group_and_launch(delegated_root, executable, argv)
    try:
        custody = LinuxFilmingCgroup(private_group=group, delegated_root=delegated_root)
    except BaseException:
        # Do not silently claim cleanup: the child may have descendants.
        # The group remains for independent host recovery.
        raise RuntimeError(
            "Filming worker launched without established cgroup custody; "
            "host must reconcile the private group before publication"
        )
    return LinuxFilmingSession(group, child, custody)
