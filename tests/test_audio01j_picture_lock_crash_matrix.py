"""AUDIO-01J genuine abrupt picture-lock approval crash windows."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01j_fault_matrix import EXIT_CODE
from backend.nvp_audio01j_native_host import NativeAudio01JHost
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from test_audio01h_native_e2e import make_source
from test_audio01i_native_master_delivery import ledger
from test_audio01j_native_final_av import source_picture

ROOT=Path(__file__).resolve().parents[1]
PICTURE_POINTS=("picture_event_reserved","picture_lock_indexed",
                "picture_event_completed")


def host(root):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    audio=NativeAudio01IHost(cap,ledger(root),root/"audioi",
            verify_creator_action=lambda *_:True,strict_linux_tree=False)
    return NativeAudio01JHost(cap,ledger(root),root/"avhost",
            verify_creator_action=lambda *_:True,audio_host=audio,
            strict_linux_tree=False)


def child(root,point):
    pid=(root/"project.txt").read_text()
    instance=host(root)
    with patch("backend.nvp_audio01j_picture_lock.verify_edited_technical_mov",
               return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE"}):
        instance.approve_picture(pid,"picture","picturelock",root,root,root,
                                 "creator_picture_lock_event")
    raise RuntimeError("Fault point failed to interrupt picture lock")


class PictureLockCrashMatrix(unittest.TestCase):
    def test_creator_picture_lock_receipt_survives_exact_crash_boundaries(self):
        for point in PICTURE_POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                cap,pid=make_source(root)
                source_picture(cap,pid,root)
                (root/"project.txt").write_text(pid)
                env=dict(os.environ)
                env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(ROOT/"tests")
                env["NVP_AUDIO01J_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01J_CRASH_AFTER"]=point
                completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                    "--child",str(root),point],cwd=ROOT,env=env,
                    capture_output=True,timeout=180)
                self.assertEqual(completed.returncode,EXIT_CODE,
                    completed.stderr.decode("utf8","replace")[-1500:])
                reopened=host(root)
                with reopened.ledger._db() as db:
                    row=db.execute("""SELECT revision FROM native_audio01j_creator_events
                        WHERE project_id=? AND operation='picture_lock'
                        AND object_id='picturelock'""",(pid,)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0],1 if point=="picture_event_completed" else -1)
                if point=="picture_event_reserved":
                    with self.assertRaises(KeyError):
                        reopened.capture.index.read_revision(pid,"picturelock")
                else:
                    picture=reopened.capture.index.read_revision(pid,"picturelock",1)
                    self.assertTrue(picture["data"]["picture_locked"])
                    self.assertFalse(picture["data"]["final_master"])
                with self.assertRaises(PermissionError):
                    with patch("backend.nvp_audio01j_picture_lock.verify_edited_technical_mov",
                               return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE"}):
                        reopened.approve_picture(
                            pid,"picture","differentlock",root,root,root,
                            "creator_picture_lock_event")


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
