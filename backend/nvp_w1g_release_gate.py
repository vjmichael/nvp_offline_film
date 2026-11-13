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


# The kernel automatically drops process lifetime locks on host death. Durable
# ORIGINAL launch journals are a SEPARATE release barrier: stale RUNNING or
# PREPARED workers cannot be promoted based on an empty PID list or free lock.
def release_process_journal_root():
    root=release_gate_path().parent/"original-process-journals"
    if root.is_symlink():
        raise RuntimeError("Original Windows launch journal root cannot be linked")
    root.mkdir(exist_ok=True)
    return root


class OriginalWindowsLaunchJournal:
    """Per-worker, original source-bound durable admission state."""

    def __init__(self,command):
        if os.name!="nt":
            raise RuntimeError("Native Windows original launch journal required")
        import secrets
        import hashlib
        import json
        self.root=release_process_journal_root()
        self.token="nvpjob_"+secrets.token_hex(16)
        self.path=self.root/(self.token+".json")
        self._record={
            "format":"nvp.w1g.original_windows_job_journal.v1",
            "job_id":self.token,
            "command_sha256":hashlib.sha256(json.dumps(
                command,separators=(",",":"),ensure_ascii=True
            ).encode("ascii")).hexdigest(),
            "state":"PREPARED",
            "process_tree_custody_verified":False,
            "worker_exit_verified":False,
        }
        self._save()

    def _save(self):
        import json
        temp=self.path.with_suffix(".new")
        if (temp.exists() or temp.is_symlink() or
            self.path.is_symlink()):
            raise RuntimeError("Original process journal is linked or interrupted")
        with temp.open("x",encoding="utf8") as f:
            json.dump(self._record,f,sort_keys=True,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.replace(temp,self.path)

    def started(self,pid):
        if self._record["state"]!="PREPARED" or type(pid) is not int or pid<1:
            raise RuntimeError("Original process start transition is invalid")
        self._record["pid_diagnostic_only"]=pid
        self._record["state"]="RUNNING"
        self._save()

    def verified_tree_reaped(self):
        if self._record["state"]!="RUNNING":
            raise RuntimeError("Original Job reaping lacks a running kernel identity")
        self._record["state"]="TREE_REAPED_VERIFIED"
        self._record["process_tree_custody_verified"]=True
        self._record["worker_exit_verified"]=True
        self._save()


def inspect_original_process_journals():
    """Read-only release check; NEVER auto-reconcile a crashed worker."""
    import json
    root=release_process_journal_root()
    rows=sorted(root.iterdir())
    if len(rows)>50000:
        raise PermissionError("Unbounded original process recovery journal topology")
    count=0
    for path in rows:
        if (path.is_symlink() or not path.is_file() or
            path.suffix!=".json" or
            not path.name.startswith("nvpjob_") or
            path.stat().st_size>2048):
            raise PermissionError("Untrusted original Windows process recovery entry")
        entry=json.loads(path.read_text("utf8"))
        if (entry.get("format")!="nvp.w1g.original_windows_job_journal.v1" or
            entry.get("job_id")!=path.stem or
            type(entry.get("command_sha256")) is not str or
            len(entry["command_sha256"])!=64 or
            entry.get("state")!="TREE_REAPED_VERIFIED" or
            entry.get("process_tree_custody_verified") is not True or
            entry.get("worker_exit_verified") is not True):
            raise PermissionError(
                "Original Windows native launch remains interrupted or unverified: "+path.stem)
        count+=1
    return {"original_windows_launch_journals_verified":count,
            "unresolved_original_native_launches":0}
