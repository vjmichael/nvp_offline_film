"""AUDIO-01K deterministic abrupt-exit fault points for native CI only."""
from __future__ import annotations
import os

EXIT_CODE=98
BOUNDARIES=(
    "creator_event_reserved",
    "staging_directory_created",
    "movie_bytes_fsynced",
    "manifest_fsynced",
    "checksums_fsynced",
    "directory_promoted",
    "filmindex_registered",
    "creator_event_published",
)


def crash_after(name):
    if name not in BOUNDARIES:
        raise ValueError("Unknown AUDIO-01K distribution fault checkpoint")
    if (os.environ.get("NVP_AUDIO01K_FAULT_TEST")=="enabled" and
        os.environ.get("NVP_AUDIO01K_CRASH_AFTER")==name):
        os._exit(EXIT_CODE)
