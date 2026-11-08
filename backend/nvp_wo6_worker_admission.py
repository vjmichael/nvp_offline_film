"""WO6 native worker must independently verify durable host admission.

Only the already-approved, resource-admitted task in the trusted TaskLedger
may execute. A model-supplied operation document or queued task.json alone
is never enough to run a first-party native OpenUSD/FilmIndex writer.

This is an admission check, not a substitute for currently checking creator
policy in the parent before/after the contained process.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import closing
import hashlib
import json
import sqlite3

from backend.nvp_approved_tasks import canonical_bytes


def verify_admitted_worker(spec:dict, *, ledger_db, owner_key:str) -> None:
    if type(spec) is not dict or type(owner_key) is not str:
        raise PermissionError("Native worker requires host-owned exact task identity")
    path=Path(ledger_db)
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()):
        raise PermissionError("Native worker admission must use existing local task ledger")
    raw=canonical_bytes(spec)
    expected=hashlib.sha256(raw).hexdigest()
    # Read-only SQLite URI: do not initialize a second ledger or create
    # schema from worker entrypoint. URI escape permits spaces in native path.
    uri=path.resolve().as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri,uri=True,timeout=10)) as db:
        row=db.execute("""SELECT t.state,t.reserved,t.kind,
                                 a.owner_key,a.spec_sha256,a.spec_json,
                                 s.owner_key,c.task_id
            FROM tasks t
            JOIN authorized_task_specs a ON a.task_id=t.id
            JOIN task_schedule s ON s.task_id=t.id
            LEFT JOIN wo6_cancel_intents c ON c.task_id=t.id
            WHERE t.id=?""",(spec.get("task_id"),)).fetchone()
    if (row is None or row[0]!="ACTIVE" or row[1]!=1 or
            row[2]!=spec.get("kind") or row[3]!=owner_key or
            row[4]!=expected or row[5].encode("ascii")!=raw or
            row[6]!=owner_key or row[7] is not None):
        raise PermissionError(
            "WO6 worker is not admitted under an exact trusted native host grant")
