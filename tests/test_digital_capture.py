"""CAPTURE-01: actual approved 3D timed world -> frozen, indexed Digital Take."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene, digest
from backend.nvp_world_state import WorldState
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_film_index import FilmIndex
from backend.nvp_digital_capture import DigitalCapture


SCREENPLAY = """INT. KITCHEN - NIGHT

MARA
Where is the key?

BOB
I don't know.
"""


class DigitalCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "nvp_capture.sqlite3"
        self.studio = Studio(self.path)
        self.pid = self.studio.create_project("Camera Test", "One frozen take")["id"]
        self.sid = self.studio.save_screenplay(self.pid, SCREENPLAY, 0)["scenes"][0]["id"]
        self.prod = ProductionScene(self.studio)
        for name in ("MARA", "BOB"):
            self.prod.create_asset(self.pid, {
                "name": name, "category": "character", "dimensions": [.4,.4,1.7]})
        stage = self.prod.stage_scene(self.pid, self.sid, [10,8,3])
        stage = self.prod.solve_scene(self.pid, self.sid, stage["plan_revision"])
        self.prod.approve_scene(self.pid, self.sid, stage["plan_revision"])
        self.bc = BlockingCamera(self.studio)
        self.actor_ids = {x["name"]: x["instance_id"]
                          for x in self.prod.export_manifest(self.pid, self.sid)["instances"]}
        self.camera = self.bc.solve_shot(self.pid,self.sid,[self.actor_ids["MARA"]])
        self.lines = self.bc.dialogue(self.pid, self.sid)["dialogue"]
        for line in self.lines:
            self.bc.set_dialogue_duration(self.pid,self.sid,line["id"],1.5)
        self.seq = ShotSequence(self.studio)
        self.seq.create(self.pid, self.sid)
        self.seq.add_shot(self.pid,self.sid,self.camera["id"],48,"single",0)
        self.seq.add_shot(self.pid,self.sid,self.camera["id"],72,"reaction",1)
        self.seq.place_cue(self.pid,self.sid,self.lines[0]["id"],1,2)
        self.seq.place_cue(self.pid,self.sid,self.lines[1]["id"],49,3)
        state=self.seq.read(self.pid,self.sid)
        self.assertFalse(state["review"]["errors"])
        if state["review"]["warnings"]:
            state=self.seq.acknowledge(
                self.pid,self.sid,[w["code"] for w in state["review"]["warnings"]],
                state["revision"])
        approved=self.seq.approve(self.pid,self.sid,state["revision"])
        self.assertEqual(approved["status"],"approved")
        self.index = FilmIndex(self.studio)
        self.capture = DigitalCapture(self.studio,self.index)

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_approved_camera_actor_dialogue_capture_reopens_after_restart(self):
        created=self.capture.capture(self.pid,self.sid,"take_001")
        self.assertEqual(created["receipt"]["revision"],1)
        self.assertEqual(created["audit"]["status"],"passed_frozen_proxy_capture")
        self.assertEqual(created["audit"]["shot_count"],2)
        self.assertEqual(created["audit"]["dialogue_line_count"],2)
        self.assertEqual(created["audit"]["actor_count"],2)
        self.assertEqual(created["audit"]["frames"],120)
        saved=DigitalCapture(Studio(self.path)).reopen(self.pid,"take_001")
        self.assertEqual(saved["record"]["data"]["capture_state"],"frozen_proxy_data")
        self.assertEqual(saved["timed_take"]["shots"][0]["start_frame"],1)
        self.assertEqual(saved["timed_take"]["shots"][1]["start_frame"],49)
        self.assertEqual(saved["timed_take"]["shots"][1]["stop_frame"],121)
        self.assertEqual(saved["timed_take"]["dialogue"][0]["duration_frames"],36)
        self.assertEqual({x["speaker"] for x in saved["timed_take"]["dialogue"]},
                         set(self.actor_ids.values()))
        self.assertEqual({x["id"] for x in saved["timed_take"]["shots"]},
                         {x["id"] for x in saved["source_plan"]["shots"]})
        self.assertEqual(saved["timed_take"]["world_sha"],
                         saved["world"]["world_digest_sha256"])
        self.assertEqual(saved["audit"]["world_sha256"],digest(saved["world"]))

    def test_content_source_nodes_reused_for_two_independent_frozen_takes(self):
        first=self.capture.capture(self.pid,self.sid,"take_A")
        second=self.capture.capture(self.pid,self.sid,"take_B")
        self.assertEqual(first["audit"],second["audit"])
        take_a=self.index.read_revision(self.pid,"take_A")
        take_b=self.index.read_revision(self.pid,"take_B")
        self.assertEqual(take_a["data"]["source_world_id"],take_b["data"]["source_world_id"])
        self.assertEqual(take_a["data"]["source_performance_id"],
                         take_b["data"]["source_performance_id"])
        self.assertEqual(len(self.index.list_objects(self.pid,kind="world")),1)
        self.assertEqual(len(self.index.list_objects(self.pid,kind="performance")),1)
        with self.assertRaisesRegex(RuntimeError,"conflict|cannot be revised"):
            self.capture.capture(self.pid,self.sid,"take_A")

    def test_existing_capture_survives_new_camera_revision_and_stale_world(self):
        self.capture.capture(self.pid,self.sid,"take_before")
        before=self.capture.reopen(self.pid,"take_before")
        approved=self.seq.read(self.pid,self.sid)
        self.seq.new_revision(self.pid,self.sid,approved["revision"])
        with self.assertRaisesRegex(RuntimeError,"Only a current director-approved sequence"):
            self.capture.capture(self.pid,self.sid,"take_draft")
        self.assertEqual(DigitalCapture(Studio(self.path)).reopen(
            self.pid,"take_before")["audit"],before["audit"])
        WorldState(self.studio).set_human(
            self.pid,self.sid,self.actor_ids["MARA"],"visible",False,0)
        with self.assertRaises(RuntimeError):
            self.capture.capture(self.pid,self.sid,"take_stale")
        self.assertEqual(self.capture.reopen(self.pid,"take_before")["world"],before["world"])

    def test_in_transaction_source_guard_refuses_to_commit_changed_live_sequence(self):
        original=self.index.register_revision
        def race(*args,**kwargs):
            if args[2] == "take":
                state=self.seq.read(self.pid,self.sid)
                self.seq.new_revision(self.pid,self.sid,state["revision"])
            return original(*args,**kwargs)
        with patch.object(self.index,"register_revision",side_effect=race):
            with self.assertRaises(RuntimeError):
                self.capture.capture(self.pid,self.sid,"take_raced")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"take_raced")
        self.assertEqual(self.index.list_objects(self.pid,kind="take"),[])

    def test_missing_project_cross_project_and_unknown_capture_refused(self):
        other = self.studio.create_project("Foreign", "Must not leak")["id"]
        self.capture.capture(self.pid,self.sid,"take_local")
        with self.assertRaises(KeyError):
            self.capture.reopen(other,"take_local")
        with self.assertRaises(KeyError):
            self.capture.reopen(self.pid,"take_missing")
        with self.assertRaises(KeyError):
            self.capture.capture(other,self.sid,"take_foreign")
        with self.assertRaises(ValueError):
            self.capture.capture(self.pid,self.sid,"../not_a_take")

    def test_approved_take_metadata_tamper_caught_on_independent_reopen(self):
        self.capture.capture(self.pid,self.sid,"take_tamper")
        original=self.index.read_revision(self.pid,"take_tamper")
        changed=copy.deepcopy(original)
        changed["data"]["frame_count"] = 100
        forged={
            "format":"nvp.film.revision.v1","object_id":"take_tamper","kind":"take",
            "data":changed["data"],"dependencies":changed["dependencies"]}
        sha=self.index.put_json(self.pid,forged)
        with self.studio._connection() as db:
            db.execute("""UPDATE film_object_revisions SET document_sha=?
                          WHERE project_id=? AND object_id=?""",(sha,self.pid,"take_tamper"))
        with self.assertRaisesRegex(RuntimeError,"metadata and source snapshot disagree"):
            DigitalCapture(Studio(self.path)).reopen(self.pid,"take_tamper")

    def test_timed_performance_source_byte_corruption_refuses_reopen(self):
        self.capture.capture(self.pid,self.sid,"take_corrupt")
        item=self.index.read_revision(self.pid,"take_corrupt")
        performance=self.index.read_revision(self.pid,item["data"]["source_performance_id"])
        location=self.index._blob_path(self.pid,performance["document_sha256"])
        location.write_bytes(b"corrupted input")
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            DigitalCapture(Studio(self.path)).reopen(self.pid,"take_corrupt")

    def test_separate_world_and_performance_lineage_to_final_derived_objects(self):
        self.capture.capture(self.pid,self.sid,"take_001")
        source=self.index.read_revision(self.pid,"take_001")
        world=source["data"]["source_world_id"]
        perf=source["data"]["source_performance_id"]
        self.assertIn({"object_id":"take_001","revision":1},
                      self.index.direct_dependents(self.pid,perf,1))
        self.assertEqual({x["object_id"] for x in self.index.impact(self.pid,world,1)},
                         {perf,"take_001"})
        presentation=self.index.register_revision(
            self.pid,"presentation_proxy","presentation",
            {"model":"deterministic_renderer_candidate","status":"not_rendered"},
            dependencies=[{"object_id":"take_001","revision":1,"role":"source_take"}])
        self.assertEqual(presentation["revision"],1)
        self.assertEqual({x["object_id"] for x in self.index.impact(self.pid,world,1)},
                         {perf,"take_001","presentation_proxy"})

    def test_nonmatching_stored_approval_and_source_rejected_on_reopen(self):
        self.capture.capture(self.pid,self.sid,"take_lineage")
        item=self.index.read_revision(self.pid,"take_lineage")
        performance=self.index.read_revision(self.pid,item["data"]["source_performance_id"])
        modified=copy.deepcopy(performance)
        modified["data"]["approval_proof"]["approved_digest"]="0"*64
        forged={"format":"nvp.film.revision.v1",
                "object_id":modified["object_id"],"kind":"performance",
                "data":modified["data"],"dependencies":modified["dependencies"]}
        sha=self.index.put_json(self.pid,forged)
        with self.studio._connection() as db:
            db.execute("""UPDATE film_object_revisions SET document_sha=?
                          WHERE project_id=? AND object_id=?""",
                       (sha,self.pid,performance["object_id"]))
        with self.assertRaisesRegex(RuntimeError,"director approval digest mismatch"):
            self.capture.reopen(self.pid,"take_lineage")


if __name__=="__main__":
    unittest.main()
