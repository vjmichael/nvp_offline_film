from contextlib import closing
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
from backend.nvp_wo5_review_storage import REQUIRED_TABLES, ReadOnlyProductionStorage


def local_identity(path, directory=False):
    # Portable identity fixture only. Windows integration uses actual EFS checks.
    path = Path(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (directory and not path.is_dir()) or (not directory and not path.is_file()):
        raise PermissionError('Invalid fixture storage')
    return info.st_dev, info.st_ino


class ReviewStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.path = self.root / 'production-journal.sqlite3'

    def make_db(self, complete=True):
        # sqlite3.Connection.__exit__ commits/rolls back but does not close.
        # Explicit closure is mandatory before Windows rename/delete checks.
        with closing(sqlite3.connect(self.path)) as db, db:
            for table in sorted(REQUIRED_TABLES if complete else {'production_jobs'}):
                db.execute(f'CREATE TABLE {table} (value TEXT)')
            db.execute("INSERT INTO production_jobs VALUES ('original')")

    def open(self):
        return ReadOnlyProductionStorage(self.root, verify_path=local_identity)

    def test_fixture_writer_and_reader_close_even_with_retained_references(self):
        original = sqlite3.connect
        retained = []
        def track(*args, **kwargs):
            db = original(*args, **kwargs)
            retained.append(db)
            return db
        with patch('sqlite3.connect', side_effect=track):
            self.make_db()
            view = self.open()
            with self.assertRaisesRegex(RuntimeError, 'intentional read failure'):
                with view._read():
                    raise RuntimeError('intentional read failure')
        self.assertEqual(len(retained), 3)
        for db in retained:
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute('SELECT 1')

    def test_missing_database_is_not_created(self):
        with self.assertRaises(FileNotFoundError):
            self.open()
        self.assertFalse(self.path.exists())

    def test_read_only_no_migration(self):
        self.make_db()
        before = self.path.read_bytes()
        view = self.open()
        with view._read() as db:
            self.assertEqual(db.execute('SELECT value FROM production_jobs').fetchone()[0], 'original')
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM production_jobs")
            db.execute('PRAGMA query_only=OFF')
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('CREATE TABLE evil (x)')
        with self.assertRaises(PermissionError):
            view._tx()
        self.assertEqual(before, self.path.read_bytes())

    def test_incomplete_schema_fails_without_creating_tables(self):
        self.make_db(False)
        before = self.path.read_bytes()
        with self.assertRaises(PermissionError):
            self.open()
        self.assertEqual(before, self.path.read_bytes())

    def test_replaced_journal_fails(self):
        self.make_db()
        view = self.open()
        self.path.rename(self.root / 'old.sqlite3')
        self.make_db()
        with self.assertRaises(PermissionError):
            with view._read():
                self.fail('Replacement was admitted')

    def test_existing_linked_sidecar_fails(self):
        self.make_db()
        external = self.root / 'untrusted'
        external.touch()
        Path(str(self.path) + '-wal').symlink_to(external)
        with self.assertRaises(PermissionError):
            self.open()
