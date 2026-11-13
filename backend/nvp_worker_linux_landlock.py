"""SEC-06 Linux kernel Landlock write boundary for strict cgroup workers.

The supervisor owns the delegated ancestor and remains outside the worker
leaf. Without a second kernel boundary a same-UID descendant can write the
systemd host subgroup's cgroup.procs and escape cgroup.kill. Before exec,
apply an inherited Landlock ruleset that permits write-open/truncate ONLY
inside the reviewed worker cwd. Writes to cgroup.procs are kernel-denied,
even if the delegated host's UID owns that cgroup.

Unsupported ABI, syscall denial or untrusted workdir => fail closed;
no uncontained Python fallback, no path filtering based on string arguments.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform


WRITE_FILE = 1 << 1
TRUNCATE = 1 << 14
CREATE_RULESET_VERSION = 1 << 0
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
SUPPORTED_ARCH = {"x86_64", "aarch64", "riscv64"}


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
        ("reserved", ctypes.c_uint32),
    ]


def restrict_strict_worker_writes(cwd: Path) -> None:
    """Inherit kernel write restrictions through exec and descendants."""
    machine = platform.machine()
    if machine not in SUPPORTED_ARCH:
        raise RuntimeError("SEC-06 Landlock architecture not admitted")
    directory = Path(cwd).resolve(strict=True)
    cgroot = Path("/sys/fs/cgroup").resolve(strict=True)
    if (not directory.is_dir() or directory == Path("/") or
        directory.is_relative_to(cgroot) or cgroot.is_relative_to(directory)):
        raise RuntimeError("SEC-06 worker directory cannot include cgroup mount")

    libc = ctypes.CDLL(None, use_errno=True)
    syscall = libc.syscall
    syscall.restype = ctypes.c_long

    def checked(number, *args):
        result = syscall(ctypes.c_long(number), *args)
        if result == -1:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return int(result)

    try:
        abi = checked(444, ctypes.c_void_p(0), ctypes.c_size_t(0),
                      ctypes.c_uint(CREATE_RULESET_VERSION))
        if abi < 1:
            raise RuntimeError("SEC-06 kernel lacks Landlock ABI")
        rights = WRITE_FILE | (TRUNCATE if abi >= 3 else 0)
        policy = RulesetAttr(rights)
        fd = checked(444, ctypes.byref(policy), ctypes.c_size_t(ctypes.sizeof(policy)),
                     ctypes.c_uint(0))
        try:
            source = os.open(directory, os.O_PATH | os.O_CLOEXEC)
            try:
                permitted = PathBeneathAttr(rights, source, 0)
                checked(445, ctypes.c_int(fd), ctypes.c_int(RULE_PATH_BENEATH),
                        ctypes.byref(permitted), ctypes.c_uint(0))
            finally:
                os.close(source)
            if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                errno = ctypes.get_errno()
                raise OSError(errno, os.strerror(errno))
            checked(446, ctypes.c_int(fd), ctypes.c_uint(0))
        finally:
            os.close(fd)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("SEC-06 kernel Landlock ancestor-migration boundary unavailable") from exc
    # Native file producers should use their explicitly admitted job root,
    # never a host /tmp or home-directory spool outside kernel policy.
    os.environ["TMPDIR"] = str(directory)
    os.environ["TMP"] = str(directory)
    os.environ["TEMP"] = str(directory)
    os.environ["XDG_CACHE_HOME"] = str(directory / ".nvp-cache")
    os.environ["XDG_CONFIG_HOME"] = str(directory / ".nvp-config")
