"""WO6-05 genuine native OpenUSD Take action, host approval and no rewrite.

Requires real usd-core and NVP's native contained worker. No mocked success
paths for the positive Take creation case.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_take_action import NativeTakeActionHost


class CreatorAndHostNativeTakeAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.studio = Studio(root / "studio.sqlite3")
        self.pid = self.studio.create_project(
            "WO6 director-approved Take", "immutable original production")["id"]
        self.index = FilmIndex(self.studio)
        self.scenes = OpenUSDSceneBridge(self.index)
        self.temporal = TemporalLedger(self.index)
        self.scene_id = "wo6_scene"
        self.timeline_id = "wo6_timeline"
        self.prims = [
            {"path": "/World/Actor", "role": "actor",
             "position": [0, 0, 0]},
            {"path": "/World/Camera", "role": "camera",
             "position": [0, 2, -5]},
        ]
        self.curves = [{
            "path": "/World/Actor",
            "samples": [
                {"tick": 0, "position": [0, 0, 0]},
                {"tick": 2 * TICKS_PER_SECOND, "position": [3, 0, 0]},
            ],
        }]
        self.scenes.publish(self.pid, self.scene_id, prims=self.prims,
                            curves=self.curves)
        self.index.register_revision(
            self.pid, "wo6_actor", "performance",
            {"format": "test.wo6.actor", "actor": "Actor"}, expected_revision=0)
        self.temporal.publish(
            self.pid, self.timeline_id,
            [{
                "event_id": "actor_walk", "event_kind": "action",
                "subject_id": "Actor", "start_tick": 0,
                "end_tick": 2 * TICKS_PER_SECOND,
                "source_id": "wo6_actor", "source_revision": 1,
                "payload": {"verb": "walk", "usd_prim_path": "/World/Actor"},
            }],
            duration_tick=3 * TICKS_PER_SECOND,
        )
        self.scope = TrustedReadScope("human_director", self.pid, "host_turn_01")
        self.creative_ok = True
        self.native_ok = True
        self.creative_calls = []
        self.native_calls = []

        def creative(decision, scope):
            self.creative_calls.append((decision, scope))
            return (self.creative_ok and decision == "creator_decision_1"
                    and scope["project_id"] == self.pid
                    and scope["new_take_id"].startswith("new_take_")
                    and scope["old_takes_immutable"] is True)

        def native(scope, sha, document):
            self.native_calls.append((scope, sha))
            return (self.native_ok and scope == self.scope
                    and document["operation"] ==
                    "nvp.film.create_frozen_take.v1"
                    and document["project_id"] == self.pid)

        self.ledger = TaskLedger(
            root / "ledger",
            sampler=lambda: ResourceSnapshot(
                time.time(), 16384, 14000, 0.0, ()))
        self.host = NativeTakeActionHost(
            self.index, self.ledger, (root / "jobs").absolute(),
            confirm_creator=creative, authorize_native=native)

    def _exact_args(self, take_id="new_take_a"):
        scene = self.index.read_revision(self.pid, self.scene_id)
        temporal = self.index.read_revision(self.pid, self.timeline_id)
        preview = preview_source_impact(
            self.index, self.pid, self.scene_id, scene["revision"],
            scene["document_sha256"], "retake", max_nodes=32)
        return {
            "creator_decision_id": "creator_decision_1",
            "scene_id": self.scene_id,
            "scene_revision": scene["revision"],
            "scene_sha256": scene["document_sha256"],
            "timeline_id": self.timeline_id,
            "timeline_revision": temporal["revision"],
            "timeline_sha256": temporal["document_sha256"],
            "new_take_id": take_id,
            "sample_ticks": [0, TICKS_PER_SECOND],
            "expected_preview_sha256": preview["preview_sha256"],
        }

    def test_native_contained_new_take_reopen_preserves_prior_take_and_history(self):
        prior = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda *_: True).freeze(
                self.pid, "prior_frozen_take",
                scene_id=self.scene_id, scene_revision=1,
                timeline_id=self.timeline_id, timeline_revision=1,
                sample_ticks=[0], creator_event="prior_human")
        historic_sha = prior["document_sha256"]
        request = self._exact_args()
        result = self.host.queue_new_take(self.scope, **request)
        self.assertEqual(result["state"], "QUEUED")
        self.assertFalse(result["native_worker_started"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "new_take_a")
        done = self.host.run_next(timeout_seconds=150)
        self.assertEqual(done["state"], "SUCCEEDED")
        self.assertTrue(done["native_worker_executed"])
        self.assertFalse(done["film_delivered"])
        created = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda *_: False).verify_take(
                self.pid, "new_take_a")
        self.assertEqual(created["status"], "VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(created["take_document_sha256"],
                         done["take_document_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid, "prior_frozen_take", 1)["document_sha256"], historic_sha)
        self.assertEqual(self.index.read_revision(
            self.pid, "new_take_a", 1)["revision"], 1)
        receipt = json.loads(
            (self.host.root / result["task_id"] / "receipt.json").read_text())
        self.assertTrue(receipt["native_take_verified"])
        self.assertFalse(receipt["existing_dcp_replaced"])
        self.assertFalse(receipt["rendered_frames"])
        self.assertTrue(self.creative_calls)
        self.assertTrue(self.native_calls)
        self.assertEqual(self.ledger.get_task(result["task_id"])["state"],
                         "SUCCEEDED")

    def test_no_human_approval_or_native_permission_cannot_queue(self):
        req = self._exact_args()
        self.creative_ok = False
        with self.assertRaises(PermissionError):
            self.host.queue_new_take(self.scope, **req)
        self.creative_ok = True
        self.native_ok = False
        with self.assertRaises(PermissionError):
            self.host.queue_new_take(self.scope, **req)
        self.assertFalse(list(self.host.root.iterdir()))
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "new_take_a")

    def test_revoked_pending_approval_blocks_admission_without_a_take(self):
        task = self.host.queue_new_take(self.scope, **self._exact_args())
        self.native_ok = False
        with self.assertRaises(PermissionError):
            self.host.run_next()
        self.assertEqual(self.ledger.get_task(task["task_id"])["state"],
                         "QUEUED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "new_take_a")
        cancelled = self.ledger.cancel_queued(
            task["task_id"], owner_key=self.host.owner)
        self.assertEqual(cancelled["state"], "CANCELLED")

    def test_stale_scene_and_forged_sha_are_never_dispatched(self):
        arguments = self._exact_args()
        arguments["scene_sha256"] = "0" * 64
        with self.assertRaises(PermissionError):
            self.host.queue_new_take(self.scope, **arguments)
        task = self.host.queue_new_take(self.scope, **self._exact_args())
        self.scenes.publish(
            self.pid, self.scene_id, prims=self.prims,
            curves=[{
                "path": "/World/Actor",
                "samples": [
                    {"tick": 0, "position": [0, 0, 0]},
                    {"tick": 2 * TICKS_PER_SECOND, "position": [9, 0, 0]},
                ],
            }],
            expected_revision=1)
        with self.assertRaises(PermissionError):
            self.host.run_next()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "new_take_a")
        self.assertEqual(self.ledger.get_task(task["task_id"])["state"],
                         "INTERRUPTED")

    def test_model_request_is_not_a_native_execute_capability(self):
        from backend.nvp_ai_read_host import NativeAiReadHost
        read = NativeAiReadHost(
            self.studio, authorize_read=lambda *_: True)
        ids = [x["id"] for x in read.catalog()["capabilities"]]
        self.assertNotIn("nvp.film.create_frozen_take.v1", ids)
        with self.assertRaises(ValueError):
            read.execute_read(
                self.scope, {"capability_id": "nvp.film.create_frozen_take.v1",
                             "project_id": self.pid})
        with self.assertRaises(ValueError):
            self.host.queue_new_take(
                self.scope, **{**self._exact_args(),
                               "sample_ticks": [0, 0]})
