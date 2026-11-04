"""GRADE-UI-02A: deterministic post-view scopes, shot wheel bounds and lineage."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import unittest

import numpy as np

from backend.nvp_grade_advanced import (
    AdvancedGradeWorkspace, FORMAT, neutral_wheels, validate_wheels,
    make_plan, validate_plan, shot_manifest, apply_wheels, measure_scopes,
)
from backend.nvp_color_mastering import grade_recipe
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio


class ScopeMathTests(unittest.TestCase):
    def test_rgb_histogram_waveform_and_vectorscope_conserve_pixels(self):
        # 4 full-range 16-bit RGB pixels, no fabricated bitmap/DOM values.
        rgb=np.array([[[0,0,0],[65535,65535,65535]],
                      [[65535,0,0],[0,0,65535]]],dtype="<u2")
        raw=rgb.tobytes()
        result=measure_scopes(raw,2,2)
        self.assertEqual(result["format"],"nvp.scope.display_rgb48.v1")
        self.assertEqual(result["pixels"],4)
        self.assertEqual(result["rgb48_sha256"],hashlib.sha256(raw).hexdigest())
        for values in result["histogram"].values():
            self.assertEqual(len(values),64)
            self.assertEqual(sum(values),4)
        self.assertEqual(sum(map(sum,result["waveform"])),4)
        self.assertEqual(sum(map(sum,result["vectorscope"])),4)
        self.assertAlmostEqual(result["luma_min"],0)
        self.assertAlmostEqual(result["luma_max"],1)
        self.assertTrue(result["display_referred"])

    def test_scopes_reject_truncated_or_wrong_raster(self):
        with self.assertRaisesRegex(RuntimeError,"inconsistent"):
            measure_scopes(b"\x00"*17,2,2)
        with self.assertRaises(ValueError):
            measure_scopes(b"",0,1)

    def test_color_wheels_scene_linear_and_no_input_mutation(self):
        pixels=np.full((2,3,4),.18,dtype=np.float32)
        pixels[:,:,3]=1.
        original=pixels.copy()
        neutral=apply_wheels(pixels,neutral_wheels())
        self.assertTrue(np.allclose(neutral,pixels,atol=1e-6))
        self.assertTrue(np.array_equal(pixels,original))
        warmed=neutral_wheels()
        warmed["gain"]=[1.10,1.,.90]
        updated=apply_wheels(pixels,warmed)
        self.assertGreater(updated[0,0,0],neutral[0,0,0])
        self.assertLess(updated[0,0,2],neutral[0,0,2])
        self.assertTrue(np.array_equal(updated[:,:,3],pixels[:,:,3]))
        self.assertTrue(np.array_equal(pixels,original))

    def test_wheel_types_limits_and_injected_unknown_control_refused(self):
        for example in (
            {"format":"bad","lift":[0,0,0],"gamma":[1,1,1],"gain":[1,1,1]},
            {"format":"nvp.color.wheels.linear_lift_gamma_gain.v1",
             "lift":[0,0,0],"gamma":[0,1,1],"gain":[1,1,1]},
            {"format":"nvp.color.wheels.linear_lift_gamma_gain.v1",
             "lift":[0,0,0],"gamma":[1,1,1],"gain":[1,1,1],"fake":True},
        ):
            with self.subTest(value=example),self.assertRaises(ValueError):
                validate_wheels(example)
        with self.assertRaises(ValueError):
            make_plan(shots={"../unsafe":neutral_wheels()})
        plan=make_plan(grade_recipe(),{"shot_A":neutral_wheels()})
        with self.assertRaisesRegex(RuntimeError,"absent"):
            validate_plan(plan,["shot_B"])
        broken=dict(plan);broken["unexpected"]="allowed?"
        with self.assertRaises(RuntimeError):
            validate_plan(broken,["shot_A"])

    def test_timeline_rejects_missing_frames_or_noncontiguous_shot_ids(self):
        rows=[{"frame":1,"shot_id":"shot_A"},{"frame":2,"shot_id":"shot_A"},
              {"frame":3,"shot_id":"shot_B"}]
        self.assertEqual(shot_manifest(rows),[
            {"shot_id":"shot_A","start_frame":1,"end_frame":2,"frames":2},
            {"shot_id":"shot_B","start_frame":3,"end_frame":3,"frames":1},
        ])
        with self.assertRaisesRegex(RuntimeError,"Noncontiguous"):
            shot_manifest([rows[0],{"frame":2,"shot_id":"shot_B"},
                           {"frame":3,"shot_id":"shot_A"}])
        with self.assertRaisesRegex(RuntimeError,"exact bounded"):
            shot_manifest([rows[0],{"frame":4,"shot_id":"shot_A"}])


class AdvancedFilmIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.studio=Studio(Path(self.tmp.name)/"film.sqlite3")
        self.pid=self.studio.create_project("NVP shot look","")["id"]
        self.other=self.studio.create_project("Other project","")["id"]
        self.index=FilmIndex(self.studio)
        self.ws=AdvancedGradeWorkspace(self.studio,self.index)
        self.index.register_revision(self.pid,"take_shot_v2","take",{"format":"fixture"})
        take=self.index.read_revision(self.pid,"take_shot_v2")
        self.index.register_revision(self.pid,"exr_shots","presentation",
            {"format":"fixture.exr"},dependencies=[
                {"object_id":"take_shot_v2","revision":1,"role":"source_take"}])
        self.src=self.index.read_revision(self.pid,"exr_shots")
        self.fake={
            "record":{"document_sha256":self.src["document_sha256"],
                      "data":{"source_take_id":"take_shot_v2",
                              "source_take_sha256":take["document_sha256"]}}
        }
        self.rows=[{"frame":1,"shot_id":"shot_A","image_sha256":"a"*64},
                   {"frame":2,"shot_id":"shot_A","image_sha256":"b"*64},
                   {"frame":3,"shot_id":"shot_B","image_sha256":"c"*64}]
        self.patcher=patch.object(self.ws.master,"_source",
                                  return_value=(self.fake,self.rows,256,144))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_save_reopen_source_bound_shot_edits_and_conflicting_revision(self):
        timeline=self.ws.timeline(self.pid,"exr_shots")
        self.assertEqual(timeline["shots"][0]["frames"],2)
        self.assertEqual(timeline["shots"][1]["start_frame"],3)
        w=neutral_wheels();w["lift"][0]=.02
        plan=make_plan(shots={"shot_B":w})
        first=self.ws.save_advanced(self.pid,"exr_shots","advanced_look",plan,0)
        self.assertEqual(first["revision"],1)
        self.assertEqual(self.ws.reopen_advanced(self.pid,"advanced_look")["plan"],plan)
        plan2=make_plan(grade_recipe(exposure_stops=.15),{"shot_A":neutral_wheels()})
        second=self.ws.save_advanced(self.pid,"exr_shots","advanced_look",plan2,1)
        self.assertEqual(second["revision"],2)
        self.assertNotEqual(first["sha256"],second["sha256"])
        self.assertEqual(self.ws.reopen_advanced(self.pid,"advanced_look",1)["plan"],plan)
        self.assertEqual(self.ws.reopen_advanced(self.pid,"advanced_look")["plan"],plan2)
        record=self.index.read_revision(self.pid,"advanced_look")
        self.assertEqual(record["kind"],"edit")
        self.assertEqual(record["data"]["approval"],"not_approved")
        self.assertEqual(len(record["dependencies"]),2)
        with self.assertRaises(RuntimeError):
            self.ws.save_advanced(self.pid,"exr_shots","advanced_look",plan,1)
        with self.assertRaises(KeyError):
            self.ws.reopen_advanced(self.other,"advanced_look")
        self.assertEqual(self.index.read_revision(self.pid,"exr_shots")["document_sha256"],
                         self.src["document_sha256"])

    def test_unknown_shot_refused_before_index_writes(self):
        with self.assertRaisesRegex(RuntimeError,"absent"):
            self.ws.save_advanced(
                self.pid,"exr_shots","foreign_shot",
                make_plan(shots={"shot_other":neutral_wheels()}),0)
        self.assertEqual(self.index.list_objects(self.pid,kind="edit"),[])


if __name__=="__main__":
    unittest.main()
