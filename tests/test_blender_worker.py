"""STACK-02A contract: pinned binary, confined files, durable state, tamper,
idempotency, cancellation, timeouts and safe interrupted-job recovery.
Real Blender execution is separately required in the native Actions lane.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import json
import os
import sys
import threading
import time
import unittest

from backend.nvp_blender_worker import (
    BlenderOperation, BlenderWorkerSupervisor, sha_file,
)


class MockProc:
    def __init__(self, code=0):
        self.pid=os.getpid()
        self.returncode=code
    def poll(self):
        return self.returncode
    def wait(self,timeout=None):
        return self.returncode


class BlenderWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)/"jobs"
        self.root.mkdir()
        self.executable=Path(sys.executable).resolve()
        self.sha=sha_file(self.executable)
        self.sup=self.make_supervisor()

    def tearDown(self):
        self.temp.cleanup()

    def make_supervisor(self):
        return BlenderWorkerSupervisor(
            self.root,blender_executable=self.executable,
            blender_sha256=self.sha,blender_version="Blender 5.2.3")

    def job(self,name="job_001"):
        directory=self.root/name
        directory.mkdir(exist_ok=True)
        (directory/"trusted.py").write_text("print('trusted blender script')\n","utf8")
        (directory/"source.json").write_text('{"source":"frozen_take","frame":1}',"utf8")
        return BlenderOperation(
            job_id=name,script="trusted.py",
            script_sha256=sha_file(directory/"trusted.py"),
            inputs={"source.json":sha_file(directory/"source.json")},
            outputs={"result.json":"json_audit","preview.png":"png"},
            arguments={"--manifest":"source.json","--audit":"result.json",
                       "--render":"preview.png"},timeout_seconds=3)

    def simulated_worker(self,command,**kwargs):
        cwd=Path(kwargs["cwd"])
        self.assertFalse(kwargs.get("shell",False))
        self.assertEqual(command[0],str(self.executable))
        self.assertIn("--python",command)
        self.assertIn("--manifest",command)
        self.assertIn("--audit",command)
        self.assertIn("--render",command)
        (cwd/"result.json").write_text('{"passed":true,"nvp":"verified"}',"utf8")
        (cwd/"preview.png").write_bytes(b"\x89PNG\r\n\x1a\n"+b"valid_measured_pixels")
        return MockProc()

    def test_no_arbitrary_worker_scripts_or_untrusted_relative_paths(self):
        op=self.job()
        malicious=BlenderOperation(**{**op.__dict__,"script":"../../evil.py"})
        with self.assertRaises(ValueError):
            self.sup.run(malicious)
        badarg=BlenderOperation(**{**op.__dict__,"arguments":{"--command":"rm -rf /"}})
        with self.assertRaises(ValueError):
            self.sup.run(badarg)
        forged=BlenderOperation(**{**op.__dict__,"script_sha256":"0"*64})
        with self.assertRaises(RuntimeError):
            self.sup.run(forged)
        changed=BlenderOperation(**{**op.__dict__,"inputs":{"source.json":"f"*64}})
        with self.assertRaises(RuntimeError):
            self.sup.run(changed)
        self.assertFalse((self.root/"worker_jobs.sqlite3").stat().st_size==0)

    def test_pinned_blender_hash_and_version_probe(self):
        with self.assertRaisesRegex(RuntimeError,"SHA-256 changed"):
            bad=BlenderWorkerSupervisor(self.root,
                blender_executable=self.executable,
                blender_sha256="a"*64,blender_version="Blender 5.2.3")
            bad.probe()
        with patch("backend.nvp_blender_worker.run_owned_subprocess",
                   return_value=SimpleNamespace(returncode=0,stdout="Blender 5.2.2\n")):
            with self.assertRaisesRegex(RuntimeError,"version differs"):
                self.sup.probe()
        with patch("backend.nvp_blender_worker.run_owned_subprocess",
                   return_value=SimpleNamespace(returncode=0,stdout="Blender 5.2.3\n")):
            self.assertEqual(self.sup.probe()["blender"],"Blender 5.2.3")

    def test_exact_success_reopen_tamper_and_idempotency_refusal(self):
        op=self.job()
        with patch.object(self.sup,"probe",return_value={"blender":"Blender 5.2.3"}),patch(
                "backend.nvp_blender_worker.launch_contained",side_effect=self.simulated_worker):
            result=self.sup.run(op)
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertEqual(result["exit_code"],0)
        self.assertEqual(set(result["outputs"]),set(op.outputs))
        self.assertEqual(self.make_supervisor().verify_completed(op.job_id)["state"],"SUCCEEDED")
        self.assertEqual([e["state"] for e in self.sup.events(op.job_id)],
                         ["PREPARED","RUNNING","SUCCEEDED"])
        with self.assertRaisesRegex(RuntimeError,"already registered"):
            self.sup.run(op)
        wrong=BlenderOperation(**{**op.__dict__,"timeout_seconds":4})
        with self.assertRaisesRegex(RuntimeError,"Idempotency ID reused"):
            # Existing outputs block replay before we reach the journal. In the
            # real system both protections exist; remove outputs only here.
            (self.root/op.job_id/"preview.png").unlink()
            (self.root/op.job_id/"result.json").unlink()
            with patch.object(self.sup,"probe",return_value={}):
                self.sup.run(wrong)
        # restore actual accepted outputs for the independent re-verification
        self.simulated_worker([str(self.executable),"--python","--manifest","--audit","--render"],
                              cwd=str(self.root/op.job_id),shell=False)
        with (self.root/op.job_id/"preview.png").open("ab") as dest:
            dest.write(b"tamper")
        with self.assertRaisesRegex(RuntimeError,"changed since"):
            self.make_supervisor().verify_completed(op.job_id)

    def test_recovery_never_falsely_marks_crashed_job_succeeded(self):
        op=self.job("interrupted_job")
        with patch.object(self.sup,"probe",return_value={}),patch(
                "backend.nvp_blender_worker.launch_contained",side_effect=self.simulated_worker):
            good=self.sup.run(op)
        self.assertEqual(good["state"],"SUCCEEDED")
        self.sup._transition(op.job_id,"RUNNING",worker_pid=99999)
        recovered=self.make_supervisor()
        self.assertEqual(recovered.recover_interrupted(),[op.job_id])
        status=recovered.inspect(op.job_id)
        self.assertEqual(status["state"],"INTERRUPTED")
        self.assertIn("orphan cleanup not proven",status["error"])
        with self.assertRaisesRegex(RuntimeError,"No successfully verified"):
            recovered.verify_completed(op.job_id)

    def test_invalid_worker_outputs_fail_closed(self):
        op=self.job("broken_output")
        def corrupted(cmd,**kwargs):
            root=Path(kwargs["cwd"])
            (root/"result.json").write_text('{"passed":false}',"utf8")
            (root/"preview.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            return MockProc()
        with patch.object(self.sup,"probe",return_value={}),patch(
            "backend.nvp_blender_worker.launch_contained",side_effect=corrupted):
            status=self.sup.run(op)
        self.assertEqual(status["state"],"FAILED")
        self.assertIn("passed=true",status["error"])
        self.assertIsNone(status["outputs"])

    def test_containment_cleanup_failure_never_commits_success(self):
        op=self.job("failed_guardian_cleanup")
        class FailedClose(MockProc):
            def close(self):
                raise RuntimeError("independent kernel guardian did not verify cleanup")
        def worker(cmd,**kwargs):
            self.simulated_worker(cmd,**kwargs)
            return FailedClose()
        with patch.object(self.sup,"probe",return_value={}),patch(
                "backend.nvp_blender_worker.launch_contained",side_effect=worker):
            result=self.sup.run(op)
        self.assertEqual(result["state"],"FAILED")
        self.assertIsNone(result["outputs"])
        self.assertIn("guardian did not verify cleanup",result["error"])
        with self.assertRaisesRegex(RuntimeError,"No successfully verified"):
            self.sup.verify_completed(op.job_id)

    def test_cancellation_reliably_stops_owned_process(self):
        op=self.job("cancelled_job")
        class Hung:
            pid=99999
            returncode=None
            def poll(self): return self.returncode
            def wait(self,timeout=None): return self.returncode
        proc=Hung()
        def terminate(p): p.returncode=-9
        outcome={}
        with patch.object(self.sup,"probe",return_value={}),patch(
             "backend.nvp_blender_worker.launch_contained",return_value=proc),patch.object(
             self.sup,"_terminate_tree",side_effect=terminate):
            thread=threading.Thread(target=lambda: outcome.update(result=self.sup.run(op)))
            thread.start()
            try:
                ready=False
                for _ in range(200):
                    try:
                        ready=self.sup.inspect(op.job_id)["state"]=="RUNNING"
                    except KeyError:
                        ready=False
                    if ready: break
                    time.sleep(.02)
                self.assertTrue(ready,"Worker never entered RUNNING")
                self.assertTrue(self.sup.cancel(op.job_id))
            finally:
                thread.join(timeout=8)
            self.assertFalse(thread.is_alive())
            self.assertEqual(outcome["result"]["state"],"CANCELLED")
            self.assertEqual(outcome["result"]["exit_code"],-9)
            self.assertNotIn(op.job_id,self.sup._running)


if __name__=="__main__":
    unittest.main()
