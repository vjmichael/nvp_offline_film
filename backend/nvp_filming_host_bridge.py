"""DA-03 trusted-host bridge: custody must finish before immutable Take publication.

This is a host integration seam, not a device adapter or an authorization grant.
The caller owns the native worker and supplies its original PCM event batch.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from contextlib import ExitStack
import struct
import tempfile

from backend.nvp_data_av_source import MAX_CHUNK_BYTES, MAX_CHUNKS

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
    frozen_options = None
    recording_error = None
    spooled_checks = []
    # Bound the entire recording batch, not just each individual sound source.
    # A 32-source batch must not consume 32 times the per-source spool budget.
    batch_pcm_bytes = 0
    # The worker may own the PCM iterator. Drain it while the worker is alive;
    # publication after shutdown must never depend on a terminated producer.
    with ExitStack() as streams:
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
            # Snapshot metadata first; PCM is bounded and spooled before shutdown.
            if any(type(event) is not dict for event in batch):
                raise ValueError("Recorder events must be typed dictionaries")
            # Snapshot every metadata field, not just the known clock attestations.
            # New structured metadata must not remain mutable across worker shutdown.
            # Preserve only the original PCM stream handle, which capture spools.
            snapshot = []
            for event in batch:
                frozen = {key: (value if key == "pcm_chunks" else deepcopy(value))
                          for key, value in event.items()}
                snapshot.append(frozen)
            batch = snapshot
            # Source scope, consent and publication options must be fixed before
            # shutdown callbacks run; never trust caller-owned nested references.
            frozen_options = deepcopy(capture_options)
            # Bound original PCM before terminating its producer. Spooled files
            # preserve streaming semantics without holding a full Take in RAM.
            for event in batch:
                spool = streams.enter_context(tempfile.SpooledTemporaryFile(
                    max_size=MAX_CHUNK_BYTES, mode="w+b"))
                count = 0
                digest = sha256()
                for chunk in event["pcm_chunks"]:
                    if (type(chunk) is not bytes or not 0 < len(chunk) <= MAX_CHUNK_BYTES
                            or len(chunk) % 2 or count >= MAX_CHUNKS):
                        raise ValueError("Invalid original PCM16LE chunk")
                    batch_pcm_bytes += len(chunk)
                    if batch_pcm_bytes > MAX_CHUNK_BYTES * MAX_CHUNKS:
                        raise ValueError("Original PCM recording batch exceeds spool budget")
                    header = struct.pack("<I", len(chunk))
                    if spool.write(header) != 4 or spool.write(chunk) != len(chunk):
                        raise OSError("Incomplete original PCM spool write")
                    digest.update(header)
                    digest.update(chunk)
                    count += 1
                if not count:
                    raise ValueError("Empty original PCM stream")
                spool.flush()
                spool.seek(0)
                expected_digest = digest.digest()
                spooled_checks.append((spool, expected_digest))
                def replay(source=spool, expected=expected_digest):
                    # The spool survives worker shutdown callbacks. Verify its
                    # original bytes before handing any PCM to Take publication.
                    source.seek(0)
                    actual = sha256()
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        actual.update(block)
                    if actual.digest() != expected:
                        raise RuntimeError("Original PCM spool integrity verification failed")
                    source.seek(0)
                    while True:
                        header = source.read(4)
                        if not header:
                            return
                        if len(header) != 4:
                            raise RuntimeError("Damaged original PCM spool header")
                        size = struct.unpack("<I", header)[0]
                        if not 0 < size <= MAX_CHUNK_BYTES or size % 2:
                            raise RuntimeError("Damaged original PCM spool size")
                        chunk = source.read(size)
                        if len(chunk) != size:
                            raise RuntimeError("Truncated original PCM spool")
                        yield chunk
                event["pcm_chunks"] = replay()
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
        # Verify all spools before invoking a publication API, even if the
        # capture service defers or never consumes its PCM iterators.
        for source, expected in spooled_checks:
            source.seek(0)
            actual = sha256()
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                actual.update(block)
            if actual.digest() != expected:
                raise RuntimeError("Original PCM spool integrity verification failed")
            source.seek(0)
        return capture.capture(project_id, take_id, recordings=batch, **frozen_options)
