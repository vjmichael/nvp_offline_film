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
        self.original=self.studio.get_project(self.pid)
        self.migration=LegacyFilmMigration(self.studio,
            review_check=lambda pid,sha:pid==self.pid and len(sha)==64)

    def assert_untouched(self):
        self.assertEqual(self.studio.get_project(self.pid),self.original)
        self.assertEqual(self.path.read_bytes(),SECRET)
        self.assertEqual(self.film.get_blob(self.pid,self.blob_id),SECRET)

    def test_dry_run_lists_referenced_blobs_and_leaves_originals_unchanged(self):
        before=self.migration.inspect(self.pid)
        after=self.migration.inspect(self.pid)
        self.assertEqual(before,after)
        self.assertEqual(before["filmindex_blobs"],[{
            "sha256":self.blob_id,"size_bytes":len(SECRET),"media_type":"audio/pcm"
        }])
        self.assertFalse(before["full_film_cutover_authorized"])
        self.assertFalse(before["active_legacy_workers_migrated"])
        self.assertFalse((self.root/"nvp_g03_migration_candidates").exists())
        self.assert_untouched()

    def test_fails_before_any_copy_on_wrong_reviewed_inventory(self):
        with self.assertRaisesRegex(MigrationRefused,"approved"):
            self.migration.stage_encrypted_candidate(
                self.pid,"Synthetic director migration passphrase","0"*64)
        self.assertFalse((self.root/"nvp_g03_migration_candidates").exists())
        self.assert_untouched()

    def test_missing_or_changed_filmindex_blob_denies_migration(self):
        self.path.write_bytes(b"modified source")
        with self.assertRaisesRegex(MigrationRefused,"corrupt"):
            self.migration.inspect(self.pid)
        self.path.unlink()
        with self.assertRaisesRegex(MigrationRefused,"missing"):
            self.migration.inspect(self.pid)

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
