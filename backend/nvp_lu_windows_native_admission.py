"""NVP-INT-LU-01F-R2-R2: protected Windows *storage/owner* admission.

This is not Lu peer enrollment. It reuses NVP's real EFS-secured production
journal and the existing OS-held SingletonSupervisor lease. The native Lu
credential/signature broker is still Core-owned and must independently admit
an actual NVP package before the provider exchanges any frames.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from backend.nvp_lu_operation_journal import IPCOperationJournal, JournalRefusal


class WindowsProtectedIPCJournalOwner:
    """Bind IPC SQLite state to the *same* EFS and native owner as NVP jobs.

    This class can only construct a journal after Windows' original production
    supervisor lock is held. The existing NVP _protected_path verifies actual
    Win32 EFS and reparse-point denial on every checked filesystem path.
    """

    def __init__(self, production_journal, production_supervisor):
        if os.name != 'nt' or sys.platform != 'win32':
            raise JournalRefusal('Genuine Windows EFS/owner qualification required')
        from backend.nvp_production_journal import ProductionJournal, _require_owner
        from backend.nvp_production_supervisor import ProductionSupervisor
        from backend.nvp_wo4_pcm_stream import _protected_path
        if (type(production_journal) is not ProductionJournal or
                type(production_supervisor) is not ProductionSupervisor or
                production_supervisor.journal is not production_journal):
            raise JournalRefusal('Only the original native production supervisor may own IPC state')
        _require_owner(production_journal.root)
        self._production = production_journal
        self._require_owner = _require_owner
        self._protected_path = _protected_path
        self.root = production_journal.root
        self._original_root = _protected_path(self.root, directory=True)
        self._original_db = _protected_path(production_journal.db_path)
        self._ipc_db = self.root / 'nvp-lu-operations.sqlite3'

    def guard(self, requested: Path) -> bool:
        """No silent sidecar replacement, encrypted-dir downgrade or lost owner.

        SQLite creates -wal/-shm lazily. Missing sidecars are fine, but every
        existing file must be an ordinary EFS-encrypted source on this owner.
        """
        self._require_owner(self.root)
        if Path(requested) != self.root:
            raise JournalRefusal('Foreign IPC journal storage root')
        if (self._protected_path(self.root, directory=True) != self._original_root or
                self._protected_path(self._production.db_path) != self._original_db):
            raise JournalRefusal('Protected NVP production owner/storage identity changed')
        for p in (self._ipc_db, *(Path(str(self._ipc_db) + s)
                                    for s in ('-wal', '-shm', '-journal'))):
            try:
                p.lstat()
            except FileNotFoundError:
                continue
            if self._protected_path(p) != (p.stat().st_dev, p.stat().st_ino):
                raise JournalRefusal('Protected IPC database/sidecar replaced')
        return True

    def open_journal(self) -> IPCOperationJournal:
        if self.guard(self.root) is not True:
            raise JournalRefusal('Protected IPC journal storage not admitted')
        journal = IPCOperationJournal(self.root, storage_guard=self.guard)
        if self.guard(self.root) is not True:
            raise JournalRefusal('IPC SQLite failed native owner/EFS postflight')
        return journal


def open_installed_windows_ipc_journal(production_journal, production_supervisor):
    """No caller-owned path, environment override or test credential fallback."""
    return WindowsProtectedIPCJournalOwner(
        production_journal, production_supervisor).open_journal()
