"""AUDIO-01I actual native mastering worker abrupt-exit quarantine tests."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from test_audio01i_native_master_delivery import setup_approved,ledger

REPO=Path(__file__).resolve().parents[1]
POINTS=("candidate_filmindex_registered","candidate_receipt_fsynced")


def host(root):
    return NativeAudio01IHost(DigitalCapture(Studio(root/"studio.sqlite3")),
        ledger(root),root/"audioi",
        verify_creator_action=lambda *_:True,strict_linux_tree=False)


def child(root,point):
    pid=(root/"pid.txt").read_text()
    h=host(root)
    q=h.stage(pid,"mixdecision",1,"candidate","archive_pcm24_v1",
              root/"candidate.wav","creator_worker_exit")
    (root/"job.txt").write_text(q["job_id"])
    try:
        h.run_next(timeout_seconds=180)
    except RuntimeError as error:
        if '96' not in str(error):
            raise
        return
    raise RuntimeError("Worker crash injection did not stop native host")


class MasteringWorkerCrashMatrix(unittest.TestCase):
    def test_worker_exits_never_mint_a_deliverable(self):
        for point in POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                cap,pid,_=setup_approved(root)
                (root/"pid.txt").write_text(pid)
                env=dict(os.environ)
                env["PYTHONPATH"]=str(REPO)+os.pathsep+str(REPO/"tests")
                env["NVP_AUDIO01I_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01I_CRASH_AFTER"]=point
                completed=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),"--child",
                     str(root),point],cwd=REPO,env=env,
                    capture_output=True,timeout=210)
                self.assertEqual(completed.returncode,0,
                    completed.stderr.decode("utf8","replace")[-2000:])
                reopened=host(root)
                job=(root/"job.txt").read_text()
                task=reopened.ledger.get_task(job)
                grant=reopened._grant(job)
                self.assertEqual(task["state"],"ACTIVE")
                self.assertEqual(task["reserved"],1)
                self.assertEqual(grant["stopped"],0)
                with self.assertRaises(PermissionError):
                    reopened.recover_candidate(job)
                with self.assertRaises(PermissionError):
                    reopened.deliver(pid,"candidate","delivery",root/"delivery",
                        "unjustified_final_delivery")
                with self.assertRaises(KeyError):
                    reopened.capture.index.read_revision(pid,"delivery")


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
