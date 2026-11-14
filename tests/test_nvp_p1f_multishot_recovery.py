"""P1-F bounded batch journal: one-use source approval, cancellation and restart.

These tests exercise the SQLite FULL-sync host journal with a stubbed already-
verified renderer receipt. The separate real Blender/Cycles fixture verifies
the actual worker, PNG/WAV and native Job execution.
"""
import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_p1f_cycles_picture_sound import P1FOriginalPictureSound
from backend.nvp_p1f_multishot_reel import P1FDurableShotReels
from test_nvp_p1f_imported_actor_native import RealImportedActorTests


class DurableOriginalShotTests(unittest.TestCase):
    def setUp(self):
        self.fixture=RealImportedActorTests(
            "test_composed_facial_actor_in_real_source_take_shot")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.test_composed_facial_actor_in_real_source_take_shot()
        tmp=TemporaryDirectory(prefix="nvp-p1f-multishot-journal-")
        self.addCleanup(tmp.cleanup)
        exe=Path(sys.executable).resolve()
        self.supervisor=BlenderWorkerSupervisor(
            Path(tmp.name)/"worker",blender_executable=exe,
            blender_sha256=sha_file(exe),
            blender_version="Blender No Native Worker Test")
        self.renderer=P1FOriginalPictureSound(
            self.fixture.index,self.supervisor,
            approve_render=lambda *_:False,
            verify_isolated_worker=lambda *_:False)
        self.journal=P1FDurableShotReels(
            self.fixture.index,self.renderer,
            approve_batch=lambda event,scope:
            event=="approved_batch" and
            scope["operation"]=="nvp.p1f.admit_finite_source_batch.v1" and
            scope["frame_count"]==2,
            verify_batch_live=lambda scope:
                scope["operation"]=="nvp.p1f.verify_finite_source_batch_live.v1"
                and scope["batch_id"]=="first_batch")

    def create(self,batch="first_batch"):
        return self.journal.create_batch(
            self.fixture.pid,"rigged_reel_plan",batch,
            reel_index=0,first_frame_offset=0,frame_count=2,
            creator_event="approved_batch")

    def test_two_frame_durable_acceptance_and_fresh_restart(self):
        self.create()
        saved={}
        def render(pid,plan,reel,offset,job_id,**kwargs):
            r={"format":"nvp.p1f.independent_picture_audio_receipt.v1",
               "passed":True,"job_id":job_id,
               "plan_document_sha256":
                   self.journal.reels.read(pid,plan)["document_sha256"],
               "entire_film_rendered":False,
               "original_picture":{"source_frame":offset,"sha256":"a"*64},
               "original_derived_audio":{"sample_count":2000,
                                         "pcm_sha256":"b"*64}}
            saved[job_id]=r
            return r
        with (patch.object(self.renderer,"render_frame",side_effect=render),
              patch.object(self.renderer,"verify_delivered",
                           side_effect=lambda pid,plan,job: saved[job])):
            one=self.journal.run_next("first_batch",creator_event="frame_a")
            two=self.journal.run_next("first_batch",creator_event="frame_b")
            self.assertEqual(one["status"],"FRAME_ACCEPTED")
            self.assertEqual(two["status"],"FRAME_ACCEPTED")
            self.assertEqual(two["remaining"],0)
            self.assertTrue(self.journal.verify("first_batch")["all_frames_verified"])
            fresh=P1FDurableShotReels(
                self.fixture.index,self.renderer,approve_batch=lambda *_:False,
                verify_batch_live=lambda scope: scope["batch_id"]=="first_batch")
            self.assertEqual(fresh.verify("first_batch")["frames_accepted"],2)
            with self.assertRaises(RuntimeError):
                fresh.run_next("first_batch",creator_event="replay")
            # A previously approved batch ID may not be reused even when a
            # fresh trusted caller again permits the exact same scope.
            fresh.approve_batch=lambda event,scope: event=="approved_batch"
            with self.assertRaisesRegex(RuntimeError,"already registered"):
                fresh.create_batch(
                    self.fixture.pid,"rigged_reel_plan","first_batch",
                    reel_index=0,first_frame_offset=0,frame_count=2,
                    creator_event="approved_batch")

    def test_cancel_persistently_rejects_pending_execution(self):
        self.create()
        stopped=self.journal.cancel("first_batch")
        self.assertEqual(stopped["status"],"CANCELLED_OR_UNTRUSTED")
        with self.assertRaises(RuntimeError):
            self.journal.run_next("first_batch",creator_event="not_admitted")
        self.assertFalse(self.journal.verify("first_batch")["all_frames_verified"])

    def test_native_journal_crash_state_never_becomes_complete(self):
        self.create()
        with self.journal._connect() as db:
            db.execute("""UPDATE source_frames SET state='RUNNING'
                 WHERE batch_id='first_batch' AND frame_index=0""")
        report=self.journal.reconcile_restart("first_batch")
        self.assertEqual(report["interrupted"],1)
        self.assertFalse(report["safe_to_auto_replay"])
        self.assertFalse(report["kernel_cleanup_verified"])
        with self.assertRaises(RuntimeError):
            self.journal.run_next("first_batch",creator_event="replay")
        after=self.journal.verify("first_batch")
        self.assertEqual(after["frames_accepted"],0)
        self.assertEqual(after["status"],"BLOCKED")

    def test_declined_batch_finite_range_and_original_guard(self):
        with self.assertRaises(PermissionError):
            self.journal.create_batch(
                self.fixture.pid,"rigged_reel_plan","declined",
                reel_index=0,first_frame_offset=0,frame_count=2,
                creator_event="refused")
        with self.assertRaises(ValueError):
            self.journal.create_batch(
                self.fixture.pid,"rigged_reel_plan","out_of_bounds",
                reel_index=0,first_frame_offset=23,frame_count=2,
                creator_event="approved_batch")
        with self.journal._connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM source_batches").fetchone()[0],0)


    def test_revoke_batch_before_dispatch_and_hold_original_sources(self):
        self.create()
        with patch.object(self.journal,"verify_batch_live",return_value=False):
            with self.assertRaises(PermissionError):
                self.journal.run_next("first_batch",creator_event="revoked")
        self.assertEqual(self.journal.verify("first_batch")["frames_accepted"],0)
        with self.journal._connect() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM source_frames
                 WHERE batch_id='first_batch' AND state='RUNNING'"""
            ).fetchone()[0],0)

    def test_distinct_batch_ids_cannot_double_dispatch_same_original_frames(self):
        self.create()
        # A different one-use ID is not permission to dispatch a second
        # native Blender Job against already-queued source-frame instants.
        with self.assertRaisesRegex(RuntimeError,"overlapping"):
            self.journal.create_batch(
                self.fixture.pid,"rigged_reel_plan","overlap_attack",
                reel_index=0,first_frame_offset=1,frame_count=2,
                creator_event="approved_batch")
        # Independent non-overlapping source interval remains available.
        second=self.journal.create_batch(
            self.fixture.pid,"rigged_reel_plan","next_original_segment",
            reel_index=0,first_frame_offset=2,frame_count=2,
            creator_event="approved_batch")
        self.assertEqual(second["frames"],2)
        with self.journal._connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM source_batches").fetchone()[0],2)

    def test_already_accepted_frame_cannot_be_dispatched_in_replacement_batch(self):
        self.create()
        # An interrupted batch may contain one genuine earlier accepted
        # frame. Neither a new ID nor a newer creator event may replay it.
        with self.journal._connect() as db:
            db.execute("UPDATE source_frames SET state='ACCEPTED' "
                       "WHERE batch_id='first_batch' AND frame_index=0")
            db.execute("UPDATE source_frames SET state='FAILED' "
                       "WHERE batch_id='first_batch' AND frame_index=1")
            db.execute("UPDATE source_batches SET state='BLOCKED' "
                       "WHERE batch_id='first_batch'")
        with self.assertRaisesRegex(RuntimeError,"overlapping"):
            self.journal.create_batch(
                self.fixture.pid,"rigged_reel_plan","untrusted_retry",
                reel_index=0,first_frame_offset=0,frame_count=2,
                creator_event="approved_batch")

    def test_sustained_queue_reviews_next_original_window_without_dispatch(self):
        from backend.nvp_p1f_sustained_reel_queue import P1FReviewedReelQueue
        queue=P1FReviewedReelQueue(self.journal)
        offered=queue.review_next(
            self.fixture.pid,"rigged_reel_plan",max_frames=2)
        self.assertEqual(offered["status"],"REVIEW_REQUIRED_NOT_AUTHORIZED")
        self.assertEqual(offered["reel_index"],0)
        self.assertEqual(offered["first_frame_offset"],0)
        self.assertEqual(offered["frame_count"],2)
        self.assertFalse(offered["worker_authorized"])
        self.assertFalse(offered["film_master_created"])
        with self.assertRaisesRegex(RuntimeError,"fresh human review"):
            queue.reserve_next(
                self.fixture.pid,"rigged_reel_plan","unreviewed_window",
                expected_review_sha256="0"*64,
                creator_event="approved_batch",max_frames=2)
        with self.assertRaises(PermissionError):
            queue.reserve_next(
                self.fixture.pid,"rigged_reel_plan","declined_window",
                expected_review_sha256=offered["review_sha256"],
                creator_event="refused",max_frames=2)
        granted=queue.reserve_next(
            self.fixture.pid,"rigged_reel_plan","original_next_batch",
            expected_review_sha256=offered["review_sha256"],
            creator_event="approved_batch",max_frames=2)
        self.assertEqual(granted["status"],"BOUNDED_SOURCE_BATCH_PLANNED_ONLY")
        self.assertFalse(granted["ready_to_auto_render"])
        with self.assertRaisesRegex(RuntimeError,"overlapping"):
            queue.reserve_next(
                self.fixture.pid,"rigged_reel_plan","racing_next_batch",
                expected_review_sha256=offered["review_sha256"],
                creator_event="approved_batch",max_frames=2)

    def test_picture_audio_prefix_refuses_planned_only_sources(self):
        from backend.nvp_p1f_picture_audio_prefix import P1FVerifiedPictureAudioPrefix
        exporter=P1FVerifiedPictureAudioPrefix(self.journal)
        with self.assertRaisesRegex(RuntimeError,"No independently verified"):
            exporter.review(self.fixture.pid,"rigged_reel_plan")
        self.create()
        with self.assertRaisesRegex(RuntimeError,"No independently verified"):
            exporter.review(self.fixture.pid,"rigged_reel_plan")
        self.assertFalse((self.supervisor.root/"p1f_picture_audio_prefixes").exists())

    def test_unverified_private_worker_is_refused_before_staging_any_bytes(self):
        from backend.nvp_p1f_cycles_picture_sound import P1FOriginalPictureSound
        trusted=P1FOriginalPictureSound(
            self.fixture.index,self.supervisor,
            approve_render=lambda *_:True,
            verify_isolated_worker=lambda *_:False)
        with self.assertRaises(PermissionError):
            trusted.render_frame(
                self.fixture.pid,"rigged_reel_plan",0,0,"private_denied",
                creator_event="creator_approved")
        self.assertFalse((self.supervisor.root/"private_denied").exists())


if __name__=="__main__":
    unittest.main()
