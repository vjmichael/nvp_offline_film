"""Integration seam tests with a simulated *authoritative* Lu host port."""
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_lu_workspace import NvpLuWorkspace, LuHostError, build_writer_messages
from backend.nvp_studio import Studio
from backend.nvp_idea_pipeline import IdeaPipeline


class FakeTrustedLuHost:
    """Only a test fixture. The actual host must enforce these in Rust."""
    def __init__(self, studio, project_id):
        self.studio = studio
        self.project_id = project_id
        self.issued_scope = object()
        self.active = True
        self.granted = True
        self.inference_calls = 0
        self.saved_calls = 0
        self.blocked_before_save = False
        self.edits_while_inference = False

    def _check(self, scope):
        if scope is not self.issued_scope or not self.active or not self.granted:
            raise LuHostError("Lu host denies this workspace operation")

    def read_project(self, scope):
        self._check(scope)
        return self.studio.get_project(self.project_id)

    def generate_story(self, scope, system, user, *, max_new_tokens):
        self._check(scope)
        self.inference_calls += 1
        assert max_new_tokens == 2800
        assert "NVP" in system
        assert "Original creator idea" in user
        if self.edits_while_inference:
            old = self.studio.get_project(self.project_id)
            self.studio.save_screenplay(self.project_id, "EXT. FOREST - DAY\n\nA footstep.", old["revision"])
        if self.blocked_before_save:
            self.active = False
        return "INT. ROOM - NIGHT\n\nA door opens.\n\nMARA\nWhere are you?"

    def save_proposal(self, scope, *, stage, content, instructions, expected_revision):
        self._check(scope)
        project = self.studio.get_project(self.project_id)
        if project["revision"] != expected_revision:
            raise LuHostError("Lu project changed during inference")
        self.saved_calls += 1
        return IdeaPipeline(self.studio).create(
            self.project_id, stage, content, instructions,
            origin="local_ai", expected_project_revision=expected_revision)


class LuWorkspaceBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Studio(self.temp.name + "/nvp.db")
        self.project = self.studio.create_project("Doorway", "Mara searches for her sister")
        self.host = FakeTrustedLuHost(self.studio, self.project["id"])
        self.bridge = NvpLuWorkspace(self.host)

    def tearDown(self):
        self.temp.cleanup()

    def test_project_scoped_proposal_uses_lu_inference_only(self):
        # Even hostile NVP_LLM_URL cannot redirect this path: no HTTP model client.
        with patch.dict("os.environ", {"NVP_LLM_URL": "https://elsewhere.invalid"}):
            draft = self.bridge.propose(self.host.issued_scope, stage="screenplay")
        self.assertEqual(draft["status"], "proposed")
        self.assertEqual(self.host.inference_calls, 1)
        self.assertEqual(self.host.saved_calls, 1)
        self.assertEqual(self.studio.get_project(self.project["id"])["screenplay"], "")

    def test_missing_or_forged_scope_is_rejected_before_read(self):
        with self.assertRaises(LuHostError):
            self.bridge.propose(object(), stage="screenplay")
        with self.assertRaises(LuHostError):
            self.bridge.propose(None, stage="screenplay")
        self.assertEqual(self.host.inference_calls, 0)

    def test_suspended_workspace_denies_inference(self):
        self.host.active = False
        with self.assertRaises(LuHostError):
            self.bridge.propose(self.host.issued_scope, stage="screenplay")
        self.assertEqual(self.host.inference_calls, 0)

    def test_revocation_between_generation_and_commit_denies_write(self):
        self.host.blocked_before_save = True
        with self.assertRaises(LuHostError):
            self.bridge.propose(self.host.issued_scope, stage="screenplay")
        self.assertEqual(self.host.saved_calls, 0)
        self.assertEqual(IdeaPipeline(self.studio).list(self.project["id"]), [])

    def test_concurrent_manual_script_edit_denies_stale_draft(self):
        self.host.edits_while_inference = True
        with self.assertRaisesRegex(LuHostError, "changed"):
            self.bridge.propose(self.host.issued_scope, stage="screenplay")
        self.assertEqual(self.host.saved_calls, 0)
        self.assertIn("FOREST", self.studio.get_project(self.project["id"])["screenplay"])

    def test_invalid_model_output_cannot_be_persisted(self):
        self.host.generate_story = lambda *a, **kw: "Sorry, I cannot write a screenplay."
        with self.assertRaisesRegex(ValueError, "scene heading"):
            self.bridge.propose(self.host.issued_scope, stage="screenplay")
        self.assertEqual(self.host.saved_calls, 0)

    def test_invalid_stage_rejected_before_host_calls(self):
        with self.assertRaises(ValueError):
            self.bridge.propose(self.host.issued_scope, stage="film_everything")
        self.assertEqual(self.host.inference_calls, 0)

    def test_scene_specific_prompt_is_bound_to_given_scene(self):
        project = self.studio.save_screenplay(self.project["id"], "INT. ROOM - DAY\n\nMARA\nCome in.", 0)
        system, user = build_writer_messages(project, "screenplay", scene_id=project["scenes"][0]["id"])
        self.assertIn("INT. ROOM - DAY", user)
        with self.assertRaises(KeyError):
            build_writer_messages(project, "screenplay", scene_id="SC_invented")

    def test_long_context_is_labeled_as_excerpt(self):
        self.studio.save_screenplay(self.project["id"], "INT. ROOM - DAY\n\n" + "A"*18000, 0)
        _, user = build_writer_messages(self.studio.get_project(self.project["id"]), "synopsis")
        self.assertIn("Screenplay excerpt only", user)

    def test_host_rejected_non_proposal_result(self):
        self.host.save_proposal = lambda *a, **kw: {"status":"accepted"}
        with self.assertRaises(LuHostError):
            self.bridge.propose(self.host.issued_scope, stage="screenplay")

if __name__ == "__main__":
    unittest.main()
