"""STACK-02C3: optional memory governor integrated into actual Blender supervisor."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest
from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


class MockWorker:
    pid=123456
    returncode=0
    def poll(self):return 0
    def wait(self,timeout=None):return 0
    def close(self):pass


class BlenderGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.sampler=lambda:ResourceSnapshot(1,32768,24000,0,())
        self.ledger=TaskLedger(self.root/"system",sampler=self.sampler)
        binary=Path(sys.executable).resolve()
        self.supervisor=BlenderWorkerSupervisor(self.root/"blender",
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version="Blender 5.2.3",activity_ledger=self.ledger)
        self.job=self.supervisor.root/"scene_a"
        self.job.mkdir()
        (self.job/"script.py").write_text("print('trusted')","utf8")
        self.op=BlenderOperation(job_id="scene_a",script="script.py",
            script_sha256=sha_file(self.job/"script.py"),
            inputs={},outputs={"scene_a.json":"json_audit"},
            arguments={"--audit":"scene_a.json"},memory_limit_mb=4096)

    def tearDown(self):self.temp.cleanup()

    def fake_launch(self,*args,**kwargs):
        (Path(kwargs["cwd"])/"scene_a.json").write_text('{"passed":true,"native":true}',"utf8")
        return MockWorker()

    def test_real_supervisor_is_queued_without_reservation_or_process_launch(self):
        self.ledger.sampler=lambda:ResourceSnapshot(1,16384,2000,0,())
        with patch.object(self.supervisor,"probe") as probe,patch(
                "backend.nvp_blender_worker.launch_contained") as launch:
            result=self.supervisor.run(self.op)
            self.assertEqual(result["state"],"QUEUED")
            probe.assert_not_called();launch.assert_not_called()
            self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_queued_work_can_retry_then_supervised_output_is_audited(self):
        self.ledger.sampler=lambda:ResourceSnapshot(1,16384,3000,0,())
        self.assertEqual(self.supervisor.run(self.op)["state"],"QUEUED")
        self.ledger.sampler=self.sampler
        with patch.object(self.supervisor,"probe",return_value={"blender":"Blender 5.2.3"}),patch(
                "backend.nvp_blender_worker.launch_contained",side_effect=self.fake_launch):
            result=self.supervisor.run(self.op)
        self.assertEqual(result["state"],"SUCCEEDED")
        activity=self.ledger.get_task(result["resource_activity_id"])
        self.assertEqual(activity["state"],"SUCCEEDED")
        self.assertEqual(activity["completed_fraction"],1.0)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertGreater(len(self.ledger.events(result["resource_activity_id"])),3)

    def test_guarded_gpu_work_requires_real_vram_budget(self):
        gpuop=BlenderOperation(**{**self.op.__dict__,
            "gpu_memory_mb":8000,"gpu_device_id":"dxgi:0"})
        with patch.object(self.supervisor,"probe") as probe:
            result=self.supervisor.run(gpuop)
            self.assertEqual(result["state"],"QUEUED")
            self.assertIn("GPU",result["error"])
            probe.assert_not_called()


if __name__=="__main__":
    unittest.main()
