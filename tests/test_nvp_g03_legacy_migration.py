"""G03-M1 non-destructive legacy film inventory and encrypted staging tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_g03_legacy_migration import LegacyFilmMigration, MigrationRefused
from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_studio import Studio

SCENE="EXT. OLD VALLEY - MORNING\n\nA secret historical screenplay."
SECRET=b'PRIVATE-ORIGINAL-FILM-PCM-DO-NOT-ALTER'


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="nvp-g03-legacy-migrate-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.studio=Studio(self.root/"studio.sqlite3")
        self.project=self.studio.create_project(
            "Existing creator film","Preserve the original idea",SCENE)
        self.pid=self.project["id"]
        self.film=FilmIndex(self.studio)
        self.blob_id=self.film.put_blob(self.pid,SECRET,"audio/pcm")
        self.path=self.film.blob_root/self.pid/self.blob_id[:2]/self.blob_id
        self.sidecar=self.root/"production"/self.pid/"scene-original.usda"
        self.sidecar.parent.mkdir(parents=True)
        self.sidecar.write_bytes(b"#usda 1.0\n# ORIGINAL SIDE DATA")
        self.original=self.studio.get_project(self.pid)
        self.migration=LegacyFilmMigration(self.studio,
            review_check=lambda pid,sha:pid==self.pid and len(sha)==64)

    def assert_untouched(self):
        self.assertEqual(self.studio.get_project(self.pid),self.original)
        self.assertEqual(self.path.read_bytes(),SECRET)
        self.assertEqual(self.film.get_blob(self.pid,self.blob_id),SECRET)
        self.assertEqual(self.sidecar.read_bytes(),
                         b"#usda 1.0\n# ORIGINAL SIDE DATA")

    def test_dry_run_lists_referenced_blobs_and_leaves_originals_unchanged(self):
        before=self.migration.inspect(self.pid)
        after=self.migration.inspect(self.pid)
        self.assertEqual(before,after)
        self.assertEqual(before["filmindex_blobs"],[{
            "sha256":self.blob_id,"size_bytes":len(SECRET),"media_type":"audio/pcm"
        }])
        self.assertFalse(before["full_film_cutover_authorized"])
        self.assertEqual(len(before["project_sidecars"]),1)
        self.assertEqual(before["project_sidecars"][0]["sha256"],
                         hashlib.sha256(self.sidecar.read_bytes()).hexdigest())
        self.assertFalse(before["active_legacy_workers_migrated"])
        self.assertFalse((self.root/"nvp_g03_migration_candidates").exists())
        self.assert_untouched()

    def test_fails_before_any_copy_on_wrong_reviewed_inventory(self):
        with self.assertRaisesRegex(MigrationRefused,"approved"):
            self.migration.stage_encrypted_candidate(
                self.pid,"Synthetic director migration passphrase","0"*64)
        self.assertFalse((self.root/"nvp_g03_migration_candidates").exists())
        self.assert_untouched()

    def test_unattributed_legacy_originals_become_reviewed_inventory_blockers(self):
        orphan=self.root/"unassigned-original-sound.pcm"
        orphan.write_bytes(SECRET)
        first=self.migration.inspect(self.pid)
        items=first["unattributed_original_files"]
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["relative"],orphan.name)
        self.assertEqual(items[0]["sha256"],hashlib.sha256(SECRET).hexdigest())
        self.assertFalse(first["full_film_cutover_authorized"])
        self.assertNotIn(SECRET.decode("ascii"),str(first))
        orphan.write_bytes(SECRET+b"-NEW")
        second=self.migration.inspect(self.pid)
        self.assertNotEqual(first["inventory_sha256"],second["inventory_sha256"])
        self.assert_untouched()

    @unittest.skipUnless(sys.platform=="win32","Requires real Windows DPAPI")
    def test_fresh_process_reopens_known_film_without_modifying_originals(self):
        import subprocess
        from backend.nvp_g03_candidate_recovery import reopen_known_originals
        inventory=self.migration.inspect(self.pid)
        password="G03 independent original film recovery test phrase"
        original_sqlite=self.studio.db_path.read_bytes()
        self.migration.stage_encrypted_candidate(
            self.pid,password,inventory["inventory_sha256"])
        root=self.root/"nvp_g03_migration_candidates"
        # The verifier creates its own store/session and does not inspect the
        # original Studio DB; execute it in a new interpreter after staging.
        code=("""
import json,sys
from backend.nvp_g03_candidate_recovery import reopen_known_originals
request=json.load(sys.stdin)
result=reopen_known_originals(
    request["root"],request["pid"],request["passphrase"],request["inventory"])
print(json.dumps(result,sort_keys=True))
""")
        request={"root":str(root),"pid":self.pid,
                 "passphrase":password,"inventory":inventory}
        run=subprocess.run([sys.executable,"-c",code],input=json.dumps(request),
                           capture_output=True,text=True,timeout=45)
        self.assertEqual(run.returncode,0,run.stderr)
        recovered=json.loads(run.stdout)
        self.assertTrue(recovered["known_payloads_authenticated"])
        self.assertEqual(recovered["known_source_count"],3)
        self.assertFalse(recovered["full_film_cutover_authorized"])
        self.assertFalse(recovered["plaintext_restoration_performed"])
        self.assertFalse(recovered["sql_schema_reconstruction_verified"])
        self.assertEqual(recovered["unresolved_unattributed_files"],0)
        self.assertEqual(recovered["reviewed_inventory_sha256"],
                         inventory["inventory_sha256"])
        self.assertEqual(self.studio.db_path.read_bytes(),original_sqlite)
        self.assert_untouched()
        altered=dict(inventory,legacy_sql_sha256="0"*64)
        with self.assertRaisesRegex(MigrationRefused,"inventory changed"):
            reopen_known_originals(root,self.pid,password,altered)

    def test_missing_or_changed_filmindex_blob_denies_migration(self):
        self.path.write_bytes(b"modified source")
        with self.assertRaisesRegex(MigrationRefused,"corrupt"):
            self.migration.inspect(self.pid)
        self.path.unlink()
        with self.assertRaisesRegex(MigrationRefused,"missing"):
            self.migration.inspect(self.pid)

    def test_unclassified_global_worker_journal_stays_a_review_blocker(self):
        worker=self.root/"native_workers"/"worker_jobs.sqlite3"
        worker.parent.mkdir()
        worker.write_bytes(b"UNCLASSIFIED_WORKER_RECOVERY_STATE")
        report=self.migration.inspect(self.pid)
        self.assertIn("native_workers/worker_jobs.sqlite3",
                      report["unclassified_worker_journals"])
        self.assertFalse(report["full_film_cutover_authorized"])
        self.assert_untouched()

    def test_uncheckpointed_worker_wal_changes_revoke_reviewed_inventory(self):
        import sqlite3
        database=self.root/"worker-recovery"/"worker_jobs.sqlite3"
        database.parent.mkdir()
        conn=sqlite3.connect(database)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA wal_autocheckpoint=0")
            conn.execute("CREATE TABLE journal_rows(project_id TEXT, state TEXT)")
            conn.execute("INSERT INTO journal_rows VALUES (?,?)",
                         (self.pid,"RUNNING"))
            conn.commit()
            wal=Path(str(database)+"-wal")
            self.assertTrue(wal.exists(),"Actual SQLite WAL missing")
            first=self.migration.inspect(self.pid)
            evidence=first["global_worker_journal_provenance"][0]
            self.assertTrue(any(x["name"]=="worker_jobs.sqlite3-wal"
                                for x in evidence["wal_and_shm"]))
            self.assertEqual(evidence["matching_project_rows"],1)
            conn.execute("UPDATE journal_rows SET state='CANCELLED'")
            conn.commit()
            second=self.migration.inspect(self.pid)
            self.assertNotEqual(first["inventory_sha256"],second["inventory_sha256"])
            self.assertFalse(second["full_film_cutover_authorized"])
        finally:
            conn.close()

    def test_real_global_worker_sqlite_is_classified_without_assuming_custody(self):
        import sqlite3
        journal=self.root/"worker-service"/"worker_jobs.sqlite3"
        journal.parent.mkdir()
        db=sqlite3.connect(journal)
        try:
            db.execute("""CREATE TABLE job_project_index(
                job_id TEXT PRIMARY KEY,project_id TEXT NOT NULL)""")
            db.execute("""CREATE TABLE worker_jobs(
                job_id TEXT PRIMARY KEY,spec_json TEXT,state TEXT)""")
            db.execute("INSERT INTO job_project_index VALUES (?,?)",
                       ("job-owner",self.pid))
            db.execute("INSERT INTO job_project_index VALUES (?,?)",
                       ("job-foreign","f"*32))
            db.execute("INSERT INTO worker_jobs VALUES (?,?,?)",
                       ("job-owner",'{"film":"private"}',"RUNNING"))
            db.commit()
        finally:
            db.close()
        report=self.migration.inspect(self.pid)
        evidence=report["global_worker_journal_provenance"]
        self.assertEqual(len(evidence),1)
        self.assertEqual(evidence[0]["format"],"sqlite")
        self.assertEqual(evidence[0]["matching_project_rows"],1)
        self.assertIn("worker_jobs",evidence[0]["unclassified_tables"])
        self.assertFalse(evidence[0]["live_worker_custody_proved"])
        self.assertFalse(evidence[0]["safe_to_cutover"])
        self.assertNotIn("private",str(report))
        self.assert_untouched()
        # Changing the global journal invalidates the reviewed inventory.
        previous=report["inventory_sha256"]
        db=sqlite3.connect(journal)
        try:
            db.execute("UPDATE worker_jobs SET state='SUCCEEDED'")
            db.commit()
        finally:
            db.close()
        self.assertNotEqual(self.migration.inspect(self.pid)["inventory_sha256"],
                            previous)

    def test_unknown_global_sql_tables_are_reported_not_hidden(self):
        with self.studio._connection() as db:
            db.execute("CREATE TABLE migration_unknown_global_notes(data TEXT)")
            db.execute("INSERT INTO migration_unknown_global_notes VALUES (?)",
                       ("Confidential unrelated source",))
        evidence=self.migration.inspect(self.pid)
        self.assertIn("migration_unknown_global_notes",
                      evidence["unknown_nonproject_tables"])
        self.assertFalse(evidence["full_film_cutover_authorized"])
        self.assert_untouched()

    @unittest.skipUnless(sys.platform=="win32","Requires real Windows DPAPI")
    def test_real_encrypted_candidate_reopens_all_sql_rows_and_pcm(self):
        from backend.nvp_g03_windows_vault import VaultError
        evidence=self.migration.inspect(self.pid)
        original_db=self.studio.db_path.read_bytes()
        result=self.migration.stage_encrypted_candidate(
            self.pid,"G03 synthetic candidate review passphrase",
            evidence["inventory_sha256"])
        self.assertEqual(result["status"],"ENCRYPTED_CANDIDATE_VERIFIED")
        self.assertFalse(result["active_project_switched"])
        self.assertFalse(result["complete_confidentiality"])
        self.assertEqual(self.studio.db_path.read_bytes(),original_db)
        self.assert_untouched()
        stage=LiveFilmStore(self.root/"nvp_g03_migration_candidates")
        token="migration-verify-"+("9"*32)
        stage.authorize(self.pid,"G03 synthetic candidate review passphrase",token)
        self.assertEqual(stage.read(self.pid,token)["screenplay"],SCENE)
        rows=json.loads(stage.get_original(
            self.pid,token,"migration/legacy-project-tables.json"))
        self.assertEqual(rows["project_id"],self.pid)
        self.assertTrue(rows["tables"]["projects"])
        blob=stage.get_original(self.pid,token,
                                "migration/filmindex/"+self.blob_id)
        self.assertEqual(blob,SECRET)
        self.assertEqual(stage.get_original(
            self.pid,token,"migration/sidecars/production/"+
            self.pid+"/scene-original.usda"),self.sidecar.read_bytes())
        self.assertEqual(result["copied_project_sidecars"],1)
        for path in (self.root/"nvp_g03_migration_candidates").rglob("*"):
            if path.is_file():
                raw=path.read_bytes()
                self.assertNotIn(SECRET,raw)
                self.assertNotIn(b"secret historical screenplay",raw)
        # No cutover without independently reviewed metadata, workers and
        # previous plaintext source cleanup: live production remains original.
        self.assertFalse((self.root/"nvp_g03_encrypted_live"/self.pid).exists())


if __name__=="__main__":
    unittest.main()
