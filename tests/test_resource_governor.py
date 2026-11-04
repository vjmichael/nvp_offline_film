"""Real resource policy, durable reservations, critical pressure and missing telemetry."""
from __future__ import annotations
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend.nvp_resource_guard import (
    GPUResource,ResourceSnapshot,AdmissionRequest,decide_admission,
    collect_resources,emergency_pressure,
)
from backend.nvp_resource_ledger import TaskLedger


def sample(ram=32768,available=20000,used=8000,gpu=True,pressure=0):
    devices=(GPUResource("gpu:0","Test GPU","test_sensor",32768,used,True),) if gpu else ()
    return ResourceSnapshot(1,ram,available,pressure,devices)


class ResourceGuardTests(unittest.TestCase):
    def test_ram_headroom_and_pressure_refuse_unsafe_start(self):
        req=AdmissionRequest("job_one","blender","Blender",8192)
        self.assertTrue(decide_admission(sample(),req)[0])
        self.assertFalse(decide_admission(sample(available=13000),req)[0])
        self.assertFalse(decide_admission(sample(pressure=9),req)[0])
        self.assertFalse(decide_admission(sample(),req,reserved_ram_mb=12000)[0])
        self.assertFalse(decide_admission(ResourceSnapshot(1,None,None,None,()),req)[0])

    def test_gpu_unknown_refused_and_reservations_subtracted(self):
        req=AdmissionRequest("gpu_one","blender","GPU rendering",1024,11000,"gpu:0")
        self.assertTrue(decide_admission(sample(),req)[0])
        self.assertFalse(decide_admission(sample(gpu=False),req)[0])
        self.assertFalse(decide_admission(sample(used=20000),req)[0])
        self.assertFalse(decide_admission(sample(),req,reserved_gpu_mb=14000)[0])
        with self.assertRaises(ValueError):
            AdmissionRequest("gpu_two","blender","GPU rendering",1024,1200)

    def test_critical_memory_cancel_policy(self):
        self.assertIn("RAM",emergency_pressure(sample(available=500)))
        self.assertIn("stall",emergency_pressure(sample(pressure=30)))
        self.assertIn("GPU",emergency_pressure(sample(used=32500),gpu_device="gpu:0"))
        self.assertIsNone(emergency_pressure(sample()))
        self.assertIn("sensor",emergency_pressure(sample(gpu=False),gpu_device="gpu:0"))

    def test_concurrent_reservations_queue_retry_and_release(self):
        with TemporaryDirectory() as tmp:
            get=lambda:sample(available=16500)
            first=TaskLedger(tmp,sampler=get)
            second=TaskLedger(tmp,sampler=get)
            a=AdmissionRequest("one","blender","Scene one",6000)
            b=AdmissionRequest("two","ai_loading","Load AI",6000)
            self.assertTrue(first.admit(a)["admitted"])
            self.assertEqual(second.admit(b)["state"],"QUEUED")
            self.assertEqual(second.snapshot()["reservations"]["ram_mb"],6000)
            self.assertFalse(second.retry("two")["admitted"])
            first.update("one","rendering","Engine running, no measured percent")
            self.assertIsNone(first.get_task("one")["completed_fraction"])
            first.finish("one","SUCCEEDED","File hashes verified")
            self.assertTrue(second.retry("two")["admitted"])
            second.update("two","loading_model","Provider measured 35%",fraction=.35)
            self.assertEqual(first.get_task("two")["completed_fraction"],.35)
            with self.assertRaises(ValueError):
                second.update("two","generating","fake progress",fraction=1.25)
            second.finish("two","FAILED","Provider refused")
            self.assertEqual(first.snapshot()["reservations"]["ram_mb"],0)
            self.assertGreater(len(first.events("two")),0)

    def test_gpu_device_specific_reservations(self):
        with TemporaryDirectory() as tmp:
            gpus=(GPUResource("gpu:0","GPU0","test",16000,2000,True),
                  GPUResource("gpu:1","GPU1","test",16000,1000,True))
            l=TaskLedger(tmp,sampler=lambda:ResourceSnapshot(1,65536,50000,0,gpus))
            self.assertTrue(l.admit(AdmissionRequest("one","blender","GPU0",2048,6000,"gpu:0"))["admitted"])
            self.assertTrue(l.admit(AdmissionRequest("two","blender","GPU1",2048,6000,"gpu:1"))["admitted"])
            self.assertFalse(l.admit(AdmissionRequest("three","blender","GPU0 again",2048,6000,"gpu:0"))["admitted"])

    def test_crash_reservation_does_not_silently_expire(self):
        with TemporaryDirectory() as tmp:
            l=TaskLedger(tmp,sampler=lambda:sample())
            l.admit(AdmissionRequest("crashed","blender","Native worker",8192))
            self.assertEqual(TaskLedger(tmp,sampler=lambda:sample()).snapshot()["reservations"]["ram_mb"],8192)
            l.finish("crashed","INTERRUPTED","OS worker containment verified")
            self.assertEqual(l.snapshot()["reservations"]["ram_mb"],0)

    def test_external_ai_is_not_a_model_load_claim(self):
        with TemporaryDirectory() as tmp:
            l=TaskLedger(tmp,sampler=lambda:sample(gpu=False))
            l.observe_external("ext_request","Writing draft")
            row=l.get_task("ext_request")
            self.assertEqual(row["state"],"OBSERVING")
            self.assertEqual(row["ram_mb"],0)
            self.assertIsNone(row["completed_fraction"])
            l.finish("ext_request","SUCCEEDED","Draft only")

    def test_actual_host_sensor_does_not_fabricate_values(self):
        value=collect_resources()
        self.assertIsInstance(value.public()["gpus"],list)
        if value.ram_available_mb is not None:
            self.assertGreaterEqual(value.ram_total_mb,value.ram_available_mb)
        for gpu in value.gpus:
            self.assertGreater(gpu.budget_mb,0)
            self.assertGreaterEqual(gpu.used_mb,0)


if __name__=="__main__":
    unittest.main()
