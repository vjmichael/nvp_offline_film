"""CONV-12: original protected USD-FILM 01Q admission/authority/retry contracts.

These are synthetic *negative and operation-admission* tests. They do not
claim Blender pixels, kernel custody or private Windows AppContainer proof.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_blender_worker import BlenderOperation
from backend.nvp_usd_film01o_original_camera_roll_source import canonical
from backend.nvp_usd_film01q_selected_view_edit import chunk_job_id
from backend.nvp_usd_film01q_selected_view_host import ReviewedSelectedViewFilm


class CapturingSupervisor:
    def __init__(self,root):
        self.root=Path(root)
        self.operation=None
        self.records={}
        self.cancelled=None
    def inspect(self,job_id):
        if job_id not in self.records:
            raise KeyError(job_id)
        return self.records[job_id]
    def _validate(self,op):
        assert isinstance(op,BlenderOperation)
        self.operation=op
    def run(self,op):
        self.operation=op
        return {"state":"QUEUED","error":"actual private native worker unavailable"}
    def cancel(self,job_id):
        self.cancelled=job_id
        return True


class ProtectedSelectedChunkContract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-conv12-selection-")
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.supervisor=CapturingSupervisor(root)
        self.source_dir=root/"pretend-source-only-for-admission"
        self.source_dir.mkdir()
        (self.source_dir/"original_camera_roll_source.usda").write_text("#usda 1.0\n",encoding="ascii")
        (self.source_dir/"original_camera_roll_source.json").write_bytes(canonical({"synthetic":True}))
        frames=[{"camera_id":"director-camera-1"} for _ in range(8)]
        self.plan={
            "format":"nvp.usd_film01q.source_selected_view_render_plan.v1",
            "edit_document_sha256":"a"*64,
            "original_world_take_sha256":"b"*64,
            "original_performance_sha256":"c"*64,
            "source_manifest_sha256":"d"*64,
            "original_usd_sha256":"e"*64,
            "render_profile_sha256":"f"*64,
            "render_profile":{"timeout_seconds":3600,"max_worker_ram_mb":12288},
            "frames":frames,
            "chunks":[{"start_frame":0,"frame_count":8,
                       "source_frames_sha256":"1"*64}]
        }
        planned={"plan":self.plan,
                 "plan_sha256":sha256(canonical(self.plan)).hexdigest()}
        self.host=object.__new__(ReviewedSelectedViewFilm)
        self.host.index=object()
        self.host.supervisor=self.supervisor
        self.host.approve=lambda event,scope: True
        self.host.execute=lambda event,scope: True
        self.host.custody=lambda job: False
        self.host.render_quality="technical_smoke"
        self.host.source_plan=lambda *args,**kwargs:(
            self.source_dir,{},planned)
        self.params={"revision":1,"start":0,
                     "director_event":"reviewed-creative-001",
                     "native_execution_event":"reviewed-execution-002"}

    def attempt(self,**kwargs):
        return self.host.run_chunk(
            "project1","edit1",**{**self.params,**kwargs})

    def test_creative_refusal_does_not_stage_native_inputs(self):
        seen=[]
        self.host.approve=lambda event,scope: seen.append(scope) or False
        self.host.execute=lambda *_: self.fail("No execution after creative denial")
        with self.assertRaises(PermissionError):
            self.attempt()
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]["operation"],
                         "nvp.render.usd_film01q_selected_source_chunk.v1")
        self.assertIsNone(self.supervisor.operation)

    def test_separate_execution_credential_is_required(self):
        self.host.execute=lambda *_: False
        with self.assertRaisesRegex(PermissionError,"Independent one-use"):
            self.attempt()
        self.assertIsNone(self.supervisor.operation)

    def test_one_credential_cannot_satisfy_both_authorities(self):
        with self.assertRaisesRegex(PermissionError,"independent"):
            self.attempt(native_execution_event=self.params["director_event"])
        self.assertIsNone(self.supervisor.operation)

    def test_source_bound_hardened_native_operation_never_counts_queued_as_success(self):
        scopes=[]
        self.host.approve=lambda event,scope: scopes.append(scope) or True
        self.host.execute=lambda event,scope: scopes.append(scope) or True
        with patch("backend.nvp_usd_film01q_selected_view_host.require_efs_stage") as encrypt, \
             patch("backend.nvp_usd_film01q_selected_view_host.verify_efs_inputs") as verify:
            with self.assertRaisesRegex(RuntimeError,"Genuine Blender selected-view job failed"):
                self.attempt()
        encrypt.assert_called_once()
        verify.assert_called_once()
        self.assertEqual(len(scopes),2)
        self.assertNotEqual(scopes[0]["operation"],scopes[1]["operation"])
        self.assertTrue(scopes[1]["requires_kernel_private_isolation"])
        self.assertTrue(scopes[1]["require_encrypted_source_storage"])
        op=self.supervisor.operation
        self.assertIsInstance(op,BlenderOperation)
        self.assertTrue(op.require_linux_cgroup_v2)
        self.assertTrue(op.require_private_isolation)
        self.assertEqual(op.timeout_seconds,600)
        self.assertEqual(len(op.outputs),9)
        self.assertEqual(sum(k.endswith(".png") for k in op.outputs),8)
        self.assertEqual(op.outputs["audit.json"],"json_audit")
        self.assertEqual(op.inputs["source.usda"],
            sha256((self.source_dir/"original_camera_roll_source.usda").read_bytes()).hexdigest())
        self.assertEqual(set(op.arguments),{"--manifest","--audit"})
        self.assertNotIn("ffmpeg",op.canonical().lower())

    def test_failed_or_interrupted_attempt_cannot_replay(self):
        ident=chunk_job_id("a"*64,0,1,"f"*64)
        for state in ("RUNNING","INTERRUPTED","FAILED","CANCELLED","TIMED_OUT"):
            self.supervisor.records[ident]={"id":ident,"state":state}
            with self.subTest(state=state),self.assertRaisesRegex(PermissionError,"replay"):
                self.attempt()
        self.assertIsNone(self.supervisor.operation)

    def test_retry_requires_independent_proven_process_death(self):
        ident=chunk_job_id("a"*64,0,1,"f"*64)
        self.supervisor.records[ident]={"id":ident,"state":"FAILED"}
        with self.assertRaisesRegex(PermissionError,"custody"):
            self.attempt(attempt=2)
        self.assertIsNone(self.supervisor.operation)

    def test_cancel_routes_through_supervised_worker(self):
        self.assertTrue(self.host.cancel_chunk("project1","edit1",revision=1,start=0))
        self.assertEqual(self.supervisor.cancelled,
            chunk_job_id("a"*64,0,1,"f"*64))

    def test_unverified_worker_receipt_not_accepted(self):
        self.supervisor.verify_completed=lambda *_: (_ for _ in ()).throw(
            RuntimeError("No successfully verified worker output"))
        with self.assertRaisesRegex(RuntimeError,"No successfully verified"):
            self.host._verify_completed(
                chunk_job_id("a"*64,0,1,"f"*64),
                self.source_dir,{},self.host.source_plan()[2],0,1)


if __name__=="__main__":
    unittest.main()
