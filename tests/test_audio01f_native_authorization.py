"""AUDIO-01F native authorization contract; independent from FFmpeg/Blender.

Tests cover the trusted creator decision, source binding, queue admission,
revoke-before-execution and no-worker-start rejection. Actual Windows
Job Object execution is separately covered by integration tests/CI.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01f_native_host import NativeAudio01FHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


class MuxNativeAuthorization(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.capture=DigitalCapture(Studio(self.root/"studio.sqlite3"))
        self.project=self.capture.studio.create_project("Mux", "Authorization")["id"]
        self.capture.index.register_revision(self.project,"pic","presentation",
              {"format":"test.frozen.picture","frame_count":24},expected_revision=0,
              dependencies=[])
        self.capture.index.register_revision(self.project,"sound","audio",
              {"format":"test.frozen.audio","total_samples_per_channel":48000},
              expected_revision=0,dependencies=[])
        self.ledger=TaskLedger(self.root/"ledger",
            sampler=lambda:ResourceSnapshot(0,16000,12000,0,tuple()))
        self.event=object()
        self.allow=True
        self.approvals=[]
        def policy(event,scope):
            self.approvals.append(scope)
            return self.allow and event is self.event and (
                scope["operation"]=="nvp.native.audio01f.picture_sound_review"
                and scope["final_master"] is False)
        self.host=NativeAudio01FHost(self.capture,self.ledger,self.root/"host",
                                     verify_creator_action=policy,
                                     strict_linux_tree=False)
        self.package=self.root/"package"
        self.conform=self.root/"conform"
        self.movie=self.root/"movie"
        self.audio=self.root/"audio"
        self.chunks=self.root/"chunks"
        for p in (self.package,self.conform,self.movie,self.audio,self.chunks):
            p.mkdir()
        self.source=self.root/"original.wav"
        self.source.write_bytes(b"fixture-only-native-admission")
        self.patches=[
            patch("backend.nvp_audio01f_native_host.verify_edited_technical_mov",
                  return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE",
                                "frames":24}),
            patch("backend.nvp_audio01f_native_host.verify_published_wavs",
                  return_value={"status":"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW"})]
        for x in self.patches:x.start()

    def tearDown(self):
        for x in reversed(self.patches):x.stop()
        self.tmp.cleanup()

    def stage(self,event=None):
        return self.host.stage_and_approve(
            self.project,"pic","sound",self.package,self.conform,self.movie,
            self.audio,{"stems":[]},{"voice":self.source},self.chunks,
            self.root/"review",self.event if event is None else event,
            presentation_id="muxreview",ram_mb=1024)

    def test_reject_unapproved_creator_without_job(self):
        self.allow=False
        with self.assertRaises(PermissionError):
            self.stage()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_audio01f_grants").fetchone()[0],0)

    def test_approved_scope_queued_and_revoked_before_worker(self):
        result=self.stage()
        self.assertEqual(result["state"],"QUEUED")
        job=result["job_id"]
        self.assertEqual(self.ledger.get_task(job)["state"],"QUEUED")
        self.assertTrue(self.approvals)
        self.host.revoke(job)
        with self.assertRaises(PermissionError):
            self.host.run_next()
        self.assertEqual(self.ledger.get_task(job)["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertFalse((self.root/"review").exists())

    def test_plan_mutation_is_rejected_at_native_admission(self):
        job=self.stage()["job_id"]
        (self.root/"host"/job/"native_plan.json").write_text("{}")
        with self.assertRaises(PermissionError):
            self.host.run_next()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertFalse((self.root/"review").exists())

    def test_stop_witness_not_invented_by_restart(self):
        job=self.stage()["job_id"]
        self.assertFalse(self.host._attest_reaped(job))
        restarted=NativeAudio01FHost(self.capture,self.ledger,
            self.root/"host",verify_creator_action=lambda *_:False,
            strict_linux_tree=False)
        self.assertFalse(restarted._attest_reaped(job))
        # This test inspects the durable witness persistence mechanism only.
        # Genuine OS-handle reaping is separately covered by Windows CI.
        self.host._record_reaped(job)
        self.assertTrue(restarted._attest_reaped(job))

    def test_restarted_host_cannot_reuse_ephemeral_creator_approval(self):
        job=self.stage()["job_id"]
        restarted=NativeAudio01FHost(self.capture,self.ledger,self.root/"host",
            verify_creator_action=lambda *_:True,strict_linux_tree=False)
        with self.assertRaises(PermissionError):
            restarted.run_next()
        self.assertEqual(self.ledger.get_task(job)["state"],"QUEUED")


if __name__=="__main__":
    unittest.main()
