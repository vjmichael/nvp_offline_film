"""AUDIO-01H approval crash replay matrix: actual os._exit after SQLite effects."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_audio01h_fault_matrix import EXIT_CODE
from backend.nvp_audio01h_native_host import NativeAudio01HHost
from backend.nvp_audio01h_loudness import analyze_wav
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from test_audio01h_native_e2e import make_source

REPO=Path(__file__).resolve().parents[1]
POINTS=("creator_event_reserved","creator_decision_registered","creator_event_completed")


def host(root):
    return NativeAudio01HHost(
        DigitalCapture(Studio(root/"studio.sqlite3")),
        TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
            0,16000,12000,0,tuple())),
        root/"native",verify_creator_action=lambda *_:True,strict_linux_tree=False)


def child(root, point):
    pid=(root/"project.txt").read_text()
    h=host(root)
    proof=analyze_wav(root/"automated.wav",expected_samples=48000)
    os.environ["NVP_AUDIO01H_FAULT_TEST"]="enabled"
    os.environ["NVP_AUDIO01H_CRASH_AFTER"]=point
    h.creator_decision(pid,"automatedmix","mixdecision",proof,
                       decision="ACCEPT",creator_event="human_event_nonce")
    raise RuntimeError("Creator crash gate not reached")


class CreatorDecisionCrashMatrix(unittest.TestCase):
    def test_every_creator_decision_boundary_is_durable_and_nonreplayable(self):
        for point in POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                cap,pid=make_source(root)
                (root/"project.txt").write_text(pid)
                first=host(root)
                queued=first.stage(pid,"originalaudio",root,root/"automated.wav",
                                   "automatedmix",[[0,0],[47999,0]],
                                   "automation_event_nonce")
                self.assertEqual(first.run_next(timeout_seconds=120)["state"],"SUCCEEDED")
                env=dict(os.environ)
                env["PYTHONPATH"]=str(REPO)+os.pathsep+str(REPO/"tests")
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                    "--child",str(root),point],env=env,cwd=REPO,
                    capture_output=True,timeout=200)
                self.assertEqual(result.returncode,EXIT_CODE,
                                 result.stderr.decode("utf8","replace")[-1800:])
                after=host(root)
                if point=="creator_event_reserved":
                    with self.assertRaises(KeyError):
                        after.capture.index.read_revision(pid,"mixdecision")
                else:
                    accepted=after.capture.index.read_revision(pid,"mixdecision",1)
                    self.assertEqual(accepted["data"]["decision"],"ACCEPT")
                    self.assertTrue(accepted["data"]["final_mix"])
                    self.assertFalse(accepted["data"]["final_master"])
                measured=analyze_wav(root/"automated.wav",expected_samples=48000)
                with self.assertRaises(PermissionError):
                    after.creator_decision(pid,"automatedmix","mixdecision",measured,
                        decision="ACCEPT",creator_event="human_event_nonce")


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
