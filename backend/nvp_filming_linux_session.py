"""Host-only DA-03 Linux filming process-tree session.

This joins the private cgroup launcher to the independent kernel custody gate.
It does not grant publication authority or reconstruct custody after restart.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import time

from backend.nvp_filming_cgroup_launch import create_private_group_and_launch
from backend.nvp_filming_cgroup_custody import LinuxFilmingCgroup


class FilmingCustodyInitializationError(RuntimeError):
    """Retain the exact launched worker and private group for host recovery.

    This exception is NOT a cleanup or publication receipt. The caller must
    reconcile the retained cgroup before allowing any frozen Take publication.
    """
    def reconcile_and_stop(self, delegated_root: Path, *, timeout: float = 5.0) -> dict:
        """Trusted-host recovery attempt; never reconstruct authority from a PID.

        Revalidates the original private cgroup against the delegated root and
        uses kernel-wide termination before reaping the retained child. A
        failed attempt is not an empty-group or publication receipt.
        """
        # Preserve one-use kernel custody across retries on this exception. A
        # timed-out direct-child reap must not reconstruct a fresh kill handle.
        if self._recovery_session is None:
            custody = LinuxFilmingCgroup(
                private_group=self.group, delegated_root=delegated_root
            )
            self._recovery_session = LinuxFilmingSession(self.group, self.child, custody)
            self._recovery_root = delegated_root
        elif delegated_root != self._recovery_root:
            raise RuntimeError("Filming recovery delegated root changed")
        return self._recovery_session.stop_and_verify(timeout=timeout)

    def __init__(self, group: Path, child: subprocess.Popen):
        self.group = group
        self.child = child
        self._recovery_session = None
        self._recovery_root = None
        super().__init__(
            "Filming worker launched without established cgroup custody; "
            "host must reconcile the private group before publication"
        )


@dataclass
class LinuxFilmingSession:
    group: Path
    child: subprocess.Popen
    custody: LinuxFilmingCgroup
    # Kernel custody is one-use. Retain an affirmative receipt if child reaping
    # fails, so recovery never attempts a second cgroup.kill.
    _verified_tree_receipt: dict | None = None

    def stop_and_verify(self, *, timeout: float = 5.0) -> dict:
        """Kill the entire cgroup before waiting on the direct child."""
        # One deadline covers kernel termination AND worker reaping.
        # Never grant a second full timeout after the kernel phase.
        if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Bounded positive filming shutdown deadline required")
        started = time.monotonic()
        receipt = self._verified_tree_receipt
        if receipt is None:
            receipt = self.custody.stop_and_verify(timeout=timeout)
        else:
            # A historical empty-tree receipt cannot authorize a later reap:
            # the group may have been repopulated after the first observation.
            # Reobserve kernel state without repeating the one-use kill.
            receipt = self.custody.verify_still_empty()
        if (not isinstance(receipt, dict)
                or receipt.get("process_tree_custody_verified") is not True
                or receipt.get("empty_group_verified") is not True
                or receipt.get("scope") != "linux-cgroup-v2"):
            raise RuntimeError("Kernel custody did not return an affirmative Linux empty-tree receipt")
        # Cache only a fully validated kernel receipt, not a partial claim.
        self._verified_tree_receipt = dict(receipt)
        remaining = timeout - (time.monotonic() - started)
        if remaining < 0:
            raise RuntimeError("Kernel custody exceeded filming shutdown deadline; worker exit unverified")
        try:
            self.child.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Cgroup empty but owned worker exit unverified") from exc
        if time.monotonic() - started > timeout:
            raise RuntimeError("Worker reaping exceeded filming shutdown deadline; bounded receipt refused")
        if self.child.returncode is None:
            raise RuntimeError("Worker wait returned without an exit status")
        # The group can be repopulated while the direct worker is being reaped.
        # A pre-wait empty observation is not a post-wait tree custody receipt.
        receipt = self.custody.verify_still_empty()
        if (not isinstance(receipt, dict)
                or receipt.get("process_tree_custody_verified") is not True
                or receipt.get("empty_group_verified") is not True
                or receipt.get("scope") != "linux-cgroup-v2"):
            raise RuntimeError("Post-reap kernel custody did not verify an empty filming group")
        if time.monotonic() - started > timeout:
            raise RuntimeError("Post-reap kernel verification exceeded filming shutdown deadline")
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
    except Exception as exc:
        # Retain the exact group and live child handle for host recovery.
        # Never terminate only the direct child: descendants may survive.
        raise FilmingCustodyInitializationError(group, child) from exc
    # A worker that has already exited cannot be an active filming session.
    # Retain its exact group and handle for host reconciliation rather than
    # treating a successful cgroup constructor as an execution receipt.
    if child.poll() is not None:
        raise FilmingCustodyInitializationError(group, child)
    return LinuxFilmingSession(group, child, custody)
