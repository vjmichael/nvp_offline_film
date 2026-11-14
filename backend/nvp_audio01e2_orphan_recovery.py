"""AUDIO-01E.2: explicit recovery of crash-interrupted AUDIO-01D chunk writes.

Trusted-host operation only. Never silently delete or trust orphan media.
Rebuilds the one expected next chunk from unchanged source recordings and the
immutable plan, validates each existing orphan byte-for-byte, fills only absent
outputs, and commits the missing receipt. Refuses unexplained artifacts and
unfinished checkpoint replacement; not an OS isolation or exclusive lock.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.nvp_audio01d_chunked_recovery import (
    CHUNK_SAMPLES, _audit_chunks, _atomic_replace, _check_inputs, _chunk_name,
    _json_bytes, _read_state, _render_chunk, _validate, _write_new,
)


def reconcile_next_chunk(plan, sources, total_samples, directory):
    """Recover exactly one orphan chunk after the trusted host stops its worker.

    If an interrupted chunk has already generated some/all files, reproduce
    the expected bytes from original sources. Any mismatch is a hard error.
    Existing receipt-bound chunks are immutable and rehashed before recovery.
    """
    root = Path(directory)
    if root.is_symlink() or not root.is_dir() or root.parent.is_symlink():
        raise RuntimeError("Unsafe recovery directory")
    state = _read_state(root)
    stems = _validate(plan, sources, total_samples)
    if (state.get("status") != "in_progress" or
        state.get("total_samples") != total_samples or
        state.get("final_mix") is not False or state.get("final_master") is not False):
        raise RuntimeError("Recovery requires an incomplete unapproved audio job")
    _check_inputs(stems, sources, state["sources"])
    start = _audit_chunks(root, state)
    if start >= total_samples:
        raise RuntimeError("No uncommitted next chunk to reconcile")
    # Atomic checkpoint .new stage could contain a completed transition.
    # Never guess whether it was committed or silently delete that evidence.
    staged = root / "checkpoint.json.new"
    if staged.exists() or staged.is_symlink():
        raise RuntimeError("Pending checkpoint replacement needs manual journal audit")
    index = len(state["chunks"])
    names = [f"stem_{s['stem_id']}_{_chunk_name(index)}" for s in stems]
    names.append("mix_" + _chunk_name(index))
    # Whitelist artifact names to refuse hidden unexpected future chunks,
    # extra sidecar files or a duplicate output from an overlapping worker.
    receipt_files = {
        name for receipt in state["chunks"] for name in receipt["files"]
    }
    permitted = receipt_files | set(names) | {"checkpoint.json"}
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file() or child.name not in permitted:
            raise RuntimeError("Unexpected recovery artifact; no automatic deletion")
    stop = min(start + CHUNK_SAMPLES, total_samples)
    raw_blocks = _render_chunk(stems, sources, start, stop)
    if len(names) != len(raw_blocks):
        raise RuntimeError("Recovery stem identity mismatch")
    existing = 0
    # Verify all existing files BEFORE creating any new ones.
    for name, raw in zip(names, raw_blocks):
        target = root / name
        if target.is_symlink():
            raise RuntimeError("Symlinked orphan chunk")
        if target.exists():
            existing += 1
            if not target.is_file() or target.stat().st_size != len(raw) or (
                hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(raw).digest()
            ):
                raise RuntimeError("Orphan PCM differs from reproducible source")
    if not existing:
        return {"status": "NO_ORPHAN_CHUNK", "next_sample": start,
                "reconciled_chunks": 0}
    for name, raw in zip(names, raw_blocks):
        target = root / name
        if not target.exists():
            _write_new(target, raw)
    receipt = {
        "index": index,
        "start_sample": start,
        "samples": stop-start,
        "files": names,
        "sha256": [hashlib.sha256(raw).hexdigest() for raw in raw_blocks],
    }
    state["chunks"].append(receipt)
    state["next_sample"] = stop
    _atomic_replace(root / "checkpoint.json", _json_bytes(state))
    _audit_chunks(root, state)
    return {"status": "RECOVERED_SOURCE_VERIFIED_CHUNK",
            "next_sample": stop, "reconciled_chunks": 1}
