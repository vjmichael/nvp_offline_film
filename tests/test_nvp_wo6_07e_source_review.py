"""WO6-07E genuine original slate source projection + real PCM frame audition.

Actual OpenUSD, FilmIndex, 48 kHz original PCM and frozen Takes. Only the
native human approval callback is simulated by existing test fixtures.
Audio sample and SHA are compared with real bytes; no picture render claimed.
"""
from __future__ import annotations
import base64
from hashlib import sha256
from io import BytesIO
import unittest
import wave

import test_nvp_wo6_sound_editorial as original
from backend.nvp_wo6_07e_source_review import (
    sample_editorial_source,FORMAT,SAMPLE_RATE,SAMPLES_PER_FRAME)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND


T=TICKS_PER_SECOND


class OriginalEditorialFramePCMReview(unittest.TestCase):
    def setUp(self):
        original.NativeSoundAndSlateFilmTime.setUp(self)
        self.cut_request=original.NativeSoundAndSlateFilmTime.authored(
            self,"editorial_cut","review_assembled_original")
        self.sound_request=original.NativeSoundAndSlateFilmTime.authored(
            self,"sound_cue","review_derived_original_sound")
        edit_task=self.host.queue_decision(
            self.scope,**self.cut_request)["task_id"]
        self.assertEqual(self.host.run_next(
            timeout_seconds=180,expected_task_id=edit_task)["state"],"SUCCEEDED")
        audio_task=self.host.queue_decision(
            self.scope,**self.sound_request)["task_id"]
        self.assertEqual(self.host.run_next(
            timeout_seconds=180,expected_task_id=audio_task)["state"],"SUCCEEDED")
        self.edit=self.index.read_revision(
            self.pid,"review_assembled_original",1)
        self.sound=self.index.read_revision(
            self.pid,"review_derived_original_sound",1)
        self.parent_sha=self.original["document_sha256"]
        self.sound_samples=self.pcm.read(
            self.pid,"original_recording",1,0,8000)

    def review(self,frame,**options):
        return sample_editorial_source(
            self.index,self.pid,"review_assembled_original",1,
            self.edit["document_sha256"],frame,**options)

    def test_source_24fps_frame24_maps_second_immutable_segment_and_real_pcm(self):
        result=self.review(24,sound_timeline_id="review_derived_original_sound",
                           sound_timeline_revision=1,
                           sound_timeline_sha256=self.sound["document_sha256"])
        self.assertEqual(result["format"],FORMAT)
        self.assertEqual(result["output_film_time_tick"],str(T))
        self.assertEqual(result["source_film_time_tick"],str(T))
        self.assertEqual(result["source_projection"]["segment_id"],"middle")
        self.assertEqual(result["source_take_id"],"old_take")
        self.assertEqual(result["source_take_sha256"],self.parent_sha)
        self.assertTrue(result["source_audio_timeline_is_derived"])
        self.assertEqual(result["source_pcm_samples"],SAMPLES_PER_FRAME)
        self.assertEqual(len(result["source_pcm_tracks"]),1)
        self.assertEqual(result["source_pcm_tracks"][0]["source_id"],
                         "original_recording")
        self.assertEqual(result["source_pcm_tracks"][0]["source_sample_first"],0)
        self.assertFalse(result["frame_pixels_rendered"])
        self.assertFalse(result["finished_film_mastered_audio"])
        self.assertFalse(result["frame_and_audio_continuous_24fps_verified"])
        self.assertFalse(result["native_worker_authorized"])
        self.assertFalse(result["original_source_modified"])
        self.assertTrue(result["audio_muted_until_user_action"])
        self.assertEqual({p["role"] for p in result["scene_poses"]},
                         {"actor","camera"})
        self.assertTrue(result["audio_data_url"].startswith("data:audio/wav;base64,"))
        wav=base64.b64decode(result["audio_data_url"].split(",",1)[1])
        self.assertEqual(sha256(wav).hexdigest(),result["source_pcm_wav_sha256"])
        with wave.open(BytesIO(wav),"rb") as media:
            self.assertEqual(media.getframerate(),SAMPLE_RATE)
            self.assertEqual(media.getnchannels(),1)
            self.assertEqual(media.getsampwidth(),2)
            self.assertEqual(media.getnframes(),SAMPLES_PER_FRAME)
            data=media.readframes(SAMPLES_PER_FRAME)
        self.assertEqual(data[:4],bytes([7,0])*2)
        self.assertEqual(self.index.read_revision(
            self.pid,"old_take",1)["document_sha256"],self.parent_sha)
        self.assertEqual(self.pcm.read(
            self.pid,"original_recording",1,0,8000),self.sound_samples)

    def test_pre_cue_original_frame_replays_no_invented_audio(self):
        r=self.review(0,sound_timeline_id="review_derived_original_sound",
                      sound_timeline_revision=1,
                      sound_timeline_sha256=self.sound["document_sha256"])
        self.assertEqual(r["source_projection"]["segment_id"],"intro")
        self.assertFalse(r["source_pcm_tracks"])
        self.assertTrue(r["zero_audio_when_no_source"])
        self.assertIsNone(r["audio_data_url"])
        self.assertFalse(r["screen_image_provided"])
        self.assertFalse(r["audio_played_by_host"])

    def test_refuses_source_or_sound_mismatch_bounds_and_foreign_timeline(self):
        args=dict(sound_timeline_id="review_derived_original_sound",
                  sound_timeline_revision=1,
                  sound_timeline_sha256="0"*64)
        with self.assertRaises(PermissionError):
            self.review(24,**args)
        # Selecting an actual original soundtrack is a legitimate,
        # distinct review and must not be conflated with an added cue.
        original=self.review(24,sound_timeline_id="actions",
                             sound_timeline_revision=1,
                             sound_timeline_sha256=self.timeline_sha)
        self.assertFalse(original["source_audio_timeline_is_derived"])
        self.assertIsNone(original["audio_data_url"])
        for frame in (48,-1,True,24*60*60*3):
            with self.subTest(frame=frame),self.assertRaises(ValueError):
                self.review(frame)
        with self.assertRaises(PermissionError):
            sample_editorial_source(self.index,self.pid,
                                    "review_assembled_original",1,
                                    "0"*64,24)
        with self.assertRaises(ValueError):
            self.review(24,sound_timeline_id="review_derived_original_sound",
                        sound_timeline_revision=None,
                        sound_timeline_sha256=self.sound["document_sha256"])


if __name__=="__main__":
    unittest.main()
