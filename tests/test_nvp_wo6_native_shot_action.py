"""WO6-05 native creator-authorized real OpenUSD camera/blocking/light edits."""
import tempfile
import time
import unittest
from pathlib import Path

from backend.nvp_ai_read_host import TrustedReadScope, NativeAiReadHost
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_shot_action import NativeShotActionHost, ACTION_KINDS

T = TICKS_PER_SECOND


class NativeDirectorShotApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.studio = Studio(root / "film.sqlite")
        self.pid = self.studio.create_project("Director shot approvals", "")["id"]
        self.index = FilmIndex(self.studio)
        self.scenes = OpenUSDSceneBridge(self.index)
        self.temporal = TemporalLedger(self.index)
        self.scenes.publish(self.pid, "scene", prims=[
            {"path": "/World/Actor", "role": "actor", "position": [0, 0, 0]},
            {"path": "/World/Camera", "role": "camera", "position": [0, 3, -8]},
            {"path": "/World/Light", "role": "light", "position": [2, 3, 1]},
        ], curves=[{"path": "/World/Actor", "samples": [
            {"tick": 0, "position": [0, 0, 0]},
            {"tick": 2*T, "position": [6, 0, 0]},
        ]}], native_schemas=True)
        self.index.register_revision(
            self.pid, "actor_source", "performance",
            {"format": "test.wo6.native.actor.v1", "role": "actor"},
            expected_revision=0)
        self.temporal.publish(
            self.pid, "timeline", [{
                "event_id": "walk", "event_kind": "action",
                "subject_id": "actor_source", "start_tick": 0,
                "end_tick": 2*T, "source_id": "actor_source",
                "source_revision": 1,
                "payload": {"usd_prim_path": "/World/Actor", "verb": "walk"},
            }], duration_tick=3*T)
        self.take = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda *_: True)
        self.take.freeze(
            self.pid, "original_take", scene_id="scene", scene_revision=1,
            timeline_id="timeline", timeline_revision=1,
            sample_ticks=[0,T], creator_event="human")
        self.take_sha = self.index.read_revision(
            self.pid, "original_take", 1)["document_sha256"]
        self.scene_sha = self.index.read_revision(
            self.pid, "scene", 1)["document_sha256"]
        self.scope = TrustedReadScope("director", self.pid, "turn_1")
        self.creator_ok = True
        self.native_ok = True
        self.creator_calls = []
        self.native_calls = []
        def confirm(decision, creative_scope):
            self.creator_calls.append((decision, creative_scope))
            return (self.creator_ok and decision == "human_click_approved"
                    and creative_scope["no_original_take_mutation"] is True)
        def native(scope, sha, doc):
            self.native_calls.append((scope, sha))
            return (self.native_ok and scope == self.scope and
                    doc["project_id"] == self.pid)
        ledger = TaskLedger(
            root / "runtime",
            sampler=lambda: ResourceSnapshot(
                time.time(), 32768, 24576, 0., ()))
        self.host = NativeShotActionHost(
            self.index, ledger, (root / "native_jobs").absolute(),
            confirm_creator=confirm, authorize_native=native)

    def _request(self, kind, shot_id):
        change = {
            "camera": {"path":"/World/Camera",
                       "property":"camera_focal_length_mm","value":85.},
            "blocking": {"path":"/World/Actor",
                         "property":"translation_offset","value":[1,0,0]},
            "lighting": {"path":"/World/Light",
                         "property":"light_intensity","value":250.},
        }[kind]
        preview = preview_source_impact(
            self.index, self.pid, "scene", 1, self.scene_sha,
            ACTION_KINDS[kind][0], max_nodes=32)
        return {
            "creator_decision_id": "human_click_approved",
            "action_kind": kind, "shot_id": shot_id,
            "take_id": "original_take", "take_sha256": self.take_sha,
            "scene_id": "scene", "scene_revision": 1,
            "scene_sha256": self.scene_sha, "start_tick": 0,
            "end_tick": T, "changes": [change],
            "purpose": "framing" if kind != "lighting" else "lighting",
            "continuity_policy": "preserve",
            "reason": "Director approved one bounded new shot-local layer",
            "expected_preview_sha256": preview["preview_sha256"],
        }

    def test_three_native_camera_blocking_lighting_operations_preserve_take(self):
        for kind in ("camera", "blocking", "lighting"):
            req = self._request(kind, "approved_" + kind)
            task = self.host.queue_shot(self.scope, **req)
            self.assertEqual(task["state"], "QUEUED")
            self.assertFalse(task["native_worker_started"])
            completed = self.host.run_next(timeout_seconds=150)
            self.assertEqual(completed["state"], "SUCCEEDED")
            shooter = OpenUSDShotOverrides(
                self.index, verify_director_action=lambda *_: False)
            evidence = shooter.evaluate(
                self.pid, "approved_" + kind, 1, tick=T//2)
            self.assertEqual(
                evidence["shot_document_sha256"],
                completed["shot_document_sha256"])
            self.assertFalse(evidence["source_performance_modified"])
            self.assertFalse(evidence["rendered_frames"])
            self.assertEqual(self.index.read_revision(
                self.pid, "original_take", 1)["document_sha256"],
                self.take_sha)
            self.assertEqual(
                self.host.ledger.get_task(task["task_id"])["state"],
                "SUCCEEDED")
        self.assertGreater(len(self.creator_calls), 2)
        self.assertGreater(len(self.native_calls), 2)

    def test_denied_approval_and_invalid_model_origin_do_not_write(self):
        req = self._request("camera", "denied")
        self.creator_ok = False
        with self.assertRaises(PermissionError):
            self.host.queue_shot(self.scope, **req)
        self.creator_ok = True
        self.native_ok = False
        with self.assertRaises(PermissionError):
            self.host.queue_shot(self.scope, **req)
        self.native_ok = True
        with self.assertRaises(ValueError):
            self.host.queue_shot(
                self.scope, **{**req, "changes": [
                    {"path":"/World/Actor", "property":"camera_focal_length_mm",
                     "value":85.}]})
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "denied")
        read = NativeAiReadHost(
            self.studio, authorize_read=lambda *_: True)
        self.assertNotIn(
            "nvp.film.author_director_shot.v1",
            [x["id"] for x in read.catalog()["capabilities"]])

    def test_revoke_before_dispatch_and_stale_source_refuses_work(self):
        task = self.host.queue_shot(
            self.scope, **self._request("blocking", "revoked"))
        self.native_ok = False
        with self.assertRaises(PermissionError):
            self.host.run_next()
        self.assertEqual(
            self.host.ledger.get_task(task["task_id"])["state"], "QUEUED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "revoked")
        self.native_ok = True
        self.scenes.publish(
            self.pid, "scene", prims=[
                {"path": "/World/Actor", "role": "actor", "position": [0,0,0]},
                {"path": "/World/Camera", "role": "camera", "position": [0,3,-8]},
                {"path": "/World/Light", "role": "light", "position": [2,3,1]},
            ], curves=[], native_schemas=True, expected_revision=1)
        with self.assertRaises(PermissionError):
            self.host.run_next()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "revoked")
        self.assertEqual(
            self.host.ledger.get_task(task["task_id"])["state"], "INTERRUPTED")


if __name__ == "__main__":
    unittest.main()
