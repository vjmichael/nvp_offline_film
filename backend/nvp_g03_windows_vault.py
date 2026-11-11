"""G03 Windows encrypted *archive* for film-original source files.

This is an explicit, non-destructive offline archive, NOT transparent encryption
of NVP's live SQLite/OpenUSD/PCM storage. The archive is sealed under an
AES-256-GCM content key wrapped with Windows current-user DPAPI and
passphrase-derived optional entropy. Neither key nor passphrase is written to
the archive. Fail closed on non-Windows hosts; no fallback to fake DPAPI.

Do NOT call this module from movie-lock API as if locking encrypted the movie.
Until native readers, SQLite/WAL, assets, logs, Takes and backups have a common
host-authorized encrypted storage layer, full project confidentiality is OPEN.
"""
from __future__ import annotations

import base64
from contextlib import suppress
import hashlib
import hmac
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import sys
import tempfile

MAGIC = b"NVPFILM1\0"
FORMAT = "nvp.g03.windows_encrypted_source_archive.v1"
PROJECT_ID = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_FILES = 100_000
READ_SIZE = 512 * 1024
NONCE_BYTES = 12
TAG_BYTES = 16


class VaultError(Exception):
    """A denied, incomplete or unauthenticated archive operation."""


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.exceptions import InvalidTag
        return Cipher, algorithms, modes, InvalidTag
    except ImportError as exc:
        raise VaultError("Vetted AES-GCM dependency is not installed") from exc


def _dpapi():
    if sys.platform != "win32":
        raise VaultError("Windows user-scoped DPAPI is mandatory; no fallback")
    try:
        import win32crypt
        return win32crypt
    except ImportError as exc:
        raise VaultError("Windows DPAPI pywin32 binding is unavailable") from exc


def _project(project_id):
    if type(project_id) is not str or not PROJECT_ID.fullmatch(project_id):
        raise VaultError("Invalid film project identity")
    return project_id


def _relative(value):
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise VaultError("Unsafe source asset name")
    p = PurePosixPath(value)
    if (p.is_absolute() or any(x in {"", ".", ".."} for x in p.parts) or
            p.as_posix() != value or ":" in value):
        raise VaultError("Unsafe source asset path")
    return p


def _no_link(path: Path):
    # Reject symbolic links and Windows reparse/junction redirects. Test both
    # each path and each parent as the directory tree is traversed.
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (
            info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            if hasattr(info, "st_file_attributes") else False):
        raise VaultError("Symlink or reparse source denied: " + path.name)
    return info


def _source_files(root: Path):
    if not root.is_dir():
        raise VaultError("Source directory is missing")
    _no_link(root)
    count = 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        files.sort()
        parent = Path(folder)
        _no_link(parent)
        for dirname in dirs:
            child = parent / dirname
            if not stat.S_ISDIR(_no_link(child).st_mode):
                raise VaultError("Source tree has a non-directory component")
        for filename in files:
            file = parent / filename
            info = _no_link(file)
            if not stat.S_ISREG(info.st_mode):
                raise VaultError("Only regular source files may be sealed")
            name = file.relative_to(root).as_posix()
            _relative(name)
            count += 1
            if count > MAX_FILES:
                raise VaultError("Film archive exceeds file-count bound")
            yield name, file, info


def _aad(project_id: str, name: str):
    return json.dumps([FORMAT, project_id, name], ensure_ascii=True,
                      separators=(",", ":")).encode("utf8")


def _token(path: str, key: bytes):
    return hmac.new(key, ("asset:" + path).encode("utf8"),
                    hashlib.sha256).hexdigest()


def _fsync_folder(path: Path):
    # Windows flushes file contents; directory fsync is unavailable.
    if sys.platform != "win32":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _encrypt_file(input_file, destination: Path, *, key: bytes,
                  project_id: str, name: str):
    Cipher, algorithms, modes, _ = _crypto()
    nonce = secrets.token_bytes(NONCE_BYTES)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(_aad(project_id, name))
    checksum = hashlib.sha256()
    length = 0
    with destination.open("xb") as out:
        out.write(MAGIC + nonce)
        while True:
            data = input_file.read(READ_SIZE)
            if not data:
                break
            length += len(data)
            checksum.update(data)
            out.write(encryptor.update(data))
        out.write(encryptor.finalize())
        out.write(encryptor.tag)
        out.flush()
        os.fsync(out.fileno())
    return {"sha256": checksum.hexdigest(), "size_bytes": length}


def _decrypt_file(path: Path, output_file, *, key: bytes,
                  project_id: str, name: str):
    Cipher, algorithms, modes, InvalidTag = _crypto()
    length = path.stat().st_size
    if length < len(MAGIC) + NONCE_BYTES + TAG_BYTES:
        raise VaultError("Truncated source archive")
    with path.open("rb") as inp:
        header = inp.read(len(MAGIC) + NONCE_BYTES)
        if header[:len(MAGIC)] != MAGIC:
            raise VaultError("Unknown encrypted source archive version")
        inp.seek(length - TAG_BYTES)
        tag = inp.read(TAG_BYTES)
        inp.seek(len(header))
        decryptor = Cipher(
            algorithms.AES(key), modes.GCM(header[len(MAGIC):], tag)
        ).decryptor()
        decryptor.authenticate_additional_data(_aad(project_id, name))
        checksum = hashlib.sha256()
        count = 0
        left = length - len(header) - TAG_BYTES
        while left:
            block = inp.read(min(READ_SIZE, left))
            if not block:
                raise VaultError("Unexpected encrypted archive EOF")
            left -= len(block)
            plain = decryptor.update(block)
            checksum.update(plain)
            count += len(plain)
            output_file.write(plain)
        try:
            decryptor.finalize()
        except InvalidTag as exc:
            raise VaultError("Encrypted source failed authentication") from exc
    return {"sha256": checksum.hexdigest(), "size_bytes": count}


def _entropy(passphrase: str, salt: bytes, project_id: str):
    if type(passphrase) is not str or not 12 <= len(passphrase) <= 256:
        raise VaultError("Movie passphrase must contain 12–256 characters")
    return hashlib.scrypt(passphrase.encode("utf8"),
                          salt=salt + bytes.fromhex(project_id),
                          n=2**14, r=8, p=1, dklen=32)


def _key_create(passphrase: str, project_id: str):
    dpapi = _dpapi()
    salt = secrets.token_bytes(16)
    key = secrets.token_bytes(32)
    binding = _entropy(passphrase, salt, project_id)
    wrapped = dpapi.CryptProtectData(
        key, "NVP project source archive", binding, None, None, 0)
    return key, {"format": FORMAT, "project_id": project_id,
                 "salt": base64.b64encode(salt).decode("ascii"),
                 "wrapped_key": base64.b64encode(wrapped).decode("ascii"),
                 "scope": "current-Windows-user+passphrase",
                 "complete_active_project_encryption": False}


def _key_open(passphrase, project_id, metadata):
    dpapi = _dpapi()
    if (type(metadata) is not dict or metadata.get("format") != FORMAT or
            metadata.get("project_id") != project_id or
            metadata.get("scope") != "current-Windows-user+passphrase" or
            metadata.get("complete_active_project_encryption") is not False):
        raise VaultError("Invalid or foreign Windows film key metadata")
    try:
        salt = base64.b64decode(metadata["salt"], validate=True)
        blob = base64.b64decode(metadata["wrapped_key"], validate=True)
        if len(salt) != 16 or not blob or len(blob) > 8192:
            raise ValueError("Invalid DPAPI metadata length")
        binding = _entropy(passphrase, salt, project_id)
        _, key = dpapi.CryptUnprotectData(blob, binding, None, None, 0)
        if len(key) != 32:
            raise ValueError("Invalid unwrapped AES-256 key")
        return key
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise VaultError("Unable to unlock this Windows-account film archive") from exc
    except Exception as exc:
        # DPAPI errors deliberately do not reveal whether the password,
        # Windows user identity or protected ciphertext was incorrect.
        raise VaultError("Unable to unlock this Windows-account film archive") from exc


def _metadata(dirpath: Path):
    path = dirpath / "key.nvpdpapi"
    if not path.is_file():
        raise VaultError("Film vault has no host-protected key")
    if path.stat().st_size > 16_384:
        raise VaultError("Oversized Windows key record")
    try:
        return json.loads(path.read_text("utf8"))
    except (ValueError, UnicodeError) as exc:
        raise VaultError("Unreadable Windows key record") from exc


def _sealed_manifest(dirpath: Path, project_id: str, key: bytes):
    manifest = io.BytesIO()
    _decrypt_file(dirpath / "manifest.nvpsealed", manifest, key=key,
                  project_id=project_id, name="__manifest__")
    try:
        value = json.loads(manifest.getvalue())
    except (UnicodeError, ValueError) as exc:
        raise VaultError("Encrypted film manifest invalid") from exc
    if (type(value) is not dict or value.get("format") != FORMAT or
            value.get("project_id") != project_id or
            type(value.get("entries")) is not list or
            len(value["entries"]) > MAX_FILES):
        raise VaultError("Invalid encrypted film source manifest")
    seen = set()
    for entry in value["entries"]:
        if (type(entry) is not dict or set(entry) !=
                {"name", "token", "sha256", "size_bytes"}):
            raise VaultError("Invalid encrypted manifest entry")
        name = str(_relative(entry["name"]))
        if name in seen or entry["token"] != _token(name, key):
            raise VaultError("Duplicated or altered archive entry")
        if (not SHA.fullmatch(entry["sha256"]) or
                type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0):
            raise VaultError("Invalid encrypted source checksum/size")
        seen.add(name)
    return value


def create_archive(project_id: str, source_root, destination,
                   passphrase: str):
    """Seal a NEW archive and independently verify *every* encrypted source.

    Source files remain untouched. NEVER present archive creation as erasure
    or protection of the still-plaintext working database and film assets.
    """
    project_id = _project(project_id)
    root = Path(source_root).absolute()
    dest = Path(destination).absolute()
    _dpapi()
    _crypto()
    if not root.is_dir() or dest.exists():
        raise VaultError("Archive needs an existing source and fresh destination")
    if dest == root or root in dest.parents:
        raise VaultError("Archive must be outside original source tree")
    if dest.parent == root or not dest.parent.is_dir():
        raise VaultError("Archive needs an independent existing parent")
    _no_link(root)
    stage = Path(tempfile.mkdtemp(prefix=".nvp-vault-staging-",
                                  dir=dest.parent))
    try:
        key, meta = _key_create(passphrase, project_id)
        entries = []
        source_witnesses = []
        for name, path, initial in _source_files(root):
            opaque = _token(name, key)
            ciphertext = stage / (opaque + ".nvpsealed")
            with path.open("rb") as inp:
                witness = _encrypt_file(
                    inp, ciphertext, key=key, project_id=project_id, name=name)
            after = _no_link(path)
            if (initial.st_size != after.st_size or
                initial.st_mtime_ns != after.st_mtime_ns):
                raise VaultError("Original source changed during archive")
            # Real independent authenticated ciphertext readback, no
            # temporary decrypted file written to disk for verification.
            verify = _decrypt_file(ciphertext, io.BytesIO() if witness[
                "size_bytes"] < 4 * READ_SIZE else _DigestWriter(),
                key=key, project_id=project_id, name=name)
            if verify != witness:
                raise VaultError("Encrypted asset failed independent readback")
            entries.append({"name":name, "token":opaque, **witness})
            source_witnesses.append((name, path, witness))
        manifest = {"format":FORMAT,"project_id":project_id,
                    "entries":entries,"source_files":len(entries)}
        raw = json.dumps(manifest, sort_keys=True,
                         separators=(",", ":")).encode("utf8")
        _encrypt_file(io.BytesIO(raw), stage / "manifest.nvpsealed",
                      key=key, project_id=project_id, name="__manifest__")
        with (stage / "key.nvpdpapi").open("x", encoding="utf8") as f:
            json.dump(meta, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        _fsync_folder(stage)
        # Check the complete manifest and every authenticated original
        # without relying on plaintext names being visible in the vault.
        verify_archive(project_id, stage, passphrase)
        # Recheck *every* original at the moment of archive promotion, not
        # merely just after its initial individual encryption. A concurrent
        # filmmaker edit later in a long archive must invalidate the package.
        for name, original, expected in source_witnesses:
            if not stat.S_ISREG(_no_link(original).st_mode):
                raise VaultError("Original source changed while archiving")
            checksum = hashlib.sha256()
            with original.open("rb") as check:
                size = 0
                while True:
                    piece = check.read(READ_SIZE)
                    if not piece: break
                    checksum.update(piece)
                    size += len(piece)
            if (size != expected["size_bytes"] or
                    checksum.hexdigest() != expected["sha256"]):
                raise VaultError("Original source changed while archiving")
        if dest.exists():
            raise VaultError("Archive destination was created concurrently")
        os.replace(stage, dest)
        _fsync_folder(dest.parent)
        return {"status":"sealed_archive_verified","project_id":project_id,
                "source_files":len(entries),"originals_modified":False,
                "working_files_encrypted":False,
                "archive_path":str(dest)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


class _DigestWriter:
    def write(self, data):
        # Verification does not need a plaintext file nor accumulated bytes.
        pass


def verify_archive(project_id: str, archive_root, passphrase: str):
    project_id = _project(project_id)
    directory = Path(archive_root)
    _no_link(directory)
    key = _key_open(passphrase, project_id, _metadata(directory))
    manifest = _sealed_manifest(directory, project_id, key)
    for entry in manifest["entries"]:
        name = entry["name"]
        source = directory / (entry["token"] + ".nvpsealed")
        _no_link(source)
        actual = _decrypt_file(source, _DigestWriter(), key=key,
                               project_id=project_id, name=name)
        if actual != {k:entry[k] for k in ("sha256","size_bytes")}:
            raise VaultError("Original source digest mismatch in archive")
    return {"status":"sealed_archive_verified",
            "project_id":project_id,"source_files":len(manifest["entries"]),
            "working_files_encrypted":False}


def restore_archive(project_id: str, archive_root, output_root, passphrase: str):
    """Restore to a NEW directory only; no overwrite and no implicit unlock."""
    project_id = _project(project_id)
    directory = Path(archive_root).absolute()
    output = Path(output_root).absolute()
    if output.exists() or output.parent == directory or directory in output.parents:
        raise VaultError("Restore must be a fresh, separate output directory")
    if not output.parent.is_dir():
        raise VaultError("Restore parent is absent")
    key = _key_open(passphrase, project_id, _metadata(directory))
    manifest = _sealed_manifest(directory, project_id, key)
    stage = Path(tempfile.mkdtemp(prefix=".nvp-restore-staging-",
                                  dir=output.parent))
    try:
        for entry in manifest["entries"]:
            name = entry["name"]
            candidate = stage.joinpath(*_relative(name).parts)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            actual_path = directory / (entry["token"] + ".nvpsealed")
            _no_link(actual_path)
            with candidate.open("xb") as out:
                witness = _decrypt_file(
                    actual_path, out, key=key, project_id=project_id, name=name)
                out.flush()
                os.fsync(out.fileno())
            if witness != {k:entry[k] for k in ("sha256","size_bytes")}:
                raise VaultError("Restored original digest mismatch")
        if output.exists():
            raise VaultError("Concurrent restore destination")
        os.replace(stage, output)
        _fsync_folder(output.parent)
        return {"status":"restored_and_verified","project_id":project_id,
                "source_files":len(manifest["entries"]),
                "restored_to":str(output)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)
