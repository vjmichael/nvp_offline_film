"""DA-03 host-owned filming worker custody (direct-child boundary only).

This deliberately does not infer termination from a PID, journal state, or a
stale process-list observation. It also does not claim process-tree custody:
Windows Job Objects / Linux cgroup custody remain a separate acceptance gate.
"""
from __future__ import annotations

import subprocess
import os
import math
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WorkerExitReceipt:
    pid: int
    returncode: int
    exited: bool
    direct_child_only: bool = True


class OwnedFilmingWorker:
    """An in-memory, one-use ownership handle to a launched child process.

    Do not reconstruct this from a PID after host restart. Such recovery must
    use an independently attested OS supervisor, not this interface.
    """

    def __init__(self, process: subprocess.Popen):
        # Production Windows MUST use WindowsFilmingSession, which retains
        # the original Job Object and release-wide launch slot. Even an
        # explicit legacy direct-child opt-in cannot bypass this gate.
        if os.name=="nt":
            raise RuntimeError("Windows direct-child filming retired: use native WindowsFilmingSession")
        if not isinstance(process, subprocess.Popen):
            raise TypeError("An actual host-owned Popen handle is required")
        self._process = process
        self._consumed = False
        self._termination_requested = False
        self._kill_requested = False

    def stop_and_verify(self, *, timeout: float = 5.0) -> WorkerExitReceipt:
        if self._consumed:
            raise RuntimeError("Worker exit receipt already consumed")
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 60):
            raise ValueError("Bounded positive termination timeout required")
        process = self._process
        deadline = time.monotonic() + timeout
        if process.poll() is None:
            if not self._termination_requested:
                self._termination_requested = True
                try:
                    process.terminate()
                except ProcessLookupError:
                    # Child exited after poll; the owned handle still provides
                    # the only admissible exit evidence.
                    pass
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                # Escalate to kill, but never silently turn an unbounded wait
                # into a verified exit. A second timeout is an explicit failure.
                if not self._kill_requested:
                    self._kill_requested = True
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                process.wait(timeout=max(0, deadline - time.monotonic()))
        code = process.poll()
        if code is None:
            raise RuntimeError("Worker exit not verified")
        self._consumed = True
        return WorkerExitReceipt(process.pid, code, True)

    def interrupt_journal(self, journal, project_id: str, take_id: str,
                          *, expected_updated_at: str,
                          timeout: float = 5.0,
                          allow_direct_child_only: bool = False) -> dict:
        """Only transition after the owned direct child is observed exited.

        A direct-child receipt is not proof of descendant containment. Callers
        must separately ensure this filming worker cannot leave descendants
        writing to the publication namespace.
        """
        # The direct child can exit while descendants continue writing.
        # Require an explicit opt-in for legacy, non-tree-contained workers;
        # callers cannot mistake the default for full custody.
        if allow_direct_child_only is not True:
            raise RuntimeError(
                "Process-tree custody unverified; direct-child journal "
                "interruption requires explicit unsafe-scope opt-in")
        receipt = self.stop_and_verify(timeout=timeout)
        result = journal.interrupt_preparing(
            project_id, take_id, expected_updated_at=expected_updated_at)
        return {**result, "worker_pid": receipt.pid,
                "worker_returncode": receipt.returncode,
                "direct_child_exit_verified": True,
                "process_tree_custody_verified": False}
