"""AUDIO-01G transaction recovery assertions after exact SQLite crash states.

Crash-exit persistence is independently tested in the subprocess matrix.
Here the restarted native host must reconcile only verified states, preserve
orphaned ACTIVE reservations, and never publish a conflicting result SHA.
"""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01g_mux_intent import prepare,read,transition
from backend.nvp_audio01g_fault_matrix import BOUNDARIES
from test_audio01g_fs_crash_matrix import FS_POINTS
from test_audio01g_sqlite_crash_matrix import ADMISSION_POINTS,FINAL_POINTS
from backend.nvp_audio01g_mux_recovery import (
    inspect_stopped_worker,finalize_verified_worker,reconcile_post_commit_gap,
)
from backend.nvp_resource_guard import AdmissionRequest,ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger

SHA="b"*64


class Host:
    def __init__(self,ledger,stopped=True):
        self.ledger=ledger
        self.stopped=stopped
    def _attest_reaped(self,job):
        return self.stopped
    def _grant(self,job):
        with self.ledger._db() as db:
            row=db.execute("SELECT result_sha FROM native_audio01f_grants WHERE job_id=?",
                           (job,)).fetchone()
        if row is None:raise KeyError("No grant")
        return {"result_sha":row[0]}


class DurableRecoveryAcrossCommit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.ledger=TaskLedger(self.root/"ledger",
            sampler=lambda:ResourceSnapshot(0,16000,12000,0,tuple()))
        self.job="muxrecovery1"
        prepare(self.ledger,self.job,"a"*64)
        self.ledger.admit(AdmissionRequest(self.job,"compositing","Native mux",1024))
        transition(self.ledger,self.job,"prepared","running")
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE native_audio01f_grants(
                job_id TEXT PRIMARY KEY,result_sha TEXT)""")
            db.execute("INSERT INTO native_audio01f_grants VALUES(?,NULL)",(self.job,))
        self.host=Host(self.ledger)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_declared_crash_points_have_subprocess_cases(self):
        cases=FS_POINTS+ADMISSION_POINTS+FINAL_POINTS
        self.assertEqual(len(cases),len(set(cases)))
        self.assertEqual(set(cases),set(BOUNDARIES))

    def test_every_fault_point_is_in_actual_production_code(self):
        import re
        repo=Path(__file__).resolve().parents[1]
        source="\n".join((repo/name).read_text("utf8") for name in (
            "backend/nvp_audio01f_picture_sound.py",
            "backend/nvp_audio01f_native_host.py",
            "tools/nvp_audio01f_native_worker.py"))
        injected=re.findall(r'crash_after[(]"([^"]+)"[)]',source)
        self.assertEqual(len(injected),len(set(injected)))
        self.assertEqual(set(injected),set(BOUNDARIES))

    def test_partial_movie_stays_quarantined_and_reservation_held(self):
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   side_effect=RuntimeError("damaged MOV")):
            status=inspect_stopped_worker(self.host,self.job,self.host._attest_reaped)
        self.assertEqual(status["state"],"QUARANTINED_PARTIAL_MUX")
        self.assertEqual(read(self.ledger,self.job)["state"],"quarantined")
        self.assertEqual(self.ledger.get_task(self.job)["state"],"ACTIVE")
        self.assertEqual(self.ledger.get_task(self.job)["reserved"],1)

    def test_no_os_stop_witness_never_inspects(self):
        host=Host(self.ledger,stopped=False)
        with self.assertRaises(PermissionError):
            inspect_stopped_worker(host,self.job,host._attest_reaped)
        self.assertEqual(read(self.ledger,self.job)["state"],"running")
        self.assertEqual(self.ledger.get_task(self.job)["state"],"ACTIVE")

    def test_completed_media_can_finalize_once_without_rerender(self):
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   return_value=SHA) as verify:
            result=finalize_verified_worker(self.host,self.job,self.host._attest_reaped)
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertEqual(verify.call_count,1)
        self.assertEqual(self.ledger.get_task(self.job)["state"],"SUCCEEDED")
        self.assertEqual(read(self.ledger,self.job),
                         {"plan_sha":"a"*64,"state":"committed","result_sha":SHA})
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   return_value=SHA) as verify:
            again=reconcile_post_commit_gap(self.host,self.job)
        self.assertFalse(again["rerendered"])
        self.assertEqual(verify.call_count,1)

    def test_crash_after_task_success_completes_journal_without_media_change(self):
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01f_grants SET result_sha=? WHERE job_id=?",
                       (SHA,self.job))
            db.commit()
        transition(self.ledger,self.job,"running","verified",SHA)
        self.ledger.finish(self.job,"SUCCEEDED","Verified before journal fsync")
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   return_value=SHA):
            result=reconcile_post_commit_gap(self.host,self.job)
        self.assertEqual(result["state"],"COMMITTED_VERIFIED")
        self.assertEqual(read(self.ledger,self.job)["state"],"committed")

    def test_conflicting_published_digest_rejected(self):
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   return_value=SHA):
            inspect_stopped_worker(self.host,self.job,self.host._attest_reaped)
        with patch("backend.nvp_audio01g_mux_recovery.verify_finished_media",
                   return_value="c"*64):
            with self.assertRaisesRegex(RuntimeError,"changed"):
                inspect_stopped_worker(self.host,self.job,self.host._attest_reaped)
        self.assertEqual(self.ledger.get_task(self.job)["state"],"ACTIVE")


if __name__=="__main__":
    unittest.main()
