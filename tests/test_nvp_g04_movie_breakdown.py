"""PLAN-03/04 original whole-movie behavior on the current G04 authority.

Purely synthetic model completions: these are negative source/transaction tests,
NOT a GGUF, native worker, renderer or physical filmmaker acceptance claim.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_g04_preproduction import G04Preproduction
from backend.nvp_studio import Studio

SCRIPT = (
    "INT. KITCHEN - MORNING\n\nA dog eats breakfast from a bowl.\n\n"
    "EXT. PARK - NIGHT\n\nClouds move above the grass.\n"
)
MODEL = "synthetic-source-only-fixture"


class SceneWriter:
    """Deterministic fake data source; cannot grant native or creative consent."""
    def __init__(self,callback=None):
        self.callback=callback
        self.calls=[]
        self.completion_receipt={
            "selected_model_id":MODEL,
            "provider_completion_finish_reason":"stop",
            "provider_reported_completion_tokens":15}

    def complete(self,system,user):
        scene=json.loads(user)
        self.calls.append(scene)
        assert "UNTRUSTED SOURCE" in system
        n=len(self.calls)
        if self.callback is not None:
            reply=self.callback(n,scene)
            if reply is not None:return reply
        return self.good(scene)

    @staticmethod
    def good(scene):
        # Use the current script heading and its genuine absolute line number.
        heading=scene["scene_script"].splitlines()[0]
        return json.dumps({"suggestions":[{
            "category":"prop",
            "value":"Set prop for "+scene["scene_name"][:50],
            "source_line":scene["source_line_start"],
            "source_quote":heading}]},separators=(",",":"))


class WholeMovieSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-plan04-")
        self.addCleanup(self.temp.cleanup)
        self.studio=Studio(Path(self.temp.name)/"studio.sqlite3")
        created=self.studio.create_project("Two original scenes","Two settings")
        saved=self.studio.save_screenplay(
            created["id"],SCRIPT,created["revision"])
        self.pid=saved["id"]
        self.revision=saved["revision"]
        self.host=G04Preproduction(self.studio)
        self.assertEqual(len(self.host.view(self.pid)["scenes"]),2)

    def rows(self):
        with self.studio._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT scene_id,category,value,status,source_sha256,"
                "screenplay_revision,model_id,model_receipt_json "
                "FROM g04_proposals ORDER BY scene_id,id")]

    def propose(self,writer,revision=None,host=None):
        selected=self.revision if revision is None else revision
        with patch.object(G04Preproduction,"_local_writer",
                          return_value=(MODEL,writer)):
            return (host or self.host).propose_movie_breakdown(
                self.pid,selected)

    def test_original_whole_movie_is_source_exact_and_approval_isolation(self):
        before=self.studio.get_project(self.pid)
        writer=SceneWriter()
        result=self.propose(writer)
        self.assertEqual(len(writer.calls),2)
        self.assertEqual(result["movie_breakdown"]["scene_count"],2)
        self.assertEqual(result["movie_breakdown"]["status"],"UNAPPROVED_PROPOSAL")
        self.assertFalse(result["movie_breakdown"]["creator_approval_granted"])
        self.assertFalse(result["movie_breakdown"]["native_worker_authorized"])
        self.assertFalse(result["movie_breakdown"]["partial_publication_performed"])
        self.assertEqual(result["movie_breakdown"]["source_screenplay_sha256"],
                         result["screenplay_sha256"])
        self.assertEqual(result["movie_breakdown"]["source_scene_ids"],
                         [s["id"] for s in result["scenes"]])
        rows=self.rows()
        self.assertEqual(len(rows),2)
        for row in rows:
            scene=next(s for s in result["scenes"] if s["id"]==row["scene_id"])
            self.assertEqual(row["source_sha256"],scene["source_sha256"])
            self.assertEqual(row["screenplay_revision"],self.revision)
            self.assertEqual(row["status"],"proposed")
            self.assertEqual(row["model_id"],MODEL)
            self.assertEqual(json.loads(row["model_receipt_json"])
                             ["selected_model_id"],MODEL)
        self.assertEqual(result["bible"]["facts"],[])
        self.assertEqual(before["screenplay"],
                         self.studio.get_project(self.pid)["screenplay"])
        self.assertEqual(before["revision"],
                         self.studio.get_project(self.pid)["revision"])

    def test_creator_must_separately_accept_each_proposal(self):
        result=self.propose(SceneWriter())
        first=result["scenes"][0]["proposals"][0]
        self.assertEqual(first["status"],"proposed")
        reviewed=self.host.decide(
            self.pid,first["id"],"accept",self.revision)
        self.assertEqual(len(reviewed["bible"]["facts"]),1)
        self.assertEqual(len([row for row in self.rows()
                              if row["status"]=="accepted"]),1)
        self.assertEqual(len([row for row in self.rows()
                              if row["status"]=="proposed"]),1)

    def test_wrong_revision_refuses_before_model_or_publication(self):
        writer=SceneWriter()
        with self.assertRaisesRegex(RuntimeError,"Screenplay changed"):
            self.propose(writer,revision=self.revision-1)
        self.assertEqual(writer.calls,[])
        self.assertEqual(self.rows(),[])

    def test_second_completion_invalid_json_never_publishes_first(self):
        writer=SceneWriter(lambda n,s:"not json" if n==2 else None)
        with self.assertRaisesRegex(ValueError,"suggestions"):
            self.propose(writer)
        self.assertEqual(len(writer.calls),2)
        self.assertEqual(self.rows(),[])

    def test_wrong_original_line_or_forged_quote_refuses_every_scene(self):
        def invalid(n,scene):
            if n!=2:return None
            return json.dumps({"suggestions":[{
                "category":"prop","value":"Invented hidden relic",
                "source_line":scene["source_line_start"],
                "source_quote":"This quote never appeared in the script"}]})
        with self.assertRaisesRegex(ValueError,"not in the screenplay"):
            self.propose(SceneWriter(invalid))
        self.assertEqual(self.rows(),[])

    def test_screenplay_mutation_during_second_completion_refuses_all(self):
        def mutate(n,scene):
            if n==2:
                current=self.studio.get_project(self.pid)
                self.studio.save_screenplay(self.pid,
                    SCRIPT+"A lantern now lights the grass.\n",
                    current["revision"])
            return None
        with self.assertRaisesRegex(RuntimeError,"changed during whole-movie"):
            self.propose(SceneWriter(mutate))
        self.assertEqual(self.rows(),[])

    def test_source_notes_change_during_model_completion_refuses_all(self):
        def mutate(n,scene):
            if n==2:
                current=self.host.view(self.pid)
                old=current["scenes"][0]
                notes=dict(old["notes"])
                notes["weather"]="Cold rain"
                self.host.save_scene(self.pid,old["id"],notes,
                    old["notes_revision"],current["screenplay_revision"])
            return None
        with self.assertRaisesRegex(RuntimeError,"changed during whole-movie"):
            self.propose(SceneWriter(mutate))
        self.assertEqual(self.rows(),[])

    def test_bad_completion_receipt_on_second_scene_refuses_all(self):
        writer=SceneWriter()
        def invalidate(n,scene):
            if n==2:
                writer.completion_receipt={
                    "selected_model_id":MODEL,
                    "provider_completion_finish_reason":"length"}
            return None
        writer.callback=invalidate
        with self.assertRaisesRegex(ValueError,"not completed"):
            self.propose(writer)
        self.assertEqual(self.rows(),[])

    def test_sqlite_second_scene_failure_rolls_back_first_scene_insert(self):
        second=self.host.view(self.pid)["scenes"][1]["id"]
        # Bound constant from first-party parser, not an external SQL input.
        with self.studio._connection() as db:
            db.execute("CREATE TRIGGER plan04_inject BEFORE INSERT ON "
                "g04_proposals WHEN NEW.scene_id='"+second+"' "
                "BEGIN SELECT RAISE(ABORT,'forced second-scene failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,
                                    "forced second-scene failure"):
            self.propose(SceneWriter())
        self.assertEqual(self.rows(),[])

    def test_duplicate_proposed_source_only_retains_one_per_scene(self):
        self.propose(SceneWriter())
        self.propose(SceneWriter())
        self.assertEqual(len(self.rows()),2)
        self.assertTrue(all(row["status"]=="proposed" for row in self.rows()))

    def test_revised_screenplay_does_not_reuse_stale_proposal_for_same_scene(self):
        self.propose(SceneWriter())
        old=self.host.view(self.pid)["scenes"][0]["proposals"][0]["id"]
        saved=self.studio.get_project(self.pid)
        revised=self.studio.save_screenplay(
            self.pid,SCRIPT+"A new character enters the park.\n",
            saved["revision"])
        self.revision=revised["revision"]
        result=self.propose(SceneWriter())
        first=result["scenes"][0]["proposals"]
        self.assertEqual(len(first),2)
        self.assertTrue(next(p["stale"] for p in first if p["id"]==old))
        self.assertEqual(len([p for p in first if not p["stale"]]),1)

    def test_over_eight_scenes_and_idea_only_refused_without_model(self):
        script="\n\n".join(
            "INT. ROOM "+str(n)+" - DAY\n\nA lamp lights scene "+str(n)+"."
            for n in range(9))
        project=self.studio.get_project(self.pid)
        saved=self.studio.save_screenplay(
            self.pid,script,project["revision"])
        writer=SceneWriter()
        with self.assertRaisesRegex(ValueError,"1-8"):
            self.propose(writer,revision=saved["revision"])
        self.assertEqual(writer.calls,[])
        self.assertEqual(self.rows(),[])
        idea=self.studio.create_project("Idea film","No screenplay yet")
        with patch.object(G04Preproduction,"_local_writer",
                          side_effect=AssertionError("Do not invoke model")):
            with self.assertRaisesRegex(ValueError,"1-8"):
                self.host.propose_movie_breakdown(
                    idea["id"],idea["revision"])

    def test_existing_single_scene_generator_uses_same_source_verifier(self):
        writer=SceneWriter()
        sid=self.host.view(self.pid)["scenes"][0]["id"]
        with patch.object(G04Preproduction,"_local_writer",
                          return_value=(MODEL,writer)):
            result=self.host.generate(self.pid,sid)
        self.assertEqual(len(result["scenes"][0]["proposals"]),1)
        self.assertEqual(result["bible"]["facts"],[])


@unittest.skipUnless(sys.platform=="win32",
                     "Real sealed SQLite/DPAPI requires Windows")
class ProtectedWholeMovieSourceTests(unittest.TestCase):
    def test_real_encrypted_film_uses_one_sealed_transaction(self):
        from backend.nvp_g03_live_store import LiveFilmStore
        with tempfile.TemporaryDirectory(prefix="nvp-plan04-sealed-") as root:
            project_id="ca"*16
            token="director-owned-plan04-"+("a"*32)
            passphrase="A real G03 test-only protected project password"
            store=LiveFilmStore(
                Path(root)/"sealed",
                grant_checker=lambda pid,grant:pid==project_id and grant==token)
            store.create(project_id,"Sealed original film",
                         "Two settings",SCRIPT,passphrase)
            store.authorize(project_id,passphrase,token)
            host=G04Preproduction(Studio(Path(root)/"ordinary.sqlite3"),
                                  live=store,token=token)
            writer=SceneWriter()
            with patch.object(G04Preproduction,"_local_writer",
                              return_value=(MODEL,writer)):
                result=host.propose_movie_breakdown(project_id,0)
            self.assertEqual(len(writer.calls),2)
            self.assertEqual([len(s["proposals"]) for s in result["scenes"]],
                             [1,1])
            self.assertEqual(result["bible"]["facts"],[])
            self.assertEqual(store.read(project_id,token)["screenplay"],SCRIPT)
            # No G04 draft/approval ledger may spill into the ordinary DB.
            with host.studio._connection() as db:
                self.assertNotIn("g04_proposals",{
                    r[0] for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")})


if __name__ == "__main__":
    unittest.main()
