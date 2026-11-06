"""AUDIO E.7 native admission outbox: crash before/after queue commit."""
import hashlib
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_audio_native_staging_lock import AudioStagingLock
from backend.nvp_approved_tasks import canonical_bytes


class DurableAdmissionOutbox(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        def sample():
            return ResourceSnapshot(0,16000,12000,0.0,tuple())
        self.ledger=TaskLedger(self.root/"ledger",sampler=sample)
        self.policy=lambda event,scope: event=="approved" and scope["final_master"] is False
        self.host=NativeAudioHost(self.ledger,self.root/"native",
            verify_creator_action=self.policy,strict_linux_tree=False)
        self.source=self.root/"voice.wav"
        with wave.open(str(self.source),"wb") as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(48000)
            out.writeframes(struct.pack("<hh",200,-200)*48000)
        self.plan={"stems":[{"stem_id":"voice","kind":"dialogue","clips":[{
            "out_start":0,"out_end":48000,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":1000}]}]}

    def tearDown(self):
        self.temp.cleanup()

    def restart(self):
        return NativeAudioHost(self.ledger,self.root/"native",
            verify_creator_action=self.policy,strict_linux_tree=False)

    def prepare_crash(self,side_effect):
        with patch.object(self.host.binding,"enqueue",side_effect=side_effect):
            with self.assertRaisesRegex(RuntimeError,"simulated crash"):
                self.host.stage_and_approve(self.plan,{"voice":self.source},48000,
                    self.root/"result","approved")
        with self.ledger._db() as db:
            row=db.execute("""SELECT job_id,state FROM audio_native_admission_outbox""").fetchone()
        self.assertEqual(row[1],"pending")
        return row[0]

    def test_crash_before_queue_commit_then_requeue(self):
        job=self.prepare_crash(RuntimeError("simulated crash before queue"))
        self.assertIsNone(self.ledger.get_task(job))
        restored=self.restart()
        reply=restored.reconcile_admission_outbox(job)
        self.assertEqual(reply["status"],"VERIFIED_QUEUED")
        self.assertEqual(self.ledger.get_task(job)["state"],"QUEUED")
        self.assertEqual(restored.reconcile_admission_outbox(job)["status"],"VERIFIED_QUEUED")
        with self.ledger._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks WHERE id=?",
                                        (job,)).fetchone()[0],1)

    def test_crash_after_queue_commit_then_mark_once(self):
        genuine=self.host.binding.enqueue
        def queue_then_die(*args,**kwargs):
            genuine(*args,**kwargs)
            raise RuntimeError("simulated crash after queue commit")
        job=self.prepare_crash(queue_then_die)
        self.assertEqual(self.ledger.get_task(job)["state"],"QUEUED")
        restored=self.restart()
        reply=restored.reconcile_admission_outbox(job)
        self.assertEqual(reply["status"],"VERIFIED_QUEUED")
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT state FROM audio_native_admission_outbox WHERE job_id=?",
                (job,)).fetchone()[0],"enqueued")
        self.assertEqual(restored.reconcile_admission_outbox(job)["status"],"VERIFIED_QUEUED")

    def test_revoked_creator_blocks_recovery(self):
        job=self.prepare_crash(RuntimeError("simulated crash before queue"))
        restored=NativeAudioHost(self.ledger,self.root/"native",
            verify_creator_action=lambda *_:False,strict_linux_tree=False)
        with self.assertRaises(PermissionError):
            restored.reconcile_admission_outbox(job)
        self.assertIsNone(self.ledger.get_task(job))

    def test_changed_sealed_plan_blocks_recovery(self):
        job=self.prepare_crash(RuntimeError("simulated crash before queue"))
        plan=self.root/"native"/job/"worker_plan.json"
        plan.write_bytes(plan.read_bytes()+b"!")
        with self.assertRaises(PermissionError):
            self.restart().reconcile_admission_outbox(job)
        self.assertIsNone(self.ledger.get_task(job))


if __name__=="__main__":
    unittest.main()
