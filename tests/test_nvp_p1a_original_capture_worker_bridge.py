"""P1-A original microphone to compiled native worker contract tests.

These are deliberately MOCKED proof-boundary tests. They never substitute for
the actual native PE/ELF executable, Windows Job, delegated Linux cgroup,
physical ADC or EFS evidence of a production install.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import os
import struct

from backend.nvp_p1a_original_capture_worker_bridge import (
    OriginalMicrophoneNativeWorkerAudit,PCM_WINDOW_BYTES)
from backend.nvp_w1g_protected_native_worker import ProtectedNativeWorker


PID="0123456789abcdef0123456789abcdef"


class OriginalMicrophoneCompiledAuditContracts(TestCase):
    def setUp(self):
        if os.name=="nt":
            # This module deliberately uses synthetic unencrypted sample
            # files to exercise logical binding. Real EFS inheritance is
            # independently required by production, not attested by mocks.
            mocked_efs=patch(
                "backend.nvp_p1a_original_capture_worker_bridge.verify_efs_inputs",
                return_value=True)
            mocked_efs.start()
            self.addCleanup(mocked_efs.stop)

    def fixture(self,root:Path,pcm:bytes):
        recovery=root/"native-original-capture-recovery"
        recovery.mkdir()
        directory=recovery/"nvp-live-original-fixture"
        directory.mkdir()
        spool=directory/"recording.pcm"
        spool.write_bytes(pcm)
        runtime=root/"workers"
        runtime.mkdir()
        worker=object.__new__(ProtectedNativeWorker)
        worker.runtime=runtime
        auditor=OriginalMicrophoneNativeWorkerAudit(
            worker,recovery_root=recovery)
        return auditor,worker,spool

    def run_kwargs(self,spool,pcm):
        return dict(
            project_id=PID,take_id="RecordedTake",source_id="OriginalMicSignal",
            scene_id="OriginalScene",scene_document_sha256="a"*64,
            camera_timeline_document_sha256="b"*64,
            subject_id="OriginalActor",emitter_path="/World/Actor",
            source_path=spool,recorded_samples=len(pcm)//2,
            original_pcm_sha256=sha256(pcm).hexdigest(),
            start_tick=0,end_tick=1000)

    def fake_kernel_verified_worker(self,worker,*,failure=False,mutate=None):
        calls=[]
        def run(owned_worker,role,pid,plan,*,sealed_inputs,memory_mb,timeout_s):
            self.assertIs(owned_worker,worker)
            self.assertEqual(role,"original_capture")
            self.assertEqual(pid,PID)
            self.assertEqual(set(sealed_inputs),{"source.pcm"})
            window=sealed_inputs["source.pcm"]
            self.assertLessEqual(len(window),PCM_WINDOW_BYTES)
            calls.append((dict(plan),sha256(window).hexdigest()))
            if mutate is not None:
                mutate()
            if failure:
                return {"state":"FAILED_UNVERIFIED",
                        "output_independently_verified":False,
                        "process_tree_custody_verified":False}
            job="w1g_"+format(len(calls),"024x")
            workspace=worker.runtime/job
            workspace.mkdir()
            checksum=sha256(window).hexdigest()
            peak=max(abs(item[0]) for item in struct.iter_unpack("<h",window))
            text=(f"format=nvp.w1g.pcm_intake.v1\n"
                  f"samples={len(window)//2}\npeak={peak}\n"
                  f"source_sha256={checksum}\n")
            (workspace/"capture.manifest").write_bytes(text.encode("ascii"))
            receipt=b"{\"fixture\":\"TEST-ONLY-NOT-OS-AUTHORITY\"}\n"
            (workspace/"result.json").write_bytes(receipt)
            return {"state":"SUCCEEDED_VERIFIED","job_id":job,
                    "input_sha256":{"source.pcm":checksum},
                    "result_sha256":sha256(receipt).hexdigest(),
                    "output_independently_verified":True,
                    "process_tree_custody_verified":True,
                    "worker_sha256":"c"*64,
                    "plan_sha256":"d"*64,
                    "os_custody_receipt":{
                        "scope":"synthetic-test-only",
                        "process_tree_custody_verified":True,
                    }}
        return calls,run

    def test_bounded_windows_cover_every_original_sample_and_bind_scene(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            # Over 4 MiB to prove the final tail receives its own bound
            # and no long-form original is silently truncated.
            pcm=struct.pack("<h",211)*(PCM_WINDOW_BYTES//2+13)
            audit,worker,spool=self.fixture(root,pcm)
            calls,run=self.fake_kernel_verified_worker(worker)
            with patch.object(ProtectedNativeWorker,"run",new=run):
                result=audit.verify_original_spool(**self.run_kwargs(spool,pcm))
            self.assertEqual(result["sample_count"],len(pcm)//2)
            self.assertEqual(result["window_count"],2)
            self.assertEqual(len(calls),2)
            self.assertEqual([call[0]["first_sample"] for call in calls],
                             [0,PCM_WINDOW_BYTES//2])
            self.assertEqual([call[0]["sample_count"] for call in calls],
                             [PCM_WINDOW_BYTES//2,13])
            self.assertEqual(result["original_pcm_sha256"],sha256(pcm).hexdigest())
            self.assertEqual(result["scene_document_sha256"],"a"*64)
            self.assertFalse(result["immutable_take_published"])
            self.assertFalse(result["device_capture_implemented_by_compiled_worker"])
            self.assertEqual(spool.read_bytes(),pcm)

    def test_failed_kernel_receipt_denies_original_source_audit(self):
        with TemporaryDirectory() as td:
            root=Path(td);pcm=struct.pack("<4h",0,1,-8,-32768)
            audit,worker,spool=self.fixture(root,pcm)
            _,run=self.fake_kernel_verified_worker(worker,failure=True)
            with patch.object(ProtectedNativeWorker,"run",new=run):
                with self.assertRaisesRegex(PermissionError,"OS/result evidence"):
                    audit.verify_original_spool(**self.run_kwargs(spool,pcm))
            self.assertEqual(spool.read_bytes(),pcm)

    def test_mutated_original_spool_never_passes_compiled_audit(self):
        with TemporaryDirectory() as td:
            root=Path(td);pcm=struct.pack("<4h",0,1,-8,-32768)
            audit,worker,spool=self.fixture(root,pcm)
            def tamper():
                spool.write_bytes(struct.pack("<4h",0,1,-7,-32768))
            _,run=self.fake_kernel_verified_worker(worker,mutate=tamper)
            with patch.object(ProtectedNativeWorker,"run",new=run):
                with self.assertRaisesRegex(RuntimeError,"changed or truncated"):
                    audit.verify_original_spool(**self.run_kwargs(spool,pcm))

    def test_untrusted_path_and_wrong_count_rejected_before_worker(self):
        with TemporaryDirectory() as td:
            root=Path(td);pcm=struct.pack("<4h",0,1,-8,-32768)
            audit,worker,spool=self.fixture(root,pcm)
            calls,run=self.fake_kernel_verified_worker(worker)
            with patch.object(ProtectedNativeWorker,"run",new=run):
                with self.assertRaisesRegex(PermissionError,"count/size"):
                    audit.verify_original_spool(**{
                        **self.run_kwargs(spool,pcm),"recorded_samples":3})
                alien=root/"outside.pcm"
                alien.write_bytes(pcm)
                with self.assertRaisesRegex(PermissionError,"trusted native device spool"):
                    audit.verify_original_spool(**{
                        **self.run_kwargs(spool,pcm),"source_path":alien})
                if hasattr(os,"symlink"):
                    linked=spool.parent/"independent_0.pcm"
                    try:
                        linked.symlink_to(spool)
                    except (OSError,NotImplementedError):
                        pass
                    else:
                        with self.assertRaisesRegex(PermissionError,"trusted native device spool"):
                            audit.verify_original_spool(**{
                                **self.run_kwargs(spool,pcm),"source_path":linked})
            self.assertFalse(calls)

    def test_bridge_refuses_untagged_or_fake_worker_authority(self):
        with TemporaryDirectory() as td:
            root=Path(td);root.mkdir(exist_ok=True)
            with self.assertRaisesRegex(TypeError,"Actual protected"):
                OriginalMicrophoneNativeWorkerAudit(object(),recovery_root=root)


if __name__=="__main__":
    import unittest
    unittest.main()
