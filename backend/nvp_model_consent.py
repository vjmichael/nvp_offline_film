"""Native-only, finite, hash-bound model-load consent. Not a model API."""
from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
import secrets
import time
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_owned_models import OwnedCpuModelOperation
from backend.nvp_resource_ledger import TaskLedger


class NativeModelConsent:
    def __init__(self,ledger:TaskLedger):
        if not isinstance(ledger,TaskLedger):
            raise TypeError("A native durable task ledger is required")
        self.ledger=ledger
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS model_load_consents (
                approval_id TEXT PRIMARY KEY, document_sha256 TEXT NOT NULL,
                task_id TEXT NOT NULL UNIQUE, model_key TEXT NOT NULL,
                context_length INTEGER NOT NULL, conservative_ram_mb INTEGER NOT NULL,
                issued_at REAL NOT NULL, expires_at REAL NOT NULL, revoked_at REAL
            )""")

    def issue_from_trusted_ui(self,operation:OwnedCpuModelOperation,*,duration_s:int):
        """Host must validate an actual creator click; model/browser cannot call."""
        if not isinstance(operation,OwnedCpuModelOperation):
            raise TypeError("A sealed estimated native CPU model request is required")
        if type(duration_s) is not int or not 10<=duration_s<=3600:
            raise ValueError("Consent must have an explicitly bounded lifetime")
        digest=sha256(canonical_bytes(asdict(operation))).hexdigest()
        approval_id="consent_"+secrets.token_hex(16)
        now=time.time()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO model_load_consents
                (approval_id,document_sha256,task_id,model_key,context_length,
                 conservative_ram_mb,issued_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (approval_id,digest,operation.task_id,operation.model_key,
                 operation.context_length,operation.conservative_ram_mb,now,now+duration_s))
            db.commit()
        return approval_id

    def check(self,approval_id,spec_digest,document):
        if not isinstance(approval_id,str) or not isinstance(document,dict):
            return False
        with self.ledger._db() as db:
            row=db.execute("""SELECT document_sha256,task_id,model_key,context_length,
                conservative_ram_mb,issued_at,expires_at,revoked_at
                FROM model_load_consents WHERE approval_id=?""",(approval_id,)).fetchone()
        if row is None:
            return False
        digest,task_id,key,context,ram,issued,expires,revoked=row
        return (revoked is None and issued<=time.time()<=expires and
                spec_digest==digest==sha256(canonical_bytes(document)).hexdigest() and
                document.get("task_id")==task_id and document.get("model_key")==key and
                document.get("context_length")==context and
                document.get("conservative_ram_mb")==ram and
                document.get("kind")=="ai_loading")

    def revoke_from_trusted_ui(self,approval_id):
        if not isinstance(approval_id,str) or not approval_id.startswith("consent_"):
            raise ValueError("Invalid native approval identifier")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            cur=db.execute("""UPDATE model_load_consents SET revoked_at=?
                WHERE approval_id=? AND revoked_at IS NULL""",(time.time(),approval_id))
            if cur.rowcount!=1:
                raise KeyError("Consent missing or already revoked")
            db.commit()
        return {"approval_id":approval_id,"revoked":True}
