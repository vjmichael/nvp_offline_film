"""W1-G/INT-02 native source-at-rest EFS boundary for protected films.

Blender's USD import requires a filesystem path. A consent checkbox cannot
make an unencrypted USD worker directory secure. Protected source jobs need
actual Windows EFS on their DEDICATED job directory and each input, or the
native launch is denied. On Linux no equivalent encrypted workspace is
attested here, so protected source rendering fails closed.

This does not replace project key management, EFS recovery-key policy, ACL
review, or crash-cleanup acceptance. NVP does not claim encryption of
plaintext 2D exports or provision EFS silently on a creator's machine.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path

FILE_IS_ENCRYPTED=1


def _efs_status(path: Path) -> bool:
    if os.name!="nt":
        return False
    status=ctypes.c_uint32()
    ok=ctypes.windll.advapi32.FileEncryptionStatusW(
        str(path),ctypes.byref(status))
    if ok==0:
        raise PermissionError("Windows EFS encryption status is unavailable")
    return status.value==FILE_IS_ENCRYPTED


def require_efs_stage(jobdir: Path):
    """Enable EFS before ANY source bytes are written, and verify it."""
    jobdir=Path(jobdir)
    if (not jobdir.is_dir() or jobdir.is_symlink() or
        jobdir.parent.is_symlink()):
        raise PermissionError("Protected native staging must use a dedicated nonlinked directory")
    if os.name!="nt":
        raise PermissionError("Protected original USD requires native EFS-capable Windows storage")
    if ctypes.windll.advapi32.EncryptFileW(str(jobdir))==0:
        raise PermissionError("Protected source cannot be staged on storage without EFS")
    if not _efs_status(jobdir):
        raise PermissionError("Native worker directory has no verified EFS encryption")
    # Verify that a new child really INHERITS encryption before placing
    # any creator source on this filesystem. Do not trust the folder flag
    # alone or discover unencrypted storage after staging sensitive bytes.
    probe=jobdir/".nvp-efs-preflight"
    if probe.exists() or probe.is_symlink():
        raise PermissionError("Stale EFS preflight file in protected source directory")
    try:
        with probe.open("xb") as out:
            out.write(b"NVP-EFS-TEST-NO-SOURCE")
            out.flush()
            os.fsync(out.fileno())
        if not _efs_status(probe):
            raise PermissionError("New worker source files would not inherit EFS")
    finally:
        probe.unlink(missing_ok=True)
    return {"encrypted_at_rest_verified":True,
            "encryption_method":"windows-efs",
            "plaintext_native_source_saved_unencrypted":False}


def verify_efs_inputs(jobdir: Path, names=("source.usda","plan.json","render.py")):
    root=Path(jobdir)
    if not _efs_status(root):
        raise PermissionError("Protected native worker lost encrypted directory")
    for name in names:
        child=root/name
        if (child.is_symlink() or not child.is_file() or
            not _efs_status(child)):
            raise PermissionError("Native protected worker source is not EFS-encrypted: "+name)
    return True
