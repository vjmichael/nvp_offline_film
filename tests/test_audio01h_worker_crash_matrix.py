"""AUDIO-01H contained worker abrupt-exit cases.

Worker exits with 94; host cannot misclassify a worker receipt or
FilmIndex media as a successful final mix or release uncertain custody.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_audio01h_native_host import NativeAudio01HHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from test_audio01h_native_e2e import make_source

REPO=Path(__file__).resolve().parents[1]
POINTS=("worker_output_registered","worker_receipt_fsynced")


def ledger(root):
    return TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        0,16000,12000,0,tuple()))


def child(root, point):
    pid=(root/"project.txt").read_text()
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    host=NativeAudio01HHost(cap,ledger(root),root/"native",
                            verify_creator_action=lambda *_:True,
                            strict_linux_tree=False)
    queued=host.stage(pid,"originalaudio",root,root/"automated.wav",
                      "automatedmix",[[0,0],[47999,0]],"creator_worker_test")
    (root/"job.txt").write_text(queued["job_id"])
    try:
        host.run_next(timeout_seconds=120)
    except RuntimeError:
        return
    raise AssertionError("Native worker should have exited at fault gate")


class WorkerCrashMatrix(unittest.TestCase):
    def test_abrupt_worker_exit_cannot_be_promoted_or_approved(self):
        for point in POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                cap,pid=make_source(root)
                (root/"project.txt").write_text(pid)
                env=dict(os.environ)
                env["PYTHONPATH"]=str(REPO)+os.pathsep+str(REPO/"tests")
                env["NVP_AUDIO01H_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01H_CRASH_AFTER"]=point
                completed=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "--child",str(root),point],cwd=REPO,env=env,
                    capture_output=True,timeout=160)
                self.assertEqual(completed.returncode,0,
                    completed.stderr.decode("utf8","replace")[-1600:])
                job=(root/"job.txt").read_text()
                restarted=NativeAudio01HHost(
                    DigitalCapture(Studio(root/"studio.sqlite3")),
                    ledger(root),root/"native",
                    verify_creator_action=lambda *_:True,
                    strict_linux_tree=False)
                state=restarted.ledger.get_task(job)
                self.assertEqual(state["state"],"ACTIVE")
                self.assertEqual(state["reserved"],1)
                self.assertEqual(restarted._grant(job)["stopped"],0)
                with self.assertRaises(PermissionError):
                    restarted.recover_completed(job)
                with self.assertRaises(PermissionError):
                    restarted.creator_decision(
                        pid,"automatedmix","mixdecision",{},
                        decision="ACCEPT",creator_event="creator_worker_test")
                with self.assertRaises(KeyError):
                    restarted.capture.index.read_revision(pid,"mixdecision")


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
