"""AUDIO-01I real process-exit matrix for final audio publication.

Every child dies through os._exit; no Python exception cleanup can make a
partially promoted directory appear to have completed the SQLite revision.
"""
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

ROOT=Path(__file__).resolve().parents[1]
DELIVERY_POINTS=(
    "delivery_event_reserved","delivery_stage_created",
    "delivery_wav_fsynced","delivery_manifest_fsynced",
    "delivery_directory_promoted","delivery_filmindex_registered",
    "delivery_event_finalized",
)


def host(root):
    return NativeAudio01IHost(
        DigitalCapture(Studio(root/"studio.sqlite3")),
        ledger(root),root/"audioi",
        verify_creator_action=lambda *_:True,strict_linux_tree=False)


def child(root,point):
    pid=(root/"pid.txt").read_text()
    h=host(root)
    h.deliver(pid,"candidate","delivery",root/"delivered",
              "creator_delivery_nonce")
    raise AssertionError("Expected actual AUDIO-01I delivery crash")


class Audio01IDeliveryCrashMatrix(unittest.TestCase):
    def test_abrupt_publication_checks_reopened_filmindex(self):
        for point in DELIVERY_POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                cap,pid,_=setup_approved(root)
                (root/"pid.txt").write_text(pid)
                h=host(root)
                queued=h.stage(pid,"mixdecision",1,"candidate",
                    "archive_pcm24_v1",root/"candidate.wav",
                    "creator_candidate_nonce")
                self.assertEqual(h.run_next(timeout_seconds=180)["state"],"SUCCEEDED")
                env=dict(os.environ)
                env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(ROOT/"tests")
                env["NVP_AUDIO01I_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01I_CRASH_AFTER"]=point
                completed=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "--child",str(root),point],
                    cwd=ROOT,env=env,capture_output=True,timeout=180)
                self.assertEqual(completed.returncode,EXIT_CODE,
                    completed.stderr.decode("utf8","replace")[-1800:])
                reopened=host(root)
                stage=root/".delivered.audio01i.stage"
                output=root/"delivered"
                registered=point in ("delivery_filmindex_registered",
                                      "delivery_event_finalized")
                promoted=point in ("delivery_directory_promoted",*(
                    "delivery_filmindex_registered","delivery_event_finalized"))
                if promoted:
                    self.assertTrue(output.is_dir())
                    self.assertFalse(stage.exists())
                elif point=="delivery_event_reserved":
                    self.assertFalse(output.exists())
                    self.assertFalse(stage.exists())
                else:
                    self.assertFalse(output.exists())
                    self.assertTrue(stage.is_dir())
                if registered:
                    result=reopened.verify_delivery(pid,"delivery",output)
                    self.assertEqual(result["status"],"VERIFIED_FINAL_AUDIO")
                else:
                    with self.assertRaises(KeyError):
                        reopened.capture.index.read_revision(pid,"delivery")
                # A consumed creator action may not approve a different
                # delivery, even if its first publication was interrupted.
                with self.assertRaises(PermissionError):
                    reopened.deliver(pid,"candidate","anotherdelivery",
                        root/"another_output","creator_delivery_nonce")


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
