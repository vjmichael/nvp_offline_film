"""Regressions for NVP's creator-controlled screenplay development."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.nvp_studio import Studio
from backend.nvp_idea_pipeline import (
    IdeaPipeline, LocalScriptModel, LocalModelUnavailable, local_llm_endpoint,
)
from backend import nvp_api


class FakeWriter:
    def complete(self, system, user):
        assert "human creator" in system.lower()
        assert "Original creator idea:" in user
        return "INT. PORCH - NIGHT\n\nA door opens.\n\nMAYA\nHello."


class TestCreativePipeline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Studio(self.temp.name + "/nvp.sqlite3")
        self.project = self.studio.create_project("Intersections", "A missing friend returns")
        self.pipeline = IdeaPipeline(self.studio, llm=FakeWriter())

    def tearDown(self):
        self.temp.cleanup()

    def test_ai_proposal_does_not_change_screenplay_until_approved(self):
        draft = self.pipeline.generate(self.project["id"], "screenplay", "Write a quieter opening")
        self.assertEqual(draft["status"], "proposed")
        self.assertEqual(draft["origin"], "local_ai")
        self.assertEqual(self.studio.get_project(self.project["id"])["screenplay"], "")
        updated = self.pipeline.decide(self.project["id"], draft["id"], "use_as_screenplay", 0)
        self.assertIn("INT. PORCH", updated["screenplay"])
        self.assertEqual(updated["revision"], 1)
        with self.assertRaises(RuntimeError):
            self.pipeline.decide(self.project["id"], draft["id"], "use_as_screenplay", 1)

    def test_editable_non_screenplay_draft(self):
        draft = self.pipeline.create(self.project["id"], "beat_sheet", "Beat one", "Keep it subtle")
        draft = self.pipeline.edit(self.project["id"], draft["id"], "Better beat one", 0)
        self.assertEqual(draft["edit_revision"], 1)
        with self.assertRaises(RuntimeError):
            self.pipeline.edit(self.project["id"], draft["id"], "Stale text", 0)
        self.pipeline.decide(self.project["id"], draft["id"], "accept", 0)
        self.assertEqual(self.studio.get_project(self.project["id"])["screenplay"], "")

    def test_old_screenplay_edits_are_recoverable(self):
        self.studio.save_screenplay(self.project["id"], "INT. HOME - DAY\n\nA door shuts.", 0)
        updated = self.studio.save_screenplay(self.project["id"], "INT. HOME - NIGHT\n\nA door shuts.", 1)
        revisions = self.studio.screenplay_history(self.project["id"])
        self.assertEqual([row["revision"] for row in revisions], [1, 0])
        restored = self.studio.restore_screenplay(self.project["id"], 1, updated["revision"])
        self.assertIn("DAY", restored["screenplay"])
        self.assertEqual(restored["revision"], 3)
        self.assertEqual(self.studio.screenplay_history(self.project["id"])[0]["revision"], 2)

    def test_approved_shots_survive_ai_rewrite_and_restore(self):
        first = self.studio.save_screenplay(self.project["id"], "INT. ROOM - DAY\n\nMAYA\nCome back.", 0)
        scene_id = first["scenes"][0]["id"]
        planned = self.studio.plan_scene(self.project["id"], scene_id)
        shot_id = planned["scenes"][0]["shots"][0]["shot_id"]
        self.studio.edit_shot(self.project["id"], scene_id, shot_id, framing="close_up",
                              subject="MAYA", intent="Show fear", notes="Approved by director", approved=True)
        draft = self.pipeline.generate(self.project["id"], "screenplay")
        rewritten = self.pipeline.decide(self.project["id"], draft["id"], "use_as_screenplay", 1)
        self.assertGreater(rewritten["archived_shots"], 0)
        recovered = self.studio.restore_screenplay(self.project["id"], 1, 2)
        shot = recovered["scenes"][0]["shots"][0]
        self.assertEqual(shot["notes"], "Approved by director")
        self.assertEqual(shot["status"], "approved")

    def test_stale_ai_proposal_cannot_replace_new_script(self):
        draft = self.pipeline.generate(self.project["id"], "screenplay")
        self.studio.save_screenplay(self.project["id"], "EXT. FIELD - DAY\n\nChanged story.", 0)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.pipeline.decide(self.project["id"], draft["id"], "use_as_screenplay", 1)

    def test_ai_completion_race_refused(self):
        class ChangingWriter:
            def complete(inner_self, system, user):
                self.studio.save_screenplay(self.project["id"], "INT. CABIN - DAY\n\nNew story.", 0)
                return "INT. HOUSE - NIGHT\n\nOld idea."
        self.pipeline.llm = ChangingWriter()
        with self.assertRaisesRegex(RuntimeError, "changed while the AI"):
            self.pipeline.generate(self.project["id"], "screenplay")
        self.assertEqual(self.pipeline.list(self.project["id"]), [])

    def test_local_writing_provider_restricts_remote_endpoints(self):
        with patch.dict(os.environ, {"NVP_LLM_URL": "https://example.com/v1/chat/completions"}):
            with self.assertRaises(ValueError):
                local_llm_endpoint()
        with patch.dict(os.environ, {"NVP_LLM_URL": "http://127.0.0.1:8080/v1/chat/completions"}):
            self.assertEqual(local_llm_endpoint(), os.environ["NVP_LLM_URL"])
        with self.assertRaises(LocalModelUnavailable):
            LocalScriptModel(endpoint="").complete("x", "y")

    def test_api_creative_round_trip(self):
        previous = nvp_api.studio
        nvp_api.studio = self.studio
        try:
            api = TestClient(nvp_api.app)
            self.assertFalse(api.get("/api/creative/status").json()["film_renderer_connected"])
            base = f"/api/projects/{self.project['id']}"
            draft = api.post(base + "/creative-drafts", json={
                "stage": "screenplay", "content": "INT. BUS - DAY\n\nThe engine stalls."})
            self.assertEqual(draft.status_code, 201)
            applied = api.post(base + "/creative-drafts/" + draft.json()["id"] + "/decision", json={
                "decision": "use_as_screenplay", "expected_project_revision": 0})
            self.assertEqual(applied.status_code, 200)
            self.assertEqual(api.get(base + "/screenplay-history").json()[0]["revision"], 0)
            restored = api.post(base + "/screenplay-history/0/restore", json={"expected_revision": 1})
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(restored.json()["screenplay"], "")
        finally:
            nvp_api.studio = previous


if __name__ == "__main__":
    unittest.main()
