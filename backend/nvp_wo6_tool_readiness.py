"""WO6-03: read-only real native tool/license availability inventory.

The trusted host, NOT a model/JS request, supplies exact absolute
installation root and expected binary/LICENSE SHA256 pins. This probes
the local files afresh on every authorized read; it never uses PATH,
downloads/installs/executes the binary, runs shell commands or grants
tool execution. A hash match is not evidence of functional execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

FORMAT="nvp.wo6.native_tool_readiness.v1"
_ID=re.compile(r"nvp\.[a-z0-9_.-]{1,75}\Z")
_SHA=re.compile(r"[0-9a-f]{64}\Z")
MAX_TOOLS=24
MAX_FILE_BYTES=1024*1024*1024

@dataclass(frozen=True)
class TrustedNativeToolPin:
    tool_id: str
    executable: str
    executable_sha256: str
    license_notice: str
    license_sha256: str
    version_label: str

    def __post_init__(self):
        if (type(self.tool_id) is not str or not _ID.fullmatch(self.tool_id)
                or self.tool_id.startswith("nvp.ffmpeg")
                or any(type(x) is not str or not _SHA.fullmatch(x)
                       for x in (self.executable_sha256,self.license_sha256))
                or type(self.version_label) is not str
                or not 1<=len(self.version_label)<=80):
            raise ValueError("Trusted native tool identity/hash metadata invalid")
        for value in (self.executable,self.license_notice):
            # Relative POSIX-style manifest paths only, no drive prefixes,
            # traversal, UNC, wildcards or hidden control characters.
            if (type(value) is not str or not 1<=len(value)<=160
                    or "\\" in value or ":" in value
                    or any(ord(c)<32 for c in value)):
                raise ValueError("Unsafe native bundle-relative tool path")
            p=PurePosixPath(value)
            if p.is_absolute() or any(part in (".","..")
                                      for part in value.split("/")):
                raise ValueError("Unsafe native tool path traversal")
        if self.executable == self.license_notice:
            raise ValueError("Codec and license must be separate assets")


@dataclass(frozen=True)
class TrustedToolInventory:
    root: Path
    pins: tuple[TrustedNativeToolPin,...]

    def __post_init__(self):
        if not isinstance(self.root,Path) or not self.root.is_absolute():
            raise ValueError("Trusted native tool root must be an absolute Path")
        if (type(self.pins) is not tuple or not 1<=len(self.pins)<=MAX_TOOLS
                or any(not isinstance(x,TrustedNativeToolPin)
                       for x in self.pins)):
            raise TypeError("Host-owned native tool pins required")
        ids=[x.tool_id for x in self.pins]
        if len(ids)!=len(set(ids)):
            raise ValueError("Repeated trusted native tool IDs")


def _native_path(root:Path,relative:str)->Path:
    path=root.joinpath(*relative.split("/"))
    # Do not follow symlinks/reparse points in the source path. No user
    # directory or PATH lookup is permitted to turn a trusted pin into a
    # different executable between probes.
    cur=root
    if root.is_symlink():
        raise PermissionError("Native tool directory is an untrusted link")
    for name in relative.split("/"):
        cur=cur/name
        if cur.is_symlink():
            raise PermissionError("Native bundle contains a symbolic link")
    if path.resolve(strict=False).is_relative_to(root.resolve(strict=False)) is False:
        raise PermissionError("Native bundle path escaped its trusted root")
    return path


def _hashed_file(path:Path):
    if not path.exists() or not path.is_file():
        return None
    stat=path.stat()
    if not 0<stat.st_size<=MAX_FILE_BYTES:
        return "TOO_LARGE_OR_EMPTY"
    meta=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)
    digest=sha256()
    with path.open("rb") as stream:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:
                break
            digest.update(chunk)
    after=path.stat()
    if meta!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
        return "CHANGED_DURING_PROBE"
    return digest.hexdigest()


def preflight_tool_inventory(inventory:TrustedToolInventory)->dict:
    if not isinstance(inventory,TrustedToolInventory):
        raise TypeError("Native host must supply exact trusted tool inventory")
    root=inventory.root
    if root.is_symlink():
        raise PermissionError("Trusted tool installation root cannot be a link")
    result=[]
    for pin in inventory.pins:
        exe=_native_path(root,pin.executable)
        notice=_native_path(root,pin.license_notice)
        executable_hash=_hashed_file(exe)
        license_hash=_hashed_file(notice)
        state=(
            "MISSING" if executable_hash is None else
            "CHANGED_DURING_PROBE" if executable_hash=="CHANGED_DURING_PROBE" else
            "INVALID_BINARY" if executable_hash=="TOO_LARGE_OR_EMPTY" else
            "BINARY_SHA_MISMATCH" if executable_hash!=pin.executable_sha256 else
            "LICENSE_MISSING" if license_hash is None else
            "LICENSE_INVALID" if license_hash in
                ("TOO_LARGE_OR_EMPTY","CHANGED_DURING_PROBE") else
            "LICENSE_SHA_MISMATCH" if license_hash!=pin.license_sha256 else
            "SHA_AND_LICENSE_VERIFIED_NOT_EXECUTED")
        result.append({
            "tool_id":pin.tool_id,
            "version_from_trusted_pin_not_probed":pin.version_label,
            "status":state,
            "verified_binary_sha256":(
                executable_hash if executable_hash==pin.executable_sha256 else None),
            "verified_license_sha256":(
                license_hash if license_hash==pin.license_sha256 else None),
            "binary_and_notice_on_disk_verified":
                state=="SHA_AND_LICENSE_VERIFIED_NOT_EXECUTED",
            "runtime_executed_and_usable_verified":False,
            "authorized_to_run":False,
            "file_paths_disclosed_to_model":False,
        })
    return {
        "format":FORMAT,
        "tool_count":len(result),
        "tools":result,
        "source":"HOST_PINNED_LOCAL_FILE_PROBE_NOT_A_MODEL_ASSERTION",
        "all_pins_verified":all(x["binary_and_notice_on_disk_verified"]
                                for x in result),
        "runtime_execution_verified":False,
        "operation_authorization_granted":False,
        "side_effects_performed":False,
    }
