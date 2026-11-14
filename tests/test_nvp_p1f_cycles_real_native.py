"""One genuine Blender/Cycles + Win32 Job public-fixture acceptance.

Requires NVP_PUBLIC_SYNTHETIC_CI=1, real native Blender binary and Windows.
The fixture is *public procedural USD* for verifying the production handoff;
it is not a real character, private creator film, photorealistic render,
signed distribution, AppContainer or a sustained-production acceptance.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor, sha_file
from backend.nvp_p1f_cycles_picture_sound import P1FOriginalPictureSound
from test_nvp_p1f_imported_actor_native import RealImportedActorTests


@unittest.skipUnless(
    os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")=="1" and
    os.name=="nt" and os.environ.get("NVP_TEST_BLENDER"),
    "Runs only on explicitly provisioned real Windows Blender fixture runner")
class P1FRealCyclesJobTests(unittest.TestCase):
    def test_actual_cycles_actor_png_plus_original_pcm_and_restart(self):
        binary=Path(os.environ["NVP_TEST_BLENDER"]).resolve()
        self.assertTrue(binary.is_file(), "Actual installed Blender binary required")
        out=subprocess.run(
            [str(binary),"-b","--version"],
            check=True,capture_output=True,text=True,timeout=25)
        version=out.stdout.splitlines()[0]
        self.assertTrue(version.startswith("Blender "))
        fixture=RealImportedActorTests(
            "test_composed_facial_actor_in_real_source_take_shot")
        fixture.setUp()
        try:
            # Builds and independently reopens actual USD mesh, skeleton,
            # animated facial controls, approved synthetic Take and PCM.
            fixture.test_composed_facial_actor_in_real_source_take_shot()
            with tempfile.TemporaryDirectory(prefix="nvp-p1f-win-job-") as tmp:
                supervisor=BlenderWorkerSupervisor(
                    Path(tmp)/"worker",
                    blender_executable=binary,
                    blender_sha256=sha_file(binary),
                    blender_version=version)
                # This test-only callback is deliberately NOT production
                # sandbox evidence: the only data provided is freshly
                # generated public synthetic USD and a sine-free PCM fixture.
                def synthetic_only_boundary(scope):
                    return (
                        os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")=="1" and
                        scope["project_id"]==fixture.pid and
                        scope["require_no_network"] is True and
                        scope["require_private_filesystem_isolation"] is True)
                refuse=P1FOriginalPictureSound(
                    fixture.index,supervisor,
                    approve_render=lambda *_:False,
                    verify_isolated_worker=synthetic_only_boundary,
                    public_fixture_mode=True)
                with self.assertRaises(PermissionError):
                    refuse.render_frame(
                        fixture.pid,"rigged_reel_plan",0,12,"refused_frame",
                        creator_event="declined")
                self.assertFalse((supervisor.root/"refused_frame").exists())
                worker=P1FOriginalPictureSound(
                    fixture.index,supervisor,
                    approve_render=lambda ev,scope:
                    ev=="public_fixture_only" and
                    scope["operation"]==
                        "nvp.p1f.render_original_cycles_frame.v1",
                    verify_isolated_worker=synthetic_only_boundary,
                    public_fixture_mode=True)
                try:
                    result=worker.render_frame(
                        fixture.pid,"rigged_reel_plan",0,12,"public_rigged_frame",
                        creator_event="public_fixture_only",
                        width=320,height=180,samples=8)
                except BaseException:
                    jobdir=supervisor.root/"public_rigged_frame"
                    for logfile in ("worker_stdout.log","worker_stderr.log"):
                        p=jobdir/logfile
                        if p.exists():
                            print(logfile+":\n"+p.read_text(
                                "utf8",errors="replace")[-12000:])
                    raise
                if result.get("status")!="NOT_DELIVERED":
                    self.assertEqual(result["format"],
                                     "nvp.p1f.independent_picture_audio_receipt.v1")
                    self.assertFalse(result["entire_film_rendered"])
                    self.assertEqual(result["original_derived_audio"]["sample_count"],
                                     2000)
                    self.assertTrue((supervisor.root/"public_rigged_frame"/
                                     "original_frame.png").is_file())
                    reopened=P1FOriginalPictureSound(
                        fixture.index,
                        BlenderWorkerSupervisor(
                            supervisor.root,blender_executable=binary,
                            blender_sha256=sha_file(binary),blender_version=version),
                        approve_render=lambda *_:False,
                        verify_isolated_worker=lambda *_:False)
                    result2=reopened.verify_delivered(
                        fixture.pid,"rigged_reel_plan","public_rigged_frame")
                    self.assertEqual(result["original_picture"],
                                     result2["original_picture"])
                    # Genuine MULTI-FRAME pipeline test: each frame is a
                    # distinct supervised Blender/Cycles/PCM transaction.
                    # Bounded public test geometry; not a finished film.
                    from backend.nvp_p1f_multishot_reel import P1FDurableShotReels
                    batch=P1FDurableShotReels(
                        fixture.index,worker,
                        approve_batch=lambda ev,scope:
                            ev=="public_fixture_only" and
                            scope["operation"]==
                                "nvp.p1f.admit_finite_source_batch.v1" and
                            scope["frame_count"]==2,
                        verify_batch_live=lambda scope:
                            scope["operation"]==
                                "nvp.p1f.verify_finite_source_batch_live.v1" and
                            scope["batch_id"]=="public_two_frames")
                    accepted=batch.create_batch(
                        fixture.pid,"rigged_reel_plan","public_two_frames",
                        reel_index=0,first_frame_offset=0,frame_count=2,
                        creator_event="public_fixture_only")
                    self.assertEqual(accepted["frames"],2)
                    for _ in range(2):
                        fresh=batch.run_next(
                            "public_two_frames",creator_event="public_fixture_only",
                            width=320,height=180,samples=8)
                        self.assertEqual(fresh["status"],"FRAME_ACCEPTED")
                    verified=batch.verify("public_two_frames")
                    self.assertTrue(verified["all_frames_verified"])
                    self.assertEqual(verified["frames_accepted"],2)
                    reopened_batch=P1FDurableShotReels(
                        fixture.index,reopened,approve_batch=lambda *_:False,
                        verify_batch_live=lambda scope:False)
                    self.assertTrue(reopened_batch.verify(
                        "public_two_frames")["all_frames_verified"])
                    from backend.nvp_p1f_picture_audio_delivery import (
                        P1FVerifiedSegmentDelivery)
                    deliverer=P1FVerifiedSegmentDelivery(reopened_batch)
                    segment=deliverer.deliver("public_two_frames")
                    self.assertEqual(segment["status"],
                                     "SOURCE_SEGMENT_DELIVERED")
                    self.assertEqual(segment["frame_count"],2)
                    self.assertEqual(segment["audio_sample_count_per_channel"],4000)
                    self.assertFalse(segment["whole_film_delivered"])
                    self.assertFalse(segment["muxed_movie_created"])
                    verified_segment=deliverer.verify_delivered("public_two_frames")
                    self.assertEqual(verified_segment["status"],
                                     "SOURCE_SEGMENT_REVERIFIED")
                    self.assertEqual(verified_segment["audio_sha256"],
                                     segment["audio_sha256"])
                    from backend.nvp_p1f_p2_verified_coverage import (
                        P1FVerifiedFilmCoverage)
                    coverage=P1FVerifiedFilmCoverage(deliverer)
                    coverage.register(
                        fixture.pid,"rigged_reel_plan","public_two_frames")
                    partial=coverage.verify_coverage(
                        fixture.pid,"rigged_reel_plan")
                    self.assertEqual(partial["verified_frames"],2)
                    self.assertFalse(partial["all_source_frames_verified"])
                    self.assertFalse(partial["portable_film_created"])
                    with self.assertRaises(RuntimeError):
                        coverage.register(
                            fixture.pid,"rigged_reel_plan","public_two_frames")
                    with self.assertRaises(RuntimeError):
                        deliverer.deliver("public_two_frames")
                    with self.assertRaises(RuntimeError):
                        reopened_batch.run_next(
                            "public_two_frames",creator_event="replayed")
                else:
                    state=supervisor.inspect("public_rigged_frame")
                    jobdir=supervisor.root/"public_rigged_frame"
                    for logfile in ("worker_stdout.log","worker_stderr.log"):
                        p=jobdir/logfile
                        if p.exists():
                            print(logfile+":\n"+p.read_text(
                                "utf8",errors="replace")[-12000:])
                    self.fail("Genuine Blender/Job fixture failed: "+str(state))
        finally:
            fixture.doCleanups()


if __name__=="__main__":
    unittest.main()
