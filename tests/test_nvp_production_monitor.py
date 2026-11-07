"""WO4 native reconnect monitor tests: scope, no source paths, no controls."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import ProductionJournal,TICKS_PER_SECOND
from backend.nvp_production_monitor import ProductionMonitor
from backend.nvp_production_supervisor import ProductionSupervisor,SingletonSupervisor


class ScopedMonitor(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.studio=Studio(self.root/"studio.sqlite")
        self.index=FilmIndex(self.studio)
        self.projects=[
            self.studio.create_project("One Film", "Original film")["id"],
            self.studio.create_project("Other Film", "Private film")["id"]
        ]
        self.journal=ProductionJournal(self.root/"supervisor")
        self.jobs=[]
        for n,pid in enumerate(self.projects):
            approved=self.index.register_revision(
                pid,f"FrozenCut{n}","edit",{"format":"test.approved_cut.v1"},
                expected_revision=0,dependencies=[])
            source=self.root/f"private_source_{n}.pcm"
            source.write_bytes((b"private-file-content-"+bytes([65+n]))*400)
            data=source.read_bytes()
            record=self.journal.submit(
                self.index,pid,
                assembly_id=f"FrozenCut{n}",assembly_revision=1,
                assembly_sha256=approved["document_sha256"],
                segments=[{"start_tick":0,"end_tick":TICKS_PER_SECOND,
                           "source_path":str(source),
                           "source_sha256":sha256(data).hexdigest(),
                           "source_bytes":len(data)}],approve=lambda _:True)
            self.jobs.append(record["job_id"])

    def test_exact_project_read_only_catalog_without_absolute_source_paths(self):
        view=ProductionMonitor(
            self.index,self.journal,
            authorize_project_read=lambda scope:
                scope["project_id"]==self.projects[0])
        result=view.catalog(self.projects[0])
        self.assertEqual(result["project_id"],self.projects[0])
        self.assertEqual(len(result["jobs"]),1)
        self.assertEqual(result["jobs"][0]["job_id"],self.jobs[0])
        self.assertFalse(result["can_cancel_job"])
        self.assertFalse(result["source_paths_exposed"])
        self.assertNotIn(str(self.root),str(result))
        with self.assertRaises(PermissionError):
            view.catalog(self.projects[1])
        with self.assertRaises(PermissionError):
            view.inspect(self.projects[0],self.jobs[1])
        with self.assertRaises(PermissionError):
            view.catalog("a"*32)

    def test_reconnect_reloads_verified_progress_from_sqlite(self):
        monitor=ProductionMonitor(
            self.index,self.journal,authorize_project_read=lambda _:True)
        with SingletonSupervisor(self.journal.root):
            runner=ProductionSupervisor(self.journal)
            self.assertEqual(runner.run_one()["status"],"SEGMENT_VERIFIED")
        reopened=ProductionJournal(self.journal.root)
        newly_opened=ProductionMonitor(
            self.index,reopened,authorize_project_read=lambda _:True)
        status=newly_opened.inspect(self.projects[0],self.jobs[0])
        self.assertEqual(status["job_state"],"VERIFY_COMPLETE")
        self.assertEqual(status["verified_segments"],1)
        self.assertEqual(status["segments"][0]["state"],"VERIFIED")
        self.assertNotIn("source_path",status["segments"][0])
        self.assertNotIn(str(self.root),str(status))
        self.assertFalse(status["can_cancel_job"])
        self.assertFalse(status["production_dcp_accepted"])


if __name__=="__main__":
    unittest.main()
