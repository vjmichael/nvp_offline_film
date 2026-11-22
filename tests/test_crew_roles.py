"""Crew-01: old NVP multi-role concept, new canon/proposal safety gates."""
import tempfile
import unittest
from pathlib import Path

from backend.nvp_crew_roles import (
    ROLE_RULES, prepare_crew_task, validate_crew_reply, check_crew_task_fresh,
)
from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible

SCRIPT = "INT. STUDY - NIGHT\n\nMARA\nI found the locket.\n"


class CrewRoles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "film.sqlite3"
        self.studio = Studio(self.path)
        self.project = self.studio.create_project("Locket", "A family secret")
        self.pid = self.project["id"]
        self.studio.save_screenplay(self.pid, SCRIPT, 0)
        self.bible = StoryBible(self.studio)
        self.actor = self.bible.create_entity(self.pid, "character", "Mara")

    def tearDown(self):
        self.temp.cleanup()

    def approved(self, key, value):
        p = self.bible.propose_fact(self.pid, self.actor["id"], key, value,
                                    origin="creator")
        self.bible.decide_fact(self.pid, p["id"], "accept",
                               self.bible.get_entity(self.pid,self.actor["id"])["revision"])

    def task(self, role="director"):
        return prepare_crew_task(self.studio, self.pid, role, "Review the scene")

    def test_single_model_can_take_distinct_roles_with_same_canon(self):
        self.approved("coat", "blue")
        director = self.task("director")
        sound = self.task("sound_designer")
        self.assertIn("creative approvals", director["system"])
        self.assertIn("mic", sound["system"])
        self.assertEqual(director["packet"]["approved_facts"],
                         sound["packet"]["approved_facts"])
        self.assertNotEqual(director["context_sha256"], sound["context_sha256"])
        self.assertEqual(len(ROLE_RULES), 8)
        self.assertFalse(director["packet"]["direct_write_authority"])

    def test_unapproved_facts_never_prompted_as_canon(self):
        self.bible.propose_fact(self.pid,self.actor["id"],
                                "secret", "MARA IS A ROBOT", origin="ai_proposal")
        task=self.task()
        self.assertNotIn("MARA IS A ROBOT",task["user"])
        self.assertEqual(task["packet"]["approved_facts"], [])

    def test_reply_cannot_claim_tool_execution_or_approval(self):
        t=self.task()
        answer={"role":"director","context_sha256":t["context_sha256"],
                "summary":"Try a close-up","proposals":["Camera only, no new acting take"]}
        got=validate_crew_reply(t,answer)
        self.assertEqual(got["state"],"unapproved_proposal")
        self.assertFalse(got["side_effects_performed"])
        with self.assertRaises(ValueError):
            validate_crew_reply(t,dict(answer, approved=True))
        with self.assertRaises(RuntimeError):
            validate_crew_reply(t,dict(answer, context_sha256="0"*64))

    def test_changed_screenplay_invalidates_old_roles(self):
        t=self.task()
        self.studio.save_screenplay(self.pid,SCRIPT.replace("locket","key"),1)
        with self.assertRaisesRegex(RuntimeError,"context changed"):
            check_crew_task_fresh(self.studio,t)

    def test_new_canon_invalidates_old_roles_even_after_restart(self):
        t=self.task()
        self.approved("coat","blue")
        reopened=Studio(self.path)
        with self.assertRaisesRegex(RuntimeError,"context changed"):
            check_crew_task_fresh(reopened,t)

    def test_unknown_roles_and_wrong_scene_denied(self):
        with self.assertRaises(ValueError):
            self.task("unrestricted_admin")
        with self.assertRaises(KeyError):
            prepare_crew_task(self.studio,self.pid,"director","Review",scene_id="SC_ghost")

    def test_project_isolation(self):
        self.approved("secret","silver locket")
        other=self.studio.create_project("Elsewhere","A second film")
        task=prepare_crew_task(self.studio,other["id"],"script_supervisor","Review")
        self.assertNotIn("silver locket",task["user"])

    def test_never_claim_legacy_placeholder_is_actual_execution(self):
        task=self.task("acting_coach")
        self.assertTrue(task["packet"]["proposal_only"])
        self.assertIn("Never invent",task["system"])
        self.assertFalse(validate_crew_reply(task,{
            "role":"acting_coach","context_sha256":task["context_sha256"],
            "summary":"Try a reserved performance","proposals":[]
        })["side_effects_performed"])


if __name__ == "__main__":
    unittest.main()
