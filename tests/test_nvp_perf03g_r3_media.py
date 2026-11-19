"""Real SQL/PCM and protected storage tests; native USD/DPAPI gate separate."""
import io
import json
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from backend.nvp_g06_filming import _json,_sha
from backend.nvp_g07_edit import G07Editor,_blank,_project,TICKS_PER_SAMPLE,RATE
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g07_paged_media import window,delivery_plan,native_source_window,WINDOW_FORMAT
from backend.nvp_g07_preview import paged_picture,paged_sound,audio_window
from backend.nvp_g07_storage_migration import storage_status,migration_review,migrate
from backend.nvp_g07_section_pages import _location
from backend.nvp_g03_live_store import LiveFilmStore,LiveFilmError
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_studio import Studio
import test_nvp_perf03g_r2_paged_active as prior
from test_nvp_perf03g_sections import fixture_take,saved,ref,T,SECRET,HEADERS


def seed_media(editor,pid):
    """Tiny generated self-contained USD/PCM originals in actual G06 schema.

    Synthetic input recording, not physical microphone or production-quality
    capture. Native test does not replace the renderer/reader or DPAPI.
    """
    def create(db,movie):
        doc=_blank();doc['title']='Scene arrangement'
        for n in range(1,5):
            clip=fixture_take(db,pid,n);tid=clip['take_id'];cid=f'{9000+n:032x}';sid='SC_abcdef012345'
            pcm=struct.pack('<h',n*2000)*(2*RATE);digest=_sha(pcm)
            db.execute('INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,pid,sid,'actor_fixture','native_microphone_pcm16le',pcm,digest,RATE,1,2*RATE,'2026-11-19'))
            raw=(f'#usda 1.0\n( defaultPrim = "World" )\ndef Xform "World" {{\n def Scope "Objects" {{\n  def Xform "Actor" {{\n   double3 xformOp:translate = ({n}, 0, 0)\n   uniform token[] xformOpOrder = ["xformOp:translate"]\n  }}\n }}\n}}\n').encode()
            sha=_sha(raw);manifest=json.loads(db.execute('SELECT performance_json FROM g06_frozen_takes WHERE take_id=?',(tid,)).fetchone()[0])
            audio=[{'clip_id':cid,'actor_id':'actor_fixture','pcm_sha256':digest,'sample_count':2*RATE,'start_tick':0,'duration_tick':2*T,'emitter_position':[0,0,0]}]
            manifest.update(original_usd_sha256=sha,performance_usd_sha256=sha,audio=audio,events=[],stage_setting={},stage_objects=[{'id':'Actor','name':'Actor','role':'actor','actor_id':'actor_fixture','shape':'cube','rotation':[0,0,0],'scale':[1,1,1],'color':'#aaaaaa'}])
            encoded=_json(manifest);take_sha=_sha(encoded.encode());db.execute('UPDATE g06_frozen_takes SET original_usd=?,original_usd_sha256=?,performance_usd=?,performance_usd_sha256=?,performance_json=?,audio_json=?,take_sha256=? WHERE take_id=?',(raw,sha,raw,sha,encoded,_json(audio),take_sha,tid))
            clip['take_sha256']=take_sha;clip['audio']=[{'clip_id':cid,'enabled':True,'gain':1.0,'pan':-1.0,'spatial':False,'offset_tick':0}]
            if n==2:clip['transition']={'kind':'dissolve','duration_tick':T//2}
            doc['clips'].append(clip)
        editor._validate(db,pid,doc);editor._save(db,pid,doc,0,0)
    editor._execute(pid,create,mutate=True);service=EditorialSections(editor)
    entry=service.directory(pid,'edits')['items'][0]
    a=saved(service,pid,'Act one',[ref(entry,0,2)]);b=saved(service,pid,'Act two',[ref(entry,2,2)])
    root=saved(service,pid,'Complete film',[ref(a),ref(b)])
    return service,root


def portable_take(editor):
    """Only substitute OpenUSD stage opening; keep real stored hash checks.

    Required because this Linux development environment has no pxr. The
    Windows test below exercises the original unmodified _take and _stage_at.
    """
    def read(db,pid,tid):
        meta,take,audio=editor.filming._take_metadata(db,pid,tid)
        row=db.execute('SELECT * FROM g06_frozen_takes WHERE project_id=? AND take_id=?',(pid,tid)).fetchone()
        if (_sha(row['original_usd'])!=meta['original_usd_sha256'] or _sha(row['performance_usd'])!=meta['performance_usd_sha256']):raise RuntimeError('Altered original')
        for source in audio:
            pcm=db.execute('SELECT pcm FROM g06_original_pcm WHERE project_id=? AND id=?',(pid,source['clip_id'])).fetchone()
            if _sha(pcm['pcm'])!=source['pcm_sha256']:raise RuntimeError('Altered original sound')
        return row,take,audio
    return patch.object(editor.filming,'_take',side_effect=read)


def decode(raw):
    with wave.open(io.BytesIO(raw),'rb') as wav:
        params=(wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())
        return params,list(struct.iter_unpack('<hh',wav.readframes(wav.getnframes())))


class MediaWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/'studio.sqlite3');self.pid=self.studio.create_project('Fixture','')['id'];self.editor=G07Editor(self.studio)
        self.service,self.root=seed_media(self.editor,self.pid)
        prior.activate(self.service,self.pid,self.root,1);self.rev=2;self.digest=self.editor.view(self.pid)['active_digest']
    def seek(self,start,end):
        return self.service._run(self.pid,lambda db,movie:window(self.service,db,self.pid,self.rev,self.digest,start,end))
    def plan(self):return delivery_plan(self.service,self.pid,self.rev,self.digest)
    def test_exact_dissolve_and_section_boundary(self):
        self.assertEqual([x['index'] for x in self.seek(7*T//4,7*T//4+1)[1]],[0,1]);self.assertEqual([x['index'] for x in self.seek(7*T//2-1,7*T//2+1)[1]],[1,2]);self.assertEqual([x['index'] for x in self.seek(7*T//2,7*T//2+1)[1]],[2]);self.assertEqual(self.plan()['frame_count'],180)
        with self.assertRaises(ValueError):self.seek(0,8*T)
        with self.assertRaises(RuntimeError):delivery_plan(self.service,self.pid,2,'f'*64)
    def test_original_pcm_mixer_matches_legacy_finite_path(self):
        # Exact same stored finite leaf order, different metadata reader. A
        # finite reference uses old _mix_window; compare every sample across dissolve/section.
        with portable_take(self.editor):
            raw=paged_sound(self.service,self.pid,self.rev,self.digest,7*T//4,T//4)
            params,frames=decode(raw);self.assertEqual(params,(2,2,RATE,RATE//4));self.assertEqual(frames[0],(3000,0));self.assertEqual(frames[-1],(4000,0))
            across=paged_sound(self.service,self.pid,self.rev,self.digest,13*T//4,T//2)
            p,samples=decode(across);self.assertEqual(p[-1],RATE//2);self.assertEqual(samples[0],(4000,0));self.assertEqual(samples[RATE//4],(6000,0))
            self.editor.restore(self.pid,1,2)
            self.assertEqual(raw,audio_window(self.editor,self.pid,'1.75','.25'))
            self.assertEqual(across,audio_window(self.editor,self.pid,'3.25','.5'))
        with self.assertRaises(RuntimeError):self.seek(0,1)
    def test_export_source_window_only_reads_participating_originals(self):
        receipt=self.plan();start=7*T//2;end=start+T
        with portable_take(self.editor):
            out=native_source_window(self.service,self.pid,self.rev,self.digest,start,end,plan_sha256=receipt['plan_sha256'])
        self.assertEqual(out['format'],WINDOW_FORMAT);self.assertEqual(len(out['original_takes']),1);self.assertEqual(out['segments'][0]['index'],2);self.assertEqual(out['window'],[start,end]);self.assertFalse(out['render_approved']);self.assertFalse(out['final_movie_exported']);self.assertEqual(out['plan_sha256'],receipt['plan_sha256'])
        item=next(iter(out['original_takes'].values()));self.assertEqual(item['audio'][0]['pcm16le'],struct.pack('<h',6000)*(2*RATE))
        with self.assertRaises(PermissionError):native_source_window(self.service,self.pid,self.rev,self.digest,start,end,plan_sha256='f'*64)
        with self.assertRaises(ValueError):native_source_window(self.service,self.pid,self.rev,self.digest,start+1,end,plan_sha256=receipt['plan_sha256'])
        with self.assertRaises(ValueError):self.editor.native_assembly(self.pid,2,window=(start,end))
    def test_media_budget_and_tampering_refuse_before_sample(self):
        with patch('backend.nvp_g07_paged_media.MAX_MEDIA_BYTES',1),patch.object(self.editor.filming,'_take',side_effect=AssertionError('Preflight must reject before payload')):
            with self.assertRaises(ValueError):paged_sound(self.service,self.pid,self.rev,self.digest,0,T)
        def alter(db,movie):db.execute('UPDATE g06_original_pcm SET pcm=? WHERE project_id=? AND id=?',(b'\x01\x00'*(2*RATE),self.pid,f'{9003:032x}'))
        self.editor._execute(self.pid,alter,mutate=True)
        with portable_take(self.editor):
            with self.assertRaises(RuntimeError):paged_sound(self.service,self.pid,self.rev,self.digest,7*T//2,T)
    def test_fractional_frame_cut_blocks_delivery_not_preview(self):
        # Build another ordinary edit and section with a sample-aligned but
        # non-frame-aligned trim; do not rewrite the accepted source history.
        def write(db,movie):
            old=json.loads(db.execute('SELECT document_json FROM g07_edit_versions WHERE project_id=? AND revision=1',(self.pid,)).fetchone()[0]);old['clips'][-1]['source_out_tick']-=TICKS_PER_SAMPLE
            self.editor._validate(db,self.pid,old);self.editor._save(db,self.pid,old,2,2)
        self.editor._execute(self.pid,write,mutate=True);entry=next(x for x in self.service.directory(self.pid,'edits')['items'] if x.get('revision')==3);group=saved(self.service,self.pid,'Fractional cut',[ref(entry)]);prior.activate(self.service,self.pid,group,3);view=self.editor.view(self.pid)
        with self.assertRaisesRegex(ValueError,'cut timing'):delivery_plan(self.service,self.pid,4,view['active_digest'])


class LateSourceTests(unittest.TestCase):
    def test_late_window_and_full_plan_detect_tail_tamper(self):
        fixture=prior.PagedActiveTests();fixture.setUp();self.addCleanup(fixture.doCleanups);fixture.activate();pid=fixture.pid;service=fixture.service;editor=fixture.editor;digest=editor.view(pid)['active_digest']
        def read(db,movie):return window(service,db,pid,3,digest,558*T,559*T)[1]
        self.assertEqual([x['index'] for x in service._run(pid,read)],[279]);self.assertEqual(delivery_plan(service,pid,3,digest)['clip_count'],280)
        def alter(db,movie):db.execute('UPDATE g06_frozen_takes SET take_sha256=? WHERE take_id=?',('0'*64,f'{280:032x}'))
        editor._execute(pid,alter,mutate=True)
        # Whole-film audit checks the tail; bounded read checks touched leaf.
        with self.assertRaises(RuntimeError):service._run(pid,read)
        with self.assertRaises(RuntimeError):delivery_plan(service,pid,3,digest)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        fixture=prior.BackupFixture();fixture.setUp();self.addCleanup(fixture.doCleanups);self.f=fixture
    def legacy(self):
        f=self.f;ident=f.b['section_id'];sha=f.b['digest']
        def make_inline(db,movie):
            original,_=f.service._section(db,f.pid,ident,sha);db.execute('UPDATE g07_sections SET document_json=? WHERE project_id=? AND section_id=?',(_json(original),f.pid,ident))
        f.service._run(f.pid,make_inline,write=True);shutil.rmtree(_location(f.store._folder(f.pid),f.key,sha));return ident,sha
    def test_migration_reuses_exact_section_digest_and_active_revision(self):
        f=self.f;ident,sha=self.legacy();view=f.editor.view(f.pid);status=storage_status(f.service,f.pid);self.assertEqual(next(x['status'] for x in status['items'] if x['section_id']==ident),'legacy_available')
        review=migration_review(f.service,f.pid,3);self.assertEqual(review['entries'],[{'section_id':ident,'sha256':sha}]);args=(f.service,f.pid,3,None,review['approval_digest'])
        with self.assertRaises(PermissionError):migrate(*args)
        with self.assertRaises(PermissionError):migrate(f.service,f.pid,3,None,'f'*64,human_approved=True)
        self.assertEqual(migrate(*args,human_approved=True)['migrated'],1);self.assertEqual(f.editor.view(f.pid)['active_digest'],view['active_digest']);self.assertEqual(f.service.verify_protected_storage(f.pid)['verified_sealed_pages'],3)
        with self.assertRaises(PermissionError):migrate(*args,human_approved=True)
        self.assertEqual(migration_review(f.service,f.pid,3)['entries'],[])
    def test_storage_status_distinguishes_missing_and_corrupt_and_revocation(self):
        f=self.f;folder=f.store._folder(f.pid);shutil.rmtree(_location(folder,f.key,f.b['digest']));body=_location(folder,f.key,f.a['digest'])/'body.nvpsealed';data=bytearray(body.read_bytes());data[-25]^=1;body.write_bytes(data)
        items={x['section_id']:x['status'] for x in storage_status(f.service,f.pid)['items']};self.assertEqual(items[f.b['section_id']],'missing');self.assertEqual(items[f.a['section_id']],'needs_review');self.assertEqual(items[f.group['section_id']],'available');self.assertFalse(storage_status(f.service,f.pid)['media_verified'])
        with self.assertRaises(VaultError):migration_review(f.service,f.pid,3)
        f.store.revoke(f.pid)
        with self.assertRaises(LiveFilmError):storage_status(f.service,f.pid)


class RecoveryDialogTests(unittest.TestCase):
    def test_native_selection_requires_original_guard_and_authenticated_backup(self):
        from types import SimpleNamespace
        from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog,recover_with_dialog
        f=prior.BackupFixture();f.setUp();self.addCleanup(f.doCleanups)
        folder=f.store._folder(f.pid);backup=f.root/'backup';shutil.copytree(folder,backup)
        target=_location(folder,f.key,f.b['digest']);shutil.rmtree(target);head=f.store._head(folder)
        origin='http://127.0.0.1:43210';picked=[];confirmed=[];valid=[True]
        def guard():
            if not valid[0]:raise PermissionError('Locked')
        class Window:
            def get_current_url(self):return origin+'/'
            def create_file_dialog(self,*args,**kwargs):picked.append(True);return [str(backup)]
            def create_confirmation_dialog(self,*args):confirmed.append(args);return True
        dialog=NativeRecoveryDialog(Window(),origin);service=EditorialSections(f.editor,access_guard=guard)
        args=(service,f.pid,f.b['section_id'],3)
        with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=20))}):
            with self.assertRaises(PermissionError):recover_with_dialog(*args,'http://127.0.0.1:9',dialog)
            self.assertEqual(picked,[])
            body=_location(backup,f.key,f.b['digest'])/'body.nvpsealed';raw=body.read_bytes();body.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
            with self.assertRaises(VaultError):recover_with_dialog(*args,origin,dialog)
            self.assertEqual(confirmed,[]);self.assertFalse(target.exists());body.write_bytes(raw)
            self.assertTrue(recover_with_dialog(*args,origin,dialog)['restored']);self.assertEqual(len(confirmed),1)
            self.assertEqual(f.store._head(folder),head);self.assertTrue(target.exists())
            with self.assertRaises(VaultError):recover_with_dialog(*args,origin,dialog)
            dialog.close()
            with self.assertRaises(PermissionError):recover_with_dialog(*args,origin,dialog)


@unittest.skipUnless(sys.platform=='win32','Actual Windows DPAPI and native OpenUSD required')
class NativeProtectedMedia(unittest.TestCase):
    def test_native_picture_pcm_window_and_lock(self):
        from backend import nvp_api
        from backend.nvp_project_access import COOKIE
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as temp:
            studio=Studio(Path(temp)/'studio.sqlite3')
            with patch.object(nvp_api,'studio',studio),patch.object(nvp_api,'_live_films',None),patch.object(nvp_api,'_film_access',None):
                client=TestClient(nvp_api.app);created=client.post('/api/projects/encrypted',headers=HEADERS,json={'title':'Protected film','idea':'','screenplay':'','passphrase':SECRET});self.assertEqual(created.status_code,201,created.text);pid=created.json()['id'];base=f'/api/projects/{pid}';url=base+'/live/edit/sections'
                editor=G07Editor(studio,live=nvp_api.live_films(),token=client.cookies.get(COOKIE));service,root=seed_media(editor,pid);prior.activate(service,pid,root,1);digest=editor.view(pid)['active_digest'];scope={'revision':2,'digest':digest}
                pic=client.post(url+'/picture',headers=HEADERS,json={**scope,'tick':str(7*T//4)});self.assertEqual(pic.status_code,200,pic.text);shots=pic.json()['shots'];self.assertEqual([s['opacity'] for s in shots],[.5,.5]);self.assertEqual([s['objects'][0]['position'][0] for s in shots],[1.,2.])
                sound=client.post(url+'/sound',headers=HEADERS,json={**scope,'start_tick':str(7*T//4),'duration_tick':str(T//4)});self.assertEqual(sound.status_code,200,sound.text if sound.status_code!=200 else '');self.assertEqual(decode(sound.content)[1][0],(3000,0));self.assertEqual(sound.headers['cache-control'],'private, no-store, max-age=0')
                plan=client.post(url+'/delivery-review',headers=HEADERS,json=scope);self.assertEqual(plan.status_code,200,plan.text);result=native_source_window(service,pid,2,digest,7*T//2,9*T//2,plan_sha256=plan.json()['plan_sha256']);self.assertEqual(result['segments'][0]['index'],2);self.assertFalse(result['render_approved'])
                self.assertEqual(client.post(base+'/edit/sections/picture',headers=HEADERS,json={**scope,'tick':'0'}).status_code,403)
                self.assertEqual(client.post(base+'/lock',headers=HEADERS).status_code,200);self.assertEqual(client.post(url+'/picture',headers=HEADERS,json={**scope,'tick':'0'}).status_code,423);self.assertEqual(client.get(url+'/storage-review',headers=HEADERS).status_code,423)
                # Reopen the independently persisted actual protected source.
                nvp_api._live_films=None;nvp_api._film_access=None;self.assertEqual(client.post(base+'/unlock',headers=HEADERS,json={'passphrase':SECRET}).status_code,200);self.assertEqual(client.post(url+'/picture',headers=HEADERS,json={**scope,'tick':str(7*T//2)}).json()['shots'][0]['objects'][0]['position'][0],3.)


if __name__=='__main__':unittest.main()
