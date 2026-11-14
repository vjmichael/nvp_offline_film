"""AUDIO-01I actual OS-worker mastering and final PCM24 delivery acceptance.

Real 2-stem AUDIO-01E compatible fixture -> AUDIO-01H contained automation ->
native explicit mix ACCEPT -> AUDIO-01I contained master -> second creator
authorization -> immutable final delivery -> independent restart verification.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.nvp_audio01h_native_host import NativeAudio01HHost
from backend.nvp_audio01h_loudness import analyze_wav
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from test_audio01h_native_e2e import make_source


def ledger(root):
    return TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        0,16000,12000,0,tuple()))


def setup_approved(root):
    cap,pid=make_source(root)
    h=NativeAudio01HHost(cap,ledger(root),root/"audioh",
        verify_creator_action=lambda *_:True,strict_linux_tree=False)
    q=h.stage(pid,"originalaudio",root,root/"processed.wav",
        "automatedmix",[[0,-3],[47999,-3]],"creator_mix_render")
    if h.run_next(timeout_seconds=120)["state"]!="SUCCEEDED":
        raise RuntimeError("Native mix production was not completed")
    evidence=analyze_wav(root/"processed.wav",expected_samples=48000)
    accepted=h.creator_decision(pid,"automatedmix","mixdecision",evidence,
        decision="ACCEPT",creator_event="real_creator_mix_accept")
    if accepted["revision"]!=1:raise RuntimeError("Mix approval not first revision")
    return cap,pid,h


class Audio01IEndToEnd(unittest.TestCase):
    def test_archival_pcm24_through_native_host_to_second_approved_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid,h=setup_approved(root)
            original={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.glob("*.wav")}
            host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            queued=host.stage(pid,"mixdecision",1,"mastercandidate",
                "archive_pcm24_v1",root/"master_candidate.wav","creator_master_candidate")
            self.assertEqual(queued["state"],"QUEUED")
            result=host.run_next(timeout_seconds=180)
            self.assertEqual(result["state"],"SUCCEEDED")
            self.assertFalse(result["final_master"])
            task=host.ledger.get_task(queued["job_id"])
            self.assertEqual((task["state"],task["reserved"]),("SUCCEEDED",0))
            candidate=cap.index.read_revision(pid,"mastercandidate",1)
            self.assertEqual(candidate["data"]["analysis"]["bit_depth"],24)
            self.assertFalse(candidate["data"]["final_master"])
            with self.assertRaises(PermissionError):
                hostile=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                    verify_creator_action=lambda *_:False,strict_linux_tree=False)
                hostile.deliver(pid,"mastercandidate","delivery",root/"delivery",
                    "unauthorized")
            self.assertFalse((root/"delivery").exists())
            delivery=host.deliver(pid,"mastercandidate","delivery",
                root/"delivery","real_creator_master_publish")
            self.assertEqual(delivery["status"],"CREATOR_APPROVED_FINAL_AUDIO")
            self.assertTrue(delivery["final_master"])
            self.assertFalse(delivery["video_master"])
            self.assertTrue((root/"delivery"/"master.wav").is_file())
            self.assertEqual((root/"delivery"/"master.wav").read_bytes(),
                             (root/"master_candidate.wav").read_bytes())
            reopened=NativeAudio01IHost(
                DigitalCapture(Studio(root/"studio.sqlite3")),ledger(root),
                root/"audioi",verify_creator_action=lambda *_:False,
                strict_linux_tree=False)
            verified=reopened.verify_delivery(pid,"delivery",root/"delivery")
            self.assertEqual(verified["status"],"VERIFIED_FINAL_AUDIO")
            for name,sha in original.items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),sha)
            with self.assertRaises(RuntimeError):
                host.deliver(pid,"mastercandidate","anotherdelivery",root/"delivery",
                    "a_different_creator_event")
            with self.assertRaises(PermissionError):
                host.deliver(pid,"mastercandidate","nonce_reuse",root/"reused",
                    "real_creator_master_publish")
            self.assertFalse((root/"reused").exists())
            with (root/"delivery"/"master.wav").open("ab") as altered:
                altered.write(b"bad")
            with self.assertRaises(RuntimeError):
                reopened.verify_delivery(pid,"delivery",root/"delivery")

    def test_revoked_mix_disallows_any_new_mastering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid,h=setup_approved(root)
            evidence=analyze_wav(root/"processed.wav",expected_samples=48000)
            h.creator_decision(pid,"automatedmix","mixdecision",evidence,
                decision="REVOKE",creator_event="real_human_revoke")
            host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            with self.assertRaises(PermissionError):
                host.stage(pid,"mixdecision",1,"candidate","archive_pcm24_v1",
                    root/"blocked.wav","creator_after_revoke")
            self.assertFalse((root/"blocked.wav").exists())

    def test_streaming_profile_is_independently_measured_not_assumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid,_=setup_approved(root)
            host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            queued=host.stage(pid,"mixdecision",1,"streamcandidate",
                "streaming_pcm24_v1",root/"stream_candidate.wav",
                "creator_streaming_candidate")
            result=host.run_next(timeout_seconds=180)
            self.assertEqual(result["state"],"SUCCEEDED")
            candidate=cap.index.read_revision(pid,"streamcandidate",1)
            self.assertEqual(candidate["data"]["analysis"]["bit_depth"],24)
            self.assertLessEqual(
                candidate["data"]["analysis"]["true_peak_dbtp"],-1.4)
            self.assertFalse(candidate["data"]["final_master"])
            self.assertFalse(candidate["data"]["master_approved"])
            recovered=host.recover_candidate(queued["job_id"])
            self.assertEqual(recovered["state"],"SUCCEEDED")
            self.assertFalse(recovered["rerendered"])

    def test_changed_candidate_does_not_become_final_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid,_=setup_approved(root)
            host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            queued=host.stage(pid,"mixdecision",1,"candidate",
                "archive_pcm24_v1",root/"candidate.wav","make_candidate")
            host.run_next(timeout_seconds=180)
            with (root/"candidate.wav").open("ab") as stream:
                stream.write(b"tamper")
            # Even with a matching content-addressed FilmIndex blob, the
            # trusted native candidate must remain bound to the original
            # worker destination and its immutable receipt.
            with self.assertRaises(RuntimeError):
                host.recover_candidate(queued["job_id"])
            with self.assertRaises(RuntimeError):
                host.deliver(pid,"candidate","tampered_delivery",
                             root/"tampered_delivery","creator_publish_tampered")
            self.assertFalse((root/"tampered_delivery").exists())

    def test_unknown_profile_rejected_prelaunch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid=make_source(root)
            host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            with self.assertRaises(ValueError):
                host.stage(pid,"mixdecision",1,"candidate","arbitrary_loudnorm",
                    root/"blocked.wav","claimed_creator")


if __name__=="__main__":
    unittest.main()
