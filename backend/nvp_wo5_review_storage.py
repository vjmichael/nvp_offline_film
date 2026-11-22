"""Reconnect to an existing production journal without initialization or write lease.

The native host supplies its original encrypted-path verifier. This storage
mixin has no independent production supervisor, recovery or migration authority.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3

REQUIRED_TABLES = frozenset({
    'production_jobs', 'production_segments', 'production_events',
    'production_cinema_reels', 'production_cinema_frames',
    'production_cinema_delivery', 'production_features',
})


class ReadOnlyProductionStorage:
    def __init__(self, state_root, *, verify_path):
        if not callable(verify_path):
            raise PermissionError('Trusted native storage verifier required')
        root = Path(state_root)
        if not root.is_absolute():
            raise PermissionError('Exact native production root required')
        self._verify_review_path = verify_path
        self.root_identity = verify_path(root, directory=True)
        self.root = root.resolve(strict=True)
        self.db_path = self.root / 'production-journal.sqlite3'
        self.db_identity = verify_path(self.db_path)
        with self._read() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise PermissionError('Native production journal schema is incomplete')

    def _check_storage(self):
        verify = self._verify_review_path
        if verify(self.root, directory=True) != self.root_identity or verify(self.db_path) != self.db_identity:
            raise PermissionError('Production review journal identity changed')
        for suffix in ('-wal', '-shm', '-journal'):
            path = Path(str(self.db_path) + suffix)
            if os.path.lexists(path):
                verify(path)

    def _tx(self):
        raise PermissionError('Desktop review does not own production writes')

    @contextmanager
    def _read(self):
        self._check_storage()
        # Never create a missing DB, initialize a schema, or migrate a journal.
        # SQLite WAL bookkeeping is allowed only under the existing protected root.
        db = sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True,
                             timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            self._check_storage()
            db.execute('BEGIN')
            yield db
            self._check_storage()
        finally:
            db.close()
