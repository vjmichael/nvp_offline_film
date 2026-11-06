"""AUDIO-01I host abrupt-exit boundaries: reservation and no-rerender checks."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_audio01i_fault_matrix import EXIT_CODE
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from test_audio01i_native_master_delivery import setup_approved,ledger

REPO=Path(__file__).resolve().parents[1]
HOST_POINTS=(
    "master_event_reserved","master_grant_committed","master_queued",
    "master_claimed","master_worker_reaped",
    "master_stop_witness_committed","master_result_committed",
    "master_ledger_finished",
)


def host(root):
    return NativeAudio01IHost(DigitalCapture(Studio(root/"studio.sqlite3")),
        ledger(root),root/"audioi",
        verify_creator_action=lambda *_:True,strict_linux_tree=False)


def child(root,point):
    pid=(root/"pid.txt").read_text()
    h=host(root)
    q=h.stage(pid,"mixdecision",1,"candidate",
              "archive_pcm24_v1",root/"candidate.wav",
              "creator_candidate_crash")
    (root/"job.txt").write_text(q["job_id"])
    h.run_next(timeout_seconds=180)
    raise AssertionError("Expected native master host crash")


class MasteringHostCrashMatrix(unittest.TestCase):
    def test_all_host_commit_edges_fail_closed_and_recover_only_stopped(self):
        for point in HOST_POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                _,pid,_=setup_approved(root)
                (root/"pid.txt").write_text(pid)
                env=dict(os.environ)
                env["PYTHONPATH"]=str(REPO)+os.pathsep+str(REPO/"tests")
                env["NVP_AUDIO01I_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01I_CRASH_AFTER"]=point
                process=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "--child",str(root),point],env=env,cwd=REPO,
                    capture_output=True,timeout=210)
                self.assertEqual(process.returncode,EXIT_CODE,
                    process.stderr.decode("utf8","replace")[-2000:])
                h=host(root)
                with self.assertRaises(KeyError):
                    h.capture.index.read_revision(pid,"delivery")
                if point in ("master_event_reserved","master_grant_committed"):
                    self.assertFalse((root/"job.txt").exists())
                    continue
                if point=="master_queued":
                    # The queue commit succeeds before stage() can return
                    # its job ID to the caller. Recover identity from SQLite.
                    with h.ledger._db() as db:
                        row=db.execute("SELECT id FROM tasks WHERE id LIKE 'masterjob%'").fetchone()
                    self.assertIsNotNone(row)
                    job=row[0]
                else:
                    job=(root/"job.txt").read_text()
                task=h.ledger.get_task(job)
                if point=="master_queued":
                    self.assertEqual(task["state"],"QUEUED")
                    with self.assertRaises(PermissionError):
                        h.recover_candidate(job)
                    continue
                if point in ("master_claimed","master_worker_reaped"):
                    self.assertEqual((task["state"],task["reserved"]),("ACTIVE",1))
                    with self.assertRaises(PermissionError):
                        h.recover_candidate(job)
                    continue
                if point in ("master_stop_witness_committed",
                             "master_result_committed"):
                    self.assertEqual((task["state"],task["reserved"]),("ACTIVE",1))
                else:
                    self.assertEqual((task["state"],task["reserved"]),("SUCCEEDED",0))
                reconciled=h.recover_candidate(job)
                self.assertEqual(reconciled["state"],"SUCCEEDED")
                self.assertFalse(reconciled["rerendered"])
                rec=h.capture.index.read_revision(pid,"candidate",1)
                self.assertFalse(rec["data"]["final_master"])


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
