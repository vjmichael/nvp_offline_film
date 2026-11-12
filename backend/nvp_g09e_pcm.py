"""Immutable original PCM read in bounded, SHA-verified SQLite BLOB pages.

Ordinary G09-E renders only. This does not admit encrypted film files.
Each page is compared to a digest from a complete first-pass source audit;
no source media is rewritten or held entirely in application RAM.
"""
from __future__ import annotations

from array import array
from hashlib import sha256
from pathlib import Path
import sqlite3
import sys

PAGE_BYTES = 256 * 1024
MAX_READ_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 1_000_000_000


class VerifiedSQLitePCM:
    PAGE_BYTES = PAGE_BYTES

    def __init__(self, db_path, project_id, scene_id, source):
        path = Path(db_path)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Ordinary source PCM database is unavailable")
        self.path = path.resolve(strict=True)
        self.uri = self.path.as_uri() + "?mode=ro"
        self.project_id = project_id
        self.scene_id = scene_id
        self.clip_id = source["clip_id"]
        self.actor_id = source["actor_id"]
        self.expected_sha256 = source["pcm_sha256"]
        self.sample_count = source["sample_count"]
        self._cached_page = -1
        self._cached_bytes = b""
        self._page_hashes = ()
        self._size = 0
        self._rowid = None
        if (type(self.sample_count) is not int or
            not 1 <= self.sample_count * 2 <= MAX_SOURCE_BYTES or
            type(self.expected_sha256) is not str or
            len(self.expected_sha256) != 64):
            raise ValueError("Large original PCM exceeds bounded admission")
        db = self._connect()
        try:
            row = self._row(db)
            self._rowid, self._size = row[:2]
            if self._size != self.sample_count * 2:
                raise RuntimeError("Original sound sample count changed")
            digest, hashes = sha256(), []
            blob = db.blobopen("g06_original_pcm", "pcm", self._rowid,
                               readonly=True)
            try:
                for start in range(0, self._size, PAGE_BYTES):
                    expected = min(PAGE_BYTES, self._size - start)
                    page = blob.read(expected)
                    if len(page) != expected:
                        raise RuntimeError("Original PCM page could not be reopened")
                    digest.update(page)
                    hashes.append(sha256(page).digest())
            finally:
                blob.close()
            if digest.hexdigest() != self.expected_sha256:
                raise RuntimeError("Original microphone PCM failed its SHA audit")
            self._page_hashes = tuple(hashes)
        finally:
            db.close()

    def _connect(self):
        db = sqlite3.connect(self.uri, uri=True, timeout=10)
        db.execute("PRAGMA query_only=ON")
        return db

    def _row(self, db):
        row = db.execute("""SELECT rowid,length(pcm),actor_id,pcm_sha256,
            sample_rate,channels,sample_count,source_kind
            FROM g06_original_pcm WHERE project_id=? AND scene_id=?
            AND id=?""", (self.project_id,self.scene_id,self.clip_id)).fetchone()
        if (row is None or row[2] != self.actor_id or
            row[3] != self.expected_sha256 or row[4] != 48000 or
            row[5] != 1 or row[6] != self.sample_count or
            row[7] != "native_microphone_pcm16le"):
            raise RuntimeError("Original PCM is missing or was replaced")
        return row

    def __len__(self):
        return self._size

    @property
    def verified_sha256(self):
        return self.expected_sha256

    def _page(self, index):
        if self._cached_page != index:
            db = self._connect()
            try:
                row = self._row(db)
                if row[0] != self._rowid or row[1] != self._size:
                    raise RuntimeError("Original PCM row changed after review")
                blob = db.blobopen("g06_original_pcm","pcm",self._rowid,
                                   readonly=True)
                try:
                    blob.seek(index * PAGE_BYTES)
                    page = blob.read(min(PAGE_BYTES,
                                         self._size - index * PAGE_BYTES))
                finally:
                    blob.close()
            finally:
                db.close()
            if sha256(page).digest() != self._page_hashes[index]:
                raise RuntimeError("Original PCM page changed after verification")
            self._cached_page = index
            self._cached_bytes = page
        return self._cached_bytes

    def __getitem__(self, key):
        if not isinstance(key,slice):
            raise TypeError("Only bounded source PCM slices are permitted")
        start,stop,step = key.indices(self._size)
        if step != 1 or stop - start > MAX_READ_BYTES:
            raise ValueError("Source PCM read exceeds its bounded window")
        result = bytearray()
        while start < stop:
            page = start // PAGE_BYTES
            offset = start % PAGE_BYTES
            count = min(stop-start, PAGE_BYTES-offset)
            result.extend(self._page(page)[offset:offset+count])
            start += count
        return bytes(result)


def verified_pcm_digest(pcm):
    if isinstance(pcm,VerifiedSQLitePCM):
        return pcm.verified_sha256
    if not isinstance(pcm,bytes):
        raise TypeError("Unsupported original PCM representation")
    return sha256(pcm).hexdigest()


class WindowedVoiceSamples:
    """Original-source 100ms-max int16 sample windows for actor jaw RMS."""

    def __init__(self, pcm):
        if not isinstance(pcm,VerifiedSQLitePCM):
            raise TypeError("Original actor voice was not verified")
        self.pcm = pcm

    def __len__(self):
        return len(self.pcm)//2

    def __getitem__(self,key):
        if not isinstance(key,slice):
            raise TypeError("Voice analysis requires a bounded time range")
        start,stop,step = key.indices(len(self))
        if step != 1 or stop-start > 4800:
            raise ValueError("Voice RMS request exceeds 100ms")
        samples = array("h")
        samples.frombytes(self.pcm[start*2:stop*2])
        if sys.byteorder != "little":
            samples.byteswap()
        return samples
