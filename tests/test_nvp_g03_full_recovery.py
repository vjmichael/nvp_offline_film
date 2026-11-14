"""G03-M5 genuine SQLite schema/FK restore tests, no DPAPI mock."""
from __future__ import annotations
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.nvp_g03_full_recovery import _rebuild_sqlite
from backend.nvp_g03_legacy_migration import MigrationRefused

class LegacyRelationalRecoveryTests(unittest.TestCase):
    def sample(self):
        pid="ab"*16
        ddl=[{"type":"table","name":"projects","table":"projects",
              "sql":"CREATE TABLE projects(id TEXT PRIMARY KEY,title TEXT NOT NULL)"},
             {"type":"table","name":"shots","table":"shots",
              "sql":"CREATE TABLE shots(project_id TEXT NOT NULL REFERENCES projects(id),shot TEXT NOT NULL,PRIMARY KEY(project_id,shot))"},
             {"type":"index","name":"idx_shots","table":"shots",
              "sql":"CREATE INDEX idx_shots ON shots(shot)"}]
        return pid,{"format":"nvp.g03.legacy.sql_snapshot.v2",
          "project_id":pid,"schema":ddl,"user_version":4,"application_id":0,
          "tables":{"projects":[{"id":pid,"title":"Original"}],
                    "shots":[{"project_id":pid,"shot":"wide"}]}}
    def test_real_sqlite_reopens_schema_project_rows_and_foreign_keys(self):
        pid,source=self.sample()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"restored.sqlite3"
            self.assertEqual(_rebuild_sqlite(path,source,pid),(3,2))
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(),("ok",))
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(),[])
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],4)
                self.assertEqual(db.execute("SELECT shot FROM shots").fetchone(),("wide",))
                self.assertTrue(db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_shots'").fetchone())
    def test_orphaned_original_relationship_cannot_be_accepted(self):
        pid,source=self.sample()
        source["tables"]["projects"]=[]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(MigrationRefused,"relational references"):
                _rebuild_sqlite(Path(tmp)/"restore.sqlite3",source,pid)
    def test_virtual_or_unreviewed_table_ddl_fails_closed(self):
        pid,source=self.sample()
        source["schema"][0]["sql"]="CREATE VIRTUAL TABLE projects USING fts5(id)"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MigrationRefused):
                _rebuild_sqlite(Path(tmp)/"restore.sqlite3",source,pid)

if __name__=="__main__":
    unittest.main()
