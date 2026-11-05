"""NVP-AI-01 reference boundary: no model, API, or worker needed."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.nvp_ai_refs import read_screenplay_lines
from backend.nvp_studio import Studio


class AIReferenceReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "nvp.sqlite3"
        self.studio = Studio(self.db)
        self.start = self.studio.create_project("Example", "Reference identity")
        self.script = ("INT. HALL - DAY\r\n\r\nALEX\r\nWait.\r\n"
                       "\r\nEXT. STREET - NIGHT\r\nSAM\r\nRun.\r\n")
        self.project = self.studio.save_screenplay(
            self.start["id"], self.script, self.start["revision"]
        )
        self.pid = self.start["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_original_source_and_selected_scene_lines_match(self):
        scene = self.project["scenes"][1]
        record = read_screenplay_lines(
            self.studio, self.pid, self.project["revision"], scene_id=scene["id"]
        )
        self.assertEqual((record["returned_start_line"], record["returned_end_line"]), (6, 9))
        self.assertIn("L06 | EXT. STREET - NIGHT", record["numbered_excerpt"])
        self.assertIn("L09 | ", record["numbered_excerpt"])
        self.assertEqual(record["source_line_count"], 9)
        self.assertEqual(record["source_sha256"], hashlib.sha256(self.script.encode()).hexdigest())
        self.assertTrue(record["current_at_read"])
        self.assertFalse(record["side_effects_performed"])
        self.assertEqual(self.studio.get_project(self.pid)["screenplay"], self.script)

    def test_bounded_global_source_page_and_omission_metadata(self):
        record = read_screenplay_lines(
            self.studio, self.pid, self.project["revision"],
            start_line=2, end_line=9, max_lines=3
        )
        self.assertEqual([item["line"] for item in record["lines"]], [2, 3, 4])
        self.assertEqual(record["next_line"], 5)
        self.assertEqual(record["lines_omitted"], 5)
        self.assertEqual(record["lines"][0]["text"], "")
        self.assertNotIn("L05", record["numbered_excerpt"])

    def test_exact_prior_revision_survives_and_edit_requires_fresh_source(self):
        old_rev = self.project["revision"]
        changed = self.studio.save_screenplay(
            self.pid, "INT. HALL - DAY\nReplacement.", old_rev
        )
        old = read_screenplay_lines(self.studio, self.pid, old_rev)
        self.assertFalse(old["current_at_read"])
        self.assertEqual(old["source_sha256"], hashlib.sha256(self.script.encode()).hexdigest())
        self.assertEqual(old["current_revision_observed"], changed["revision"])
        with self.assertRaisesRegex(RuntimeError, "stale"):
            read_screenplay_lines(self.studio, self.pid, old_rev, require_current=True)
        self.assertEqual(self.studio.get_project(self.pid)["screenplay"], changed["screenplay"])

    def test_no_cross_project_scene_resolution_or_unknown_history(self):
        other = self.studio.create_project("Other", "Different film")
        sid = self.project["scenes"][0]["id"]
        with self.assertRaises(KeyError):
            read_screenplay_lines(self.studio, other["id"], other["revision"], scene_id=sid)
        with self.assertRaises(KeyError):
            read_screenplay_lines(self.studio, self.pid, 10000)
        with self.assertRaises(KeyError):
            read_screenplay_lines(self.studio, "other-project", 0)

    def test_rejects_bools_outside_scene_invalid_ranges_and_budgets(self):
        revision = self.project["revision"]
        for bad in (True, -1, "1"):
            with self.assertRaises(ValueError):
                read_screenplay_lines(self.studio, self.pid, bad)
        for bad in (0, 121, 1.5, True):
            with self.assertRaises(ValueError):
                read_screenplay_lines(self.studio, self.pid, revision, max_lines=bad)
        with self.assertRaises(ValueError):
            read_screenplay_lines(self.studio, self.pid, revision, start_line=2, end_line=1)
        scene = self.project["scenes"][1]
        with self.assertRaises(ValueError):
            read_screenplay_lines(self.studio, self.pid, revision, scene_id=scene["id"], start_line=3)

    def test_empty_source_is_one_blank_line(self):
        r = read_screenplay_lines(self.studio, self.pid, 0)
        self.assertEqual(r["source_line_count"], 1)
        self.assertEqual(r["lines"], [{"line": 1, "text": ""}])


if __name__ == "__main__":
    unittest.main()
