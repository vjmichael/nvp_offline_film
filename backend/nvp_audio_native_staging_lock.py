"""Cross-process, OS-released staging lock for NVP audio native jobs.

File ownership and directory admission remain host responsibilities. This lock
protects cooperating host processes even if the SQLite staging row is stale.
Never infer terminated worker ownership from the lock alone.
"""
from __future__ import annotations

import os
from pathlib import Path


class AudioStagingLock:
    def __init__(self, staging_dir):
        target = Path(staging_dir)
        parent = target.parent
        if (not parent.is_dir() or parent.is_symlink() or target.is_symlink()):
            raise RuntimeError("Unsafe audio staging lock parent")
        self.path = parent / (target.name + ".nvp-audio.lock")
        self._file = None

    def acquire(self):
        if self._file is not None:
            raise RuntimeError("Audio staging lock already held")
        # Never follow an existing symlink, even when reopened after a crash.
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(str(self.path), flags, 0o600)
        try:
            if self.path.is_symlink() or not self.path.is_file():
                raise RuntimeError("Unsafe audio staging lock file")
            stream = os.fdopen(fd, "r+b", buffering=0)
        except BaseException:
            os.close(fd)
            raise
        try:
            if os.name == "nt":
                import msvcrt
                # Windows locking is relative to the current file offset.
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            elif os.name == "posix":
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise RuntimeError("Unsupported OS for native audio staging lock")
        except (OSError, RuntimeError) as exc:
            stream.close()
            raise RuntimeError("Audio staging directory is owned by another worker") from exc
        self._file = stream
        return self

    def release(self):
        f = self._file
        self._file = None
        if f is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()
