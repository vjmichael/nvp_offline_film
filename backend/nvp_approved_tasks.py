"""STACK-02C3B2: immutable, host-approved scheduler work, never a web API.

A caller-provided approval verifier MUST consult creator/project policy. Merely
knowing owner_key is not an authorization capability. The same SQLite FULL-sync
transaction persists the approved operation, exact SHA and queued task.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger

_APPROVAL = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,119}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


def canonical_bytes(document):
    if not isinstance(document,dict):
        raise TypeError("An immutable typed operation document is required")
    try:
        raw=json.dumps(document,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False).encode("ascii")
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("Operation cannot be sealed") from exc
    if not 0<len(raw)<=65536:
        raise ValueError("Operation is too large or empty")
    return raw


class ApprovedTaskBindings:
    """Native-only, creator-policy-checked task spec records.

    approval_check(approval_id, spec_digest, document) must be a trusted,
    non-model-exposed callable that checks the current approved project state.
    """
    def __init__(self, ledger:TaskLedger, *, approval_check):
        if not isinstance(ledger,TaskLedger) or not callable(approval_check):
            raise TypeError("A durable ledger and native creator approval verifier are required")
        self.ledger=ledger
        self.approval_check=approval_check
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS authorized_task_specs (
                task_id TEXT PRIMARY KEY,
                owner_key TEXT NOT NULL,
                approval_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                spec_sha256 TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                accepted_at REAL NOT NULL
            )""")

    def _check(self,approval_id,digest,document):
        if not isinstance(approval_id,str) or not _APPROVAL.fullmatch(approval_id):
            raise ValueError("Invalid creator approval reference")
        if not _DIGEST.fullmatch(digest):
            raise ValueError("Invalid approved spec digest")
        if self.approval_check(approval_id,digest,document) is not True:
            raise PermissionError("Creator approval missing, changed or revoked")

    def enqueue(self,request:AdmissionRequest,*,owner_key,lane,approval_id,document):
        if not isinstance(request,AdmissionRequest):
            raise TypeError("Typed memory admission request required")
        TaskLedger._schedule_args(owner_key,lane)
        raw=canonical_bytes(document)
        digest=hashlib.sha256(raw).hexdigest()
        # Authorization is checked BEFORE any durable record is created.
        self._check(approval_id,digest,document)
        if document.get("task_id")!=request.task_id or document.get("kind")!=request.kind:
            raise ValueError("Approved operation and requested task identity disagree")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tasks WHERE id=?",(request.task_id,)).fetchone():
                raise RuntimeError("Already registered; approved task IDs are never reused")
            now=time.time()
            detail="Waiting for "+lane+" priority native admission; no worker started"
            db.execute("""INSERT INTO tasks(id,kind,title,state,phase,detail,completed_fraction,
                ram_mb,gpu_mb,device_id,reserved,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (request.task_id,request.kind,request.title,"QUEUED",
                 "waiting_for_resources",detail,None,request.ram_mb,request.gpu_mb,
                 request.device_id,0,now,now))
            db.execute("""INSERT INTO task_schedule(task_id,owner_key,lane,queued_at)
                VALUES(?,?,?,?)""",(request.task_id,owner_key,lane,now))
            db.execute("""INSERT INTO authorized_task_specs
                (task_id,owner_key,approval_id,kind,spec_sha256,spec_json,accepted_at)
                VALUES (?,?,?,?,?,?,?)""",(request.task_id,owner_key,approval_id,
                                           request.kind,digest,raw.decode("ascii"),now))
            self.ledger._event(db,request.task_id,"QUEUED","waiting_for_resources",detail,None)
            db.commit()
        return {"task_id":request.task_id,"state":"QUEUED","spec_sha256":digest,
                "approval_id":approval_id,"admitted":False}

    def verified_spec(self,task_id,*,owner_key,require_active=True):
        TaskLedger._schedule_args(owner_key)
        with self.ledger._db() as db:
            row=db.execute("""SELECT a.approval_id,a.kind,a.spec_sha256,a.spec_json,
                t.state,t.kind,s.owner_key
                FROM authorized_task_specs a
                JOIN tasks t ON t.id=a.task_id
                JOIN task_schedule s ON s.task_id=t.id
                WHERE a.task_id=? AND a.owner_key=?""",(task_id,owner_key)).fetchone()
        if row is None:
            raise PermissionError("No immutable approved task for this producer")
        approval_id,kind,digest,serialized,state,actual_kind,scheduled_owner=row
        if scheduled_owner!=owner_key or actual_kind!=kind:
            raise RuntimeError("Approved operation metadata mismatch")
        if require_active and state!="ACTIVE":
            raise RuntimeError("Approved work is not admitted")
        if hashlib.sha256(serialized.encode("ascii")).hexdigest()!=digest:
            raise RuntimeError("Sealed operation was altered after approval")
        try:
            document=json.loads(serialized)
        except (ValueError,TypeError) as exc:
            raise RuntimeError("Unreadable immutable operation") from exc
        if (canonical_bytes(document).decode("ascii")!=serialized or
            document.get("task_id")!=task_id or document.get("kind")!=kind):
            raise RuntimeError("Sealed operation is inconsistent")
        # Creator policy can revoke an operation while it is waiting.
        self._check(approval_id,digest,document)
        return document

    def claim_next(self,*,owner_key):
        # Preflight the head-of-line binding before reserving memory. A
        # revoked approval should not strand host RAM merely because the
        # queued task has become unauthorized. The policy is rechecked again
        # after the atomic admission to handle concurrent approval changes.
        TaskLedger._schedule_args(owner_key)
        with self.ledger._db() as db:
            candidate=db.execute("""SELECT t.id FROM tasks t
                JOIN task_schedule s ON s.task_id=t.id
                WHERE t.state='QUEUED' AND s.owner_key=?
                ORDER BY CASE s.lane WHEN 'interactive' THEN 2
                    WHEN 'standard' THEN 1 ELSE 0 END DESC,
                    s.queued_at ASC,t.id ASC LIMIT 1""",(owner_key,)).fetchone()
        if candidate is None:
            return None
        self.verified_spec(candidate[0],owner_key=owner_key,require_active=False)
        result=self.ledger.claim_next(owner_key=owner_key)
        if result is None or not result["admitted"]:
            return result
        self.verified_spec(result["task_id"],owner_key=owner_key)
        return result
