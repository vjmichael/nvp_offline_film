"""COLOR-01B: pinned ACES 2 view transforms, 16bit output, refusal paths."""
from __future__ import annotations
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_color_ocio import (
    _config, _deps, color_policy, _encode_png16,
    apply_view, ColorReviewPipeline, OCIO_VERSION, CONFIG_NAME,
    SOURCE_COLOR_SPACE, OUTPUT_DISPLAY, OUTPUT_VIEW,
)
from backend.nvp_studio import Studio


class ColorOCIOTests(unittest.TestCase):
    def test_pinned_config_library_and_aces_display_view_exist(self):
        ocio,cfg=_config()
        policy,cpu=color_policy()
        self.assertEqual(ocio.GetVersion(), OCIO_VERSION)
        self.assertEqual(policy["config"],CONFIG_NAME)
        self.assertEqual(policy["source_space"],SOURCE_COLOR_SPACE)
        self.assertEqual(policy["display"],OUTPUT_DISPLAY)
        self.assertEqual(policy["view"],OUTPUT_VIEW)
        self.assertEqual(policy["intent"],"sdr_color_managed_review_not_final_graded_master")
        self.assertEqual(len(policy["config_sha256"]),64)
        self.assertEqual(len(policy["processor_cache_id"])>0,True)

    def test_aces_view_differs_from_linear_identity_and_handles_hdr(self):
        _,np=_deps()
        policy,cpu=color_policy()
        pixels=np.array([[
            [0.18,0.18,0.18,1.0],
            [2.25,0.37,0.059,1.0],
            [0.02,0.08,0.14,1.0],
            [0.9,0.8,0.7,1.0],
        ]],dtype=np.float32)
        quant,stats=apply_view(pixels,cpu)
        self.assertEqual(quant.dtype,np.dtype("<u2"))
        self.assertEqual(quant.shape,(1,4,3))
        # A legal display rendering of scene-linear 18% is neither zero
        # nor the 18% numeric code value on each output channel.
        self.assertTrue((quant[0,0]>0).all())
        self.assertFalse(np.array_equal(quant[0,0],[11796]*3))
        self.assertEqual(stats["pixels"],4)
        self.assertTrue(np.isfinite(quant).all())
        self.assertEqual(float(pixels[0,1,0]),float(np.float32(2.25)))
        self.assertGreater(int(quant[0,1,0]), int(quant[0,0,0]))

    def test_png16_roundtrip_exact(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("FFmpeg required for native 16-bit PNG roundtrip")
        _,np=_deps()
        values=np.array([
            [[0,65535,10001],[23456,34567,45678]],
            [[55555,100,4096],[1,32768,50000]],
        ],dtype="<u2")
        with tempfile.TemporaryDirectory() as d:
            receipt=_encode_png16(values,Path(d)/"graded.png",shutil.which("ffmpeg"))
            self.assertEqual(receipt["bit_depth"],16)
            self.assertTrue(receipt["full_decode_exact"])
            self.assertGreater(receipt["size_bytes"],50)
            with self.assertRaisesRegex(RuntimeError,"already exists"):
                _encode_png16(values,Path(d)/"graded.png",shutil.which("ffmpeg"))

    def test_refuse_alpha_change_nan_and_excessive_clipping(self):
        _,np=_deps()
        pixels=np.ones((1,2,4),dtype=np.float32)*0.18
        pixels[:,:,3]=1
        class WrongAlpha:
            def applyRGBA(self,buffer):
                buffer[...,3]=0.9
        with self.assertRaisesRegex(RuntimeError,"alpha"):
            apply_view(pixels,WrongAlpha())
        class OutOfRange:
            def applyRGBA(self,buffer):
                buffer[...,:3]=-100
        with self.assertRaisesRegex(RuntimeError,"clip too many"):
            apply_view(pixels,OutOfRange())
        pixels[0,0,0]=float("nan")
        with self.assertRaisesRegex(RuntimeError,"NaN/Infinity"):
            apply_view(pixels,OutOfRange())
        pixels[0,0,0]=0.18
        pixels[0,0,3]=0.5
        with self.assertRaisesRegex(RuntimeError,"transparent"):
            apply_view(pixels,OutOfRange())

    def test_unapproved_source_space_and_forged_review_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            studio=Studio(Path(d)/"film.sqlite3")
            pid=studio.create_project("Color test","")["id"]
            pipe=ColorReviewPipeline(studio)
            with self.assertRaisesRegex(RuntimeError,"explicitly confirm"):
                pipe.render(pid,"source_exr","graded_1",Path(d)/"output")
            with self.assertRaisesRegex(RuntimeError,"explicitly confirm"):
                pipe.render(pid,"source_exr","graded_1",Path(d)/"output",
                            assumed_source_space="ACEScg",
                            director_source_space_approval=True)
            self.assertFalse((Path(d)/"output").exists())
            with self.assertRaises(KeyError):
                pipe.reopen(pid,"never_exists")


if __name__=="__main__":
    unittest.main()
