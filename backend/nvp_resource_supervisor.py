"""Host-side NVP worker pressure watchdog.

Combines existing TaskLedger measured-pressure checks with existing OS-contained
worker control. Never attempts to kill unrelated processes or release safety
reservations: the producer owns that after verified worker-tree cleanup.
"""
from __future__ import annotations

import subprocess
import time


class ResourceGuardStop(RuntimeError):
    """Sustained critical pressure stopped one NVP-owned contained worker."""


def wait_guarded(worker, ledger, task_id: str, *, timeout_seconds: int,
                 poll_interval: float = 1.0, critical_samples: int = 2,
                 clock=time.monotonic, sleep=time.sleep):
    """Wait for one owned worker, monitoring live RAM/GPU every sample.

    Two consecutive critical samples are required by default. The contained
    worker is stopped before raising; the caller must independently verify
    full OS cleanup and only then reconcile durable ledger reservations.
    """
    if (type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 86400 or
        type(poll_interval) not in (int, float) or not .05 <= poll_interval <= 5 or
        type(critical_samples) is not int or not 2 <= critical_samples <= 5):
        raise ValueError("Invalid native resource watchdog policy")
    if not callable(getattr(worker, "poll", None)) or not callable(
            getattr(worker, "terminate_tree", None)):
        raise TypeError("A supervisor-owned contained worker is required")
    start = clock()
    strikes = 0
    while True:
        code = worker.poll()
        if code is not None:
            return worker.wait(timeout=15)
        if clock() - start >= timeout_seconds:
            worker.terminate_tree()
            raise subprocess.TimeoutExpired("NVP contained worker", timeout_seconds)
        reason = ledger.critical_pressure(task_id)
        if reason:
            strikes += 1
            if strikes >= critical_samples:
                worker.terminate_tree()
                raise ResourceGuardStop("NVP worker stopped after sustained resource pressure: " + reason)
        else:
            strikes = 0
        sleep(poll_interval)
