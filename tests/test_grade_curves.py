"""NVP GRADE-UI-02B1 HDR EV curves, per-shot draft revision and source safety."""
from __future__ import annotations
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from backend.nvp_grade_curves import (
    neutral_curve, validate_curve, apply_ev_curve,
    make_curve_plan, validate_curve_plan, CurveGradeWorkspace,
)
from backend.nvp_grade_advanced import make_plan
from backend.nvp_color_mastering import grade_recipe
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio


class CurveMathTests(unittest.TestCase):
    def test_neutral_curve_preserves_higher_than_one_hdr_and_source(self):
        pixels=np.array([[[2.25,.37,.058,1.],[.18,.18,.18,1.],[0,0,0,1.]]],dtype=np.float32)
        original=pixels.copy()
        after=apply_ev_curve(pixels,neutral_curve())
        self.assertTrue(np.allclose(after,original,atol=1e-6))
        self.assertTrue(np.array_equal(pixels,original))
        self.assertGreater(after[0,0,0],1)

    def test_mid_tone_one_stop_and_black_preservation(self):
        curve=neutral_curve();curve["ev_offsets"][2]=1.
        pixels=np.array([[[.18,.18,.18,1.],[0,0,0,1.],[.72,.72,.72,1.]]],dtype=np.float32)
        after=apply_ev_curve(pixels,curve)
        self.assertAlmostEqual(float(after[0,0,0]),.36,places=5)
        self.assertEqual(float(after[0,1,0]),0)
        self.assertGreater(float(after[0,2,0]),.72)
        self.assertTrue(np.array_equal(pixels[:,:,3],after[:,:,3]))

    def test_nan_out_of_bounds_and_unsafe_shape_refused(self):
        for knots in ([0.,0.,float("nan"),0.,0.],[.1,0,0,0,0],
                      [0,0,2,0,0],[0,0,0,0,0,0]):
            candidate=neutral_curve();candidate["ev_offsets"]=knots
            with self.subTest(knots=knots),self.assertRaises(ValueError):
                validate_curve(candidate)
        with self.assertRaises(ValueError):
            apply_ev_curve(np.zeros((1,1,3),dtype=np.float32),neutral_curve())
        with self.assertRaises(RuntimeError):
            apply_ev_curve(np.array([[[-.01,.01,.01,1]]],dtype=np.float32),neutral_curve())

    def test_source_shot_cannot_be_substituted(self):
        plan=make_curve_plan(curves={"shot_B":neutral_curve()})
        with self.assertRaisesRegex(RuntimeError,"absent source shot"):
            validate_curve_plan(plan,["shot_A"])
        modified=dict(plan);modified["forged"]="yes"
        with self.assertRaises(RuntimeError):
            validate_curve_plan(modified,["shot_B"])
        self.assertEqual(validate_curve_plan(plan,["shot_B"]),plan)


class CurvesFilmIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.db=Path(self.tmp.name)/"film.sqlite3"
        self.studio=Studio(self.db)
        self.project=self.studio.create_project("Curve studio","")["id"]
        self.foreign=self.studio.create_project("Other","")["id"]
        self.index=FilmIndex(self.studio)
        self.index.register_revision(self.project,"take_curves","take",{"format":"test.take"})
        take=self.index.read_revision(self.project,"take_curves")
        self.index.register_revision(self.project,"exr_curves","presentation",
            {"format":"test.exr"},dependencies=[
                {"object_id":"take_curves","revision":1,"role":"source_take"}])
        exr=self.index.read_revision(self.project,"exr_curves")
        self.fake={
            "record":{"document_sha256":exr["document_sha256"],
                      "data":{"source_take_id":"take_curves",
                              "source_take_sha256":take["document_sha256"]}}
        }
        self.rows=[
            {"frame":1,"shot_id":"shot_A","image_sha256":"a"*64},
            {"frame":2,"shot_id":"shot_A","image_sha256":"b"*64},
            {"frame":3,"shot_id":"shot_B","image_sha256":"c"*64},
        ]
        self.ws=CurveGradeWorkspace(self.studio,self.index)
        # Mock only the heavy source-decoder path, not FilmIndex custody.
        self.patch=patch.object(self.ws.master,"_source",
            return_value=(self.fake,self.rows,256,144))
        self.patch.start()

    def tearDown(self):
        self.patch.stop();self.tmp.cleanup()

    def test_curves_are_immutable_drafts_reopen_both_versions_and_refuse_stale(self):
        curve=neutral_curve();curve["ev_offsets"][1]=.5
        plan=make_curve_plan(curves={"shot_A":curve})
        first=self.ws.save_curve(self.project,"exr_curves","look_curves",plan,0)
        second_plan=make_curve_plan(grade_recipe(exposure_stops=.2),curves={"shot_B":curve})
        second=self.ws.save_curve(self.project,"exr_curves","look_curves",second_plan,1)
        self.assertNotEqual(first["sha256"],second["sha256"])
        self.assertEqual(self.ws.reopen_curve(self.project,"look_curves",1)["plan"],plan)
        self.assertEqual(self.ws.reopen_curve(self.project,"look_curves")["plan"],second_plan)
        with self.assertRaises(RuntimeError):
            self.ws.save_curve(self.project,"exr_curves","look_curves",plan,1)
        with self.assertRaises(KeyError):
            self.ws.reopen_curve(self.foreign,"look_curves")
        self.assertEqual(self.index.read_revision(self.project,"look_curves")["data"]["approval"],"not_approved")
        self.assertEqual(self.index.read_revision(self.project,"exr_curves")["data"]["format"],"test.exr")

    def test_unknown_shot_rejected_before_any_write(self):
        with self.assertRaises(RuntimeError):
            self.ws.save_curve(self.project,"exr_curves","bogus",
                make_curve_plan(curves={"foreign_shot":neutral_curve()}),0)
        self.assertEqual(self.index.list_objects(self.project,kind="edit"),[])


class CurvesHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.studio=Studio(Path(self.tmp.name)/"api.sqlite3")
        self.pid=self.studio.create_project("Curves test","")["id"]
        self.patcher=patch("backend.nvp_api.studio",self.studio)
        self.patcher.start()
        from backend.nvp_api import app
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close();self.patcher.stop();self.tmp.cleanup()

    def test_save_refuses_unknown_source_and_missing_primaries_consent(self):
        url=f"/api/projects/{self.pid}/color-grading/curves/grades"
        payload={"source_id":"missing","grade_id":"look","expected_revision":0,
                 "source_primaries_declared":False,
                 "plan":make_curve_plan()}
        self.assertEqual(self.client.post(url,json=payload).status_code,422)
        payload["source_primaries_declared"]=True
        self.assertEqual(self.client.post(url,json=payload).status_code,404)
        self.assertEqual(FilmIndex(self.studio).list_objects(self.pid,kind="edit"),[])


if __name__=="__main__":
    unittest.main()
