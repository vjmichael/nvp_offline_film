"""Story chronology and character knowledge are explicitly authored, never guessed."""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_story_timeline import StoryTimeline
from backend.nvp_idea_pipeline import IdeaPipeline
from backend import nvp_api

# The flashback is written second, but precedes the reunion in story time.
SCRIPT = "INT. DINER - NIGHT\n\nMARA\nYou know now.\n\nEXT. PIER - DAWN\n\nMARA\nI found it.\n"


class FakeWriter:
    def __init__(self):
        self.calls = []
        self.side_effect = None

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.side_effect:
            self.side_effect()
        return "INT. DINER - NIGHT\n\nMARA\nI know who did it."


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "project.sqlite"
        self.studio = Studio(self.db)
        self.bible = StoryBible(self.studio)
        self.timeline = StoryTimeline(self.studio)
        self.project = self.studio.create_project("Pier", "Mara learns the truth")
        self.pid = self.project["id"]
        self.script = self.studio.save_screenplay(self.pid, SCRIPT, 0)
        self.diner, self.pier = [s["id"] for s in self.script["scenes"]]
        self.mara = self.bible.create_entity(self.pid, "character", "Mara")
        self.fact = self.bible.propose_fact(self.pid, self.mara["id"], "culprit", "Bob")
        self.bible.decide_fact(self.pid, self.fact["id"], "accept",
                               self.bible.get_entity(self.pid, self.mara["id"])["revision"])
        self.finds = self.bible.create_entity(self.pid, "event", "Finds evidence")
        self.reveals = self.bible.create_entity(self.pid, "event", "Reveals evidence")
        self.other = self.bible.create_entity(self.pid, "event", "Elsewhere unknown")
        self.writer = FakeWriter()
        self.pipeline = IdeaPipeline(self.studio, self.writer)

    def tearDown(self):
        self.tmp.cleanup()

    def edge(self, before=None, after=None):
        return self.timeline.add_precedence(self.pid, before or self.finds["id"],
                                            after or self.reveals["id"],
                                            self.timeline.revision(self.pid))

    def mark(self, scene, event, phase="after"):
        return self.timeline.bind_scene(self.pid, scene, event,
                                        phase, self.timeline.revision(self.pid))

    def accepted_knowledge(self, event=None):
        proposed = self.timeline.propose_knowledge(self.pid, self.mara["id"], self.fact["id"],
                                                   event)
        return self.timeline.decide_knowledge(self.pid, proposed["id"], "accept",
                                              self.timeline.revision(self.pid))

    def link_mara(self, scene):
        return self.bible.link_scene(self.pid, self.mara["id"], scene,
                                     self.bible.get_entity(self.pid, self.mara["id"])["revision"])

    def know(self, scene):
        return self.timeline.snapshot(self.pid, scene)["knowledge"][0]["state"]

    def test_partial_order_flashback_is_not_screenplay_order(self):
        self.edge()
        self.mark(self.pier, self.finds["id"], "before")
        self.mark(self.diner, self.reveals["id"], "before")
        self.accepted_knowledge(self.finds["id"])
        self.assertEqual(self.know(self.pier), "not_yet")
        self.assertEqual(self.know(self.diner), "known")
        # Diner appears first in the script, but is later in story time.
        self.assertEqual(self.script["scenes"][0]["id"], self.diner)

    def test_same_event_before_after_boundary(self):
        self.accepted_knowledge(self.finds["id"])
        self.mark(self.pier, self.finds["id"], "before")
        self.assertEqual(self.know(self.pier), "not_yet")
        self.mark(self.pier, self.finds["id"], "after")
        self.assertEqual(self.know(self.pier), "known")

    def test_indeterminate_never_claimed_known_or_unknown(self):
        self.accepted_knowledge(self.other["id"])
        self.mark(self.diner, self.reveals["id"])
        self.assertEqual(self.know(self.diner), "indeterminate")

    def test_unanchored_does_not_assume_scene_time(self):
        self.accepted_knowledge(self.finds["id"])
        self.assertEqual(self.know(self.diner), "unanchored")

    def test_known_before_story_only_with_explicit_approval(self):
        self.accepted_knowledge(None)
        self.assertEqual(self.know(self.diner), "known")

    def test_cycle_rejected_with_no_partial_mutation(self):
        self.edge()
        before = self.timeline.revision(self.pid)
        with self.assertRaisesRegex(RuntimeError, "cycle"):
            self.timeline.add_precedence(self.pid, self.reveals["id"],
                                         self.finds["id"], before)
        self.assertEqual(self.timeline.revision(self.pid), before)
        self.assertEqual(len(self.timeline.snapshot(self.pid)["edges"]), 1)

    def test_duplicate_and_stale_order_rejected(self):
        rev = self.timeline.revision(self.pid)
        self.edge()
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.timeline.add_precedence(self.pid, self.finds["id"],
                                         self.other["id"], rev)
        with self.assertRaisesRegex(RuntimeError, "already"):
            self.edge()

    def test_remove_edge_restores_incomparability(self):
        self.edge()
        self.mark(self.pier, self.finds["id"])
        self.accepted_knowledge(self.reveals["id"])
        self.assertEqual(self.know(self.pier), "not_yet")
        self.timeline.remove_precedence(self.pid, self.finds["id"],
                                         self.reveals["id"], self.timeline.revision(self.pid))
        self.assertEqual(self.know(self.pier), "indeterminate")

    def test_other_film_events_and_characters_are_not_valid(self):
        second = self.studio.create_project("Other", "A second movie")
        eid = self.bible.create_entity(second["id"], "event", "Elsewhere")["id"]
        with self.assertRaises(KeyError):
            self.timeline.add_precedence(self.pid, eid, self.finds["id"],
                                         self.timeline.revision(self.pid))
        with self.assertRaises(KeyError):
            self.timeline.bind_scene(self.pid, self.diner, eid, "before",
                                     self.timeline.revision(self.pid))
        with self.assertRaises(KeyError):
            self.timeline.propose_knowledge(second["id"], self.mara["id"], self.fact["id"])

    def test_character_is_not_a_valid_event(self):
        with self.assertRaises(KeyError):
            self.timeline.add_precedence(self.pid, self.mara["id"], self.finds["id"],
                                         self.timeline.revision(self.pid))

    def test_knowledge_requires_accepted_same_film_fact(self):
        p = self.bible.propose_fact(self.pid, self.mara["id"], "unconfirmed", "Speculation")
        with self.assertRaisesRegex(RuntimeError, "approved"):
            self.timeline.propose_knowledge(self.pid, self.mara["id"], p["id"], self.finds["id"])
        self.assertFalse(self.timeline.snapshot(self.pid)["knowledge"])

    def test_proposal_does_not_make_character_know_fact(self):
        self.timeline.propose_knowledge(self.pid, self.mara["id"], self.fact["id"], self.finds["id"])
        self.mark(self.diner, self.finds["id"])
        self.assertEqual(self.timeline.snapshot(self.pid, self.diner)["knowledge"], [])

    def test_knowledge_approval_is_optimistic_and_no_double_approval(self):
        one = self.timeline.propose_knowledge(self.pid, self.mara["id"], self.fact["id"], self.finds["id"])
        two = self.timeline.propose_knowledge(self.pid, self.mara["id"], self.fact["id"], self.reveals["id"])
        stale = self.timeline.revision(self.pid)
        self.timeline.decide_knowledge(self.pid, one["id"], "accept", stale)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.timeline.decide_knowledge(self.pid, two["id"], "accept", stale)
        with self.assertRaisesRegex(RuntimeError, "already approved"):
            self.timeline.decide_knowledge(self.pid, two["id"], "accept", self.timeline.revision(self.pid))

    def test_superseded_fact_flags_knowledge_as_stale(self):
        self.accepted_knowledge(self.finds["id"])
        new = self.bible.propose_fact(self.pid, self.mara["id"], "culprit", "Alice")
        self.bible.decide_fact(self.pid, new["id"], "accept",
                               self.bible.get_entity(self.pid,self.mara["id"])["revision"],
                               self.fact["id"])
        self.mark(self.diner, self.finds["id"])
        self.link_mara(self.diner)
        self.assertEqual(self.know(self.diner), "source_fact_changed")
        prompt = self.pipeline.bible_context(self.pid, self.diner)["timeline"]["text"]
        self.assertIn("SOURCE_FACT_CHANGED", prompt)

    def test_removed_or_changed_scene_mark_is_not_silently_reused(self):
        self.mark(self.diner, self.reveals["id"])
        new_script = SCRIPT.replace("You know now.", "You must leave.")
        self.studio.save_screenplay(self.pid, new_script, 1)
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.timeline.snapshot(self.pid, self.diner)
        self.mark(self.diner, self.reveals["id"])
        self.assertEqual(self.timeline.snapshot(self.pid, self.diner)["scene_marker"]["phase"], "after")

    def test_persisted_graph_knowledge_and_links_survive_restart(self):
        self.edge()
        self.accepted_knowledge(self.finds["id"])
        self.mark(self.diner, self.reveals["id"])
        new = StoryTimeline(Studio(self.db))
        self.assertEqual(len(new.snapshot(self.pid)["edges"]), 1)
        self.assertEqual(new.snapshot(self.pid, self.diner)["knowledge"][0]["state"], "known")

    def test_prompt_separates_objective_facts_from_character_awareness(self):
        self.edge()
        self.mark(self.diner, self.finds["id"], "before")
        self.link_mara(self.diner)
        self.accepted_knowledge(self.reveals["id"])
        self.pipeline.generate(self.pid, "screenplay", scene_id=self.diner)
        content = self.writer.calls[-1][1]
        self.assertIn("[KNOWLEDGE: NOT_YET]", content)
        self.assertIn("Character knowledge and explicit story-event timing", content)
        self.assertIn("story time", content)

    def test_chronology_change_during_model_completion_aborts_proposal(self):
        self.edge()
        self.writer.side_effect = lambda: self.timeline.remove_precedence(
            self.pid, self.finds["id"], self.reveals["id"], self.timeline.revision(self.pid))
        with self.assertRaisesRegex(RuntimeError, "Story Bible changed"):
            self.pipeline.generate(self.pid, "screenplay")
        self.assertFalse(self.pipeline.list(self.pid))

    def test_new_edge_after_generation_requires_reapproval(self):
        draft = self.pipeline.generate(self.pid, "screenplay")
        self.edge()
        self.assertEqual(self.pipeline.get(self.pid, draft["id"])["bible_context_status"], "needs_review")
        with self.assertRaisesRegex(RuntimeError, "canon changed"):
            self.pipeline.decide(self.pid, draft["id"], "use_as_screenplay", 1)
        self.assertEqual(self.studio.get_project(self.pid)["screenplay"], SCRIPT)

    def test_unapproved_knowledge_does_not_invalidate_existing_draft(self):
        draft = self.pipeline.generate(self.pid, "screenplay")
        self.timeline.propose_knowledge(self.pid, self.mara["id"], self.fact["id"], self.finds["id"])
        self.assertEqual(self.pipeline.get(self.pid, draft["id"])["bible_context_status"], "current")

    def test_api_round_trip_with_explicit_phase_and_knowledge(self):
        existing = nvp_api.studio
        nvp_api.studio = self.studio
        try:
            with TestClient(nvp_api.app) as client:
                root = f"/api/projects/{self.pid}/timeline"
                r = client.get(root)
                self.assertEqual(r.status_code, 200)
                rev = r.json()["revision"]
                order = client.post(root + "/precedence", json={
                    "before_id": self.finds["id"], "after_id": self.reveals["id"],
                    "expected_revision": rev,
                })
                self.assertEqual(order.status_code, 200)
                bind = client.put(root + "/scenes/" + self.diner, json={
                    "event_id": self.reveals["id"], "phase": "before",
                    "expected_revision": order.json()["revision"],
                })
                self.assertEqual(bind.status_code, 200)
                proposal = client.post(root + "/knowledge", json={
                    "character_id": self.mara["id"], "fact_id": self.fact["id"],
                    "learned_at_event_id": self.finds["id"],
                })
                self.assertEqual(proposal.status_code, 201)
                approve = client.post(root + "/knowledge/" + proposal.json()["id"] + "/decision",
                    json={"decision": "accept", "expected_revision": bind.json()["revision"]})
                self.assertEqual(approve.status_code, 200)
                view = client.get(root + "?scene_id=" + self.diner)
                self.assertEqual(view.json()["knowledge"][0]["state"], "known")
                self.assertEqual(client.get("/api/projects/missing/timeline").status_code, 404)
        finally:
            nvp_api.studio = existing


if __name__ == "__main__":
    unittest.main()
