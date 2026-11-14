"""GRADE-UI-01: immutable edit revisions, creator approval and preview API contracts.

No Blender required: a real native source/reopen fixture runs separately.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_grade_workspace import GradeWorkspace, FORMAT
from backend.nvp_color_mastering import grade_recipe, validate_grade


class GradeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.studio=Studio(Path(self.temp.name)/"film.sqlite3")
        self.pid=self.studio.create_project("Film A","graded look")["id"]
        self.other=self.studio.create_project("Film B","other")["id"]
        self.index=FilmIndex(self.studio)
        self.ws=GradeWorkspace(self.studio,self.index)
        self.take_id="take_grade_demo"
        self.src_id="exr_grade_demo"
        self.index.register_revision(self.pid,self.take_id,"take",{"format":"fixture.take.v1"})
        self.src_record=self.index.register_revision(self.pid,self.src_id,"presentation",
            {"format":"fixture.exr.v1"},dependencies=[
                {"object_id":self.take_id,"revision":1,"role":"source_take"}])
        self.fake_source={
            "record":{
                "document_sha256":self.src_record["document_sha256"],
                "data":{
                    "source_take_id":self.take_id,
                    "source_take_sha256":self.index.read_revision(
                        self.pid,self.take_id)["document_sha256"],
                },
            },
        }
        self.fake_frames=[{"frame":1,"shot_id":"shot1","image_sha256":"a"*64},
                          {"frame":2,"shot_id":"shot1","image_sha256":"b"*64}]

    def tearDown(self):
        self.temp.cleanup()

    def test_versioned_unapproved_draft_survives_restart_with_optimistic_conflict(self):
        with patch.object(self.ws.master,"_source",
                          return_value=(self.fake_source,self.fake_frames,256,144)):
            first=self.ws.save(self.pid,self.src_id,"look_main",
                               grade_recipe(red_gain=1.05),0)
            self.assertEqual(first["revision"],1)
            self.assertEqual(first["status"],"draft_not_director_approved")
            second=self.ws.save(self.pid,self.src_id,"look_main",
                                grade_recipe(blue_gain=1.08),1)
            self.assertEqual(second["revision"],2)
            self.assertNotEqual(first["document_sha256"],second["document_sha256"])
            old=self.ws.reopen(self.pid,"look_main",revision=1)
            latest=self.ws.reopen(self.pid,"look_main")
            self.assertEqual(old["recipe"]["red_gain"],1.05)
            self.assertEqual(latest["recipe"]["blue_gain"],1.08)
            self.assertEqual(len(self.ws.history(self.pid,"look_main")),2)
            self.assertEqual(self.ws.list_grades(self.pid)[0]["revision"],2)
            self.assertEqual(self.index.read_revision(self.pid,self.take_id)["kind"],"take")
            with self.assertRaisesRegex(RuntimeError,"conflict"):
                self.ws.save(self.pid,self.src_id,"look_main",grade_recipe(),1)
            with self.assertRaises(KeyError):
                GradeWorkspace(Studio(Path(self.temp.name)/"film.sqlite3")).reopen(
                    self.other,"look_main")

    def test_new_grade_never_approves_film_or_alters_source(self):
        with patch.object(self.ws.master,"_source",
                          return_value=(self.fake_source,self.fake_frames,256,144)):
            result=self.ws.save(self.pid,self.src_id,"unapproved_look",grade_recipe(),0)
            doc=self.index.read_revision(self.pid,"unapproved_look")
            self.assertEqual(doc["kind"],"edit")
            self.assertEqual(doc["data"]["approval"],"not_approved")
            self.assertEqual(doc["data"]["format"],FORMAT)
            self.assertEqual(len(doc["dependencies"]),2)
            self.assertEqual(self.index.read_revision(self.pid,self.src_id)["document_sha256"],
                             self.src_record["document_sha256"])
            self.assertNotIn("screening_ready",str(doc))

    def test_preview_guard_bounded_and_released_on_decoder_failure(self):
        class Gate:
            def __init__(self,allow):
                self.allow=allow
                self.released=0
            def acquire(self,blocking=False):
                self.assertFalseBlock = blocking
                return self.allow
            def release(self):
                self.released+=1
        busy=Gate(False)
        with patch("backend.nvp_grade_workspace._PREVIEW_SLOTS",busy):
            with self.assertRaisesRegex(RuntimeError,"two-worker limit"):
                self.ws.preview(self.pid,"source",1)
        self.assertEqual(busy.released,0)
        entered=Gate(True)
        with patch("backend.nvp_grade_workspace._PREVIEW_SLOTS",entered),patch.object(
            self.ws,"_preview_actual",side_effect=RuntimeError("decode error")):
            with self.assertRaisesRegex(RuntimeError,"decode error"):
                self.ws.preview(self.pid,"source",1)
        self.assertEqual(entered.released,1)

    def test_source_change_and_invalid_recipe_are_refused(self):
        with patch.object(self.ws.master,"_source",
                          return_value=(self.fake_source,self.fake_frames,256,144)) as src:
            self.ws.save(self.pid,self.src_id,"look_first",grade_recipe(),0)
            self.assertEqual(len(self.ws.list_grades(self.pid,self.src_id)),1)
            with self.assertRaises(KeyError):
                self.ws.save(self.other,self.src_id,"wrong_project",grade_recipe(),0)
            with self.assertRaisesRegex(RuntimeError,"conflicts"):
                self.ws.save(self.pid,"other_exr","look_first",grade_recipe(),1)
            invalid=dict(grade_recipe());invalid["exposure_stops"]=99
            with self.assertRaisesRegex(RuntimeError,"invalid grading"):
                self.ws.save(self.pid,self.src_id,"bad_recipe",invalid,0)
            with self.assertRaises(ValueError):
                self.ws.save(self.pid,self.src_id,"bad_name/../../",grade_recipe(),0)


class GradeHTTPContracts(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.studio=Studio(Path(self.temp.name)/"api.sqlite3")
        self.pid=self.studio.create_project("Test UI","")["id"]
        self.other=self.studio.create_project("Unrelated","")["id"]
        self.mock=patch("backend.nvp_api.studio",self.studio)
        self.mock.start()
        from backend.nvp_api import app
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close()
        self.mock.stop()
        self.temp.cleanup()

    def test_empty_source_api_and_invalid_grade_rejected_without_mutation(self):
        response=self.client.get(f"/api/projects/{self.pid}/color-grading/sources")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),[])
        with self.assertRaisesRegex(KeyError,"not found"):
            FilmIndex(self.studio).read_revision(self.pid,"look_bad")
        forbidden=self.client.post(f"/api/projects/{self.pid}/color-grading/grades",
            json={"source_exr_id":"missing_source","grade_id":"look_bad",
                  "expected_revision":0,"recipe":grade_recipe(),
                  "source_primaries_declared":False})
        self.assertEqual(forbidden.status_code,422)
        not_found=self.client.post(f"/api/projects/{self.pid}/color-grading/grades",
            json={"source_exr_id":"missing_source","grade_id":"look_bad",
                  "expected_revision":0,"recipe":grade_recipe(),
                  "source_primaries_declared":True})
        self.assertEqual(not_found.status_code,404)
        self.assertEqual(FilmIndex(self.studio).list_objects(self.pid,kind="edit"),[])

    def test_real_preview_endpoint_uses_neutral_or_current_grade(self):
        payload=b"\x89PNG\r\n\x1a\n"+b"z"*70
        def result(_self,pid,sid,frame,recipe):
            self.assertEqual(pid,self.pid)
            self.assertEqual(sid,"exr_source_16f")
            self.assertEqual(frame,1)
            return {"bytes":payload,"source_frame":frame,"recipe":recipe}
        with patch.object(GradeWorkspace,"preview",new=result):
            neutral=self.client.get(
                f"/api/projects/{self.pid}/color-grading/sources/exr_source_16f/preview",
                params={"frame":1,"mode":"before","red_gain":1.20})
            self.assertEqual(neutral.status_code,200)
            self.assertEqual(neutral.headers.get("x-nvp-preview-quality"),
                             "uncalibrated-display-preview-not-master")
            self.assertEqual(neutral.headers.get("cache-control"),"no-store, private")
            self.assertEqual(neutral.content,payload)
            modified=self.client.get(
                f"/api/projects/{self.pid}/color-grading/sources/exr_source_16f/preview",
                params={"frame":1,"mode":"after","red_gain":1.20})
            self.assertEqual(modified.status_code,200)
            invalid=self.client.get(
                f"/api/projects/{self.pid}/color-grading/sources/exr_source_16f/preview",
                params={"frame":1,"mode":"after","red_gain":100})
            self.assertEqual(invalid.status_code,422)
            self.assertEqual(FilmIndex(self.studio).list_objects(self.pid,kind="edit"),[])


if __name__=="__main__":
    unittest.main()
