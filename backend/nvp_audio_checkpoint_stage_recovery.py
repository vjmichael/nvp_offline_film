"""AUDIO-01E.6: source-verified reconciliation of a checkpoint .new stage.

Only trusted host after OS-attested worker stop and exclusive staging lock.
The staged checkpoint must describe precisely one next chunk or completion.
Never assume an arbitrary .new file is safe, and never delete evidence.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from backend.nvp_audio01d_chunked_recovery import (
    _audit_chunks, _check_inputs, _chunk_name, _json_bytes,
    _read_state, _render_chunk, _validate, _sha_file, CHUNK_SAMPLES
)


def reconcile_checkpoint_stage(plan, sources, total_samples, directory):
    root=Path(directory)
    if root.is_symlink() or not root.is_dir() or root.parent.is_symlink():
        raise RuntimeError("Unsafe checkpoint recovery root")
    stage=root/"checkpoint.json.new"
    if not stage.exists() and not stage.is_symlink():
        return {"status":"NO_PENDING_CHECKPOINT"}
    if stage.is_symlink() or not stage.is_file():
        raise RuntimeError("Unsafe pending checkpoint stage")
    old=_read_state(root)
    stems=_validate(plan,sources,total_samples)
    _check_inputs(stems,sources,old["sources"])
    offset=_audit_chunks(root,old)
    candidate_bytes=stage.read_bytes()
    candidate=json.loads(candidate_bytes)
    if (_json_bytes(candidate)!=candidate_bytes or
        candidate.get("format")!=old["format"] or
        candidate.get("total_samples")!=total_samples or
        candidate.get("sources")!=old["sources"] or
        candidate.get("sample_rate")!=old["sample_rate"] or
        candidate.get("channels")!=old["channels"] or
        candidate.get("final_mix") is not False or
        candidate.get("final_master") is not False):
        raise RuntimeError("Staged checkpoint identity differs from trusted sources")
    if old["status"]!="in_progress":
        raise RuntimeError("Cannot adopt stage for a terminal checkpoint")
    if (candidate.get("status")=="complete" and
        candidate.get("chunks")==old["chunks"] and
        candidate.get("next_sample")==total_samples and offset==total_samples):
        # Final marker replacement only; already verified all earlier chunks.
        os.replace(stage,root/"checkpoint.json")
        return {"status":"RECOVERED_COMPLETION_MARKER","next_sample":offset}
    if candidate.get("status")!="in_progress":
        raise RuntimeError("Unrecognized staged state transition")
    receipts=candidate.get("chunks")
    if (not isinstance(receipts,list) or len(receipts)!=len(old["chunks"])+1 or
        receipts[:-1]!=old["chunks"]):
        raise RuntimeError("Staged checkpoint attempted to rewrite history")
    last=receipts[-1]
    stop=min(offset+CHUNK_SAMPLES,total_samples)
    files=[f"stem_{s['stem_id']}_{_chunk_name(len(old['chunks']))}" for s in stems]
    files.append("mix_"+_chunk_name(len(old["chunks"])))
    expected=_render_chunk(stems,sources,offset,stop)
    required={
        "index":len(old["chunks"]),"start_sample":offset,"samples":stop-offset,
        "files":files,"sha256":[hashlib.sha256(raw).hexdigest() for raw in expected]
    }
    if last!=required or candidate.get("next_sample")!=stop:
        raise RuntimeError("Staged receipt cannot be reproduced from original audio")
    for name,raw in zip(files,expected):
        p=root/name
        if p.is_symlink() or not p.is_file() or p.stat().st_size!=len(raw) or _sha_file(p)!=hashlib.sha256(raw).hexdigest():
            raise RuntimeError("Staged checkpoint audio bytes missing or corrupted")
    # Forbid unrecognized files, including future chunk output and symlinks.
    permitted={"checkpoint.json","checkpoint.json.new"} | {
        name for receipt in candidate["chunks"] for name in receipt["files"]
    }
    if any(p.is_symlink() or not p.is_file() or p.name not in permitted
           for p in root.iterdir()):
        raise RuntimeError("Unexpected artifact during staged checkpoint recovery")
    os.replace(stage,root/"checkpoint.json")
    _audit_chunks(root,candidate)
    return {"status":"RECOVERED_STAGED_CHECKPOINT","next_sample":stop}
