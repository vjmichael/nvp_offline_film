"""Crash-injected native audio admission gap: read-only quarantine audit."""
from pathlib import Path
import tempfile
import unittest
from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_audio01e3_native_journal import AudioJobJournal


class AdmissionGapTests(unittest.TestCase):
    def test_grant_without_task_does_not_become_queued_or_recoverable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def sample():
                return ResourceSnapshot(0,16000,14000,0.0,tuple())
            ledger=TaskLedger(root/"ledger",sampler=sample)
            host=NativeAudioHost(ledger,root/"native",
                    verify_creator_action=lambda *_:True,strict_linux_tree=False)
            # Inject exactly the state after grant/lease commit but before
            # ApprovedTaskBindings.enqueue. This models abrupt host exit.
            job="audiojobcrash1"
            with ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO audio_native_grants(
                    job_id,approval_id,creator_event,scope_json,spec_sha,plan_sha,
                    python_sha,worker_sha,expires_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (job,"audioapproval_crash1","approved","{}","0"*64,"0"*64,
                     "0"*64,"0"*64,9999999999))
                db.execute("""INSERT INTO audio_native_staging_leases
                    (directory,job_id,predecessor) VALUES(?,?,NULL)""",
                    (str(root/"work"),job))
                db.commit()
            # Minimal authentic journal record; do not invent output.
            with host.journal._db() as db:
                db.execute("BEGIN IMMEDIATE")
                spec={"job_id":job,"directory":str(root/"work")}
                from backend.nvp_audio01e3_native_journal import canonical,digest
                db.execute("""INSERT INTO audio_native_jobs(
                    job_id,spec_json,spec_sha,state,generation,last_next_sample
                ) VALUES(?,?,?,?,?,?)""",
                    (job,canonical(spec).decode(),digest(spec),"approved",0,0))
            restarted=NativeAudioHost(ledger,root/"native",
                    verify_creator_action=lambda *_:True,strict_linux_tree=False)
            quarantined=restarted.audit_incomplete_admissions()
            self.assertEqual(len(quarantined),1)
            self.assertEqual(quarantined[0]["reason"],"ADMISSION_NOT_ATOMIC_WITH_GRANT")
            self.assertEqual(quarantined[0]["status"],"QUARANTINED_NEEDS_NATIVE_AUDIT")
            self.assertIsNone(ledger.get_task(job))
            with self.assertRaises(RuntimeError):
                restarted.recover_stopped(job)


if __name__=="__main__":
    unittest.main()
