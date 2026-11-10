"""PLAN-03 source-grounded Scene Library and strictly unapproved local AI proposals."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_scene_library import SceneLibrary, FORMAT, PROPOSAL_FORMAT


SCREENPLAY = (
    "INT. KITCHEN - MORNING\n\n"
    "A dog eats food from a bowl.\n\n"
    "ALEX\nThis is breakfast.\n\n"
    "EXT. PARK - DAY\n\n"
    "The dog trots past a bench.\n"
)


class Writer:
    def __init__(self, value=None, callback=None):
        self.value = (value if value is not None else json.dumps({
            "actors": ["ALEX", "DOG (unconfirmed role)"],
            "locations": ["Kitchen set (needs approval)"],
            "props": ["Dog bowl (needs approval)"],
        }))
        self.callback = callback
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        assert "source" in user.lower()
        if self.callback:
            self.callback()
        return self.value


class SceneLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(Path(self.temp.name) / "nvp_studio.sqlite3")
        self.project = self.studio.create_project("Dog movie", "A dog eats.")
        self.project = self.studio.save_screenplay(
            self.project["id"], SCREENPLAY, self.project["revision"])
        self.service = SceneLibrary(self.studio)

    def test_source_only_has_unassigned_props_and_no_approved_cast(self):
        snap = self.service.snapshot(self.project["id"])
        self.assertEqual(snap["format"], FORMAT)
        self.assertFalse(snap["ai_generated"])
        self.assertEqual(snap["scene_count"], 2)
        first = snap["scenes"][0]
        self.assertIn("ALEX", first["screenplay_character_cues"])
        self.assertEqual(first["actors"], [])
        self.assertEqual(first["props"], [])
        self.assertEqual(first["props_status"], "not_yet_assigned")
        self.assertEqual(first["location_status"], "screenplay_heading_only")
        self.assertEqual(first["heading"], "INT. KITCHEN - MORNING")
        self.assertEqual(first["source_scene_sha256"],
                         hashlib.sha256(first["screenplay_text"].encode()).hexdigest())

    def test_only_creator_linked_source_current_props_appear(self):
        pid = self.project["id"]
        b = StoryBible(self.studio)
        prop = b.create_entity(pid, "prop", "Bowl")
        snap = self.service.snapshot(pid)
        scene = snap["scenes"][0]
        self.assertFalse(scene["props"])  # A Bible entity is not automatically in a scene.
        b.link_scene(pid, prop["id"], scene["scene_id"], prop["revision"])
        current = self.service.snapshot(pid)["scenes"][0]
        self.assertEqual([p["name"] for p in current["props"]], ["Bowl"])
        self.assertTrue(current["props"][0]["approved"])
        changed = SCREENPLAY.replace("A dog eats food", "A hungry dog eats food")
        self.project = self.studio.save_screenplay(
            pid, changed, self.project["revision"])
        later = self.service.snapshot(pid)["scenes"][0]
        self.assertEqual(later["props"], [])
        self.assertEqual(later["stale_links"][0]["reason"],
                         "screenplay_source_changed")

    def test_ai_bounded_proposal_does_not_change_screenplay_or_bible(self):
        pid = self.project["id"]
        snap = self.service.snapshot(pid)
        scene = snap["scenes"][0]
        writer = Writer()
        proposal = self.service.propose_ai_breakdown(
            pid, scene["scene_id"], snap["project_revision"], writer=writer)
        self.assertEqual(writer.calls, 1)
        self.assertEqual(proposal["format"], PROPOSAL_FORMAT)
        self.assertEqual(proposal["status"], "UNAPPROVED_PROPOSAL")
        self.assertFalse(proposal["creator_approval_granted"])
        self.assertFalse(proposal["native_tools_invoked"])
        self.assertIn("Dog bowl (needs approval)", proposal["suggestions"]["props"])
        self.assertEqual(self.service.snapshot(pid), snap)
        self.assertEqual(StoryBible(self.studio).list_entities(pid), [])

    def test_ai_refuses_stale_revision_or_wrong_scene_or_project(self):
        pid = self.project["id"]
        snap = self.service.snapshot(pid)
        sid = snap["scenes"][0]["scene_id"]
        writer = Writer()
        with self.assertRaises(RuntimeError):
            self.service.propose_ai_breakdown(pid, sid, snap["project_revision"]-1,
                                              writer=writer)
        self.assertEqual(writer.calls, 0)
        with self.assertRaises(KeyError):
            self.service.propose_ai_breakdown(pid, "SC_unknown",
                                              snap["project_revision"], writer=writer)
        other = self.studio.create_project("Other", "Different")
        with self.assertRaises(KeyError):
            self.service.propose_ai_breakdown(other["id"], sid,
                                              other["revision"], writer=writer)

    def test_ai_refuses_bad_json_and_proposal_array_expansion(self):
        snap = self.service.snapshot(self.project["id"])
        sid = snap["scenes"][0]["scene_id"]
        for bad in ("not JSON", "{}", json.dumps({
            "actors": [], "locations": [], "props": ["x"]*13
        }),json.dumps({"actors": [4], "locations": [], "props": []})):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.service.propose_ai_breakdown(
                        self.project["id"], sid, snap["project_revision"],
                        writer=Writer(bad))

    def test_whole_movie_breakdown_has_exact_source_scenes_unapproved(self):
        pid=self.project["id"]
        first=self.service.snapshot(pid)
        writer=Writer()
        proposal=self.service.propose_movie_breakdown(
            pid,first["project_revision"],writer=writer)
        self.assertEqual(proposal["format"],"nvp.plan04.source_bound_movie_breakdown.v1")
        self.assertEqual(proposal["scene_count"],2)
        self.assertEqual(writer.calls,2)
        self.assertEqual([s["scene_id"] for s in proposal["scenes"]],
                         [s["scene_id"] for s in first["scenes"]])
        self.assertEqual([s["screenplay_heading"] for s in proposal["scenes"]],
                         [s["heading"] for s in first["scenes"]])
        self.assertEqual(proposal["status"],"UNAPPROVED_PROPOSAL")
        self.assertFalse(proposal["creator_approval_granted"])
        self.assertFalse(proposal["native_render_authorized"])
        self.assertFalse(proposal["original_source_modified"])
        self.assertEqual(self.service.snapshot(pid),first)
        self.assertFalse(StoryBible(self.studio).list_entities(pid))

    def test_whole_movie_change_during_model_completion_discards_all(self):
        pid=self.project["id"]
        first=self.service.snapshot(pid)
        def change():
            self.studio.save_screenplay(
                pid,SCREENPLAY.replace("This is breakfast.", "My breakfast."),
                first["project_revision"])
        with self.assertRaisesRegex(RuntimeError,"changed during"):
            self.service.propose_movie_breakdown(
                pid,first["project_revision"],writer=Writer(callback=change))
        self.assertFalse(StoryBible(self.studio).list_entities(pid))

    def test_concurrent_screenplay_change_discards_model_output(self):
        pid = self.project["id"]
        snap = self.service.snapshot(pid)
        sid = snap["scenes"][0]["scene_id"]
        def change():
            self.studio.save_screenplay(pid,
                SCREENPLAY.replace("This is breakfast.", "A later breakfast."),
                snap["project_revision"])
        with self.assertRaisesRegex(RuntimeError, "changed during AI"):
            self.service.propose_ai_breakdown(
                pid,sid,snap["project_revision"],writer=Writer(callback=change))


if __name__ == "__main__":
    unittest.main()
