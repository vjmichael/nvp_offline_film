"""W1-D source-only fixtures: durable PCM journal, original hashes and freeze links.

No fake microphone or native test is represented as physical device acceptance.
"""
from __future__ import annotations

from array import array
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.nvp_g06_chunked_capture import (
    CHUNK_SAMPLES, DurableOriginalChunkStore, FORMAT,
    _schema, long_capture_health, recording_member)
from backend.nvp_g09c_capture import _schema as capture_schema


class FakeStudio:
    def __init__(self,path):
        self.db_path=path


class FakeFilming:
    def __init__(self,path):
        self.path=path
    def _with(self,pid,scene_id,callback,mutate=False):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            return callback(db,None,{"scene_source_sha256":"approved"})


class DurableCaptureTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"original-film.sqlite"
        self.pid="a"*32
        self.sid="SC_"+"b"*12
        self.session="c"*32
        self.studio=FakeStudio(self.path)
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            db.execute("""CREATE TABLE g06_original_pcm(
                id TEXT PRIMARY KEY,project_id TEXT,scene_id TEXT,
                actor_id TEXT,source_kind TEXT,pcm BLOB,pcm_sha256 TEXT,
                sample_rate INTEGER,channels INTEGER,sample_count INTEGER,
                recorded_at TEXT)""")
            _schema(db)
            capture_schema(db)
            db.execute("""INSERT INTO g09c_capture_sessions(
                project_id,scene_id,session_id,actor_id,state,
                started_at,updated_at)
                VALUES (?,?,?,NULL,'recording','start','start')""",
                (self.pid,self.sid,self.session))

    def make_store(self):
        return DurableOriginalChunkStore(self.studio,self.session,
                                          self.pid,self.sid,None,"stage")

    def finish(self,parts):
        store=self.make_store()
        store.begin()
        joined=b"".join(parts)
        for i,part in enumerate(parts):
            store.push(part)
            if i%5==0: time.sleep(.02)  # Native callback cadence; no overflow
        result=store.finish_spooling(expected_samples=len(joined)//2)
        return store,joined,result

    def receipt(self,store,data):
        return {"format":"nvp.g09c.original_capture_audit.v1",
            "session_id":self.session,"project_id":self.pid,
            "scene_id":self.sid,"actor_id":None,
            "original_pcm_modified":False,
            "hardware_audio_to_picture_sync_proven":False,
            "sample_count":len(data)//2,
            "original_pcm_sha256":sha256(data).hexdigest()}

    def test_durable_offsets_and_full_source_reopen(self):
        part=bytes(array("h",[100,-100,50,0])*1200)
        store,all_bytes,status=self.finish([part]*101)
        self.assertEqual(status["sample_count"],len(all_bytes)//2)
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            rows=list(db.execute("""SELECT * FROM g06_long_capture_chunks
                WHERE session_id=? ORDER BY chunk_index""",(self.session,)))
            self.assertEqual(sum(r["sample_count"] for r in rows),
                             len(all_bytes)//2)
            self.assertEqual(b"".join(r["pcm"] for r in rows),all_bytes)
            self.assertEqual(rows[0]["start_sample"],0)
            self.assertEqual(rows[-1]["start_sample"]+
                             rows[-1]["sample_count"],len(all_bytes)//2)
            self.assertEqual(db.execute("""SELECT status FROM
                g06_long_capture_sessions WHERE session_id=?""",
                (self.session,)).fetchone()["status"],"stopped")

    def test_full_transactional_publish_and_immutable_manifest(self):
        payload=(bytes(array("h",[1,2,3,4])*1200))*1500
        # 150 seconds of real PCM-byte fixtures; split into <=120s originals.
        parts=[payload[n:n+48000*2]
            for n in range(0,len(payload),48000*2)]
        store,joined,_=self.finish(parts)
        with patch("backend.nvp_g06_chunked_capture._stage",
                   return_value=({"revision":1},
                       {"usd_sha256":"stage"},{"objects":[]},b"usd")):
            saved=store.publish(FakeFilming(self.path),
                                self.receipt(store,joined))
        self.assertEqual(len(saved["clip_ids"]),2)
        self.assertEqual(saved["sample_count"],len(joined)//2)
        self.assertEqual(saved["original_pcm_sha256"],sha256(joined).hexdigest())
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            original=b"".join(db.execute("""SELECT pcm FROM g06_original_pcm
                WHERE id=?""",(clip_id,)).fetchone()[0]
                for clip_id in saved["clip_ids"])
            self.assertEqual(original,joined)
            first=recording_member(db,self.pid,self.sid,saved["clip_ids"][0])
            second=recording_member(db,self.pid,self.sid,saved["clip_ids"][1])
            self.assertEqual(first["recording_source_start_sample"],0)
            self.assertEqual(second["recording_source_start_sample"],
                saved["segments"][0]["sample_count"])
            self.assertEqual(first["recording_manifest_sha256"],
                saved["manifest_sha256"])
            db.execute("""UPDATE g06_long_recording_manifests
                SET original_sha256=? WHERE recording_id=?""",
                ("0"*64,saved["recording_id"]))
            with self.assertRaises(RuntimeError):
                recording_member(db,self.pid,self.sid,saved["clip_ids"][0])

    def test_interrupted_staged_chunks_never_publish_themselves(self):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            db.execute("""INSERT INTO g06_long_capture_sessions(
                session_id,project_id,scene_id,actor_id,stage_sha256,
                status,started_at,updated_at)
                VALUES (?,?,?,NULL,'stage','recording','before','before')""",
                (self.session,self.pid,self.sid))
            rows=long_capture_health(db,self.pid,self.sid,active_ids=())
            self.assertEqual(rows[0]["status"],"interrupted")
            self.assertFalse(rows[0]["source_published"])
            self.assertTrue(rows[0]["requires_human_review"])
            self.assertEqual(db.execute(
                "SELECT count(*) FROM g06_original_pcm").fetchone()[0],0)

    def test_rejects_chunk_loss_or_wrong_stage_at_publish(self):
        store,pcm,_=self.finish([b"\x01\x00"*48000,
            b"\x01\x00"*6])
        with sqlite3.connect(self.path) as db:
            db.execute("""DELETE FROM g06_long_capture_chunks
                WHERE session_id=?""",(self.session,))
        with patch("backend.nvp_g06_chunked_capture._stage",
                   return_value=({"revision":1},
                       {"usd_sha256":"stage"},{"objects":[]},b"usd")):
            with self.assertRaises(RuntimeError):
                store.publish(FakeFilming(self.path),self.receipt(store,pcm))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM g06_original_pcm").fetchone()[0],0)


if __name__=="__main__":
    unittest.main()
