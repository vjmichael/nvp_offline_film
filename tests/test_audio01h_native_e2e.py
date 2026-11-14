"""Native AUDIO-01H acceptance: real indexed multistem WAV -> contained mix -> approval.

This test exercises the actual TaskLedger/OS worker (Windows Job Object or
Linux process-group supervisor) and actual FFmpeg EBU R128 measurement.
Upstream AUDIO-01D chunk synthesis is independently gated elsewhere.
"""
from __future__ import annotations
import hashlib
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import wave

from backend.nvp_audio01e_wav_publication import FORMAT as AUDIO_FORMAT
from backend.nvp_audio01h_native_host import NativeAudio01HHost
from backend.nvp_audio01h_loudness import analyze_wav
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def write_wav(path, values):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(48000)
        writer.writeframes(b"".join(struct.pack("<hh", x, x) for x in values))


def make_source(root):
    cap = DigitalCapture(Studio(root / "studio.sqlite3"))
    pid = cap.studio.create_project("NVP AUDIO-01H native acceptance",
                                    "Real multistem mixer")["id"]
    n = 48000
    dialogue = [int(4200 * math.sin(2 * math.pi * 223 * i / 48000)) for i in range(n)]
    music = [int(1600 * math.sin(2 * math.pi * 449 * i / 48000)) for i in range(n)]
    combined = [a+b for a,b in zip(dialogue,music)]
    named = [("dialogue","stem_dialogue.wav",dialogue),
             ("music","stem_music.wav",music),
             (None,"mix_preview.wav",combined)]
    rows = []
    for stem_id, name, values in named:
        path = root / name
        write_wav(path, values)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        cap.index.put_media_file(pid,path,"audio/wav")
        rows.append({"stem_id": stem_id, "filename": name,
                     "sha256": digest, "samples_per_channel": n,
                     "kind": "composite" if stem_id is None else "stem"})
    cap.index.register_revision(
        pid, "originalaudio", "audio",
        {"format": AUDIO_FORMAT, "status": "unapproved_audio_only_pcm16_stems",
         "project_id": pid, "wav_outputs": rows,
         "total_samples_per_channel": n, "sample_rate":48000,
         "channels":2,"sample_width":2,
         "picture_bound":False,"picture_locked":False,
         "director_approved":False,"final_mix":False,"final_master":False},
        expected_revision=0,dependencies=[])
    return cap,pid


class NativeAudio01HEndToEnd(unittest.TestCase):
    def test_multistem_composite_through_contained_worker_to_creator_final_mix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cap, pid = make_source(root)
            pristine = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.glob("*.wav")}
            ledger = TaskLedger(root / "ledger", sampler=lambda:ResourceSnapshot(
                0,16000,12000,0,tuple()))
            creator_events = {"automate_mix","accept_mix","revoke_mix"}
            host = NativeAudio01HHost(cap,ledger,root/"native",
                verify_creator_action=lambda event,scope: event in creator_events,
                strict_linux_tree=False)
            queued = host.stage(pid,"originalaudio",root,root/"processed.wav",
                                "automatedmix",[[0,-3],[47999,-3]],
                                "automate_mix",stem_id=None,ram_mb=1024)
            self.assertEqual(queued["state"],"QUEUED")
            result=host.run_next(timeout_seconds=120)
            self.assertEqual(result["state"],"SUCCEEDED")
            self.assertEqual(ledger.get_task(queued["job_id"])["reserved"],0)
            self.assertEqual(host._grant(queued["job_id"])["stopped"],1)
            reopened=NativeAudio01HHost(
                DigitalCapture(Studio(root/"studio.sqlite3")),
                TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
                    0,16000,12000,0,tuple())),root/"native",
                verify_creator_action=lambda *_:False,strict_linux_tree=False)
            recovered=reopened.recover_completed(queued["job_id"])
            self.assertEqual(recovered["state"],"SUCCEEDED")
            self.assertFalse(recovered["rerendered"])
            for name,sha in pristine.items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),sha)
            out=cap.index.read_revision(pid,"automatedmix",1)
            self.assertEqual(out["data"]["source_stem_id"],None)
            self.assertFalse(out["data"]["final_mix"])
            self.assertFalse(out["data"]["director_approved"])
            measured=analyze_wav(root/"processed.wav",expected_samples=48000)
            with self.assertRaises(PermissionError):
                host.creator_decision(pid,"automatedmix","mixdecision",measured,
                    decision="ACCEPT",creator_event="unrecognized")
            accepted=host.creator_decision(pid,"automatedmix","mixdecision",measured,
                decision="ACCEPT",creator_event="accept_mix")
            self.assertEqual(accepted["status"],"CREATOR_REVIEW_ACCEPT")
            self.assertTrue(accepted["final_mix"])
            self.assertFalse(accepted["final_master"])
            with self.assertRaises(PermissionError):
                host.creator_decision(pid,"automatedmix","mixdecision",measured,
                    decision="REVOKE",creator_event="accept_mix")
            revoked=host.creator_decision(pid,"automatedmix","mixdecision",measured,
                decision="REVOKE",creator_event="revoke_mix")
            self.assertFalse(revoked["final_mix"])
            self.assertEqual(cap.index.history(pid,"mixdecision")[0]["revision"],1)
            self.assertEqual(cap.index.history(pid,"mixdecision")[1]["revision"],2)

    def test_missing_worker_stop_witness_refuses_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid=make_source(root)
            ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
                0,16000,12000,0,tuple()))
            host=NativeAudio01HHost(cap,ledger,root/"native",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            queued=host.stage(pid,"originalaudio",root,root/"pending.wav",
                              "pendingmix",[[0,0],[47999,0]],"approve_stage")
            with self.assertRaises(PermissionError):
                host.recover_completed(queued["job_id"])
            self.assertEqual(ledger.get_task(queued["job_id"])["state"],"QUEUED")
            self.assertFalse((root/"pending.wav").exists())

    def test_direct_uncontained_filmindex_audio_cannot_be_final_approved(self):
        from backend.nvp_audio01h_stem_revision import automate_stem
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid=make_source(root)
            result=automate_stem(cap,pid,"originalaudio",None,
                [[0,0],[47999,0]],root,root/"orphan.wav",
                "uncontainedmix",authorize=lambda _:True)
            self.assertEqual(result["status"],"UNAPPROVED_AUTOMATED_STEM")
            ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
                0,16000,12000,0,tuple()))
            host=NativeAudio01HHost(cap,ledger,root/"native",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            evidence=analyze_wav(root/"orphan.wav",expected_samples=48000)
            with self.assertRaises(PermissionError):
                host.creator_decision(pid,"uncontainedmix","decision",
                    evidence,decision="ACCEPT",creator_event="real_human_event")
            with self.assertRaises(KeyError):
                cap.index.read_revision(pid,"decision")

    def test_denied_automation_cannot_enqueue_or_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cap,pid=make_source(root)
            ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
                0,16000,12000,0,tuple()))
            host=NativeAudio01HHost(cap,ledger,root/"native",
                verify_creator_action=lambda *_:False,strict_linux_tree=False)
            with self.assertRaises(PermissionError):
                host.stage(pid,"originalaudio",root,root/"out.wav",
                           "automatedmix",[[0,0],[47999,0]],"forged")
            self.assertFalse((root/"out.wav").exists())
            with self.assertRaises(KeyError):
                cap.index.read_revision(pid,"automatedmix")


if __name__ == "__main__":
    unittest.main()
