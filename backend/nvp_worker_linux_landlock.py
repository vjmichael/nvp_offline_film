"""P1-A Linux producer write confinement: restrict writes before exec.

Every untrusted ADC child runs in a delegated private cgroup. Even a valid
cgroup.kill is inadequate if the child can write an ancestor cgroup.procs and
migrate before cancellation. Landlock denies writes outside its original PCM
spool (and the genuine /dev/snd device nodes). No unsupported-kernel fallback.
The independent guardian remains outside this restriction.
"""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import sys

SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

WRITE_FILE = 1 << 1
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
MAKE_SYM = 1 << 12
REFER = 1 << 13
TRUNCATE = 1 << 14


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs",ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [("allowed_access",ctypes.c_uint64),
                ("parent_fd",ctypes.c_int32)]


def _call(libc, nr, *args):
    result = libc.syscall(nr, *args)
    if result < 0:
        value = ctypes.get_errno()
        raise OSError(value, os.strerror(value))
    return result


def restrict_native_producer_writes(spool):
    """Install irreversible kernel path-write rules for a reviewed worker.

    Does not grant filesystem permissions; it only subtracts authority. If the
    kernel lacks Landlock or cannot apply the rules, the child NEVER executes
    the recording worker.
    """
    if sys.platform != "linux":
        raise RuntimeError("Linux Landlock producer policy requires Linux")
    source = Path(spool)
    if (not source.is_absolute() or source.is_symlink() or
        not source.is_dir() or not source.name.startswith("nvp-live-original-")):
        raise PermissionError("Expected host-owned original recording spool")
    source = source.resolve(strict=True)
    libc = ctypes.CDLL(None, use_errno=True)
    abi = _call(libc, SYS_LANDLOCK_CREATE_RULESET,
                ctypes.c_void_p(), ctypes.c_size_t(0),
                ctypes.c_uint(LANDLOCK_CREATE_RULESET_VERSION))
    if abi < 1:
        raise RuntimeError("Kernel cannot enforce producer Landlock write restrictions")
    handled = (WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_CHAR |
               MAKE_DIR | MAKE_REG | MAKE_SOCK | MAKE_FIFO |
               MAKE_BLOCK | MAKE_SYM)
    if abi >= 2:
        handled |= REFER
    if abi >= 3:
        handled |= TRUNCATE
    rules = RulesetAttr(handled)
    rulefd = _call(libc, SYS_LANDLOCK_CREATE_RULESET,
                   ctypes.byref(rules), ctypes.c_size_t(ctypes.sizeof(rules)),
                   ctypes.c_uint(0))
    try:
        def permit(directory, access):
            fd = os.open(str(directory), os.O_PATH | os.O_CLOEXEC)
            try:
                attr = PathBeneathAttr(access, fd)
                _call(libc, SYS_LANDLOCK_ADD_RULE,
                      ctypes.c_int(rulefd), ctypes.c_int(LANDLOCK_RULE_PATH_BENEATH),
                      ctypes.byref(attr), ctypes.c_uint(0))
            finally:
                os.close(fd)
        permit(source, handled)
        # Python subprocess.DEVNULL uses O_RDWR even for a child whose
        # streams are discarded. Native kernel regression demonstrated that
        # omitting this exact character node blocks detached descendants.
        # Do NOT allow the entire /dev tree, which would widen authority.
        if Path("/dev/null").is_char_device():
            permit(Path("/dev/null"), WRITE_FILE)
        # ALSA/Pulse backends need native OS sound device handles, not the
        # ability to mutate system configuration or any ancestor cgroup.
        sound_devices = Path("/dev/snd")
        if sound_devices.is_dir() and not sound_devices.is_symlink():
            permit(sound_devices, WRITE_FILE)
        _call(libc, 157, ctypes.c_int(PR_SET_NO_NEW_PRIVS),
              ctypes.c_ulong(1), ctypes.c_ulong(0),
              ctypes.c_ulong(0), ctypes.c_ulong(0))
        _call(libc, SYS_LANDLOCK_RESTRICT_SELF,
              ctypes.c_int(rulefd), ctypes.c_uint(0))
    finally:
        os.close(rulefd)
    return {"scope":"linux-landlock-write-spool-v1",
            "abi":abi, "ancestor_cgroup_writes_allowed":False}
