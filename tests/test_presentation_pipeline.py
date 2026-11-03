"""NVP-PIPE-01A: capability refusal, exact shot sampling and immutable output checks."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import FilmIndex
from backend.nvp_presentation_pipeline import (
    PresentationPipeline, selected_frames, _png_info, ENGINE,
)


class PresentationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"presents.sqlite"
        self.studio=Studio(self.db)
        self.pid=self.studio.create_project("Pipeline Test","Immutable presentations")["id"]
        script="INT. ROOM - NIGHT\n\nMARA\nHello.\n"
        self.sid=self.studio.save_screenplay(self.pid,script,0)["scenes"][0]["id"]
        prod=ProductionScene(self.studio)
        prod.create_asset(self.pid,{"name":"MARA","category":"character",
                                   "dimensions":[.4,.4,1.7]})
        layout=prod.stage_scene(self.pid,self.sid,[8,6,3])
        layout=prod.solve_scene(self.pid,self.sid,layout["plan_revision"])
        prod.approve_scene(self.pid,self.sid,layout["plan_revision"])
        bc=BlockingCamera(self.studio)
        actor=prod.export_manifest(self.pid,self.sid)["instances"][0]["instance_id"]
        cam=bc.solve_shot(self.pid,self.sid,[actor])
        line=bc.dialogue(self.pid,self.sid)["dialogue"][0]
        bc.set_dialogue_duration(self.pid,self.sid,line["id"],.5)
        seq=ShotSequence(self.studio)
        state=seq.create(self.pid,self.sid)
        state=seq.add_shot(self.pid,self.sid,cam["id"],20,"single",state["revision"])
        state=seq.add_shot(self.pid,self.sid,cam["id"],20,"reaction",state["revision"])
        state=seq.place_cue(self.pid,self.sid,line["id"],1,state["revision"])
        if state["review"]["warnings"]:
            state=seq.acknowledge(self.pid,self.sid,
                       [x["code"] for x in state["review"]["warnings"]],state["revision"])
        seq.approve(self.pid,self.sid,state["revision"])
        self.index=FilmIndex(self.studio)
        self.take=DigitalCapture(self.studio,self.index)
        self.take.capture(self.pid,self.sid,"take_001")
        self.pipeline=PresentationPipeline(self.studio,self.index)

    def tearDown(self):
        self.tmp.cleanup()

    def test_engine_capabilities_are_truthful(self):
        modes=self.pipeline.available_engines()
        self.assertEqual(len(modes),2)
        self.assertEqual(modes[0]["engine"],ENGINE)
        self.assertEqual(modes[0]["styles"],["flat","studio"])
        self.assertIn("No generated video/voice/audio",modes[0]["limitations"][1])
        self.assertEqual(modes[1]["engine"],"blender_cycles")
        self.assertEqual(modes[1]["styles"],["pbr_noir","pbr_studio"])
        self.assertNotIn("wan",str(modes).lower())

    def test_native_capture_shot_policy_is_exact_and_bounded(self):
        timed=self.take.reopen(self.pid,"take_001")["timed_take"]
        preview=selected_frames(timed,"keyframes")
        self.assertEqual([(x["frame"],x["shot_id"]) for x in preview],
            [(1,timed["shots"][0]["id"]),(10,timed["shots"][0]["id"]),
             (21,timed["shots"][1]["id"]),(30,timed["shots"][1]["id"])])
        full=selected_frames(timed,"full")
        self.assertEqual([x["frame"] for x in full],list(range(1,41)))
        self.assertEqual(len({x["filename"] for x in full}),40)
        with self.assertRaises(ValueError):
            selected_frames({"shots":[{"id":"a","start_frame":8,"stop_frame":15}]})
        with self.assertRaises(ValueError):
            selected_frames(timed,"imaginary")
        with self.assertRaises(ValueError):
            selected_frames({"shots":[{"id":"shot01","start_frame":1,"stop_frame":2402}]},"full")

    def test_unknown_engines_and_styles_fail_without_work(self):
        root=Path(self.tmp.name)/"new"
        for config in [{"engine":"wan_video"},{"style":"photoreal_ai"},
                       {"frame_mode":"unsupported"},{"width":0},
                       {"height":5000},{"timeout":0}]:
            with self.subTest(config=config),self.assertRaises(ValueError):
                self.pipeline.render(self.pid,"take_001","presentation_bad",root,**config)
        self.assertFalse(root.exists())
        self.assertEqual(self.index.list_objects(self.pid,kind="presentation"),[])

    def test_unavailable_blender_refused_no_approved_presentation(self):
        root=Path(self.tmp.name)/"renders"
        with patch("backend.nvp_presentation_pipeline.blender_available",
                   return_value={"available":False,"reason":"Blender absent"}):
            with self.assertRaisesRegex(RuntimeError,"Blender unavailable"):
                self.pipeline.render(self.pid,"take_001","presentation_no_blender",root)
        self.assertEqual(self.index.list_objects(self.pid,kind="presentation"),[])
        self.assertFalse(root.exists())
        self.assertEqual(self.take.reopen(self.pid,"take_001")["record"]["kind"],"take")

    def test_forged_presentation_and_wrong_lineage_cannot_reopen(self):
        self.index.register_revision(self.pid,"fake_presentation","presentation",
                    {"format":"nvp.presentation.blender.v1","status":"rendered_unreviewed",
                     "engine":"blender_workbench","style":"studio",
                     "source_take_id":"take_001","source_take_sha256":"0"*64,
                     "frame_mode":"keyframes","rendered_frames":[]},
                    dependencies=[{"object_id":"take_001","revision":1,"role":"source_take"}])
        with self.assertRaisesRegex(RuntimeError,"source take digest mismatch"):
            self.pipeline.reopen(self.pid,"fake_presentation")
        with self.assertRaises(KeyError):
            self.pipeline.reopen(self.pid,"missing")
        other=self.studio.create_project("Other","")["id"]
        with self.assertRaises(KeyError):
            self.pipeline.reopen(other,"fake_presentation")

    def test_unverified_render_receipt_cannot_be_reopened(self):
        real_take=self.take.reopen(self.pid,"take_001")
        self.index.register_revision(
            self.pid,"forged_blender","presentation",{
                "format":"nvp.presentation.blender.v1",
                "status":"rendered_unreviewed",
                "engine":"blender_workbench","style":"studio",
                "source_take_id":"take_001","source_take_revision":1,
                "source_take_sha256":real_take["record"]["document_sha256"],
                "frame_rate":24,"frame_mode":"keyframes",
                "native_geometry_checks":12,"rendered_frames":[],
                "render_receipt":{}
            },dependencies=[{"object_id":"take_001","revision":1,"role":"source_take"}])
        with self.assertRaisesRegex(RuntimeError,"native render receipt"):
            self.pipeline.reopen(self.pid,"forged_blender")

    def test_invalid_png_headers_and_sizes_fail_closed(self):
        for payload in (b"",b"\x89PNG\r\n\x1a\n"+"x".encode()*60,
                        b"not a real picture"*10):
            with self.subTest(length=len(payload)),self.assertRaises(RuntimeError):
                _png_info(payload)

    def test_original_capture_and_index_survive_reopen(self):
        old=self.take.reopen(self.pid,"take_001")
        new=PresentationPipeline(Studio(self.db))
        assert old["record"]["document_sha256"]==new.capture.reopen(
             self.pid,"take_001")["record"]["document_sha256"]
        self.assertEqual(self.index.list_objects(self.pid,kind="presentation"),[])


if __name__=="__main__":
    unittest.main()
