"""Release-only immutable codec provisioning. Never invoked by WebView/worker.

The caller supplies an independently approved pin, not a hash derived from a
runtime manifest. Windows provisioning requires elevation and private machine
ACLs. Old pin directories are never overwritten, moved or deleted.
"""
from pathlib import Path
from hashlib import sha256
import json
import os
import re
import secrets
import stat

PIN = re.compile(r"[0-9a-f]{64}\Z")
FORMAT = "nvp.wo3.native_codec_bundle_provenance.v1"
ROSTER = {
    "openjpeg-encoder": ("OpenJPEG", "BSD-2-Clause", "opj_compress.exe", "openjpeg.BSD-2-Clause.LICENSE"),
    "openjpeg-decoder": ("OpenJPEG", "BSD-2-Clause", "opj_decompress.exe", "openjpeg.BSD-2-Clause.LICENSE"),
    "asdcp-wrap": ("asdcplib", "BSD-3-Clause", "asdcp-wrap.exe", "asdcplib.BSD-3-Clause.LICENSE"),
    "asdcp-info": ("asdcplib", "BSD-3-Clause", "asdcp-info.exe", "asdcplib.BSD-3-Clause.LICENSE"),
    "asdcp-unwrap": ("asdcplib", "BSD-3-Clause", "asdcp-unwrap.exe", "asdcplib.BSD-3-Clause.LICENSE"),
}
MANIFEST = "nvp-codec-manifest.json"


def require_pin(pin):
    if type(pin) is not str or not PIN.fullmatch(pin):
        raise PermissionError("Independent release codec SHA-256 required")
    return pin


def _plain(path, directory=False):
    path = Path(path)
    if not path.is_absolute() or any(part in ("..", ".") for part in path.parts):
        raise PermissionError("Exact absolute codec path required")
    for p in (path, *path.parents):
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
            raise PermissionError("Linked or reparse codec path refused")
    if directory and not path.is_dir() or not directory and not path.is_file():
        raise PermissionError("Unexpected codec file type")
    return path


def _digest_file(path, minimum, maximum):
    path = _plain(path)
    h = sha256()
    size = 0
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            size += len(block)
            if size > maximum:
                raise PermissionError("Codec payload exceeds bound")
            h.update(block)
    if size < minimum:
        raise PermissionError("Codec payload is truncated")
    return h.hexdigest()


def verify_payload(root, pin):
    """Pure integrity check, not proof of signed provenance or codec execution."""
    require_pin(pin)
    root = _plain(root, directory=True)
    path = _plain(root / MANIFEST)
    with path.open("rb") as f:
        raw = f.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024 or sha256(raw).hexdigest() != pin:
        raise PermissionError("Codec manifest does not match approved release")
    manifest = json.loads(raw)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if raw != canonical or type(manifest) is not dict or set(manifest) != {"format", "tools"} or manifest["format"] != FORMAT:
        raise PermissionError("Invalid canonical codec manifest")
    tools = manifest["tools"]
    if type(tools) is not dict or set(tools) != set(ROSTER):
        raise PermissionError("Exact five-tool codec roster required")
    files = {MANIFEST: (pin, 1, 128 * 1024)}
    for role, (product, license_id, name, notice) in ROSTER.items():
        item = tools[role]
        if (type(item) is not dict or set(item) != {"product", "license", "filename", "sha256", "license_notice", "license_sha256"}
                or (item["product"], item["license"], item["filename"], item["license_notice"]) != (product, license_id, name, notice)):
            raise PermissionError("Unexpected codec role, filename or notice")
        for leaf, digest, low, high in ((name, item["sha256"], 256, 256 * 1024 * 1024), (notice, item["license_sha256"], 200, 128 * 1024)):
            entry = (require_pin(digest), low, high)
            if leaf in files and files[leaf] != entry:
                raise PermissionError("Inconsistent shared notice digest")
            files[leaf] = entry
    if {p.name for p in root.iterdir()} != set(files):
        raise PermissionError("Unmanifested or missing codec payload")
    for leaf, (digest, low, high) in files.items():
        if _digest_file(root / leaf, low, high) != digest:
            raise PermissionError("Codec or license bytes changed")
    return files


def _copy_verified(source, stage, files):
    for leaf, (digest, low, high) in files.items():
        src = _plain(source / leaf)
        h = sha256()
        size = 0
        with src.open("rb") as inp, (stage / leaf).open("xb") as out:
            while block := inp.read(1024 * 1024):
                size += len(block)
                if size > high:
                    raise PermissionError("Codec copy exceeds approved bound")
                h.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        if size < low or h.hexdigest() != digest:
            raise PermissionError("Codec copy differs from approved bytes")


def provision_immutable(source, pin, root, *, mkdir_secure, check_secure, seal_new_file):
    """Internal host-only transaction core; no runtime callers or elevation."""
    require_pin(pin)
    source = _plain(source, directory=True)
    root = _plain(root, directory=True)
    check_secure(root)
    files = verify_payload(source, pin)
    target = root / pin
    if target.exists() or target.is_symlink():
        check_secure(target)
        verify_payload(target, pin)
        for leaf in files:
            check_secure(target / leaf)
        return target
    stage = root / (".pending-" + pin + "-" + secrets.token_hex(12))
    mkdir_secure(stage)
    check_secure(stage)
    _copy_verified(source, stage, files)
    verify_payload(stage, pin)
    for leaf in files:
        seal_new_file(stage / leaf)
        check_secure(stage / leaf)
    check_secure(root)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Concurrent codec provision; no replacement authorized")
    # On Windows os.rename fails if the destination already exists. An
    # interrupted stage is retained as evidence, never admitted by the host.
    os.rename(stage, target)
    check_secure(target)
    verify_payload(target, pin)
    return target


class _MachineACL:
    """Fixed Windows machine boundary; never rewrite an existing directory ACL."""
    def __init__(self):
        if os.name != "nt":
            raise PermissionError("Windows machine codec custody required")
        import winreg
        import win32security
        import win32file
        import pywintypes
        self.security = win32security
        self.winfile = win32file
        self.pytypes = pywintypes
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            program = Path(winreg.QueryValueEx(key, "ProgramFilesDir")[0])
        self.program = _plain(program, directory=True)
        self.app = self.program / "NVP"
        self.root = self.app / "native-codecs"
        self.admins = {"S-1-5-18", "S-1-5-32-544"}
        # Public codec binaries may be read/executed by a normal zero-capability
        # AppContainer; protected media never receives this ACE. Parent folders
        # receive traverse-only package access, never inherited package reads.
        base = "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;GRGX;;;BU)"
        self.parent_descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            base + "(A;;GX;;;AC)", 1)
        self.descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            base + "(A;OICI;GRGX;;;AC)", 1)

    def check(self, path, *, package_read=False, package_traverse=False):
        path = _plain(path, directory=Path(path).is_dir())
        sec = self.security
        desc = sec.GetNamedSecurityInfo(str(path), sec.SE_FILE_OBJECT,
                                        sec.OWNER_SECURITY_INFORMATION | sec.DACL_SECURITY_INFORMATION)
        owner = sec.ConvertSidToStringSid(desc.GetSecurityDescriptorOwner())
        dacl = desc.GetSecurityDescriptorDacl()
        control, _ = desc.GetSecurityDescriptorControl()
        if owner not in self.admins or dacl is None or not control & 0x1000:
            raise PermissionError("Codec path lacks trusted machine owner/DACL")
        writers = set()
        package_mask = 0
        # DELETE, WRITE_DAC, WRITE_OWNER, write/append data, attributes,
        # extended attributes, delete child, generic write/all.
        write_mask = 0x500D0156
        for i in range(dacl.GetAceCount()):
            header, mask, sid = dacl.GetAce(i)
            kind, flags = header
            identity = sec.ConvertSidToStringSid(sid)
            if kind != 0 or flags & 0x08:
                raise PermissionError("Unknown or inherit-only codec ACL entry")
            if identity not in self.admins and mask & ~0xA01200A9:
                raise PermissionError("Nonadministrative codec write authority")
            if mask & write_mask:
                writers.add(identity)
            if identity == "S-1-15-2-1":
                package_mask |= mask
        if writers != self.admins:
            raise PermissionError("Codec ACL does not admit both trusted machine owners")
        execute = bool(package_mask & 0x20000000 or package_mask & 0x20)
        read = bool(package_mask & 0x80000000 or package_mask & 0x01)
        if (package_read or package_traverse) and not execute or package_read and not read:
            raise PermissionError("Pre-provisioned AppContainer codec read/execute ACL absent")

    def mkdir(self, path):
        attrs = self.pytypes.SECURITY_ATTRIBUTES()
        attrs.SECURITY_DESCRIPTOR = (self.descriptor if path.parent == self.root
                                     else self.parent_descriptor)
        self.winfile.CreateDirectory(str(path), attrs)
        self.check(path)

    def seal_file(self, path):
        path = _plain(path)
        sec = self.security
        sec.SetNamedSecurityInfo(str(path), sec.SE_FILE_OBJECT,
            sec.OWNER_SECURITY_INFORMATION | sec.DACL_SECURITY_INFORMATION | 0x80000000,
            self.descriptor.GetSecurityDescriptorOwner(), None,
            self.descriptor.GetSecurityDescriptorDacl(), None)

    def ensure_root(self):
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise PermissionError("Explicit elevated machine installation required")
        for path in (self.app, self.root):
            try:
                self.check(path)
            except FileNotFoundError:
                self.mkdir(path)
        return self.root


def check_installed(pin):
    """Runtime check of fixed machine path; no creation, elevation or repair."""
    require_pin(pin)
    acl = _MachineACL()
    acl.check(acl.app, package_traverse=True)
    acl.check(acl.root, package_traverse=True)
    target = acl.root / pin
    acl.check(target, package_read=True)
    for leaf in verify_payload(target, pin):
        acl.check(target / leaf, package_read=True)
    return target


def require_machine_codec_scope(roots, files, executable, *, pin, compiled_pin, frozen):
    """Only a frozen host's exact public codec release avoids mutable code ACLs."""
    require_pin(pin)
    if frozen is not True or pin != compiled_pin:
        raise PermissionError("No independent installed codec release authority")
    root = check_installed(pin)
    exe = Path(executable)
    names = {row[2] for row in ROSTER.values()}
    if tuple(roots) != (root,) or files or exe.parent != root or exe.name not in names:
        raise PermissionError("Machine codec access cannot authorize any other code or media")
    return root


def provision_machine(source, pin):
    """Only a trusted elevated release operator may invoke this entry point."""
    require_pin(pin)
    acl = _MachineACL()
    root = acl.ensure_root()
    ingress = acl.app / "codec-payloads"
    if Path(source) != ingress / pin:
        raise PermissionError("Only trusted machine-approved codec ingress is accepted")
    acl.check(ingress)
    acl.check(source)
    for leaf in verify_payload(source, pin):
        acl.check(Path(source) / leaf)
    provision_immutable(source, pin, root, mkdir_secure=acl.mkdir,
                        check_secure=acl.check, seal_new_file=acl.seal_file)
    return check_installed(pin)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-pin", required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    target = provision_machine(args.payload, args.approved_pin)
    print(json.dumps({"status": "MACHINE_CODEC_PAYLOAD_VERIFIED", "pin": target.name,
                      "native_playback_accepted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
