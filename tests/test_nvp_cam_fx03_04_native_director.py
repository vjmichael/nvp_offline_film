"""CAM-FX-03/04 genuine native ActorID/district + durable AI handoff.

Real FilmIndex, original 01E ActorID/PCM, verified source 02M-H modular
district and pxr.OpenUSD; fake model used ONLY for contract parser tests.
The independent real GGUF + installed Windows test remains a native gate.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails
from backend.nvp_cam_fx03_source_guidance import guided_camera_scene,_hit
from backend.nvp_cam_fx03_durable_drafts import DurableOriginalCameraDrafts
from backend.nvp_cam_fx04_model_camera_candidate import (
    generate_camera_candidate,FORMAT as MODEL_FORMAT)
from backend.nvp_wo6_verified_local_model import FORMAT as MODEL_RECEIPT


class FakeCompletedCameraProvider:
    """Contract-only generated text. Never pass as GGUF execution evidence."""
    def __init__(self,reply,model_id="local-cam-test"):
        self.reply=reply
        self.model_id=model_id
        self.completion_receipt=None
    def complete(self,system,user):
        self.completion_receipt={
            "format":MODEL_RECEIPT,
            "selected_model_id":self.model_id,
            "provider_reported_model_id":self.model_id,
            "generated_text_sha256":
                sha256(self.reply.strip().encode("utf8")).hexdigest(),
            "native_worker_authorized":False,
            "provider_self_report_not_attestation":True}
        return self.reply

def node(tick,pos,target):
    return {
        "tick":tick,"position_m":pos,"target_m":target,
        "tangent_in_mps":[0.,0.,0.],
        "tangent_out_mps":[0.,0.,0.],
        "roll_deg":0.,
        "focal_length_mm":35.,
        "focus_distance_m":8.,
        "f_stop":5.6,
        "segment_mode":"hermite","easing":"smoothstep"}

class OriginalCAMFX03SourceAndDurableAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse genuinely approved source district + original 01E actors.
        # Local import avoids unittest collecting another TestCase twice.
        from test_nvp_usd_film02mh_real_shot_render import (
            OriginalActorDistrictNativeRenderTests)
        cls.source=OriginalActorDistrictNativeRenderTests
        cls.source.setUpClass()
        cls.index=cls.source.index
        cls.pid=cls.source.pid
        cls.world_take=cls.source.take_id
        bank=DirectorCameraBank(
            cls.index,verify_director_action=lambda event,scope:
            event=="TEST_NATIVE_CAMERA_BANK" and
            scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        cls.bank=bank.create(cls.pid,"NativeCAMFX03Bank",
            world_take_id=cls.world_take,
            cameras=[{"camera_id":"SourceRailCam",
                      "setup":"Actual approved 02M street",
                      "framing":"wide",
                      "position_m":[0.,-8.,5.],
                      "rotation_euler_deg":[0.,0.,0.],
                      "focal_length_mm":35.,
                      "focus_distance_m":8.,
                      "clip_range_m":[.01,10000.],
                      "move_keys":[],"camera_ray_exclusions":[]}],
            director_event="TEST_NATIVE_CAMERA_BANK")
        cls.original_take_sha=cls.index.read_revision(
            cls.pid,cls.world_take,1)["document_sha256"]
        cls.original_pcm_take_shas=list(cls.source.original_actor_take_shas)

    @classmethod
    def tearDownClass(cls):
        cls.source.tearDownClass()

    def setUp(self):
        self.temp=TemporaryDirectory(prefix="nvp-camfx03-real-src-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.session="a"*64
        self.store=DurableOriginalCameraDrafts(
            self.index,self.root,host_session_id=self.session)
        self.spec={
            "camera_bank_id":"NativeCAMFX03Bank",
            "camera_bank_revision":1,
            "camera_id":"SourceRailCam",
            "film_start_tick":0,
            "film_end_tick":2*T,
            "technique":"dolly",
            "rail_origin_m":[0.,0.,0.],
            "filmback_mm":[36.,20.25],
            "nodes":[
                node(0,[0.,-9.,4.],[0.,0.,1.]),
                node(T,[.5,-8.,4.],[0.,0.,1.]),
                node(2*T,[1.,-7.,4.],[0.,0.,1.])]}
        self.actor_id=self.index.read_revision(
            self.pid,self.world_take,1)["data"][
                "canonical_original_actors"][0]["actor_id"]

    def guide(self,actor=None):
        return guided_camera_scene(
            self.index,self.pid,self.spec,
            actor_id=actor,
            district_binding_id="Native02MHBinding1")

    def test_true_source_actor_bounds_and_approved_native_mesh_occlusion_guidance(self):
        report=self.guide(self.actor_id)
        self.assertEqual(report["format"],
            "nvp.cam_fx03.source_grounded_actor_framing_and_occlusion.v1")
        self.assertEqual(report["world_take_sha256"],self.original_take_sha)
        self.assertEqual(report["native_actor_count"],4)
        self.assertEqual(len(report["source_guided_frames"]),3)
        self.assertEqual(report["source_guided_frames"][0]["film_tick"],0)
        self.assertEqual(report["source_guided_frames"][-1]["film_tick"],2*T)
        self.assertTrue(report["native_scene_reviewed"])
        self.assertTrue(report["source_actor_takes_and_pcm_unchanged"])
        self.assertFalse(report["cycles_pixels_rendered"])
        for frame in report["source_guided_frames"]:
            self.assertEqual(len(frame["original_actor_views"]),4)
            self.assertEqual(frame["selected_actor_id"],self.actor_id)
            self.assertIsNotNone(frame["selected_actor_center_world_m"])
            self.assertGreater(frame["selected_actor_center_ray"][
                "reviewed_original_district_triangles"],0)
            self.assertFalse(frame["selected_actor_center_ray"][
                "full_image_visibility_proven"])
            for actor in frame["original_actor_views"]:
                self.assertEqual(len(actor["bounds_world_m"]),2)
                self.assertEqual(len(actor["center_world_m"]),3)
                self.assertIn(actor["frame"]["state"],{
                    "BEHIND_CAMERA","PARTLY_IN_FRAME","OUT_OF_FRAME"})
        with self.assertRaises(PermissionError):
            self.guide("ImaginaryModelActor")
        self.assertEqual(self.index.read_revision(
            self.pid,self.world_take,1)["document_sha256"],
            self.original_take_sha)
        for take,original_sha in zip(self.source.shots,
                                     self.original_pcm_take_shas):
            self.assertEqual(self.index.read_revision(
                self.pid,take["take_id"],1)["document_sha256"],original_sha)

    def test_real_original_usd_triangle_math_has_detected_and_clear_center_rays(self):
        triangle=([0.,0.,0.],[2.,0.,0.],[0.,2.,0.])
        self.assertAlmostEqual(_hit([.4,.4,2.],[0.,0.,-1.],5.,triangle),2.)
        self.assertIsNone(_hit([4.,4.,2.],[0.,0.,-1.],5.,triangle))
        self.assertIsNone(_hit([.4,.4,2.],[0.,0.,1.],5.,triangle))
        self.assertIsNone(_hit([.4,.4,2.],[0.,0.,-1.],2.02,triangle))

    def test_durable_handle_edits_undo_restart_and_old_process_model_custody(self):
        first=self.store.create(
            self.pid,"DurableSourceCameraRail",0,self.spec)
        self.assertEqual(first["state"],"DRAFT")
        self.assertEqual(first["version"],1)
        self.assertEqual(first["source_world_take_sha256"],
                         self.original_take_sha)
        edited=deepcopy(self.spec)
        edited["nodes"][1]["position_m"]=[.9,-7.7,4.2]
        second=self.store.save(
            self.pid,first["draft_id"],first["version"],edited)
        self.assertEqual(second["version"],2)
        self.assertEqual(second["undo_depth"],1)
        with self.assertRaises(RuntimeError):
            self.store.save(self.pid,first["draft_id"],1,edited)
        restarted=DurableOriginalCameraDrafts(
            self.index,self.root,host_session_id="b"*64)
        recovered=restarted.reopen(self.pid,first["draft_id"])
        self.assertEqual(recovered["version"],2)
        self.assertEqual(recovered["rail_spec"]["nodes"][1][
            "position_m"],[.9,-7.7,4.2])
        undone=restarted.undo(self.pid,first["draft_id"],2)
        self.assertEqual(undone["version"],3)
        self.assertEqual(undone["undo_depth"],0)
        self.assertEqual(undone["rail_spec"]["nodes"][1][
            "position_m"],[.5,-8.,4.])
        self.assertTrue(self.index.list_objects(
            self.pid,kind="take"))
        self.assertEqual(self.index.read_revision(
            self.pid,self.world_take,1)["document_sha256"],
            self.original_take_sha)

    def test_interrupted_native_os_approval_never_replays_and_existing_source_recovers(self):
        first=self.store.create(self.pid,"InterruptedSourceRail",0,self.spec)
        started=self.store.begin_publish(
            self.pid,first["draft_id"],1,first["proposal_sha256"])
        self.assertEqual(started["version"],1)
        # Reopen in SAME desktop profile must not manufacture a crash.
        self.assertEqual(self.store.reopen(self.pid,first["draft_id"])[
            "state"],"PUBLISHING")
        restart=DurableOriginalCameraDrafts(
            self.index,self.root,host_session_id="c"*64)
        interrupted=restart.reopen(self.pid,first["draft_id"])
        self.assertEqual(interrupted["state"],
            "INTERRUPTED_REQUIRES_NEW_APPROVAL")
        self.assertEqual(restart.recover_published(
            self.pid,first["draft_id"])["state"],
            "INTERRUPTED_REQUIRES_NEW_APPROVAL")
        with self.assertRaises(PermissionError):
            restart.begin_publish(
                self.pid,first["draft_id"],1,first["proposal_sha256"])
        # An independent *original* publication may have committed just
        # before the previous process died. Reconcile it by SHA, no retry.
        original=OriginalCameraRails(
            self.index,verify_director_action=lambda event,scope:
            event=="TEST_ONE_USE_OS" and
            scope["operation"]==
                "nvp.cam_fx02.publish_exact_director_camera_rail.v1")
        emitted=original.publish(
            self.pid,"InterruptedSourceRail",self.spec,
            expected_revision=0,
            preview_sha256=first["proposal_sha256"],
            director_event="TEST_ONE_USE_OS")
        restored=restart.recover_published(self.pid,first["draft_id"])
        self.assertEqual(restored["state"],"PUBLISHED")
        self.assertEqual(restored["published_sha256"],
                         emitted["document_sha256"])
        self.assertFalse(restored["native_approval_granted"])
        self.assertEqual(self.index.read_revision(
            self.pid,self.world_take,1)["document_sha256"],
            self.original_take_sha)

    def test_local_model_source_contract_and_atomic_cancelled_late_response(self):
        source=self.guide(self.actor_id)
        answer={"technique":"dolly",
                "nodes":[
                    {k:v for k,v in {
                        "tick":0,"position_m":[0.,-9.,4.],
                        "target_m":[0.,0.,1.],
                        "roll_deg":0.,
                        "focal_length_mm":35.,
                        "focus_distance_m":8.}.items()},
                    {"tick":2*T,"position_m":[1.,-7.,4.],
                     "target_m":[0.,0.,1.],"roll_deg":0.,
                     "focal_length_mm":45.,
                     "focus_distance_m":6.}]}
        model=FakeCompletedCameraProvider(json.dumps(answer))
        proposed=generate_camera_candidate(
            self.spec,source,direction="Dolly toward the verified actor",
            model_id="local-cam-test",writer=model)
        self.assertEqual(proposed["format"],MODEL_FORMAT)
        self.assertTrue(proposed["unapproved_draft_only"])
        self.assertFalse(proposed["os_authorization_granted"])
        self.assertFalse(proposed["model_weights_attested"])
        self.assertEqual(proposed["source_guidance_sha256"],
            source["guidance_sha256"])
        first=self.store.create(self.pid,"AIDraftCameraRail",0,self.spec)
        aid=self.store.start_model(
            self.pid,first["draft_id"],1,"local-cam-test",
            source["guidance_sha256"],proposed["director_direction_sha256"])
        status=self.store.complete_model(
            self.pid,aid,1,source["guidance_sha256"],
            proposed["proposed_rail_spec"],proposed)
        self.assertEqual(status["state"],"DRAFT_UPDATED_UNAPPROVED")
        self.assertEqual(status["result_version"],2)
        self.assertEqual(status["draft"]["state"],"DRAFT")
        self.assertEqual(status["draft"]["proposed_by"],"model")
        self.assertFalse(status["draft"]["native_approval_granted"])
        # Cancelled model completion cannot write late USD; no authority.
        aid2=self.store.start_model(
            self.pid,first["draft_id"],2,"local-cam-test",
            source["guidance_sha256"],proposed["director_direction_sha256"])
        self.store.cancel_model(self.pid,aid2)
        with self.assertRaises(PermissionError):
            self.store.complete_model(
                self.pid,aid2,2,source["guidance_sha256"],
                proposed["proposed_rail_spec"],proposed)
        old=DurableOriginalCameraDrafts(
            self.index,self.root,host_session_id="e"*64)
        aid3=self.store.start_model(
            self.pid,first["draft_id"],2,"local-cam-test",
            source["guidance_sha256"],proposed["director_direction_sha256"])
        self.assertEqual(old.model_status(self.pid,aid3)["state"],
                         "INTERRUPTED_REQUIRES_NEW_GENERATION")
        with self.assertRaises(PermissionError):
            self.store.complete_model(
                self.pid,aid3,2,source["guidance_sha256"],
                proposed["proposed_rail_spec"],proposed)
        malformed=deepcopy(answer);malformed["execute"]="grant_root"
        with self.assertRaises(ValueError):
            generate_camera_candidate(
                self.spec,source,direction="Original framing",
                model_id="local-cam-test",
                writer=FakeCompletedCameraProvider(json.dumps(malformed)))
        self.assertEqual(self.index.read_revision(
            self.pid,self.world_take,1)["document_sha256"],
            self.original_take_sha)

if __name__=="__main__":
    unittest.main()
