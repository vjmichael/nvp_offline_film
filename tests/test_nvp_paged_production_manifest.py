"""Portable SQLite transactions and real bytes; no EFS/native ownership claim."""
from hashlib import sha256
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend import nvp_production_journal as j
from backend import nvp_paged_production_manifest as p


class PagedProductionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.index=FilmIndex(Studio(self.root/"film.sqlite"))
        self.pid=self.index.studio.create_project("Portable source fixture", "")["id"]
        self.assembly=self.index.register_revision(self.pid,"Cut","edit",{"fixture":True})
        self.source=self.root/"source.bin"; self.source.write_bytes(b"original")
        self.digest=sha256(b"original").hexdigest()
        # Real disk-backed SQLite WAL with its original transaction methods.
        # Explicitly stub only OS EFS/native supervisor guard, not journal logic.
        self.journal=object.__new__(j.ProductionJournal)
        self.journal.root=self.root;self.journal.db_path=self.root/"journal.sqlite"
        for name,fn in (("_safe_source",lambda path:str(Path(path).resolve(strict=True))),
                        ("_hash_stream",lambda path:(sha256(path.read_bytes()).hexdigest(),path.stat().st_size)),
                        ("_require_owner",lambda root:None)):
            ctx=patch.object(j,name,side_effect=fn);ctx.start();self.addCleanup(ctx.stop)
        self.journal._check_storage=lambda:None
        with self.journal._tx() as db: self.journal._initialize_schema(db)

    def factory(self,count):
        for first in range(0,count,p.PAGE_SIZE):
            yield [{"start_tick":i,"end_tick":i+1,"source_path":str(self.source),
                    "source_sha256":self.digest,"source_bytes":8}
                   for i in range(first,min(first+p.PAGE_SIZE,count))]

    def submit(self,count=130,approve=lambda _:True,factory=None):
        return self.journal.submit_paged(self.index,self.pid,assembly_id="Cut",assembly_revision=1,
                assembly_sha256=self.assembly["document_sha256"],
                page_factory=factory or (lambda:self.factory(count)),approve=approve)

    def test_over_legacy_limit_atomic_publish_and_reopen(self):
        received=[]
        receipt=self.submit(12001,approve=lambda scope:received.append(scope) or True)
        uid=receipt["job_id"]
        self.assertEqual(receipt["segment_count"],12001)
        self.assertEqual(received[0]["manifest_sha256"],receipt["manifest_sha256"])
        with self.journal._read() as db:
            job=db.execute("SELECT manifest_json FROM production_jobs").fetchone()
            self.assertLess(len(job[0]),2048)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM production_manifest_pages").fetchone()[0],188)
        reopened=object.__new__(j.ProductionJournal);reopened.root=self.root
        reopened.db_path=self.journal.db_path;reopened._check_storage=lambda:None
        page=reopened.status_page(uid,first_position=12000,expected_project_id=self.pid)
        self.assertEqual(page["total_segments"],12001)
        self.assertEqual(page["segments"][0]["position"],12000)
        self.assertIsNone(page["next_position"])
        self.assertEqual(len(reopened.status(uid)["segments"]),64)
        self.assertFalse(page["production_dcp_accepted"])

    def test_refusal_and_mutated_second_pass_rollback(self):
        self.assertEqual(self.submit(approve=lambda _:False)["status"],"DENIED")
        self.assertEqual(self.journal.list_jobs(),[])
        passes=0
        def factory():
            nonlocal passes
            passes+=1
            yield from self.factory(130 if passes==1 else 129)
        with self.assertRaises(PermissionError): self.submit(factory=factory)
        with self.journal._read() as db:
            for table in ("production_jobs","production_segments","production_manifest_pages","production_events"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0],0)

    def test_tail_tamper_refused_at_claim_and_status(self):
        uid=self.submit()["job_id"]
        with self.journal._tx() as db:
            db.execute("UPDATE production_segments SET expected_sha256=? WHERE job_id=? AND position=129",("a"*64,uid))
        with self.assertRaises(RuntimeError):self.journal.status_page(uid,limit=1)
        with self.assertRaises(RuntimeError):self.journal.claim_next("Owner",os.getpid())
        with self.journal._read() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM production_segments WHERE state='RUNNING'").fetchone()[0],0)

    def test_missing_page_and_rehashed_position_refused(self):
        uid=self.submit()["job_id"]
        import json
        with self.journal._tx() as db:
            row=db.execute("SELECT page_json FROM production_manifest_pages WHERE job_id=? AND page_index=2",(uid,)).fetchone()
            page=json.loads(row[0]);page["segments"][-1]["position"]=999
            raw=p.canon(page);db.execute("UPDATE production_manifest_pages SET page_json=?,page_sha256=? WHERE job_id=? AND page_index=2",(raw.decode(),sha256(raw).hexdigest(),uid))
            db.execute("UPDATE production_segments SET position=999 WHERE job_id=? AND position=129",(uid,))
        with self.assertRaises(RuntimeError):self.journal.status_page(uid)
        with self.journal._tx() as db:db.execute("DELETE FROM production_manifest_pages WHERE job_id=? AND page_index=2",(uid,))
        with self.assertRaises(RuntimeError):self.journal.status_page(uid)

    def test_rehashed_page_index_boolean_cannot_change_approved_root(self):
        uid=self.submit()["job_id"]
        import json
        with self.journal._tx() as db:
            row=db.execute("SELECT page_json FROM production_manifest_pages WHERE job_id=? AND page_index=1",(uid,)).fetchone()
            page=json.loads(row[0]);page["page_index"]=True
            raw=p.canon(page)
            db.execute("UPDATE production_manifest_pages SET page_json=?,page_sha256=? WHERE job_id=? AND page_index=1",
                       (raw.decode(),sha256(raw).hexdigest(),uid))
        with self.assertRaises(RuntimeError):self.journal.status_page(uid)

    def test_large_recovery_report_bounded_and_exact_counts(self):
        uid=self.submit()["job_id"]
        with self.journal._tx() as db:
            # Fixture-only historical states exercise the >one-page recovery path.
            db.execute("UPDATE production_segments SET state='VERIFIED',verified_sha256=?,verified_bytes=8 WHERE position<100 AND job_id=?",
                       (self.digest,uid))
        self.source.write_bytes(b"modified")
        report=self.journal.reconcile_after_restart()["jobs"][0]
        self.assertEqual(report["tampered_count"],100)
        self.assertEqual(report["tampered"],list(range(64)))
        self.assertTrue(report["positions_truncated"])
        self.assertEqual(report["state"],"REVIEW_REQUIRED")
        self.assertEqual(self.journal.status_page(uid,first_position=99,limit=1)["segments"][0]["state"],"REVIEW_REQUIRED")

    def test_single_claim_restart_cancel_and_review_retry(self):
        uid=self.submit()["job_id"]
        claim=self.journal.claim_next("Owner",os.getpid());self.assertEqual(claim["position"],0)
        self.assertIsNone(self.journal.claim_next("Other",os.getpid()))
        self.assertFalse(self.journal.claim_cancel_requested("Owner",uid,0))
        with self.assertRaises(PermissionError): self.journal.claim_cancel_requested("Other",uid,0)
        with self.assertRaises(PermissionError):self.journal.finish_verified("Other",uid,0,self.digest,8)
        self.journal.finish_verified("Owner",uid,0,self.digest,8)
        self.assertEqual(self.journal.claim_next("Owner",os.getpid())["position"],1)
        report=self.journal.reconcile_after_restart()["jobs"][0]
        self.assertEqual(report["interrupted"],[1]);self.assertEqual(report["state"],"QUEUED")
        self.source.write_bytes(b"modified")
        report=self.journal.reconcile_after_restart()["jobs"][0]
        self.assertEqual(report["tampered"],[0]);self.assertEqual(report["state"],"REVIEW_REQUIRED")
        with self.assertRaises(PermissionError):self.journal.authorize_review_retry(uid,lambda _:True)
        self.source.write_bytes(b"original")
        self.assertEqual(self.journal.authorize_review_retry(uid,lambda _:True)["segments_requeued"],1)
        self.assertEqual(self.journal.claim_next("NewOwner",os.getpid())["position"],0)
        self.journal.request_cancel(uid,lambda _:True)
        self.assertTrue(self.journal.claim_cancel_requested("NewOwner",uid,0))
        with self.assertRaises(RuntimeError):self.journal.finish_verified("NewOwner",uid,0,self.digest,8)
        self.journal.finalize_cancel(uid)
        self.assertEqual(self.journal.status(uid)["state"],"CANCELLED")
        self.assertIsNone(self.journal.claim_next("NewOwner",os.getpid()))

    def test_existing_read_only_storage_snapshot_is_reused(self):
        uid=self.submit()["job_id"]
        from contextlib import contextmanager
        original_read=self.journal._read
        @contextmanager
        def snapshot():
            with original_read() as db:
                db.execute("BEGIN")
                yield db
        with patch.object(self.journal,"_read",side_effect=snapshot):
            self.assertEqual(self.journal.status(uid)["total_segments"],130)
            self.assertEqual(self.journal.status_page(uid,first_position=128)["total_segments"],130)

    def test_legacy_and_paged_coexist(self):
        segments=next(self.factory(3))
        legacy=self.journal.submit(self.index,self.pid,assembly_id="Cut",assembly_revision=1,
            assembly_sha256=self.assembly["document_sha256"],segments=segments,approve=lambda _:True)
        paged=self.submit()
        self.assertEqual(len(self.journal.status(legacy["job_id"])["segments"]),3)
        self.assertEqual(len(self.journal.status(paged["job_id"])["segments"]),64)
        with self.assertRaises(PermissionError):self.journal.status_page(paged["job_id"],expected_project_id="foreign")

    def test_bad_page_geometry(self):
        for factory in (lambda:iter(()),lambda:iter([next(self.factory(1)),next(self.factory(2))]),
                        lambda:iter([next(self.factory(64))*2])):
            with self.assertRaises(ValueError):self.submit(factory=factory)


@unittest.skipUnless(os.name=="nt","Windows encrypted state and supervisor lease required")
class NativePagedJournalTests(unittest.TestCase):
    def test_real_efs_pages_and_native_owner_reopen(self):
        from backend.nvp_w1g_encrypted_source import require_efs_stage
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); require_efs_stage(root)
            index=FilmIndex(Studio(root/"film.sqlite"))
            pid=index.studio.create_project("Encrypted source fixture", "")["id"]
            assembly=index.register_revision(pid,"Cut","edit",{"fixture":True})
            source=root/"original.bin";source.write_bytes(b"original")
            digest=sha256(b"original").hexdigest()
            def factory():
                for first in range(0,130,p.PAGE_SIZE):
                    yield [{"start_tick":i,"end_tick":i+1,"source_path":str(source),
                            "source_sha256":digest,"source_bytes":8}
                           for i in range(first,min(first+p.PAGE_SIZE,130))]
            journal=j.ProductionJournal(root/"journal")
            job=journal.submit_paged(index,pid,assembly_id="Cut",assembly_revision=1,
                assembly_sha256=assembly["document_sha256"],page_factory=factory,approve=lambda _:True)
            uid=job["job_id"]
            with j.SingletonSupervisor(journal.root):
                claim=journal.claim_next("NativeFixture",os.getpid())
                self.assertEqual(claim["position"],0)
                journal.finish_verified("NativeFixture",uid,0,digest,8)
                self.assertEqual(journal.claim_next("NativeFixture",os.getpid())["position"],1)
            reopened=j.ProductionJournal(journal.root)
            with j.SingletonSupervisor(reopened.root):
                result=reopened.reconcile_after_restart()["jobs"][0]
                self.assertEqual(result["interrupted"],[1])
                self.assertEqual(result["state"],"QUEUED")
                self.assertEqual(reopened.status_page(uid,first_position=128)["total_segments"],130)
                self.assertEqual(reopened.claim_next("NewNativeFixture",os.getpid())["position"],1)
                reopened.request_cancel(uid,lambda _:True)
                reopened.finalize_cancel(uid)
            self.assertEqual(reopened.status(uid)["state"],"CANCELLED")
            self.assertEqual(source.read_bytes(),b"original")


if __name__=="__main__":unittest.main()
