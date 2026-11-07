"""WO4-LF01 real native process separation, OS singleton and crash recovery.

Unlike fake thread tests, this starts new Python interpreters and calls
os._exit(79) after claiming a durable segment. A later separate process
must recover from the journal, not from the editor's in-memory state.
"""
from hashlib import sha256
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import ProductionJournal,TICKS_PER_SECOND
from backend.nvp_production_supervisor import SingletonSupervisor
from backend.nvp_studio import Studio


class NativeSeparateProcessSupervisor(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.workspace=Path(__file__).resolve().parents[1]
        studio=Studio(self.root/"project.sqlite3")
        index=FilmIndex(studio)
        pid=studio.create_project("Native supervisor test", "Offline source")["id"]
        assembly=index.register_revision(
            pid,"ApprovedAssembly","edit",
            {"format":"nvp.test.immutable_assembly.v1","frozen":True},
            expected_revision=0,dependencies=[])
        self.state=self.root/"supervisor"
        self.journal=ProductionJournal(self.state)
        original=self.root/"approved_recording.raw"
        original.write_bytes(b"trusted original cinema source"*22000)
        source=original.read_bytes()
        self.raw_sha=sha256(source).hexdigest()
        self.original=original
        segments=[{
            "start_tick":n*TICKS_PER_SECOND,
            "end_tick":(n+1)*TICKS_PER_SECOND,
            "source_path":str(original),
            "source_sha256":self.raw_sha,
            "source_bytes":len(source)
        } for n in range(3)]
        self.job=self.journal.submit(
            index,pid,assembly_id="ApprovedAssembly",assembly_revision=1,
            assembly_sha256=assembly["document_sha256"],
            segments=segments,approve=lambda _:True)["job_id"]

    def call(self,command="once",timeout=30):
        return subprocess.run(
            [sys.executable,"-m","backend.nvp_production_supervisor",command,
             "--state-root",str(self.state)],
            cwd=str(self.workspace),check=False,timeout=timeout,
            stdin=subprocess.DEVNULL,capture_output=True,text=True)

    def test_gui_independent_one_shot_processes_finish_durable_job(self):
        self.assertEqual(self.journal.status(self.job)["state"],"QUEUED")
        for n in range(3):
            result=self.call()
            self.assertEqual(result.returncode,0,result.stderr[-700:])
            snapshot=ProductionJournal(self.state).status(self.job)
            self.assertEqual(snapshot["verified_segments"],n+1)
        result=self.call()
        self.assertEqual(result.returncode,0,result.stderr[-700:])
        self.assertEqual(self.journal.status(self.job)["state"],"VERIFY_COMPLETE")
        self.assertEqual(sha256(self.original.read_bytes()).hexdigest(),
                         self.raw_sha)

    def test_real_crash_after_claim_recovers_same_segment_without_data_loss(self):
        code=(
            "import os,sys;"
            "from backend.nvp_production_journal import ProductionJournal;"
            "j=ProductionJournal(sys.argv[1]);"
            "assert j.claim_next('CrashWorker',os.getpid()) is not None;"
            "os._exit(79)"
        )
        child=subprocess.run(
            [sys.executable,"-c",code,str(self.state)],
            cwd=str(self.workspace),check=False,timeout=25,
            stdin=subprocess.DEVNULL,capture_output=True,text=True)
        self.assertEqual(child.returncode,79,child.stderr[-500:])
        interrupted=self.journal.status(self.job)
        self.assertEqual(interrupted["state"],"RUNNING")
        self.assertEqual(interrupted["verified_segments"],0)
        for _ in range(3):
            result=self.call()
            self.assertEqual(result.returncode,0,result.stderr[-700:])
        self.assertEqual(self.journal.status(self.job)["state"],"VERIFY_COMPLETE")
        self.assertEqual(sha256(self.original.read_bytes()).hexdigest(),
                         self.raw_sha)

    def test_second_daemon_cannot_take_singleton_while_first_owns_lock(self):
        with SingletonSupervisor(self.state):
            child=self.call()
        self.assertNotEqual(child.returncode,0)
        self.assertIn("already owns this journal",child.stderr)
        self.assertEqual(self.journal.status(self.job)["state"],"QUEUED")

    def test_native_service_remains_alive_and_completes_without_gui(self):
        service=subprocess.Popen(
            [sys.executable,"-m","backend.nvp_production_supervisor","serve",
             "--state-root",str(self.state)],
            cwd=str(self.workspace),stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                if service.poll() is not None:
                    break
                if self.journal.status(self.job)["state"]=="VERIFY_COMPLETE":
                    break
                time.sleep(0.04)
            self.assertIsNone(service.poll(),"Supervisor should remain running, independent of editor")
            self.assertEqual(self.journal.status(self.job)["state"],"VERIFY_COMPLETE")
            self.assertEqual(sha256(self.original.read_bytes()).hexdigest(),
                             self.raw_sha)
        finally:
            if service.poll() is None:
                service.terminate()
            try:
                out,err=service.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                service.kill()
                out,err=service.communicate(timeout=8)
            self.assertIn("NVP independent production supervisor active",out,
                          err[-600:])


if __name__=="__main__":
    unittest.main()
