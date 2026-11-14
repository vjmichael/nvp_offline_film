"""B11 native FilmIndex FLOAT32 source/ACES2 review trust, cut timing and OS safety.

Synthetic B9 frame rows are used only for these native refusal and lineage
tests. Genuine native Blender 120-frame HDR EXR -> official ACES2 16bit PNG
is covered separately in the Linux acceptance fixture.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_b11_editorial import (frozen_review_source,render_aces2_sdr_review,
    normalize_near_opaque_preview_alpha,NEAR_OPAQUE_ALPHA_POLICY)
from backend.nvp_b11_native_review import NativeB11ReviewHost,PLAN
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from tools.nvp_stack02c3b8_real_frozen_take import prepare_capture


def measured():
    return ResourceSnapshot(1,32768,25000,0,())


def insufficient():
    return ResourceSnapshot(1,16384,1000,0,())


class NearOpaqueAASourceContracts(unittest.TestCase):
    def test_real_blender_workbench_near_opaque_alpha_normalized_only_in_review(self):
        import numpy as np
        rgba=np.array([[[.16,.17,.18,.99853515625],
                        [.05,.05,.05,.99853515625]]],dtype=np.float32)
        original=rgba.copy()
        derived,proof=normalize_near_opaque_preview_alpha(rgba)
        self.assertEqual(proof["format"],NEAR_OPAQUE_ALPHA_POLICY)
        self.assertEqual(proof["source_alpha_min"],.99853515625)
        self.assertEqual(proof["normalized_preview_pixels"],2)
        self.assertFalse(proof["actual_transparency_composited"])
        self.assertFalse(proof["source_float32_exr_alpha_modified"])
        np.testing.assert_array_equal(rgba,original)
        np.testing.assert_array_equal(derived[...,:3],original[...,:3])
        self.assertTrue((derived[...,3]==1.0).all())

    def test_real_transparency_wrong_alpha_or_nonfinite_pixels_still_refused(self):
        import numpy as np
        for a in (0.0,.25,.96,1.01,float("nan")):
            with self.subTest(alpha=a):
                frame=np.array([[[.2,.3,.4,a]]],dtype=np.float32)
                with self.assertRaises(RuntimeError):
                    normalize_near_opaque_preview_alpha(frame)


class NativeB11SDREditorialContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio,self.capture,self.pid,self.sid,self.take_id,_=prepare_capture(root)
        original=self.capture.reopen(self.pid,self.take_id)
        self.take_sha=original["record"]["document_sha256"]
        self.exr_id="unit_float_source"
        indexed=self.capture.index.register_revision(
            self.pid,self.exr_id,"presentation",
            {"format":"nvp.presentation.scene_linear_float32_exr_sequence.v1",
             "source_take_id":self.take_id,
             "source_take_sha256":self.take_sha,
             "fps":24,"frame_count":120,
             "frames":[{"frame":k,"sha256":format(k,"064x")}
                       for k in range(1,121)]},
            dependencies=[{"object_id":self.take_id,"revision":1,"role":"source_take"}])
        self.exr_sha=indexed["document_sha256"]
        fake={"frames":120,"fps":24,"width":160,"height":90,
              "source_take_id":self.take_id,"source_take_sha256":self.take_sha}
        self.mock=patch("backend.nvp_b11_editorial.verify_indexed_exr_sequence",
                        return_value=fake)
        self.mock.start()
        self.ledger=TaskLedger(root/"resource",sampler=measured)
        self.event=object()
        self.scopes=[]
        def verifier(event,scope):
            self.scopes.append(scope)
            return event is self.event and scope.get("project_id")==self.pid
        self.host=NativeB11ReviewHost(
            self.capture,self.ledger,root/"native",verify_creator_action=verifier)

    def tearDown(self):
        self.mock.stop()
        self.tmp.cleanup()

    def approve(self):
        return self.host.stage_and_approve(
            self.pid,self.exr_id,self.event,ram_mb=2048,duration_s=1200)

    def test_original_two_camera_cuts_preserved_from_frozen_take_not_mutable_state(self):
        src=frozen_review_source(self.capture,self.pid,self.exr_id)
        self.assertEqual(src["fps"],24)
        self.assertEqual(src["frame_count"],120)
        self.assertEqual(len(src["cutlist"]),2)
        self.assertEqual(src["cutlist"][0]["start_frame"],1)
        self.assertEqual(src["cutlist"][0]["stop_frame_exclusive"],49)
        self.assertEqual(src["cutlist"][1]["stop_frame_exclusive"],121)
        self.assertEqual(src["source_take_sha256"],self.take_sha)

    def test_no_untrusted_creator_or_undeclared_input_color_authority(self):
        with self.assertRaises(PermissionError):
            self.host.stage_and_approve(self.pid,self.exr_id,{"clicked":True})
        with self.assertRaises(PermissionError):
            render_aces2_sdr_review(self.capture,self.pid,self.exr_id,
                                    "untrusted_review",self.host.root)
        self.assertEqual(self.ledger.snapshot()["tasks"],[])

    def test_native_approval_binds_exact_take_frames_cuts_and_ocio_processor(self):
        staged=self.approve()
        self.assertEqual(staged["state"],"QUEUED")
        self.assertFalse(staged["workers_started"])
        self.assertEqual(staged["frames"],120)
        self.assertEqual(self.scopes[-1]["source_take_id"],self.take_id)
        self.assertEqual(self.scopes[-1]["frames"],120)
        self.assertEqual(self.scopes[-1]["fps"],24)
        self.assertEqual(self.scopes[-1]["source_presentation_sha256"],self.exr_sha)
        self.assertEqual(self.scopes[-1]["output"],
            "color_managed_ACES2_sRGB_16bit_RGB_PNG_sequence")
        self.assertEqual(self.scopes[-1]["alpha_policy"],NEAR_OPAQUE_ALPHA_POLICY)
        self.assertFalse(self.scopes[-1]["transparency_compositing_approved"])

    def test_low_ram_keeps_queued_review_and_does_not_launch_worker(self):
        self.approve()
        self.ledger.sampler=insufficient
        with patch("backend.nvp_b11_native_review.launch_contained",
                   side_effect=AssertionError("Must not start review")) as launch:
            denied=self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(denied["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_tampered_native_plan_refuses_before_admission(self):
        staged=self.approve()
        path=self.host.root/staged["job_id"]/PLAN
        path.write_bytes(path.read_bytes()+b"corrupt")
        with patch("backend.nvp_b11_native_review.launch_contained") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_expiry_refuses_native_work_without_launch(self):
        staged=self.approve()
        with self.ledger._db() as db:
            db.execute("""UPDATE native_b11_review_grants
                   SET expires_at=0 WHERE job_id=?""",(staged["job_id"],))
        with patch("backend.nvp_b11_native_review.launch_contained") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_native_revocation_cancels_only_unadmitted_queue(self):
        staged=self.approve()
        with self.assertRaises(PermissionError):
            self.host.revoke_from_trusted_native_action(staged["job_id"],{"web":True})
        self.assertEqual(self.ledger.get_task(staged["job_id"])["state"],"QUEUED")
        cancelled=self.host.revoke_from_trusted_native_action(
            staged["job_id"],self.event)
        self.assertTrue(cancelled["revoked"])
        self.assertTrue(cancelled["cancelled_queued"])
        self.assertFalse(cancelled["active_os_cleanup_claimed"])
        self.assertEqual(self.ledger.get_task(staged["job_id"])["state"],"CANCELLED")

    def test_native_launcher_ambiguity_retains_os_owned_ram_reservation(self):
        staged=self.approve()
        with patch("backend.nvp_b11_native_review.launch_contained",
                   side_effect=RuntimeError("launcher lost kernel handle")):
            with self.assertRaisesRegex(RuntimeError,"kernel handle"):
                self.host.run_next()
        task=self.ledger.get_task(staged["job_id"])
        self.assertEqual(task["state"],"ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],2048)

    def test_reopen_never_treats_queued_work_as_completed(self):
        staged=self.approve()
        again=NativeB11ReviewHost(
            self.capture,self.ledger,self.host.root,
            verify_creator_action=lambda *_:False)
        with self.assertRaises(RuntimeError):
            again.verify_completed(staged["job_id"])
        self.assertEqual(self.capture.index.list_objects(self.pid,kind="presentation")[-1]["object_id"],self.exr_id)


if __name__=="__main__":
    unittest.main()
