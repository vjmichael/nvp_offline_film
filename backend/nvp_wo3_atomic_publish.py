"""WO3 native atomic DCP directory publication without replacement.

Linux renameat2(RENAME_NOREPLACE) and Windows MoveFileExW without
MOVEFILE_REPLACE_EXISTING are OS-enforced cross-process no-clobber
operations. Unsupported systems fail closed rather than use check-then-rename.
The exporter writes and fsyncs each stage file before calling this primitive.
"""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import sys

AT_FDCWD = -100
RENAME_NOREPLACE = 1
MOVEFILE_WRITE_THROUGH = 0x8


def _fsync_directory(folder):
    """Flush directory metadata where supported; never promise Windows power-loss durability."""
    if os.name == "nt":
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(folder, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def atomic_publish_directory(stage, target):
    """Promote on the same volume, without ever replacing an existing name.

    Staging and destination must be siblings. Caller owns the trusted root,
    parent-directory selection, staged manifest validation and failure recovery.
    """
    source = Path(stage)
    destination = Path(target)
    if (not source.is_absolute() or not destination.is_absolute()
            or source.parent != destination.parent
            or source == destination or source.is_symlink()
            or not source.is_dir() or destination.is_symlink()):
        raise PermissionError("Atomic export requires approved same-parent stage")
    parent = source.parent
    if parent.is_symlink() or not parent.is_dir():
        raise PermissionError("Approved export parent changed")
    src = os.fspath(source)
    dst = os.fspath(destination)
    # The existence check is advisory only. The kernel operation provides
    # the cross-process no-overwrite guarantee even if another writer races.
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(dst)
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise NotImplementedError("renameat2 no-replace unavailable")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p,
                           ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(AT_FDCWD, os.fsencode(src), AT_FDCWD,
                        os.fsencode(dst), RENAME_NOREPLACE)
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(error, os.strerror(error), dst)
            raise OSError(error, os.strerror(error), dst)
    elif sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move = kernel32.MoveFileExW
        move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                         ctypes.c_uint]
        move.restype = ctypes.c_int
        if not move(src, dst, MOVEFILE_WRITE_THROUGH):
            error = ctypes.get_last_error()
            if error in (80, 183):
                raise FileExistsError(error, "Destination exists", dst)
            raise OSError(error, "Windows atomic move failed", dst)
    else:
        raise NotImplementedError("No verified atomic no-replace backend for host")
    _fsync_directory(parent)
    return {"status": "ATOMIC_NO_REPLACE_PROMOTED",
            "parent_metadata_fsynced": os.name != "nt",
            "power_loss_durability_certified": False}
