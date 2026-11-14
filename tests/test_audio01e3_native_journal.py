"""AUDIO-01E.3: source-bound durable journal and stopped-worker recovery."""
import json
import sqlite3
from contextlib import closing
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from backend.nvp_audio01d_chunked_recovery import (
    RATE, _render_chunk, _validate, run_chunked_preview,
)
from backend.nvp_audio01e3_native_journal import AudioJobJournal


class AudioNativeJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.src=self.root/"source.wav"
        with wave.open(str(self.src),"wb") as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE)
            w.writeframes(struct.pack("<hh",1000,-1000)*RATE*3)
        self.sources={"voice":self.src}
        self.n=RATE*3
        self.plan={"stems":[{"stem_id":"voice","kind":"dialogue","clips":[{
            "out_start":0,"out_end":self.n,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":1000}]}]}
        self.work=self.root/"audio_work"
        self.db=self.root/"native_journal.sqlite3"
        self.j=AudioJobJournal(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def grant(self):
        return self.j.register("job1",self.plan,self.sources,self.n,self.work,
                               creator_event="approved",
                               verify_creator_action=lambda event,scope: event=="approved")

    def test_creator_permission_and_illegal_transition(self):
        with self.assertRaises(PermissionError):
            self.j.register("denied",self.plan,self.sources,self.n,self.work,
                            creator_event="denied",verify_creator_action=lambda *_:False)
        self.grant()
        self.assertEqual(self.j.read("job1")["state"],"approved")
        with self.assertRaises(RuntimeError):
            self.j.transition("job1",0,"completed","not_run")
        with self.assertRaises(sqlite3.IntegrityError):
            self.grant()

    def test_recover_after_verified_worker_stop_and_restart(self):
        self.grant()
        self.j.transition("job1",0,"running","worker_admitted")
        run_chunked_preview(self.plan,self.sources,self.n,self.work,max_new_chunks=1)
        stems=_validate(self.plan,self.sources,self.n)
        orphan=_render_chunk(stems,self.sources,RATE,2*RATE)[0]
        (self.work/"stem_voice_chunk_0000001.pcm").write_bytes(orphan)
        self.j.transition("job1",1,"recovery_required","worker_killed",
                          next_sample=RATE,cleanup_required=True)
        reopened=AudioJobJournal(self.db)
        with self.assertRaises(PermissionError):
            reopened.recover("job1",attest_stopped=lambda *_:False)
        self.assertEqual(reopened.read("job1")["state"],"recovery_required")
        done=reopened.recover("job1",attest_stopped=lambda *_:True)
        self.assertEqual(done["next_sample"],2*RATE)
        self.assertEqual(done["state"],"reconciled")
        self.assertEqual(reopened.read("job1")["requires_cleanup"],0)
        with self.assertRaises(RuntimeError):
            reopened.recover("job1",attest_stopped=lambda *_:True)
        run_chunked_preview(self.plan,self.sources,self.n,self.work)
        reopened.transition("job1",3,"completed","verified_audio",next_sample=self.n)
        self.assertEqual(reopened.read("job1")["state"],"completed")

    def test_reject_changed_authorized_source(self):
        self.grant()
        self.j.transition("job1",0,"recovery_required","crash")
        run_chunked_preview(self.plan,self.sources,self.n,self.work,max_new_chunks=1)
        with self.src.open("r+b") as f:
            f.seek(100);f.write(b"CHNG")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            self.j.recover("job1",attest_stopped=lambda *_:True)
        self.assertEqual(self.j.read("job1")["state"],"recovery_required")

    def test_stale_generation_and_persisted_events(self):
        self.grant()
        self.j.transition("job1",0,"running","start")
        with self.assertRaisesRegex(RuntimeError,"Stale"):
            self.j.transition("job1",0,"recovery_required","old_writer")
        self.j.transition("job1",1,"recovery_required","terminated",
                          cleanup_required=True)
        # sqlite3.Connection context managers commit but do not close.
        # Windows refuses TemporaryDirectory deletion with an open DB handle.
        with closing(sqlite3.connect(self.db)) as db:
            rows=db.execute("SELECT next_state FROM audio_native_events ORDER BY seq").fetchall()
        self.assertEqual([r[0] for r in rows],
                         ["approved","running","recovery_required"])


if __name__=="__main__":
    unittest.main()
