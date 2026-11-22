"""MASTER-01B real contained reviewer and durable host boundaries.

Tests use genuine ProRes/PCM24 and trusted creator verification fixtures;
these are technical movies, not AI performances or director-approved films.
"""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import threading
import time
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_longform_review import index_technical_reel
from backend.nvp_master01b_native_host import NativeMasterReviewHost
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded, NativeCancelRequested
from backend.nvp_studio import Studio
from tests.test_nvp_longform_review import make_prores_with_pcm24


def sampler():
    return ResourceSnapshot(1, 32768, 28000, 0.0, ())


def require(executable):
    result = shutil.which(executable)
    if result is None:
        raise unittest.SkipTest("Genuine native " + executable + " not found")
    return result


class Master01BNativeHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg, cls.ffprobe = require("ffmpeg"), require("ffprobe")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nvp-master01b-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.studio = Studio(self.root / "studio.sqlite3")
        self.index = FilmIndex(self.studio)
        self.project_id = self.studio.create_project("Thirty seconds", "Bounded reels")["id"]
        self.ledger = TaskLedger(self.root / "activity", sampler=sampler)
        self.events = set(["creator-review-001"])
        self.root_host = self.root / "native-host"
        self.host = NativeMasterReviewHost(
            self.index, self.ledger, self.root_host,
            verify_creator_action=lambda event, scope:
                event in self.events
                and scope.get("project_id") == self.project_id
                and scope.get("creator_approved_final_master") is False)

    def reels(self, seconds=10):
        refs = []
        for i, color in enumerate(("blue", "red", "green")):
            path = self.root / f"original{i}.mov"
            make_prores_with_pcm24(self.ffmpeg, path, seconds=seconds,
                                   color=color, tone=440 + i * 60)
            media = self.index.put_media_file(self.project_id, path, "video/quicktime")
            producer = f"capture{i}"
            self.index.register_revision(self.project_id, producer, "presentation", {
                "format": "nvp.master01b.unapproved_original.v1",
                "frames": seconds * 24, "movie_sha256": media["sha256"],
                "creator_approved_final_master": False,
                "dcp_delivered": False,
            }, expected_revision=0)
            reel = f"boundedreel{i}"
            index_technical_reel(self.index, self.project_id, reel, producer, 1)
            refs.append({"object_id": reel, "revision": 1})
        return refs

    def stage(self, refs=None, review_id="reviewcomplete", event="creator-review-001"):
        return self.host.stage_and_approve(
            self.project_id, review_id, refs or self.reels(), event,
            ffmpeg=self.ffmpeg, ffprobe=self.ffprobe, ram_mb=1024)

    def test_real_contained_thirty_second_film_and_independent_restart(self):
        staged = self.stage()
        job = staged["job_id"]
        self.assertEqual(self.ledger.get_task(job)["state"], "QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 0)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.project_id, "reviewcomplete")
        proof = self.host.run_next(timeout_seconds=300)
        self.assertEqual(proof["state"], "SUCCEEDED")
        self.assertEqual(proof["frames"], 720)
        self.assertFalse(proof["creator_approved_final_master"])
        self.assertEqual(self.host._grant(job)["stop_witness"], 1)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 0)
        # Reopen with fresh native host and the existing immutable source film.
        reopened = NativeMasterReviewHost(
            FilmIndex(Studio(self.studio.db_path)),
            TaskLedger(self.root / "activity", sampler=sampler),
            self.root_host, verify_creator_action=lambda *_: False)
        verified = reopened.reconcile_after_restart(job)
        self.assertEqual(verified["state"], "SUCCEEDED")
        self.assertEqual(verified["movie_sha256"], proof["movie_sha256"])
        self.assertFalse(verified["creator_approved_final_master"])
        self.assertEqual(len(self.index.read_revision(
            self.project_id, "reviewcomplete", 1)["dependencies"]), 3)

    def test_creator_denial_and_replay_are_fail_closed(self):
        refs = self.reels()
        with self.assertRaises(PermissionError):
            self.stage(refs, event="unapproved")
        self.assertEqual(self.ledger.snapshot()["tasks"], [])
        staged = self.stage(refs, review_id="review_a")
        self.assertEqual(self.host.revoke(staged["job_id"])["state"], "CANCELLED")
        with self.assertRaises(PermissionError):
            self.stage(refs, review_id="review_b")  # Consumed creator event SHA.
        self.assertEqual(self.ledger.get_task(staged["job_id"])["state"], "CANCELLED")

    def test_rejects_arbitrary_native_executable_substitution(self):
        from backend.nvp_master01b_native_host import _tool
        with self.assertRaises(PermissionError):
            _tool("ffmpeg", str(self.root / "untrusted" / "ffmpeg"))
        self.assertEqual(_tool("ffmpeg", self.ffmpeg), Path(self.ffmpeg).resolve())

    def test_tampered_sealed_plan_cannot_claim_worker(self):
        job = self.stage()["job_id"]
        target = self.root_host / job / "plan.json"
        source = json.loads(target.read_bytes())
        source["review_id"] = "forged"
        target.write_text(json.dumps(source))
        with self.assertRaises(PermissionError):
            self.host.run_next(timeout_seconds=20)
        self.assertEqual(self.ledger.get_task(job)["state"], "QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 0)

    def test_unknown_active_worker_never_releases_reservation_on_restart(self):
        job = self.stage()["job_id"]
        self.assertTrue(self.host.binding.claim_next(owner_key=self.host.owner)["admitted"])
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 1024)
        fresh = NativeMasterReviewHost(
            self.index, TaskLedger(self.root / "activity", sampler=sampler),
            self.root_host, verify_creator_action=lambda *_: False)
        status = fresh.reconcile_after_restart(job)
        self.assertEqual(status["state"], "STALE_UNVERIFIED")
        self.assertTrue(status["reservation_retained"])
        self.assertEqual(self.ledger.get_task(job)["state"], "ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 1024)

    def test_real_worker_cancelled_by_host_preserves_untouched_film(self):
        job = self.stage(review_id="cancelledreview")["job_id"]
        observed = []
        def run():
            try:
                self.host.run_next(timeout_seconds=300)
            except Exception as exc:
                observed.append(exc)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        until = time.monotonic() + 10
        while job not in self.host._cancel and time.monotonic() < until:
            time.sleep(0.01)
        self.assertIn(job, self.host._cancel, "Native worker was never admitted")
        self.host.request_cancel(job)
        thread.join(timeout=60)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(observed), 1)
        self.assertIsInstance(observed[0], NativeCancelRequested)
        self.assertEqual(self.ledger.get_task(job)["state"], "CANCELLED")
        self.assertEqual(self.host._grant(job)["stop_witness"], 1)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 0)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.project_id, "cancelledreview")

    def test_actual_host_hard_exit_after_os_stop_recovers_without_replaying(self):
        refs = self.reels()
        # A genuine separate host process performs the approved operation,
        # then os._exit immediately after the fsynced OS stop witness but
        # before ledger completion. The kernel releases its worker-host lease.
        child = """
import os,sys
from pathlib import Path
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_master01b_native_host import NativeMasterReviewHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
root=Path(sys.argv[1]); pid=sys.argv[2]
refs=[{'object_id':f'boundedreel{i}','revision':1} for i in range(3)]
def sample():return ResourceSnapshot(1,32768,28000,0.0,())
host=NativeMasterReviewHost(FilmIndex(Studio(root/'studio.sqlite3')),
    TaskLedger(root/'activity',sampler=sample),root/'native-host',
    verify_creator_action=lambda event,scope:event=='creator-crash-002' and
        scope['project_id']==pid and scope['creator_approved_final_master'] is False)
host.stage_and_approve(pid,'crashreview',refs,'creator-crash-002',ram_mb=1024)
host._complete_after_stop=lambda job: os._exit(79)
host.run_next(timeout_seconds=300)
"""
        process = subprocess.run(
            [sys.executable, "-c", child, str(self.root), self.project_id],
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=180, check=False)
        self.assertEqual(process.returncode, 79,
                         process.stderr.decode("utf8", "replace")[-1800:])
        with self.ledger._db() as db:
            job = db.execute("SELECT job_id FROM native_master01b_grants WHERE review_id=?",
                             ("crashreview",)).fetchone()[0]
        self.assertEqual(self.ledger.get_task(job)["state"], "ACTIVE")
        self.assertEqual(self.host._grant(job)["stop_witness"], 1)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 1024)
        recovered = NativeMasterReviewHost(
            FilmIndex(Studio(self.studio.db_path)),
            TaskLedger(self.root / "activity", sampler=sampler), self.root_host,
            verify_creator_action=lambda *_: False)
        completed = recovered.reconcile_after_restart(job)
        self.assertEqual(completed["state"], "SUCCEEDED")
        self.assertEqual(completed["frames"], 720)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"], 0)
        self.assertEqual(self.index.read_revision(self.project_id,"crashreview")["revision"],1)
        # Repeated cold-start reconciliation cannot duplicate the film output.
        again = recovered.reconcile_after_restart(job)
        self.assertEqual(again["state"],"SUCCEEDED")
        self.assertEqual(self.index.read_revision(self.project_id,"crashreview")["revision"],1)

    def test_stale_media_rejected_before_approval(self):
        refs = self.reels()
        source = self.index.read_revision(self.project_id, refs[1]["object_id"], 1)
        checked = self.index.verify_media_file(self.project_id, source["data"]["movie_sha256"])
        with open(checked["path"], "r+b") as blob:
            blob.seek(1000)
            content = blob.read(1)
            blob.seek(1000)
            blob.write(bytes([content[0] ^ 1]))
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            self.stage(refs)
        self.assertEqual(self.ledger.snapshot()["tasks"], [])


class GuardCancellationTests(unittest.TestCase):
    def test_native_guard_cancellation_kills_owned_tree_without_fake_progress(self):
        class Worker:
            closed = False
            def poll(self): return None
            def terminate_tree(self): self.closed = True
            def wait(self, timeout=None): return -9
        worker = Worker()
        class Ledger:
            def critical_pressure(self, task_id): raise AssertionError("Should cancel first")
        with self.assertRaises(NativeCancelRequested):
            wait_guarded(worker, Ledger(), "testjob", timeout_seconds=10,
                         should_cancel=lambda: True)
        self.assertTrue(worker.closed)


if __name__ == "__main__":
    unittest.main()