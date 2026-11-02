import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio, parse_screenplay

SCRIPT = """INT. APARTMENT - NIGHT

Sarah sets a cup down.

SARAH
Where were you?

JOHN (O.S.)
Outside.

EXT. STREET - NIGHT

John walks away.
"""


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.db"
        self.studio = Studio(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parser_finds_scene_and_dialogue(self):
        scenes = parse_screenplay(SCRIPT)
        self.assertEqual(len(scenes), 2)
        self.assertEqual(scenes[0]["characters"], ["SARAH", "JOHN"])
        self.assertEqual(scenes[0]["dialogue"][1]["line"], "Outside.")
        self.assertEqual(scenes[1]["heading"], "EXT. STREET - NIGHT")

    def test_persistence_approval_and_no_overwrite(self):
        created = self.studio.create_project("My film", "Two people and a secret")
        p = self.studio.save_screenplay(created["id"], SCRIPT, created["revision"])
        sid = p["scenes"][0]["id"]
        p = self.studio.plan_scene(p["id"], sid)
        shot = p["scenes"][0]["shots"][0]
        p = self.studio.edit_shot(p["id"], sid, shot["shot_id"], framing="close_up",
                                  subject="SARAH", intent="Reveal suspicion", notes="Director approved",
                                  approved=True)
        p = Studio(self.path).plan_scene(p["id"], sid)
        self.assertEqual(p["scenes"][0]["shots"][0]["framing"], "close_up")
        self.assertEqual(p["scenes"][0]["shots"][0]["status"], "approved")
        self.assertEqual(p["scenes"][0]["shots"][0]["notes"], "Director approved")

    def test_stale_revision_does_not_overwrite(self):
        p = self.studio.create_project("Title", "Idea")
        self.studio.save_screenplay(p["id"], SCRIPT, p["revision"])
        with self.assertRaisesRegex(RuntimeError, "Reload"):
            self.studio.save_screenplay(p["id"], "EXT. PARK - DAY", p["revision"])

    def test_script_revisions_archive_outdated_shots(self):
        p = self.studio.create_project("Title", "Idea")
        p = self.studio.save_screenplay(p["id"], SCRIPT, p["revision"])
        p = self.studio.plan_scene(p["id"], p["scenes"][0]["id"])
        p = self.studio.save_screenplay(p["id"], "INT. HOUSE - DAY\n\nA door opens.", p["revision"])
        self.assertGreater(p["archived_shots"], 0)
        self.assertEqual(p["scenes"][0]["shots"], [])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.studio.create_project("", "")
        with self.assertRaises(ValueError):
            parse_screenplay("x" * 1000001)
        with self.assertRaises(KeyError):
            self.studio.get_project("../foo")


if __name__ == "__main__":
    unittest.main()
