"""NVP-WRITE-04: approved Story Bible writing integration regressions."""
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_idea_pipeline import IdeaPipeline
from backend import nvp_api

SCENE = "INT. COTTAGE - NIGHT\n\nMARA\nDon't open it.\n\nEXT. ROAD - DAY\n\nBOB\nI came back.\n"


class Writer:
    def __init__(self):
        self.calls = []
        self.on_generation = None

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.on_generation:
            self.on_generation()
        return "INT. COTTAGE - NIGHT\n\nMARA\nI remember the key."


class ApprovedBibleWritingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "film.sqlite3"
        self.studio = Studio(self.path)
        self.bible = StoryBible(self.studio)
        self.pid = self.studio.create_project("Door", "Mara investigates a locked room")["id"]
        self.writer = Writer()
        self.pipe = IdeaPipeline(self.studio, self.writer)

    def tearDown(self):
        self.tmp.cleanup()

    def character(self, name="Mara"):
        return self.bible.create_entity(self.pid, "character", name)

    def fact(self, entity, key, value, scope="global", approve=True):
        p = self.bible.propose_fact(self.pid, entity["id"], key, value, scope)
        if approve:
            latest = self.bible.get_entity(self.pid, entity["id"])
            self.bible.decide_fact(self.pid, p["id"], "accept", latest["revision"])
        return p

    def replace(self, entity, original, key, value):
        p = self.bible.propose_fact(self.pid, entity["id"], key, value)
        latest = self.bible.get_entity(self.pid, entity["id"])
        self.bible.decide_fact(self.pid, p["id"], "accept", latest["revision"], original["id"])

    def test_approved_facts_enter_prompt_but_proposals_do_not(self):
        mara = self.character()
        self.fact(mara, "cannot_drive", "Mara has never learned to drive")
        self.fact(mara, "robot_secret", "SECRET ROBOT", approve=False)
        draft = self.pipe.generate(self.pid, "screenplay")
        prompt = self.writer.calls[-1][1]
        self.assertIn("never learned to drive", prompt)
        self.assertNotIn("SECRET ROBOT", prompt)
        self.assertEqual(draft["bible_context_status"], "current")
        self.assertEqual(self.studio.get_project(self.pid)["screenplay"], "")

    def test_scene_scope_requires_explicit_link(self):
        project = self.studio.save_screenplay(self.pid, SCENE, 0)
        mara, bob = self.character(), self.character("Bob")
        self.fact(mara, "owns_key", "old brass key")
        self.fact(bob, "cannot_swim", "Bob cannot swim")
        scene_id = project["scenes"][0]["id"]
        self.pipe.generate(self.pid, "screenplay", scene_id=scene_id)
        self.assertIn("NO APPROVED BIBLE ENTITIES LINKED", self.writer.calls[-1][1])
        latest = self.bible.get_entity(self.pid, mara["id"])
        self.bible.link_scene(self.pid, mara["id"], scene_id, latest["revision"])
        self.pipe.generate(self.pid, "screenplay", scene_id=scene_id)
        self.assertIn("old brass key", self.writer.calls[-1][1])
        self.assertNotIn("Bob cannot swim", self.writer.calls[-1][1])

    def test_scoped_knowledge_is_labeled_not_assumed_chronological(self):
        mara = self.character()
        self.fact(mara, "knows_secret", "does not know about key", "before_reveal")
        self.fact(mara, "knows_secret", "knows Bob has key", "after_reveal")
        self.pipe.generate(self.pid, "screenplay")
        text = self.writer.calls[-1][1]
        self.assertIn("scope=before_reveal", text)
        self.assertIn("scope=after_reveal", text)
        self.assertIn("not an inferred timeline", text)

    def test_canon_change_during_ai_completion_refuses_save(self):
        mara = self.character()
        old = self.fact(mara, "cannot_drive", "cannot drive")
        self.writer.on_generation = lambda: self.replace(mara, old, "cannot_drive", "can drive")
        with self.assertRaisesRegex(RuntimeError, "Story Bible changed while AI"):
            self.pipe.generate(self.pid, "screenplay")
        self.assertFalse(self.pipe.list(self.pid))

    def test_canon_change_after_generation_blocks_approval_not_discard(self):
        mara = self.character()
        old = self.fact(mara, "cannot_drive", "cannot drive")
        draft = self.pipe.generate(self.pid, "screenplay")
        self.replace(mara, old, "cannot_drive", "can drive")
        self.assertEqual(self.pipe.get(self.pid, draft["id"])["bible_context_status"], "needs_review")
        with self.assertRaisesRegex(RuntimeError, "Story Bible canon changed"):
            self.pipe.decide(self.pid, draft["id"], "use_as_screenplay", 0)
        self.assertEqual(self.studio.get_project(self.pid)["screenplay"], "")
        self.pipe.decide(self.pid, draft["id"], "discard", 0)

    def test_approved_upstream_context_must_stay_current(self):
        mara = self.character()
        old = self.fact(mara, "owns_key", "red key")
        draft = self.pipe.create(self.pid, "synopsis", "Mara wants the key")
        self.pipe.decide(self.pid, draft["id"], "accept", 0)
        self.replace(mara, old, "owns_key", "blue key")
        with self.assertRaisesRegex(RuntimeError, "Earlier accepted story stages"):
            self.pipe.generate(self.pid, "beat_sheet")

    def test_unapproved_fact_has_no_staleness_effect(self):
        mara = self.character()
        self.fact(mara, "cannot_drive", "cannot drive")
        draft = self.pipe.generate(self.pid, "screenplay")
        self.fact(mara, "robot_secret", "speculative robot", approve=False)
        self.assertEqual(self.pipe.get(self.pid, draft["id"])["bible_context_status"], "current")

    def test_restart_persists_snapshot_and_prevents_stale_approval(self):
        mara = self.character()
        old = self.fact(mara, "eye_color", "blue")
        draft = self.pipe.generate(self.pid, "screenplay")
        reopen = IdeaPipeline(Studio(self.path))
        self.assertEqual(reopen.get(self.pid, draft["id"])["bible_context_status"], "current")
        self.replace(mara, old, "eye_color", "brown")
        self.assertEqual(reopen.get(self.pid, draft["id"])["bible_context_status"], "needs_review")

    def test_other_project_never_leaks_canon(self):
        mara = self.character()
        self.fact(mara, "secret", "PRIVATE MOVIE SECRET")
        second = self.studio.create_project("Another", "Different plot")["id"]
        self.pipe.generate(second, "screenplay")
        self.assertNotIn("PRIVATE MOVIE SECRET", self.writer.calls[-1][1])

    def test_prompt_budget_does_not_erase_durable_canon_fence(self):
        mara = self.character()
        for i in range(8):
            self.fact(mara, f"fact_{i}", "value_" + "X" * 1400)
        snapshot = self.pipe.bible_context(self.pid)
        self.assertLess(len(snapshot["text"]), 9500)
        self.assertIn("OMITTED", snapshot["text"])
        draft = self.pipe.generate(self.pid, "screenplay")
        old = self.bible.get_entity(self.pid, mara["id"])["facts"][-1]
        self.replace(mara, old, old["fact_key"], "revised")
        self.assertEqual(self.pipe.get(self.pid, draft["id"])["bible_context_status"], "needs_review")

    def test_named_character_without_facts_enters_canon_and_rename_stales(self):
        mara = self.character()
        draft = self.pipe.generate(self.pid, "screenplay")
        self.assertIn("[no approved facts yet]", self.writer.calls[-1][1])
        self.assertEqual(draft["bible_facts_total"], 0)
        current = self.bible.get_entity(self.pid, mara["id"])
        self.bible.rename_entity(self.pid, mara["id"], "Mara Wells", current["revision"])
        self.assertEqual(self.pipe.get(self.pid, draft["id"])["bible_context_status"], "needs_review")

    def test_new_character_mid_completion_invalidates_whole_project_snapshot(self):
        self.writer.on_generation = lambda: self.character("Unknown Witness")
        with self.assertRaisesRegex(RuntimeError, "Story Bible changed while AI"):
            self.pipe.generate(self.pid, "screenplay")
        self.assertEqual(self.pipe.list(self.pid), [])

    def test_api_scoped_preview_and_missing_project(self):
        mara = self.character()
        self.fact(mara, "cannot_drive", "cannot drive")
        saved = nvp_api.studio
        nvp_api.studio = self.studio
        try:
            with TestClient(nvp_api.app) as client:
                r = client.get(f"/api/projects/{self.pid}/creative/bible-context")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["facts_total"], 1)
                self.assertEqual(client.get("/api/projects/none/creative/bible-context").status_code, 404)
        finally:
            nvp_api.studio = saved


if __name__ == "__main__":
    unittest.main()
