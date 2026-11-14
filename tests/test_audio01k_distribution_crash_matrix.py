"""AUDIO-01K actual abrupt process exits at eight publication boundaries.

Real SQLite and FilmIndex, real on-disk bytes and fsync. The upstream native
AV approval is substituted by a clearly bounded proof stub; a separate
real-media integration test exercises NVP AUDIO-01J's contained output.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_audio01j_final_av import FORMAT as FINAL_AV_FORMAT
from backend.nvp_audio01k_fault_matrix import BOUNDARIES,EXIT_CODE
from backend.nvp_audio01k_native_host import NativeAudio01KHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger

ROOT=Path(__file__).resolve().parents[1]


class VerifiedUpstream:
    def verify_published(self,*args,**kwargs):
        return {"status":"VERIFIED_FINAL_AV_MASTER","final_master":True}


def host(root):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        0,16000,12000,0,tuple()))
    return NativeAudio01KHost(cap,ledger,av_host=VerifiedUpstream(),
        verify_creator_action=lambda *_:True)


def setup(root):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    pid=cap.studio.create_project("AUDIO-01K crash matrix",
                                  "Package custody only")["id"]
    (root/"project.txt").write_text(pid)
    audio=root/"finalav"
    audio.mkdir()
    raw=b"native-fs-transaction-test-media"*1000
    (audio/"final_picture_sound.mov").write_bytes(raw)
    sha=hashlib.sha256(raw).hexdigest()
    cap.index.register_revision(pid,"masterav","master",
        {"format":FINAL_AV_FORMAT,"frames":24,
         "rendered_mov_sha256":sha,"final_master":True,
         "director_approved":True,"dcp_delivered":False},
        expected_revision=0,dependencies=[])
    return pid,sha


def child(root):
    pid=(root/"project.txt").read_text()
    host(root).publish(pid,"masterav","package",root/"finalav",
                       root,root,root/"delivery","creator_unique_nonce")
    raise RuntimeError("AUDIO-01K injected exit did not execute")


class NativeDistributionCrashMatrix(unittest.TestCase):
    def test_all_eight_checkpoints_fail_closed(self):
        self.assertEqual(len(BOUNDARIES),8)
        for point in BOUNDARIES:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                pid,sha=setup(root)
                env=dict(os.environ)
                env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(ROOT/"tests")
                env["NVP_AUDIO01K_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01K_CRASH_AFTER"]=point
                execution=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "--child",str(root)],
                    env=env,cwd=ROOT,capture_output=True,timeout=90)
                self.assertEqual(execution.returncode,EXIT_CODE,
                    execution.stderr.decode("utf8","replace")[-1500:])
                fresh=host(root)
                output=root/"delivery"
                stage=root/".delivery.audio01k.stage"
                promoted=point in (
                    "directory_promoted","filmindex_registered",
                    "creator_event_published")
                indexed=point in ("filmindex_registered",
                                  "creator_event_published")
                self.assertEqual(output.exists(),promoted)
                if point=="creator_event_reserved":
                    self.assertFalse(stage.exists())
                elif promoted:
                    self.assertFalse(stage.exists())
                else:
                    self.assertTrue(stage.exists())
                if indexed:
                    record=fresh.capture.index.read_revision(pid,"package",1)
                    self.assertFalse(record["data"]["dcp_delivered"])
                    self.assertEqual(record["data"]["source_movie_sha256"],sha)
                else:
                    with self.assertRaises(KeyError):
                        fresh.capture.index.read_revision(pid,"package")
                if point=="creator_event_published":
                    self.assertEqual(
                        fresh.verify(pid,"package",output,root/"finalav",root,root)[
                            "status"],"VERIFIED_MEZZANINE_DISTRIBUTION")
                elif indexed:
                    with self.assertRaises(PermissionError):
                        fresh.verify(pid,"package",output,root/"finalav",root,root)
                with self.assertRaises(PermissionError):
                    fresh.publish(pid,"masterav","another",root/"finalav",
                                  root,root,root/"another",
                                  "creator_unique_nonce")
                self.assertFalse((root/"another").exists())


if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]))
    else:
        unittest.main()
