"""B9 native EXR full-sequence consent, frame plan and resource refusal.

Uses real frozen FilmIndex capture but an explicitly FAKE indexed .blend to
exercise source/identity guards without pretending native Blender ran.
The separate Linux acceptance fixture exercises real Blender + image pixels.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import sys
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_exr_sequence import NativeEXRSequence,frame_filename
from backend.nvp_exr_publish import publish_exr_sequence
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from tools.nvp_stack02c3b8_real_frozen_take import prepare_capture


def measured():
    return ResourceSnapshot(1,32768,25000,0,())


def low():
    return ResourceSnapshot(1,16384,900,0,())


class FullNativeEXRSequenceContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio,self.capture,self.pid,self.sid,self.take_id,_=prepare_capture(root)
        source=self.capture.reopen(self.pid,self.take_id)
        self.capture_sha=source["record"]["document_sha256"]
        fake=root/"test_only_not_a_real_blend.blend"
        fake.write_bytes(b"BLENDER"+b"\0"*80)
        media=self.capture.index.put_media_file(
            self.pid,fake,"application/octet-stream")
        self.blend_sha=media["sha256"]
        self.preview_id="fixture_preview"
        self.capture.index.register_revision(
            self.pid,self.preview_id,"presentation",
            {"format":"nvp.test.fake_preview_not_rendered.v1"},
            dependencies=[{"object_id":self.take_id,"revision":1,"role":"source_take"}])
        self.snapshot={
            "source_take_id":self.take_id,
            "source_capture_sha256":self.capture_sha,
            "timeline_frames":120,
            "blend_sha256":self.blend_sha,
        }
        self.ledger=TaskLedger(root/"resources",sampler=measured)
        binary=Path(sys.executable).resolve()
        self.worker=BlenderWorkerSupervisor(
            root/"workers",blender_executable=binary,
            blender_sha256=sha_file(binary),blender_version="Blender Test",
            activity_ledger=self.ledger)
        self.event=object()
        self.scopes=[]
        def verify(event,scope):
            self.scopes.append(scope)
            return event is self.event and (scope.get("frame_count")==120 or scope.get("frames")==120)
        self.host=NativeEXRSequence(
            self.capture,self.worker,self.ledger,
            verify_creator_action=verify)
        self.mock=patch("backend.nvp_exr_sequence.verify_presentation",
                        return_value=self.snapshot)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.tmp.cleanup()

    def approve(self,**kw):
        return self.host.create_from_trusted_native_action(
            self.pid,self.take_id,self.preview_id,self.event,**kw)

    def test_full_120_timeline_partitions_into_exact_15_bounded_chunks(self):
        receipt=self.approve()
        seq=self.host._row(receipt["sequence_id"])
        source,_=self.host._verify_source(seq)
        batches=list(self.host._plans(seq,source))
        self.assertEqual(len(batches),15)
        self.assertEqual([f["frame"] for _,_,p in batches
                          for f in p["frames"]],list(range(1,121)))
        self.assertEqual(len(batches[0][2]["frames"]),8)
        self.assertEqual(batches[-1][:2],(113,120))
        self.assertEqual([s["start_frame"] for s in batches[0][2]["shots"]],
                         [1,49])

    def test_creator_must_explicitly_approve_real_float32_native_output(self):
        with self.assertRaises(PermissionError):
            self.host.create_from_trusted_native_action(
                self.pid,self.take_id,self.preview_id,{"clicked":True})
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_exr_sequences").fetchone()[0],0)
        receipt=self.approve(width=160,height=90)
        context=self.scopes[-1]
        self.assertEqual(context["channels"],"RGBA_FLOAT32")
        self.assertEqual(context["view_transform"],"Raw")
        self.assertEqual(context["fps"],24)
        self.assertEqual(context["native_blend_sha256"],self.blend_sha)
        self.assertFalse(receipt["full_sequence_verified"])

    def test_bad_film_format_and_excessive_resource_request_denied(self):
        for kw in ({"width":0},{"height":0},{"chunk_size":9},
                   {"chunk_size":True},{"ram_mb":True},{"ram_mb":65537},
                   {"duration_s":7201}):
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    self.approve(**kw)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_frame_filenames_and_native_script_are_not_arbitrary(self):
        receipt=self.approve()
        staged=self.host.queue_next_chunk(receipt["sequence_id"])
        self.assertEqual(staged["chunk"],[1,8])
        op=self.host._chunk(receipt["sequence_id"],1)["op"]
        self.assertEqual(set(op.outputs),
                         {frame_filename(i) for i in range(1,9)})
        self.assertTrue(all(kind=="exr" for kind in op.outputs.values()))
        self.assertEqual(op.scene,"frozen_take.blend")
        self.assertEqual(set(op.arguments),{"--plan"})
        self.assertEqual(len(self.ledger.snapshot()["tasks"]),1)
        with self.assertRaises(ValueError):
            frame_filename(True)
        with self.assertRaises(ValueError):
            frame_filename(14401)

    def test_resource_guard_queues_exr_without_running_blender(self):
        receipt=self.approve()
        staged=self.host.queue_next_chunk(receipt["sequence_id"])
        self.ledger.sampler=low
        with patch.object(self.worker,"_run_worker",
                          side_effect=AssertionError("Blender must not start")) as launch:
            denied=self.host.run_queued_chunk()
            launch.assert_not_called()
        self.assertEqual(denied["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertFalse(any((self.worker.root/staged["job_id"]).glob("frame_*.exr")))

    def test_source_plan_tampering_blocks_policy_before_worker_admission(self):
        receipt=self.approve()
        staged=self.host.queue_next_chunk(receipt["sequence_id"])
        path=self.worker.root/staged["job_id"]/"exr_chunk_plan.json"
        path.write_bytes(path.read_bytes()+b"CORRUPT")
        with patch.object(self.worker,"_run_worker") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_queued_chunk()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_revocation_requires_real_native_action_and_cancels_only_queued(self):
        receipt=self.approve()
        staged=self.host.queue_next_chunk(receipt["sequence_id"])
        with self.assertRaises(PermissionError):
            self.host.revoke_from_trusted_native_action(
                receipt["sequence_id"],{"browser_clicked":True})
        self.assertEqual(self.ledger.get_task(staged["task_id"])["state"],"QUEUED")
        revoked=self.host.revoke_from_trusted_native_action(
            receipt["sequence_id"],self.event)
        self.assertTrue(revoked["revoked"])
        self.assertEqual(revoked["cancelled_queued_task_ids"],[staged["task_id"]])
        self.assertFalse(revoked["active_worker_cleanup_claimed"])
        self.assertEqual(self.ledger.get_task(staged["task_id"])["state"],"CANCELLED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        with self.assertRaises(PermissionError):
            self.host.queue_next_chunk(receipt["sequence_id"])

    def test_crash_before_enqueue_recovers_exact_staged_original_source(self):
        receipt=self.approve()
        with (patch.object(self.host.dispatcher,"enqueue",
                           side_effect=RuntimeError("interrupted enqueue")),
              patch.object(self.ledger,"get_task",
                           side_effect=RuntimeError("simulated crash inside cleanup"))):
            with self.assertRaisesRegex(RuntimeError,"simulated crash"):
                self.host.queue_next_chunk(receipt["sequence_id"])
        staged=self.host._chunk(receipt["sequence_id"],1)
        self.assertIsNotNone(staged)
        self.assertIsNone(self.ledger.get_task(self.worker._activity_id(staged["job_id"])))
        recovered=self.host.queue_next_chunk(receipt["sequence_id"])
        self.assertTrue(recovered["recovered_staged_source"])
        self.assertEqual(recovered["job_id"],staged["job_id"])
        self.assertEqual(recovered["state"],"QUEUED")
        self.assertEqual(self.ledger.get_task(recovered["task_id"])["state"],"QUEUED")

    def test_publishing_before_all_120_frames_does_not_claim_video_or_exr(self):
        receipt=self.approve()
        self.host.queue_next_chunk(receipt["sequence_id"])
        with self.assertRaises(RuntimeError):
            publish_exr_sequence(self.host,receipt["sequence_id"])
        self.assertEqual(self.capture.index.list_objects(self.pid,kind="presentation"),
                         [{"object_id":self.preview_id,"kind":"presentation","head_revision":1}])


if __name__=="__main__":
    unittest.main()
