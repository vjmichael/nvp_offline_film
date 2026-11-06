"""B10 production-resolution admission and genuine ACEScg/OpenColorIO conversion.

Synthetic unit images are used to test mathematical/color contracts; they
are NOT presented as evidence that Blender rendered a real movie. The real
1920x1080 native Blender/OCIO fixture is a separate CI acceptance.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_b10_render_profiles import profile_for,validate_full_render


class RenderProfileContracts(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_measured_profiles_include_1080p_and_4k_with_bounded_frames(self):
        self.assertEqual(profile_for(160,90).max_chunk_frames,8)
        self.assertEqual(profile_for(1280,720).max_chunk_frames,2)
        self.assertEqual(profile_for(1920,1080).max_chunk_frames,1)
        uhd=profile_for(3840,2160)
        self.assertEqual(uhd.name,"UHD_4K")
        self.assertEqual(uhd.minimum_ram_mb,8192)
        self.assertEqual(uhd.estimated_rgba_f32_frame_bytes,3840*2160*16)

    def test_wrong_dimensions_budgets_and_batches_fail_closed(self):
        for dims in ((0,90),(1921,1080),(3841,2160),(1280,721),
                     (True,90),(1920,True)):
            with self.subTest(dims=dims):
                with self.assertRaises(ValueError):
                    profile_for(*dims)
        for options in (
            (1920,1080,2,4096,120),
            (1280,720,3,4096,120),
            (160,90,8,512,120),
            (1920,1080,1,True,120)
        ):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    validate_full_render(*options,
                        worker_root=self.root,archive_root=self.root)

    def test_4k_is_explicitly_blocked_without_measured_gpu_vram_admission(self):
        # A zero-GPU-budget Workbench task cannot claim safe 4K VRAM use.
        with self.assertRaisesRegex(RuntimeError,"GPU VRAM admission"):
            validate_full_render(3840,2160,1,8192,120,
                                 worker_root=self.root,archive_root=self.root)

    def test_disk_capacity_must_cover_full_sequence_not_just_first_frame(self):
        result=validate_full_render(1920,1080,1,4096,120,
                                    worker_root=self.root,archive_root=self.root)
        self.assertEqual(result["profile"],"full_HD")
        expected=2*120*1920*1080*16+1024**3
        self.assertEqual(result["required_available_disk_bytes"],expected)
        import shutil
        sample=shutil.disk_usage(self.root)
        insufficient=type(sample)(sample.total,sample.used,expected-1)
        with patch("backend.nvp_b10_render_profiles.shutil.disk_usage",
                   return_value=insufficient):
            with self.assertRaisesRegex(RuntimeError,"disk"):
                validate_full_render(1920,1080,1,4096,120,
                                     worker_root=self.root,archive_root=self.root)

    def test_exr_b9_script_high_resolution_guard_is_conservative(self):
        from backend.nvp_exr_scripts import EXR_RENDER_SCRIPT
        self.assertIn("3840",EXR_RENDER_SCRIPT)
        self.assertIn("2160",EXR_RENDER_SCRIPT)
        self.assertIn("height%2",EXR_RENDER_SCRIPT)


class NativeOCIOColorContracts(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
            import OpenEXR
            import Imath
            import PyOpenColorIO
        except ImportError as exc:
            self.fail("B10 CI must provide real official OCIO and OpenEXR: "+str(exc))
        self.np=np
        self.openexr=OpenEXR
        self.imath=Imath
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.src=self.root/"source_linear.exr"
        self.dst=self.root/"acescg.exr"
        h,w=64,96
        channels={}
        x=np.linspace(.02,.8,w*h,dtype=np.float32)
        for c,pixel in (("R",x),("G",x*.65+.08),("B",x*.27+.04),
                        ("A",np.ones_like(x))):
            channels[c]=pixel.tobytes()
        header=OpenEXR.Header(w,h)
        header["channels"]={k:Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT))
                            for k in channels}
        writer=OpenEXR.OutputFile(str(self.src),header)
        try:
            writer.writePixels(channels)
        finally:
            writer.close()
        self.width=w
        self.height=h

    def tearDown(self):
        self.temp.cleanup()

    def test_official_versioned_aces2_config_fingerprint_is_stable(self):
        from backend.nvp_b10_ocio import load_verified_config,CONFIG_URI
        ocio,config,identity=load_verified_config()
        self.assertEqual(identity["config_uri"],CONFIG_URI)
        self.assertEqual(identity["target_space"],"ACEScg")
        self.assertEqual(len(identity["config_serialized_sha256"]),64)
        self.assertEqual(identity["library_version"].split(".")[:2],["2","5"])
        self.assertTrue(identity["source_space"])
        self.assertIsNotNone(config.getColorSpace(identity["source_space"]))

    def test_real_float32_acescg_conversion_and_independent_pixel_processor(self):
        from backend.nvp_b10_ocio import convert_linear_rec709_to_acescg,_sha,load_verified_config
        from backend.nvp_b10_color_verify import verify_acescg_frame
        ident=load_verified_config()[2]
        written=convert_linear_rec709_to_acescg(
            self.src,self.dst,width=self.width,height=self.height,
            expected_sha256=_sha(self.src),
            required_config_sha256=ident["config_serialized_sha256"])
        self.assertEqual(written["working_space"],"ACEScg")
        self.assertTrue(written["aces2_working_space_converted"])
        self.assertTrue(self.dst.exists())
        independent=verify_acescg_frame(
            self.src,self.dst,written,width=self.width,height=self.height)
        self.assertTrue(independent["verified"])
        self.assertGreaterEqual(independent["sampled_pixels"],8)
        self.assertTrue(independent["alpha_preserved"])
        self.assertTrue(independent["acescg_chromaticities_verified"])
        self.assertLess(independent["max_spot_color_error"],.002)
        with self.assertRaisesRegex(RuntimeError,"overwrite"):
            convert_linear_rec709_to_acescg(
                self.src,self.dst,width=self.width,height=self.height,
                expected_sha256=_sha(self.src))

    def test_wrong_config_or_source_hash_never_creates_acescg_file(self):
        from backend.nvp_b10_ocio import convert_linear_rec709_to_acescg,_sha
        with self.assertRaisesRegex(RuntimeError,"config"):
            convert_linear_rec709_to_acescg(
                self.src,self.dst,width=self.width,height=self.height,
                expected_sha256=_sha(self.src),
                required_config_sha256="0"*64)
        self.assertFalse(self.dst.exists())
        with self.assertRaisesRegex(RuntimeError,"changed"):
            convert_linear_rec709_to_acescg(
                self.src,self.dst,width=self.width,height=self.height,
                expected_sha256="1"*64)
        self.assertFalse(self.dst.exists())

    def test_non_color_patched_metadata_or_changed_pixel_bytes_refuses(self):
        from backend.nvp_b10_ocio import convert_linear_rec709_to_acescg,_sha
        from backend.nvp_b10_color_verify import verify_acescg_frame
        original=convert_linear_rec709_to_acescg(
            self.src,self.dst,width=self.width,height=self.height,
            expected_sha256=_sha(self.src))
        with self.assertRaises(RuntimeError):
            verify_acescg_frame(
                self.src,self.dst,{**original,"source_space":"unverified"},
                width=self.width,height=self.height)
        with self.dst.open("ab") as fd:
            fd.write(b"fake extra bytes")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            verify_acescg_frame(
                self.src,self.dst,original,width=self.width,height=self.height)


if __name__=="__main__":
    unittest.main()
