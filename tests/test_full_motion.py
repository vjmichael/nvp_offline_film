"""PIPE-01B CPU-safe refusals, media checks and frame/audio contract."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_full_motion import FullMotionPipeline, EXPORT_PROFILES, _dialogue_timeline, _probe_video
from backend.nvp_presentation_pipeline import PresentationPipeline, PBR_ENGINE


class FullMotionContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"studio.sqlite"
        self.studio=Studio(self.db)
        self.index=FilmIndex(self.studio)
        self.pid=self.studio.create_project("PIPE-01B","Full motion film data")["id"]
        self.other=self.studio.create_project("Different project","No data leakage")["id"]
        self.pipeline=FullMotionPipeline(self.studio,self.index)

    def tearDown(self):
        self.tmp.cleanup()

    def test_declares_real_backend_limits_and_voice_unavailable(self):
        cap=self.pipeline.capabilities()
        self.assertEqual(cap["output"],"video/mp4")
        self.assertEqual(cap["codec"],"h264")
        self.assertEqual(sorted(cap["export_profiles"]),["dnxhr_hqx_mov","h264_mp4","prores_422_hq_mov"])
        self.assertEqual(cap["export_profiles"]["prores_422_hq_mov"],
                         {"container":"mov","codec":"prores","pix_fmt":"yuv422p10le",
                          "bits_per_component":10})
        self.assertEqual(EXPORT_PROFILES["prores_422_hq_mov"]["codec_tag"],"apch")
        self.assertEqual(cap["export_profiles"]["dnxhr_hqx_mov"],{
            "container":"mov","codec":"dnxhd","pix_fmt":"yuv422p10le",
            "bits_per_component":10})
        self.assertEqual(EXPORT_PROFILES["dnxhr_hqx_mov"]["codec_tag"],"AVdh")
        self.assertIn("blender_cycles",cap["renderers"])
        self.assertEqual(cap["audio"],"timecoded_dialogue_manifest_only_no_waveform")
        engine=PresentationPipeline.available_engines()
        self.assertEqual(len(engine),2)
        pbr=next(x for x in engine if x["engine"]==PBR_ENGINE)
        self.assertEqual(pbr["styles"],["pbr_noir","pbr_studio"])
        self.assertIn("proxy meshes",pbr["limitations"][1])

    def test_sample_accurate_dialogue_timebase_from_frozen_frames(self):
        frozen={"timed_take":{"fps":24,"shots":[{"stop_frame":49}],
               "dialogue":[{"line_id":"line_1","speaker":"actor_1",
                           "start_frame":4,"duration_frames":12},
                          {"line_id":"line_2","speaker":"actor_2",
                           "start_frame":30,"duration_frames":8}]}}
        cues=_dialogue_timeline(frozen)
        self.assertEqual(cues[0]["start_sample"],6000)
        self.assertEqual(cues[0]["duration_samples"],24000)
        self.assertEqual(cues[1]["start_sample"],58000)
        self.assertEqual(cues[1]["duration_samples"],16000)
        self.assertTrue(all(c["status"]=="timing_only_no_waveform" for c in cues))
        frozen["timed_take"]["dialogue"][1]["duration_frames"]=25
        with self.assertRaisesRegex(RuntimeError,"time span"):
            _dialogue_timeline(frozen)

    def test_rejects_unknown_video_backend_and_invalid_dimensions_pre_render(self):
        for conf in ({"engine":"ai_video"}, {"engine":"blender_cycles","style":"studio"},
                     {"engine":"blender_workbench","style":"pbr_studio"},
                     {"width":127},{"height":71},{"width":48},{"timeout":0},
                     {"output_profile":"cinema_dcp_not_a_video_file"},
                     {"output_profile":"dnxhr_unknown_variant"}):
            with self.subTest(conf=conf),self.assertRaises(ValueError):
                self.pipeline.render_video(self.pid,"missing_take","video_1",self.root/"movie",**conf)
        self.assertEqual(self.index.list_objects(self.pid,kind="presentation"),[])

    def test_verified_immutable_streamed_media_recovers_and_rejects_corruption(self):
        content=b"\0\1NVP FILM CLIP BYTES"*50
        src=self.root/"movie.mp4"
        src.write_bytes(content)
        receipt=self.index.put_media_file(self.pid,src,"video/mp4")
        self.assertEqual(receipt["sha256"],hashlib.sha256(content).hexdigest())
        store=FilmIndex(Studio(self.db))
        checked=store.verify_media_file(self.pid,receipt["sha256"],"video/mp4")
        self.assertEqual(checked["size_bytes"],len(content))
        with self.assertRaises(KeyError):
            store.verify_media_file(self.other,receipt["sha256"],"video/mp4")
        with self.assertRaisesRegex(RuntimeError,"type mismatch"):
            store.verify_media_file(self.pid,receipt["sha256"],"audio/wav")
        with self.assertRaises(ValueError):
            store.put_media_file(self.pid,src,"video/mp4",max_bytes=4)
        with self.assertRaises(ValueError):
            store.put_media_file(self.pid,src,"image/gif")
        Path(checked["path"]).write_bytes(content[:-1]+b"X")
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            store.verify_media_file(self.pid,receipt["sha256"],"video/mp4")
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            store.put_media_file(self.pid,src,"video/mp4")

    def test_professional_mov_sha_registration_reopens_and_isolation(self):
        raw=b"demo-encoded-mov-not-decoded-here"*40
        mov=self.root/"source_mezzanine.mov"
        mov.write_bytes(raw)
        record=self.index.put_media_file(self.pid,mov,"video/quicktime")
        self.assertEqual(record["media_type"],"video/quicktime")
        after=FilmIndex(Studio(self.db))
        self.assertEqual(after.verify_media_file(self.pid,record["sha256"],
                                                "video/quicktime")["size_bytes"],len(raw))
        with self.assertRaises(KeyError):
            after.verify_media_file(self.other,record["sha256"],"video/quicktime")
        with self.assertRaisesRegex(RuntimeError,"type mismatch"):
            after.verify_media_file(self.pid,record["sha256"],"video/mp4")

    def test_prores_probe_rejects_wrong_profile_bitdepth_and_codec_tag(self):
        base={"codec_name":"prores","codec_tag_string":"apch",
              "width":128,"height":72,"nb_read_frames":"16",
              "r_frame_rate":"24/1","pix_fmt":"yuv422p10le"}
        request={"fps":24,"width":128,"height":72,"frames":16,
                 "output_profile":"prores_422_hq_mov"}
        import json
        with patch("backend.nvp_full_motion._run",return_value=
            type("Result",(),{"stdout":json.dumps({"streams":[base]})})()):
            good=_probe_video(self.root/"professional.mov","ffprobe",request)
            self.assertEqual(good["codec"],"prores")
            self.assertEqual(good["codec_tag"],"apch")
        for change in ({"codec_tag_string":"apcn"},
                       {"pix_fmt":"yuv422p"},
                       {"r_frame_rate":"25/1"},
                       {"nb_read_frames":"15"},
                       {"codec_name":"h264"}):
            corrupted={**base,**change}
            with self.subTest(change=change),patch(
                "backend.nvp_full_motion._run",return_value=
                type("Result",(),{"stdout":json.dumps({"streams":[corrupted]})})()):
                with self.assertRaisesRegex(RuntimeError,"mismatch"):
                    _probe_video(self.root/"professional.mov","ffprobe",request)

    def test_dnxhr_hqx_codec_profile_and_raster_refusal(self):
        import json
        frame={"codec_name":"dnxhd","profile":"DNXHR HQX",
               "codec_tag_string":"AVdh","width":256,"height":144,
               "nb_read_frames":"16","r_frame_rate":"24/1",
               "pix_fmt":"yuv422p10le"}
        request={"output_profile":"dnxhr_hqx_mov",
                 "fps":24,"width":256,"height":144,"frames":16}
        with patch("backend.nvp_full_motion._run",
                   return_value=type("Result",(),{"stdout":json.dumps({"streams":[frame]})})()):
            receipt=_probe_video(self.root/"dnxhr.mov","ffprobe",request)
            self.assertEqual(receipt["codec_profile"],"DNXHR HQX")
            self.assertEqual(receipt["codec_tag"],"AVdh")
        for corruption in ({"profile":"DNXHR HQ"},{"codec_tag_string":"AVdn"},
                           {"pix_fmt":"yuv422p"},{"nb_read_frames":"15"},
                           {"width":128},{"codec_name":"prores"}):
            with self.subTest(corruption=corruption),patch(
                "backend.nvp_full_motion._run",
                return_value=type("Result",(),{"stdout":json.dumps({"streams":[{**frame,**corruption}]})})()):
                with self.assertRaisesRegex(RuntimeError,"mismatch"):
                    _probe_video(self.root/"dnxhr.mov","ffprobe",request)

    def test_media_path_symlink_or_empty_rejected(self):
        blank=self.root/"empty.mp4"
        blank.write_bytes(b"")
        with self.assertRaisesRegex(ValueError,"Empty media"):
            self.index.put_media_file(self.pid,blank,"video/mp4")
        link=self.root/"symlink.mp4"
        try:
            link.symlink_to(blank)
        except OSError:
            self.skipTest("OS does not permit creating file symlinks")
        with self.assertRaisesRegex(RuntimeError,"symlinked"):
            self.index.put_media_file(self.pid,link,"video/mp4")

    def test_forged_motion_presentation_does_not_claim_verified_video(self):
        fake=self.index.register_revision(
            self.pid,"video_forged","presentation",
            {"format":"nvp.presentation.motion.v1","status":"rendered_unreviewed",
             "engine":"blender_workbench","source_take_id":"missing_take",
             "source_frames_id":"missing_frames"},
            dependencies=[])
        self.assertEqual(fake["revision"],1)
        with self.assertRaisesRegex(RuntimeError,"source lineage"):
            self.pipeline.reopen(self.pid,"video_forged")
        with self.assertRaises(KeyError):
            self.pipeline.reopen(self.other,"video_forged")
        with self.assertRaises(KeyError):
            self.pipeline.reopen(self.pid,"does_not_exist")

    def test_fail_closed_when_ffmpeg_probe_disagrees(self):
        with patch("backend.nvp_full_motion._run",
                   return_value=type("Result",(),{"stdout":'{"streams":[{"codec_name":"h264","width":160,"height":90,"nb_read_frames":"12","r_frame_rate":"30/1","pix_fmt":"yuv420p"}]}'})()):
            with self.assertRaisesRegex(RuntimeError,"mismatch"):
                _probe_video(self.root/"film.mp4","ffprobe",
                    {"fps":24,"width":160,"height":90,"frames":12})
        with patch("backend.nvp_full_motion._run",
                   return_value=type("Result",(),{"stdout":"{}"})()):
            with self.assertRaisesRegex(RuntimeError,"incomplete"):
                _probe_video(self.root/"film.mp4","ffprobe",
                    {"fps":24,"width":160,"height":90,"frames":12})

if __name__=="__main__":
    unittest.main()
