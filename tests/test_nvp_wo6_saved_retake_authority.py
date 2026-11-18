"""WO6-B portable separate-grant and durable task ownership contracts.

The expensive native source reopen is substituted only for this authorization
test; test_nvp_wo6_saved_retake_scope exercises real OpenUSD source separately.
No test here claims a protected worker was launched.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo6_saved_retake_authority import SavedRetakeTaskAuthority
from backend.nvp_studio import Studio
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_worker_host_lease import WorkerHostLease


class RetakeAuthorityTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        studio = Studio(Path(tmp.name)/"film.sqlite")
        self.index = FilmIndex(studio)
        self.pid = studio.create_project("Film", "Idea")["id"]
        self.ledger = TaskLedger(Path(tmp.name)/"runtime",
            sampler=lambda: ResourceSnapshot(1, 32768, 24000, 0, ()))
        self.allow = True
        self.allowed = True
        self.prompts = []
        self.on_confirm = lambda: None
        self.scope = {"plan_id":"Plan", "plan_document_sha256":"a"*64,
            "new_take_id":"Take", "scope_sha256":"b"*64}
        self.host = self.make_host()
        self.patch = patch.object(self.host, "_prepare", side_effect=lambda *_:dict(self.scope))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def make_host(self):
        def confirm(doc, digest):
            self.prompts.append((doc, digest))
            self.on_confirm()
            return self.allow
        return SavedRetakeTaskAuthority(self.index, self.ledger, self.pid,
            confirm_native=confirm, live_gate=lambda _: self.allowed)

    def queue(self):
        return self.host.queue(plan_id="Plan", plan_sha256="a"*64, new_take_id="Take")

    def test_separate_denial_no_durable_task(self):
        self.allow=False
        with self.assertRaises(PermissionError):
            self.queue()
        self.assertEqual(len(self.prompts),1)
        self.assertIsNone(self.ledger.get_task(self.prompts[0][0]["task_id"]))

    def test_live_revocation_during_native_consent_fails_closed(self):
        self.on_confirm=lambda:setattr(self,"allowed",False)
        with self.assertRaises(PermissionError):
            self.queue()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertIsNone(self.ledger.get_task(self.prompts[0][0]["task_id"]))

    def test_exact_durable_spec_and_kernel_owner(self):
        queued=self.queue()
        task=queued["task_id"]
        self.assertEqual(self.ledger.get_task(task)["state"],"QUEUED")
        self.assertEqual(queued["spec_sha256"],self.prompts[0][1])
        self.assertFalse(queued["native_worker_started"])
        with WorkerHostLease(self.ledger.root):
            with self.assertRaises(RuntimeError):
                with self.host.admitted(task):
                    self.fail("Competing host acquired worker custody")
        with self.host.admitted(task) as document:
            self.assertEqual(document,self.prompts[0][0])
            self.assertEqual(self.ledger.get_task(task)["state"],"ACTIVE")
            self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],4096)
        # No actual execution or cleanup evidence was supplied by this test:
        # admission must retain the reservation, never invent success.
        self.assertEqual(self.ledger.get_task(task)["state"],"ACTIVE")
        self.assertEqual(self.ledger.get_task(task)["phase"],"recovering")

    def test_restart_cannot_reuse_native_grant(self):
        task=self.queue()["task_id"]
        restarted=self.make_host()
        with self.assertRaises(PermissionError):
            with restarted.admitted(task):
                self.fail("Restart reused old native consent")
        self.assertEqual(self.ledger.get_task(task)["state"],"QUEUED")

    def test_source_change_or_revocation_before_claim(self):
        task=self.queue()["task_id"]
        self.scope["scope_sha256"]="c"*64
        with self.assertRaises(PermissionError):
            with self.host.admitted(task):
                self.fail("Stale source admitted")
        self.host.revoke(task)
        with self.assertRaises(PermissionError):
            with self.host.admitted(task):
                self.fail("Revoked grant admitted")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_exact_execution_pin_change_denied_before_admission(self):
        pin={"worker_sha256":"d"*64,"input_sha256":"e"*64}
        self.host._seal_execution=lambda _:dict(pin)
        queued=self.queue()
        task=queued["task_id"]
        self.assertEqual(self.prompts[0][0]["execution"],pin)
        pin["worker_sha256"]="f"*64
        with self.assertRaises(PermissionError):
            with self.host.admitted(task):
                self.fail("Changed sealed worker admitted")
        self.assertEqual(self.ledger.get_task(task)["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_live_grant_is_bound_to_exact_spec_and_revoked_on_close(self):
        self.queue()
        doc=self.prompts[0][0]
        self.assertTrue(self.host.grant_live(doc))
        self.assertFalse(self.host.grant_live({**doc,"ram_mb":1024}))
        self.host.close()
        self.assertFalse(self.host.grant_live(doc))

    def test_never_claim_another_task(self):
        first=self.queue()["task_id"]
        second=self.queue()["task_id"]
        with self.host.admitted(second) as document:
            self.assertIsNone(document)
        self.assertEqual(self.ledger.get_task(first)["state"],"QUEUED")
        self.assertEqual(self.ledger.get_task(second)["state"],"QUEUED")


if __name__=="__main__":
    unittest.main()
