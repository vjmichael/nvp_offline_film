"""Data-first cinema/HDR gate never confuses an EXR/PNG with an SMPTE DCP."""
from __future__ import annotations
from pathlib import Path
import json
import tempfile
import unittest

import test_nvp_final_2d_native as fixture
from backend.nvp_native_cinema_master_gate import (
    assess_unmastered_source_package,FORMAT)


class NativeCinemaReadinessTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDataFirstOutputTests.setUp(self)
        self.take_sha=fixture.NativeDataFirstOutputTests.create(self)
        self.result=self.exporter.export(
            self.pid,"OutputTake",self.take_sha,
            "CinemaReadiness",self.out,
            listener_path="/World/ListenerLeft",fps_num=24,fps_den=1)
        self.folder=Path(self.result["directory"])

    def test_real_source_integrity_verified_without_fake_dcp_claim(self):
        grade=assess_unmastered_source_package(
            self.folder,target="SMPTE_2K_FLAT_24",
            expected_take_sha256=self.take_sha)
        self.assertEqual(grade["format"],FORMAT)
        self.assertEqual(grade["status"],"NO_CINEMA_OR_HDR_MASTER_AUTHORIZED")
        self.assertTrue(grade["source_integrity_verified"])
        self.assertFalse(grade["dcp_delivered"])
        self.assertFalse(grade["projector_ingest_certified"])
        self.assertFalse(grade["ffmpeg_used"])
        self.assertEqual(grade["original_derived_image_count"],24)
        self.assertIn("native_SMPTE_2K_XYZ_12bit_JPEG2000_encoder",
                      grade["required_master_color_and_delivery_capabilities"])
        self.assertIn("source_48k_stereo_PCM16_is_not_24bit_master_sound",
                      grade["required_master_color_and_delivery_capabilities"])
        self.assertEqual(grade["source_picture_raster"],[8,8])
        self.assertEqual(self.index.read_revision(
            self.pid,"OutputTake",1)["document_sha256"],self.take_sha)

    def test_HDR_preflight_keeps_PQ_Rec2020_calibration_open(self):
        check=assess_unmastered_source_package(
            self.folder,target="HDR10_REC2100_PQ")
        self.assertFalse(check["hdr10_master_approved"])
        self.assertIn("reference_colorimeter_HDR_PQ_and_Rec2020_measurements",
                      check["required_master_color_and_delivery_capabilities"])
        self.assertNotIn("native_SMPTE_2K_XYZ_12bit_JPEG2000_encoder",
                         check["required_master_color_and_delivery_capabilities"])

    def test_tampered_original_derived_picture_and_audio_refused(self):
        original=self.folder/"pictures"/"0000001.png"
        source=original.read_bytes()
        try:
            original.write_bytes(source+b"unapproved-cinema-overlay")
            with self.assertRaises(RuntimeError):
                assess_unmastered_source_package(self.folder)
        finally:original.write_bytes(source)
        audio=self.folder/"soundtrack.wav"
        data=audio.read_bytes()
        try:
            audio.write_bytes(data+b"modified")
            with self.assertRaises(RuntimeError):
                assess_unmastered_source_package(self.folder)
        finally:audio.write_bytes(data)
        with self.assertRaises(RuntimeError):
            assess_unmastered_source_package(
                self.folder,expected_take_sha256="f"*64)

    def test_manifest_cannot_invent_exr_color_profile_or_delivery(self):
        manifest=self.folder/"manifest.json"
        old=manifest.read_text()
        try:
            doc=json.loads(old)
            doc["format"]="nvp.final_2d.acescg_exr_sequence_pcm.v1"
            doc["picture_format"]="exr"
            manifest.write_text(json.dumps(doc))
            with self.assertRaises(RuntimeError):
                assess_unmastered_source_package(self.folder)
        finally:manifest.write_text(old)


if __name__=="__main__":
    unittest.main()
