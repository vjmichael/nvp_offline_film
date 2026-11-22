"""G07 section metadata and transactional activation: no synthetic native media claim."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_g03_live_store import LiveFilmStore, LiveFilmError
from backend.nvp_studio import Studio
from backend.nvp_g06_filming import TAKE_FORMAT, _json, _sha
from backend.nvp_g07_edit import G07Editor, _blank, _project, _default_grade
from backend.nvp_g07_sections import EditorialSections, FORMAT
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T

HEADERS={'x-nvp-director':'1'}
SECRET='PERF03G fixture passphrase for protected film'


def fixture_take(db,pid,n):
    # Synthetic tiny payloads, validated only as immutable Take metadata. No
    # actual OpenUSD evaluation, codec or physical capture is asserted here.
    tid=f'{n:032x}';sid='SC_abcdef012345';usd=b'fixture metadata only';digest=_sha(usd)
    manifest={'format':TAKE_FORMAT,'scene_id':sid,'duration_tick':T*2,
              'original_usd_sha256':digest,'performance_usd_sha256':digest,'audio':[]}
    encoded=_json(manifest);sha=_sha(encoded.encode('utf8'))
    db.execute('INSERT INTO g06_frozen_takes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (tid,pid,sid,1,digest,digest,usd,digest,usd,encoded,'[]',sha,'2026-11-19'))
    return {'id':f'{100000+n:032x}','take_id':tid,'take_sha256':sha,'source_in_tick':0,'source_out_tick':T*2,
            'camera':{'name':'Wide','position':[0,0,1],'look_at':[1,0,0],'focal_mm':50},
            'grade':_default_grade(),'audio':[],'transition':{'kind':'cut','duration_tick':0},'note':''}


def seed(editor,pid,count=4):
    def work(db,movie):
        doc=_blank();doc['title']='Original cuts';doc['clips']=[fixture_take(db,pid,n) for n in range(1,count+1)]
        editor._validate(db,pid,doc);revision=editor._save(db,pid,doc,0,0)
        return doc,revision
    return editor._execute(pid,work,mutate=True)


def ref(item,first=0,count=None):
    if item['kind']=='section':return {k:item[k] for k in ('kind','section_id','digest')}
    return {'kind':'edit','revision':item['revision'],'digest':item['digest'],'first':first,'count':count if count is not None else item['clip_count']}


def saved(service,pid,title,refs):
    p=service.preview(pid,title,refs)
    return service.publish(pid,title,refs,p['digest'])['selection']


class SectionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/'studio.sqlite3');self.pid=self.studio.create_project('Fixture','')['id']
        self.editor=G07Editor(self.studio);self.source=EditorialSections(self.editor)
        self.doc,self.rev=seed(self.editor,self.pid)
        self.edit=self.source.directory(self.pid,'edits')['items'][0]

    def group(self):
        a=saved(self.source,self.pid,'First act',[ref(self.edit,0,2)])
        b=saved(self.source,self.pid,'Last act',[ref(self.edit,2,2)])
        return saved(self.source,self.pid,'Reordered film',[ref(b),ref(a)])

    def test_preview_save_and_activation_original_history_and_clock(self):
        group=self.group();pid=self.pid
        self.assertEqual(self.source.directory(pid,'edits')['active_revision'],1)
        report=self.source.page(pid,ref(group),limit=1);self.assertEqual(report['next_first'],1)
        self.assertEqual(report['items'][0]['label'],'Last act')
        self.assertEqual(report['items'][0]['end_tick'],str(4*T))
        detail=self.source.page(pid,report['items'][0]['source']);leaf=detail['items'][0]['source']
        cut=self.source.page(pid,leaf,limit=1);self.assertEqual(cut['items'][0]['label'],'Cut 3');self.assertEqual(cut['items'][0]['start_tick'],'0')
        self.assertEqual(cut['selection']['clip_count'],2)
        preview=self.source.preview_activation(pid,group['section_id'],group['digest'],1)
        self.assertEqual(preview['duration_tick'],str(8*T));self.assertFalse(preview['render_approved'])
        self.source.activate(pid,group['section_id'],group['digest'],1,preview['approval_digest'])
        reopened=G07Editor(Studio(self.studio.db_path))
        rev,doc=reopened._execute(pid,lambda db,movie:_project(db,pid))
        self.assertEqual(rev,2);self.assertEqual(doc['clips'],self.doc['clips'][2:]+self.doc['clips'][:2])
        self.assertEqual(EditorialSections(reopened).directory(pid,'sections')['active_section'],group)
        self.assertEqual([x['take_id'] for x in reopened.view(pid)['timeline']],[c['take_id'] for c in doc['clips']])
        old=self.source._run(pid,lambda db,movie:self.source._edit(db,pid,1,self.edit['digest'])[0]);self.assertEqual(old,self.doc)
        with self.assertRaises(RuntimeError):self.source.activate(pid,group['section_id'],group['digest'],1,preview['approval_digest'])

    def test_paging_take_metadata_no_media_blob_reads(self):
        def more(db,movie):
            for n in range(5,86):fixture_take(db,self.pid,n)
        self.editor._execute(self.pid,more,mutate=True)
        with patch.object(self.editor.filming,'_take',side_effect=AssertionError('must not open original media')):
            first=self.source.directory(self.pid,'takes',limit=32)
            second=self.source.directory(self.pid,'takes',after=first['next_after'],limit=32)
            third=self.source.directory(self.pid,'takes',after=second['next_after'],limit=32)
            self.assertEqual([len(x['items']) for x in (first,second,third)],[32,32,21]);self.assertIsNone(third['next_after'])
            self.assertEqual(len({x['take_id'] for p in (first,second,third) for x in p['items']}),85)
        with self.assertRaises(ValueError):self.source.directory(self.pid,'takes',limit=65)

    def test_scene_directory_exact_revision_and_keyset_takes(self):
        from backend.nvp_g05_scene_authoring import FORMAT as SCENE_FORMAT
        sid='SC_abcdef012345'
        def seed_scene(db,movie):
            self.editor.filming.g05._schema(db)
            for ordinal in range(35):
                scene=sid if ordinal==0 else f'SC_{ordinal:012x}'
                sha='a'*64;layer=b'scene fixture only';plan={'format':SCENE_FORMAT,'source':{'scene_id':scene,'project_id':self.pid,'scene_sha256':sha},'scene_name':f'Scene {ordinal}'}
                db.execute('INSERT INTO g05_scene_versions VALUES(?,?,?,?,?,?,?,?,?)',(self.pid,scene,1,sha,'approved',_json(plan),layer,_sha(layer),'2026-11-19'))
                db.execute('INSERT INTO g05_scene_heads VALUES(?,?,?,?,?,?)',(self.pid,scene,1,sha,'approved','2026-11-19'))
            for n in range(5,38):fixture_take(db,self.pid,n)
        self.editor._execute(self.pid,seed_scene,mutate=True)
        first=self.source.directory(self.pid,'scenes',limit=32)
        second=self.source.directory(self.pid,'scenes',after=first['next_after'],limit=32)
        self.assertEqual(len(first['items'])+len(second['items']),35)
        row=next(x for x in second['items'] if x['scene_id']==sid)
        ref={k:row[k] for k in ('kind','scene_id','revision','digest')}
        a=self.source.page(self.pid,ref,limit=32);b=self.source.page(self.pid,ref,limit=32,after=a['next_after'])
        self.assertEqual(len(a['items'])+len(b['items']),37);self.assertIsNone(b['next_after'])
        self.assertTrue(all(x['scene_id']==sid for x in a['items']+b['items']))
        with self.assertRaises(PermissionError):self.source.page(self.pid,{**ref,'digest':'f'*64})

    def test_section_retry_idempotent_and_group_activation_provenance(self):
        a=saved(self.source,self.pid,'Same',[ref(self.edit)])
        b=saved(self.source,self.pid,'Same',[ref(self.edit)])
        self.assertEqual(a,b);self.assertEqual(len(self.source.directory(self.pid,'sections')['items']),1)
        preview=self.source.preview_activation(self.pid,a['section_id'],a['digest'],1)
        self.source.activate(self.pid,a['section_id'],a['digest'],1,preview['approval_digest'])
        self.assertEqual(self.source.directory(self.pid,'sections')['active_section'],a)
        # Any subsequent normal edit revision supersedes the group activation.
        self.editor.mutate(self.pid,2,'note',{'clip_id':self.doc['clips'][0]['id'],'note':'Revised'})
        self.assertIsNone(self.source.directory(self.pid,'sections')['active_section'])

    def test_scope_digest_forged_approval_and_no_partial_write(self):
        p=self.source.preview(self.pid,'My section',[ref(self.edit)])
        with self.assertRaises(PermissionError):self.source.publish(self.pid,'Changed title',[ref(self.edit)],p['digest'])
        self.assertEqual(self.source.directory(self.pid,'sections')['items'],[])
        other=self.studio.create_project('Other','')['id']
        with self.assertRaises(KeyError):self.source.preview(other,'Wrong film',[ref(self.edit)])
        group=self.group()
        with self.assertRaises(KeyError):self.source.page(other,ref(group))
        with self.assertRaises(RuntimeError):self.source.page(self.pid,{**ref(group),'digest':'e'*64})
        with self.assertRaises(PermissionError):self.source.activate(self.pid,group['section_id'],group['digest'],1,'a'*64)
        self.assertEqual(self.source.directory(self.pid,'edits')['active_revision'],1)

    def test_duplicate_clip_and_depth_and_budget_denied(self):
        a=saved(self.source,self.pid,'A',[ref(self.edit,0,2)])
        b=saved(self.source,self.pid,'B',[ref(self.edit,1,2)])
        g=saved(self.source,self.pid,'Overlap',[ref(a),ref(b)])
        with self.assertRaises(ValueError):self.source.preview_activation(self.pid,g['section_id'],g['digest'],1)
        c=saved(self.source,self.pid,'Level 3',[ref(g)])
        with self.assertRaises(ValueError):self.source.preview(self.pid,'Level 4',[ref(c)])
        with self.assertRaises(ValueError):self.source.preview(self.pid,'Duplicate',[ref(a),ref(a)])
        with self.assertRaises(ValueError):self.source.preview(self.pid,'Too many',[ref(a)]*65)

    def test_browse_large_group_without_flattening_into_active_edit(self):
        children=[saved(self.source,self.pid,f'Act {i}',[ref(self.edit)]) for i in range(64)]
        root=saved(self.source,self.pid,'Large working assembly',[ref(x) for x in children])
        self.assertEqual(root['clip_count'],256)
        a=self.source.page(self.pid,ref(root),limit=32)
        b=self.source.page(self.pid,ref(root),first=a['next_first'],limit=32)
        self.assertEqual(len(a['items'])+len(b['items']),64)
        with self.assertRaises(ValueError):self.source.preview_activation(self.pid,root['section_id'],root['digest'],1)
        self.assertEqual(self.source.directory(self.pid,'edits')['active_revision'],1)

    def test_rejects_existing_dissolve_boundary_and_mutated_original(self):
        newer=copy.deepcopy(self.doc);newer['clips'][1]['transition']={'kind':'dissolve','duration_tick':T//2}
        def put(db,movie):self.editor._validate(db,self.pid,newer);self.editor._save(db,self.pid,newer,1,1)
        self.editor._execute(self.pid,put,mutate=True)
        edit=self.source.directory(self.pid,'edits')['items'][1]
        with self.assertRaises(ValueError):self.source.preview(self.pid,'Starts on dissolve',[ref(edit,1,1)])
        with self.assertRaises(ValueError):self.source.preview(self.pid,'Ends on dissolve',[ref(edit,0,1)])
        group=self.group()
        with self.studio._connection() as db:
            db.execute("UPDATE g06_frozen_takes SET take_sha256=? WHERE project_id=? AND take_id=?",('f'*64,self.pid,self.doc['clips'][0]['take_id']))
        with self.assertRaises(RuntimeError):self.source.preview_activation(self.pid,group['section_id'],group['digest'],2)

    def test_access_revoked_inside_transaction_rolls_back(self):
        preview=self.source.preview(self.pid,'Revoked',[ref(self.edit)])
        calls=0
        def check():
            nonlocal calls
            calls+=1
            if calls==2:raise PermissionError('Revoked')
        guarded=EditorialSections(self.editor,access_guard=check)
        with self.assertRaises(PermissionError):guarded.publish(self.pid,'Revoked',[ref(self.edit)],preview['digest'])
        self.assertEqual(self.source.directory(self.pid,'sections')['items'],[])

    def test_http_lock_wrong_storage_header_and_extra_fields(self):
        with patch.object(nvp_api,'studio',self.studio):
            client=TestClient(nvp_api.app);base=f'/api/projects/{self.pid}'
            url=base+'/edit/sections'
            self.assertEqual(client.get(url,params={'family':'edits'}).status_code,403)
            response=client.get(url,params={'family':'edits'},headers=HEADERS);self.assertEqual(response.status_code,200,response.text)
            self.assertIn('no-store',response.headers['cache-control'])
            self.assertEqual(client.get(base+'/live/edit/sections',params={'family':'edits'},headers=HEADERS).status_code,403)
            self.assertEqual(client.post(url+'/preview',json={'title':'A','children':[ref(self.edit)],'approved':True},headers=HEADERS).status_code,422)
            preview=client.post(url+'/preview',json={'title':'A','children':[ref(self.edit)]},headers=HEADERS);self.assertEqual(preview.status_code,200,preview.text)
            self.assertEqual(client.post(base+'/protect',json={'passphrase':SECRET},headers=HEADERS).status_code,200)
            self.assertEqual(client.post(url+'/save',json={'title':'A','children':[ref(self.edit)],'digest':preview.json()['digest']},headers=HEADERS).status_code,423)
            self.assertEqual(client.post(base+'/unlock',json={'passphrase':SECRET},headers=HEADERS).status_code,200)
            self.assertEqual(client.get(url,params={'family':'edits'},headers=HEADERS).status_code,200)
            response=client.post(url+'/save',json={'title':'A','children':[ref(self.edit)],'digest':preview.json()['digest']},headers=HEADERS)
            self.assertEqual(response.status_code,200,response.text)


@unittest.skipUnless(sys.platform=='win32','Real Windows DPAPI encrypted live storage required')
class WindowsProtectedSections(unittest.TestCase):
    def test_real_sealed_store_reopen_revoke_and_group_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            studio=Studio(Path(temp)/'studio.sqlite3');pid=studio.create_project('Shell','')['id'];grants=set();token='session-'+'a'*32
            def reopen():return LiveFilmStore(Path(temp)/'secured',grant_checker=lambda p,t:(p,t) in grants)
            store=reopen();store.create(pid,'Protected film','','',SECRET);grants.add((pid,token));store.authorize(pid,SECRET,token)
            editor=G07Editor(studio,live=store,token=token);service=EditorialSections(editor);original,_=seed(editor,pid)
            entry=service.directory(pid,'edits')['items'][0];group=saved(service,pid,'PRIVATE_SECTION_MARKER',[ref(entry,2,2),ref(entry,0,2)])
            preview=service.preview_activation(pid,group['section_id'],group['digest'],1)
            service.activate(pid,group['section_id'],group['digest'],1,preview['approval_digest'])
            grants.clear()
            with self.assertRaises(LiveFilmError):service.directory(pid,'sections')
            fresh=reopen();grants.add((pid,token));fresh.authorize(pid,SECRET,token)
            restored=G07Editor(studio,live=fresh,token=token);new=EditorialSections(restored)
            self.assertEqual(new.directory(pid,'sections')['items'][0],group)
            pointer=restored._execute(pid,lambda db,movie:db.execute('SELECT document_json FROM g07_sections WHERE project_id=? AND section_id=?',(pid,group['section_id'])).fetchone()[0])
            from backend.nvp_g07_section_pages import FORMAT as PAGE_FORMAT
            import json
            self.assertEqual(json.loads(pointer),{'format':PAGE_FORMAT,'sha256':group['digest']})
            self.assertEqual(new.cut_page(pid,group['section_id'],group['digest'],first=1,limit=2)['items'][0]['take_id'],original['clips'][3]['take_id'])
            self.assertEqual(restored._execute(pid,lambda db,movie:new.verify_activated_edit(db,pid,*_project(db,pid)))['section_digest'],group['digest'])
            rev,doc=restored._execute(pid,lambda db,movie:_project(db,pid));self.assertEqual(rev,2);self.assertEqual(doc['clips'],original['clips'][2:]+original['clips'][:2])
            for f in (Path(temp)/'secured').rglob('*'):
                if f.is_file():self.assertNotIn(b'PRIVATE_SECTION_MARKER',f.read_bytes());self.assertNotIn(b'fixture metadata only',f.read_bytes())
            with studio._connection() as db:self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='g07_sections'").fetchone())
            body=next((Path(temp)/'secured'/pid/'editorial-pages').rglob('body.nvpsealed'))
            ciphertext=bytearray(body.read_bytes());ciphertext[-30]^=1;body.write_bytes(ciphertext)
            from backend.nvp_g03_windows_vault import VaultError
            with self.assertRaises(VaultError):new.directory(pid,'sections')
            with self.assertRaises(VaultError):restored.native_assembly(pid,2,window=(0,T))

    def test_real_windows_locked_http_creator_actions_reopen(self):
        from backend.nvp_project_access import COOKIE
        with tempfile.TemporaryDirectory() as temp:
            studio=Studio(Path(temp)/'studio.sqlite3')
            with patch.object(nvp_api,'studio',studio),patch.object(nvp_api,'_live_films',None),patch.object(nvp_api,'_film_access',None):
                client=TestClient(nvp_api.app)
                created=client.post('/api/projects/encrypted',headers=HEADERS,json={'title':'Protected creator workflow','idea':'','screenplay':'','passphrase':SECRET})
                self.assertEqual(created.status_code,201,created.text)
                pid=created.json()['id'];base=f'/api/projects/{pid}';url=base+'/live/edit/sections'
                editor=G07Editor(studio,live=nvp_api.live_films(),token=client.cookies.get(COOKIE));original,_=seed(editor,pid)
                def request(path,body):
                    result=client.post(url+path,headers=HEADERS,json=body)
                    self.assertEqual(result.status_code,200,result.text);return result.json()
                listing=client.get(url,params={'family':'edits'},headers=HEADERS);self.assertEqual(listing.status_code,200,listing.text)
                edit=listing.json()['items'][0];composition={'title':'Act from creator controls','children':[ref(edit,2,2),ref(edit,0,2)]}
                reviewed=request('/preview',composition)
                saved_group=request('/save',{**composition,'digest':reviewed['digest']})['selection']
                activation={'section_id':saved_group['section_id'],'digest':saved_group['digest'],'expected_revision':1}
                proposed=request('/activation-preview',activation)
                self.assertEqual(client.post(base+'/lock',headers=HEADERS).status_code,200)
                self.assertEqual(client.post(url+'/activate',headers=HEADERS,json={**activation,'approval_digest':proposed['approval_digest']}).status_code,423)
                nvp_api._live_films=None;nvp_api._film_access=None
                self.assertEqual(client.post(base+'/unlock',headers=HEADERS,json={'passphrase':SECRET}).status_code,200)
                proposed=request('/activation-preview',activation)
                receipt=request('/activate',{**activation,'approval_digest':proposed['approval_digest']});self.assertEqual(receipt['revision'],2);self.assertFalse(receipt['render_approved'])
                fresh=G07Editor(studio,live=nvp_api.live_films(),token=client.cookies.get(COOKIE))
                current,doc=fresh._execute(pid,lambda db,movie:_project(db,pid))
                self.assertEqual(current,2);self.assertEqual(doc['clips'],original['clips'][2:]+original['clips'][:2])
                self.assertEqual(client.get(base+'/edit/sections',headers=HEADERS,params={'family':'sections'}).status_code,403)

if __name__=='__main__':unittest.main()
