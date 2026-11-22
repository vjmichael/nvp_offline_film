"""Film-only creator-approved story progression and stale-decision regressions."""
import tempfile
import unittest

from fastapi.testclient import TestClient
from backend.nvp_studio import Studio
from backend.nvp_idea_pipeline import IdeaPipeline
from backend.nvp_story_context import APPROVED_STAGE_LIMITS, build_story_messages
from backend import nvp_api


class CapturingWriter:
    def __init__(self, text="INT. GARAGE - NIGHT\n\nLEAH\nStay here."):
        self.text = text
        self.calls = []
        self.on_complete = None

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.on_complete:
            self.on_complete()
        return self.text


class StoryContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Studio(self.tmp.name + "/film.sqlite3")
        self.movie = self.store.create_project("Last Stop", "A driver finds her lost friend")
        self.writer = CapturingWriter()
        self.pipe = IdeaPipeline(self.store, self.writer)
        self.pid = self.movie["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def accept(self, stage, text):
        d = self.pipe.create(self.pid, stage, text)
        self.pipe.decide(self.pid, d["id"], "accept", self.store.get_project(self.pid)["revision"])
        return d

    def test_approved_logline_and_synopsis_reach_beat_prompt(self):
        self.accept("logline", "LEAH carries a brass compass she won't surrender.")
        self.accept("synopsis", "The compass points to the last passenger's sister.")
        self.writer.text = "1. Night bus crosses the bridge."
        draft = self.pipe.generate(self.pid, "beat_sheet", "Quiet thriller")
        prompt = self.writer.calls[-1][1]
        self.assertIn("[CREATOR-APPROVED LOGLINE]", prompt)
        self.assertIn("brass compass", prompt)
        self.assertIn("[CREATOR-APPROVED SYNOPSIS]", prompt)
        self.assertIn("last passenger's sister", prompt)
        self.assertIn("numbered dramatic beats", prompt)
        self.assertEqual([x["stage"] for x in draft["upstream_sources"]],
                         ["logline", "synopsis"])
        self.assertEqual(draft["context_status"], "current")
        self.assertEqual(self.store.get_project(self.pid)["screenplay"], "")

    def test_unapproved_ai_draft_never_becomes_canon(self):
        self.pipe.create(self.pid, "logline", "ALL CHARACTERS ARE SECRETLY ROBOTS", origin="local_ai")
        self.writer.text = "The friend returns home."
        self.pipe.generate(self.pid, "synopsis")
        self.assertNotIn("SECRETLY ROBOTS", self.writer.calls[-1][1])
        self.assertIn("No earlier writing stage has been approved", self.writer.calls[-1][1])

    def test_changed_upstream_is_detected_and_requires_review(self):
        old = self.accept("logline", "LEAH is looking for her sister.")
        synopsis = self.accept("synopsis", "LEAH follows the last bus.")
        self.accept("logline", "LEAH is looking for her brother, not her sister.")
        annotated = self.pipe.get(self.pid, synopsis["id"])
        self.assertEqual(annotated["context_status"], "needs_review")
        self.assertEqual(annotated["changed_upstream_stages"], ["logline"])
        with self.assertRaisesRegex(RuntimeError, "out of date"):
            self.pipe.generate(self.pid, "beat_sheet")
        # Repair from the earliest affected stage, then resume.
        self.assertEqual([x["stage"] for x in self.pipe.approved_story(self.pid, "synopsis")], ["logline"])
        self.accept("synopsis", "LEAH investigates where her brother boarded.")
        self.pipe.generate(self.pid, "beat_sheet")
        self.assertIn("brother boarded", self.writer.calls[-1][1])
        self.assertEqual(self.pipe.get(self.pid, old["id"])["status"], "accepted")

    def test_stale_proposal_cannot_be_approved_but_can_be_discarded(self):
        self.accept("logline", "LEAH owns the compass")
        proposed = self.pipe.create(self.pid, "synopsis", "LEAH follows the compass")
        self.accept("logline", "MIRA owns the compass")
        with self.assertRaisesRegex(RuntimeError, "context changed"):
            self.pipe.decide(self.pid, proposed["id"], "accept", 0)
        self.pipe.decide(self.pid, proposed["id"], "discard", 0)
        self.assertEqual(self.pipe.get(self.pid, proposed["id"])["status"], "discarded")

    def test_stale_upstream_prevents_new_manual_approval(self):
        self.accept("logline", "LEAH owns the compass")
        self.accept("synopsis", "LEAH returns with the compass")
        self.accept("logline", "MIRA owns the compass")
        manual = self.pipe.create(self.pid, "beat_sheet", "1. LEAH boards the ferry")
        with self.assertRaisesRegex(RuntimeError, "need review"):
            self.pipe.decide(self.pid, manual["id"], "accept", 0)
        self.assertEqual(self.pipe.get(self.pid, manual["id"])["status"], "proposed")

    def test_newest_approval_wins_without_deleting_prior_decision(self):
        earlier = self.accept("logline", "The first creator choice")
        later = self.accept("logline", "A revised creator choice")
        active = self.pipe.approved_story(self.pid, "synopsis")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], later["id"])
        self.assertEqual(self.pipe.get(self.pid, earlier["id"])["status"], "accepted")

    def test_ai_generation_race_rejects_changed_approved_decisions(self):
        self.accept("logline", "First approved premise")
        def approve_during_inference():
            self.accept("logline", "Second approved premise")
        self.writer.on_complete = approve_during_inference
        with self.assertRaisesRegex(RuntimeError, "Accepted story decisions changed"):
            self.pipe.generate(self.pid, "screenplay")
        self.assertFalse(any(x["stage"] == "screenplay" for x in self.pipe.list(self.pid)))
        self.assertEqual(self.store.get_project(self.pid)["screenplay"], "")

    def test_story_context_survives_database_reopen(self):
        self.accept("logline", "LEAH carries the compass")
        result = self.pipe.generate(self.pid, "screenplay")
        reopened = IdeaPipeline(Studio(self.tmp.name + "/film.sqlite3"))
        saved = reopened.get(self.pid, result["id"])
        self.assertEqual(saved["context_status"], "current")
        self.assertEqual(len(saved["upstream_sources"]), 1)
        self.assertEqual(saved["upstream_sources"][0]["stage"], "logline")

    def test_story_projects_do_not_leak_approved_decisions(self):
        self.accept("logline", "SECRET COMPASS IS BLUE")
        other = self.store.create_project("Second Film", "A rival crew meets")
        self.pipe.generate(other["id"], "screenplay")
        self.assertNotIn("SECRET COMPASS", self.writer.calls[-1][1])

    def test_long_approved_material_is_explicitly_truncated(self):
        self.accept("treatment", "A " * 60_000)
        self.pipe.generate(self.pid, "screenplay")
        prompt = self.writer.calls[-1][1]
        self.assertIn("EXCERPT TRUNCATED", prompt)
        self.assertLess(len(prompt), 20_000)
        self.assertIn("[CREATOR-APPROVED TREATMENT]", prompt)

    def test_screenplay_ai_uses_editor_line_references_without_modifying_source(self):
        screenplay = "INT. ROOM - DAY\n\nALEX\nWait.\n\nEXT. STREET - NIGHT\nSAM\nRun."
        project = self.store.get_project(self.pid)
        updated = self.store.save_screenplay(self.pid, screenplay, project["revision"])
        system, prompt = build_story_messages(updated, "screenplay", "Revise line 4", None, [])
        self.assertIn("L04 | Wait.", prompt)
        self.assertIn("L02 | ", prompt)
        self.assertIn("never include line labels", system)
        self.assertEqual(self.store.get_project(self.pid)["screenplay"], screenplay)
        selected = updated["scenes"][1]
        self.assertEqual(selected["start_line"], 6)
        _, focused = build_story_messages(updated, "screenplay", "Improve the dialogue", selected["id"], [])
        self.assertIn("L06 | EXT. STREET - NIGHT", focused)
        self.assertIn("L08 | Run.", focused)
        self.assertNotIn("L01 | INT. ROOM", focused)

    def test_older_stage_never_inherits_later_approved_content(self):
        self.accept("treatment", "LATE-STAGE OUTCOME: THE ALIEN SHIP CRASHES")
        self.pipe.generate(self.pid, "synopsis")
        self.assertNotIn("ALIEN SHIP", self.writer.calls[-1][1])

    def test_stage_system_rules_are_specific(self):
        project = self.store.get_project(self.pid)
        for stage, expected in (("logline", "one strong"), ("synopsis", "causally connected"),
                                ("beat_sheet", "numbered dramatic beats"), ("treatment", "filmable prose"),
                                ("screenplay", "Fountain screenplay scenes")):
            _, prompt = build_story_messages(project, stage, "", None, [])
            self.assertIn(expected, prompt)
        self.assertEqual(APPROVED_STAGE_LIMITS["treatment"], 6600)

    def test_api_exposes_approved_context_and_staleness(self):
        previous = nvp_api.studio
        nvp_api.studio = self.store
        try:
            self.accept("logline", "LEAH owns the map")
            with TestClient(nvp_api.app) as api:
                out = api.get(f"/api/projects/{self.pid}/approved-story?stage=synopsis")
            self.assertEqual(out.status_code, 200)
            self.assertEqual(out.json()["approved"][0]["stage"], "logline")
            self.assertEqual(out.json()["approved"][0]["context_status"], "current")
        finally:
            nvp_api.studio = previous

if __name__ == "__main__":
    unittest.main()
