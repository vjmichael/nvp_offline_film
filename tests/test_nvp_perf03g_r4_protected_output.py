"""R4 storage/backup and actual bounded MJPEG/PCM verification.
Portable cases substitute only OpenUSD world opening and Windows DPAPI key
custody; genuine Windows fixture retains both without substitutes.
"""
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g03_live_backup import create_backup,restore_copy
from backend.nvp_g03_pcm_pages import migrate_recording,read_pcm,_location
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g07_preview import paged_sound
from backend.nvp_g07_review_reels import review,render_approved,open_reel,list_reels,inspect
from backend.nvp_g06_filming import _json,_sha
from backend.nvp_studio import Studio
from test_nvp_perf03g_r3_media import seed_media
from test_nvp_perf03g_r2_paged_active import activate
from test_nvp_perf03g_sections import SECRET,T


class Fixture:
    def __init__(self,owner,*,native=False):
        tmp=tempfile.TemporaryDirectory();owner.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.studio=Studio(self.root/'studio.sqlite3');self.pid=self.studio.create_project('Fixture','')['id']
        self.store=LiveFilmStore(self.root/'secured');self.token='r4-test-'+'x'*32
        if native:
            self.store.create(self.pid,'Fixture','','',SECRET);self.store.authorize(self.pid,SECRET,self.token)
        else:
            folder=self.store._folder(self.pid);folder.mkdir();(folder/'revisions').mkdir();(folder/'assets').mkdir()
            # Public test key and fake wrapped metadata: NOT Windows DPAPI.
            (folder/'key.nvpdpapi').write_text('{"portable_fixture":true}')
            key=b'\x71'*32;self.store._keys[self.token]=(self.pid,key)
            db=self.store._new_sqlite('Fixture','','');raw=db.serialize();db.close();self.store._publish_head(folder,self.store._seal_db(folder,self.pid,key,raw,0))
        self.folder=self.store._folder(self.pid);self.key=self.store._session(self.pid,self.token)
        self.editor=G07Editor(self.studio,live=self.store,token=self.token)
        # Native G08 supports box, not G07 preview's cube shorthand. Use exact
        # source fixture geometry and a front-facing camera before freezing the edit.
        service,group=seed_media(self.editor,self.pid)
        def convert(db,movie):
            doc=json.loads(db.execute('SELECT document_json FROM g07_edit_versions WHERE project_id=? AND revision=1',(self.pid,)).fetchone()[0])
            for clip in doc['clips']:
                row=db.execute('SELECT performance_json FROM g06_frozen_takes WHERE take_id=?',(clip['take_id'],)).fetchone();take=json.loads(row[0]);take['stage_objects'][0]['shape']='box';raw=_json(take);digest=_sha(raw.encode())
                db.execute('UPDATE g06_frozen_takes SET performance_json=?,take_sha256=? WHERE take_id=?',(raw,digest,clip['take_id']));clip['take_sha256']=digest
                clip['camera'].update(position=[-4.,-4.,2.],look_at=[2.,0.,0.])
            # Seed fixture only: replace its not-yet-approved edit and delete
            # fixture-only arrangements referencing the former geometry.
            db.execute('DELETE FROM g07_sections');raw=_json(doc);digest=_sha(raw.encode())
            db.execute('UPDATE g07_edit_versions SET document_json=?,document_sha256=? WHERE project_id=? AND revision=1',(raw,digest,self.pid));db.execute('UPDATE g07_edit_heads SET document_sha256=? WHERE project_id=?',(digest,self.pid))
        self.editor._execute(self.pid,convert,mutate=True)
        from test_nvp_perf03g_sections import saved,ref
        self.service=EditorialSections(self.editor,access_guard=self.guard)
        entry=self.service.directory(self.pid,'edits')['items'][0];a=saved(self.service,self.pid,'Act one',[ref(entry,0,2)]);b=saved(self.service,self.pid,'Act two',[ref(entry,2,2)]);group=saved(self.service,self.pid,'Review film',[ref(a),ref(b)])
        activate(self.service,self.pid,group,1);self.digest=self.editor.view(self.pid)['active_digest'];self.rev=2
    def guard(self):self.store._session(self.pid,self.token)
    def source(self,cid=9002):return f'{cid:032x}'
    def migrate(self,cid=9002):
        return migrate_recording(self.editor.filming,self.pid,'SC_abcdef012345',self.source(cid),_sha(struct.pack('<h',(cid-9000)*2000)*(2*48000)),guard=self.guard,human_approved=True)
    def portable_usd(self):
        # Genuine G06 _take is still used, including PCM verification; replace
        # pxr imports only, for portable fixture. Actual Windows test does not.
        from types import SimpleNamespace
        class Layer:
            subLayerPaths=[]
            def ImportFromString(self,raw):return raw.startswith('#usda')
            def GetExternalReferences(self):return []
        return patch.dict(sys.modules,{'pxr':SimpleNamespace(Sdf=SimpleNamespace(Layer=SimpleNamespace(CreateAnonymous=lambda _:Layer())),Usd=SimpleNamespace(Stage=SimpleNamespace(Open=lambda *a:True,LoadNone=0)))})


class PortableR4(unittest.TestCase):
    def setUp(self):self.f=Fixture(self)
    def test_migration_preserves_audio_and_active_edit(self):
        f=self.f;before=f.store._head(f.folder)
        with f.portable_usd():
            original=paged_sound(f.service,f.pid,2,f.digest,7*T//4,T//4)
            result=f.migrate();self.assertTrue(result['migrated']);self.assertFalse(f.migrate()['migrated'])
            self.assertEqual(paged_sound(f.service,f.pid,2,f.digest,7*T//4,T//4),original)
        after=f.store._head(f.folder);self.assertGreater(after['sequence'],before['sequence']);self.assertTrue((f.folder/'revisions'/before['name']).is_file())
        def check(db,movie):
            n=db.execute('SELECT length(pcm) FROM g06_original_pcm WHERE id=?',(f.source(),)).fetchone()[0];self.assertEqual(n,0)
            p=read_pcm(db,f.editor.filming,f.pid,'SC_abcdef012345',f.source(),first=4,count=12)
            self.assertEqual(p['pcm'],struct.pack('<h',4000)*6)
        f.editor._execute(f.pid,check);self.assertEqual(f.editor.view(f.pid)['active_digest'],f.digest)
    def test_multi_page_recording_compacts_active_database_and_range(self):
        f=self.f;cid=f'{9999:032x}';raw=bytes(range(256))*4500;digest=_sha(raw)
        f.editor._execute(f.pid,lambda db,movie:db.execute('INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,f.pid,'SC_abcdef012345',None,'native_microphone_pcm16le',raw,digest,48000,1,len(raw)//2,'2026-11-19')),mutate=True)
        before=f.store._head(f.folder);before_bytes=(f.folder/'revisions'/before['name']).stat().st_size
        result=migrate_recording(f.editor.filming,f.pid,'SC_abcdef012345',cid,digest,guard=f.guard,human_approved=True);self.assertTrue(result['migrated'])
        after=f.store._head(f.folder);after_bytes=(f.folder/'revisions'/after['name']).stat().st_size
        self.assertLess(after_bytes,before_bytes-len(raw)//2);self.assertTrue((f.folder/'revisions'/before['name']).is_file())
        def read(db,movie):return read_pcm(db,f.editor.filming,f.pid,'SC_abcdef012345',cid,first=524284,count=16)['pcm']
        self.assertEqual(f.editor._execute(f.pid,read),raw[524284:524300]);loc=_location(f.folder,f.key,cid,digest);self.assertEqual(len(list(loc.glob('[0-9]*.nvpsealed'))),3)
        data=bytearray((loc/'00000002.nvpsealed').read_bytes());data[-1]^=1;(loc/'00000002.nvpsealed').write_bytes(data)
        with self.assertRaises(VaultError):f.editor._execute(f.pid,read)
        print(f'R4_PCM_STORAGE_FIXTURE before={before_bytes} after={after_bytes} original_bytes={len(raw)}')
    def test_pcm_tamper_denied_and_unapproved_migration_refused(self):
        f=self.f;digest=_sha(struct.pack('<h',4000)*(2*48000));args=(f.editor.filming,f.pid,'SC_abcdef012345',f.source(),digest)
        with self.assertRaises(PermissionError):migrate_recording(*args,guard=f.guard)
        f.migrate();file=_location(f.folder,f.key,f.source(),digest)/'00000000.nvpsealed';raw=bytearray(file.read_bytes());raw[-20]^=1;file.write_bytes(raw)
        with f.portable_usd(),self.assertRaises(RuntimeError):paged_sound(f.service,f.pid,2,f.digest,7*T//4,T//4)
    def test_verified_backup_and_separate_restoration(self):
        f=self.f;f.migrate();f.store.put_original(f.pid,f.token,'source/demo',b'preserved picture bytes')
        parent=f.root/'backups';parent.mkdir();restore=f.root/'restore';restore.mkdir();before=f.store._head(f.folder)
        with self.assertRaises(PermissionError):create_backup(f.store,f.pid,f.token,parent,guard=f.guard)
        out=create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True);self.assertTrue(out['backup_created']);self.assertEqual(f.store._head(f.folder),before)
        folder=parent/('NVP-'+f.pid+'-backup');self.assertTrue((folder/'backup.nvpinventory').is_file())
        result=restore_copy(f.store,f.pid,f.token,folder,restore,guard=f.guard,human_approved=True);self.assertTrue(result['restored_copy']);self.assertEqual(f.store._head(restore/f.pid),before)
        recovered=LiveFilmStore(restore);recovered._keys[f.token]=(f.pid,f.key);editor=G07Editor(f.studio,live=recovered,token=f.token)
        self.assertEqual(editor.view(f.pid)['active_digest'],f.digest);self.assertEqual(recovered.get_original(f.pid,f.token,'source/demo'),b'preserved picture bytes')
        with self.assertRaises(VaultError):restore_copy(f.store,f.pid,f.token,folder,restore,guard=f.guard,human_approved=True)
        with self.assertRaises(VaultError):create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
        another=f.root/'other';another.mkdir();p=folder/'HEAD.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(VaultError):restore_copy(f.store,f.pid,f.token,folder,another,guard=f.guard,human_approved=True)
        self.assertFalse((another/f.pid).exists())
    def test_native_dialog_denial_and_explicit_copy(self):
        from types import SimpleNamespace
        from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog,review_clip_with_dialog,copy_clip_with_dialog,backup_with_dialog
        f=self.f;origin='http://127.0.0.1:43210';parent=f.root/'copies';parent.mkdir();accept=[False];selected=[parent];confirmations=[]
        class Window:
            def get_current_url(self):return origin+'/'
            def create_file_dialog(self,*args,**kwargs):return [str(selected[0])]
            def create_confirmation_dialog(self,*args):confirmations.append(args);return accept[0]
        dialog=NativeRecoveryDialog(Window(),origin)
        args=(f.service,f.pid,2,f.digest,42,8)
        with self.assertRaises(PermissionError):review_clip_with_dialog(*args,'http://127.0.0.1:9',dialog)
        self.assertTrue(review_clip_with_dialog(*args,origin,dialog)['cancelled']);self.assertEqual(list_reels(f.service,f.pid,2,f.digest)['items'],[])
        class World:
            def __init__(self,record):self.record=record
            def polygons(self,*args):return [(2.,[(120,100),(240,100),(240,220)],(120,60,20))]
        accept[0]=True
        with f.portable_usd(),patch('backend.nvp_g09e_chunk.SourceWorld',World):saved=review_clip_with_dialog(*args,origin,dialog)
        ident=saved['reel_id'];raw=open_reel(f.service,f.pid,ident,2,f.digest)
        with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=20))}):
            accept[0]=False;self.assertTrue(copy_clip_with_dialog(f.service,f.pid,2,f.digest,ident,origin,dialog)['cancelled']);self.assertEqual(list(parent.iterdir()),[])
            accept[0]=True;copy=copy_clip_with_dialog(f.service,f.pid,2,f.digest,ident,origin,dialog);self.assertTrue(copy['copy_saved']);self.assertEqual((parent/('NVP-review-'+ident)/'review.avi').read_bytes(),raw)
            with self.assertRaises(FileExistsError):copy_clip_with_dialog(f.service,f.pid,2,f.digest,ident,origin,dialog)
            selected[0]=f.root/'backup';selected[0].mkdir();self.assertTrue(backup_with_dialog(f.service,f.pid,origin,dialog)['backup_created'])
        dialog.close()
        with self.assertRaises(PermissionError):review_clip_with_dialog(*args,origin,dialog)
    def test_real_codec_reel_readback_and_pcm_order(self):
        f=self.f;f.migrate();expected=review(f.service,f.pid,2,f.digest,42,8)
        with self.assertRaises(PermissionError):render_approved(f.service,f.pid,expected)
        # Real renderer, JPEG encoder, AVI writer, PCM mix and readback; fake
        # only the evaluated geometry because pxr is unavailable locally.
        class World:
            def __init__(self,record):self.record=record
            def polygons(self,*args):return [(2.,[(120,100),(240,100),(240,220)],(120,60,20))]
        with f.portable_usd(),patch('backend.nvp_g09e_chunk.SourceWorld',World):out=render_approved(f.service,f.pid,expected,human_approved=True)
        self.assertTrue(out['verified']);self.assertFalse(out['whole_movie_exported']);raw=open_reel(f.service,f.pid,out['reel_id'],2,f.digest)
        data=inspect(raw,8,expected_sha=_sha(raw));self.assertEqual(data['audio_samples_per_channel'],16000);self.assertTrue(data['exact_index_verified'])
        corrupted=bytearray(raw);corrupted[-1]^=1
        with self.assertRaises((VaultError,RuntimeError)):inspect(bytes(corrupted),8,expected_sha=_sha(bytes(corrupted)))
        self.assertEqual(list_reels(f.service,f.pid,2,f.digest)['items'][0]['state'],'saved')
        f.store.revoke(f.pid)
        with self.assertRaises(Exception):open_reel(f.service,f.pid,out['reel_id'],2,f.digest)


@unittest.skipUnless(sys.platform=='win32','Real Windows DPAPI and original OpenUSD renderer required')
class NativeR4(unittest.TestCase):
    def test_real_source_reel_and_encrypted_backup_reopen(self):
        f=Fixture(self,native=True);f.migrate();expected=review(f.service,f.pid,2,f.digest,42,8)
        out=render_approved(f.service,f.pid,expected,human_approved=True);raw=open_reel(f.service,f.pid,out['reel_id'],2,f.digest)
        audit=inspect(raw,8,expected_sha=_sha(raw));self.assertEqual(audit['audio_samples_per_channel'],16000)
        parent=f.root/'backups';parent.mkdir();new=f.root/'restored';new.mkdir();create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
        restore_copy(f.store,f.pid,f.token,parent/('NVP-'+f.pid+'-backup'),new,guard=f.guard,human_approved=True)
        recovered=LiveFilmStore(new);recovered.authorize(f.pid,SECRET,f.token);editor=G07Editor(f.studio,live=recovered,token=f.token);service=EditorialSections(editor,access_guard=lambda:recovered._session(f.pid,f.token))
        self.assertEqual(open_reel(service,f.pid,out['reel_id'],2,f.digest),raw)
        # Exercise Windows DPAPI recovery without the original active movie or
        # its in-memory key/session, using only the separate authenticated backup.
        from backend.nvp_g03_live_backup import restore_detached
        f.store.revoke(f.pid);shutil.rmtree(f.folder);detached=f.root/'disaster-recovery';detached.mkdir()
        with self.assertRaises(VaultError):restore_detached(f.pid,'wrong passphrase for fixture',parent/('NVP-'+f.pid+'-backup'),detached,guard=lambda:None,human_approved=True)
        self.assertFalse((detached/f.pid).exists())
        result=restore_detached(f.pid,SECRET,parent/('NVP-'+f.pid+'-backup'),detached,guard=lambda:None,human_approved=True);self.assertTrue(result['restored_copy'])
        reopened=LiveFilmStore(detached);reopened.authorize(f.pid,SECRET,f.token)
        editor=G07Editor(f.studio,live=reopened,token=f.token);service=EditorialSections(editor,access_guard=lambda:reopened._session(f.pid,f.token))
        self.assertEqual(open_reel(service,f.pid,out['reel_id'],2,f.digest),raw)

if __name__=='__main__':unittest.main()
