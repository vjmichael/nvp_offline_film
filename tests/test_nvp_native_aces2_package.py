"""DA-06E: real USD-derived creator-approved ACES RGB16 picture + PCM package.

Unlike the original 8-bit legacy raster, every picture in this original
Digital Take projection is source-evaluated as FLOAT32, converted by the
pinned real OCIO ACES2 SDR processor and preserved as 16-bit PNG.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave

import test_nvp_source_linear_aces_scene as scene_fixture

from backend.nvp_final_2d_native import Approved2DPackage
from backend.nvp_native_cpu_raster import NativeSourceRaster
from backend.nvp_native_avi_delivery import deliver_avi


class RealSourceColorPackageTests(unittest.TestCase):
    def setUp(self):
        scene_fixture.NativeSourceLinearACESAcceptance.setUp(self)
        output=tempfile.TemporaryDirectory(prefix="nvp-approved-aces2-")
        self.addCleanup(output.cleanup)
        self.output=Path(output.name)
        self.grants=[]
        self.allowed=True
        self.packager=Approved2DPackage(
            self.index,native_creator_approval=lambda scope:
                self.grants.append(scope) is None and self.allowed,
            render_png=NativeSourceRaster(self.index,self.pid).render_png)
        self.pins={
            "grade_id":"SourceColor001",
            "revision":1,
            "document_sha256":self.grade["document_sha256"],
            "config_sha256":self.policy["configuration_sha256"],
        }

    def test_native_pinned_aces2_rgb16_and_sound_remain_derived_only(self):
        original=self.index.read_revision(
            self.pid,"SourceColorTake",1)["document_sha256"]
        result=self.packager.export(
            self.pid,"SourceColorTake",original,
            "ACESPresentation001",self.output,
            listener_path="/World/Camera",fps_num=24,fps_den=1,
            aces_color_grade=self.pins)
        self.assertEqual(result["status"],"DERIVED_2D_PACKAGE")
        self.assertEqual(result["pixel_bit_depth"],16)
        self.assertEqual(result["color_pipeline"],
                         "ocio_aces2_scene_linear_png16_unmastered")
        self.assertFalse(result["single_file_master"])
        self.assertFalse(result["ffmpeg_used"])
        folder=Path(result["directory"])
        manifest=json.loads((folder/"manifest.json").read_text())
        self.assertEqual(manifest["original_take_sha256"],original)
        self.assertEqual(manifest["pixel_bit_depth"],16)
        self.assertEqual(manifest["aces_color_grade"]["document_sha256"],
                         self.grade["document_sha256"])
        self.assertEqual(manifest["aces_color_grade"]["config_sha256"],
                         self.policy["configuration_sha256"])
        self.assertEqual(manifest["output_picture_count"],24)
        self.assertEqual(len(manifest["aces_source_receipts"]),24)
        self.assertFalse(manifest["derived_scene_linear_aces_audit"][
            "cinema_master_approved"])
        picture=folder/"pictures"/"0000001.png"
        buf=picture.read_bytes()
        self.assertEqual(buf[24:26],bytes((16,2)))
        self.assertEqual(hashlib.sha256(buf).hexdigest(),
                         manifest["pictures"][0]["sha256"])
        self.assertEqual(manifest["pictures"][0]["pixel_bit_depth"],16)
        self.assertEqual(manifest["audio_samples"],48000)
        with wave.open(str(folder/"soundtrack.wav"),"rb") as audio:
            self.assertEqual(audio.getnchannels(),2)
            self.assertEqual(audio.getnframes(),48000)
        self.assertEqual(self.index.read_revision(
            self.pid,"SourceColorTake",1)["document_sha256"],original)
        self.assertEqual(self.grants[0]["aces_config_sha256"],
                         self.policy["configuration_sha256"])
        self.assertTrue(self.grants[0]["original_data_immutable"])
        with self.assertRaises(RuntimeError):
            deliver_avi(
                folder,self.output/"forbidden-8bit-downconvert.avi",
                expected_take_sha256=original,
                approve_delivery=lambda _:True)
        self.assertFalse((self.output/"forbidden-8bit-downconvert.avi").exists())

    def test_denied_config_or_duplicate_package_never_creates_a_master(self):
        original=self.take["document_sha256"]
        self.allowed=False
        with self.assertRaises(PermissionError):
            self.packager.export(
                self.pid,"SourceColorTake",original,
                "Declined",self.output,
                listener_path="/World/Camera",
                aces_color_grade=self.pins)
        self.assertEqual(list(self.output.iterdir()),[])
        with self.assertRaises(RuntimeError):
            self.packager.export(
                self.pid,"SourceColorTake",original,
                "InvalidConfig",self.output,
                listener_path="/World/Camera",
                aces_color_grade={
                    **self.pins,"config_sha256":"f"*64})
        with self.assertRaises(ValueError):
            self.packager.export(
                self.pid,"SourceColorTake",original,
                "DoubleGrade",self.output,
                listener_path="/World/Camera",
                color_grade={
                    "grade_id":"SourceColor001",
                    "revision":1,
                    "document_sha256":self.grade["document_sha256"],
                },aces_color_grade=self.pins)
        self.assertEqual(list(self.output.iterdir()),[])


if __name__=="__main__":
    unittest.main()
