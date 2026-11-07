"""DA-06C: real native OCIO processor + 16-bit PNG. No FFmpeg or fake view LUT.

Synthetic linear input verifies independent color kernel only. A calibrated
renderer, real display, HDR and a final cinema master need separate gates.
"""
import hashlib
from io import BytesIO
import struct
import unittest

import numpy as np
from PIL import Image
import test_nvp_data_av_native as fixture

from backend.nvp_native_aces_color import (
    NativeACESColor,policy,png16_rgb,FORMAT)
from backend.nvp_native_color_decisions import NativeColorDecisions

DEFAULT={"exposure_stops":0.2,"contrast":1.05,"saturation":1.1,
         "temperature_kelvin":6500.,"tint_magenta_green":0.}


class OCIONativeDataFirstTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.grade=NativeColorDecisions(self.index).publish(
            self.pid,"OCIOColor001",take_id="frozen_audio_take",
            take_sha256=self.sha,parameters=DEFAULT)
        self.policy,_=policy()
        self.encoder=NativeACESColor(self.index)
        self.linear=np.full((8,8,4),0.1,dtype=np.float32)
        self.linear[:,:,3]=1.0

    def test_true_aces2_native_processor_and_png16_preserve_original(self):
        before=self.linear.tobytes()
        png,receipt=self.encoder.process_scene_linear(
            self.pid,"frozen_audio_take",self.sha,
            "OCIOColor001",1,self.grade["document_sha256"],
            self.linear,
            expected_config_sha256=self.policy["configuration_sha256"])
        self.assertEqual(receipt["format"],FORMAT)
        self.assertFalse(receipt["ffmpeg_used"])
        self.assertFalse(receipt["original_modified"])
        self.assertFalse(receipt["cinema_master_approved"])
        self.assertEqual(receipt["png16_sha256"],hashlib.sha256(png).hexdigest())
        self.assertEqual(png[:8],b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png[24:26],bytes((16,2)))
        self.assertEqual(self.linear.tobytes(),before)
        self.assertEqual(self.index.read_revision(
            self.pid,"frozen_audio_take",1)["document_sha256"],self.sha)
        with Image.open(BytesIO(png)) as im:
            self.assertEqual(im.size,(8,8))

    def test_config_source_and_bitdepth_fail_closed(self):
        with self.assertRaises(RuntimeError):
            self.encoder.process_scene_linear(
                self.pid,"frozen_audio_take",self.sha,
                "OCIOColor001",1,self.grade["document_sha256"],
                self.linear,expected_config_sha256="f"*64)
        with self.assertRaises(ValueError):
            self.encoder.process_scene_linear(
                self.pid,"frozen_audio_take",self.sha,
                "OCIOColor001",1,self.grade["document_sha256"],
                self.linear.astype(np.float64),
                expected_config_sha256=self.policy["configuration_sha256"])
        with self.assertRaises(RuntimeError):
            self.encoder.process_scene_linear(
                self.pid,"frozen_audio_take",self.sha,
                "OCIOColor001",1,"f"*64,
                self.linear,expected_config_sha256=
                    self.policy["configuration_sha256"])

    def test_independent_native_rgb16_png_encoding_is_deterministic(self):
        data=np.arange(24,dtype=np.uint16).reshape(2,4,3)
        first=png16_rgb(data)
        self.assertEqual(first,png16_rgb(data))
        self.assertEqual(first[24],16)
        self.assertEqual(first[25],2)
        self.assertEqual(struct.unpack_from(">II",first,16),(4,2))


if __name__=="__main__":
    unittest.main()
