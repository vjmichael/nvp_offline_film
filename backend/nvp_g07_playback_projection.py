"""Small host-private index of one previously verified playback selection.

The original SQLite snapshot is still one AEAD object. A warm request hashes
its exact ciphertext and every external metadata dependency before using the
index. It does not deserialize it or repeat the full cut/decision/receipt walk.
No timestamp-based trust, persistent plaintext, original media or key caching.
"""
import hashlib
import hmac
import os
import stat
from pathlib import Path
from backend.nvp_g03_windows_vault import VaultError, _no_link, _authenticated_reads
from backend.nvp_g03_live_store import MAX_DB_BYTES

MAX_PROJECTED_BYTES = 4 * 1024 * 1024
INVENTORY_PAGES = 4
MAX_INVENTORY_BYTES = 256 * 1024
MAX_DEPENDENCIES = 4096
MAX_DEPENDENCY_BYTES = 64 * 1024 * 1024
BLOCK = 256 * 1024


class Dependencies:
    def __init__(self, folder, pid):
        self.folder, self.pid = folder, pid
        self.files = {}
        self.bytes = 0
        self.valid = True

    def observe(self, path, pid, size, sha):
        if not self.valid:
            return
        try:
            rel = Path(path).relative_to(self.folder)
        except ValueError:
            self.valid = False
            return
        # Only existing immutable metadata stores are understood. Any future
        # additional encrypted dependency forces the ordinary full read.
        if (pid != self.pid or len(rel.parts) != 3 or
                rel.parts[0] not in ('editorial-pages', 'protected-objects') or
                rel.parts[-1] != 'body.nvpsealed'):
            self.valid = False
            return
        name = rel.as_posix()
        old = self.files.get(name)
        if old is not None:
            if old != (size, sha):
                raise VaultError('Protected metadata changed during review')
            return
        self.bytes += size
        if len(self.files) >= MAX_DEPENDENCIES or self.bytes > MAX_DEPENDENCY_BYTES:
            self.valid = False
            self.files.clear()
            return
        self.files[name] = (size, sha)

    def collect(self, action):
        token = _authenticated_reads.set(self.observe)
        try:
            return action()
        finally:
            _authenticated_reads.reset(token)


def _hash(folder, rel, limit, expected, guard, *, size=None):
    # Preserve the path and directory restrictions of the metadata readers.
    # Authenticate the actual open descriptor, not an mtime/size shortcut.
    path = folder
    _no_link(path)
    for name in Path(rel).parts:
        path = path / name
        info = _no_link(path)
    if not stat.S_ISREG(info.st_mode):
        raise VaultError('Protected metadata is not a file')
    if rel.startswith('protected-objects/') and (info.st_nlink != 1 or
            {p.name for p in path.parent.iterdir()} != {'body.nvpsealed'}):
        raise VaultError('Unexpected protected metadata entries')
    h = hashlib.sha256()
    with path.open('rb') as file:
        opened = os.fstat(file.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(info, opened):
            raise VaultError('Protected metadata path changed')
        length = opened.st_size
        if not 0 < length <= limit or (size is not None and length != size):
            raise VaultError('Protected metadata size changed')
        remaining = length
        while remaining:
            guard()
            block = file.read(min(BLOCK, remaining))
            if not block:
                raise VaultError('Protected metadata truncated')
            h.update(block)
            remaining -= len(block)
        if (file.read(1) or not hmac.compare_digest(h.hexdigest(), expected) or
                not os.path.samestat(opened, _no_link(path))):
            raise VaultError('Protected metadata ciphertext changed')


class Projection:
    def __init__(self, scope, head, spec, done, parts, dependencies, bytes_used):
        self.scope, self.head = scope, dict(head)
        self.spec, self.done = spec, done
        self.parts = tuple(parts)
        self.dependencies = tuple(dependencies.files.items())
        self.bytes_used = bytes_used

    def row(self, part):
        return {'state': 'verified', 'receipt': self.parts[part]}

    def verify(self, store, folder, guard):
        if store._head(folder) != self.head:
            raise VaultError('Movie snapshot changed during playback')
        _hash(folder, 'revisions/' + self.head['name'], MAX_DB_BYTES + 64,
              self.head['sha256'], guard)
        for rel, (size, sha) in self.dependencies:
            guard()
            _hash(folder, rel, size, sha, guard, size=size)
        if store._head(folder) != self.head:
            raise VaultError('Movie snapshot changed during playback')
        guard()


def verify_snapshot(store, folder, head, guard):
    if store._head(folder) != head:
        raise VaultError('Movie snapshot changed during inventory retrieval')
    _hash(folder, 'revisions/' + head['name'], MAX_DB_BYTES + 64,
          head['sha256'], guard)
    if store._head(folder) != head:
        raise VaultError('Movie snapshot changed during inventory retrieval')
    guard()
