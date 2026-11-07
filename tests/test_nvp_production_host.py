"""WO4 trusted host/independent supervisor reconnect acceptance.

Uses a real OS child process and a real SQLite FilmIndex. This does NOT claim
that Lu's future packaged DLC host/installer already exposes the interface.
"""
from hashlib import sha256
from pathlib import Path
import os
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from backend.nvp_production_host import NativeProductionHost
from backend.nvp_production_journal import TICKS_PER_SECOND
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex


class NativeProductionHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        studio=Studio(self.root/"studio.sqlite3")
        self.index=FilmIndex(studio)
        self.pid=studio.create_project(
            "Background Film","NVP approved export")["id"]
        self.other=studio.create_project(
            "Private Other Film","Isolated project")["id"]
        source=self.root/"original_take.raw"
        data=b"untouched original media"*11000
        source.write_bytes(data)
        assembly=self.index.register_revision(
            self.pid,"FrozenAssembly","edit",
            {"format":"nvp.test.immutable_source.v1","frozen":True},
            expected_revision=0,dependencies=[])
        self.host=NativeProductionHost(self.root/"durable-supervisor")
        approved=self.host.journal.submit(
            self.index,self.pid,assembly_id="FrozenAssembly",
            assembly_revision=1,
            assembly_sha256=assembly["document_sha256"],
            segments=[{"start_tick":0,"end_tick":TICKS_PER_SECOND,
                      "source_path":str(source),
                      "source_sha256":sha256(data).hexdigest(),
                      "source_bytes":len(data)}],approve=lambda _:True)
        self.job=approved["job_id"]

    def tearDown(self):
        if self.host.process is not None and self.host.process.poll() is None:
            self.host.request_clean_shutdown(authorize=lambda _:True)

    def test_trusted_host_autostarts_and_reopened_host_reads_progress(self):
        started=self.host.ensure_running(startup_seconds=15)
        self.assertEqual(started["status"],"RUNNING")
        self.assertFalse(started["gui_process_owns_worker"])
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if self.host.journal.status(self.job)["state"]=="VERIFY_COMPLETE":
                break
            time.sleep(.05)
        self.assertEqual(self.host.journal.status(self.job)["state"],
                         "VERIFY_COMPLETE")
        reopened=NativeProductionHost(self.host.root)
        self.assertEqual(reopened.ensure_running()["status"],
                         "ALREADY_RUNNING")
        status=reopened.reconnect_read_only(
            self.index,self.pid,authorize=lambda s:
                s["project_id"]==self.pid)
        self.assertEqual(len(status["jobs"]),1)
        self.assertEqual(status["jobs"][0]["verified_segments"],1)
        self.assertTrue(status["supervisor_running"])
        self.assertTrue(status["read_only"])
        self.assertFalse(status["can_cancel_job"])
        self.assertNotIn(str(self.root),str(status))
        with self.assertRaises(PermissionError):
            reopened.reconnect_read_only(
                self.index,self.other,authorize=lambda _:False)
        self.assertFalse(self.host.journal.status(self.job)["cancel_requested"])

    def test_supervisor_survives_actual_short_lived_ui_parent_exit(self):
        # A short-lived GUI-like native process launches the background host
        # and exits. A second independent host opens the existing journal.
        script=(
            "import os,sys;"
            "from backend.nvp_production_host import NativeProductionHost;"
            "host=NativeProductionHost(sys.argv[1]);"
            "receipt=host.ensure_running(startup_seconds=15);"
            "assert receipt['supervisor_running'];"
            "print(receipt['pid'],flush=True);"
            "os._exit(0)"
        )
        root=Path(__file__).resolve().parents[1]
        parent=subprocess.run(
            [sys.executable,"-c",script,str(self.host.root)],
            cwd=str(root),capture_output=True,text=True,
            stdin=subprocess.DEVNULL,timeout=24)
        self.assertEqual(parent.returncode,0,parent.stderr[-600:])
        pid=int(parent.stdout.strip().splitlines()[-1])
        try:
            reopened=NativeProductionHost(self.host.root)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if (reopened.is_running() and
                        reopened.journal.status(self.job)["state"]=="VERIFY_COMPLETE"):
                    break
                time.sleep(.05)
            self.assertTrue(reopened.is_running())
            self.assertEqual(reopened.journal.status(self.job)["state"],
                             "VERIFY_COMPLETE")
            self.assertFalse(reopened.journal.status(self.job)["cancel_requested"])
            self.assertEqual(reopened.reconnect_read_only(
                self.index,self.pid,authorize=lambda _:True)["jobs"][0]["status"],
                "VERIFY_COMPLETE")
        finally:
            # The test's detached supervisor belongs to this exact temporary
            # job, not to any installed user service.
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass

    def test_manual_lock_or_reopen_never_requests_worker_cancellation(self):
        self.host.ensure_running()
        monitor=NativeProductionHost(self.host.root)
        for _ in range(3):
            view=monitor.reconnect_read_only(self.index,self.pid,
                                             authorize=lambda _:True)
            self.assertTrue(view["read_only"])
        self.assertFalse(self.host.journal.status(self.job)["cancel_requested"])
        self.assertEqual(self.host.request_clean_shutdown(
            authorize=lambda _:False)["status"],"DENIED")
        self.assertTrue(self.host.is_running())


if __name__=="__main__":
    unittest.main()
