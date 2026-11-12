"""Source-only Wave 1 PCM integrity tests; no model, renderer or OS device."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.nvp_g09e_pcm import (
    PAGE_BYTES,VerifiedSQLitePCM,WindowedVoiceSamples,
    verified_pcm_digest)


class BoundedOriginalPCMTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"film.sqlite"
        self.source=(b"\x00\x01\xfe\xff"*(PAGE_BYTES//4+77))
        self.digest=hashlib.sha256(self.source).hexdigest()
        self.metadata={"clip_id":"clip","actor_id":"actor",
            "sample_count":len(self.source)//2,"pcm_sha256":self.digest}
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE g06_original_pcm(
                id TEXT,project_id TEXT,scene_id TEXT,actor_id TEXT,
                source_kind TEXT,pcm BLOB,pcm_sha256 TEXT,
                sample_rate INTEGER,channels INTEGER,sample_count INTEGER)""")
            db.execute("""INSERT INTO g06_original_pcm VALUES(
                'clip','project','scene','actor','native_microphone_pcm16le',
                ?,?,48000,1,?)""",
                (self.source,self.digest,len(self.source)//2))

    def source_pcm(self,**revisions):
        metadata=dict(self.metadata)
        metadata.update(revisions)
        return VerifiedSQLitePCM(self.path,"project","scene",metadata)

    def test_cross_page_and_original_digest(self):
        source=self.source_pcm()
        self.assertEqual(len(source),len(self.source))
        self.assertEqual(verified_pcm_digest(source),self.digest)
        self.assertEqual(source[PAGE_BYTES-7:PAGE_BYTES+9],
            self.source[PAGE_BYTES-7:PAGE_BYTES+9])
        self.assertEqual(source[:100],self.source[:100])
        with self.assertRaises(TypeError):
            _=source[0]
        with self.assertRaises(ValueError):
            _=source[0:100:2]

    def test_foreign_source_or_tampered_digest_refused(self):
        with self.assertRaises(RuntimeError):
            self.source_pcm(actor_id="other")
        with self.assertRaises(RuntimeError):
            self.source_pcm(pcm_sha256="f"*64)

    def test_original_mutation_after_audit_refused(self):
        source=self.source_pcm()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE g06_original_pcm SET pcm=? WHERE id='clip'",
                (b"\x7f"+self.source[1:],))
        with self.assertRaises(RuntimeError):
            _=source[:2]

    def test_cached_pcm_page_rechecks_mutation_after_bounded_window(self):
        from unittest.mock import patch
        source=self.source_pcm()
        self.assertEqual(source[:2],self.source[:2])
        # A source mutation cannot become a permanent cached-page bypass.
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE g06_original_pcm SET pcm=? WHERE id='clip'",
                (b"\x7f"+self.source[1:],))
        with patch("backend.nvp_g09e_pcm.time.monotonic_ns",
                   return_value=source._cache_checked_ns+101_000_000):
            with self.assertRaises(RuntimeError):
                _=source[:2]

    def test_actual_over_64_mib_original_is_page_addressable(self):
        size=64*1024*1024+2
        zero_page=b"\x00"*PAGE_BYTES
        check=hashlib.sha256()
        for _ in range(size//PAGE_BYTES):
            check.update(zero_page)
        check.update(b"\x00"*(size%PAGE_BYTES))
        digest=check.hexdigest()
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE g06_original_pcm
                SET pcm=zeroblob(?),pcm_sha256=?,sample_count=?
                WHERE id='clip'""",(size,digest,size//2))
        pcm=self.source_pcm(sample_count=size//2,pcm_sha256=digest)
        self.assertEqual(len(pcm),size)
        self.assertEqual(pcm[size-2:size],b"\x00\x00")
        self.assertEqual(pcm[PAGE_BYTES-2:PAGE_BYTES+2],b"\x00"*4)

    def test_voice_rms_reads_only_short_verified_window(self):
        source=self.source_pcm()
        voice=WindowedVoiceSamples(source)
        self.assertEqual(len(voice),len(self.source)//2)
        self.assertEqual(len(voice[200:1160]),960)
        with self.assertRaises(ValueError):
            _=voice[0:4801]


if __name__=="__main__":
    unittest.main()
