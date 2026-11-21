"""AUDIO-01K actual media integration: approved AV master -> mezzanine package.

Production picture-source reconstruction remains separately B14-gated. This
test generates real native ProRes and uses upstream B14 verifier substitution
only for the synthetic video fixture, as in the AUDIO-01J acceptance suite.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_audio01j_native_host import NativeAudio01JHost
from backend.nvp_audio01k_native_host import NativeAudio01KHost
from backend.nvp_audio01k_dcp_preflight import assess_dcp_readiness
from test_audio01i_native_master_delivery import setup_approved,ledger
from test_audio01j_native_final_av import source_picture


class FinalDistributionE2E(unittest.TestCase):
    def test_approved_av_into_exact_copy_and_dcp_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cap,pid,_=setup_approved(root)
            audio=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            queued=audio.stage(pid,"mixdecision",1,"mastercandidate",
                "archive_pcm24_v1",root/"candidate.wav","master_creation")
            self.assertEqual(audio.run_next(timeout_seconds=180)["state"],"SUCCEEDED")
            approved_audio=audio.deliver(pid,"mastercandidate","audiofinal",
                root/"approved_audio","final_audio_approval")
            self.assertTrue(approved_audio["final_master"])
            video=source_picture(cap,pid,root)
            source_sha=hashlib.sha256(video.read_bytes()).hexdigest()
            av=NativeAudio01JHost(cap,ledger(root),root/"avhost",
                verify_creator_action=lambda *_:True,audio_host=audio,
                strict_linux_tree=False)
            with patch("backend.nvp_audio01j_picture_lock.verify_edited_technical_mov",
                       return_value={
                           "status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE",
                           "frames":24,"movie_sha256":source_sha}):
                av.approve_picture(pid,"picture","picturelock",root,root,root,
                                   "picture_approval")
            av_job=av.stage(pid,"picturelock","audiofinal",root,
                 root/"approved_audio",root/"approved_av","avfinal",
                 "av_approval")
            self.assertEqual(av.run_next(timeout_seconds=240)["state"],"SUCCEEDED")
            final_mov=root/"approved_av"/"final_picture_sound.mov"
            before=hashlib.sha256(final_mov.read_bytes()).hexdigest()
            host=NativeAudio01KHost(cap,ledger(root),av_host=av,
                verify_creator_action=lambda *_:True)
            published=host.publish(pid,"avfinal","distribution",root/"approved_av",
                root,root/"approved_audio",root/"mezzanine","distribute_action")
            self.assertEqual(published["status"],"MEZZANINE_DISTRIBUTION_PUBLISHED")
            self.assertFalse(published["dcp_delivered"])
            self.assertEqual((root/"mezzanine"/"feature_master.mov").read_bytes(),
                             final_mov.read_bytes())
            proof=host.verify(pid,"distribution",root/"mezzanine",
                root/"approved_av",root,root/"approved_audio")
            self.assertEqual(proof["status"],"VERIFIED_MEZZANINE_DISTRIBUTION")
            self.assertEqual(hashlib.sha256(final_mov.read_bytes()).hexdigest(),before)
            record=cap.index.read_revision(pid,"distribution",1)
            dcp=assess_dcp_readiness(record["data"])
            self.assertEqual(dcp["status"],"NOT_READY")
            self.assertFalse(dcp["can_claim_dcp"])
            self.assertGreater(len(dcp["missing_capabilities"]),0)


if __name__=="__main__":
    unittest.main()
