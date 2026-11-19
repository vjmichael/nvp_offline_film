import sqlite3
import tempfile
import unittest
from pathlib import Path
from backend.nvp_production_catalog_pages import page, validate_page

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=sqlite3.connect(Path(self.tmp.name)/'journal.db');self.addCleanup(self.db.close)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''CREATE TABLE production_jobs(job_id TEXT PRIMARY KEY, project_id TEXT, state TEXT, task_kind TEXT, updated_at TEXT, created_at TEXT, manifest_json TEXT);
        CREATE INDEX production_jobs_catalog_page ON production_jobs(project_id,created_at,job_id);
        CREATE TABLE production_features(feature_id TEXT PRIMARY KEY, project_id TEXT, project_db TEXT, state TEXT, assembly_sha256 TEXT, manifest_sha256 TEXT, cancel_requested INTEGER, updated_at TEXT, created_at TEXT, manifest_json TEXT);
        CREATE INDEX production_features_catalog_page ON production_features(project_id,project_db,created_at,feature_id);''')
        self.db.executemany('INSERT INTO production_jobs VALUES (?,?,?,?,?,?,?)',((f'j{i:06d}', 'p','QUEUED','verify','now',f't{i//5:06d}','private') for i in range(30000)))
        self.db.executemany('INSERT INTO production_features VALUES (?,?,?,?,?,?,?,?,?,?)',((f'f{i:06d}', 'p','/approved','INDEXED','a'*64,'b'*64,0,'now',f't{i//5:06d}','private') for i in range(3000)))
        self.db.execute("INSERT INTO production_jobs VALUES ('foreign','q','QUEUED','verify','now','t000001','private')")
        self.db.execute("INSERT INTO production_features VALUES ('foreign','p','/foreign','INDEXED','a','b',0,'now','t000001','private')")
        self.db.commit();self.db.execute('PRAGMA query_only=ON')
    def test_full_keyset_scan(self):
        for kind,count,key,extra in [('jobs',30000,'job_id',{}),('features',3000,'feature_id',{'project_db':'/approved'})]:
            cursor=None;n=0
            while True:
                rows,cursor=page(self.db,'p',kind=kind,after=cursor,limit=64,**extra)
                self.assertLessEqual(len(rows),64)
                for row in rows:
                    self.assertEqual(row[key],f'{key[0] if kind=="jobs" else "f"}{n:06d}');n+=1
                    self.assertNotIn('manifest_json',row);self.assertNotIn('project_db',row)
                if cursor is None: break
            self.assertEqual(n,count)
    def test_scope_and_cursor(self):
        for kind,extra in [('jobs',{}),('features',{'project_db':'/approved'})]:
            with self.assertRaises(PermissionError):page(self.db,'p',kind=kind,after=['t000001','foreign'],**extra)
            with self.assertRaises(PermissionError):page(self.db,'p',kind=kind,after=['missing','j000000'],**extra)
        self.assertEqual(page(self.db,'q',kind='features',project_db='/approved'),([],None))
        with self.assertRaises(PermissionError):page(self.db,'p',kind='features')
    def test_invalid_limits_and_cursor(self):
        for x in (0,65,True,1.0):
            with self.assertRaises(ValueError):validate_page(None,x)
        for x in ('x',[],['x','a'*129],['x','/path'],[1,'id']):
            with self.assertRaises(ValueError):validate_page(x,32)
    def test_index_plan(self):
        plan=self.db.execute('EXPLAIN QUERY PLAN SELECT job_id FROM production_jobs WHERE project_id=? AND (created_at,job_id)>(?,?) ORDER BY created_at,job_id LIMIT ?',('p','t000001','j000001',65)).fetchall()
        self.assertIn('production_jobs_catalog_page',str([tuple(r) for r in plan]))
        self.assertNotIn('TEMP B-TREE',str([tuple(r) for r in plan]))
if __name__=='__main__':unittest.main()
