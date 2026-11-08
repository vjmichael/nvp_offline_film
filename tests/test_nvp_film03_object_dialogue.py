"""FILM03-01 genuine original-script / StoryBible / OpenUSD actor revision tests.

No recorded speech is fabricated; voice_source=None means "not recorded".
Tests use an actual original immutable three-shot OpenUSD source and Studio
database, not fake FilmIndex metadata or model-generated dialogue.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_film03_object_dialogue import (
    ObjectActorDialogue, SCRIPT_FORMAT, PERFORMANCE_FORMAT, SELECTION_FORMAT,
    read_scene_dialogue_selection, _script_scenes,
)
from backend.nvp_wo6_scene_context import assemble_film_crew_context
from backend.nvp_story_bible import StoryBible
from backend.nvp_studio import Studio, parse_screenplay
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from tools.nvp_film01_original_30s import write_original_30s_source

SCRIPT_1 = """INT. RELAY NINE - NIGHT

DONUT
The relay has been silent for twenty years.

BOX
I think I found the problem.

SPHERE
Stand aside. I've got this.
"""
SCRIPT_2 = SCRIPT_1.replace(
    "The relay has been silent for twenty years.",
    "The relay is coming back online."
)
T = TICKS_PER_SECOND
EVENT = "TRUSTED_CREATOR_ACTION_FIXTURE_ONLY"


def approves(event, scope):
    return bool(event == EVENT and scope["operation"].startswith("film03_")
                and type(scope["project_id"]) is str)


class RealFilm03DialogueLineage(unittest.TestCase):
    def test_speech_lines_script_revision_bible_and_old_takes_survive(self):
        with TemporaryDirectory(prefix="nvp-film03-") as temp:
            root = Path(temp).resolve()
            source = root / "original-source"
            report = write_original_30s_source(source, approve_test_only=True)
            pid = report["project_id"]
            studio = Studio(source/"short.sqlite3")
            index = FilmIndex(studio)
            bible = StoryBible(studio)
            initial = studio.save_screenplay(pid, SCRIPT_1, expected_revision=0)
            self.assertEqual(initial["revision"], 1)
            scene_id = initial["scenes"][0]["id"]
            people = {}
            for name in ("DONUT", "BOX", "SPHERE"):
                entity = bible.create_entity(pid, "character", name)
                entity = bible.link_scene(
                    pid, entity["id"], scene_id, entity["revision"],
                    note="FILM03 original actor/canon link, not a generated voice")
                self.assertEqual(entity["scene_links"][0]["screenplay_revision"], 1)
                people[name] = entity
            author = ObjectActorDialogue(index, verify_creator_action=approves)
            pub1 = author.publish_script_snapshot(
                pid, "Relay03ScreenplayDialogue",
                expected_screenplay_revision=1, expected_manifest_revision=0,
                creator_event=EVENT)
            self.assertEqual(pub1["revision"], 1)
            old = index.read_revision(pid, "Relay03ScreenplayDialogue", 1)
            self.assertEqual(old["data"]["format"], SCRIPT_FORMAT)
            self.assertEqual(old["data"]["screenplay_revision"], 1)
            lines = {line["speaker"]:line for line in old["data"]["scenes"][0]["lines"]}
            self.assertEqual(set(lines), {"DONUT", "BOX", "SPHERE"})
            taken = index.read_revision(pid, "RelayRekindleTake", 1)
            take_sha = taken["document_sha256"]
            original_timeline_sha = taken["data"]["timeline_document_sha256"]
            specs = (
                ("DONUT", "/World/Engineer", "DonutOriginalLine"),
                ("BOX", "/World/CrossingBox", "BoxOriginalLine"),
                ("SPHERE", "/World/PassingSphere", "SphereOriginalLine"),
            )
            created = []
            for n, (speaker, prim, name) in enumerate(specs):
                result = author.record_performance(
                    pid, name, script_id="Relay03ScreenplayDialogue",
                    script_revision=1, script_line_id=lines[speaker]["line_id"],
                    bible_entity_id=people[speaker]["id"],
                    actor_prim_path=prim,
                    source_take_id="RelayRekindleTake",
                    source_take_sha256=take_sha,
                    first_tick=n*T, end_tick=(n+1)*T,
                    delivery_intent="Quietly, with original geometric-object actor blocking",
                    creator_event=EVENT)
                self.assertEqual(result["revision"], 1)
                recorded = index.read_revision(pid, name, 1)
                self.assertEqual(recorded["data"]["format"], PERFORMANCE_FORMAT)
                self.assertIsNone(recorded["data"]["recorded_voice_source"])
                self.assertFalse(recorded["data"]["voice_synthesized"])
                self.assertEqual(recorded["data"]["production_bible"]["entity_id"],
                                 people[speaker]["id"])
                created.append(result)
            first_edit = author.publish_scene_dialogue(
                pid, selection_id="Relay03DialogueEdit",
                overlay_timeline_id="Relay03DialogueOverlay",
                source_take_id="RelayRekindleTake",
                source_take_sha256=take_sha,
                script_id="Relay03ScreenplayDialogue", script_revision=1,
                performance_ids=[x["object_id"] for x in created],
                creator_event=EVENT)
            self.assertEqual(first_edit["revision"], 1)
            edit1 = index.read_revision(pid, "Relay03DialogueEdit", 1)
            self.assertEqual(edit1["data"]["format"], SELECTION_FORMAT)
            self.assertTrue(edit1["data"]["all_original_take_events_preserved"])
            self.assertEqual(len(edit1["data"]["selected"]), 3)
            crew_before = assemble_film_crew_context(
                index, pid, "RelayRekindleTake", 1, 0,
                dialogue_selection_id="Relay03DialogueEdit",
                dialogue_selection_revision=1)
            selected_before = crew_before["authored_object_actor_dialogue_selection"]
            self.assertIsNotNone(selected_before)
            self.assertFalse(selected_before["script_changed_since_selected_dialogue"])
            self.assertEqual(selected_before["active_object_actor_lines"][0][
                "screenplay_speaker"], "DONUT")
            self.assertEqual(selected_before["active_object_actor_lines"][0][
                "production_bible_entity_id"], people["DONUT"]["id"])
            self.assertFalse(selected_before["active_object_actor_lines"][0][
                "voice_source_recorded"])
            with self.assertRaises(PermissionError):
                read_scene_dialogue_selection(
                    index, pid, "Relay03DialogueEdit", 1,
                    tick=0, expected_take_id="RelayDiscoveryTake")
            original = TemporalLedger(index)
            overlay1 = original.verify(pid, "Relay03DialogueOverlay", 1)
            self.assertGreater(overlay1["event_count"],
                               original.verify(
                                   pid, taken["data"]["timeline_id"],
                                   taken["data"]["timeline_revision"])["event_count"])
            self.assertEqual(
                index.read_revision(pid, "RelayRekindleTake", 1)["document_sha256"],
                take_sha)
            self.assertEqual(taken["data"]["timeline_document_sha256"],
                             original_timeline_sha)
            old_donut_sha = created[0]["document_sha256"]
            # Actual source-screenplay editor changes line content. StoryBible
            # reports the impacted character/scene and the new script preview
            # identifies impacted *old* voice performance without touching it.
            edited = studio.save_screenplay(pid, SCRIPT_2, expected_revision=1)
            self.assertEqual(edited["revision"], 2)
            bible_before = bible.report(pid)
            self.assertGreaterEqual(
                sum(issue["type"] == "scene_changed" for issue in bible_before["issues"]), 1)
            impact = author.preview_script_changes(
                pid, "Relay03ScreenplayDialogue")
            self.assertEqual(impact["screenplay_revision"], 2)
            self.assertEqual(impact["last_published_script_snapshot_revision"], 1)
            crew_after_rewrite = assemble_film_crew_context(
                index, pid, "RelayRekindleTake", 1, 0,
                dialogue_selection_id="Relay03DialogueEdit",
                dialogue_selection_revision=1)
            self.assertTrue(crew_after_rewrite[
                "authored_object_actor_dialogue_selection"][
                    "script_changed_since_selected_dialogue"])
            self.assertEqual(crew_after_rewrite[
                "authored_object_actor_dialogue_selection"][
                    "active_object_actor_lines"][0]["original_spoken_text"],
                "The relay has been silent for twenty years.")
            self.assertIn("DonutOriginalLine",
                          [x["performance_id"] for x in impact["impacted_historical_performances"]])
            self.assertNotIn("BoxOriginalLine",
                             [x["performance_id"] for x in impact["impacted_historical_performances"]])
            pub2 = author.publish_script_snapshot(
                pid, "Relay03ScreenplayDialogue",
                expected_screenplay_revision=2, expected_manifest_revision=1,
                creator_event=EVENT)
            self.assertEqual(pub2["revision"], 2)
            newer = index.read_revision(pid, "Relay03ScreenplayDialogue", 2)
            self.assertEqual(newer["data"]["previous_screenplay_revision"], 1)
            lines2 = {line["speaker"]:line for line in newer["data"]["scenes"][0]["lines"]}
            self.assertEqual(lines2["DONUT"]["line_id"], lines["DONUT"]["line_id"])
            self.assertEqual(lines2["DONUT"]["lineage_status"], "revised")
            self.assertNotEqual(lines2["DONUT"]["text_sha256"],
                                lines["DONUT"]["text_sha256"])
            self.assertEqual(lines2["BOX"]["line_id"], lines["BOX"]["line_id"])
            self.assertEqual(lines2["SPHERE"]["line_id"], lines["SPHERE"]["line_id"])
            self.assertEqual(index.read_revision(pid, "DonutOriginalLine", 1)[
                "document_sha256"], old_donut_sha)
            with self.assertRaises(PermissionError):
                author.publish_scene_dialogue(
                    pid, selection_id="Relay03DialogueEdit",
                    overlay_timeline_id="Relay03DialogueOverlay",
                    source_take_id="RelayRekindleTake",
                    source_take_sha256=take_sha,
                    script_id="Relay03ScreenplayDialogue", script_revision=2,
                    performance_ids=[x["object_id"] for x in created],
                    expected_selection_revision=1, expected_timeline_revision=1,
                    creator_event=EVENT)
            # Director may expressly RETAIN the old recorded delivery despite
            # the revised script. A second *immutable* selection is saved.
            retained = author.publish_scene_dialogue(
                pid, selection_id="Relay03DialogueEdit",
                overlay_timeline_id="Relay03DialogueOverlay",
                source_take_id="RelayRekindleTake",
                source_take_sha256=take_sha,
                script_id="Relay03ScreenplayDialogue", script_revision=2,
                performance_ids=[x["object_id"] for x in created],
                expected_selection_revision=1, expected_timeline_revision=1,
                preserve_prior_script_performances=True,
                preservation_reason="Director explicitly kept the earlier donut delivery",
                creator_event=EVENT)
            self.assertEqual(retained["revision"], 2)
            self.assertEqual(
                index.read_revision(pid, "Relay03DialogueEdit", 1)["document_sha256"],
                first_edit["document_sha256"])
            self.assertIn("DonutOriginalLine", index.read_revision(
                pid, "Relay03DialogueEdit", 2)["data"]["retained_earlier_performances"])
            self.assertEqual(
                original.verify(pid, "Relay03DialogueOverlay", 1)["status"],
                "VERIFIED_INDEXED_EVENT_PROVENANCE")
            self.assertEqual(
                original.verify(pid, "Relay03DialogueOverlay", 2)["status"],
                "VERIFIED_INDEXED_EVENT_PROVENANCE")
            # After reviewing the StoryBible scene change, the director
            # relinks canon and records a NEW donut delivery, then selects it.
            revised_entity = bible.get_entity(pid, people["DONUT"]["id"])
            bible.link_scene(pid, revised_entity["id"], scene_id,
                             revised_entity["revision"], note="Read revised line aloud")
            new_perf = author.record_performance(
                pid, "DonutRevisedLine",
                script_id="Relay03ScreenplayDialogue", script_revision=2,
                script_line_id=lines2["DONUT"]["line_id"],
                bible_entity_id=people["DONUT"]["id"],
                actor_prim_path="/World/Engineer",
                source_take_id="RelayRekindleTake",
                source_take_sha256=take_sha,
                first_tick=0, end_tick=T,
                delivery_intent="Revised original delivery, no auto-recorded voice",
                creator_event=EVENT)
            self.assertEqual(new_perf["revision"], 1)
            third = author.publish_scene_dialogue(
                pid, selection_id="Relay03DialogueEdit",
                overlay_timeline_id="Relay03DialogueOverlay",
                source_take_id="RelayRekindleTake",
                source_take_sha256=take_sha,
                script_id="Relay03ScreenplayDialogue", script_revision=2,
                performance_ids=["DonutRevisedLine", "BoxOriginalLine",
                                 "SphereOriginalLine"],
                expected_selection_revision=2, expected_timeline_revision=2,
                creator_event=EVENT)
            self.assertEqual(third["revision"], 3)
            self.assertEqual(
                index.read_revision(pid, "Relay03DialogueEdit", 3)["data"][
                    "selected"][0]["performance_id"], "DonutRevisedLine")
            self.assertEqual(index.read_revision(pid, "DonutOriginalLine", 1)[
                "document_sha256"], old_donut_sha)
            self.assertEqual(index.read_revision(pid, "RelayRekindleTake", 1)[
                "document_sha256"], take_sha)
            crew_final = assemble_film_crew_context(
                index, pid, "RelayRekindleTake", 1, 0,
                dialogue_selection_id="Relay03DialogueEdit",
                dialogue_selection_revision=3)
            active_final = crew_final["authored_object_actor_dialogue_selection"][
                "active_object_actor_lines"][0]
            self.assertEqual(active_final["performance_id"], "DonutRevisedLine")
            self.assertEqual(active_final["original_spoken_text"],
                             "The relay is coming back online.")
            self.assertFalse(crew_final[
                "authored_object_actor_dialogue_selection"][
                    "script_changed_since_selected_dialogue"])
            self.assertGreaterEqual(len(studio.screenplay_history(pid)), 2)
            self.assertEqual(
                original.verify(pid, "Relay03DialogueOverlay", 3)["status"],
                "VERIFIED_INDEXED_EVENT_PROVENANCE")
            # Real restart: reopen the SAME persistent SQLite project and
            # exact FilmIndex blob history in a fresh process-style reader.
            reopened_index = FilmIndex(Studio(source/"short.sqlite3"))
            preserved = read_scene_dialogue_selection(
                reopened_index, pid, "Relay03DialogueEdit", 1, tick=0,
                expected_take_id="RelayRekindleTake")
            newest = read_scene_dialogue_selection(
                reopened_index, pid, "Relay03DialogueEdit", 3, tick=0,
                expected_take_id="RelayRekindleTake")
            self.assertEqual(preserved["active_object_actor_lines"][0][
                "original_spoken_text"],
                "The relay has been silent for twenty years.")
            self.assertEqual(newest["active_object_actor_lines"][0][
                "original_spoken_text"], "The relay is coming back online.")
            self.assertEqual(reopened_index.read_revision(
                pid, "RelayRekindleTake", 1)["document_sha256"], take_sha)

    def test_ambiguous_multi_line_rewrites_do_not_claim_old_actor_lineage(self):
        first = parse_screenplay("""INT. RELAY - NIGHT

DONUT
First line.

DONUT
Second line.
""")
        original, _ = _script_scenes(
            """INT. RELAY - NIGHT

DONUT
First line.

DONUT
Second line.
""", "ScriptNoGuess", 1)
        revised, changes = _script_scenes(
            """INT. RELAY - NIGHT

DONUT
Different first line.

DONUT
Different second line.
""", "ScriptNoGuess", 2, {"scenes":original})
        self.assertEqual(len(revised[0]["lines"]), 2)
        self.assertTrue(all(x["lineage_status"] == "requires_director_reconciliation"
                            for x in revised[0]["lines"]))
        self.assertTrue(all(r["line_id"] not in {
            old["line_id"] for old in original[0]["lines"]}
            for r in revised[0]["lines"]))
        self.assertGreaterEqual(
            sum(x["kind"] == "requires_director_reconciliation" for x in changes), 2)

    def test_repeated_identical_cues_with_adjacent_insert_do_not_silently_rebind_recordings(self):
        old = """INT. RELAY - NIGHT

DONUT
Yes.

DONUT
Yes.

BOX
Understood.
"""
        revised = """INT. RELAY - NIGHT

BOX
Something changed.

DONUT
Yes.

DONUT
Yes.

BOX
Understood.
"""
        old_scenes, _ = _script_scenes(old, "RepeatedScript", 1)
        revised_scenes, impact = _script_scenes(
            revised, "RepeatedScript", 2, {"scenes":old_scenes})
        candidates = [line for line in revised_scenes[0]["lines"]
                      if line["speaker"] == "DONUT"]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(
            line["lineage_status"] == "requires_director_reconciliation"
            for line in candidates))
        old_ids = {line["line_id"] for line in old_scenes[0]["lines"]}
        self.assertTrue(all(line["line_id"] not in old_ids
                            for line in candidates))
        self.assertTrue(any(x["kind"] ==
                            "requires_director_reconciliation" for x in impact))

    def test_ambiguous_two_line_rewrite_requires_explicit_authoritative_mapping(self):
        with TemporaryDirectory() as d:
            studio = Studio(Path(d)/"film03-lineage.sqlite3")
            project = studio.create_project("Object actor production bible", "Immutable script")
            pid = project["id"]
            original_script = """INT. RELAY - NIGHT

DONUT
First line.

DONUT
Second line.
"""
            revised_script = """INT. RELAY - NIGHT

DONUT
Rewritten first.

DONUT
Rewritten second.
"""
            studio.save_screenplay(pid, original_script, expected_revision=0)
            index = FilmIndex(studio)
            author = ObjectActorDialogue(index, verify_creator_action=approves)
            author.publish_script_snapshot(
                pid, "TwoLineSource", expected_screenplay_revision=1,
                expected_manifest_revision=0, creator_event=EVENT)
            original = index.read_revision(pid, "TwoLineSource", 1)
            old_lines = original["data"]["scenes"][0]["lines"]
            studio.save_screenplay(pid, revised_script, expected_revision=1)
            author.publish_script_snapshot(
                pid, "TwoLineSource", expected_screenplay_revision=2,
                expected_manifest_revision=1, creator_event=EVENT)
            before = index.read_revision(pid, "TwoLineSource", 2)
            self.assertTrue(before["data"]["lineage_ambiguous"])
            replacements = before["data"]["scenes"][0]["lines"]
            self.assertTrue(all(x["lineage_status"] ==
                                "requires_director_reconciliation"
                                for x in replacements))
            choices = [
                {"new_line_id": replacements[n]["line_id"],
                 "old_line_id": old_lines[n]["line_id"]}
                for n in (0, 1)
            ]
            with self.assertRaises(ValueError):
                author.reconcile_ambiguous_lineage(
                    pid, "TwoLineSource", expected_manifest_revision=2,
                    decisions=[choices[0], choices[0]], creator_event=EVENT)
            denied = ObjectActorDialogue(index,
                verify_creator_action=lambda *_: False)
            with self.assertRaises(PermissionError):
                denied.reconcile_ambiguous_lineage(
                    pid, "TwoLineSource", expected_manifest_revision=2,
                    decisions=choices, creator_event="NO")
            reconciled = author.reconcile_ambiguous_lineage(
                pid, "TwoLineSource", expected_manifest_revision=2,
                decisions=choices, creator_event=EVENT)
            self.assertEqual(reconciled["revision"], 3)
            current = index.read_revision(pid, "TwoLineSource", 3)
            current_lines = current["data"]["scenes"][0]["lines"]
            self.assertFalse(current["data"]["lineage_ambiguous"])
            self.assertEqual(len(current["data"]["lineage_reconciliations"]), 2)
            self.assertEqual([x["line_id"] for x in current_lines],
                             [x["line_id"] for x in old_lines])
            self.assertTrue(all(x["lineage_status"] == "reconciled_by_director"
                                for x in current_lines))
            # All *three* source revisions survive. No screenplay was edited
            # by the lineage decision; the one actual Studio revision stays 2.
            self.assertEqual(index.read_revision(pid, "TwoLineSource", 1)[
                "document_sha256"], original["document_sha256"])
            self.assertEqual(index.read_revision(pid, "TwoLineSource", 2)[
                "document_sha256"], before["document_sha256"])
            self.assertEqual(studio.get_project(pid)["revision"], 2)
            preview = author.preview_script_changes(pid, "TwoLineSource")
            self.assertEqual(preview["new_or_changed_script_lines"], [])
            self.assertFalse(preview["requires_manual_lineage_review"])

    def test_reject_creator_false_approval_before_any_script_snapshot(self):
        with TemporaryDirectory() as d:
            studio = Studio(Path(d)/"studio.sqlite3")
            project = studio.create_project("Dialogue test", "No silent approvals")
            pid = project["id"]
            studio.save_screenplay(pid, SCRIPT_1, expected_revision=0)
            index = FilmIndex(studio)
            denied = ObjectActorDialogue(index,
                verify_creator_action=lambda event,scope:False)
            with self.assertRaises(PermissionError):
                denied.publish_script_snapshot(
                    pid,"RejectedDialogueSource",
                    expected_screenplay_revision=1,
                    expected_manifest_revision=0,
                    creator_event="NOT_AUTHORIZED")
            self.assertEqual(index.list_objects(pid,kind="dialogue"), [])


if __name__ == "__main__":
    unittest.main()
