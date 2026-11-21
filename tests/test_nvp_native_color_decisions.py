"""DA-06 native non-destructive Take-linked color decisions, no old frame codecs."""
import unittest

import test_nvp_data_av_native as fixture
from backend.nvp_native_color_decisions import NativeColorDecisions

DEFAULTS={"exposure_stops":.3,"contrast":1.1,"saturation":.9,
          "temperature_kelvin":5600,"tint_magenta_green":0.}

class NativeTakeColorTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.engine=NativeColorDecisions(self.index)

    def test_color_version_is_source_bound_and_does_not_create_frames(self):
        a=self.engine.publish(
            self.pid,"Color001",take_id="frozen_audio_take",
            take_sha256=self.sha,parameters=DEFAULTS)
        self.assertEqual(a["revision"],1)
        self.assertFalse(a["source_modified"])
        self.assertFalse(a["rendered_frames"])
        self.assertFalse(a["flat_master_approved"])
        revised={**DEFAULTS,"exposure_stops":1.25}
        b=self.engine.publish(
            self.pid,"Color001",take_id="frozen_audio_take",
            take_sha256=self.sha,parameters=revised,expected_revision=1)
        self.assertEqual(b["revision"],2)
        self.assertNotEqual(a["document_sha256"],b["document_sha256"])
        self.assertEqual(self.engine.read(
            self.pid,"Color001",1)["parameters"],DEFAULTS)
        self.assertEqual(self.engine.read(
            self.pid,"Color001")["parameters"],revised)
        self.assertEqual(self.index.read_revision(
            self.pid,"frozen_audio_take",1)["document_sha256"],self.sha)
        with self.assertRaises(Exception):
            self.engine.publish(
                self.pid,"Color001",take_id="frozen_audio_take",
                take_sha256=self.sha,parameters=revised,expected_revision=1)

    def test_grade_rejects_forged_take_and_invalid_values(self):
        with self.assertRaises(RuntimeError):
            self.engine.publish(
                self.pid,"InvalidTake",take_id="frozen_audio_take",
                take_sha256="f"*64,parameters=DEFAULTS)
        with self.assertRaises(ValueError):
            self.engine.publish(
                self.pid,"InvalidParams",take_id="frozen_audio_take",
                take_sha256=self.sha,parameters={
                    **DEFAULTS,"contrast":float("nan")})
        with self.assertRaises(ValueError):
            self.engine.publish(
                self.pid,"InvalidParams",take_id="frozen_audio_take",
                take_sha256=self.sha,parameters={
                    **DEFAULTS,"target_frame":24})


if __name__=="__main__":
    unittest.main()
