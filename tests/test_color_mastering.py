"""COLOR-01B2: real codec, mastering metadata, grading recipe and refusal tests."""
from __future__ import annotations
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from backend.nvp_color_mastering import (
    grade_recipe,validate_grade,grade_pixels,view_to_rgb48,PROFILES,
    _yuv_reference,encode_mov,video_audit,ColorMasteringPipeline,
)
from backend.nvp_studio import Studio


class GradeContractTests(unittest.TestCase):
    def test_typed_neutral_bounded_recipe_and_forgery(self):
        grade=grade_recipe()
        self.assertEqual(grade["exposure_stops"],0.)
        self.assertEqual(grade["saturation"],1.)
        self.assertEqual(validate_grade(grade),grade)
        for change in ({"exposure_stops":-5},{"exposure_stops":float("nan")},
                       {"contrast":0.01},{"saturation":2.1},{"red_gain":1.7},
                       {"blue_gain":True},{"color_temperature_kelvin":1800}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                grade_recipe(**change)
        altered=dict(grade);altered["unknown"]="approval"
        with self.assertRaisesRegex(RuntimeError,"[Ff]orged"):
            validate_grade(altered)
        forged=dict(grade);forged["exposure_stops"]=10.
        with self.assertRaisesRegex(RuntimeError,"[Ff]orged"):
            validate_grade(forged)

    def test_linear_grade_non_destructive_exposure_and_saturation(self):
        source=np.array([[[.10,.15,.3,1],[.6,.5,.4,1]]],dtype=np.float32)
        with patch("backend.nvp_color_mastering._deps",return_value=(None,np)):
            neutral=grade_pixels(source,grade_recipe())
            exposed=grade_pixels(source,grade_recipe(exposure_stops=1.))
            gray=grade_pixels(source,grade_recipe(saturation=0.))
        np.testing.assert_allclose(neutral,source,atol=2e-7)
        np.testing.assert_allclose(exposed[...,:3],source[...,:3]*2,atol=2e-7)
        np.testing.assert_allclose(gray[...,0],gray[...,1],atol=2e-7)
        np.testing.assert_allclose(source[0,0],[.1,.15,.3,1],atol=2e-7)

    def test_alpha_change_and_excessive_clip_refused(self):
        class Identity:
            def applyRGB(self,a):pass
        class BreakRGB:
            def applyRGB(self,a):a[:]=float("nan")
        pixel=np.array([[[.5,.3,.2,1.]]],dtype=np.float32)
        with patch("backend.nvp_color_mastering._deps",return_value=(None,np)):
            raw,stats=view_to_rgb48(pixel,Identity())
            self.assertEqual(len(raw),6)
            self.assertEqual(stats["clipped_channels"],0)
            transparent=pixel.copy();transparent[...,3]=.5
            with self.assertRaisesRegex(RuntimeError,"opaque"):
                view_to_rgb48(transparent,Identity())
            with self.assertRaisesRegex(RuntimeError,"nonfinite"):
                view_to_rgb48(pixel,BreakRGB())
            np.testing.assert_allclose(pixel,np.array([[[.5,.3,.2,1.]]],dtype=np.float32))
            clip=pixel.copy();clip[...,0]=10.
            with self.assertRaisesRegex(RuntimeError,"clip too many"):
                view_to_rgb48(clip,Identity())
            nan=pixel.copy();nan[...,0]=float("nan")
            with self.assertRaisesRegex(RuntimeError,"nonfinite"):
                view_to_rgb48(nan,Identity())

    def test_unapproved_primaries_and_unknown_codec_refuse_prepublication(self):
        with tempfile.TemporaryDirectory() as d:
            studio=Studio(Path(d)/"film.sqlite3")
            pid=studio.create_project("COLOR-01B2","")["id"]
            pipe=ColorMasteringPipeline(studio)
            with self.assertRaisesRegex(RuntimeError,"declare the source"):
                pipe.encode(pid,"missing","master",Path(d)/"masters")
            with self.assertRaises(ValueError):
                pipe.encode(pid,"missing","master",Path(d)/"masters",
                    output_profile="fake_codec",source_primaries_declared=True)
            self.assertFalse((Path(d)/"masters").exists())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"Native FFmpeg required")
class ActualCodecAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.width=256;self.height=144;self.frames=4
        self.raw=self.root/"test.rgb48"
        y=np.linspace(.12,.68,self.height,dtype=np.float32)[:,None]
        x=np.linspace(.08,.82,self.width,dtype=np.float32)[None,:]
        with self.raw.open("wb") as f:
            for k in range(self.frames):
                a=np.stack([np.broadcast_to(x,(self.height,self.width)),
                    np.broadcast_to(y,(self.height,self.width)),
                    np.full((self.height,self.width),.2+k*.02,dtype=np.float32)],axis=2)
                f.write(np.rint(a*65535).astype("<u2").tobytes())
        self.ref=self.root/"ref.yuv"
        _yuv_reference(self.raw,self.ref,width=self.width,height=self.height,
                       frames=self.frames,ffmpeg=shutil.which("ffmpeg"))

    def tearDown(self):self.temp.cleanup()

    def test_two_real_tagged_10bit_codecs_decode_and_match_reference(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                mov=self.root/(profile+".mov")
                encode_mov(self.raw,mov,profile,width=self.width,height=self.height,
                           frames=self.frames,ffmpeg=shutil.which("ffmpeg"))
                with patch("backend.nvp_color_mastering._deps",return_value=(None,np)):
                    audit=video_audit(mov,profile=profile,width=self.width,
                        height=self.height,frames=self.frames,ffmpeg="ffmpeg",
                        ffprobe="ffprobe",reference_yuv=self.ref)
                self.assertEqual(audit["decoded"]["illegal_samples"],0)
                self.assertEqual(audit["metadata"]["color_transfer"],"bt709")
                self.assertEqual(audit["metadata"]["color_primaries"],"bt709")
                self.assertEqual(audit["decoded"]["reference_comparison"],
                                 "passed_bounded_lossy_10bit_yuv")
                self.assertLess(audit["decoded"]["p99_error_codes"],32)

    def test_mismatched_codec_and_frame_count_refused(self):
        mov=self.root/"prores.mov"
        encode_mov(self.raw,mov,"prores_422_hq_mov",width=self.width,
                   height=self.height,frames=self.frames,ffmpeg="ffmpeg")
        with patch("backend.nvp_color_mastering._deps",return_value=(None,np)):
            with self.assertRaisesRegex(RuntimeError,"codec_name"):
                video_audit(mov,profile="dnxhr_hqx_mov",width=self.width,
                    height=self.height,frames=self.frames,ffmpeg="ffmpeg",ffprobe="ffprobe")
            with self.assertRaisesRegex(RuntimeError,"extra picture frames"):
                video_audit(mov,profile="prores_422_hq_mov",width=self.width,
                    height=self.height,frames=self.frames+1,ffmpeg="ffmpeg",ffprobe="ffprobe")


if __name__=="__main__":
    unittest.main()
