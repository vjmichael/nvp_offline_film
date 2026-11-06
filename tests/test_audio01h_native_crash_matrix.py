"""AUDIO-01H real subprocess crash matrix, with no exception-based simulation.

The parent process reopens the actual SQLite/FilmIndex state after each
child abruptly exits; a stopped witness alone never approves a mix.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_audio01h_fault_matrix import EXIT_CODE
from backend.nvp_audio01h_native_host import NativeAudio01HHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from test_audio01h_native_e2e import make_source

REPO=Path(__file__).resolve().parents[1]
PRE_WORKER=("plan_fsynced","grant_committed","queued_committed",
            "claimed_active")
POST_WORKER=("worker_handle_reaped","stopped_witness_committed",
             "output_independently_verified","ledger_succeeded",
             "grant_result_committed")
HOST_POINTS=PRE_WORKER+POST_WORKER


def ledger(root):
    return TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        0,16000,12000,0,tuple()))


def child(root,point):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    pid=(root/"project.txt").read_text()
    host=NativeAudio01HHost(cap,ledger(root),root/"native",
        verify_creator_action=lambda *_:True,strict_linux_tree=False)
    queued=host.stage(pid,"originalaudio",root,root/"automated.wav",
                      "automatedmix",[[0,0],[47999,0]],
                      "creator_crash_test",stem_id=None)
    (root/"job.txt").write_text(queued["job_id"])
    host.run_next(timeout_seconds=120)
    raise RuntimeError("Fault gate was not executed")


class NativeAbruptHostCrashMatrix(unittest.TestCase):
    def test_exact_abrupt_host_crashes_never_approve_and_keep_custody(self):
        for point in HOST_POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                cap,pid=make_source(root)
                (root/"project.txt").write_text(pid)
                env=dict(os.environ)
                env["PYTHONPATH"]=str(REPO)+os.pathsep+str(REPO/"tests")
                env["NVP_AUDIO01H_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01H_CRASH_AFTER"]=point
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                    "--child",str(root),point],env=env,cwd=REPO,
                    capture_output=True,timeout=180)
                self.assertEqual(result.returncode,EXIT_CODE,
                                 result.stderr.decode("utf8","replace")[-2000:])
                reopened=NativeAudio01HHost(
                    DigitalCapture(Studio(root/"studio.sqlite3")),
                    ledger(root),root/"native",
                    verify_creator_action=lambda *_:False,strict_linux_tree=False)
                with self.assertRaises(KeyError):
                    reopened.capture.index.read_revision(pid,"mixdecision")
                if point in ("plan_fsynced","grant_committed"):
                    self.assertFalse((root/"job.txt").exists())
                    continue
                job=(root/"job.txt").read_text()
                task=reopened.ledger.get_task(job)
                if point=="queued_committed":
                    self.assertEqual(task["state"],"QUEUED")
                    with self.assertRaises(PermissionError):
                        reopened.recover_completed(job)
                    continue
                if point in ("claimed_active","worker_handle_reaped"):
                    self.assertEqual(task["state"],"ACTIVE")
                    self.assertEqual(task["reserved"],1)
                    with self.assertRaises(PermissionError):
                        reopened.recover_completed(job)
                    continue
                if point in ("stopped_witness_committed","output_independently_verified"):
                    self.assertEqual(task["state"],"ACTIVE")
                    self.assertEqual(task["reserved"],1)
                else:
                    self.assertEqual(task["state"],"SUCCEEDED")
                    self.assertEqual(task["reserved"],0)
                checked=reopened.recover_completed(job)
                self.assertEqual(checked["state"],"SUCCEEDED")
                self.assertFalse(checked["rerendered"])
                record=reopened.capture.index.read_revision(pid,"automatedmix",1)
                self.assertFalse(record["data"]["director_approved"])
                self.assertFalse(record["data"]["final_master"])


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
