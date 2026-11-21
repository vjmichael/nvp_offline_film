"""AUDIO-01G failure injection: durable intent and fail-closed publication."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_audio01g_mux_intent import prepare,read,transition
from backend.nvp_audio01g_mux_recovery import inspect_stopped_worker
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot


class Stub:
    pass


class MuxRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ledger=TaskLedger(Path(self.temp.name)/"ledger",
            sampler=lambda:ResourceSnapshot(0,16000,12000,0,tuple()))
        self.job="muxfault1"
        prepare(self.ledger,self.job,"0"*64)

    def tearDown(self):
        self.temp.cleanup()

    def test_journal_transition_restarts_without_rewriting_history(self):
        self.assertEqual(read(self.ledger,self.job)["state"],"prepared")
        transition(self.ledger,self.job,"prepared","running")
        with self.assertRaises(RuntimeError):
            transition(self.ledger,self.job,"prepared","verified")
        restarted=read(self.ledger,self.job)
        self.assertEqual(restarted["state"],"running")

    def test_recovery_requires_real_stop_attestation_before_audit(self):
        host=Stub()
        host.ledger=self.ledger
        with self.assertRaises(PermissionError):
            inspect_stopped_worker(host,self.job,lambda _:False)
        self.assertEqual(read(self.ledger,self.job)["state"],"prepared")

    def test_partial_output_stays_quarantined_and_reserved(self):
        transition(self.ledger,self.job,"prepared","running")
        from backend.nvp_resource_guard import AdmissionRequest
        self.ledger.admit(AdmissionRequest(self.job,"compositing","Mux",1024))
        host=Stub();host.ledger=self.ledger
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   side_effect=RuntimeError("injected partial MOV")):
            result=inspect_stopped_worker(host,self.job,lambda _:True)
        self.assertEqual(result["state"],"QUARANTINED_PARTIAL_MUX")
        self.assertEqual(read(self.ledger,self.job)["state"],"quarantined")
        self.assertEqual(self.ledger.get_task(self.job)["state"],"ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],1024)


if __name__=="__main__":
    unittest.main()
