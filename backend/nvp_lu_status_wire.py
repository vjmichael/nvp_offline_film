"""NVP B5: bounded, authenticated status-only messages for a future Lu host.

This does NOT enable an API in the accepted Lu alpha. The Lu-host test double
uses an ephemeral host-issued secret. No inference/model lifecycle action is
accepted, and a socket address is never a permission grant.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import time

from backend.nvp_lu_alpha_contract import LuRuntimeView
from backend.nvp_resource_ledger import TaskLedger

LIMIT=8192
REF=re.compile(r"^[a-f0-9]{32}$")
PROJECT=re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")


def canonical(data):
    result=json.dumps(data,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True).encode("ascii")
    if not 0<len(result)<=LIMIT:
        raise ValueError("Status envelope oversized")
    return result


def _pairs(items):
    out={}
    for k,v in items:
        if k in out:
            raise ValueError("Duplicated status field")
        out[k]=v
    return out


def parse(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=LIMIT:
        raise ValueError("Invalid bounded status envelope")
    try:
        result=json.loads(raw,object_pairs_hook=_pairs)
    except (ValueError,UnicodeError) as exc:
        raise ValueError("Invalid status JSON") from exc
    if not isinstance(result,dict) or canonical(result)!=raw:
        raise ValueError("Status payload must be canonical")
    return result


def authenticate(secret,purpose,body):
    return hmac.new(secret,purpose+canonical(body),hashlib.sha256).hexdigest()


def wrap(secret,purpose,body):
    return canonical({"body":body,"auth":authenticate(secret,purpose,body)})


def unwrap(secret,purpose,raw):
    doc=parse(raw)
    if set(doc)!={"auth","body"} or not isinstance(doc["body"],dict):
        raise PermissionError("Invalid host envelope")
    auth=doc["auth"]
    if not isinstance(auth,str) or not re.fullmatch("[a-f0-9]{64}",auth):
        raise PermissionError("Invalid authentication code")
    if not hmac.compare_digest(authenticate(secret,purpose,doc["body"]),auth):
        raise PermissionError("Lu status authentication failed")
    return doc["body"]


@dataclass(frozen=True)
class StatusGrant:
    project:str
    epoch:str
    key:bytes
    expires_ms:int

    def __post_init__(self):
        if (not isinstance(self.project,str) or not PROJECT.fullmatch(self.project)
            or not isinstance(self.epoch,str) or not REF.fullmatch(self.epoch)
            or not isinstance(self.key,bytes) or len(self.key)!=32
            or type(self.expires_ms) is not int or self.expires_ms<1):
            raise ValueError("Invalid host-granted read-only scope")


REQUEST=b"nvp-lu-read-status-v1\x00"
RESPONSE=b"nvp-lu-status-result-v1\x00"


def request(grant,*,now_ms=None,ident=None):
    if not isinstance(grant,StatusGrant):
        raise TypeError("Host-issued status scope required")
    now=int(time.time()*1000) if now_ms is None else now_ms
    if type(now) is not int or not 0<now<grant.expires_ms:
        raise PermissionError("Status grant expired")
    ident=secrets.token_hex(16) if ident is None else ident
    if not isinstance(ident,str) or not REF.fullmatch(ident):
        raise ValueError("Invalid fresh request identity")
    body={"v":1,"operation":"status","project":grant.project,
          "epoch":grant.epoch,"id":ident,"issued":now,
          "expires":min(now+5000,grant.expires_ms)}
    return wrap(grant.key,REQUEST,body)


class StatusHostProof:
    """A test contract, not a server enrolled in the Lu alpha desktop."""
    def __init__(self,ledger:TaskLedger,grant:StatusGrant):
        if not isinstance(ledger,TaskLedger) or not isinstance(grant,StatusGrant):
            raise TypeError("Native host grant and task ledger required")
        self.ledger=ledger;self.grant=grant
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS lu_status_nonces(
                epoch TEXT NOT NULL, request_id TEXT NOT NULL,
                PRIMARY KEY(epoch,request_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS lu_status_revoked(
                epoch TEXT NOT NULL,project TEXT NOT NULL,
                PRIMARY KEY(epoch,project))""")

    def revoke(self):
        with self.ledger._db() as db:
            db.execute("INSERT OR IGNORE INTO lu_status_revoked VALUES (?,?)",
                (self.grant.epoch,self.grant.project))

    def accept(self,raw,*,now_ms=None):
        body=unwrap(self.grant.key,REQUEST,raw)
        now=int(time.time()*1000) if now_ms is None else now_ms
        if (set(body)!={"v","operation","project","epoch","id","issued","expires"}
            or body["v"]!=1 or body["operation"]!="status"
            or body["project"]!=self.grant.project or body["epoch"]!=self.grant.epoch
            or not isinstance(body["id"],str) or not REF.fullmatch(body["id"])
            or type(now) is not int or type(body["issued"]) is not int
            or type(body["expires"]) is not int
            or not body["issued"]-1000<=now<=body["expires"]
            or body["expires"]-body["issued"]>5000
            or body["expires"]>self.grant.expires_ms):
            raise PermissionError("Rejected Lu status scope, time or operation")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM lu_status_revoked WHERE epoch=? AND project=?",
                          (self.grant.epoch,self.grant.project)).fetchone():
                db.rollback();raise PermissionError("Host revoked Lu status grant")
            if db.execute("SELECT 1 FROM lu_status_nonces WHERE epoch=? AND request_id=?",
                          (self.grant.epoch,body["id"])).fetchone():
                db.rollback();raise PermissionError("Replayed Lu status request")
            db.execute("INSERT INTO lu_status_nonces VALUES (?,?)",
                       (self.grant.epoch,body["id"]))
            db.commit()
        return body

    def respond(self,received,status,*,now_ms=None):
        checked=LuRuntimeView.from_trusted_host(status)
        now=int(time.time()*1000) if now_ms is None else now_ms
        if type(now) is not int or now<received["issued"]-1000:
            raise ValueError("Invalid host status timestamp")
        data={"modelRef":checked.model_ref,"sessionId":checked.session_id,
              "generationId":checked.generation_id,"phase":checked.phase,"pid":checked.pid}
        return wrap(self.grant.key,RESPONSE,
            {"v":1,"operation":"status_result","project":self.grant.project,
             "epoch":self.grant.epoch,"id":received["id"],"observed":now,
             "status":data})


def verify_reply(grant,original,raw,*,now_ms=None):
    req=unwrap(grant.key,REQUEST,original)
    received=unwrap(grant.key,RESPONSE,raw)
    now=int(time.time()*1000) if now_ms is None else now_ms
    if (set(received)!={"v","operation","project","epoch","id","observed","status"}
        or received["v"]!=1 or received["operation"]!="status_result"
        or received["project"]!=grant.project or received["epoch"]!=grant.epoch
        or received["id"]!=req["id"] or type(received["observed"]) is not int
        or type(now) is not int
        or not req["issued"]-1000<=received["observed"]<=now+1000):
        raise PermissionError("Unbound, altered or future Lu status response")
    checked=LuRuntimeView.from_trusted_host(received["status"])
    return {"modelRef":checked.model_ref,"sessionId":checked.session_id,
            "generationId":checked.generation_id,"phase":checked.phase,"pid":checked.pid}
