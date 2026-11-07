"""WO6-04 source/Production Bible impact and approval PREVIEW contracts.

Uses real project SQLite, FilmIndex revision edges, accepted Story Bible,
partial-order story events and scene belief infrastructure. No native
worker, no media file, and no model-generated approvals are produced.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_ai_read_host import NativeAiReadHost, TrustedReadScope
from backend.nvp_bible_context import canon_snapshot
from backend.nvp_film_index import FilmIndex
from backend.nvp_scene_mind import SceneMind
from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_temporal_ledger import TemporalLedger
from backend.nvp_wo6_impact_preview import (
    FORMAT, _indexed_consumers, preview_source_impact)


class OriginalSourceImpactAndApprovedBibleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="nvp-wo6-impact-")
        self.addCleanup(self.tmp.cleanup)
        self.studio = Studio(Path(self.tmp.name) / "studio.sqlite3")
        self.pid = self.studio.create_project("Original Film", "Human-directed")["id"]
        script = self.studio.save_screenplay(
            self.pid, "INT. ENGINEERING BAY - NIGHT\n\nADA\nThe relay is alive.", 0)
        self.scene_id = script["scenes"][0]["id"]
        self.script_revision = script["revision"]
        self.index = FilmIndex(self.studio)
        self.scene = self.index.register_revision(
            self.pid, "RelayScene", "scene",
            {"format": "nvp.test.scene.v1", "camera": "wide", "edited": False})
        self.take = self.index.register_revision(
            self.pid, "FrozenRelayTake", "take",
            {"format": "nvp.test.frozen.take.v1", "frozen": True},
            dependencies=[{"object_id": "RelayScene",
                           "revision": 1, "role": "scene"}])
        self.edit = self.index.register_revision(
            self.pid, "RelayEdit", "edit",
            {"format": "nvp.test.edit.v1"},
            dependencies=[{"object_id": "FrozenRelayTake",
                           "revision": 1, "role": "source_take"}])
        self.master = self.index.register_revision(
            self.pid, "RelayMaster", "master",
            {"format": "nvp.test.master.v1"},
            dependencies=[{"object_id": "RelayEdit",
                           "revision": 1, "role": "presentation"}])
        self.final = self.index.register_revision(
            self.pid, "RelayDCP", "presentation",
            {"format": "nvp.test.delivery.v1", "accepted": False},
            dependencies=[{"object_id": "RelayMaster",
                           "revision": 1, "role": "presentation"}])
        self.bible = StoryBible(self.studio)
        SceneMind(self.studio)  # existing StoryTimeline and mind tables
        self.character = self.bible.create_entity(
            self.pid, "character", "Ada")
        proposed = self.bible.propose_fact(
            self.pid, self.character["id"],
            "reluctance", "Ada refuses to open the relay alone")
        latest = self.bible.get_entity(self.pid, self.character["id"])
        self.accepted = self.bible.decide_fact(
            self.pid, proposed["id"], "accept", latest["revision"])
        unapproved = self.bible.propose_fact(
            self.pid, self.character["id"],
            "invention", "SECRET AI IDEA", origin="ai_proposal")
        self.unapproved_id = unapproved["id"]
        latest = self.bible.get_entity(self.pid, self.character["id"])
        self.bible.link_scene(
            self.pid, self.character["id"], self.scene_id,
            latest["revision"])

    def bible_digest(self):
        with self.studio._connection() as db:
            return canon_snapshot(db,self.pid,self.scene_id)["digest"]

    def preview(self, **overrides):
        args = {
            "scene_id": self.scene_id,
            "screenplay_revision": self.script_revision,
            "expected_bible_digest": self.bible_digest(),
            "max_nodes": 32,
        }
        args.update(overrides)
        return preview_source_impact(
            self.index, self.pid, "RelayScene", 1,
            self.scene["document_sha256"],
            "revise_scene", **args)

    def test_proven_scene_take_edit_master_dcp_chain_and_full_approved_canon(self):
        histories = {name:self.index.history(self.pid,name) for name in (
            "RelayScene","FrozenRelayTake","RelayEdit","RelayMaster","RelayDCP")}
        result=self.preview()
        self.assertEqual(result["format"], FORMAT)
        self.assertEqual(
            result["status"],"READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT")
        self.assertEqual(
            [(x["object_id"],x["kind"],x["depth"]) for x in
             result["indexed_downstream"]],
            [("FrozenRelayTake","take",1),("RelayEdit","edit",2),
             ("RelayMaster","master",3),("RelayDCP","presentation",4)])
        self.assertFalse(result["indexed_downstream_truncated"])
        self.assertFalse(result["all_downstream_outputs_proven"])
        self.assertFalse(result["feature_journal_outputs_reconciled"])
        self.assertTrue(result["other_unindexed_derivatives_possible"])
        bible=result["approved_production_bible"]
        self.assertEqual(bible["status"],
                         "APPROVED_SCENE_PRODUCTION_BIBLE_SNAPSHOT")
        self.assertEqual(bible["digest"],self.bible_digest())
        self.assertIn("refuses to open the relay alone",
                      bible["approved_facts_text"])
        self.assertNotIn("SECRET AI IDEA",bible["approved_facts_text"])
        self.assertTrue(bible["story_order_verified"])
        self.assertTrue(bible["character_knowledge_verified"])
        self.assertFalse(result["new_take_created"])
        self.assertFalse(result["final_dcp_replaced"])
        self.assertFalse(result["native_worker_executed"])
        gates=result["approval_gate_preview"]
        self.assertTrue(gates)
        self.assertIn("new_immutable_take",{x["gate_id"] for x in gates})
        self.assertIn("final_delivery_and_cinema_qc",
                      {x["gate_id"] for x in gates})
        self.assertTrue(all(x["state"]=="NOT_REQUESTED"
                            and x["approval_token"] is None
                            and not x["approval_issued_by_ai"] for x in gates))
        self.assertFalse(result["native_execution_admissible_from_this_preview"])
        self.assertFalse(result["creator_approved"])
        raw=dict(result); digest=raw.pop("preview_sha256")
        self.assertEqual(hashlib.sha256(json.dumps(
            raw,sort_keys=True,ensure_ascii=True,
            allow_nan=False,separators=(",",":")).encode("ascii")).hexdigest(),
            digest)
        for name,historical in histories.items():
            self.assertEqual(self.index.history(self.pid,name),historical)

    def test_normalized_temporal_event_consumer_is_included_without_duplicate(self):
        ledger=TemporalLedger(self.index)
        ledger.publish(
            self.pid,"CameraActions",[
                {"event_id":"ActiveCamera","event_kind":"camera",
                 "subject_id":"Camera","start_tick":0,"end_tick":100,
                 "source_id":"RelayScene","source_revision":1,
                 "payload":{"camera":"wide"}}
            ],duration_tick=200)
        chain=self.preview()
        ids=[x["object_id"] for x in chain["indexed_downstream"]]
        self.assertEqual(ids.count("CameraActions"),1)
        self.assertIn("CameraActions",ids)
        self.assertEqual(next(x["depth"] for x in chain["indexed_downstream"]
                              if x["object_id"]=="CameraActions"),1)

    def test_bible_fact_change_requires_exact_accepted_fact_and_known_scene(self):
        result=preview_source_impact(
            self.index,self.pid,"RelayScene",1,self.scene["document_sha256"],
            "revise_bible_fact",scene_id=self.scene_id,
            screenplay_revision=self.script_revision,
            bible_fact_id=self.accepted["id"])
        fact=result["approved_bible_fact_impact"]
        self.assertEqual(fact["fact_id"],self.accepted["id"])
        self.assertEqual(fact["fact_key"],"reluctance")
        self.assertTrue(fact["accepted_fact_may_be_superseded_only_by_creator"])
        self.assertEqual(fact["known_linked_scenes"][0]["scene_id"],self.scene_id)
        self.assertFalse(result["creator_approved"])
        with self.assertRaises(PermissionError):
            preview_source_impact(
                self.index,self.pid,"RelayScene",1,
                self.scene["document_sha256"],"revise_bible_fact",
                scene_id=self.scene_id,
                screenplay_revision=self.script_revision,
                bible_fact_id=self.unapproved_id)
        with self.assertRaises(ValueError):
            self.preview(bible_fact_id=self.accepted["id"])

    def test_old_scene_and_existing_dcp_unchanged_even_when_new_revision_exists(self):
        self.index.register_revision(
            self.pid,"RelayScene","scene",
            {"format":"nvp.test.scene.v1","camera":"close","edited":True},
            expected_revision=1)
        old=self.preview()
        self.assertEqual(old["status"],"HISTORICAL_SOURCE_REFRESH_REQUIRED")
        self.assertFalse(old["proposal_source"]["is_current_head"])
        self.assertEqual(old["proposal_source"]["head_revision_observed"],2)
        self.assertEqual(
            self.index.read_revision(self.pid,"RelayDCP",1)[
                "document_sha256"],self.final["document_sha256"])
        self.assertEqual(
            self.index.read_revision(self.pid,"RelayScene",1)[
                "document_sha256"],self.scene["document_sha256"])

    def test_bounded_graph_truncation_and_unindexed_custody_block(self):
        result=self.preview(max_nodes=2)
        self.assertEqual(
            [x["kind"] for x in result["indexed_downstream"]],
            ["take","edit"])
        self.assertTrue(result["indexed_downstream_truncated"])
        self.assertIn(
            "Indexed impact graph truncated; search further before approval",
            result["approval_blockers"])
        with self.assertRaises(ValueError):
            self.preview(max_nodes=65)
        with self.assertRaises(ValueError):
            self.preview(max_nodes=True)

    def test_creator_supplied_delivery_budget_is_only_an_estimate(self):
        result=self.preview(delivery={
            "frames": 43200,"profile":"2K_FLAT_24","channels":6})
        capacity=result["resource_estimate"]
        self.assertEqual(capacity["frame_count"],43200)
        self.assertEqual(capacity["channels"],6)
        self.assertGreaterEqual(capacity["reel_count"],6)
        self.assertGreater(capacity["scratch_upper_estimate_bytes"],0)
        self.assertFalse(capacity["actual_free_disk_checked"])
        self.assertFalse(capacity["actual_runtime_admitted"])
        self.assertFalse(capacity["throughput_measured"])
        with self.assertRaises(ValueError):
            self.preview(delivery={"frames":43200,"channels":6,
                                   "profile":"2K_FLAT_24","output_path":"C:/"})

    def test_stale_screenplay_bible_digest_forged_source_and_cross_project_fail(self):
        with self.assertRaises(PermissionError):
            preview_source_impact(
                self.index,self.pid,"RelayScene",1,"0"*64,
                "revise_scene")
        with self.assertRaises(ValueError):
            preview_source_impact(
                self.index,self.pid,"RelayScene",1,
                self.scene["document_sha256"],"republish_dcp")
        with self.assertRaises(RuntimeError):
            self.preview(expected_bible_digest="0"*64)
        other=self.studio.create_project("Other","")["id"]
        with self.assertRaises(KeyError):
            preview_source_impact(
                self.index,other,"RelayScene",1,self.scene["document_sha256"],
                "revise_scene")
        updated=self.studio.save_screenplay(
            self.pid,"INT. ENGINEERING BAY - DAY\n\nADA\nChanged.",1)
        with self.assertRaises(RuntimeError):
            self.preview(screenplay_revision=1)

    def test_current_host_authorization_is_per_turn_and_rejects_approval_injection(self):
        grants={"allow":True}
        seen=[]
        def decide(scope,op,digest,request):
            seen.append((scope,op,digest,request))
            return grants["allow"]
        host=NativeAiReadHost(self.studio,authorize_read=decide)
        self.assertIn("nvp.film.preview_source_impact.v1",
                      [c["id"] for c in host.catalog()["capabilities"]])
        scope=TrustedReadScope("creator",self.pid,"turn-1")
        req={
            "capability_id":"nvp.film.preview_source_impact.v1",
            "project_id":self.pid,"source_id":"RelayScene",
            "source_revision":1,
            "source_sha256":self.scene["document_sha256"],
            "change_kind":"retake",
            "scene_id":self.scene_id,
            "screenplay_revision":self.script_revision,
        }
        got=host.execute_read(scope,req)
        self.assertEqual(got["result"]["format"],FORMAT)
        self.assertEqual(got["request_sha256"],seen[-1][2])
        self.assertFalse(got["authority_granted_to_model"])
        self.assertFalse(got["side_effects_performed"])
        self.assertFalse(got["creator_approval_granted"])
        grants["allow"]=False
        with self.assertRaises(PermissionError):
            host.execute_read(
                TrustedReadScope("creator",self.pid,"turn-2"),req)
        grants["allow"]=True
        with self.assertRaises(PermissionError):
            host.execute_read(scope,{**req,"project_id":"other"})
        with self.assertRaises(ValueError):
            host.execute_read(scope,{**req,"approved":True})
        with self.assertRaises(ValueError):
            host.execute_read(scope,{**req,"worker_command":"render now"})
        self.assertEqual(len(seen),1)

    def test_uninitialized_bible_is_reported_not_silently_created(self):
        root=Path(self.tmp.name)/"other.sqlite3"
        studio=Studio(root)
        pid=studio.create_project("No Bible","")["id"]
        p=studio.save_screenplay(pid,
            "INT. CABIN - NIGHT\n\nSAGE\nWe leave.",0)
        index=FilmIndex(studio)
        src=index.register_revision(pid,"NewScene","scene",
                                    {"format":"test"})
        packet=preview_source_impact(
            index,pid,"NewScene",1,src["document_sha256"],
            "revise_scene",scene_id=p["scenes"][0]["id"],
            screenplay_revision=p["revision"])
        self.assertEqual(packet["approved_production_bible"]["status"],
                         "PRODUCTION_BIBLE_NOT_FULLY_INITIALIZED")
        self.assertIn("Approved scene Bible is missing/incomplete or unselected",
                      packet["approval_blockers"])
        with studio._connection() as db:
            self.assertFalse(db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='bible_entities'""").fetchone())

    def test_bible_change_in_progress_fails_before_preview_return(self):
        actual=self.studio.get_project
        # Deliberately alter accepted canon between source inspection and
        # its final Bible digest fence without ever creating an NVP edit.
        from backend import nvp_wo6_impact_preview as module
        initial=module._bible_snapshot
        calls={"count":0}
        def mutated(studio,pid,scene,rev,digest):
            calls["count"]+=1
            got=initial(studio,pid,scene,rev,digest)
            if calls["count"]==1:
                proposal=self.bible.propose_fact(
                    self.pid,self.character["id"],"height","1.75m")
                fresh=self.bible.get_entity(self.pid,self.character["id"])
                self.bible.decide_fact(
                    self.pid,proposal["id"],"accept",fresh["revision"])
            return got
        with patch.object(module,"_bible_snapshot",side_effect=mutated):
            with self.assertRaisesRegex(RuntimeError,"Production Bible changed"):
                self.preview(expected_bible_digest=None)


if __name__=="__main__":
    unittest.main()
