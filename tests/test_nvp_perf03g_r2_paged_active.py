"""Actual SQLite and AES-GCM metadata acceptance, separate from Windows DPAPI.

The tiny original Take fixtures do not represent rendered footage or playback.
"""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_g03_live_store import LiveFilmStore, LiveFilmError
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g07_edit import G07Editor, _blank, _project
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g07_paged_active import FORMAT
from backend.nvp_g07_section_pages import _location
from backend.nvp_studio import Studio
from backend.nvp_g06_filming import _json,_sha
from test_nvp_perf03g_sections import fixture_take, saved, ref, T, SECRET, HEADERS


def seed_large(editor,pid):
    def put(db,movie):
        for rev in range(2):
            doc=_blank();doc['title']=f'Act {rev+1}'
            doc['clips']=[fixture_take(db,pid,n) for n in range(1+rev*140,141+rev*140)]
            editor._validate(db,pid,doc);editor._save(db,pid,doc,rev,rev)
    editor._execute(pid,put,mutate=True)
    service=EditorialSections(editor)
    first,last=service.directory(pid,'edits')['items']
    a=saved(service,pid,'First act',[ref(first)])
    b=saved(service,pid,'Second act',[ref(last)])
    return service,saved(service,pid,'Feature arrangement',[ref(a),ref(b)]),a,b


def activate(service,pid,group,rev=2):
    args=(pid,group['section_id'],group['digest'],rev)
    preview=service.preview_paged(*args)
    assert preview['paged'] and not preview['render_approved']
    return service.activate_paged(*args,preview['approval_digest'])


class PagedActiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/'studio.sqlite3');self.pid=self.studio.create_project('Fixture','')['id']
        self.editor=G07Editor(self.studio)
        self.service,self.group,self.a,self.b=seed_large(self.editor,self.pid)
    def activate(self):
        return activate(self.service,self.pid,self.group)
    def test_compact_same_head_late_page_and_native_exact_clocks(self):
        self.assertEqual(self.activate()['clip_count'],280)
        view=self.editor.view(self.pid);self.assertEqual(view['format'],FORMAT)
        self.assertEqual(view['revision'],3);self.assertEqual(view['timeline'],[])
        rev,doc=self.editor._execute(self.pid,lambda db,movie:_project(db,self.pid,allow_paged=True))
        self.assertEqual(rev,3);self.assertLess(len(_json(doc)),768)
        with patch.object(self.editor.filming,'_take',side_effect=AssertionError('No original media load')):
            page=self.service.active_page(self.pid,3,view['active_digest'],135,16,native=True)
        self.assertEqual([x['index'] for x in page['items']],list(range(135,151)))
        self.assertEqual(page['items'][0]['start_tick'],270*T);self.assertEqual(page['items'][-1]['end_tick'],302*T)
        self.assertEqual(page['items'][5]['source_revision'],2)
        end=self.service.active_page(self.pid,3,view['active_digest'],279,64)
        self.assertEqual(end['items'][0]['index'],279);self.assertIsNone(end['next_first']);self.assertNotIn('take_id',end['items'][0])
        self.assertEqual(self.service.audit_active(self.pid)['clip_count'],280)
        self.assertEqual(self.service.directory(self.pid,'sections')['active_section'],self.group)
        self.assertEqual(self.service.directory(self.pid,'edits')['items'][-1]['kind'],'section')
    def test_no_render_or_flat_edit_and_restore_as_new_revision(self):
        self.activate();self.assertRaises(ValueError,self.editor.native_assembly,self.pid)
        self.assertRaises(ValueError,self.editor.mutate,self.pid,3,'append',{})
        old=self.editor.view(self.pid)
        restored=self.editor.restore(self.pid,1,3);self.assertEqual(restored['revision'],4);self.assertEqual(len(restored['clips']),140)
        self.assertRaises(RuntimeError,self.service.active_page,self.pid,3,old['active_digest'])
        self.assertEqual(self.service.directory(self.pid,'edits')['items'][2]['kind'],'section')
    def test_wrong_receipt_stale_approval_and_tail_tamper(self):
        args=(self.pid,self.group['section_id'],self.group['digest'],2)
        preview=self.service.preview_paged(*args)
        self.assertRaises(PermissionError,self.service.activate_paged,*args,'f'*64)
        self.activate();self.assertRaises(RuntimeError,self.service.activate_paged,*args,preview['approval_digest'])
        v=self.editor.view(self.pid)
        self.assertRaises(RuntimeError,self.service.active_page,self.pid,3,'f'*64)
        self.assertRaises(ValueError,self.service.active_page,self.pid,3,v['active_digest'],0,65)
        def change(db,movie):db.execute('UPDATE g06_frozen_takes SET take_sha256=? WHERE project_id=? AND take_id=?',('f'*64,self.pid,f'{280:032x}'))
        self.editor._execute(self.pid,change,mutate=True)
        # A bounded early page is not whole-tree verification. Tail and audit fail.
        self.assertEqual(len(self.service.active_page(self.pid,3,v['active_digest'])['items']),32)
        self.assertRaises(RuntimeError,self.service.active_page,self.pid,3,v['active_digest'],279)
        self.assertRaises(RuntimeError,self.service.audit_active,self.pid)
    def test_duplicate_identity_rejected_and_permission_lost_before_commit(self):
        duplicate=saved(self.service,self.pid,'Same cuts elsewhere',[ref(self.a)])
        root=saved(self.service,self.pid,'Repeated source',[ref(self.a),ref(duplicate)])
        self.assertRaises(ValueError,self.service.preview_paged,self.pid,root['section_id'],root['digest'],2)
        args=(self.pid,self.group['section_id'],self.group['digest'],2);preview=self.service.preview_paged(*args)
        calls=0
        def check():
            nonlocal calls
            calls+=1
            if calls>100:raise PermissionError('revoked')
        guarded=EditorialSections(self.editor,access_guard=check)
        self.assertRaises(PermissionError,guarded.activate_paged,*args,preview['approval_digest'])
        self.assertEqual(self.editor.view(self.pid)['revision'],2)
    def test_exact_receipt_required_even_for_first_page(self):
        self.activate();v=self.editor.view(self.pid)
        def change(db,movie):db.execute('DELETE FROM g07_section_activations WHERE project_id=? AND revision=3',(self.pid,))
        self.editor._execute(self.pid,change,mutate=True)
        self.assertRaises(RuntimeError,self.editor.view,self.pid)
        self.assertRaises(RuntimeError,self.service.active_page,self.pid,3,v['active_digest'])


class LongClockAndSmokeFixture(unittest.TestCase):
    def test_nine_hour_metadata_clock_without_raising_finite_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            studio=Studio(Path(temp)/'studio.sqlite3');pid=studio.create_project('Fixture','')['id'];editor=G07Editor(studio)
            def seed(db,movie):
                for revision in range(2):
                    doc=_blank();doc['title']=f'Volume {revision+1}'
                    for n in range(1+revision*9,10+revision*9):
                        clip=fixture_take(db,pid,n);row=db.execute('SELECT performance_json FROM g06_frozen_takes WHERE project_id=? AND take_id=?',(pid,clip['take_id'])).fetchone()
                        manifest=json.loads(row[0]);manifest['duration_tick']=1800*T;raw=_json(manifest);sha=_sha(raw.encode('utf8'))
                        db.execute('UPDATE g06_frozen_takes SET performance_json=?, take_sha256=? WHERE project_id=? AND take_id=?',(raw,sha,pid,clip['take_id']))
                        clip.update(take_sha256=sha,source_out_tick=1800*T);doc['clips'].append(clip)
                    editor._validate(db,pid,doc);editor._save(db,pid,doc,revision,revision)
            editor._execute(pid,seed,mutate=True);service=EditorialSections(editor)
            first,last=service.directory(pid,'edits')['items'];group=saved(service,pid,'Nine hour source plan',[ref(first),ref(last)])
            self.assertRaises(ValueError,service.preview_activation,pid,group['section_id'],group['digest'],2)
            self.assertEqual(activate(service,pid,group)['duration_tick'],str(9*3600*T));v=editor.view(pid)
            last=service.active_page(pid,3,v['active_digest'],17)['items'][0];self.assertEqual(last['end_tick'],str(9*3600*T))
            self.assertEqual(service.audit_active(pid)['clip_count'],18)
    def test_installed_smoke_seed_runs_same_editor_without_native_media_claim(self):
        from tools.nvp_perf03g_gui_smoke import seed_fixture
        with tempfile.TemporaryDirectory() as temp:
            studio=Studio(Path(temp)/'studio.sqlite3');pid=studio.create_project('Isolated fixture','')['id'];editor=G07Editor(studio)
            group=seed_fixture(editor,pid);self.assertEqual(editor.view(pid)['revision'],3);service=EditorialSections(editor)
            self.assertEqual(activate(service,pid,group,3)['revision'],4)
            v=editor.view(pid);self.assertEqual(v['title'],'Reordered feature');p=service.active_page(pid,4,v['active_digest'],0,1,native=True)
            self.assertEqual(p['items'][0]['source_revision'],2)


class BackupFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.studio=Studio(self.root/'studio.sqlite3');self.pid=self.studio.create_project('Fixture','')['id']
        self.store=LiveFilmStore(self.root/'protected');self.token='fixture-session-'+'a'*32
        self.key=b'\x22'*32 # public disposable fixture; not DPAPI proof.
        folder=self.store._folder(self.pid);folder.mkdir();(folder/'revisions').mkdir();(folder/'assets').mkdir()
        db=self.store._new_sqlite('Fixture','','');raw=db.serialize();db.close()
        record=self.store._seal_db(folder,self.pid,self.key,raw,0);self.store._publish_head(folder,record)
        self.store._keys[self.token]=(self.pid,self.key)
        self.editor=G07Editor(self.studio,live=self.store,token=self.token)
        self.service,self.group,self.a,self.b=seed_large(self.editor,self.pid);activate(self.service,self.pid,self.group)
    def test_backup_copy_reopens_and_exact_missing_page_recovery_preserves_head(self):
        folder=self.store._folder(self.pid);backup=self.root/'backup';shutil.copytree(folder,backup)
        self.assertEqual(self.service.verify_protected_storage(self.pid)['verified_paged_edits'],1)
        target=_location(folder,self.key,self.b['digest']);head=self.store._head(folder)
        shutil.rmtree(target)
        with self.assertRaises(VaultError):self.service.verify_protected_storage(self.pid)
        args=(self.pid,self.b['section_id'],self.b['digest'],backup)
        with self.assertRaises(PermissionError):self.service.recover_missing_page(*args,expected_revision=3)
        with self.assertRaises(RuntimeError):self.service.recover_missing_page(*args,expected_revision=2,human_approved=True)
        self.assertFalse(target.exists())
        self.assertTrue(self.service.recover_missing_page(*args,expected_revision=3,human_approved=True)['restored'])
        self.assertEqual(self.store._head(folder),head);self.assertEqual(self.service.verify_protected_storage(self.pid)['verified_sealed_pages'],3)
        with self.assertRaises(VaultError):self.service.recover_missing_page(*args,expected_revision=3,human_approved=True)
    def test_corrupt_backup_and_revoke_refuse_without_writes(self):
        folder=self.store._folder(self.pid);backup=self.root/'backup';shutil.copytree(folder,backup)
        target=_location(folder,self.key,self.b['digest']);shutil.rmtree(target)
        bad=_location(backup,self.key,self.b['digest'])/'body.nvpsealed';raw=bytearray(bad.read_bytes());raw[-30]^=1;bad.write_bytes(raw)
        args=(self.pid,self.b['section_id'],self.b['digest'],backup)
        with self.assertRaises(VaultError):self.service.recover_missing_page(*args,expected_revision=3,human_approved=True)
        self.assertFalse(target.exists());self.store.revoke(self.pid)
        with self.assertRaises(LiveFilmError):self.service.recover_missing_page(*args,expected_revision=3,human_approved=True)


@unittest.skipUnless(sys.platform=='win32','Real Windows DPAPI required')
class WindowsActiveTimeline(unittest.TestCase):
    def test_real_dpapi_backup_reopen_and_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);studio=Studio(root/'studio.sqlite3');pid=studio.create_project('Fixture','')['id'];token='director-'+'c'*32
            store=LiveFilmStore(root/'secured');store.create(pid,'Protected film','','',SECRET);store.authorize(pid,SECRET,token)
            editor=G07Editor(studio,live=store,token=token);service,group,a,b=seed_large(editor,pid);activate(service,pid,group)
            original=store._folder(pid);backup_root=root/'backup';backup_root.mkdir();shutil.copytree(original,backup_root/pid)
            restored=LiveFilmStore(backup_root);restored.authorize(pid,SECRET,token)
            reopened=G07Editor(studio,live=restored,token=token);new=EditorialSections(reopened)
            v=reopened.view(pid);self.assertEqual(new.active_page(pid,3,v['active_digest'],279)['items'][0]['index'],279)
            self.assertEqual(new.verify_protected_storage(pid)['verified_paged_edits'],1)
            key=store._session(pid,token);shutil.rmtree(_location(original,key,b['digest']));head=store._head(original)
            self.assertTrue(service.recover_missing_page(pid,b['section_id'],b['digest'],backup_root/pid,expected_revision=3,human_approved=True)['restored'])
            self.assertEqual(store._head(original),head);self.assertEqual(service.verify_protected_storage(pid)['verified_sealed_pages'],3)
            store.revoke(pid);self.assertRaises(LiveFilmError,service.audit_active,pid)
    def test_windows_real_protected_http_activation_page_lock_reopen(self):
        from fastapi.testclient import TestClient
        from backend import nvp_api
        from backend.nvp_project_access import COOKIE
        with tempfile.TemporaryDirectory() as temp:
            studio=Studio(Path(temp)/'studio.sqlite3')
            with patch.object(nvp_api,'studio',studio),patch.object(nvp_api,'_live_films',None),patch.object(nvp_api,'_film_access',None):
                client=TestClient(nvp_api.app);created=client.post('/api/projects/encrypted',headers=HEADERS,json={'title':'Chapter film','idea':'','screenplay':'','passphrase':SECRET})
                self.assertEqual(created.status_code,201,created.text);pid=created.json()['id'];base=f'/api/projects/{pid}';url=base+'/live/edit/sections'
                editor=G07Editor(studio,live=nvp_api.live_films(),token=client.cookies.get(COOKIE));service,group,_,_=seed_large(editor,pid)
                args={'section_id':group['section_id'],'digest':group['digest'],'expected_revision':2}
                def post(path,body,status=200):
                    response=client.post(url+path,headers=HEADERS,json=body);self.assertEqual(response.status_code,status,response.text);return response.json()
                preview=post('/paged-activation-preview',args);post('/paged-activate',{**args,'approval_digest':preview['approval_digest']})
                v=editor.view(pid);page={'revision':3,'digest':v['active_digest'],'first':279,'limit':32}
                self.assertEqual(post('/active-page',page)['items'][0]['index'],279)
                self.assertEqual(client.post(base+'/lock',headers=HEADERS).status_code,200);post('/active-page',page,423)
                nvp_api._live_films=None;nvp_api._film_access=None
                self.assertEqual(client.post(base+'/unlock',headers=HEADERS,json={'passphrase':SECRET}).status_code,200)
                self.assertEqual(post('/active-page',page)['total'],280)
                self.assertEqual(client.post(base+'/edit/sections/active-page',headers=HEADERS,json=page).status_code,403)

if __name__=='__main__':unittest.main()
