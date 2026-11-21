"""Native trusted host contract. Synthetic fixture, not installed service."""
import unittest
from unittest.mock import patch
import test_nvp_production_delivery as delivery_fixture
from backend.nvp_production_host import NativeProductionHost
from backend.nvp_production_journal import AnotherSupervisorRunning


class NativeProductionHostTests(unittest.TestCase):
    def setUp(self):
        self.base=delivery_fixture.DurableCinemaDeliveryTests("test_project_approval_is_separate_from_picture_approval")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.pid=self.base.f.f.pid
        self.index=self.base.f.f.index
        self.root=self.base.journal.root
        self.events=[]
        def verify(event,scope):
            self.events.append((event,scope))
            return event=="confirmed" and scope["project_id"]==self.pid
        def resolve(pid):
            if pid!=self.pid:
                raise PermissionError("Wrong project")
            return self.index
        def codecs(pid,check):
            f=self.base.f
            f.authority.cancel=check
            return f.codec,f.wrap,f.info
        self.host=NativeProductionHost(self.root,resolve_project=resolve,codec_factory=codecs,
                                      verify_creator_action=verify)
        p=patch("backend.nvp_production_host.inspect_original_process_journals",return_value={"mock_fixture":True})
        p.start();self.addCleanup(p.stop)

    def test_host_reconnect_denies_other_project_and_does_not_cancel(self):
        job=self.base.finish_picture()
        denied=self.host.attach_delivery(self.pid,job,creator_event="no",sound_candidate=self.base.wav,
            output_root=self.base.output,title="Host film")
        self.assertEqual(denied["status"],"DENIED")
        accepted=self.host.attach_delivery(self.pid,job,creator_event="confirmed",sound_candidate=self.base.wav,
            output_root=self.base.output,title="Host film")
        self.assertEqual(accepted["status"],"SOUND_PENDING")
        with self.assertRaises(PermissionError):
            self.host.reconnect_read_only(self.pid,creator_event="no")
        with self.assertRaises(PermissionError):
            self.host.reconnect_read_only("a"*32,creator_event="confirmed")
        view=self.host.reconnect_read_only(self.pid,creator_event="confirmed")
        self.assertTrue(view["read_only"])
        self.assertNotIn(str(self.root),str(view))
        self.assertFalse(view["can_cancel_job"])
        self.assertFalse(self.host.journal.status(job)["cancel_requested"])
        self.assertEqual(self.host.request_delivery_cancel(self.pid,job,creator_event="no")["status"],"DENIED")
        self.assertEqual(self.host.request_delivery_cancel(self.pid,job,creator_event="confirmed")["status"],"CANCEL_REQUESTED")
        with self.host.service_session():
            self.assertEqual(self.host.journal.status(job)["state"],"CANCELLED")

    def test_review_reconnect_uses_existing_protected_journal_without_constructor_or_lease(self):
        from backend.nvp_wo4_feature_journal import FeatureJournal
        import sqlite3
        with self.host.service_session():
            with patch.object(FeatureJournal,"__init__",side_effect=AssertionError("must not initialize")):
                view=NativeProductionHost.open_review_journal(self.root,self.index)
            self.assertIsInstance(view,FeatureJournal)
            with view._read() as db:
                self.assertIsNotNone(db.execute("SELECT count(*) FROM production_features").fetchone())
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute("DELETE FROM production_features")
            with self.assertRaises(PermissionError):
                view._tx()
            with self.assertRaises(AnotherSupervisorRunning):
                with self.host.service_session():
                    self.fail("Review must not change service ownership")
        self.assertFalse((self.root/"review-copy.sqlite3").exists())

    def test_service_session_owns_exclusive_recovery_and_run_lease(self):
        with self.host.service_session() as runner:
            self.assertEqual(runner.run_one()["status"],"IDLE")
            with self.assertRaises(AnotherSupervisorRunning):
                with self.host.service_session():
                    self.fail("Second host entered active service session")
        with self.host.service_session() as runner:
            self.assertEqual(runner.run_one()["status"],"IDLE")


if __name__=="__main__":
    unittest.main()
