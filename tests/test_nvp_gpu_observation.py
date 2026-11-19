import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import nvp_gpu_observation as g
from backend import nvp_performance_probe as p
from backend import nvp_resource_guard as resources
from tools import nvp_perf_benchmark as b

DEVICE = "luid_0x00000000_0x000000ab_phys_0"


class FakePDH:
    PERF_DETAIL_WIZARD = 400
    PDH_FMT_LARGE = 1024
    PDH_FMT_NOSCALE = 4096

    def __init__(self, instances):
        self.instances = instances
        self.paths = []
        self.closed = False
        self.refreshed = False

    def EnumObjects(self, source, machine, level, refresh):
        self.refreshed = (source is None and machine is None and refresh == 1)
        return ["GPU Adapter Memory", "GPU Process Memory"]

    def EnumObjectItems(self, *args):
        return ["Dedicated Usage", "Shared Usage"], self.instances

    def OpenQuery(self): return object()

    def AddCounter(self, query, path):
        self.paths.append(path)
        return path

    def CollectQueryData(self, query): pass

    def GetFormattedCounterValue(self, path, flags):
        return 0, 123 if path.endswith("Dedicated Usage") else 0

    def CloseQuery(self, query): self.closed = True


class GPUObservationTests(unittest.TestCase):
    def test_pdh_exact_pid_and_adapter_scope(self):
        pdh = FakePDH([f"pid_1_{DEVICE}", f"pid_12_{DEVICE}", f"pid_12_{DEVICE}#1", "secret"])
        rows = g._wddm_rows(pdh, pid=12)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["device"], DEVICE)
        self.assertEqual(rows[0]["scope"], "owned_root_process")
        self.assertEqual(rows[0]["dedicated_used_bytes"], 123)
        self.assertEqual(rows[0]["shared_used_bytes"], 0)
        self.assertTrue(all("pid_12_" in x for x in pdh.paths))
        self.assertTrue(pdh.closed)
        self.assertTrue(pdh.refreshed)
        self.assertNotIn("pid_", json.dumps(rows))
        self.assertNotIn("budget_bytes", rows[0])

    def test_adapter_and_duplicates(self):
        pdh = FakePDH([DEVICE, "pid_2_" + DEVICE])
        self.assertEqual(g._wddm_rows(pdh)[0]["scope"], "adapter_global")
        self.assertEqual(g._wddm_rows(FakePDH([DEVICE, DEVICE])), [])
        self.assertEqual(g._wddm_rows(FakePDH(["unknown"])), [])

    def test_invalid_counter_unknown_and_cleanup(self):
        pdh = FakePDH([DEVICE])
        pdh.GetFormattedCounterValue = lambda *args: (0, -1)
        self.assertEqual(g._wddm_rows(pdh), [])
        self.assertTrue(pdh.closed)
        pdh = FakePDH([DEVICE])
        with patch.object(pdh, "CollectQueryData", side_effect=OSError("PRIVATE")):
            with self.assertRaises(OSError):
                g._wddm_rows(pdh)
        self.assertTrue(pdh.closed)

    def test_exact_owned_handle_alive_before_and_after(self):
        h = object()
        pdh = FakePDH([f"pid_12_{DEVICE}"])
        event = SimpleNamespace(WAIT_TIMEOUT=258, WaitForSingleObject=lambda *_: 258)
        process = SimpleNamespace(GetProcessId=lambda handle: 12 if handle is h else 13)
        with patch.object(g.sys,"platform","win32"), patch.dict(sys.modules,
                {"win32event":event,"win32pdh":pdh,"win32process":process}):
            self.assertEqual(len(g._native_owned_worker(h, 12)), 1)
            self.assertEqual(g._native_owned_worker(h, 13), [])
            with patch.object(event,"WaitForSingleObject",side_effect=[258,0]):
                self.assertEqual(g._native_owned_worker(h, 12), [])
            with patch.object(event,"WaitForSingleObject",return_value=0):
                self.assertEqual(g._native_owned_worker(h, 12), [])

    def test_native_sources_separate_budget_from_capacity(self):
        dx = resources.GPUResource("dxgi:0", "SECRET", "windows_dxgi_process_budget", 100, 125, False)
        nv = resources.GPUResource("nvidia:0", "SECRET", "nvml_global", 100, 75, True)
        with patch.object(g.sys,"platform","win32"), patch.dict(sys.modules,{"win32pdh":FakePDH([DEVICE])}), \
                patch.object(resources,"_windows_dxgi_gpus",return_value=[dx]), \
                patch.object(resources,"_nvml_gpus",return_value=[nv]):
            rows, errors = g._native_adapters()
        self.assertEqual(errors,0)
        rows = {r["source"]:r for r in rows}
        self.assertEqual(rows[dx.source]["budget_bytes"],100*g.MIB)
        self.assertEqual(rows[dx.source]["dedicated_used_bytes"],125*g.MIB)
        self.assertNotIn("capacity_bytes",rows[dx.source])
        self.assertEqual(rows[nv.source]["capacity_bytes"],100*g.MIB)
        self.assertNotIn("budget_bytes",rows[nv.source])
        self.assertNotIn("SECRET",json.dumps(rows))

    def test_linux_amd_capacity(self):
        amd=resources.GPUResource("card0","AMD","linux_drm_amdgpu_global",32000,3,True)
        with patch.object(g.sys,"platform","linux"),patch.object(resources,"_linux_amd_gpus",return_value=[amd]), \
                patch.object(resources,"_nvml_gpus",return_value=[]):
            rows,errors=g._native_adapters()
        self.assertEqual(errors,0)
        self.assertEqual(rows[0]["capacity_bytes"],32000*g.MIB)
        self.assertEqual(rows[0]["scope"],"adapter_global")

    def test_sample_throttle_peaks_baseline_and_missing_budget(self):
        observer=g.GPUObserver()
        row={"source":"windows_pdh","scope":"adapter_global","device":DEVICE,"dedicated_used_bytes":0}
        with patch.object(g,"_native_adapters",side_effect=[([row],0),([{**row,"dedicated_used_bytes":17}],0)]) as fetch:
            observer.sample(force=True)
            observer.sample()
            observer.sample(force=True)
        self.assertEqual(fetch.call_count,2)
        r=observer.report()["sensors"][0]
        self.assertEqual(r["samples"],2)
        self.assertEqual(r["first_dedicated_used_bytes"],0)
        self.assertEqual(r["last_dedicated_used_bytes"],17)
        self.assertEqual(r["peak_dedicated_used_bytes"],17)
        self.assertIsNone(r["peak_budget_bytes"])

    def test_missing_and_bounded_aggregation(self):
        observer=g.GPUObserver()
        with patch.object(g,"_native_adapters",side_effect=RuntimeError("PRIVATE")):
            observer.sample(force=True)
        self.assertEqual(observer.report()["status"],"unavailable")
        self.assertEqual(observer.errors,1)
        self.assertNotIn("PRIVATE",json.dumps(observer.report()))
        observer._merge([{"source":"windows_pdh","scope":"adapter_global","device":str(i),
                          "dedicated_used_bytes":1} for i in range(100)])
        self.assertEqual(len(observer.rows),g.MAX_ROWS)
        self.assertEqual(observer.dropped_rows,100-g.MAX_ROWS)

    def test_opt_in_only_and_worker_failure_observational(self):
        with patch.object(g,"_native_adapters",return_value=([],0)) as sample:
            with p.observe() as session:
                p.observe_live_windows_gpu(object(),12)
                with p.span("reel.frame"): pass
            self.assertEqual(sample.call_count,0)
            self.assertEqual(session.report()["gpu"]["status"],"disabled")
            with p.observe(gpu=True) as session:
                with patch.object(g,"_native_owned_worker",side_effect=OSError("PRIVATE")):
                    p.observe_live_windows_gpu(object(),12)
                    with self.assertRaises(PermissionError):
                        with p.span("take.worker"): raise PermissionError("denied")
            self.assertEqual(sample.call_count,2)
            self.assertEqual(session.report()["gpu"]["errors"],1)
            self.assertEqual(session.report()["gpu"]["status"],"unavailable")


    def test_native_poll_observes_only_live_owned_handle(self):
        from backend import nvp_worker_containment as custody
        h = object()
        event = SimpleNamespace(WAIT_OBJECT_0=0, WAIT_TIMEOUT=258,
                                WaitForSingleObject=lambda *_: 258)
        process = SimpleNamespace(GetExitCodeProcess=lambda _: 7)
        worker = custody.WindowsJobProcess(object(), h, 12)
        with patch.dict(sys.modules, {"win32event": event, "win32process": process}), \
                patch.object(custody,"observe_live_windows_gpu") as observer:
            self.assertIsNone(worker.poll())
            observer.assert_called_once_with(h,12)
            with patch.object(event,"WaitForSingleObject",return_value=0):
                self.assertEqual(worker.poll(),7)
                self.assertEqual(worker.poll(),7)
            observer.assert_called_once_with(h,12)


class BenchmarkTests(unittest.TestCase):
    def test_duration_cardinality_and_limits(self):
        rows=list(b.duration_cases())
        self.assertEqual([r["frames"] for r in rows],[43200,86400,259200,518400,691200,1036800])
        self.assertEqual([r["minimum_chunks"] for r in rows],[1800,3600,10800,21600,28800,43200])
        self.assertEqual([r["blocked_by_frame_limit"] for r in rows],[False]*6)
        self.assertEqual([r["blocked_by_chunk_limit"] for r in rows],[False]*6)
        self.assertEqual(rows[-1]["pcm_stereo_s16_48khz_bytes"],8294400000)
        self.assertTrue(all(not r["production_accepted"] for r in rows))

    def test_page_bound_and_partial_chunk(self):
        rows=list(b.pages(7,chunk_frames=3,page_limit=2))
        self.assertEqual(rows,[((0,3),(3,3)),((6,1),)])
        self.assertTrue(all(r["max_page_chunks"]<=r["page_limit"] for r in b.walk_duration_cases()))

    def test_overhead_fixture_never_fakes_gpu_measurements(self):
        with patch.object(g,"_native_adapters",return_value=([],0)):
            rows=b.overhead(2,3)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r["gpu_trials_observed"]==0 for r in rows))
        self.assertTrue(all(set(r["median_ns_per_call"])=={"direct","disabled","host","host_gpu"} for r in rows))
        with self.assertRaises(ValueError): b.overhead(2001,3)


if __name__ == "__main__":
    unittest.main()
