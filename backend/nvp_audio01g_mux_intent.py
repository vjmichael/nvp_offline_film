"""Durable AUDIO-01G mux intent and inspection state."""
from __future__ import annotations
import sqlite3


def install(ledger):
    with ledger._db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS audio01g_mux_intents(
          job_id TEXT PRIMARY KEY, plan_sha TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN
            ('prepared','running','quarantined','verified','committed')),
          result_sha TEXT)""")


def prepare(ledger, job_id, plan_sha):
    install(ledger)
    with ledger._db() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO audio01g_mux_intents VALUES(?,?,'prepared',NULL)",
                   (job_id,plan_sha))
        db.commit()


def read(ledger, job_id):
    install(ledger)
    with ledger._db() as db:
        row=db.execute("SELECT plan_sha,state,result_sha FROM audio01g_mux_intents WHERE job_id=?",
                       (job_id,)).fetchone()
    if row is None:
        raise KeyError("No durable audio mux intent")
    return {"plan_sha":row[0],"state":row[1],"result_sha":row[2]}


_TRANSITIONS={
    "prepared":frozenset({"running"}),
    "running":frozenset({"quarantined","verified"}),
    "quarantined":frozenset({"verified"}),
    "verified":frozenset({"committed"}),
    "committed":frozenset(),
}


def transition(ledger, job_id, previous, next_state, result_sha=None):
    if next_state not in _TRANSITIONS.get(previous,()):
        raise RuntimeError("Illegal native mux publication transition")
    if next_state in ("verified","committed"):
        if (type(result_sha) is not str or len(result_sha)!=64 or
            any(ch not in "0123456789abcdef" for ch in result_sha)):
            raise ValueError("Verified mux result SHA-256 is required")
    elif result_sha is not None:
        raise ValueError("Unverified mux cannot carry a result digest")
    with ledger._db() as db:
        db.execute("BEGIN IMMEDIATE")
        changed=db.execute("""UPDATE audio01g_mux_intents SET state=?,result_sha=?
            WHERE job_id=? AND state=?""",
            (next_state,result_sha,job_id,previous)).rowcount
        if changed!=1:
            db.rollback()
            raise RuntimeError("Stale mux publication transition")
        db.commit()
