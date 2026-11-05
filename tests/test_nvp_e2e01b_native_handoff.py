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
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            recovered=self.chain.reopen(ticket["chain_id"])
        self.assertEqual(recovered["state"],"CONFORM_QUEUED")
        self.assertIsNone(recovered["worker_state"])
        self.assertFalse(recovered["recovered_without_relaunch"])

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

    def test_b13_stage_failure_retains_durable_uncertain_intent(self):
        with patch.object(self.b13,"stage_and_approve",
                          side_effect=RuntimeError("crash after native B13 stage")):
            with self.assertRaisesRegex(RuntimeError,"crash after"):
                self.chain.stage_edit(
                    self.pid,"delivery_original",self.package,self.otio,
                    object(),edit_id="cut_v1",presentation_id="conformed_cut_v1",
                    destination_dir=self.destination)
        with self.ledger._db() as db:
            record=db.execute("""SELECT chain_id,state,import_job
                FROM native_e2e01b_chains WHERE project_id=?""",(self.pid,)).fetchone()
        self.assertEqual(record[1],"IMPORT_STAGING_UNCERTAIN")
        self.assertTrue(record[2].startswith("pending_"))
        self.assertTrue(self.chain.reopen(record[0])["requires_native_reconciliation"])
        with patch.object(self.b13,"stage_and_approve") as duplicate:
            with self.assertRaises(Exception):
                self.chain.stage_edit(
                    self.pid,"delivery_original",self.package,self.otio,
                    object(),edit_id="cut_v1",presentation_id="conformed_cut_v1",
                    destination_dir=self.destination)
            duplicate.assert_not_called()

    def test_b14_stage_failure_retains_durable_uncertain_intent(self):
        ticket=self.stage()
        self.committed_edit()
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            with patch.object(self.b14,"stage_and_approve",
                side_effect=RuntimeError("crash after native B14 stage")):
                with self.assertRaisesRegex(RuntimeError,"crash after"):
                    self.chain.stage_conform(ticket["chain_id"],object())
        self.assertEqual(self.chain._row(ticket["chain_id"])["state"],
                         "CONFORM_STAGING_UNCERTAIN")
        self.assertTrue(self.chain.reopen(ticket["chain_id"])[
                        "requires_native_reconciliation"])
        with patch.object(self.b14,"stage_and_approve") as duplicate:
            with self.assertRaises(RuntimeError):
                self.chain.stage_conform(ticket["chain_id"],object())
            duplicate.assert_not_called()

    def _finish_native_task_fixture(self,job):
        from backend.nvp_resource_guard import AdmissionRequest
        accepted=self.ledger.admit(AdmissionRequest(
            job,"compositing","Native recovery fixture",1024))
        self.assertTrue(accepted["admitted"])
        self.ledger.finish(job,"SUCCEEDED","Simulated host-verified stop")

    def test_completed_b13_native_grant_reconciles_lost_stage_response(self):
        import time
        with patch.object(self.b13,"stage_and_approve",
                          side_effect=RuntimeError("native host returned after crash")):
            with self.assertRaises(RuntimeError):
                self.chain.stage_edit(
                    self.pid,"delivery_original",self.package,self.otio,
                    object(),edit_id="cut_v1",presentation_id="conformed_cut_v1",
                    destination_dir=self.destination)
        record=self.committed_edit()
        job="editjob_recovered"
        self._finish_native_task_fixture(job)
        digest="a"*64
        with self.ledger._db() as db:
            db.execute("""INSERT INTO native_b13_import_grants(
                job_id,approval_id,project_id,delivery_id,delivery_sha256,
                take_sha256,package_dir,edit_id,expected_revision,
                edited_otio_sha256,plan_sha256,spec_sha256,python_sha256,
                script_sha256,ram_mb,issued_at,expires_at,result_document_sha256)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job,"approved_import_fixture",self.pid,"delivery_original",
                 digest,digest,str(self.package.resolve()),"cut_v1",0,
                 digest,digest,digest,digest,digest,1024,time.time(),
                 time.time()+1200,record["document_sha256"]))
            chain_id=db.execute("""SELECT chain_id FROM native_e2e01b_chains
                WHERE project_id=?""",(self.pid,)).fetchone()[0]
        with patch.object(self.b13,"verify_completed",
                          return_value=self.imported_proof()):
            recovered=self.chain.reopen(chain_id)
        self.assertEqual(recovered["state"],"IMPORT_VERIFIED")
        self.assertTrue(recovered["recovered_without_relaunch"])
        self.assertEqual(self.chain._row(chain_id)["import_job"],job)

    def test_completed_b14_native_grant_reconciles_lost_stage_response(self):
        import time
        ticket=self.stage()
        edit=self.committed_edit()
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            with patch.object(self.b14,"stage_and_approve",
                              side_effect=RuntimeError("native stage response lost")):
                with self.assertRaises(RuntimeError):
                    self.chain.stage_conform(ticket["chain_id"],object())
        picture=self.capture.index.register_revision(
            self.pid,"conformed_cut_v1","presentation",{
                "format":"fixture.sourcebound.sdr16",
                "picture_locked":False,"final_master":False})
        job="conformjob_recovered"
        self._finish_native_task_fixture(job)
        digest="b"*64
        with self.ledger._db() as db:
            db.execute("""INSERT INTO native_b14_conform_grants(
                job_id,approval_id,project_id,edit_id,edit_revision,edit_sha,
                package_dir,destination_dir,presentation_id,ram_mb,plan_sha,
                spec_sha,python_sha,script_sha,expires_at,result_sha)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job,"approved_conform_fixture",self.pid,"cut_v1",1,
                 edit["document_sha256"],str(self.package.resolve()),
                 str(self.destination.absolute()),"conformed_cut_v1",
                 1024,digest,digest,digest,digest,time.time()+1200,
                 picture["document_sha256"]))
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            with patch.object(self.b14,"verify_completed",
                              return_value={
                              "status":"VERIFIED_SDR16_PICTURE_CONFORM",
                              "frames":24}):
                restored=self.chain.reopen(ticket["chain_id"])
        self.assertEqual(restored["state"],"CONFORM_VERIFIED")
        self.assertTrue(restored["recovered_without_relaunch"])
        self.assertEqual(self.chain._row(ticket["chain_id"])["conform_job"],job)

    def test_worker_ticket_mismatch_never_promotes_import(self):
        ticket=self.stage()
        self.committed_edit()
        with patch.object(self.b13,"run_next",return_value={
            "job_id":"another_native_job","state":"SUCCEEDED"}):
            with self.assertRaisesRegex(RuntimeError,"ticket mismatch"):
                self.chain.run_import(ticket["chain_id"])
        self.assertEqual(self.chain._row(ticket["chain_id"])["state"],"IMPORT_QUEUED")

    def test_native_import_then_conform_receipts_and_reopen(self):
        ticket=self.stage()
        self.committed_edit()
        with patch.object(self.b13,"run_next",return_value={
            "job_id":self.import_job,"state":"SUCCEEDED"}):
            with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
                accepted=self.chain.run_import(ticket["chain_id"])
        self.assertEqual(accepted["state"],"IMPORT_VERIFIED")
        with patch.object(self.b13,"verify_completed",return_value=self.imported_proof()):
            with patch.object(self.b14,"stage_and_approve",
                return_value={"job_id":self.conform_job,"state":"QUEUED"}):
                self.chain.stage_conform(ticket["chain_id"],object())
            self.capture.index.register_revision(
                self.pid,"conformed_cut_v1","presentation",{
                    "format":"nvp.presentation.b14.edited_technical_mov_candidate.v1",
                    "picture_locked":False,"final_master":False
                },dependencies=[])
            verified={"status":"VERIFIED_SDR16_PICTURE_CONFORM","frames":24}
            with patch.object(self.b14,"run_next",return_value={
                "job_id":self.conform_job,"state":"SUCCEEDED"}):
                with patch.object(self.b14,"verify_completed",return_value=verified):
                    result=self.chain.run_conform(ticket["chain_id"])
            self.assertEqual(result["state"],"CONFORM_VERIFIED")
            self.assertFalse(result["final_master"])
            with patch.object(self.b14,"verify_completed",return_value=verified):
                reopened=self.chain.reopen(ticket["chain_id"])
            self.assertTrue(reopened["recovered_without_relaunch"])
            self.assertEqual(reopened["state"],"CONFORM_VERIFIED")

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
