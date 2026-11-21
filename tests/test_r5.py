import hashlib
from contextlib import closing
import json
import os
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock
from backend import nvp_audio_recovery as audio
from backend import nvp_feature_sections as tree
from backend import nvp_review_navigation as nav


class DiskJournal:
    def __init__(self, root):
        self.path=Path(root)/'journal.sqlite3'
        with self._tx() as db:audio.initialize(db)
    @contextmanager
    def _tx(self):
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    @contextmanager
    def _read(self):
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.journal=DiskJournal(self.root)
        self.source=b'\x01\x02\x03'*12000;self.source_sha=hashlib.sha256(self.source).hexdigest()
        (self.root/'source.pcm').write_bytes(self.source)
        self.scope={'operation':'nvp.wo4.master_partitioned_original_pcm24.v1',
                    'format':audio.FORMAT,'source_path':str(self.root/'source.pcm'),
                    'output_root':str(self.root),'source_sha256':self.source_sha,'original_take_sha256':'a'*64,
                    'frame_count':3,'sample_count':6000,'reel_count':1,'channel_order':['L','R'],
                    'sample_rate':48000,'gain':[1,1],'max_reel_frames':3}
        self.pid='project';self.project_db='/trusted/project.sqlite';self.mode='normal';self.calls=0
    def produce(self,*,approve,publication_id,before_publish,cancelled,**kw):
        self.calls+=1
        if not approve(self.scope):return {'status':'DENIED'}
        stage,target=audio.paths(self.scope,publication_id);stage.mkdir()
        (stage/'media.pcm').write_bytes(self.source)
        if self.mode=='before':raise InterruptedError('interrupted before digest')
        doc={**self.scope,'source_pcm_sha256':self.source_sha,'master_pcm_sha256':self.source_sha}
        raw=audio.canonical(doc);(stage/'manifest.json').write_text(raw,encoding='ascii')
        sha=audio.digest(raw);before_publish(sha)
        if self.mode=='prepared':raise InterruptedError('interrupted after digest')
        stage.rename(target)
        if self.mode=='hard_exit':os._exit(73)
        if self.mode=='promoted':raise InterruptedError('interrupted after promotion')
        return self.reopen({**self.scope,'destination':str(target)},sha,cancelled=cancelled)
    def reopen(self,plan,sha,*,cancelled):
        target=Path(plan['destination']);data=(target/'manifest.json').read_text(encoding='ascii')
        if audio.digest(data)!=sha:raise PermissionError('manifest tampered')
        if hashlib.sha256((self.root/'source.pcm').read_bytes()).hexdigest()!=self.source_sha:raise PermissionError('source tampered')
        return {**json.loads(data),'destination':str(target),'manifest_sha256':sha,
                'status':'PARTITIONED_PCM24_CANDIDATE_PUBLISHED','production_audio_accepted':False}
    def verify(self,receipt,*,cancelled):
        if cancelled():raise InterruptedError('cancelled')
        target=Path(receipt['destination'])
        if hashlib.sha256((target/'media.pcm').read_bytes()).hexdigest()!=receipt['master_pcm_sha256']:raise PermissionError('media tampered')
        return {'manifest_sha256':receipt['manifest_sha256'],'production_audio_accepted':False}
    def run_set(self,approve=lambda _:True,cancelled=lambda:False):
        return audio.run(self.journal,self.pid,self.project_db,approve=approve,produce=self.produce,
                         verify=self.verify,cancelled=cancelled,source_ref={'source_take_id':'Take1','source_take_revision':1})
    def only(self):
        with self.journal._read() as db:return dict(db.execute('SELECT * FROM production_audio_sets').fetchone())
    def crash(self,mode):
        self.mode=mode
        with self.assertRaises(InterruptedError):self.run_set()
        # Fresh connection and journal object (not a process-death test).
        self.journal=DiskJournal(self.root);audio.reconcile(self.journal)
        return self.only()['audio_id']
    def adopt(self,uid,approve=lambda _:True,pid=None,cancelled=lambda:False):
        return audio.adopt(self.journal,uid,pid or self.pid,self.project_db,approve=approve,
                           reopen=self.reopen,verify=self.verify,cancelled=cancelled)
    def test_normal(self):
        r=self.run_set();row=self.only();self.assertEqual(row['state'],'VERIFIED')
        self.assertEqual(row['audio_id'],r['audio_set_id']);self.assertFalse(r['production_audio_accepted'])
        self.assertEqual(json.loads(row['approval_json'])['source_take_id'],'Take1')
    def test_refused_no_record_no_output(self):
        self.assertEqual(self.run_set(lambda _:False)['status'],'DENIED')
        with self.journal._read() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM production_audio_sets').fetchone()[0],0)
        self.assertEqual(list(self.root.glob('PCM24_REELS_*')),[])
    def test_before_digest_never_adopt(self):
        uid=self.crash('before')
        self.assertEqual(self.only()['state'],'REVIEW_REQUIRED')
        with self.assertRaises(PermissionError):self.adopt(uid)
        self.assertEqual(self.calls,1)
    def test_prepared_not_promoted_never_adopt(self):
        uid=self.crash('prepared');self.assertIsNotNone(self.only()['manifest_sha256'])
        with self.assertRaises(PermissionError):self.adopt(uid)
        self.assertEqual(len(list(self.root.glob('.nvp-pcm-reels-*'))),1)
    def test_promoted_requires_explicit_approval(self):
        uid=self.crash('promoted');self.assertEqual(self.adopt(uid,lambda _:False)['status'],'DENIED')
        self.assertEqual(self.only()['state'],'REVIEW_REQUIRED')
        self.assertEqual(self.adopt(uid)['audio_set_id'],uid);self.assertEqual(self.only()['state'],'VERIFIED');self.assertEqual(self.calls,1)
    @unittest.skipUnless(hasattr(os,'fork'),'Linux portable hard-exit test')
    def test_real_process_exit_after_atomic_promotion(self):
        self.mode='hard_exit'
        pid=os.fork()
        if pid==0:
            try:self.run_set()
            finally:os._exit(99)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),73)
        self.journal=DiskJournal(self.root)
        self.assertEqual(self.only()['state'],'PREPARED')
        self.assertEqual(audio.reconcile(self.journal),1)
        uid=self.only()['audio_id'];self.assertEqual(self.adopt(uid)['audio_set_id'],uid)
        self.assertEqual(self.only()['state'],'VERIFIED')
    def test_cross_project_denied(self):
        uid=self.crash('promoted')
        with self.assertRaises(PermissionError):self.adopt(uid,pid='different')
    def test_tampered_output(self):
        uid=self.crash('promoted');(next(self.root.glob('PCM24_REELS_*'))/'media.pcm').write_bytes(b'bad')
        with self.assertRaises(PermissionError):self.adopt(uid)
        self.assertEqual(self.only()['state'],'REVIEW_REQUIRED')
    def test_tampered_source(self):
        uid=self.crash('promoted');(self.root/'source.pcm').write_bytes(b'bad')
        with self.assertRaises(PermissionError):self.adopt(uid)
    def test_tampered_manifest(self):
        uid=self.crash('promoted');(next(self.root.glob('PCM24_REELS_*'))/'manifest.json').write_text('{}')
        with self.assertRaises(PermissionError):self.adopt(uid)
    def test_cancel_during_verification(self):
        uid=self.crash('promoted')
        with self.assertRaises(InterruptedError):self.adopt(uid,cancelled=lambda:True)
        self.assertEqual(self.only()['state'],'REVIEW_REQUIRED')
    def test_restart_marks_prepared_and_running(self):
        for i in range(70):
            uid=f'{i:032x}'
            audio._insert(self.journal,uid,self.pid,self.project_db,self.scope,lambda _:True)
            if i%2:audio._prepare(self.journal,uid,'a'*64)
        self.assertEqual(audio.reconcile(self.journal),70);self.assertEqual(audio.reconcile(self.journal),0)
    def test_recovery_page_and_verified_reuse(self):
        uid=self.crash('promoted');r=audio.page(self.journal,self.pid,self.project_db)
        self.assertEqual(r['items'][0]['state'],'REVIEW_REQUIRED')
        self.assertNotIn(str(self.root),str(r))
        with self.assertRaises(PermissionError):audio.verified_receipt(self.journal,uid,self.pid,self.project_db,verify=self.verify)
        self.adopt(uid)
        self.assertEqual(audio.verified_receipt(self.journal,uid,self.pid,self.project_db,verify=self.verify)['manifest_sha256'],self.only()['manifest_sha256'])
        with self.assertRaises(PermissionError):audio.page(self.journal,'other',self.project_db,after=uid)
    def test_recovery_page_all_records(self):
        for i in range(70):audio._insert(self.journal,f'{i:032x}',self.pid,self.project_db,self.scope,lambda _:True)
        after=None;seen=[]
        while True:
            r=audio.page(self.journal,self.pid,self.project_db,after=after);seen.extend(x['audio_set_id'] for x in r['items']);self.assertLessEqual(len(r['items']),32)
            after=r['next_after']
            if after is None:break
        self.assertEqual(seen,[f'{i:032x}' for i in range(70)])
    def test_approval_tamper(self):
        uid=self.crash('promoted')
        with self.journal._tx() as db:db.execute("UPDATE production_audio_sets SET approval_json='{}'")
        with self.assertRaises(PermissionError):self.adopt(uid)


class Index:
    def __init__(self):self.rows={};self.deps={}
    def add(self,oid,data):
        sha=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        self.rows[oid]={'kind':'presentation','document_sha256':sha,'data':data}
        return {'object_id':oid,'revision':1,'sha256':sha}
    def read_revision(self,pid,oid,rev):
        if pid!='p' or rev!=1:raise PermissionError('wrong scope')
        return self.rows[oid]
    def _read_revision(self,db,pid,oid,rev):return {'document_sha':self.read_revision(pid,oid,rev)['document_sha256']}
    def register_revision(self,pid,oid,kind,data,*,expected_revision,dependencies,precommit_guard):
        assert expected_revision==0 and kind=='presentation' and len(dependencies)<=64
        precommit_guard(None);self.deps[oid]=dependencies;return self.add(oid,data)


class TreeTests(unittest.TestCase):
    def setUp(self):self.index=Index();self.tick=294000000
    def leaf(self,i,frames=10):return self.index.add('L'+str(i),{'format':tree.LEAF,'start_tick':0,'end_tick':frames*self.tick,'ordered_reel_job_ids':[f'job{i}a',f'job{i}b']})
    def group(self,oid,refs,approve=lambda _:True):return tree.register(self.index,'p',oid,refs,frame_ticks=self.tick,approve=approve)
    def test_4096_section_hierarchy(self):
        groups=[]
        for i in range(64):groups.append(self.group('G'+str(i),[self.leaf(i*64+j) for j in range(64)]))
        root=self.group('Root',groups);count=0;end=0
        for leaf in tree.walk(self.index,'p',root,frame_ticks=self.tick):
            self.assertEqual(leaf['start_tick'],end);end=leaf['end_tick'];count+=1
        self.assertEqual(count,4096);self.assertEqual(end,40960*self.tick)
        self.assertEqual(len(self.index.deps['Root']),64)
    def test_bad_child_digest(self):
        a,b=self.leaf(1),self.leaf(2);a['sha256']='0'*64
        with self.assertRaises(PermissionError):self.group('G',[a,b])
    def test_duplicate(self):
        a=self.leaf(1)
        with self.assertRaises(PermissionError):self.group('G',[a,a])
    def test_refusal(self):
        self.assertEqual(self.group('G',[self.leaf(1),self.leaf(2)],lambda _:False),{'status':'DENIED'});self.assertNotIn('G',self.index.rows)
    def test_clock_tamper(self):
        root=self.group('G',[self.leaf(1),self.leaf(2)]);self.index.rows['G']['data']['children'][1]['start_tick']+=1
        with self.assertRaises(PermissionError):list(tree.walk(self.index,'p',root,frame_ticks=self.tick))
    def test_child_tamper_during_consent(self):
        a,b=self.leaf(1),self.leaf(2)
        def approve(_):self.index.rows['L2']['document_sha256']='0'*64;return True
        with self.assertRaises(PermissionError):self.group('G',[a,b],approve)
    def test_limit(self):
        with self.assertRaises(ValueError):self.group('G',[self.leaf(i) for i in range(65)])


class NavigationTests(unittest.TestCase):
    def test_catalog_large_and_cursor_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            with closing(sqlite3.connect(Path(tmp)/'nav.sqlite')) as db, db:
                db.row_factory=sqlite3.Row
                db.execute('CREATE TABLE production_features(feature_id TEXT PRIMARY KEY,assembly_id TEXT,assembly_revision INT,assembly_sha256 TEXT,project_id TEXT,project_db TEXT,state TEXT,updated_at TEXT,created_at TEXT)')
                db.execute('CREATE INDEX ix ON production_features(project_id,project_db,created_at,feature_id)')
                db.executemany('INSERT INTO production_features VALUES(?,?,?,?,?,?,?,?,?)',((f'f{i:06d}',f'a{i}',1,'a'*64,'p','/p','INDEXED','t',f'{i//3:06d}') for i in range(3000)))
                db.execute("INSERT INTO production_features VALUES('foreign','a',1,'sha','q','/q','INDEXED','t','999999')")
                cursor=None;seen=[]
                while True:
                    rows,cursor=nav.feature_window(db,'p','/p',after=cursor)
                    self.assertLessEqual(len(rows),32);seen.extend(r['feature_id'] for r in rows)
                    if cursor is None:break
                self.assertEqual(seen,[f'f{i:06d}' for i in reversed(range(3000))])
                with self.assertRaises(PermissionError):nav.feature_window(db,'p','/p',after=['999999','foreign'])
    def test_invalid_cursor_shape(self):
        with self.assertRaises(ValueError):nav.cursors({'edit':None})
        with self.assertRaises(ValueError):nav.feature_window(None,'p','/p',limit=65)
    def test_first_page(self):self.assertEqual(nav.cursors(None),{'edit':None,'presentation':None,'features':None})

class DeliveryGroupTests(unittest.TestCase):
    leaf=TreeTests.leaf
    group=TreeTests.group
    def setUp(self):
        self.index=Index();self.tick=294000000;self.native={}
        for i in range(4):
            src=self.leaf(i)
            receipt=self.index.add('R'+str(i),{'format':'native receipt','source_ref':src})
            self.native['F'+str(i)]={'feature_id':'F'+str(i),'source_ref':src,'receipt_ref':receipt,
                 'frame_count':10,'profile':'2K','manifest_sha256':'a'*64,'production_dcp_accepted':False}
    def verify_leaf(self,uid,src):return self.native[uid]
    def group_receipt(self,oid,src,sel,approve=lambda _:True):
        from backend import nvp_feature_delivery_groups as receipts
        return receipts.register(self.index,'p',oid,src,sel,frame_ticks=self.tick,verify_leaf=self.verify_leaf,approve=approve)
    def source_pair(self,i):
        return self.group('G'+str(i),[self.native['F'+str(i*2+j)]['source_ref'] for j in range(2)])
    def test_nested_delivery(self):
        from backend import nvp_feature_delivery_groups as receipts
        a,b=self.source_pair(0),self.source_pair(1);root=self.group('Root',[a,b])
        ra=self.group_receipt('DA',a,[{'feature_id':'F0'},{'feature_id':'F1'}]);rb=self.group_receipt('DB',b,[{'feature_id':'F2'},{'feature_id':'F3'}])
        dr=self.group_receipt('DROOT',root,[ra,rb]);r=receipts.verify_group(self.index,'p',dr,frame_ticks=self.tick,verify_leaf=self.verify_leaf)
        self.assertEqual(r['section_count'],4);self.assertEqual(r['end_tick'],40*self.tick);self.assertFalse(r['single_dcp_published'])
    def test_wrong_order(self):
        with self.assertRaises(PermissionError):self.group_receipt('D',self.source_pair(0),[{'feature_id':'F1'},{'feature_id':'F0'}])
    def test_profile_mismatch(self):
        self.native['F1']['profile']='4K'
        with self.assertRaises(PermissionError):self.group_receipt('D',self.source_pair(0),[{'feature_id':'F0'},{'feature_id':'F1'}])
    def test_audited_output_changed(self):
        def approve(_):self.native['F1']['manifest_sha256']='b'*64;return True
        with self.assertRaises(PermissionError):self.group_receipt('D',self.source_pair(0),[{'feature_id':'F0'},{'feature_id':'F1'}],approve)
    def test_exact_coverage(self):
        with self.assertRaises(ValueError):self.group_receipt('D',self.source_pair(0),[{'feature_id':'F0'}])
    def test_denied_group(self):
        self.assertEqual(self.group_receipt('D',self.source_pair(0),[{'feature_id':'F0'},{'feature_id':'F1'}],lambda _:False),{'status':'DENIED'})
        self.assertNotIn('D',self.index.rows)

if __name__=="__main__":unittest.main()
