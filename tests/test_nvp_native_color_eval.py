"""DA-06B: exact source-bound grade affects only derived presentation."""
import hashlib
import json
from io import BytesIO
from PIL import Image
from pathlib import Path
import unittest

from backend.nvp_native_color_decisions import NativeColorDecisions
from backend.nvp_native_color_eval import apply_display_grade
from test_nvp_final_2d_native import NativeDataFirstOutputTests,png

NEUTRAL={"exposure_stops":0.,"contrast":1.,"saturation":1.,
         "temperature_kelvin":6500.,"tint_magenta_green":0.}


class NativeColorEvaluationTests(unittest.TestCase):
    def test_display_grade_changes_derived_pixels_without_mutating_bytes(self):
        original=png(25,56,92)
        changed=apply_display_grade(original,{
            **NEUTRAL,"exposure_stops":1.0})
        self.assertNotEqual(original,changed)
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         hashlib.sha256(png(25,56,92)).hexdigest())
        with self.assertRaises(ValueError):
            apply_display_grade(original,{
                **NEUTRAL,"exposure_stops":float("nan")})

    def test_srgb_exposure_is_linear_light_and_clipping_is_audited(self):
        # +1 stop on middle gray is about sRGB 175, not byte-level 255.
        neutral={**NEUTRAL,"exposure_stops":1.0}
        graded,audit=apply_display_grade(
            png(128,128,128),neutral,return_audit=True)
        with Image.open(BytesIO(graded)) as image:
            result=image.getpixel((0,0))
            self.assertTrue(all(168<=channel<=185 for channel in result))
        self.assertEqual(audit["channels_clipped"],0)
        self.assertFalse(audit["aces2_output"])
        self.assertFalse(audit["real_scene_linear_renderer"])
        blown,audit2=apply_display_grade(
            png(240,240,240),neutral,return_audit=True)
        self.assertGreater(audit2["channels_clipped"],0)
        self.assertFalse(audit2["hdr_master"])

    def test_pinned_color_plan_preserves_original_take_and_full_history(self):
        fx=NativeDataFirstOutputTests(
            "test_denied_export_never_creates_derived_or_mutates_take")
        fx.setUp()
        self.addCleanup(fx.doCleanups)
        sha=fx.create()
        grade=NativeColorDecisions(fx.index).publish(
            fx.pid,"ColorForMovie",
            take_id="OutputTake",take_sha256=sha,
            parameters={**NEUTRAL,"exposure_stops":1.1})
        original=fx.exporter.export(
            fx.pid,"OutputTake",sha,"Plain",fx.out,
            listener_path="/World/ListenerLeft")
        variant=fx.exporter.export(
            fx.pid,"OutputTake",sha,"Graded",fx.out,
            listener_path="/World/ListenerLeft",
            color_grade={"grade_id":"ColorForMovie",
                         "revision":grade["revision"],
                         "document_sha256":grade["document_sha256"]})
        before=Path(original["directory"])/"pictures"/"0000001.png"
        after=Path(variant["directory"])/"pictures"/"0000001.png"
        self.assertNotEqual(before.read_bytes(),after.read_bytes())
        doc=json.loads(
            (Path(variant["directory"])/"manifest.json").read_text())
        self.assertEqual(doc["color_grade"]["document_sha256"],
                         grade["document_sha256"])
        self.assertEqual(doc["original_take_sha256"],sha)
        self.assertEqual(fx.index.read_revision(
            fx.pid,"OutputTake",1)["document_sha256"],sha)
        with self.assertRaises(RuntimeError):
            fx.exporter.export(
                fx.pid,"OutputTake",sha,"BadGrade",fx.out,
                listener_path="/World/ListenerLeft",
                color_grade={"grade_id":"ColorForMovie",
                             "revision":grade["revision"],
                             "document_sha256":"f"*64})


if __name__=="__main__":
    unittest.main()
