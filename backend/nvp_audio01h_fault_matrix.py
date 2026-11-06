"""AUDIO-01H explicit test-only abrupt process-exit checkpoints.

Disabled in production unless both exact environment opt-in keys are set.
Never copy these environment variables from submitted model/creator plans.
"""
from __future__ import annotations
import os

EXIT_CODE = 94
BOUNDARIES = (
    "plan_fsynced",
    "grant_committed",
    "queued_committed",
    "claimed_active",
    "worker_output_registered",
    "worker_receipt_fsynced",
    "worker_handle_reaped",
    "stopped_witness_committed",
    "output_independently_verified",
    "ledger_succeeded",
    "grant_result_committed",
    "creator_event_reserved",
    "creator_decision_registered",
    "creator_event_completed",
)


def crash_after(name):
    if name not in BOUNDARIES:
        raise ValueError("Unrecognized AUDIO-01H crash checkpoint")
    if (os.environ.get("NVP_AUDIO01H_FAULT_TEST") == "enabled" and
        os.environ.get("NVP_AUDIO01H_CRASH_AFTER") == name):
        os._exit(EXIT_CODE)
