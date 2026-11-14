"""Genuine Blender/Cycles multi-shot original source: actor+scene UV/PBR+PCM.

Only PUBLIC independently authored synthetic film data on Windows CI.
Actual Win32 Job containment is exercised; the kernel private namespace
checks here are explicitly mocked in THIS TEST ONLY, not production code.
Real private SCM+creator signature remains a separate installed gate.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_p1f_cycles_picture_sound import P1FOriginalPictureSound
from backend.nvp_p1f_multishot_reel import P1FDurableShotReels
from backend.nvp_p1f_picture_audio_delivery import P1FVerifiedSegmentDelivery
from backend.nvp_p1f_p2_verified_coverage import P1FVerifiedFilmCoverage
from backend.nvp_p1f_sustained_reel_queue import P1FReviewedReelQueue
from test_nvp_p1f_shot_material_binding_native import (
    OriginalShotReviewedMaterialTests,original_combined_shot)


@unittest.skipUnless(os.name=="nt" and
                     os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")=="1" and
                     os.environ.get("NVP_TEST_BLENDER"),
                     "Actual Windows Blender Job synthetic source-only acceptance")
class NVPRealReviewedMaterialMultiShot(unittest.TestCase):
    def test_two_original_actor_uv_pbr_frames_and_stereo_pcm_reopen(self):
        fixture=OriginalShotReviewedMaterialTests(
            "test_real_actor_timeline_original_take_and_uv_material_binding")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original_combined_shot(fixture)
        fixture.publish()
        binary=Path(os.environ["NVP_TEST_BLENDER"]).resolve()
        version=subprocess.run(
            [str(binary),"-b","--version"],check=True,
            capture_output=True,text=True,timeout=30).stdout.splitlines()[0]
        self.assertTrue(version.startswith("Blender "))
        with tempfile.TemporaryDirectory(prefix="nvp-p1f-authored-multishot-") as tmp:
            root=Path(tmp)/"jobs"
            supervisor=BlenderWorkerSupervisor(
                root,blender_executable=binary,
                blender_sha256=sha_file(binary),
                blender_version=version)
            renderer=P1FOriginalPictureSound(
                fixture.fixture.index,supervisor,
                approve_render=lambda event,scope:
                    event=="one_frame_signed_test_only" and
                    scope["operation"]=="nvp.p1f.render_original_cycles_frame.v1" and
                    scope["reviewed_look_id"]=="original_scene_look" and
                    len(scope["reviewed_look_document_sha256"])==64,
                verify_isolated_worker=lambda scope:
                    scope["require_no_network"] is True and
                    scope["require_private_filesystem_isolation"] is True)
            journal=P1FDurableShotReels(
                fixture.fixture.index,renderer,
                approve_batch=lambda event,scope:
                    event=="finite_public_batch_review" and
                    scope["operation"]=="nvp.p1f.admit_finite_source_batch.v1",
                verify_batch_live=lambda scope:
                    scope["operation"]=="nvp.p1f.verify_finite_source_batch_live.v1")
            test_only_boundaries=(
                patch("backend.nvp_worker_private_sandbox.prove_private_kernel_boundary",
                      return_value={"public_fixture_only":True}),
                patch("backend.nvp_worker_private_sandbox.private_os_preflight",
                      return_value={"public_fixture_only":True}),
                patch("backend.nvp_worker_private_sandbox.sandbox_command",
                      side_effect=lambda cmd,jobdir:{"command":cmd}),
            )
            for scoped in test_only_boundaries:
                scoped.start()
                self.addCleanup(scoped.stop)
            admitted=journal.create_batch(
                fixture.fixture.pid,"combined_set_reel_plan","reviewed_pbr_batch",
                reel_index=0,first_frame_offset=0,frame_count=2,
                creator_event="finite_public_batch_review")
            self.assertEqual(admitted["frames"],2)
            for offset in range(2):
                result=journal.run_next(
                    "reviewed_pbr_batch",
                    creator_event="one_frame_signed_test_only",
                    reviewed_look_id="original_scene_look",samples=8)
                self.assertEqual(result["status"],"FRAME_ACCEPTED")
            checked=journal.verify("reviewed_pbr_batch")
            self.assertTrue(checked["all_frames_verified"])
            doc,state=journal._manifest("reviewed_pbr_batch")
            for shot in doc["source_frames"]:
                receipt=renderer.verify_delivered(
                    fixture.fixture.pid,"combined_set_reel_plan",shot["job_id"])
                material=receipt["original_picture"]["reviewed_material"]
                self.assertEqual(material["look_id"],"original_scene_look")
                self.assertEqual(set(material["texture_sha256"]),{
                    "baseColor","roughness","metallic","normal"})
                self.assertEqual(material["rendered_uv_meshes"],["Wall"])
                self.assertTrue(receipt["original_derived_audio"]["source_owned"])
            delivery=P1FVerifiedSegmentDelivery(journal)
            exported=delivery.deliver("reviewed_pbr_batch")
            self.assertEqual(exported["status"],"SOURCE_SEGMENT_DELIVERED")
            reopened=delivery.verify_delivered("reviewed_pbr_batch")
            self.assertEqual(reopened["frame_count"],2)
            self.assertEqual(reopened["audio_sample_count_per_channel"],4000)
            restarted=P1FDurableShotReels(
                fixture.fixture.index,renderer,
                approve_batch=lambda *_:False,
                verify_batch_live=lambda *_:False)
            self.assertTrue(restarted.verify("reviewed_pbr_batch")["all_frames_verified"])
            coverage=P1FVerifiedFilmCoverage(delivery)
            coverage.register(
                fixture.fixture.pid,"combined_set_reel_plan","reviewed_pbr_batch")
            observed=coverage.verify_coverage(
                fixture.fixture.pid,"combined_set_reel_plan")
            self.assertEqual(observed["verified_frames"],2)
            self.assertFalse(observed["all_source_frames_verified"])
            next_=P1FReviewedReelQueue(restarted).review_next(
                fixture.fixture.pid,"combined_set_reel_plan",max_frames=2)
            self.assertEqual(next_["first_frame_offset"],2)
            self.assertEqual(next_["frame_count"],2)
            self.assertFalse(next_["worker_authorized"])
            with self.assertRaises(RuntimeError):
                restarted.run_next(
                    "reviewed_pbr_batch",creator_event="replay",
                    reviewed_look_id="original_scene_look")


if __name__=="__main__":
    unittest.main()
