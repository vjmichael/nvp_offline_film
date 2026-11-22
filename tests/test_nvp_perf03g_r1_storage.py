"""Real AES-GCM storage and bounded hierarchy tests; no fake DPAPI claim."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_g03_windows_vault import _encrypt_file,_decrypt_file,VaultError
from backend.nvp_g03_live_store import LiveFilmStore,LiveFilmError
from backend.nvp_g07_section_pages import seal_page,read_page,resolve,MAX_BYTES,FORMAT
import test_nvp_perf03g_sections as fixtures
from test_nvp_perf03g_sections import saved, ref, T

PID='a'*32
KEY=b'\x19'*32 # disposable public fixture key, no user key or DPAPI substitute

class SealedPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.raw=json.dumps({'title':'PRIVATE_EDIT_MARKER','children':['cut']*96},separators=(',',':'))
        self.sha=hashlib.sha256(self.raw.encode()).hexdigest()
    def test_real_ciphertext_immutable_page_and_legacy_inline(self):
        pointer=seal_page(self.root,PID,KEY,self.raw,self.sha)
        self.assertEqual(json.loads(pointer),{'format':FORMAT,'sha256':self.sha})
        self.assertEqual(resolve(pointer,self.sha,folder=self.root,pid=PID,key=KEY),self.raw)
        files=list(self.root.rglob('*.nvpsealed'));self.assertEqual(len(files),1)
        ciphertext=files[0].read_bytes();self.assertNotIn(b'PRIVATE_EDIT_MARKER',ciphertext)
        self.assertEqual(seal_page(self.root,PID,KEY,self.raw,self.sha),pointer)
        self.assertEqual(files[0].read_bytes(),ciphertext)
        self.assertEqual(resolve(self.raw,self.sha),self.raw)
        with self.assertRaises(VaultError):resolve(pointer,self.sha)
        with self.assertRaises(VaultError):read_page(self.root,'b'*32,KEY,self.sha)
    def test_tamper_and_missing_page_fail_closed(self):
        pointer=seal_page(self.root,PID,KEY,self.raw,self.sha)
        path=next(self.root.rglob('*.nvpsealed'));raw=bytearray(path.read_bytes());raw[-30]^=1;path.write_bytes(raw)
        with self.assertRaises(VaultError):resolve(pointer,self.sha,folder=self.root,pid=PID,key=KEY)
        with self.assertRaises(VaultError):seal_page(self.root,PID,KEY,self.raw,self.sha)
        path.unlink()
        with self.assertRaises(VaultError):resolve(pointer,self.sha,folder=self.root,pid=PID,key=KEY)
    def test_bounded_preflight_rejects_before_decrypt(self):
        raw='x'*(MAX_BYTES+1);sha=hashlib.sha256(raw.encode()).hexdigest()
        with self.assertRaises(VaultError):seal_page(self.root,PID,KEY,raw,sha)
        self.assertEqual(list(self.root.iterdir()),[])
        path=self.root/'oversize';_encrypt_file(io.BytesIO(raw.encode()),path,key=KEY,project_id=PID,name='oversize')
        sink=io.BytesIO()
        with self.assertRaises(VaultError):_decrypt_file(path,sink,key=KEY,project_id=PID,name='oversize',max_plain_bytes=MAX_BYTES)
        self.assertEqual(sink.getvalue(),b'')
    def test_pinned_ciphertext_identity_checked_on_same_read(self):
        path=self.root/'snapshot';_encrypt_file(io.BytesIO(b'source'),path,key=KEY,project_id=PID,name='snapshot')
        sha=hashlib.sha256(path.read_bytes()).hexdigest();sink=io.BytesIO()
        _decrypt_file(path,sink,key=KEY,project_id=PID,name='snapshot',expected_ciphertext_sha256=sha,max_plain_bytes=6)
        self.assertEqual(sink.getvalue(),b'source')
        with self.assertRaises(VaultError):_decrypt_file(path,io.BytesIO(),key=KEY,project_id=PID,name='snapshot',expected_ciphertext_sha256='f'*64)
    def test_live_snapshot_does_not_allocate_ciphertext_read_bytes(self):
        (self.root/'revisions').mkdir();store=LiveFilmStore(self.root)
        db=store._new_sqlite('Fixture','','');raw=db.serialize();db.close()
        record=store._seal_db(self.root,PID,KEY,raw,0);store._publish_head(self.root,record)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('full ciphertext read')):
            opened,head=store._read_db(self.root,PID,KEY)
            try:self.assertEqual(opened.execute('select title from film_metadata').fetchone()[0],'Fixture')
            finally:opened.close()
        self.assertEqual(head,record)
        store._publish_head(self.root,{**record,'sha256':'f'*64})
        with self.assertRaises(LiveFilmError):store._read_db(self.root,PID,KEY)

class GroupNativeTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.SectionsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.editor,self.source,self.pid,self.doc,self.edit=fixture.editor,fixture.source,fixture.pid,fixture.doc,fixture.edit
    def test_native_selected_group_reopens_exact_receipt_before_media(self):
        group=saved(self.source,self.pid,'Reordered',[ref(self.edit,2,2),ref(self.edit,0,2)])
        preview=self.source.preview_activation(self.pid,group['section_id'],group['digest'],1)
        self.source.activate(self.pid,group['section_id'],group['digest'],1,preview['approval_digest'])
        from backend.nvp_g07_edit import _project
        def inspect(db,movie):
            revision,doc=_project(db,self.pid)
            return self.source.verify_activated_edit(db,self.pid,revision,doc)
        self.assertEqual(self.editor._execute(self.pid,inspect)['duration_tick'],8*T)
        def alter(db,movie):db.execute('UPDATE g07_section_activations SET approval_digest=? WHERE project_id=?',( 'f'*64,self.pid))
        self.editor._execute(self.pid,alter,mutate=True)
        with self.assertRaisesRegex(RuntimeError,'Active grouped cut'):
            self.editor.native_assembly(self.pid,2,window=(0,T))
    def test_late_cut_page_past_legacy_active_limit(self):
        children=[saved(self.source,self.pid,f'Act {i}',[ref(self.edit)]) for i in range(64)]
        group=saved(self.source,self.pid,'Working material',[ref(x) for x in children]);page=self.source.cut_page(self.pid,group['section_id'],group['digest'],first=251,limit=4)
        self.assertEqual([x['index'] for x in page['items']],[251,252,253,254]);self.assertEqual(page['items'][0]['start_tick'],502*T)
        self.assertEqual(page['next_first'],255);self.assertFalse(page['render_approved'])
        self.assertEqual(self.source.cut_page(self.pid,group['section_id'],group['digest'],first=255)['next_first'],None)
        with self.assertRaises(ValueError):self.source.cut_page(self.pid,group['section_id'],group['digest'],limit=65)
        with self.assertRaises(ValueError):self.source.preview_activation(self.pid,group['section_id'],group['digest'],1)

# unittest discovery must not re-run the imported fixture class.
