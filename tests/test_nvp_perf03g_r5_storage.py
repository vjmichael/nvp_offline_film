"""Portable sealed payload migration; Windows qualification uses real DPAPI/pxr."""
import hashlib
import json
import shutil
import sys
import unittest
from unittest.mock import patch

from backend import nvp_g03_payloads as payloads
from backend.nvp_g03_live_backup import create_backup, restore_copy, restore_detached
from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g07_paged_media import delivery_plan
from backend.nvp_g07_preview import paged_sound
from test_nvp_perf03g_r4_protected_output import Fixture, SECRET, T


class R5Portable(unittest.TestCase):
    def setUp(self):self.f=Fixture(self)

    def migrate(self,family,after=None):
        f=self.f;r=payloads.review(f.store,f.pid,f.token,family,after)
        return payloads.migrate(f.store,f.pid,f.token,family,after,r['approval_digest'],human_approved=True)

    def test_edl_history_active_and_future_write(self):
        f=self.f;before=f.store._head(f.folder);active=f.editor.view(f.pid);directory=f.service.directory(f.pid,'edits');plan=delivery_plan(f.service,f.pid,2,f.digest)
        review=payloads.review(f.store,f.pid,f.token,'edl')
        self.assertEqual(len(review['entries']),2)
        with self.assertRaises(PermissionError):payloads.migrate(f.store,f.pid,f.token,'edl',None,review['approval_digest'])
        self.assertEqual(before,f.store._head(f.folder))
        self.assertEqual(self.migrate('edl')['migrated'],2)
        self.assertEqual(active,f.editor.view(f.pid));self.assertEqual(directory,f.service.directory(f.pid,'edits'));self.assertEqual(plan,delivery_plan(f.service,f.pid,2,f.digest))
        self.assertTrue((f.folder/'revisions'/before['name']).is_file())
        # Native restore still produces a new revision, not an overwrite.
        restored=f.editor.restore(f.pid,1,2);self.assertEqual(restored['revision'],3)
        def read(db,movie):
            rows=list(db.execute('SELECT revision,document_json,document_sha256 FROM g07_edit_versions ORDER BY revision'))
            for row in rows:
                raw=json.loads(row['document_json']);self.assertEqual(raw['storage'],payloads.POINTER)
                payloads.resolve_edit(db,f.pid,row['revision'],row['document_json'],row['document_sha256'])
            self.assertEqual(rows[0]['document_sha256'],rows[2]['document_sha256'])
        f.editor._execute(f.pid,read)
        self.assertIn(1,[r['revision'] for r in f.editor.view(f.pid)['history']])

    def test_source_migration_preserves_original_exact_bytes_and_admission_budget(self):
        f=self.f
        def records(db,movie):
            out={}
            for r in db.execute('SELECT take_id,original_usd_sha256,performance_usd_sha256 FROM g06_frozen_takes'):
                tid=r['take_id'];p=payloads.read_take_payloads(db,f.pid,tid);meta,_doc,_audio=f.editor.filming._take_metadata(db,f.pid,tid)
                out[tid]=(p,meta['original_usd_size'],meta['performance_usd_size'])
            return out
        old=f.editor._execute(f.pid,records)
        with f.portable_usd():before=paged_sound(f.service,f.pid,2,f.digest,7*T//4,T//4)
        self.assertEqual(self.migrate('take')['migrated'],len(old))
        self.assertEqual(old,f.editor._execute(f.pid,records))
        f.editor._execute(f.pid,lambda db,movie:self.assertTrue(all(r[0]==r[1]==0 for r in db.execute('SELECT length(original_usd),length(performance_usd) FROM g06_frozen_takes'))))
        with f.portable_usd():self.assertEqual(before,paged_sound(f.service,f.pid,2,f.digest,7*T//4,T//4))
        # Restore a finite edit to exercise the G07 native assembly reader too.
        f.editor.restore(f.pid,1,2)
        with f.portable_usd():
            result=f.editor.native_assembly(f.pid,3,window=(0,T))
        self.assertTrue(result)

    def test_stale_review_and_interrupted_publication(self):
        f=self.f;review=payloads.review(f.store,f.pid,f.token,'edl');f.store.save_screenplay(f.pid,f.token,'INT. ROOM - DAY',0)
        with self.assertRaises(PermissionError):payloads.migrate(f.store,f.pid,f.token,'edl',None,review['approval_digest'],human_approved=True)
        before=f.store._head(f.folder);r=payloads.review(f.store,f.pid,f.token,'edl')
        # Simulated HEAD publication interruption after immutable object seal.
        with patch.object(f.store,'_publish_head',side_effect=OSError('simulated interrupted HEAD publication')):
            with self.assertRaises(OSError):payloads.migrate(f.store,f.pid,f.token,'edl',None,r['approval_digest'],human_approved=True)
        self.assertEqual(before,f.store._head(f.folder));self.assertEqual(f.editor.view(f.pid)['active_digest'],f.digest)
        self.assertEqual(self.migrate('edl')['migrated'],2);self.assertEqual(f.editor.view(f.pid)['active_digest'],f.digest)

    def test_tamper_missing_foreign_and_backup(self):
        f=self.f;self.migrate('edl');self.migrate('take');f.migrate()
        parent=f.root/'backup';parent.mkdir();dest=f.root/'restored';dest.mkdir()
        before=f.store._head(f.folder);create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
        restore_copy(f.store,f.pid,f.token,parent/('NVP-'+f.pid+'-backup'),dest,guard=f.guard,human_approved=True)
        new=LiveFilmStore(dest);new._keys[f.token]=(f.pid,f.key);editor=G07Editor(f.studio,live=new,token=f.token)
        self.assertEqual(editor.view(f.pid)['active_digest'],f.digest);self.assertEqual(new._head(dest/f.pid),before)
        def read(db,movie):
            row=db.execute('SELECT revision,document_json,document_sha256 FROM g07_edit_versions WHERE revision=2').fetchone()
            with self.assertRaises(VaultError):payloads.resolve_edit(db,'f'*32,2,row['document_json'],row['document_sha256'])
            return row['document_sha256']
        sha=f.editor._execute(f.pid,read);name,_=payloads._identity('edl',2,sha);path=payloads._path(f.folder,f.key,name)/'body.nvpsealed';raw=path.read_bytes()
        path.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        with self.assertRaises(VaultError):f.editor.view(f.pid)
        other=f.root/'other';other.mkdir()
        with self.assertRaises(VaultError):create_backup(f.store,f.pid,f.token,other,guard=f.guard,human_approved=True)
        path.write_bytes(raw);self.assertEqual(f.editor.view(f.pid)['active_digest'],f.digest)
        path.unlink()
        with self.assertRaises(VaultError):f.editor.view(f.pid)
        self.assertEqual(f.store._head(f.folder),before)

    def test_corrupt_original_and_revocation_fail_closed(self):
        f=self.f;r=payloads.review(f.store,f.pid,f.token,'take');tid=r['entries'][0]['id']
        # Tampered fixture changes original bytes without altering the digest.
        f.editor._execute(f.pid,lambda db,movie:db.execute('UPDATE g06_frozen_takes SET original_usd=zeroblob(length(original_usd)) WHERE take_id=?',(tid,)),mutate=True)
        head=f.store._head(f.folder);r=payloads.review(f.store,f.pid,f.token,'take')
        with self.assertRaises(VaultError):payloads.migrate(f.store,f.pid,f.token,'take',None,r['approval_digest'],human_approved=True)
        self.assertEqual(head,f.store._head(f.folder));f.store.revoke(f.pid)
        with self.assertRaises(VaultError):payloads.review(f.store,f.pid,f.token,'edl')

    def test_native_migration_selection_and_refusal(self):
        from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog,optimize_payloads_with_dialog
        f=self.f;origin='http://127.0.0.1:43210';choices=[False];urls=[origin+'/'];prompts=[]
        class Window:
            def get_current_url(self):return urls[0]
            def create_file_dialog(self,*a,**k):raise AssertionError('No file picker needed')
            def create_confirmation_dialog(self,*args):prompts.append(args);return choices[0]
        dialog=NativeRecoveryDialog(Window(),origin)
        before=f.store._head(f.folder)
        self.assertTrue(optimize_payloads_with_dialog(f.service,f.pid,origin,dialog,'edl')['cancelled'])
        self.assertEqual(before,f.store._head(f.folder));choices[0]=True
        result=optimize_payloads_with_dialog(f.service,f.pid,origin,dialog,'edl');self.assertEqual(result['migrated'],2);self.assertTrue(result['complete'])
        self.assertTrue(optimize_payloads_with_dialog(f.service,f.pid,origin,dialog,'edl')['complete']);self.assertEqual(len(prompts),2)
        urls[0]='https://untrusted.example/'
        with self.assertRaises(PermissionError):optimize_payloads_with_dialog(f.service,f.pid,origin,dialog,'take')

    def test_sealed_new_take_and_detached_backup_recovery(self):
        f=self.f;self.migrate('edl');self.migrate('take');f.migrate()
        # Exercise new-Take storage primitive in same trusted transaction as
        # fixture-only new immutable Take insert. No real camera capture claim.
        def insert(db,movie):
            row=dict(db.execute('SELECT * FROM g06_frozen_takes ORDER BY take_id LIMIT 1').fetchone());raw=payloads.read_take_payloads(db,f.pid,row['take_id']);tid='f'*32
            self.assertTrue(payloads.enabled(db,f.pid,'take'))
            row['original_usd'],row['performance_usd']=payloads.seal_new_take(db,f.pid,tid,raw['original_usd'],raw['performance_usd']);row['take_id']=tid
            fields=list(row);db.execute('INSERT INTO g06_frozen_takes('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(row[x] for x in fields))
            self.assertEqual(payloads.read_take_payloads(db,f.pid,tid),raw)
        f.editor._execute(f.pid,insert,mutate=True)
        backup=f.root/'backup';backup.mkdir();dest=f.root/'detached';dest.mkdir()
        create_backup(f.store,f.pid,f.token,backup,guard=f.guard,human_approved=True)
        f.store.revoke(f.pid);shutil.rmtree(f.folder);self.assertFalse(f.folder.exists())
        # Public fixture key only; actual backup MAC, ciphertext and restore
        # execute without substitutions. Real DPAPI test below is separate.
        with patch('backend.nvp_g03_windows_vault._key_open',return_value=f.key):
            restored=restore_detached(f.pid,SECRET,backup/('NVP-'+f.pid+'-backup'),dest,guard=lambda:None,human_approved=True)
        self.assertTrue(restored['restored_copy']);self.assertFalse(restored['active_registration_created'])
        store=LiveFilmStore(dest);store._keys[f.token]=(f.pid,f.key);editor=G07Editor(f.studio,live=store,token=f.token)
        self.assertEqual(editor.view(f.pid)['active_digest'],f.digest)

    def test_bounded_review_compacts_historical_edl(self):
        f=self.f
        # Save valid immutable finite EDL revisions, exercising history rather than fake long movie duration.
        def save(db,movie):
            from backend.nvp_g07_edit import G07Editor
            row=db.execute('SELECT document_json FROM g07_edit_versions WHERE revision=1').fetchone();doc=json.loads(row[0]);rev=2
            for i in range(20):
                doc['notes']='a'*1800+str(i);rev=G07Editor._save(db,f.pid,doc,rev,rev)
        f.editor._execute(f.pid,save,mutate=True)
        old=f.store._head(f.folder);old_bytes=(f.folder/'revisions'/old['name']).stat().st_size
        n=0;after=None
        while True:
            r=payloads.review(f.store,f.pid,f.token,'edl',after);self.assertLessEqual(len(r['entries']),payloads.BATCH)
            result=payloads.migrate(f.store,f.pid,f.token,'edl',after,r['approval_digest'],human_approved=True);n+=result['migrated'];after=result['next_after']
            if after is None:break
        self.assertEqual(n,22);head=f.store._head(f.folder);new_bytes=(f.folder/'revisions'/head['name']).stat().st_size
        self.assertLess(new_bytes,old_bytes);self.assertTrue((f.folder/'revisions'/old['name']).is_file())
        print(f'R5_EDL_STORAGE_FIXTURE count={n} current_snapshot_before={old_bytes} after={new_bytes}')


@unittest.skipUnless(sys.platform=='win32','Real Windows DPAPI and OpenUSD required')
class R5Native(unittest.TestCase):
    def test_original_source_and_detached_recovery(self):
        f=Fixture(self,native=True)
        for family in ('edl','take'):
            review=payloads.review(f.store,f.pid,f.token,family)
            payloads.migrate(f.store,f.pid,f.token,family,None,review['approval_digest'],human_approved=True)
        before=paged_sound(f.service,f.pid,2,f.digest,7*T//4,T//4)
        parent=f.root/'backup';parent.mkdir();recovered=f.root/'recovered';recovered.mkdir()
        create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
        f.store.revoke(f.pid);shutil.rmtree(f.folder)
        restore_detached(f.pid,SECRET,parent/('NVP-'+f.pid+'-backup'),recovered,guard=lambda:None,human_approved=True)
        store=LiveFilmStore(recovered);store.authorize(f.pid,SECRET,f.token)
        editor=G07Editor(f.studio,live=store,token=f.token);service=EditorialSections(editor,access_guard=lambda:store._session(f.pid,f.token))
        self.assertEqual(editor.view(f.pid)['active_digest'],f.digest);self.assertEqual(paged_sound(service,f.pid,2,f.digest,7*T//4,T//4),before)
