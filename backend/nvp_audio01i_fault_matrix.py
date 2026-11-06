"""AUDIO-01I explicit native process-failure gates for isolated CI only.

Two independent environment opt-ins required. Production input plans never
accept arbitrary fault-point settings or pass creator-provided environment.
"""
from __future__ import annotations
import os

EXIT_CODE=96
BOUNDARIES=(
    "master_event_reserved",
    "master_grant_committed",
    "master_queued",
    "master_claimed",
    "candidate_filmindex_registered",
    "candidate_receipt_fsynced",
    "master_worker_reaped",
    "master_stop_witness_committed",
    "master_result_committed",
    "master_ledger_finished",
    "delivery_event_reserved",
    "delivery_stage_created",
    "delivery_wav_fsynced",
    "delivery_manifest_fsynced",
    "delivery_directory_promoted",
    "delivery_filmindex_registered",
    "delivery_event_finalized",
)


def crash_after(name):
    if name not in BOUNDARIES:
        raise ValueError("Unknown AUDIO-01I fault point")
    if (os.environ.get("NVP_AUDIO01I_FAULT_TEST")=="enabled" and
        os.environ.get("NVP_AUDIO01I_CRASH_AFTER")==name):
        os._exit(EXIT_CODE)
