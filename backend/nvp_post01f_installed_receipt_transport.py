"""Read the SCM-owned, EFS-encrypted POST-01F v2 receipt by *fixed* Windows path.

Host-side transport only. Neither the worker nor a UI chooses a filename,
trust key, digest or result. The separately pinned P-256 signature, exact job
scope, and durable G03 nonce consumption are checked by InstalledScmCngV2Channel.
This code does NOT install/attest a Windows service or provision a signing key.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import stat
import sys
import uuid

from backend.nvp_post01f_scm_cng_v2 import (
    InstalledScmCngV2Channel, load_installed_scm_verifier_key,
)

_JOB = re.compile(r'ltx_[0-9a-f]{24}\Z')
_MAX_RECEIPT_BYTES = 8192
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_FILE_IS_ENCRYPTED = 1
_INVALID_FILE_ATTRIBUTES = 0xffffffff
# FOLDERID_ProgramData: fixed machine known-folder identity, never an env value.
_PROGRAM_DATA_GUID = '62ab5d82-fdc1-4dc3-a9dd-070d1d495d97'


class _GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]


def _program_data() -> Path:
    if sys.platform != 'win32':
        raise PermissionError('SCM receipts require the installed Windows host')
    raw = uuid.UUID(_PROGRAM_DATA_GUID).bytes_le
    guid = _GUID.from_buffer_copy(raw)
    folder = ctypes.c_void_p()
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    ole = ctypes.WinDLL('ole32', use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(_GUID), wintypes.DWORD,
                                          wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    hr = shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(folder))
    if hr != 0 or not folder.value:
        raise PermissionError('Native ProgramData known folder unavailable')
    try:
        path = ctypes.wstring_at(folder.value)
    finally:
        ole.CoTaskMemFree(folder)
    root = Path(path)
    if not root.is_absolute():
        raise PermissionError('Native ProgramData known folder was not absolute')
    return root


def _attributes(path: Path) -> int:
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    attrs = kernel.GetFileAttributesW(str(path))
    if attrs == _INVALID_FILE_ATTRIBUTES or attrs & _FILE_ATTRIBUTE_REPARSE_POINT:
        raise PermissionError('SCM protected receipt path is missing or redirected')
    return attrs


def _require_efs(path: Path) -> None:
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.FileEncryptionStatusW.argtypes = [wintypes.LPCWSTR,
                                             ctypes.POINTER(wintypes.DWORD)]
    advapi.FileEncryptionStatusW.restype = wintypes.BOOL
    state = wintypes.DWORD()
    if not advapi.FileEncryptionStatusW(str(path), ctypes.byref(state)) or state.value != _FILE_IS_ENCRYPTED:
        raise PermissionError('SCM result lacks real Windows EFS protection')


def _installed_receipt_path(job_id: str) -> Path:
    root = _program_data()
    for sub in ('NVP', 'POST01F', 'SCMReceipts'):
        root = root / sub
        if not _attributes(root) & _FILE_ATTRIBUTE_DIRECTORY:
            raise PermissionError('Missing protected SCM receipt directory')
    # The installed native SCM broker verifies EFS on SCMReceipts and the
    # receipt itself, not necessarily on its intermediate ProgramData parents.
    # Preserve that source contract while refusing links on EVERY component.
    _require_efs(root)
    return root / (job_id + '.v2.json')


def receive_installed_scm_receipt(job_id: str, worker_pid: int) -> bytes:
    """Read a bounded EFS SCM receipt; cryptographic verification is mandatory next.

    No caller-supplied path, alternate trust root, environment override, or
    unsigned receipt fallback. Reject ambiguous metadata changes during read.
    """
    if (type(job_id) is not str or not _JOB.fullmatch(job_id) or
            type(worker_pid) is not int or worker_pid <= 0 or sys.platform != 'win32'):
        raise PermissionError('Exact installed Windows SCM result identity required')
    path = _installed_receipt_path(job_id)
    if _attributes(path) & _FILE_ATTRIBUTE_DIRECTORY:
        raise PermissionError('SCM receipt is not an ordinary file')
    _require_efs(path)
    # pathlib.Path.stat(follow_symlinks=...) was added in Python 3.13;
    # installed NVP can run Python 3.11. os.stat has this contract on 3.11.
    before = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or before.st_size < 2 or
            before.st_size > _MAX_RECEIPT_BYTES):
        raise PermissionError('SCM result size/type out of bounds')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev, before.st_ino, before.st_size):
            raise PermissionError('SCM receipt replaced between validation and open')
        chunks = bytearray()
        while len(chunks) <= _MAX_RECEIPT_BYTES:
            part = os.read(fd, min(4096, _MAX_RECEIPT_BYTES + 1 - len(chunks)))
            if not part:
                break
            chunks.extend(part)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (len(chunks) != before.st_size or len(chunks) > _MAX_RECEIPT_BYTES or
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
            (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
        raise PermissionError('SCM receipt was truncated or changed during read')
    if _attributes(path) & _FILE_ATTRIBUTE_DIRECTORY:
        raise PermissionError('SCM receipt changed after read')
    _require_efs(path)
    return bytes(chunks)


def bind_installed_scm_receipt_channel(*, consume_once):
    """Construct only the source-locked host reader and independently pinned verifier.

    `consume_once` must be supplied by the live authenticated project journal.
    Its durability and the native Windows installation are separate gates.
    """
    if sys.platform != 'win32' or not callable(consume_once):
        raise PermissionError('Installed Windows host and durable nonce journal required')
    return InstalledScmCngV2Channel(
        pinned_p256_public=load_installed_scm_verifier_key(),
        receive_from_scm=receive_installed_scm_receipt,
        consume_once=consume_once,
    )
