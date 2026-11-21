"""AUDIO-01G SQLite crash matrix: separate abrupt-exit process per commit.

Admission gates exercise actual NativeAudio01FHost. Post-worker commit gates
exercise the exact TaskLedger/intent transactions with a synthetic completed
worker, NOT a substitute for the separate real Windows Job Object acceptance.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01g_fault_matrix import EXIT_CODE, crash_after
from backend.nvp_audio01g_mux_intent import prepare,read,transition
from backend.nvp_audio01f_native_host import NativeAudio01FHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import AdmissionRequest,ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio

from test_audio01g_fs_crash_matrix import prepare_fixture

ADMISSION_POINTS=(
    "approved_grant_sqlite",
    "intent_prepared_sqlite",
    "task_queued_sqlite",
    "task_claimed_sqlite",
    "intent_running_sqlite",
)
FINAL_POINTS=(
    "worker_receipt_fsynced",
    "native_worker_reaped",
    "os_stop_witness_sqlite",
    "grant_result_sqlite",
    "intent_verified_sqlite",
    "ledger_succeeded_sqlite",
    "intent_committed_sqlite",
)


def ledger_at(root):
    return TaskLedger(root/"ledger",
        sampler=lambda:ResourceSnapshot(0,16000,12000,0,tuple()))


def admission_child(root,point):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    pid=(root/"project_id.txt").read_text()
    host=NativeAudio01FHost(cap,ledger_at(root),root/"native",
        verify_creator_action=lambda event,scope: event=="human_allowed",
        strict_linux_tree=False)
    with (patch("backend.nvp_audio01f_native_host.verify_edited_technical_mov",
                return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE","frames":24}),
          patch("backend.nvp_audio01f_native_host.verify_published_wavs",
                return_value={"status":"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW"})):
        host.stage_and_approve(pid,"picture","sound",root,root,root,root,
            {},{},root,root/("native_output_"+point),
            "human_allowed",presentation_id="native"+point.replace("_",""),
            ram_mb=1024)
        if point in ("task_claimed_sqlite","intent_running_sqlite"):
            host.run_next(timeout_seconds=10)
    raise RuntimeError("Expected native admission fault did not trigger")


def finish_child(root,point):
    ledger=ledger_at(root)
    job="muxcommitted1"
    prepare(ledger,job,"a"*64)
    ledger.admit(AdmissionRequest(job,"compositing","AUDIO 01G fault",1024))
    transition(ledger,job,"prepared","running")
    # This fixture exercises durable mutations, NOT a genuine OS-stop proof.
    # The actual native Job Object proof is tested independently on Windows.
    if point=="worker_receipt_fsynced":
        receipt=root/"worker_receipt.json"
        with receipt.open("xb") as f:
            f.write(b'{"final_master":false,"test_fixture":true}')
            f.flush();os.fsync(f.fileno())
        crash_after(point)
    if point=="native_worker_reaped":
        crash_after(point)
    with ledger._db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS native_audio01g_os_stops(
            job_id TEXT PRIMARY KEY,verified_reaped INTEGER,stopped_at REAL,source TEXT)""")
        db.execute("""CREATE TABLE IF NOT EXISTS native_audio01f_grants(
            job_id TEXT PRIMARY KEY,result_sha TEXT)""")
        db.execute("INSERT INTO native_audio01f_grants VALUES(?,NULL)",(job,))
        db.execute("BEGIN IMMEDIATE")
        db.execute("""INSERT INTO native_audio01g_os_stops VALUES
            (?,1,1,'owned_native_handle_reaped')""",(job,))
        db.commit()
    if point=="os_stop_witness_sqlite":
        crash_after(point)
    sha="b"*64
    with ledger._db() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE native_audio01f_grants SET result_sha=? WHERE job_id=?",
                   (sha,job))
        db.commit()
    if point=="grant_result_sqlite":
        crash_after(point)
    transition(ledger,job,"running","verified",sha)
    if point=="intent_verified_sqlite":
        crash_after(point)
    ledger.finish(job,"SUCCEEDED","Synthetic verified commit fixture")
    if point=="ledger_succeeded_sqlite":
        crash_after(point)
    transition(ledger,job,"verified","committed",sha)
    crash_after(point)
    raise RuntimeError("Expected SQLite fault did not trigger")


class NativeSQLiteCrashMatrix(unittest.TestCase):
    def run_case(self,root,point,mode):
        repo=Path(__file__).resolve().parents[1]
        env=os.environ.copy()
        env["PYTHONPATH"]=str(repo)+os.pathsep+str(repo/"tests")
        env["NVP_AUDIO01G_FAULT_TEST"]="enabled"
        env["NVP_AUDIO01G_CRASH_AFTER"]=point
        completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),
            "--child",str(root),point,mode],cwd=repo,env=env,
            capture_output=True,timeout=90)
        self.assertEqual(completed.returncode,EXIT_CODE,
            completed.stderr.decode("utf8","replace")[-1500:])

    def test_actual_native_admission_crashes(self):
        import shutil
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("Native FFmpeg tools required for authorized preflight")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for point in ADMISSION_POINTS:
                with self.subTest(point=point):
                    case=root/point
                    case.mkdir()
                    # Each case has its own complete FilmIndex and immutable
                    # source asset store; copying SQLite alone drops media.
                    prepare_fixture(case)
                    self.run_case(case,point,"admission")
                    ledger=ledger_at(case)
                    with ledger._db() as db:
                        row=db.execute("SELECT job_id FROM native_audio01f_grants").fetchone()
                        self.assertIsNotNone(row)
                        job=row[0]
                        stops=db.execute("SELECT COUNT(*) FROM native_audio01g_os_stops").fetchone()[0]
                    self.assertEqual(stops,0)
                    state=ledger.get_task(job)
                    if point in ("approved_grant_sqlite","intent_prepared_sqlite"):
                        self.assertIsNone(state)
                    else:
                        self.assertEqual(state["state"],
                            "QUEUED" if point=="task_queued_sqlite" else "ACTIVE")
                        self.assertEqual(state["reserved"],int(state["state"]=="ACTIVE"))
                    self.assertFalse((case/("native_output_"+point)).exists())

    def test_sqlite_completion_crash_boundaries(self):
        for point in FINAL_POINTS:
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                self.run_case(root,point,"finish")
                ledger=ledger_at(root)
                intent=read(ledger,"muxcommitted1")
                task=ledger.get_task("muxcommitted1")
                if point in ("worker_receipt_fsynced","native_worker_reaped"):
                    self.assertEqual(intent["state"],"running")
                    self.assertEqual(task["state"],"ACTIVE")
                    if point=="worker_receipt_fsynced":
                        self.assertTrue((root/"worker_receipt.json").is_file())
                elif point in ("os_stop_witness_sqlite","grant_result_sqlite"):
                    self.assertEqual(intent["state"],"running")
                    self.assertEqual(task["state"],"ACTIVE")
                elif point=="intent_verified_sqlite":
                    self.assertEqual(intent["state"],"verified")
                    self.assertEqual(task["state"],"ACTIVE")
                elif point=="ledger_succeeded_sqlite":
                    self.assertEqual(intent["state"],"verified")
                    self.assertEqual(task["state"],"SUCCEEDED")
                else:
                    self.assertEqual(intent["state"],"committed")
                    self.assertEqual(task["state"],"SUCCEEDED")


if __name__=="__main__":
    if len(sys.argv)==5 and sys.argv[1]=="--child":
        root,point,mode=Path(sys.argv[2]),sys.argv[3],sys.argv[4]
        (admission_child if mode=="admission" else finish_child)(root,point)
    else:
        unittest.main()
