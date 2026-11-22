"""Portable R5 contract tests with real AES-GCM and FAKE Windows/DPAPI/SCM.

These are not installed Windows EFS, physical GPU, or SCM acceptance evidence.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CANDIDATE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CANDIDATE))

class FakeLiveFilmStore:
    def __init__(self,root):
        self._guard=threading.RLock()
        self.root=root
        self.pid='a'*32
        self.key=os.urandom(32)
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE worker_receipts(receipt_id TEXT PRIMARY KEY, '
                   'asset_name TEXT, operation TEXT, digest TEXT, recorded_at TEXT)')
        db.commit()
        self.serial=db.serialize();db.close()
        (root/self.pid).mkdir()
    def _folder(self,pid):
        if pid!=self.pid:raise PermissionError('foreign')
        return self.root/pid
    def _session(self,pid,token):
        if pid!=self.pid or token!='active-session':raise PermissionError('locked')
        return self.key
    def _read_db(self,folder,pid,key):
        if folder!=self._folder(pid) or key!=self.key:raise PermissionError('foreign')
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.deserialize(self.serial)
        return db,{'sequence':1}
    def _change(self,pid,token,mutator):
        key=self._session(pid,token)
        db,_=self._read_db(self._folder(pid),pid,key)
        try:
            mutator(db,key,self._folder(pid))
            db.commit();self.serial=db.serialize()
        finally:db.close()

MAGIC=b'NVPFILM1\x00'
def fake_encrypt(inp,target,*,key,project_id,name):
    data=inp.read()
    nonce=os.urandom(12)
    ciphertext=MAGIC+nonce+AESGCM(key).encrypt(nonce,data,(project_id+'/'+name).encode())
    with target.open('xb') as f:
        f.write(ciphertext);f.flush();os.fsync(f.fileno())
    return {'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
def fake_decrypt(source,out,*,key,project_id,name,max_plain_bytes=None,**ignored):
    raw=source.read_bytes()
    if not raw.startswith(MAGIC):raise PermissionError('invalid G03 ciphertext')
    nonce=raw[len(MAGIC):len(MAGIC)+12]
    data=AESGCM(key).decrypt(nonce,raw[len(MAGIC)+12:],(project_id+'/'+name).encode())
    if max_plain_bytes is not None and len(data)>max_plain_bytes:raise PermissionError('limit')
    out.write(data)
    return {'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
def no_link(path):
    if path.is_symlink() or not path.exists():raise PermissionError('linked/missing')

LIVE=types.ModuleType('backend.nvp_g03_live_store');LIVE.LiveFilmStore=FakeLiveFilmStore
VAULT=types.ModuleType('backend.nvp_g03_windows_vault')
VAULT._encrypt_file=fake_encrypt;VAULT._decrypt_file=fake_decrypt;VAULT._no_link=no_link
EFS=types.ModuleType('backend.nvp_w1g_encrypted_source')
EFS.require_efs_stage=lambda root:True
EFS.verify_efs_inputs=lambda root,names=():True
STUDIO=types.ModuleType('backend.nvp_studio');STUDIO.now=lambda:'2026-11-20T20:00:00Z'
FAKES={LIVE.__name__:LIVE,VAULT.__name__:VAULT,EFS.__name__:EFS,STUDIO.__name__:STUDIO}

class R5EncryptedDerivedPicture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.dict(sys.modules,FAKES):
            spec=importlib.util.spec_from_file_location('r5_review_test_module',CANDIDATE/'backend/nvp_post01f_encrypted_review.py')
            cls.module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.patch=mock.patch.dict(sys.modules,FAKES)
        self.patch.start()
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.patch.stop)
        self.store=FakeLiveFilmStore(Path(self.tmp.name))
        self.take_ok=True;self.creator_ok=True;self.native_ok=True
        self.review=self.module.EncryptedLtxReview(self.store,
            verify_original_take=lambda _:self.take_ok,
            authenticate_creator_decision=lambda scope,event:self.creator_ok,
            confirm_native_admission=lambda scope:self.native_ok,
            quarantine_root=Path(self.tmp.name))
        self.worker=Path(self.tmp.name)/('ltx_'+'1'*24)
        self.worker.mkdir()
        self.movie=self.worker/'picture.mp4'
        self.movie.write_bytes(b'frame-backed-media-test-only!')
        (self.worker/'result.json').write_bytes(b'not-an-LTX-output')
        self.pid=self.store.pid
        self.job=self.worker.name
        self.picsha=hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.result={'state':'PICTURE_VERIFIED_UNAPPROVED',
                     'job_id':self.job,'project_id':self.pid,
                     'picture_sha256':self.picsha,'source_take_sha256':'2'*64,
                     'model_stack_sha256':'3'*64,
                     'plan_sha256':'4'*64,
                     'scm_receipt_sha256':'5'*64,
                     'picture_location':str(self.movie),
                     'creator_approved':False,'publishable':False}
        self.window=mock.patch.object(self.module,'_windows_required',return_value=None)
        self.window.start();self.addCleanup(self.window.stop)

    def pub(self):
        return self.review.publish_pending(self.pid,'active-session',result=self.result)

    def test_encrypted_pending_review_and_no_original_asset_mutation(self):
        self.assertEqual(self.pub()['status'],'ENCRYPTED_PICTURE_UNAPPROVED')
        target=self.store._folder(self.pid)/'derived_ltx'/self.job
        self.assertEqual(set(x.name for x in target.iterdir()),
                         {'picture.nvpsealed','manifest.nvpsealed'})
        self.assertNotIn(self.movie.read_bytes(),(target/'picture.nvpsealed').read_bytes())
        self.assertEqual(self.review.review(self.pid,'active-session',self.job)['status'],
                         'PICTURE_VERIFIED_UNAPPROVED')

    def test_real_authenticated_aes_gcm_tamper_refusal(self):
        self.pub()
        media=self.store._folder(self.pid)/'derived_ltx'/self.job/'picture.nvpsealed'
        raw=bytearray(media.read_bytes());raw[-1]^=1;media.write_bytes(raw)
        with self.assertRaises(Exception):self.review.review(self.pid,'active-session',self.job)

    def test_creator_approval_is_immutable_and_reopens(self):
        self.pub()
        done=self.review.decide(self.pid,'active-session',self.job,action='approve',creator_event=b'auth-click')
        self.assertEqual(done['status'],'CREATOR_APPROVED')
        self.assertEqual(self.review.review(self.pid,'active-session',self.job)['status'],'CREATOR_APPROVED')
        with self.assertRaises(PermissionError):self.review.decide(self.pid,'active-session',self.job,
                                                        action='reject',creator_event=b'changed')

    def test_reject_refuses_approval_replay(self):
        self.pub();self.review.decide(self.pid,'active-session',self.job,
                                     action='reject',creator_event=b'auth-click')
        self.assertEqual(self.review.review(self.pid,'active-session',self.job)['status'],'CREATOR_REJECTED')
        with self.assertRaises(PermissionError):self.review.decide(self.pid,'active-session',self.job,
                                             action='approve',creator_event=b'replay')

    def test_missing_native_admission_refuses_before_storage(self):
        self.native_ok=False
        with self.assertRaises(PermissionError):self.pub()
        self.assertFalse((self.store._folder(self.pid)/'derived_ltx').exists())

    def test_wrong_source_or_unverified_take_refuses(self):
        self.take_ok=False
        with self.assertRaises(PermissionError):self.pub()
        self.take_ok=True;self.pub();self.take_ok=False
        with self.assertRaises(PermissionError):self.review.review(self.pid,'active-session',self.job)

    def test_missing_live_session_denies_review(self):
        self.pub()
        with self.assertRaises(PermissionError):self.review.review(self.pid,'expired',self.job)

    def test_unindexed_ciphertext_orphan_is_not_reviewable(self):
        self.pub()
        db=sqlite3.connect(':memory:');db.deserialize(self.store.serial)
        db.execute('DELETE FROM worker_receipts WHERE operation=?',('derived_picture_sealed',))
        db.commit();self.store.serial=db.serialize();db.close()
        with self.assertRaises(PermissionError):self.review.review(self.pid,'active-session',self.job)

    def test_deleted_decision_cannot_revert_to_pending(self):
        self.pub()
        self.review.decide(self.pid,'active-session',self.job,action='approve',creator_event=b'auth')
        target=self.store._folder(self.pid)/'derived_ltx'/self.job
        (target/'decision.nvpsealed').unlink()
        with self.assertRaises(PermissionError):self.review.review(self.pid,'active-session',self.job)

    def test_decision_without_authenticated_head_receipt_refuses(self):
        self.pub()
        self.review.decide(self.pid,'active-session',self.job,action='approve',creator_event=b'auth')
        db=sqlite3.connect(':memory:');db.deserialize(self.store.serial)
        db.execute('DELETE FROM worker_receipts WHERE operation=?',('derived_review_sealed',))
        db.commit();self.store.serial=db.serialize();db.close()
        with self.assertRaises(PermissionError):self.review.review(self.pid,'active-session',self.job)

    def test_duplicate_generation_result_cannot_overwrite(self):
        self.pub()
        with self.assertRaises(FileExistsError):self.pub()

    def test_refused_creator_consent_makes_no_decision(self):
        self.pub();self.creator_ok=False
        with self.assertRaises(PermissionError):self.review.decide(self.pid,'active-session',self.job,
                                                        action='approve',creator_event=b'bad')
        self.assertEqual(self.review.review(self.pid,'active-session',self.job)['status'],
                         'PICTURE_VERIFIED_UNAPPROVED')

    def test_unreviewed_presentation_sidecar_denied(self):
        self.pub()
        (self.store._folder(self.pid)/'derived_ltx'/self.job/'audio.wav').write_bytes(b'no')
        with self.assertRaises(PermissionError):self.review.review(self.pid,'active-session',self.job)

    def test_stale_partial_and_wrong_project_refused(self):
        self.pub()
        (self.store._folder(self.pid)/'derived_ltx'/(self.job+'.partial')).mkdir()
        with self.assertRaises(PermissionError):self.review.review(self.pid,'active-session',self.job)
        with self.assertRaises(PermissionError):self.review.review('b'*32,'active-session',self.job)

if __name__=='__main__':unittest.main()
