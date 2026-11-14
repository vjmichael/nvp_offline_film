"""AUDIO-01E.8 never-admitted SQLite journal crash recovery tests."""
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot


class JournalOnlyCrashTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.ledger=TaskLedger(self.root/"ledger",
            sampler=lambda:ResourceSnapshot(0,16000,12000,0,tuple()))
        self.host=NativeAudioHost(self.ledger,self.root/"host",
            verify_creator_action=lambda *_:True,strict_linux_tree=False)
        self.wav=self.root/"voice.wav"
        with wave.open(str(self.wav),"wb") as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
            w.writeframes(struct.pack("<hh",20,-20)*48000)
        self.plan={"stems":[{"stem_id":"voice","kind":"dialogue","clips":[{
            "out_start":0,"out_end":48000,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":1000}]}]}
        self.job="journalonly1"
        self.target=self.root/"rendered"
        self.host.journal.register(self.job,self.plan,{"voice":self.wav},
            48000,self.target,verify_creator_action=lambda *_:True,
            creator_event="approved")

    def tearDown(self):
        self.temp.cleanup()

    def test_close_intent_before_grant_without_synthesizing_worker(self):
        restarted=NativeAudioHost(self.ledger,self.root/"host",
            verify_creator_action=lambda *_:True,strict_linux_tree=False)
        result=restarted.reconcile_journal_only(self.job)
        self.assertEqual(result["state"],"failed")
        self.assertEqual(restarted.journal.read(self.job)["state"],"failed")
        self.assertIsNone(self.ledger.get_task(self.job))
        with self.ledger._db() as db:
            self.assertIsNone(db.execute(
                "SELECT * FROM audio_native_os_stop_receipts WHERE job_id=?",
                (self.job,)).fetchone())
        with self.assertRaises(RuntimeError):
            restarted.reconcile_journal_only(self.job)

    def test_existing_output_is_not_considered_never_started(self):
        self.target.mkdir()
        with self.assertRaisesRegex(RuntimeError,"unverified downstream"):
            self.host.reconcile_journal_only(self.job)
        self.assertEqual(self.host.journal.read(self.job)["state"],"approved")

    def test_existing_lease_blocks_unverified_cleanup(self):
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO audio_native_staging_leases
                (directory,job_id,predecessor) VALUES(?,?,NULL)""",
                (str(self.target.absolute()),self.job))
            db.commit()
        with self.assertRaisesRegex(RuntimeError,"unverified downstream"):
            self.host.reconcile_journal_only(self.job)


if __name__=="__main__":
    unittest.main()
