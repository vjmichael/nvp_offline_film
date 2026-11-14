"""NVP-PROD-01: asset identity, staging, constraint solution, approval, Blender export."""
import ast
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient
from backend.nvp_studio import Studio
from backend.nvp_production_scene import (
    ProductionScene, solve_layout, verify_layout, validate_asset, validate_room,
    blender_script, digest, validate_instances,
)
from backend import nvp_api

SCRIPT = """INT. KITCHEN - NIGHT

MARA
What happened to the key?

BOB
I don't know.

EXT. STREET - NIGHT

Bob runs into the darkness.
"""

class ProductionStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "production.sqlite3"
        self.studio = Studio(self.path)
        self.pid = self.studio.create_project("Locked Door", "A missing key")["id"]
        self.project = self.studio.save_screenplay(self.pid, SCRIPT, 0)
        self.scene_id = self.project["scenes"][0]["id"]
        self.prod = ProductionScene(self.studio)

    def tearDown(self):
        self.tmp.cleanup()

    def asset(self, name="Table", category="furniture", dimensions=None, anchors=None):
        return self.prod.create_asset(self.pid, {"name": name, "category": category,
              "dimensions": dimensions or [2.0, 1.0, .75], "anchors": anchors or {}})

    def stage(self, room=None):
        return self.prod.stage_scene(self.pid, self.scene_id, room or [8, 6, 3])

    def add(self, plan, asset, instance_id, **kwargs):
        return self.prod.add_instance(self.pid, self.scene_id, asset["asset_id"],
                                      instance_id, plan["plan_revision"], **kwargs)

    def test_asset_identity_and_provenance_survive_database_restart(self):
        table = self.asset(anchors={"front": [0, -.5, .7]})
        reopened = ProductionScene(Studio(self.path)).list_assets(self.pid)
        self.assertEqual(reopened[0]["asset_id"], table["asset_id"])
        self.assertEqual(reopened[0]["source_kind"], "procedural_proxy")
        self.assertEqual(reopened[0]["license"], "creator_procedural")
        self.assertEqual(reopened[0]["anchors"]["front"], [0, -.5, .7])

    def test_cast_is_linked_only_when_asset_registered(self):
        mara = self.asset("MARA", "character", [.6, .6, 1.7])
        stage = self.stage()
        self.assertEqual(stage["unresolved_cast"], ["BOB"])
        self.assertEqual(stage["instances"][0]["asset_id"], mara["asset_id"])
        self.assertEqual(stage["instances"][0]["instance_id"], "cast_1")

    def test_unknown_characters_remain_unresolved_not_invented(self):
        stage = self.stage()
        self.assertEqual(stage["unresolved_cast"], ["MARA", "BOB"])
        self.assertEqual(stage["instances"], [])

    def test_reject_malicious_and_invalid_asset_dimensions(self):
        with self.assertRaises(ValueError):
            self.asset("X", dimensions=[float('nan'), 1, 1])
        with self.assertRaises(ValueError):
            self.asset("X", dimensions=[True, 1, 1])
        with self.assertRaises(ValueError):
            self.asset("X", anchors={"off": [3, 0, 0]})
        with self.assertRaises(ValueError):
            self.asset("X", anchors={"off": [0, 0, -1]})
        with self.assertRaises(ValueError):
            self.prod.create_asset(self.pid, {"name": "bad", "category": "unknown", "dimensions": [1, 1, 1]})
        with self.assertRaises(ValueError):
            self.prod.create_asset(self.pid, {"name": "bad", "category": "prop", "dimensions": [1, 1, 1],
                                               "anchors": {"bad name": [0,0,0]}})

    def test_duplicate_asset_names_are_refused(self):
        self.asset()
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.asset()

    def test_layout_determinism_and_nonoverlap(self):
        table = self.asset()
        chair = self.asset("Chair", dimensions=[.55, .55, .9])
        stage = self.stage()
        stage = self.add(stage, table, "table", wall="north")
        stage = self.add(stage, chair, "chair")
        assets = {a["asset_id"]: a for a in self.prod.list_assets(self.pid)}
        first = solve_layout(stage["room"], stage["instances"], assets)
        second = solve_layout(stage["room"], stage["instances"], assets)
        self.assertEqual(first["placements"], second["placements"])
        self.assertEqual(first["checked"]["status"], "valid")
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertEqual(stage["layout"]["placements"], first["placements"])

    def test_anchor_target_order_and_proximity(self):
        table = self.asset(anchors={"front": [0, -.5, .5]})
        chair = self.asset("Chair", dimensions=[.5, .5, .9], anchors={"front": [0, .25, .5]})
        stage = self.stage()
        stage = self.add(stage, table, "z_table", wall="north")
        stage = self.add(stage, chair, "a_chair", attachment={
            "target_instance": "z_table", "self_anchor": "front", "target_anchor": "front", "max_gap": .6})
        solved = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertEqual(solved["layout"]["checked"]["status"], "valid")
        self.assertIn("a_chair", solved["layout"]["placements"])

    def test_attachment_cycle_refused(self):
        a = self.asset("A", anchors={"hook": [0, 0, .2]})
        b = self.asset("B", anchors={"hook": [0, 0, .2]})
        nodes = [{"instance_id": "a", "asset_id": a["asset_id"], "attachment": {
                     "target_instance": "b", "target_anchor": "hook", "self_anchor": "hook", "max_gap": .5}},
                 {"instance_id": "b", "asset_id": b["asset_id"], "attachment": {
                     "target_instance": "a", "target_anchor": "hook", "self_anchor": "hook", "max_gap": .5}}]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_instances(nodes, {a["asset_id"]: a, b["asset_id"]: b})

    def test_missing_attachment_refused(self):
        a = self.asset("A", anchors={"hook": [0, 0, .2]})
        stage = self.stage()
        with self.assertRaisesRegex(ValueError, "target does not exist"):
            self.add(stage, a, "a", attachment={
                "target_instance": "missing", "target_anchor": "hook", "self_anchor": "hook", "max_gap": .5})

    def test_solver_refuses_unsatisfiable_room(self):
        big = self.asset(dimensions=[5, 5, 2])
        stage = self.stage([3, 3, 3])
        stage = self.add(stage, big, "big")
        with self.assertRaisesRegex(RuntimeError, "No feasible layout"):
            self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertIsNone(self.prod.get_plan(self.pid, self.scene_id)["layout"])

    def test_solver_budget_exhaustion_is_explicit(self):
        large = self.asset(dimensions=[6, 5, 1])
        stage = self.stage([8, 6, 3])
        stage = self.add(stage, large, "first")
        stage = self.add(stage, large, "second")
        with self.assertRaisesRegex(RuntimeError, "budget"):
            self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"], max_nodes=1)

    def test_validator_rejects_overlap_and_out_of_bounds(self):
        a = self.asset()
        assets = {a["asset_id"]: a}
        requests = [{"instance_id": "left", "asset_id": a["asset_id"], "wall": None, "attachment": None},
                    {"instance_id": "right", "asset_id": a["asset_id"], "wall": None, "attachment": None}]
        bad = {"left": {"asset_id": a["asset_id"], "x": 2, "y": 2, "z": 0, "rotation": 0},
               "right": {"asset_id": a["asset_id"], "x": 2, "y": 2, "z": 0, "rotation": 0}}
        with self.assertRaisesRegex(ValueError, "overlap"):
            verify_layout([8, 6, 3], requests, bad, assets)
        bad["right"]["x"] = 100
        with self.assertRaisesRegex(ValueError, "outside room"):
            verify_layout([8, 6, 3], requests, bad, assets)

    def test_approval_gate_and_durable_export(self):
        a = self.asset()
        stage = self.stage()
        stage = self.add(stage, a, "table")
        with self.assertRaisesRegex(RuntimeError, "approve layout"):
            self.prod.export_manifest(self.pid, self.scene_id)
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        with self.assertRaisesRegex(RuntimeError, "approve layout"):
            self.prod.export_manifest(self.pid, self.scene_id)
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertEqual(stage["approval_state"], "approved")
        exported = ProductionScene(Studio(self.path)).export_manifest(self.pid, self.scene_id)
        self.assertEqual(exported["instances"][0]["asset_id"], a["asset_id"])
        self.assertEqual(exported["layout_sha256"], stage["layout_sha"])
        self.assertEqual(exported["room_m"], [8, 6, 3])

    def test_approved_stage_immutable_except_explicit_resync(self):
        a = self.asset()
        stage = self.stage()
        stage = self.add(stage, a, "table")
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            self.add(stage, a, "another")
        reopened = self.prod.resync_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertEqual(reopened["approval_state"], "proposed")
        self.assertIsNone(reopened["layout"])
        self.assertEqual(reopened["instances"][0]["instance_id"], "table")
        self.assertGreater(len(self.prod.history(self.pid, self.scene_id)), 1)

    def test_screenplay_edit_invalidates_export_until_resync(self):
        a = self.asset()
        stage = self.stage()
        stage = self.add(stage, a, "table")
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.studio.save_screenplay(self.pid, SCRIPT.replace("key?", "door?"), 1)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.prod.export_manifest(self.pid, self.scene_id)
        stage = self.prod.resync_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertEqual(stage["approval_state"], "proposed")
        self.assertIsNone(stage["layout"])

    def test_no_scene_id_reuse_after_heading_rename(self):
        self.stage()
        self.studio.save_screenplay(self.pid, SCRIPT.replace("KITCHEN", "OFFICE"), 1)
        with self.assertRaises(KeyError):
            self.prod.export_manifest(self.pid, self.scene_id)

    def test_conflicting_plan_revision_refused(self):
        a = self.asset()
        stage = self.stage()
        self.add(stage, a, "table")
        with self.assertRaisesRegex(RuntimeError, "changed elsewhere"):
            self.add(stage, a, "stale")

    def test_cross_project_asset_and_export_denied(self):
        a = self.asset()
        second = self.studio.create_project("Other", "x")
        other = self.studio.save_screenplay(second["id"], SCRIPT, 0)
        prod2 = self.prod.stage_scene(second["id"], other["scenes"][0]["id"])
        with self.assertRaises(KeyError):
            self.prod.add_instance(second["id"], other["scenes"][0]["id"], a["asset_id"], "theft", prod2["plan_revision"])
        self.assertEqual(self.prod.list_assets(second["id"]), [])

    def test_tampered_layout_detected_before_export(self):
        a = self.asset()
        stage = self.stage()
        stage = self.add(stage, a, "table")
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        with self.studio._connection() as db:
            row = json.loads(db.execute("SELECT layout_json FROM prod_plans WHERE project_id=? AND scene_id=?", (self.pid, self.scene_id)).fetchone()[0])
            row["placements"]["table"]["x"] += 0.5
            db.execute("UPDATE prod_plans SET layout_json=? WHERE project_id=? AND scene_id=?", (json.dumps(row), self.pid, self.scene_id))
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            self.prod.export_manifest(self.pid, self.scene_id)

    def test_blender_script_uses_json_data_not_executable_asset_name(self):
        a = self.asset("Chair's End")
        stage = self.stage()
        stage = self.add(stage, a, "chair")
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        script = self.prod.export_blender_script(self.pid, self.scene_id)
        ast.parse(script)
        self.assertIn('json.loads(', script)
        self.assertIn('primitive_cube_add', script)
        self.assertNotIn('exec(', script)
        self.assertNotIn('subprocess', script)
        self.assertIn("Chair\\'s End", script)  # escaped by a Python string literal
        injected_manifest = self.prod.export_manifest(self.pid, self.scene_id)
        injected_manifest["instances"][0]["name"] = "x'; __import__('os').system('nope'); #"
        tree = ast.parse(blender_script(injected_manifest))
        # The injected text must only occur in the literal passed to json.loads.
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                             and node.func.attr == "system" for node in ast.walk(tree)))

    def test_blender_script_stages_camera_floor_and_light(self):
        stage = self.stage()
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        script = self.prod.export_blender_script(self.pid, self.scene_id)
        self.assertIn('NVP_Establishing_Camera', script)
        self.assertIn('NVP_FLOOR', script)
        self.assertIn('NVP_Overhead_Key', script)
        self.assertIn('save_as_mainfile', script)

    def test_scene_staging_does_not_change_screenplay_or_director_shots(self):
        initial = self.studio.plan_scene(self.pid, self.scene_id)
        shot = initial["scenes"][0]["shots"][0]
        approved = self.studio.edit_shot(self.pid, self.scene_id, shot["shot_id"],
            framing="close_up", subject="MARA", intent="Reveal suspicion",
            notes="Pinned by director", approved=True)
        a = self.asset()
        plan = self.stage()
        plan = self.add(plan, a, "table")
        plan = self.prod.solve_scene(self.pid, self.scene_id, plan["plan_revision"])
        self.prod.approve_scene(self.pid, self.scene_id, plan["plan_revision"])
        latest = self.studio.get_project(self.pid)
        self.assertEqual(latest["screenplay"], approved["screenplay"])
        self.assertEqual(latest["revision"], approved["revision"])
        self.assertEqual(latest["scenes"][0]["shots"][0]["notes"], "Pinned by director")
        self.assertEqual(latest["scenes"][0]["shots"][0]["status"], "approved")

    def test_casefold_duplicate_asset_identity_rejected(self):
        self.asset("Mara", "character", [.6, .6, 1.6])
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.asset("MARA", "character", [.6, .6, 1.6])

    def test_same_asset_can_be_reused_in_multiple_script_scenes(self):
        table = self.asset()
        first = self.stage()
        first = self.add(first, table, "table")
        second_scene = self.project["scenes"][1]["id"]
        second = self.prod.stage_scene(self.pid, second_scene, [8, 6, 3])
        second = self.prod.add_instance(self.pid, second_scene, table["asset_id"],
                                         "table_again", second["plan_revision"])
        self.assertEqual(first["instances"][0]["asset_id"], second["instances"][0]["asset_id"])

    def test_changed_screenplay_during_solve_cannot_commit_old_layout(self):
        from unittest.mock import patch
        import backend.nvp_production_scene as module
        a = self.asset()
        stage = self.stage()
        stage = self.add(stage, a, "table")
        original = module.solve_layout
        def update_during_solve(*args, **kwargs):
            result = original(*args, **kwargs)
            self.studio.save_screenplay(self.pid, SCRIPT.replace("key?", "door?"), 1)
            return result
        with patch.object(module, "solve_layout", update_during_solve):
            with self.assertRaisesRegex(RuntimeError, "Source scene changed"):
                self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        self.assertIsNone(self.prod.get_plan(self.pid, self.scene_id)["layout"])

    def test_independent_validator_refuses_invalid_wall_placement(self):
        table = self.asset()
        asset_map = {table["asset_id"]: table}
        item = {"instance_id": "table", "asset_id": table["asset_id"],
                "wall": "north", "attachment": None}
        with self.assertRaisesRegex(ValueError, "wall or anchor"):
            verify_layout([8,6,3], [item], {"table": {
                "asset_id": table["asset_id"], "x": 4, "y": 3, "z": 0, "rotation": 0}}, asset_map)

    def test_export_validation_fails_on_unknown_spoofed_asset(self):
        table = self.asset()
        stage = self.stage()
        stage = self.add(stage, table, "table")
        stage = self.prod.solve_scene(self.pid, self.scene_id, stage["plan_revision"])
        stage = self.prod.approve_scene(self.pid, self.scene_id, stage["plan_revision"])
        with self.studio._connection() as db:
            layout = json.loads(db.execute("SELECT layout_json FROM prod_plans WHERE project_id=? AND scene_id=?",
                                          (self.pid, self.scene_id)).fetchone()[0])
            layout["placements"]["table"]["asset_id"] = "AS_NOT_IN_PROJECT"
            db.execute("UPDATE prod_plans SET layout_json=? WHERE project_id=? AND scene_id=?",
                       (json.dumps(layout), self.pid, self.scene_id))
        with self.assertRaises(ValueError):
            self.prod.export_manifest(self.pid, self.scene_id)

    def test_stage_created_once_without_silent_overwrite(self):
        first = self.stage()
        with self.assertRaisesRegex(RuntimeError, "already staged"):
            self.stage()
        self.assertEqual(self.prod.get_plan(self.pid, self.scene_id)["plan_revision"], first["plan_revision"])

    def test_room_constraints_and_nonfinite_values_refused(self):
        for bad in ([8,6,float('inf')], [8,True,3], [1,1,1], [20,10,3]):
            with self.assertRaises(ValueError):
                validate_room(bad)

    def test_api_stage_solve_approve_export_round_trip(self):
        original = nvp_api.studio
        nvp_api.studio = self.studio
        try:
            with TestClient(nvp_api.app) as api:
                base = f"/api/projects/{self.pid}/production"
                a = api.post(base + "/assets", json={"name": "Worktable", "category": "furniture",
                    "dimensions": [2,1,.8], "anchors": {"front": [0,-.5,.6]}})
                self.assertEqual(a.status_code, 201, a.text)
                st = api.post(base + f"/scenes/{self.scene_id}/stage", json={"room": [8,6,3]})
                self.assertEqual(st.status_code, 201, st.text)
                added = api.post(base + f"/scenes/{self.scene_id}/instances", json={
                    "asset_id": a.json()["asset_id"], "instance_id": "desk", "wall": "north",
                    "expected_plan_revision": st.json()["plan_revision"]})
                self.assertEqual(added.status_code, 200, added.text)
                solved = api.post(base + f"/scenes/{self.scene_id}/solve", json={
                    "expected_plan_revision": added.json()["plan_revision"]})
                self.assertEqual(solved.status_code, 200, solved.text)
                approved = api.post(base + f"/scenes/{self.scene_id}/approve", json={
                    "expected_plan_revision": solved.json()["plan_revision"]})
                self.assertEqual(approved.status_code, 200, approved.text)
                exported = api.get(base + f"/scenes/{self.scene_id}/manifest")
                self.assertEqual(exported.status_code, 200, exported.text)
                self.assertEqual(exported.json()["instances"][0]["instance_id"], "desk")
                script = api.get(base + f"/scenes/{self.scene_id}/blender-script")
                self.assertEqual(script.status_code, 200, script.text)
                ast.parse(script.json()["script"])
        finally:
            nvp_api.studio = original

if __name__ == '__main__':
    unittest.main()
