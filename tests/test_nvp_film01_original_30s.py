"""FILM01 independent original 30-second source and actual CPU preview checks."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import base64
import json
import unittest
import wave

from tools.nvp_film01_original_30s import (
    write_original_30s_source,render_original_30s_review,
    FORMAT,FRAMES,FPS,DURATION,T,SHOT_SECONDS,SOURCE_IDS)
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_wo6_07f_rendered_av import rendered_source_window


class Genuine30SecondOriginalShort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=TemporaryDirectory()
        cls.root=Path(cls.temporary.name).resolve()/"Original30s"
        cls.report=write_original_30s_source(
            cls.root,approve_test_only=True)
        cls.studio=Studio(cls.root/"short.sqlite3")
        cls.index=FilmIndex(cls.studio)
        cls.pid=cls.report["project_id"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_three_distinct_real_openusd_takes_two_cuts_and_original_pcm(self):
        r=self.report
        self.assertEqual(r["format"],FORMAT)
        self.assertEqual(r["duration_seconds"],DURATION)
        self.assertEqual(r["target_frames"],720)
        self.assertEqual(r["shot_count"],3)
        self.assertEqual(r["hard_cuts"],2)
        self.assertEqual(len(r["shots"]),3)
        self.assertFalse(r["photorealistic_story_quality_approved"])
        self.assertFalse(r["full_color_managed_2k_dci_delivery"])
        self.assertFalse(r["virtual_artistic_lighting_rendered_in_pixels"])
        for i,shot in enumerate(r["shots"]):
            take=self.index.read_revision(self.pid,shot["take_id"],1)
            self.assertTrue(take["data"]["frozen"])
            self.assertEqual(take["document_sha256"],shot["take_sha256"])
            self.assertEqual(take["data"]["scene_revision"],i+1)
            self.assertEqual(
                OpenUSDTakeCapture(
                    self.index,verify_creator_action=lambda *_:False).verify_take(
                    self.pid,shot["take_id"])["status"],
                "VERIFIED_FROZEN_DATA_TAKE")
        edit=SlateSequenceAssembly(
            DigitalSlateBranches(self.index,verify_editor_action=lambda *_:False),
            verify_editor_action=lambda *_:False)
        mapped=[edit.source_at(
            self.pid,r["edit_id"],1,
            timeline_tick=frame*T//FPS,
            expected_edit_sha256=r["edit_sha256"])
            for frame in (0,240,480)]
        self.assertEqual([x["source_take_id"] for x in mapped],list(SOURCE_IDS))
        self.assertEqual(len({x["source_take_sha256"] for x in mapped}),3)

    def test_real_three_shot_visual_samples_and_timed_beacon_sound(self):
        receipts=[]
        for frame in (0,240,480,624):
            packet=rendered_source_window(
                self.index,self.pid,self.report["edit_id"],1,
                self.report["edit_sha256"],frame,1,
                camera_path="/World/Camera")
            self.assertEqual(packet["count"],1)
            self.assertTrue(packet["real_original_usd_pixels_rendered"])
            self.assertEqual(packet["actual_audio_sample_count"],2000)
            self.assertGreater(packet["images"][0]["actual_rasterized_triangles"],0)
            receipts.append(packet)
        self.assertEqual([
            r["images"][0]["source_take_id"] for r in receipts[:3]],
            list(SOURCE_IDS))
        self.assertTrue(any(
            x["event_id"]=="BeaconSignalRestored"
            for x in receipts[3]["images"][0]["recorded_pcm_source_tracks"]))
        self.assertFalse(receipts[3]["film_delivered"])

    def test_genuinely_rendered_window_archive_has_original_png_and_sound_but_no_fake_movie(self):
        dest=Path(self.temporary.name).resolve()/"first-six-real-frames.zip"
        proof=render_original_30s_review(
            self.root,dest,max_frames=6)
        self.assertEqual(proof["rendered_frame_count"],6)
        self.assertEqual(proof["audio_sample_count"],6*2000)
        self.assertFalse(proof["complete_720_frame_source_preview"])
        with ZipFile(dest) as archive:
            names=set(archive.namelist())
            self.assertIn("preview_frames/frame_0000.png",names)
            self.assertIn("preview_frames/frame_0005.png",names)
            self.assertIn("audio/original_source_review_48k_mono.wav",names)
            self.assertNotIn("movie.mp4",names)
            manifest=json.loads(archive.read(
                "original_30s_preview_receipt.json"))
            self.assertEqual(manifest["frames_rendered_from_usd"],6)
            self.assertFalse(manifest["playable_muxed_movie_created"])
            self.assertFalse(manifest["dci_master_or_dcp_created"])
            with wave.open(BytesIO(archive.read(
                    "audio/original_source_review_48k_mono.wav")),"rb") as wav:
                self.assertEqual(wav.getnframes(),6*2000)
                self.assertEqual(wav.getframerate(),48000)

    def test_no_creator_grant_no_overwrite_and_reopen_source_revision(self):
        with self.assertRaises(PermissionError):
            write_original_30s_source(
                self.root.parent/"NoConsent",approve_test_only=False)
        with self.assertRaises(PermissionError):
            write_original_30s_source(
                self.root,approve_test_only=True)
        prior=self.index.read_revision(
            self.pid,"Relay30Scene",1)["document_sha256"]
        later=self.index.read_revision(
            self.pid,"Relay30Scene",3)["document_sha256"]
        self.assertNotEqual(prior,later)
        self.assertEqual(self.report["shots"][0]["scene_sha256"],prior)
        self.assertEqual(self.report["shots"][2]["scene_sha256"],later)


if __name__=="__main__":
    unittest.main()
