"""Real disk SQLite and journal methods; native EFS/lease is qualified separately."""
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from unittest.mock import patch
import unittest
from backend import nvp_wo4_feature_pages as pages
from backend import nvp_wo4_feature_journal as journal
from backend.nvp_production_journal import _canonical,_digest


class FeaturePageTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.path=self.root/'journal.sqlite3'
        self.j=object.__new__(journal.FeatureJournal);self.j.root=self.root
        def conn():
            db=sqlite3.connect(self.path,isolation_level=None);db.row_factory=sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON');return db
        @contextmanager
        def tx():
            db=conn();db.execute('BEGIN IMMEDIATE')
            try:yield db;db.commit()
            except BaseException:db.rollback();raise
            finally:db.close()
        @contextmanager
        def read():
            db=conn();db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            try:yield db
            finally:db.close()
        self.j._tx=tx;self.j._read=read
        with tx() as db:
            db.execute('''CREATE TABLE production_features(feature_id TEXT PRIMARY KEY,project_id,assembly_id,
                assembly_revision,assembly_sha256,project_db,output_root,title,profile,manifest_json,
                manifest_sha256,state,owner,cancel_requested DEFAULT 0,file_sha_json,filmindex_sha256,updated_at,created_at)''')
            db.execute('CREATE TABLE production_jobs(state)');pages.initialize(db)
        self.header={'format':journal.FORMAT,'project_id':'project','assembly_id':'edit','assembly_revision':1,
                     'assembly_sha256':'a'*64,'project_db':'db','output_root':str(self.root),'title':'Test movie',
                     'profile':'2K_FLAT_24','ids':{'cpl':'fixed'},'production_dcp_accepted':False}
        self.manifest={**self.header,'ordered_reel_job_ids':[str(i) for i in range(125)],
            'reels':[{'frames':7200,'picture':{'file_path':'secret','file_sha256':'b'*64},
                      'sound':{'file_path':'secret','file_sha256':'c'*64}} for i in range(125)],
            'source_reel_authority':[{'source_take_sha256':'d'*64,'mastering_decision_sha256':'a'*64} for i in range(125)]}
        self.sha=_digest(_canonical(self.manifest))
        self.files={f'{kind}_{i:04d}.mxf': 'e'*64 for i in range(125) for kind in ('picture','sound')}
        self.files.update({name:'f'*64 for name in ('CPL.xml','PKL.xml','ASSETMAP.xml','VOLINDEX.xml')})
        p=patch.object(journal,'_require_owner');p.start();self.addCleanup(p.stop)

    def insert(self,fid='feature',legacy=False,state='QUEUED'):
        with self.j._tx() as db:
            db.execute('INSERT INTO production_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (fid,'project','edit',1,'a'*64,'db',str(self.root),'Test movie','2K_FLAT_24',
                        _canonical(self.manifest).decode('ascii'),self.sha,state,None,0,None,None,'now','now'))
            if not legacy:
                root=pages.store_source(db,fid,self.manifest,self.sha)
                db.execute('UPDATE production_features SET manifest_json=? WHERE feature_id=?',(root,fid))
        return fid

    def page(self,fid='feature',**kw):
        return self.j.feature_page(fid,project_id='project',project_db='db',**kw)

    def test_exact_source_hash_bounded_page_and_legacy(self):
        self.insert();self.insert('old',legacy=True)
        with self.j._read() as db:
            row=db.execute('SELECT manifest_json FROM production_features WHERE feature_id=?',('feature',)).fetchone()
            self.assertLess(len(row[0]),1500)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM production_feature_pages').fetchone()[0],2)
        for uid in ('feature','old'):
            self.assertEqual(json.loads(self.j.feature(uid)['manifest_json']),self.manifest)
            got=self.page(uid,first=64,limit=64)
            self.assertEqual((got['total'],len(got['entries']),got['next_first']),(125,61,None))
            self.assertEqual(got['entries'][-1]['reel'],125)
            self.assertNotIn('secret',repr(got));self.assertFalse(got['production_dcp_accepted'])
        with self.assertRaises(PermissionError):self.j.feature_page('feature',project_id='other',project_db='db')
        with self.assertRaises(ValueError):self.page(limit=65)

    def test_tail_tamper_rehash_claim_fails(self):
        fid=self.insert()
        with self.j._tx() as db:
            raw=db.execute('SELECT page_json FROM production_feature_pages WHERE page_index=1').fetchone()[0]
            page=json.loads(raw);page['rows'][-1]['reels']['frames']=3
            data=_canonical(page);db.execute('UPDATE production_feature_pages SET page_json=?,page_sha256=? WHERE page_index=1',(data.decode(),_digest(data)))
        with self.assertRaises(PermissionError):self.page(first=0,limit=1)
        with self.assertRaises(PermissionError):self.j.next_feature('Owner')
        self.assertEqual(self.j.reconcile_features()['jobs'][0]['state'],'REVIEW_REQUIRED')
        self.assertIsNone(self.j.next_feature('Owner'))

    def test_checkpoint_output_pages_and_rollback(self):
        fid=self.insert()
        with self.assertRaises(RuntimeError):
            with self.j._tx() as db:
                pages.store_output(db,fid,self.files,self.sha);raise RuntimeError('crash')
        self.assertEqual(self.page(kind='output')['total'],0)
        with self.j._tx() as db:
            pointer=pages.store_output(db,fid,self.files,self.sha)
            db.execute('UPDATE production_features SET file_sha_json=?,state=? WHERE feature_id=?',(pointer,'PUBLISHED_PENDING_INDEX',fid))
        self.assertEqual(json.loads(self.j.feature(fid)['file_sha_json']),self.files)
        self.assertEqual(self.page(kind='output',first=192,limit=64)['total'],254)
        with self.j._tx() as db:
            db.execute("DELETE FROM production_feature_pages WHERE kind='output' AND page_index=3")
        with self.assertRaises(PermissionError):self.page(first=0,limit=1)

    def test_actual_commit_hashes_before_durable_pages(self):
        fid=self.insert();self.j.next_feature('Owner')
        folder=self.root/'DCP_FEATURE_fixed';folder.mkdir()
        manifest=self.manifest
        # Portable fixture supplies original verified source and structure boundaries;
        # commit_feature independently hashes the actual package bytes.
        for name in self.files:(folder/name).write_bytes(name.encode())
        files={name:_digest(name.encode()) for name in self.files}
        # Use explicit source/approval fields required by actual commit.
        authority=manifest['source_reel_authority'][0]
        # Make the existing source descriptor valid for this isolated commit test.
        # The fixture deliberately doesn't represent real MXF or DCP structure.
        receipt={'status':'MULTIREEL_STRUCTURAL_DCP_PUBLISHED','destination':str(folder),
            'cpl_uuid':'fixed','reel_count':125,'source_reel_authority':manifest['source_reel_authority'],
            'source_take_sha256':authority['source_take_sha256'],'mastering_decision_sha256':authority['mastering_decision_sha256'],
            'feature_assembly_sha256':manifest['assembly_sha256'],'file_sha256':files}
        audit={'status':'STRUCTURE_AND_SHA_VERIFIED','cpl_uuid':'fixed','reel_durations':[7200]*125}
        with patch.object(self.j,'_verify_feature_sources'),patch.object(self.j,'_verify_feature_package'),patch.object(self.j,'_audit_new_feature_package',return_value=audit):
            bad={**receipt,'file_sha256':{**files,'CPL.xml':'0'*64}}
            with self.assertRaises(PermissionError):self.j.commit_feature('Owner',fid,bad)
            self.assertEqual(self.page(kind='output')['total'],0)
            self.assertEqual(self.j.commit_feature('Owner',fid,receipt)['status'],'PUBLISHED_PENDING_INDEX')
        self.assertEqual(self.page(kind='output')['total'],254)

    def test_claim_once_and_recovery_preserves_artifact(self):
        fid=self.insert();job=self.j.next_feature('Owner');self.assertEqual(job['manifest'],self.manifest)
        self.assertIsNone(self.j.next_feature('Other'))
        for f,args in ((self.j.claim_next,('Other',1)),(self.j.next_track,('Other',1)),(self.j.next_delivery,('Other',1)),(self.j.next_feature_index,())):
            with self.assertRaises(PermissionError):f(*args)
        target=self.root/'DCP_FEATURE_fixed';target.mkdir();(target/'original').write_bytes(b'keep')
        self.j.request_feature_cancel(fid,lambda _:True)
        self.assertEqual(self.j.finalize_feature_cancel(fid,'Owner')['status'],'REVIEW_REQUIRED')
        self.assertEqual((target/'original').read_bytes(),b'keep')
        self.assertIsNone(self.j.next_feature('Owner'))

    def test_recovery_paged_report_and_clean_cancel(self):
        for i in range(70):self.insert(f'job{i:03d}',legacy=True,state='STAGING')
        report=self.j.reconcile_features();self.assertEqual(report['total_jobs'],70)
        self.assertEqual(len(report['jobs']),64);self.assertTrue(report['report_truncated'])
        self.assertEqual(self.j.feature('job069')['state'],'REVIEW_REQUIRED')
        self.insert('clean');self.j.request_feature_cancel('clean',lambda _:True)
        self.assertEqual(self.j.finalize_feature_cancel('clean',None)['status'],'CANCELLED')


if __name__=='__main__':unittest.main()
