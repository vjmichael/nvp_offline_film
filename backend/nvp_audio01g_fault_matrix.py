"""AUDIO-01G deterministic abrupt-exit fault gates for native CI only.

A crash gate is inert unless *both* explicit test flags are present. It uses
os._exit (not an exception) so finally blocks, SQLite connection managers
and file cleanup cannot accidentally mask interrupted publication boundaries.
Never accept either flag from an AI-authored job or a creator media document.
"""
from __future__ import annotations
import os

EXIT_CODE = 93

# Each boundary is immediately AFTER an effect and BEFORE its next effect.
BOUNDARIES = (
    "intent_prepared_sqlite",
    "approved_grant_sqlite",
    "task_queued_sqlite",
    "task_claimed_sqlite",
    "intent_running_sqlite",
    "stage_directory_created",
    "mov_bytes_written",
    "mov_independently_verified",
    "filmindex_media_ingested",
    "manifest_file_fsynced",
    "movie_file_fsynced",
    "staging_directory_promoted",
    "destination_parent_fsynced",
    "filmindex_presentation_registered",
    "worker_receipt_fsynced",
    "native_worker_reaped",
    "os_stop_witness_sqlite",
    "grant_result_sqlite",
    "intent_verified_sqlite",
    "ledger_succeeded_sqlite",
    "intent_committed_sqlite",
)


def crash_after(name):
    if name not in BOUNDARIES:
        raise ValueError("Unknown AUDIO-01G crash-injection boundary")
    if (os.environ.get("NVP_AUDIO01G_FAULT_TEST") == "enabled" and
        os.environ.get("NVP_AUDIO01G_CRASH_AFTER") == name):
        os._exit(EXIT_CODE)
