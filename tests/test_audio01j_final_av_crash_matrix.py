"""AUDIO-01J actual abrupt exits at native MOV/SQLite publication boundaries.

The fixture uses real ProRes and approved real PCM24; only the upstream B14
scene-linear picture render audit is patched for the generated ProRes fixture.
"""
from __future__ import annotations
import json
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
from test_audio01j_native_final_av import source_picture
from test_audio01i_native_master_delivery import setup_approved,ledger

ROOT=Path(__file__).resolve().parents[1]
HOST_POINTS=("av_export_event_reserved","av_grant_committed",
             "av_queued","av_claimed","av_worker_reaped",
             "av_stop_witness_committed","av_master_registered","av_result_committed",
             "av_ledger_succeeded","av_event_completed")
WORKER_POINTS=("av_stage_created","av_mov_verified","av_media_indexed",
               "av_manifest_fsynced","av_directory_promoted","av_filmindex_registered",
               "av_worker_receipt_fsynced")


def hosts(root):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    ah=NativeAudio01IHost(cap,ledger(root),root/"audioi",
       verify_creator_action=lambda *_:True,strict_linux_tree=False)
    j=NativeAudio01JHost(cap,ledger(root),root/"avhost",
       verify_creator_action=lambda *_:True,audio_host=ah,
       strict_linux_tree=False)
    return j


def prepare(root):
    cap,pid,_=setup_approved(root)
    (root/"project.txt").write_text(pid)
    ah=NativeAudio01IHost(cap,ledger(root),root/"audioi",
       verify_creator_action=lambda *_:True,strict_linux_tree=False)
    ah.stage(pid,"mixdecision",1,"candidate","archive_pcm24_v1",
             root/"candidate.wav","human_makes_candidate")
    ah.run_next(timeout_seconds=180)
    ah.deliver(pid,"candidate","audiofinal",root/"audiofinal",
               "human_approves_final_audio")
    source_picture(cap,pid,root)
    j=hosts(root)
    with patch("backend.nvp_audio01j_picture_lock.verify_edited_technical_mov",
               return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE"}):
        j.approve_picture(pid,"picture","picturelock",root,root,root,
                          "human_approves_picture_lock")


def child(root,point):
    pid=(root/"project.txt").read_text()
    j=hosts(root)
    q=j.stage(pid,"picturelock","audiofinal",root,root/"audiofinal",
              root/"finalav","finalfilm","human_final_av_event")
    (root/"job.txt").write_text(q["job_id"])
    if point in WORKER_POINTS:
        try:
            j.run_next(timeout_seconds=180)
        except RuntimeError as error:
            if "97" not in str(error):
                raise
            return
        raise AssertionError("Native AV worker did not abort at injected point")
    j.run_next(timeout_seconds=180)
    raise AssertionError("Native AV host did not abort at injected point")


class FinalAVCrashMatrix(unittest.TestCase):
    def test_post_effect_fail_closed_publication(self):
        for point in (*HOST_POINTS,*WORKER_POINTS):
            with self.subTest(boundary=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                prepare(root)
                pid=(root/"project.txt").read_text()
                env=dict(os.environ)
                env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(ROOT/"tests")
                env["NVP_AUDIO01J_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01J_CRASH_AFTER"]=point
                ran=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                         "--child",str(root),point],cwd=ROOT,env=env,
                         capture_output=True,timeout=260)
                self.assertEqual(ran.returncode,
                    0 if point in WORKER_POINTS else EXIT_CODE,
                    ran.stderr.decode("utf8","replace")[-1600:])
                host=hosts(root)
                if point in ("av_export_event_reserved","av_grant_committed"):
                    self.assertFalse((root/"job.txt").exists())
                    with self.assertRaises(KeyError):
                        host.capture.index.read_revision(pid,"finalfilm")
                    continue
                if point=="av_queued":
                    with host.ledger._db() as db:
                        found=db.execute(
                           "SELECT id FROM tasks WHERE id LIKE 'avjob%'").fetchone()
                    self.assertIsNotNone(found)
                    job=found[0]
                    self.assertEqual(host.ledger.get_task(job)["state"],"QUEUED")
                    with self.assertRaises(PermissionError):
                        host.recover_completed(job)
                    continue
                job=(root/"job.txt").read_text()
                task=host.ledger.get_task(job)
                grant=host._grant(job)
                if point in ("av_claimed","av_worker_reaped",*WORKER_POINTS):
                    self.assertEqual((task["state"],task["reserved"]),("ACTIVE",1))
                    self.assertEqual(grant["stopped"],0)
                    with self.assertRaises(PermissionError):
                        host.recover_completed(job)
                elif point in ("av_stop_witness_committed","av_master_registered",
                             "av_result_committed"):
                    self.assertEqual((task["state"],task["reserved"]),("ACTIVE",1))
                    self.assertEqual(grant["stopped"],1)
                    reconciled=host.recover_completed(job)
                    self.assertEqual(reconciled["state"],"SUCCEEDED")
                    self.assertFalse(reconciled["rerendered"])
                else:
                    self.assertEqual((task["state"],task["reserved"]),("SUCCEEDED",0))
                    self.assertEqual(host.recover_completed(job)["state"],"SUCCEEDED")
                # Worker-published AV candidate never becomes a final master
                # until the trusted host has reaped, independently verified
                # and issued the terminal FilmIndex master revision.
                candidate_id=__import__(
                    "backend.nvp_audio01j_final_av",
                    fromlist=["candidate_id_for"]).candidate_id_for(pid,"finalfilm")
                has_candidate=point not in (
                    "av_queued","av_claimed","av_stage_created",
                    "av_mov_verified","av_media_indexed",
                    "av_manifest_fsynced","av_directory_promoted")
                if has_candidate:
                    candidate=host.capture.index.read_revision(pid,candidate_id,1)
                    self.assertFalse(candidate["data"]["final_master"])
                    self.assertFalse(candidate["data"]["director_approved"])
                else:
                    with self.assertRaises(KeyError):
                        host.capture.index.read_revision(pid,candidate_id)
                if point in ("av_filmindex_registered","av_worker_receipt_fsynced",
                             "av_worker_reaped"):
                    with self.assertRaises(KeyError):
                        host.capture.index.read_revision(pid,"finalfilm")
                elif point in ("av_master_registered","av_result_committed",
                               "av_ledger_succeeded","av_event_completed",
                               "av_stop_witness_committed"):
                    master=host.capture.index.read_revision(pid,"finalfilm",1)
                    self.assertTrue(master["data"]["final_master"])
                    self.assertFalse(master["data"]["dcp_delivered"])



if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
