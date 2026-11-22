"""Real AUDIO-01E.3 Windows Job Object / Linux process-group termination.

These tests launch the genuine AUDIO worker using NativeAudioHost and the
existing B14 ApprovedTaskBindings, TaskLedger, launch_contained, wait_guarded.
No fake worker objects. A test-only child holds after writing its first chunk.
"""
from __future__ import annotations
import os
import struct
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch
from pathlib import Path

from backend.nvp_audio01d_chunked_recovery import RATE, _read_state
from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


class ActualAudioContainment(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.old_env=os.environ.get("NVP_NATIVE_TERMINATION_TEST")
        os.environ["NVP_NATIVE_TERMINATION_TEST"]="1"
        self.critical=False

        def sample():
            # Deterministic test sensor for the REAL supervisor: when critical,
            # memory is too low for the existing resource watchdog.
            available=512 if self.critical else 12000
            return ResourceSnapshot(0,16000,available,0.0,tuple())
        self.ledger=TaskLedger(self.root/"ledger",sampler=sample)
        self.host=NativeAudioHost(self.ledger,self.root/"native",
                                  verify_creator_action=lambda event,scope:
                                  event=="creator_confirmed" and
                                  scope["final_master"] is False,
                                  strict_linux_tree=False)
        self.src=self.root/"dialogue.wav"
        self.n=RATE*3
        with wave.open(str(self.src),"wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(struct.pack("<hh",1000,-1000)*self.n)
        self.plan={"stems":[{"stem_id":"voice","kind":"dialogue","clips":[{
            "out_start":0,"out_end":self.n,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":1000}]}]}

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("NVP_NATIVE_TERMINATION_TEST",None)
        else:
            os.environ["NVP_NATIVE_TERMINATION_TEST"]=self.old_env
        self.tmp.cleanup()

    def prepare(self):
        grant=self.host.stage_and_approve(self.plan,{"voice":self.src},self.n,
                      self.root/"rendered","creator_confirmed",ram_mb=1024,
                      duration_s=3600)
        return grant["job_id"]

    def started(self,job):
        marker=self.root/"native"/job/"test_worker_ready"
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if marker.exists() and job in self.host._running:
                return self.host._running[job]
            time.sleep(.05)
        raise AssertionError("Actual contained audio child never reached first chunk")

    def run_background(self):
        result={}
        def task():
            try:
                result["value"]=self.host.run_next(timeout_seconds=45,test_hold=True)
            except BaseException as exc:
                result["error"]=exc
        thread=threading.Thread(target=task,daemon=True)
        thread.start()
        return thread,result

    def test_real_os_terminate_tree_then_durable_recovery(self):
        job=self.prepare()
        thread,result=self.run_background()
        proc=self.started(job)
        self.assertIsNone(proc.poll())
        pid=proc.pid
        self.assertGreater(pid,0)
        proc.terminate_tree()  # ACTUAL OS process termination, not mock!
        thread.join(timeout=30)
        self.assertFalse(thread.is_alive(),"Native host hung after worker kill")
        self.assertIn("error",result)
        self.assertEqual(self.ledger.get_task(job)["state"],"INTERRUPTED")
        self.assertEqual(self.host.journal.read(job)["state"],"recovery_required")
        state=_read_state(self.root/"rendered")
        self.assertGreaterEqual(state["next_sample"],RATE)
        # Rebuild the trusted host to prove a persisted OS-stop receipt,
        # rather than relying on a stale in-memory worker handle.
        restarted=NativeAudioHost(self.ledger,self.root/"native",
                verify_creator_action=lambda event,scope: event=="creator_confirmed"
                and scope["final_master"] is False,
                strict_linux_tree=False)
        recovered=restarted.recover_stopped(job)
        self.assertEqual(recovered["state"],"reconciled")
        self.assertGreaterEqual(recovered["next_sample"],RATE)
        with self.ledger._db() as db:
            witness=db.execute("SELECT worker_reaped FROM audio_native_os_stop_receipts WHERE job_id=?",
                               (job,)).fetchone()
        self.assertEqual(witness,(1,))

    def test_reconciled_job_requires_new_authorized_native_attempt(self):
        job=self.prepare()
        thread,result=self.run_background()
        process=self.started(job)
        process.terminate_tree()
        thread.join(timeout=30)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.ledger.get_task(job)["state"],"INTERRUPTED")
        restarted=NativeAudioHost(self.ledger,self.root/"native",
            verify_creator_action=lambda event,scope:
            event=="creator_confirmed" and scope["final_master"] is False,
            strict_linux_tree=False)
        proof=restarted.recover_stopped(job)
        self.assertEqual(proof["state"],"reconciled")
        first=(self.root/"rendered"/"mix_chunk_0000000.pcm").read_bytes()
        resumed=restarted.stage_and_approve(
            self.plan,{"voice":self.src},self.n,self.root/"rendered",
            "creator_confirmed",ram_mb=1024,duration_s=3600,resume_from=job)
        self.assertNotEqual(resumed["job_id"],job)
        with self.assertRaises(RuntimeError):
            restarted.stage_and_approve(
                self.plan,{"voice":self.src},self.n,self.root/"rendered",
                "creator_confirmed",ram_mb=1024,duration_s=3600,resume_from=job)
        final=restarted.run_next(timeout_seconds=40)
        self.assertEqual(final["state"],"SUCCEEDED")
        self.assertEqual(final["job_id"],resumed["job_id"])
        self.assertEqual(self.ledger.get_task(resumed["job_id"])["state"],"SUCCEEDED")
        self.assertEqual(self.ledger.get_task(job)["state"],"INTERRUPTED")
        self.assertEqual(first,(self.root/"rendered"/"mix_chunk_0000000.pcm").read_bytes())
        self.assertEqual(restarted.journal.read(resumed["job_id"])["state"],"completed")

    def test_resource_watchdog_kills_real_contained_audio_child(self):
        job=self.prepare()
        thread,result=self.run_background()
        proc=self.started(job)
        self.assertIsNone(proc.poll())
        self.critical=True  # real wait_guarded reads critical_pressure
        thread.join(timeout=30)
        self.assertFalse(thread.is_alive(),"Watchdog did not terminate native audio")
        self.assertIn("error",result)
        self.assertIsNotNone(proc.poll())
        self.assertEqual(self.ledger.get_task(job)["state"],"INTERRUPTED")
        self.assertEqual(self.host.journal.read(job)["state"],"recovery_required")

    def test_verified_worker_exit_then_host_verifier_failure_is_recoverable(self):
        job=self.prepare()
        # Worker genuinely runs, exits, is reaped, and the Windows process
        # handle is closed before host-side verification fault injection.
        with patch("backend.nvp_audio01e3_native_host.verify_chunked_preview",
                   side_effect=RuntimeError("forced post-exit proof failure")):
            with self.assertRaisesRegex(RuntimeError,"forced post-exit proof failure"):
                self.host.run_next(timeout_seconds=40)
        self.assertEqual(self.ledger.get_task(job)["state"],"INTERRUPTED")
        self.assertEqual(self.host.journal.read(job)["state"],"recovery_required")
        with self.ledger._db() as db:
            stopped=db.execute("""SELECT worker_reaped FROM audio_native_os_stop_receipts
                                  WHERE job_id=?""",(job,)).fetchone()
        self.assertEqual(stopped,(1,))
        # This assertion would previously crash on Windows because the
        # exception handler tried to poll a closed PROCESS handle.
        self.assertNotIn(job,self.host._running)

    def test_real_child_normal_completion_verified(self):
        job=self.prepare()
        result=self.host.run_next(timeout_seconds=40)
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertEqual(self.ledger.get_task(job)["state"],"SUCCEEDED")
        self.assertEqual(self.host.journal.read(job)["state"],"completed")
        self.assertTrue((self.root/"rendered"/"checkpoint.json").exists())


if __name__=="__main__":
    unittest.main()
