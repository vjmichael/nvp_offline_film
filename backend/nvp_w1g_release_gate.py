"""W1-G release-wide Windows worker-launch and program-mutation kernel fence.

Every worker launched through nvp_worker_containment holds a byte-range file
lock for the ENTIRE native Job Object lifetime, not just while spawning.
A trusted update acquires the same file's guard plus *all* worker slots
exclusively before authorizing or renaming the installed program.

The kernel releases file locks on host death. The Job's kill-on-close policy
then handles its descendants; restart remains UNCERTAIN until journals are
reconciled and owner admission occurs. A slot is not a substitute for kernel
job accounting at close, nor does it certify launchers outside NVP.
"""
from __future__ import annotations

import os
from pathlib import Path

MAX_SLOTS = 128
LOCK_LENGTH = MAX_SLOTS + 1


def release_gate_path():
    if os.name != "nt":
        raise RuntimeError("Release-wide Windows admission is Windows-only")
    parent = os.environ.get("LOCALAPPDATA")
    if not parent or not Path(parent).is_absolute():
        raise RuntimeError("Native Windows local application state unavailable")
    root = Path(parent) / "NVP" / "Runtime" / "release-custody"
    for component in (root.parent.parent, root.parent, root):
        if component.is_symlink():
            raise RuntimeError("Symlinked native release custody root refused")
        component.mkdir(exist_ok=True)
    return root / "original-workers.lock"


def _open_lock(path):
    import msvcrt
    path = Path(path)
    if not path.parent.is_dir() or path.parent.is_symlink() or path.is_symlink():
        raise RuntimeError("Native release lock parent or marker not trusted")
    flags = os.O_RDWR | os.O_CREAT | os.O_BINARY
    fd = os.open(path, flags, 0o600)
    if os.fstat(fd).st_size < LOCK_LENGTH:
        os.ftruncate(fd, LOCK_LENGTH)
        os.fsync(fd)
    return fd


def _lock(fd, offset, length):
    import msvcrt
    os.lseek(fd, offset, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_NBLCK, length)


def _unlock(fd, offset, length):
    import msvcrt
    os.lseek(fd, offset, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, length)


class WindowsWorkerLifetimeSlot:
    """Held from before CreateProcess until the original Job tree is empty."""

    def __init__(self, path=None):
        if os.name != "nt":
            raise RuntimeError("Windows worker release fence requires native kernel")
        self.path = Path(path) if path is not None else release_gate_path()
        self.fd = None
        self.slot = None

    def acquire(self):
        if self.fd is not None:
            raise RuntimeError("Native release slot already acquired")
        fd = _open_lock(self.path)
        guard = False
        try:
            _lock(fd, 0, 1)
            guard = True
            for slot in range(1, MAX_SLOTS + 1):
                try:
                    _lock(fd, slot, 1)
                except OSError:
                    continue
                self.fd = fd
                self.slot = slot
                return self
            raise PermissionError("Native release worker capacity or custody blocked")
        finally:
            if guard:
                _unlock(fd, 0, 1)
            if self.fd is None:
                os.close(fd)

    def release(self):
        if self.fd is None:
            return
        fd, slot = self.fd, self.slot
        _unlock(fd, slot, 1)
        os.close(fd)
        self.fd = None
        self.slot = None


class WindowsReleaseMutationGate:
    """Exclusive all-slots kernel proof; no worker launch can race a swap."""

    def __init__(self, path=None):
        if os.name != "nt":
            raise RuntimeError("Production release mutation requires native Windows")
        self.path = Path(path) if path is not None else release_gate_path()
        self.fd = None

    def __enter__(self):
        if self.fd is not None:
            raise RuntimeError("Release mutation gate was already claimed")
        fd = _open_lock(self.path)
        guard = False
        slots = False
        try:
            _lock(fd, 0, 1)
            guard = True
            _lock(fd, 1, MAX_SLOTS)
            slots = True
            self.fd = fd
            return self
        except OSError as exc:
            raise PermissionError(
                "Kernel sees live original workers or another program mutation") from exc
        finally:
            if self.fd is None:
                if slots:
                    _unlock(fd, 1, MAX_SLOTS)
                if guard:
                    _unlock(fd, 0, 1)
                os.close(fd)

    def __exit__(self, kind, value, trace):
        fd = self.fd
        if fd is not None:
            try:
                _unlock(fd, 1, MAX_SLOTS)
                _unlock(fd, 0, 1)
            finally:
                self.fd = None
                os.close(fd)
        return False

    @property
    def held(self):
        return self.fd is not None
