"""Durable one-use signed SCM nonce spend, existing encrypted G03 movie HEAD.

The producer never accepts a process-local set as replay protection. This
helper lives strictly in the trusted host's unlocked-project session and uses
LiveFilmStore._change's existing OS write mutex and authenticated SQL commit.
It does not grant permission to launch, preview or approve generated media.
"""
from __future__ import annotations
import re
from backend.nvp_g03_live_store import LiveFilmStore

JOB = re.compile(r'ltx_[a-f0-9]{24}\Z')
NONCE = re.compile(r'[a-f0-9]{32}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')
PROJECT = re.compile(r'[a-f0-9]{32}\Z')

class G03ScmNonceLedger:
    def __init__(self, store: LiveFilmStore, *, project_id: str, session_token: str):
        if (not isinstance(store,LiveFilmStore) or
            type(project_id) is not str or not PROJECT.fullmatch(project_id) or
            type(session_token) is not str or not session_token):
            raise TypeError('Existing protected G03 project/session authority required')
        self.store,self.pid,self.token=store,project_id,session_token

    def __call__(self, job_id: str, receipt_nonce: str, signed_sha256: str) -> bool:
        if (any(type(x) is not str for x in (job_id,receipt_nonce,signed_sha256)) or
            not JOB.fullmatch(job_id) or not NONCE.fullmatch(receipt_nonce) or
            not SHA.fullmatch(signed_sha256)):
            raise PermissionError('Invalid signed SCM one-use receipt identity')
        receipt_id='ltx-scm:'+job_id+':'+receipt_nonce
        def commit(db,key,folder):
            if db.execute('SELECT 1 FROM worker_receipts WHERE receipt_id=?',
                          (receipt_id,)).fetchone():
                raise PermissionError('SCM signature replay at authenticated film HEAD')
            from backend.nvp_studio import now
            db.execute('INSERT INTO worker_receipts '
                       '(receipt_id,asset_name,operation,digest,recorded_at) '
                       'VALUES (?,?,?,?,?)',
                       (receipt_id,'derived_ltx/'+job_id,'scm_signed_receipt_spent',
                        signed_sha256,now()))
        try:
            self.store._change(self.pid,self.token,commit)
        except PermissionError as exc:
            if str(exc)=='SCM signature replay at authenticated film HEAD':
                return False
            raise
        return True
