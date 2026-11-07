"""WO4-LF01 durable SQLite job journal and trusted FilmIndex admission."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import os

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import ProductionJournal,TICKS_PER_SECOND
from backend.nvp_production_supervisor import ProductionSupervisor,SingletonSupervisor


class DurableProductionJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.studio=Studio(self.root/"studio.sqlite3")
        self.pid=self.studio.create_project("Durable NVP source", "Original")["id"]
        self.index=FilmIndex(self.studio)
        self.assembly=self.index.register_revision(
            self.pid,"ApprovedCut","edit",{
                "format":"nvp.test.approved_assembly.v1",
                "director_reviewed":True,"original_take_modified":False,
                "start_tick":0,"end_tick":3*TICKS_PER_SECOND},
            expected_revision=0,dependencies=[])
        self.state_root=self.root/"supervisor"
        self.journal=ProductionJournal(self.state_root)
        self.file1=self.root/"original_media_A.bin"
        self.file2=self.root/"original_media_B.bin"
        self.file1.write_bytes(b"source-media-A" * 10000)
        self.file2.write_bytes(b"source-media-B" * 15000)
        self.before={str(f):sha256(f.read_bytes()).hexdigest()
                     for f in (self.file1,self.file2)}

    def segment(self,file,start,end):
        raw=file.read_bytes()
        return {"start_tick":start,"end_tick":end,"source_path":str(file),
                "source_sha256":sha256(raw).hexdigest(),
                "source_bytes":len(raw)}

    def submit(self,*,segments=None,approve=lambda _:True,assembly_sha=None):
        if segments is None:
            segments=[
                self.segment(self.file1,0,TICKS_PER_SECOND),
                self.segment(self.file2,TICKS_PER_SECOND,2*TICKS_PER_SECOND),
                self.segment(self.file1,2*TICKS_PER_SECOND,3*TICKS_PER_SECOND),
            ]
        return self.journal.submit(
            self.index,self.pid,assembly_id="ApprovedCut",assembly_revision=1,
            assembly_sha256=assembly_sha or self.assembly["document_sha256"],
            segments=segments,approve=approve)

    def test_exact_filmindex_revision_and_consent_required(self):
        with self.assertRaises(PermissionError):
            self.submit(assembly_sha="0"*64)
        result=self.submit(approve=lambda _:False)
        self.assertEqual(result["status"],"DENIED")
        self.assertEqual(self.journal.list_jobs(),[])
        accepted=self.submit()
        self.assertEqual(accepted["status"],"QUEUED")
        report=self.journal.status(accepted["job_id"])
        self.assertEqual(report["total_segments"],3)
        self.assertEqual(report["verified_segments"],0)
        self.assertFalse(report["production_dcp_accepted"])

    def test_creator_scope_changes_cannot_rewrite_trusted_manifest(self):
        def malicious(scope):
            scope["assembly_sha256"]="f"*64
            scope["segment_count"]=0
            return True
        accepted=self.submit(approve=malicious)
        snapshot=self.journal.status(accepted["job_id"])
        self.assertEqual(snapshot["assembly_sha256"],
                         self.assembly["document_sha256"])
        self.assertEqual(snapshot["total_segments"],3)

    def test_read_only_supervisor_completes_all_sections_and_is_reopenable(self):
        result=self.submit()
        with SingletonSupervisor(self.state_root):
            runner=ProductionSupervisor(self.journal)
            for index in range(3):
                record=runner.run_one()
                self.assertEqual(record["status"],"SEGMENT_VERIFIED")
            self.assertEqual(runner.run_one()["status"],"IDLE")
        reopened=ProductionJournal(self.state_root)
        job=reopened.status(result["job_id"])
        self.assertEqual(job["verified_segments"],3)
        self.assertEqual(job["state"],"VERIFY_COMPLETE")
        for file in (self.file1,self.file2):
            self.assertEqual(sha256(file.read_bytes()).hexdigest(),
                             self.before[str(file)])

    def test_tampered_source_blocks_commit_without_deleting_it(self):
        accepted=self.submit()
        self.file1.write_bytes(b"corrupted SOURCE")
        with SingletonSupervisor(self.state_root):
            runner=ProductionSupervisor(self.journal)
            result=runner.run_one()
        self.assertEqual(result["status"],"REVIEW_REQUIRED")
        state=self.journal.status(accepted["job_id"])
        self.assertEqual(state["state"],"REVIEW_REQUIRED")
        self.assertTrue(self.file1.exists())
        self.assertEqual(self.file1.read_bytes(),b"corrupted SOURCE")

    def test_wrong_owner_cannot_commit_another_supervisors_segment(self):
        accepted=self.submit()
        claim=self.journal.claim_next("WorkerA",321)
        self.assertEqual(claim["position"],0)
        with self.assertRaises(PermissionError):
            self.journal.finish_verified("WorkerB",accepted["job_id"],0,
                claim["expected_sha256"],claim["expected_bytes"])
        self.assertEqual(self.journal.status(accepted["job_id"])["state"],"RUNNING")

    def test_restart_requeues_interrupted_read_only_work(self):
        accepted=self.submit()
        claim=self.journal.claim_next("DeadWorker",12345)
        self.assertEqual(claim["position"],0)
        with SingletonSupervisor(self.state_root):
            reconciliation=self.journal.reconcile_after_restart()
            self.assertEqual(reconciliation["jobs"][0]["interrupted"],[0])
            self.assertEqual(self.journal.status(accepted["job_id"])["state"],
                             "QUEUED")
            runner=ProductionSupervisor(self.journal)
            for _ in range(3):
                self.assertEqual(runner.run_one()["status"],"SEGMENT_VERIFIED")
        self.assertEqual(self.journal.status(accepted["job_id"])["state"],
                         "VERIFY_COMPLETE")

    def test_restart_detects_changed_previously_verified_source(self):
        accepted=self.submit()
        with SingletonSupervisor(self.state_root):
            runner=ProductionSupervisor(self.journal)
            for _ in range(3):
                runner.run_one()
        self.file2.write_bytes(b"tampered and never auto removed")
        with SingletonSupervisor(self.state_root):
            report=self.journal.reconcile_after_restart()
        self.assertEqual(report["jobs"][0]["tampered"],[1])
        self.assertEqual(self.journal.status(accepted["job_id"])["state"],
                         "REVIEW_REQUIRED")
        self.assertTrue(self.file2.exists())

    def test_cancellation_requires_distinct_host_approval(self):
        accepted=self.submit()
        job_id=accepted["job_id"]
        self.assertEqual(self.journal.request_cancel(job_id,lambda _:False)
                         ["status"],"DENIED")
        self.assertFalse(self.journal.status(job_id)["cancel_requested"])
        self.assertEqual(self.journal.request_cancel(job_id,lambda _:True)
                         ["status"],"CANCEL_REQUESTED")
        with SingletonSupervisor(self.state_root):
            runner=ProductionSupervisor(self.journal)
            runner.run_one()
        self.assertEqual(self.journal.status(job_id)["state"],"CANCELLED")
        self.assertTrue(self.file1.is_file())

    def test_planning_three_hours_does_not_allocate_three_hours_of_pixels(self):
        plan=[self.segment(self.file1,0,3*3600*TICKS_PER_SECOND)]
        job=self.submit(segments=plan)
        status=self.journal.status(job["job_id"])
        self.assertEqual(status["total_segments"],1)
        self.assertEqual(status["segments"][0]["end_tick"],
                         3*3600*TICKS_PER_SECOND)
        self.assertEqual(status["state"],"QUEUED")

    def test_owner_heartbeat_preserves_only_exact_native_lease(self):
        accepted=self.submit()
        segment=self.journal.claim_next("RealOwner",os.getpid())
        self.assertEqual(segment["position"],0)
        with self.assertRaises(PermissionError):
            self.journal.heartbeat("WrongOwner",accepted["job_id"],0)
        receipt=self.journal.heartbeat("RealOwner",accepted["job_id"],0)
        self.assertFalse(receipt["cancel_requested"])
        self.assertTrue(self.journal.status(accepted["job_id"])["updated_at"])
        self.assertEqual(len(self.journal.events(accepted["job_id"])),2)

    def test_reviewed_restoration_requires_host_approval_and_original_sha(self):
        job=self.submit()["job_id"]
        original=self.file1.read_bytes()
        self.file1.write_bytes(b"INVALID")
        with SingletonSupervisor(self.state_root):
            self.assertEqual(ProductionSupervisor(self.journal).run_one()["status"],
                             "REVIEW_REQUIRED")
        self.assertEqual(self.journal.authorize_review_retry(job,lambda _:False)
                         ["status"],"DENIED")
        with self.assertRaises(PermissionError):
            self.journal.authorize_review_retry(job,lambda _:True)
        self.file1.write_bytes(original)
        result=self.journal.authorize_review_retry(job,lambda _:True)
        self.assertEqual(result["status"],"QUEUED")
        self.assertEqual(result["segments_requeued"],1)
        with SingletonSupervisor(self.state_root):
            runner=ProductionSupervisor(self.journal)
            for _ in range(3):
                self.assertEqual(runner.run_one()["status"],"SEGMENT_VERIFIED")
        self.assertEqual(self.journal.status(job)["state"],"VERIFY_COMPLETE")
        self.assertTrue(any(x["event_kind"]=="SOURCE_RETRY_APPROVED"
                            for x in self.journal.events(job)))
        self.assertEqual(self.file1.read_bytes(),original)

    def test_symlinked_media_or_noncontiguous_film_time_rejected(self):
        with self.assertRaises(ValueError):
            self.submit(segments=[
                self.segment(self.file1,0,TICKS_PER_SECOND),
                self.segment(self.file2,2*TICKS_PER_SECOND,3*TICKS_PER_SECOND)])
        link=self.root/"source_symlink"
        try:
            link.symlink_to(self.file1)
        except (OSError,NotImplementedError):
            self.skipTest("Native filesystem disallows symlink creation")
        with self.assertRaises(PermissionError):
            self.submit(segments=[self.segment(link,0,TICKS_PER_SECOND)])


if __name__=="__main__":
    unittest.main()
