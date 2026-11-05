"""E2E-01C finishing coordinator: actual SQLite custody / host-policy contracts.

Existing native host implementations are instantiated, with external
mastering/encoder operations patched at their trusted boundaries.
These tests are NOT film-level native mastering or GUI acceptance.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_studio import Studio
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_audio01j_native_host import NativeAudio01JHost
from backend.nvp_audio01k_native_host import NativeAudio01KHost
from backend.nvp_e2e01c_finishing import NativeFinishingHandoff


class NativeFinishingContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.studio=Studio(self.root/"film.sqlite3")
        self.pid=self.studio.create_project("NVP E2E 01C alpha fixture","")["id"]
        self.capture=DigitalCapture(self.studio)
        self.ledger=TaskLedger(
            self.root/"ledger",sampler=lambda:ResourceSnapshot(
                1,32768,25000,0,()))
        creator=lambda *_:True
        self.audio=NativeAudio01IHost(
            self.capture,self.ledger,self.root/"audio",
            verify_creator_action=creator,strict_linux_tree=False)
        self.av=NativeAudio01JHost(
            self.capture,self.ledger,self.root/"av",
            verify_creator_action=creator,audio_host=self.audio,
            strict_linux_tree=False)
        self.distribution=NativeAudio01KHost(
            self.capture,self.ledger,av_host=self.av,
            verify_creator_action=creator)
        self.chain=NativeFinishingHandoff(
            self.capture,self.ledger,self.audio,self.av,self.distribution)
        self.lock=self.capture.index.register_revision(
            self.pid,"picture_lock","presentation",{
                "format":"fixture.lock","picture_locked":True,
                "director_approved":True,"final_master":False})
        self.audio_rec=self.capture.index.register_revision(
            self.pid,"audio_delivery","audio",{
                "format":"fixture.approved_audio","director_approved":True})
        self.movie_dir=self.root/"picture"
        self.movie_dir.mkdir()
        self.audio_dir=self.root/"audio_delivery_dir"
        self.audio_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_lock(self,cap,pid,lock_id):
        if pid!=self.pid or lock_id!="picture_lock":
            raise PermissionError("Not the approved picture")
        return (self.capture.index.read_revision(pid,"picture_lock",1),None)

    def _register(self):
        return self.chain.register(
            self.pid,"picture_lock","audio_delivery",
            movie_dir=self.movie_dir,audio_dir=self.audio_dir,
            final_dir=self.root/"approved_film",
            export_id="approved_movie",distribution_id="distribution",
            distribution_dir=self.root/"mezzanine")

    def _verified_av(self):
        self.capture.index.register_revision(
            self.pid,"approved_movie","master",{
                "format":"nvp.audio01j.final_av_master.v1",
                "final_master":True,"dcp_delivered":False,
                "picture_lock_id":"picture_lock",
                "audio_delivery_id":"audio_delivery"})

    def _verified_distribution(self):
        return self.capture.index.register_revision(
            self.pid,"distribution","master",{
                "format":"nvp.audio01k.distribution_package.v1",
                "export_id":"approved_movie","dcp_delivered":False})

    def _stage_av(self):
        with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
                   side_effect=self._fake_lock),patch.object(
                   self.audio,"verify_delivery",return_value={"status":"VERIFIED"}),patch.object(
                   self.av,"stage",return_value={
                        "job_id":"avjob_unit","state":"QUEUED","export_id":"approved_movie"}):
            self._register()
            return self.chain.stage_final_av(self.pid,"approved_movie","creator-event")

    def test_registration_rejects_duplicate_identity_and_reopens(self):
        with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
                   side_effect=self._fake_lock),patch.object(
                   self.audio,"verify_delivery",return_value={"status":"VERIFIED"}):
            result=self._register()
            self.assertEqual(result["state"],"APPROVALS_VERIFIED")
            with self.assertRaises(Exception):
                self._register()
        self.assertEqual(self.chain._row(self.pid,"approved_movie")["state"],
                         "APPROVALS_VERIFIED")
        restarted=NativeFinishingHandoff(
            self.capture,self.ledger,self.audio,self.av,self.distribution)
        self.assertEqual(restarted._row(self.pid,"approved_movie")["lock_sha"],
                         self.lock["document_sha256"])

    def test_staging_is_write_ahead_and_cannot_duplicate_after_crash(self):
        with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
                   side_effect=self._fake_lock),patch.object(
                   self.audio,"verify_delivery",return_value={"status":"VERIFIED"}):
            self._register()
            with patch.object(self.av,"stage",side_effect=RuntimeError("native crash")):
                with self.assertRaisesRegex(RuntimeError,"native crash"):
                    self.chain.stage_final_av(self.pid,"approved_movie","creator")
            self.assertEqual(self.chain._row(self.pid,"approved_movie")["state"],
                             "AV_STAGING_UNCERTAIN")
            self.assertTrue(self.chain.reopen(
                self.pid,"approved_movie")["requires_native_reconciliation"])
            with patch.object(self.av,"stage") as duplicated:
                with self.assertRaises(RuntimeError):
                    self.chain.stage_final_av(self.pid,"approved_movie","creator")
                duplicated.assert_not_called()

    def test_cannot_publish_when_worker_did_not_finish(self):
        self._stage_av()
        with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
                   side_effect=self._fake_lock),patch.object(
                   self.audio,"verify_delivery",return_value={"status":"VERIFIED"}),patch.object(
                   self.ledger,"get_task",return_value={
                       "state":"ACTIVE","reserved":1}):
            with patch.object(self.distribution,"publish") as emitted:
                with self.assertRaisesRegex(RuntimeError,"not stopped"):
                    self.chain.publish_mezzanine(
                        self.pid,"approved_movie","creator")
                emitted.assert_not_called()
        self.assertEqual(self.chain._row(self.pid,"approved_movie")["state"],
                         "AV_QUEUED")

    def test_verified_film_to_mezzanine_and_restart_no_dcp_claim(self):
        self._stage_av()
        self._verified_av()
        with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
                   side_effect=self._fake_lock),patch.object(
                   self.audio,"verify_delivery",return_value={"status":"VERIFIED"}),patch.object(
                   self.ledger,"get_task",return_value={
                       "state":"SUCCEEDED","reserved":0}),patch.object(
                   self.av,"verify_published",return_value={
                       "status":"VERIFIED_FINAL_AV_MASTER"}),patch.object(
                   self.distribution,"verify",return_value={
                       "status":"VERIFIED_MEZZANINE_DISTRIBUTION"}):
            proof=self.chain.verify_final_av(self.pid,"approved_movie")
            self.assertEqual(proof["state"],"AV_VERIFIED")
            with patch.object(self.distribution,"publish",side_effect=lambda *_a,**_k:
                              self._verified_distribution()):
                result=self.chain.publish_mezzanine(
                    self.pid,"approved_movie","creator")
            self.assertEqual(result["state"],"DISTRIBUTION_VERIFIED")
            self.assertFalse(result["dcp_delivered"])
            recovered=self.chain.reopen(self.pid,"approved_movie")
            self.assertEqual(recovered["state"],"DISTRIBUTION_VERIFIED")
            self.assertTrue(recovered["recovered_without_rerender"])

    def test_unverified_distribution_after_crash_stays_uncertain(self):
        self._stage_av()
        self._verified_av()
        with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
                   side_effect=self._fake_lock),patch.object(
                   self.audio,"verify_delivery",return_value={"status":"VERIFIED"}),patch.object(
                   self.ledger,"get_task",return_value={
                       "state":"SUCCEEDED","reserved":0}),patch.object(
                   self.av,"verify_published",return_value={
                       "status":"VERIFIED_FINAL_AV_MASTER"}):
            self.chain.verify_final_av(self.pid,"approved_movie")
            with patch.object(self.distribution,"publish",
                              side_effect=RuntimeError("after creator event")):
                with self.assertRaisesRegex(RuntimeError,"creator event"):
                    self.chain.publish_mezzanine(self.pid,"approved_movie","event")
            with patch.object(self.distribution,"verify",
                              side_effect=PermissionError("no publication witness")):
                proof=self.chain.reopen(self.pid,"approved_movie")
            self.assertEqual(proof["state"],"DISTRIBUTION_UNCERTAIN")
            self.assertTrue(proof["requires_native_reconciliation"])
            with patch.object(self.distribution,"publish") as duplicate:
                with self.assertRaises(RuntimeError):
                    self.chain.publish_mezzanine(self.pid,"approved_movie","event")
                duplicate.assert_not_called()


if __name__=="__main__":
    unittest.main()
