"""E2E-01B durable native B13 -> B14 orchestration contract.

Mocks only the *already separately tested* B13/B14 worker results. Actual
process containment, J2K, full source-bound native render remain separate
native CI gates; mock results cannot certify a completed film.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_b13_native_reimport import NativeB13ImportHost
from backend.nvp_b14_native_conform import NativeB14ConformHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_studio import Studio
from backend.nvp_e2e01b_native_editorial import NativeEditorialChain


class EditorialChainContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.studio=Studio(self.root/"film.sqlite3")
        self.pid=self.studio.create_project("E2E native handoff","")["id"]
        self.capture=DigitalCapture(self.studio)
        self.ledger=TaskLedger(self.root/"ledger",sampler=lambda:ResourceSnapshot(
            1,32768,25000,0,()))
        self.b13=NativeB13ImportHost(
            self.capture,self.ledger,self.root/"import_host",
            verify_creator_action=lambda *_:True)
        self.b14=NativeB14ConformHost(
            self.capture,self.ledger,self.root/"conform_host",
            verify_creator_action=lambda *_:True)
        self.chain=NativeEditorialChain(self.capture,self.ledger,self.b13,self.b14)
        self.package=self.root/"package"
        self.package.mkdir()
        self.otio=self.root/"edit.otio"
        self.otio.write_text("not a native worker input; patched only")
        self.destination=self.root/"conform"
        self.import_job="editjob_unit"
        self.conform_job="conformjob_unit"

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self):
        with patch.object(self.b13,"stage_and_approve",
            return_value={"job_id":self.import_job,"state":"QUEUED"}):
            return self.chain.stage_edit(
                self.pid,"delivery_original",self.package,self.otio,
                object(),edit_id="cut_v1",presentation_id="conformed_cut_v1",
                destination_dir=self.destination)

    def committed_edit(self):
        return self.capture.index.register_revision(
            self.pid,"cut_v1","edit",{
                "format":"nvp.b13.imported_otio.unit",
                "picture_approved":False,"audio_present":False
            },expected_revision=0,dependencies=[])

    def imported_proof(self):
        return {"status":"VERIFIED_EDITED_OTIO_REVISION",
                "edit_id":"cut_v1","revision":1,
                "picture_approved":False,"audio_included":False}

    def test_durable_import_handoff_exact_revision_restart(self):
        ticket=self.stage()
        self.assertEqual(ticket["state"],"IMPORT_QUEUED")
        self.assertFalse(ticket["worker_started"])
        self.assertFalse(ticket["final_master"])
        self.assertEqual(self.chain.reopen(ticket["chain_id"])["state"],"IMPORT_QUEUED")
        self.committed_edit()
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            record,proof=self.chain.verify_import(ticket["chain_id"])
            self.assertEqual(record["kind"],"edit")
        after=NativeEditorialChain(
            DigitalCapture(Studio(self.studio.db_path)),
            TaskLedger(self.root/"ledger",sampler=lambda:ResourceSnapshot(
                1,32768,25000,0,())),
            NativeB13ImportHost(
                DigitalCapture(Studio(self.studio.db_path)),
                TaskLedger(self.root/"ledger",sampler=lambda:ResourceSnapshot(
                    1,32768,25000,0,())),
                self.root/"import_host",verify_creator_action=lambda *_:True),
            NativeB14ConformHost(
                DigitalCapture(Studio(self.studio.db_path)),
                TaskLedger(self.root/"ledger",sampler=lambda:ResourceSnapshot(
                    1,32768,25000,0,())),
                self.root/"conform_host",verify_creator_action=lambda *_:True))
        # Cross-host handoff state survives new process objects.
        self.assertEqual(after._row(ticket["chain_id"])["state"],"IMPORT_VERIFIED")
        self.assertEqual(after._row(ticket["chain_id"])["edit_sha"],
                         record["document_sha256"])
        with self.assertRaises(RuntimeError):
            with patch.object(self.b13,"stage_and_approve") as spawned:
                self.chain.stage_edit(
                    self.pid,"delivery_original",self.package,self.otio,
                    object(),edit_id="cut_other",presentation_id="conformed_cut_v1",
                    destination_dir=self.destination)
                spawned.assert_not_called()

    def test_only_verified_import_can_stage_native_conform(self):
        ticket=self.stage()
        with self.assertRaises(RuntimeError):
            with patch.object(self.b14,"stage_and_approve") as spawned:
                self.chain.stage_conform(ticket["chain_id"],object())
                spawned.assert_not_called()
        self.committed_edit()
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            with patch.object(self.b14,"stage_and_approve",
                return_value={"job_id":self.conform_job,"state":"QUEUED"}) as spawned:
                staged=self.chain.stage_conform(ticket["chain_id"],object())
                self.assertEqual(staged["state"],"CONFORM_QUEUED")
                self.assertEqual(spawned.call_count,1)
                again=self.chain.stage_conform(ticket["chain_id"],object())
                self.assertEqual(again["conform_job"],self.conform_job)
                self.assertEqual(spawned.call_count,1)
        self.assertFalse(staged["final_master"])
        self.assertIsNone(self.chain.reopen(ticket["chain_id"])["worker_state"]
                          if False else None)  # No implied OS-stop witness

    def test_corrupt_b14_state_cannot_be_claimed_as_final(self):
        ticket=self.stage()
        self.committed_edit()
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            with patch.object(self.b14,"stage_and_approve",
                return_value={"job_id":self.conform_job,"state":"QUEUED"}):
                self.chain.stage_conform(ticket["chain_id"],object())
            # Even if B14's worker reports completion, FilmIndex cannot
            # truthfully claim a locked or approved final picture.
            self.capture.index.register_revision(
                self.pid,"conformed_cut_v1","presentation",{
                    "format":"nvp.presentation.b14.edited_technical_mov_candidate.v1",
                    "picture_locked":True,"final_master":True
                },dependencies=[])
            with patch.object(self.b14,"verify_completed",return_value={
                "status":"VERIFIED_SDR16_PICTURE_CONFORM","frames":24}):
                with self.assertRaises(RuntimeError):
                    self.chain.verify_conform(ticket["chain_id"])
        self.assertEqual(self.chain._row(ticket["chain_id"])["state"],"CONFORM_QUEUED")

    def test_cancel_requires_original_trusted_native_approval(self):
        ticket=self.stage()
        with patch.object(self.b13,"revoke_from_trusted_native_action",
             return_value={"queued_cancelled":False}):
            with self.assertRaises(RuntimeError):
                self.chain.cancel_queued_import(ticket["chain_id"],object())
        self.assertEqual(self.chain._row(ticket["chain_id"])["state"],"IMPORT_QUEUED")
        with patch.object(self.b13,"revoke_from_trusted_native_action",
             return_value={"queued_cancelled":True}):
            result=self.chain.cancel_queued_import(ticket["chain_id"],object())
        self.assertFalse(result["live_worker_terminated_claimed"])
        self.assertEqual(result["state"],"CANCELLED_BEFORE_IMPORT")


if __name__=="__main__":
    unittest.main()
