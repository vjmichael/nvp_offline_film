"""Additional partial-order, stale-source, concurrency and scope regressions."""
import unittest
from tests.test_story_timeline import TimelineTests as _TimelineFixture


class TimelineInvariantTests(unittest.TestCase):
    # Reuse fixture helpers without inheriting another 21 test methods.
    setUp = _TimelineFixture.setUp
    tearDown = _TimelineFixture.tearDown
    edge = _TimelineFixture.edge
    mark = _TimelineFixture.mark
    accepted_knowledge = _TimelineFixture.accepted_knowledge
    link_mara = _TimelineFixture.link_mara
    know = _TimelineFixture.know

    def test_transitive_knowledge_proven_without_direct_edge(self):
        self.edge()
        self.timeline.add_precedence(self.pid, self.reveals["id"], self.other["id"],
                                     self.timeline.revision(self.pid))
        self.accepted_knowledge(self.finds["id"])
        self.mark(self.diner, self.other["id"], "before")
        self.assertEqual(self.know(self.diner), "known")

    def test_approved_order_fed_to_writing_model_without_screenplay_sort(self):
        self.edge()
        self.pipeline.generate(self.pid, "screenplay")
        prompt = self.writer.calls[-1][1]
        self.assertIn("[APPROVED STORY ORDER] Finds evidence BEFORE Reveals evidence", prompt)
        self.assertIn("screenplay", self.writer.calls[-1][0])

    def test_scene_anchor_changed_during_generation_refuses_write(self):
        self.mark(self.diner, self.reveals["id"], "before")
        self.link_mara(self.diner)
        self.writer.side_effect = lambda: self.mark(self.diner, self.reveals["id"], "after")
        with self.assertRaisesRegex(RuntimeError, "Story Bible changed"):
            self.pipeline.generate(self.pid, "screenplay", scene_id=self.diner)
        self.assertFalse(self.pipeline.list(self.pid))

    def test_stale_knowledge_does_not_leak_superseded_fact_value_into_prompt(self):
        self.accepted_knowledge(self.finds["id"])
        new = self.bible.propose_fact(self.pid, self.mara["id"], "culprit", "Alice")
        self.bible.decide_fact(self.pid, new["id"], "accept",
                               self.bible.get_entity(self.pid, self.mara["id"])["revision"],
                               self.fact["id"])
        self.mark(self.diner, self.finds["id"])
        self.link_mara(self.diner)
        self.pipeline.generate(self.pid, "screenplay", scene_id=self.diner)
        prompt = self.writer.calls[-1][1]
        self.assertIn("SOURCE_FACT_CHANGED", prompt)
        self.assertNotIn("culprit: Bob", prompt)
        self.assertIn("culprit [scope=global]: Alice", prompt)

    def test_ordering_reverse_cycle_is_rejected_when_indirect(self):
        self.edge()
        self.timeline.add_precedence(self.pid, self.reveals["id"], self.other["id"],
                                     self.timeline.revision(self.pid))
        rev = self.timeline.revision(self.pid)
        with self.assertRaisesRegex(RuntimeError, "cycle"):
            self.timeline.add_precedence(self.pid, self.other["id"], self.finds["id"], rev)
        self.assertEqual(self.timeline.revision(self.pid), rev)

    def test_different_character_lacks_knowledge_by_default(self):
        self.accepted_knowledge(self.finds["id"])
        self.mark(self.diner, self.reveals["id"])
        other = self.bible.create_entity(self.pid, "character", "Partner")
        self.bible.link_scene(self.pid, other["id"], self.diner, other["revision"])
        preview = self.pipeline.bible_context(self.pid, self.diner)["timeline"]["text"]
        self.assertNotIn("[KNOWLEDGE: KNOWN] Partner", preview)


# Prevent duplicate collection of the imported fixture's 21 tests.
del _TimelineFixture

if __name__ == "__main__":
    unittest.main()
