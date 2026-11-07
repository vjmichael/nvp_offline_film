"""WO6-01: exact-source AI retake planner, intentionally zero effects.

Runs on Windows/Linux with only SQLite/Studio/FilmIndex. It does not
start models, render USD or claim independent DCP conformance.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from backend.nvp_ai_read_host import NativeAiReadHost, TrustedReadScope
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_take import FORMAT as USD_TAKE_FORMAT
from backend.nvp_studio import Studio
from backend.nvp_wo6_creator_plan import FORMAT, plan_source_retake


class WO6SourceBoundCreatorPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="nvp-wo6-")
        self.addCleanup(self.tmp.cleanup)
        self.studio = Studio(Path(self.tmp.name) / "film.sqlite3")
        self.project = self.studio.create_project("Original movie", "Retake demonstration")
        self.pid = self.project["id"]
        self.index = FilmIndex(self.studio)
        self.scope = TrustedReadScope("creator", self.pid, "turn-wo6")
        self.scene = self.index.register_revision(
            self.pid, "Scene001", "scene", {"format": "original.scene", "camera": "wide"})
        self.temporal = self.index.register_revision(
            self.pid, "Actions001", "temporal",
            {"format": "original.action", "frames": 720})
        self.take = self.index.register_revision(
            self.pid, "TakeOriginal", "take",
            {"format": USD_TAKE_FORMAT, "frozen": True,
             "scene_id": "Scene001", "scene_revision": 1,
             "scene_document_sha256": self.scene["document_sha256"],
             "timeline_id": "Actions001", "timeline_revision": 1,
             "timeline_document_sha256": self.temporal["document_sha256"],
             "artist_presentation_approved": False},
            dependencies=[
                {"object_id": "Scene001", "revision": 1, "role": "scene"},
                {"object_id": "Actions001", "revision": 1, "role": "temporal"},
            ])
        self.edit = self.index.register_revision(
            self.pid, "Edit001", "edit", {"format": "original.cut"},
            dependencies=[{
                "object_id": "TakeOriginal", "revision": 1,
                "role": "source_take",
            }])
        self.dcp = self.index.register_revision(
            self.pid, "PublishedFinal", "presentation",
            {"format": "original.delivery", "approved": False},
            dependencies=[{
                "object_id": "Edit001", "revision": 1,
                "role": "presentation",
            }])

    def test_presentation_to_original_scene_and_temporal_revision_without_writes(self):
        before = {
            item: self.index.history(self.pid, item)
            for item in ("Scene001", "Actions001", "TakeOriginal",
                         "Edit001", "PublishedFinal")
        }
        plan = plan_source_retake(
            self.index, self.pid, "PublishedFinal", 1)
        self.assertEqual(plan["format"], FORMAT)
        self.assertEqual(
            plan["status"], "PINNED_USD_RETAKE_SOURCES_FOUND_NOT_AUTHORIZED")
        self.assertEqual(
            [x["kind"] for x in plan["indexed_lineage"]],
            ["presentation", "edit", "take", "scene", "temporal"])
        self.assertEqual(plan["source_take_count"], 1)
        original = plan["source_takes"][0]
        self.assertEqual(original["take_id"], "TakeOriginal")
        self.assertEqual(
            original["source_scene"]["document_sha256"],
            self.scene["document_sha256"])
        self.assertEqual(
            original["source_timeline"]["document_sha256"],
            self.temporal["document_sha256"])
        self.assertFalse(plan["authored_usd_files_independently_reopened"])
        self.assertFalse(plan["complete_downstream_impact_coverage"])
        self.assertFalse(plan["feature_journal_custody_followed"])
        self.assertFalse(plan["creator_grant_received"])
        self.assertFalse(plan["worker_executed"])
        self.assertFalse(plan["published_dcp_mutated"])
        self.assertFalse(plan["new_take_recorded"])
        source = dict(plan)
        digest = source.pop("plan_sha256")
        self.assertEqual(
            digest, sha256(json.dumps(
                source, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False).encode("ascii")
            ).hexdigest())
        for item, revisions in before.items():
            self.assertEqual(self.index.history(self.pid, item), revisions)

    def test_retake_is_a_new_revision_and_frozen_take_is_never_rewritten(self):
        original_sha = self.take["document_sha256"]
        new_scene = self.index.register_revision(
            self.pid, "Scene001", "scene",
            {"format": "original.scene", "camera": "closer"},
            expected_revision=1)
        proposal = plan_source_retake(
            self.index, self.pid, "PublishedFinal", 1)
        self.assertEqual(proposal["source_takes"][0]["take_document_sha256"],
                         original_sha)
        self.assertEqual(proposal["source_takes"][0]["source_scene"][
            "document_sha256"], self.scene["document_sha256"])
        self.assertNotEqual(self.scene["document_sha256"],
                            new_scene["document_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid, "TakeOriginal", 1)["document_sha256"], original_sha)

    def test_flattened_presentation_without_indexed_source_never_reconstructs_take(self):
        bare = self.index.register_revision(
            self.pid, "ExternalDCP", "presentation",
            {"format": "theater.delivery", "contains_j2k": True})
        plan = plan_source_retake(
            self.index, self.pid, "ExternalDCP", bare["revision"])
        self.assertEqual(
            plan["status"], "INCOMPLETE_OR_UNLINKED_RETAKE_SOURCE_EVIDENCE")
        self.assertEqual(plan["source_take_count"], 0)
        self.assertFalse(plan["new_take_possible_from_bound_metadata"])
        self.assertTrue(plan["unindexed_reels_or_outputs_may_exist"])
        self.assertFalse(plan["feature_journal_custody_followed"])

    def test_strict_bounded_incomplete_lineage_does_not_claim_retake(self):
        result = plan_source_retake(
            self.index, self.pid, "PublishedFinal", 1, max_nodes=4)
        self.assertFalse(result["indexed_lineage_complete"])
        self.assertGreaterEqual(result["indexed_lineage_omitted_at_least"], 1)
        self.assertFalse(result["new_take_possible_from_bound_metadata"])
        with self.assertRaises(ValueError):
            plan_source_retake(self.index, self.pid, "PublishedFinal", 1,
                               max_nodes=65)

    def test_malformed_take_source_sha_cannot_authorize_retake(self):
        fake = self.index.register_revision(
            self.pid, "FakeTake", "take",
            {"format": USD_TAKE_FORMAT, "frozen": True,
             "scene_id": "Scene001", "scene_revision": 1,
             "scene_document_sha256": "0" * 64,
             "timeline_id": "Actions001", "timeline_revision": 1,
             "timeline_document_sha256": self.temporal["document_sha256"]},
            dependencies=[
                {"object_id": "Scene001", "revision": 1, "role": "scene"},
                {"object_id": "Actions001", "revision": 1, "role": "temporal"},
            ])
        with self.assertRaises(PermissionError):
            plan_source_retake(self.index, self.pid, "FakeTake",
                               fake["revision"])

    def test_other_project_and_unknown_revision_fail(self):
        other = self.studio.create_project("Unrelated", "")
        with self.assertRaises(KeyError):
            plan_source_retake(self.index, other["id"], "PublishedFinal", 1)
        with self.assertRaises(KeyError):
            plan_source_retake(self.index, self.pid, "PublishedFinal", 12)
        with self.assertRaises(ValueError):
            plan_source_retake(self.index, self.pid, "Scene001", 1)

    def test_native_read_host_reuses_existing_turn_scope_authorization(self):
        seen = []
        def authorize(scope, op, digest, spec):
            seen.append((scope, op, digest, spec))
            return scope.actor_id == "creator" and scope.turn_id == "turn-wo6"

        host = NativeAiReadHost(self.studio, authorize_read=authorize)
        catalog = host.catalog()
        cap = next(c for c in catalog["capabilities"]
                   if c["id"] == "nvp.film.plan_retake.v1")
        self.assertEqual(cap["effect"], "read")
        self.assertFalse(cap["executable_by_model"])
        self.assertFalse(catalog["authorization_provided"])
        request = {
            "capability_id": "nvp.film.plan_retake.v1",
            "project_id": self.pid,
            "object_id": "PublishedFinal",
            "revision": 1,
            "max_nodes": 64,
        }
        receipt = host.execute_read(self.scope, request)
        self.assertEqual(receipt["format"], "nvp.ai.read_receipt.v1")
        self.assertEqual(
            receipt["result"]["status"],
            "PINNED_USD_RETAKE_SOURCES_FOUND_NOT_AUTHORIZED")
        self.assertFalse(receipt["authority_granted_to_model"])
        self.assertFalse(receipt["creator_approval_granted"])
        self.assertFalse(receipt["side_effects_performed"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][2], receipt["request_sha256"])
        with self.assertRaises(PermissionError):
            host.execute_read(self.scope, {**request, "project_id": "other"})
        with self.assertRaises(ValueError):
            host.execute_read(self.scope, {**request, "approve": True})
        with self.assertRaises(ValueError):
            host.execute_read(self.scope, {**request,
                                          "capability_id": "nvp.film.freeze_take.v1"})
        self.assertEqual(len(seen), 1)

    def test_revoked_native_host_permission_blocks_new_reads(self):
        permitted = {"allowed": True}
        host = NativeAiReadHost(
            self.studio,
            authorize_read=lambda *_: permitted["allowed"])
        req = {
            "capability_id": "nvp.film.plan_retake.v1",
            "project_id": self.pid,
            "object_id": "PublishedFinal",
            "revision": 1,
        }
        host.execute_read(self.scope, req)
        permitted["allowed"] = False
        with self.assertRaises(PermissionError):
            host.execute_read(self.scope, req)


if __name__ == "__main__":
    unittest.main()
