"""AUDIO-01G: real contained worker through seven late native crash boundaries.

The native host launches an actual Python/FFmpeg subprocess under the NVP
Windows Job Object. The worker renders authentic 24-fps ProRes + 48-kHz PCM
into FilmIndex. Upstream B14/audio proof callbacks are isolated fixtures, so
this test proves native lifecycle, real mux, and late SQL crash persistence;
the full unmocked B14 integration remains a separate acceptance gate.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01g_fault_matrix import EXIT_CODE
from backend.nvp_audio01g_mux_intent import read
from backend.nvp_audio01f_native_host import NativeAudio01FHost
from backend.nvp_audio01f_picture_sound import _verify_streams,_decoded_sha,_wav_pcm_proof
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_studio import Studio
from test_audio01g_fs_crash_matrix import prepare_fixture

LATE=(
    "worker_receipt_fsynced","native_worker_reaped",
    "os_stop_witness_sqlite","grant_result_sqlite",
    "intent_verified_sqlite","ledger_succeeded_sqlite",
    "intent_committed_sqlite",
)
REPO=Path(__file__).resolve().parents[1]
WORKER=REPO/"tests/fixtures/nvp_audio01g_native_real_mux_worker.py"


def ledger(root):
    return TaskLedger(root/"ledger",
        sampler=lambda:ResourceSnapshot(0,16000,12000,0,tuple()))


def child(root,point):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    project=(root/"project_id.txt").read_text()
    host=NativeAudio01FHost(cap,ledger(root),root/"native",
        verify_creator_action=lambda event,scope: event=="creator_ci",
        strict_linux_tree=False)
    host.worker=WORKER
    with (
        patch("backend.nvp_audio01f_native_host.verify_edited_technical_mov",
              return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE","frames":24}),
        patch("backend.nvp_audio01f_native_host.verify_published_wavs",
              return_value={"status":"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW"}),
        patch("backend.nvp_audio01f_native_host.verify_picture_sound_preview",
              return_value={"status":"VERIFIED_UNAPPROVED_PICTURE_SOUND_REVIEW",
                            "samples_per_channel":48000,"frames":24}),
    ):
        queued=host.stage_and_approve(
            project,"picture","sound",root,root,root,root,{},{},root,
            root/"review","creator_ci",presentation_id="nativecrashpreview",
            ram_mb=1024,ffmpeg="ffmpeg",ffprobe="ffprobe")
        (root/"job_id.txt").write_text(queued["job_id"])
        try:
            host.run_next(timeout_seconds=100)
        except RuntimeError:
            if point=="worker_receipt_fsynced":
                os._exit(95)  # Real worker exited 93; host caught and quarantined
            raise
    raise RuntimeError("Crash point was not reached")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Real FFmpeg/FFprobe required")
class ActualNativeWorkerLateCrashMatrix(unittest.TestCase):
    def test_every_late_boundary_real_worker_and_durable_recovery_state(self):
        for point in LATE:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                prepare_fixture(root)
                original=(root/"silent.mov").read_bytes(),(root/"mix_preview.wav").read_bytes()
                env=os.environ.copy()
                env["PYTHONPATH"]=str(REPO)+os.pathsep+str(REPO/"tests")
                env["NVP_AUDIO01G_FAULT_TEST"]="enabled"
                env["NVP_AUDIO01G_CRASH_AFTER"]=point
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                    "--child",str(root),point],cwd=REPO,env=env,
                    capture_output=True,timeout=180)
                expected=95 if point=="worker_receipt_fsynced" else EXIT_CODE
                self.assertEqual(result.returncode,expected,
                    result.stderr.decode("utf8","replace")[-2400:])
                job=(root/"job_id.txt").read_text()
                native=ledger(root)
                task=native.get_task(job)
                intent=read(native,job)
                host=NativeAudio01FHost(
                    DigitalCapture(Studio(root/"studio.sqlite3")),
                    native,root/"native",verify_creator_action=lambda *_:False,
                    strict_linux_tree=False)
                self.assertEqual((root/"silent.mov").read_bytes(),original[0])
                self.assertEqual((root/"mix_preview.wav").read_bytes(),original[1])
                # Actual real mux and decoded stream must survive at every
                # post-worker crash boundary, including worker receipt fsync.
                mov=root/"review/picture_sound_review.mov"
                self.assertTrue(mov.is_file())
                self.assertEqual(_verify_streams(mov,24,"ffprobe")["samples_per_channel"],48000)
                self.assertEqual(_decoded_sha(mov,"audio","ffmpeg")[0],
                                 _wav_pcm_proof(root/"mix_preview.wav")[0])
                self.assertFalse((root/"review/picture_sound_manifest.json").is_symlink())
                if point=="native_worker_reaped":
                    self.assertFalse(host._attest_reaped(job),
                        "Host crash before stop witness must not forge attestation")
                else:
                    self.assertTrue(host._attest_reaped(job))
                if point in ("ledger_succeeded_sqlite","intent_committed_sqlite"):
                    self.assertEqual(task["state"],"SUCCEEDED")
                    self.assertEqual(task["reserved"],0)
                else:
                    self.assertEqual(task["state"],"ACTIVE")
                    self.assertEqual(task["reserved"],1)
                states={
                    "worker_receipt_fsynced":"quarantined",
                    "native_worker_reaped":"running",
                    "os_stop_witness_sqlite":"running",
                    "grant_result_sqlite":"running",
                    "intent_verified_sqlite":"verified",
                    "ledger_succeeded_sqlite":"verified",
                    "intent_committed_sqlite":"committed",
                }
                self.assertEqual(intent["state"],states[point])
                if point=="native_worker_reaped":
                    with self.assertRaises(PermissionError):
                        host.inspect_interrupted(job)
                elif task["state"]=="ACTIVE":
                    # Reopen independent verifier fixture only; this *still*
                    # enforces original source media and no implicit re-render.
                    with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                               return_value=host.capture.index.read_revision(
                                   (root/"project_id.txt").read_text(),
                                   "nativecrashpreview",1)["document_sha256"]):
                        inspected=host.inspect_interrupted(job)
                    self.assertEqual(inspected["state"],"VERIFIED_STOPPED_MUX")
                else:
                    with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                               return_value=host._grant(job)["result_sha"]):
                        reconciled=host.reconcile_committed_after_restart(job)
                    self.assertFalse(reconciled["rerendered"])


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
