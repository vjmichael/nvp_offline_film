"""AUDIO-01J native final audiovisual crash checkpoints (test opt-in only).

Never accept fault switches from a creator manifest or model task.
"""
from __future__ import annotations
import os
EXIT_CODE=97
BOUNDARIES=(
    "picture_event_reserved",
    "picture_lock_indexed",
    "picture_event_completed",
    "av_export_event_reserved",
    "av_grant_committed",
    "av_queued",
    "av_claimed",
    "av_stage_created",
    "av_mov_verified",
    "av_media_indexed",
    "av_manifest_fsynced",
    "av_directory_promoted",
    "av_filmindex_registered",
    "av_worker_receipt_fsynced",
    "av_worker_reaped",
    "av_master_registered",
    "av_stop_witness_committed",
    "av_result_committed",
    "av_ledger_succeeded",
    "av_event_completed",
)

def crash_after(name):
    if name not in BOUNDARIES:
        raise ValueError("Unknown native AV crash checkpoint")
    if (os.environ.get("NVP_AUDIO01J_FAULT_TEST")=="enabled" and
        os.environ.get("NVP_AUDIO01J_CRASH_AFTER")==name):
        os._exit(EXIT_CODE)
