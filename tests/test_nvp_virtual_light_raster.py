"""V-LIGHT: real OpenUSD pixel differences from digital gold/locked-sun FX.

A film cheat is only considered implemented after the CPU shader changes
genuine 3D pixels at the right original USD object path. Art direction
and photorealistic/DCI reference quality remain separately judged.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import numpy as np
from PIL import Image

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_virtual_light_fx import make_simple_virtual_fx
from backend.nvp_virtual_light_raster_adapter import evaluate_scene_virtual_lighting
from backend.nvp_wo6_07f_rendered_av import rendered_source_window
from tools.nvp_film01_original_30s import (
    write_original_30s_source,render_original_30s_review)


class RealDigitalCinematicLightPixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.root=Path(cls.temp.name).resolve()
        cls.project_root=cls.root/"actual_original_short"
        cls.source=write_original_30s_source(
            cls.project_root,approve_test_only=True)
        cls.studio=Studio(cls.project_root/"short.sqlite3")
        cls.index=FilmIndex(cls.studio)
        cls.pid=cls.source["project_id"]
        cls.gold=cls.source["virtual_artistic_lighting_sources"][1]
        cls.sun=cls.source["virtual_artistic_lighting_sources"][0]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _frame(self,effects,frame=480):
        return rendered_source_window(
            self.index,self.pid,
            self.source["edit_id"],1,self.source["edit_sha256"],
            frame,1,camera_path="/World/Camera",
            virtual_fx=effects)

    def _image(self,packet):
        raw=base64.b64decode(
            packet["images"][0]["frame_image_data_url"].split(",",1)[1])
        with Image.open(BytesIO(raw)) as img:
            img.load()
            return np.asarray(img,dtype=np.int16)

    def test_real_usd_engineer_gets_extra_warm_gold_fill_without_a_gold_reflector(self):
        raw=self._frame(None)
        warm=self._frame([self.gold])
        self.assertFalse(raw["images"][0]["virtual_fx_actually_applied_to_pixels"])
        self.assertTrue(warm["images"][0]["virtual_fx_actually_applied_to_pixels"])
        self.assertEqual(warm["images"][0]["virtual_fx_count"],1)
        self.assertNotEqual(
            raw["images"][0]["frame_png_sha256"],
            warm["images"][0]["frame_png_sha256"])
        self.assertEqual(
            raw["source_audio_wav_sha256"],warm["source_audio_wav_sha256"])
        old=self._image(raw)
        gold=self._image(warm)
        delta=gold-old
        self.assertGreater(np.count_nonzero(delta),10)
        self.assertGreater(int(np.sum(delta[:,:,0])),
                           int(np.sum(delta[:,:,2])))
        self.assertEqual(
            self.index.read_revision(self.pid,"RelayRekindleTake",1)[
                "document_sha256"],
            self.source["shots"][2]["take_sha256"])
        self.assertFalse(warm["film_delivered"])
        self.assertTrue(warm["virtual_light_not_necessarily_source_authorized"])
        self.assertTrue(warm["source_rasterizer_only_not_hydra"])

    def test_fixed_summer_sun_changes_pixels_without_moving_with_story_time(self):
        baseline=self._frame(None,480)
        with_sun=self._frame([self.sun],480)
        self.assertNotEqual(baseline["images"][0]["frame_png_sha256"],
                            with_sun["images"][0]["frame_png_sha256"])
        self.assertTrue(with_sun["images"][0]["virtual_fx_actually_applied_to_pixels"])
        self.assertEqual(with_sun["images"][0]["virtual_fx_count"],1)

    def test_invalid_virtual_target_unsynced_live_and_duplicates_refused(self):
        for invalid in (
            [{**self.gold,"target_path":"/World/UntrustedAbsentObject"}],
            [self.gold,self.gold],
            [{**self.gold,"clock_mode":"independent_live",
              "anchor_monotonic_ns":123456789}],
        ):
            with self.subTest(invalid=invalid),self.assertRaises(
                    (PermissionError,ValueError)):
                self._frame(invalid,480)

    def test_actual_six_original_frames_render_and_export_with_artist_light(self):
        out=self.root/"original-six-with-virtual-gold.zip"
        result=render_original_30s_review(
            self.project_root,out,max_frames=6,apply_virtual_fx=True)
        self.assertEqual(result["rendered_frame_count"],6)
        self.assertFalse(result["complete_720_frame_source_preview"])
        with ZipFile(out) as archive:
            receipt=json.loads(archive.read("original_30s_preview_receipt.json"))
            self.assertTrue(receipt["virtual_gold_and_sun_fx_applied_to_render"])
            self.assertEqual(len(receipt["frame_receipts"]),6)
            self.assertTrue(all(x["virtual_light_shader_used"]
                                for x in receipt["frame_receipts"]))
            self.assertFalse(receipt["dci_master_or_dcp_created"])


if __name__=="__main__":
    unittest.main()
