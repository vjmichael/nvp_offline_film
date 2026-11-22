"""USD-FILM-01O/Q original source integration, NO simulated Blender pixels.

Reuses the existing genuine nine-camera world/ActorID/48k Take fixture; tests
the original 720-frame USD source, creator-approved revisioned 01M bank and
01Q edit, precise selected-view 90x8 render plan and stale-source refusal.
It never substitutes old FFmpeg, uncontained worker or an accepted film master.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from pxr import Usd,UsdGeom

from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01o_original_camera_roll_source import (
    original_camera_roll_source,STAGE,MANIFEST,file_sha,FRAMES)
from backend.nvp_usd_film01p_source_multicam_edl import (
    even_camera_coverage_edl)
from backend.nvp_usd_film01q_selected_view_edit import (
    OriginalSelectedViewEdit,selected_render_plan,CHUNK,CHUNKS)


class NativeOriginalSelectedCameraSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import within setup so unittest discovery does not duplicate the
        # imported original TestCase in this exact-head workflow step.
        from test_nvp_usd_film01i_ninecam_take import NineCameraOriginalFilmSource
        cls.fixture=NineCameraOriginalFilmSource
        cls.fixture.setUpClass()
        cls.index=cls.fixture.index
        cls.pid=cls.fixture.pid
        cls.root=cls.fixture.root
        cls.take_id="OneThirtySecondWorldTake"
        cls.bank_id="OriginalReviewedFilm01MSource"
        cls.edit_id="OriginalReviewedFilm01QSelected"
        cls.bank_writer=DirectorCameraBank(cls.index,
            verify_director_action=lambda event,scope:
                event=="DIRECTOR_APPROVED_SOURCE_ONLY" and
                scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
        cls.editor=OriginalSelectedViewEdit(cls.index,
            verify_director_action=lambda event,scope:
                event=="DIRECTOR_APPROVED_SOURCE_ONLY" and
                scope["operation"]=="nvp.film01q.publish_selected_view_edit.v1")
        cls.source_dir=cls.root/"original_source_01o"
        cls.bank=cls.bank_writer.create_standard_nine_preset(
            cls.pid,cls.bank_id,
            original_nine_rig_id="OnePerformanceNineCamBank",
            director_event="DIRECTOR_APPROVED_SOURCE_ONLY")
        cls.bank_doc=cls.bank_writer.verify(cls.pid,cls.bank_id,1)
        cls.ids=[c["camera_id"] for c in cls.bank_doc["cameras"]]
        cls.cuts=even_camera_coverage_edl(cls.ids)
        cls.record=cls.editor.create(
            cls.pid,cls.edit_id,
            camera_bank_id=cls.bank_id,camera_bank_revision=1,
            cuts=cls.cuts,director_event="DIRECTOR_APPROVED_SOURCE_ONLY")
        cls.original_take_sha=cls.index.read_revision(
            cls.pid,cls.take_id,1)["document_sha256"]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"fixture"):
            cls.fixture.tearDownClass()

    def test_exact_source_720_frames_and_90_native_selected_chunks(self):
        manifest=original_camera_roll_source(
            self.index,self.pid,self.bank_id,revision=1,
            folder=self.source_dir)
        self.assertEqual(manifest["frame_count"],720)
        self.assertEqual(manifest["camera_count"],9)
        self.assertEqual(len(manifest["original_frame_evidence"]),720)
        self.assertFalse(manifest["native_cycles_pixels_rendered"])
        self.assertEqual(manifest["original_world_take_sha256"],
                         self.original_take_sha)
        stage=Usd.Stage.Open(str(self.source_dir/STAGE))
        self.assertEqual(stage.GetFramesPerSecond(),24.)
        self.assertEqual(stage.GetStartTimeCode(),1.)
        self.assertEqual(stage.GetEndTimeCode(),720.)
        self.assertEqual(file_sha(self.source_dir/STAGE),
                         manifest["source_usd_sha256"])
        for number in (0,4,239,240,479,480,719):
            frame=manifest["original_frame_evidence"][number]
            self.assertEqual(frame["original_film_tick"],
                number*manifest["original_ticks_per_second"]//24)
            self.assertEqual(len(frame["original_actor_positions"]),4)
            self.assertEqual(len(frame["original_camera_positions"]),9)
        plan=selected_render_plan(
            self.index,self.pid,self.edit_id,1,
            original_source_directory=self.source_dir)
        body=plan["plan"]
        self.assertEqual(body["selected_final_frame_count"],FRAMES)
        self.assertEqual(len(body["frames"]),720)
        self.assertEqual(len(body["chunks"]),90)
        self.assertEqual(CHUNK*CHUNKS,720)
        self.assertFalse(body["cycles_pixels_rendered"])
        self.assertFalse(body["director_visual_approval"])
        self.assertFalse(body["all_original_camera_rolls_required"])
        self.assertEqual(body["original_world_take_sha256"],
                         self.original_take_sha)
        for number in (0,4,79,80,239,240,719):
            entry=body["frames"][number]
            original=manifest["original_frame_evidence"][number]
            self.assertEqual(entry["original_film_tick"],
                             original["original_film_tick"])
            self.assertEqual(entry["original_actor_state_sha256"],
                             original["original_actor_state_sha256"])
            self.assertEqual(entry["camera_id"],self.cuts[number//80][
                "camera_id"])
            self.assertEqual(len(entry["view_cache_sha256"]),64)
        self.assertEqual(self.index.read_revision(
            self.pid,self.take_id,1)["document_sha256"],self.original_take_sha)

    def test_director_camera_rig_is_session_only(self):
        # An absent original namespace must be accepted, never turned into
        # an invalid-prim exception or a persistent source-world mutation.
        with self.bank_writer.open_source_views(
                self.pid, self.bank_id, 1) as view:
            rig = view["stage"].GetPrimAtPath("/World/NVPDirectorCameraRig")
            self.assertTrue(rig and rig.IsDefined())
            self.assertEqual(len(view["camera_paths"]), 9)

        from backend.nvp_usd_film01_world import OpenUSDWorldComposer
        take = self.index.read_revision(self.pid, self.take_id, 1)["data"]
        with OpenUSDWorldComposer(self.index).open(
                self.pid, take["world_id"], take["world_revision"]) as world:
            world.load([take["original_scene_takes"][0]["set"]])
            rig = world.stage.GetPrimAtPath("/World/NVPDirectorCameraRig")
            self.assertFalse(rig and rig.IsDefined())
        self.assertEqual(self.index.read_revision(
            self.pid, self.take_id, 1)["document_sha256"],
            self.original_take_sha)

    def test_director_refusal_cannot_publish_new_source_edit(self):
        denied=OriginalSelectedViewEdit(
            self.index,verify_director_action=lambda *_:False)
        with self.assertRaises(PermissionError):
            denied.create(self.pid,"DeniedOriginalFilmEdit",
                camera_bank_id=self.bank_id,camera_bank_revision=1,
                cuts=self.cuts,director_event="MODEL_REQUEST")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DeniedOriginalFilmEdit",1)

    def test_tampered_source_manifest_refused_without_render(self):
        if not self.source_dir.exists():
            original_camera_roll_source(
                self.index,self.pid,self.bank_id,revision=1,
                folder=self.source_dir)
        path=self.source_dir/MANIFEST
        original=path.read_bytes()
        manifest=json.loads(original)
        manifest["original_performance_sha256"]="f"*64
        try:
            path.write_text(json.dumps(manifest,sort_keys=True),encoding="utf8")
            with self.assertRaises(PermissionError):
                selected_render_plan(
                    self.index,self.pid,self.edit_id,1,
                    original_source_directory=self.source_dir)
        finally:
            path.write_bytes(original)
        self.assertEqual(self.index.read_revision(
            self.pid,self.take_id,1)["document_sha256"],self.original_take_sha)

    def test_plan_never_synthesizes_an_accepted_worker_receipt(self):
        doc=self.editor.verify(self.pid,self.edit_id,1)
        self.assertEqual(doc["original_actor_performance_unchanged"],True)
        self.assertEqual(doc["original_audio_is_one_shared_source"],True)
        self.assertEqual(doc["film_rendered"],False)
        self.assertEqual(doc["director_picture_reviewed"],False)
        self.assertEqual(len(doc["selected_viewpoint_ids"]),9)


if __name__=="__main__":
    unittest.main()
