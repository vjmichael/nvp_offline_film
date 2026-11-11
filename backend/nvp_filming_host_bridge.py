"""DA-03 trusted-host bridge: custody must finish before immutable Take publication.

This is a host integration seam, not a device adapter or an authorization grant.
The caller owns the native worker and supplies its original PCM event batch.
"""
from __future__ import annotations

from copy import deepcopy

from backend.nvp_filming_linux_session import LinuxFilmingSession
from backend.nvp_data_first_filming import NativeSceneSoundCapture


def finish_linux_recording_and_freeze(session, capture, project_id, take_id, *,
                                      recordings, timeout=5.0, **capture_options):
    """Finalize a recorded batch only after independently verified process custody.

    Always attempt process-tree shutdown, including on cancellation or recorder
    failure. A failed shutdown cannot authorize a Take, even if PCM exists.
    """
    if not isinstance(session, LinuxFilmingSession):
        raise TypeError("Host-owned Linux filming session required")
    batch = None
    recording_error = None
    try:
        # Even invalid host inputs must not leave an admitted worker running.
        # Validate them inside the protected shutdown region, not before it.
        if not isinstance(capture, NativeSceneSoundCapture):
            raise TypeError("Trusted original-scene capture service required")
        if not callable(recordings):
            raise TypeError("Trusted native recording batch supplier required")
        batch = recordings()
        if type(batch) is not list or not 1 <= len(batch) <= 32:
            raise ValueError("Recorder must return 1..32 original sound events")
        # Freeze event dictionaries before shutdown invokes worker callbacks.
        # Keep original PCM iterators: capture owns their bounded spooling and
        # digest verification, while this bridge fixes metadata at handoff.
        if any(type(event) is not dict for event in batch):
            raise ValueError("Recorder events must be typed dictionaries")
        batch = [dict(event) for event in batch]
        # Clock attestations contain nested dictionaries/lists. Snapshot only
        # these metadata fields; PCM iterators must retain stream identity.
        for event in batch:
            for field in ("source_sync", "clock_evidence"):
                if field in event:
                    event[field] = deepcopy(event[field])
    except BaseException as exc:
        recording_error = exc
    # Custody is mandatory even when the recording supplier raises. A shutdown
    # failure must never be suppressed by an earlier recording error.
    custody_receipt = session.stop_and_verify(timeout=timeout)
    if (type(custody_receipt) is not dict or
        custody_receipt.get("process_tree_custody_verified") is not True or
        custody_receipt.get("empty_group_verified") is not True or
        custody_receipt.get("worker_exit_verified") is not True or
        custody_receipt.get("scope") != "linux-cgroup-v2"):
        raise RuntimeError("Filming custody unverified; frozen Take publication denied")
    if recording_error is not None:
        raise recording_error
    return capture.capture(project_id, take_id, recordings=batch, **capture_options)
