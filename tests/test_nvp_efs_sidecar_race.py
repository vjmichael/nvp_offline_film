"""Portable error classification and guarded optional WAL disappearance tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backend.nvp_w1g_encrypted_source import _raise_efs_query_failure
from backend.nvp_production_journal import ProductionJournal


class EfsSidecarRace(unittest.TestCase):
    def test_only_native_missing_codes_are_absence(self):
        for code in (2,3):
            with self.subTest(code=code), self.assertRaises(FileNotFoundError):
                _raise_efs_query_failure(code)
        for code in (0,5,32,87,6002):
            with self.subTest(code=code), self.assertRaisesRegex(PermissionError, f'Win32 {code}'):
                _raise_efs_query_failure(code)

    def setUp(self):
        temp=TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        db=root/'production-journal.sqlite3'; db.write_bytes(b'db')
        self.side=Path(str(db)+'-wal'); self.side.write_bytes(b'wal')
        self.journal=SimpleNamespace(root=root,db_path=db,root_identity=(1,1),db_identity=(1,2))

    def check(self, side_effect, *, root_identity=(1,1),db_identity=(1,2)):
        def verify(path,*,directory=False):
            if path==self.journal.root: return root_identity
            if path==self.journal.db_path: return db_identity
            return side_effect(path)
        with patch('backend.nvp_production_journal._protected_path', side_effect=verify):
            ProductionJournal._check_storage(self.journal)

    def test_optional_disappearance_after_native_query_is_allowed(self):
        def gone(path):
            path.unlink(); _raise_efs_query_failure(2)
        self.check(gone)
        self.assertFalse(self.side.exists())

    def test_missing_error_with_existing_entry_refused(self):
        with self.assertRaises(FileNotFoundError): self.check(lambda _: _raise_efs_query_failure(2))

    def test_access_denial_never_becomes_absence(self):
        def denied(path):
            path.unlink(); _raise_efs_query_failure(5)
        with self.assertRaises(PermissionError): self.check(denied)

    def test_non_encrypted_existing_entry_refused(self):
        with self.assertRaises(PermissionError):
            self.check(lambda _: (_ for _ in ()).throw(PermissionError('not encrypted')))

    def test_changed_root_on_disappearance_refused(self):
        calls=0
        def verify(path,*,directory=False):
            nonlocal calls
            if path==self.journal.root:
                calls+=1; return (1,calls)
            if path==self.journal.db_path: return (1,2)
            path.unlink(); _raise_efs_query_failure(2)
        with patch('backend.nvp_production_journal._protected_path',side_effect=verify),self.assertRaises(PermissionError):
            ProductionJournal._check_storage(self.journal)

    def test_missing_main_database_is_never_optional(self):
        def verify(path,*,directory=False):
            if path==self.journal.root: return (1,1)
            _raise_efs_query_failure(2)
        with patch('backend.nvp_production_journal._protected_path',side_effect=verify),self.assertRaises(FileNotFoundError):
            ProductionJournal._check_storage(self.journal)

if __name__=='__main__': unittest.main()
