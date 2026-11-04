"""NVP-STACK-02C: kernel-backed one-owner lease for a worker journal.

Uses standard OS advisory record locks, not PID files, expiry timestamps or
home-grown heartbeats. A host must own this lock for the COMPLETE execution of
a worker operation or cold-start journal recovery.

POSIX flock is on its own opened file description; Windows uses msvcrt.locking
with an exclusive, non-blocking byte-range lock. A kernel releases the lock
automatically on process exit, including os._exit or an actual host crash.

This contract is for a single-machine, local-filesystem workspace. Networked
shares, multiple machines and code that bypasses this lease are unsupported.
Read-only inspect/verification can remain concurrent because they do not mutate
the journal, authorize processing, or mark an active task interrupted.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path


class WorkerHostLease:
    def __init__(self, workspace):
        self.root=Path(workspace).resolve()
        self.fd=None

    def __enter__(self):
        if self.fd is not None:
            raise RuntimeError("Worker host lease is already owned")
        if not self.root.is_dir() or self.root.is_symlink():
            raise RuntimeError("Worker workspace must exist and not be a symlink")
        path=self.root/"worker_host.lock"
        if path.is_symlink():
            raise RuntimeError("Refusing a symlinked worker host lease")
        flags=os.O_RDWR|os.O_CREAT
        if hasattr(os,"O_BINARY"):
            flags|=os.O_BINARY
        if hasattr(os,"O_NOFOLLOW"):
            flags|=os.O_NOFOLLOW
        fd=os.open(path,flags,0o600)
        try:
            # Windows' 1-byte locking works on existing file bytes. The fixed
            # byte is a marker, never an ownership token or PID.
            if os.fstat(fd).st_size==0:
                os.write(fd,b"L")
                os.fsync(fd)
            os.lseek(fd,0,os.SEEK_SET)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
            elif os.name=="posix":
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            else:
                raise RuntimeError("Unsupported OS for NVP production lease")
            self.fd=fd
            return self
        except (OSError,RuntimeError) as exc:
            os.close(fd)
            if isinstance(exc,OSError) and exc.errno in (errno.EACCES,errno.EAGAIN):
                raise RuntimeError("Another NVP host owns the worker journal; recovery and execution blocked") from exc
            raise

    def __exit__(self,exc_type,exc,traceback):
        fd=self.fd
        if fd is None:
            return False
        self.fd=None
        try:
            os.lseek(fd,0,os.SEEK_SET)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_UN)
        finally:
            os.close(fd)
        return False


def exclusive_worker_host(fn):
    """Hold a kernel lock across all worker launches and journal mutations."""
    from functools import wraps
    @wraps(fn)
    def wrapped(self,*args,**kwargs):
        with WorkerHostLease(self.root):
            return fn(self,*args,**kwargs)
    return wrapped
