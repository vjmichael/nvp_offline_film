"""CONV-06 adopted original USD-FILM-01S deterministic planner and queue tests.

No mock native Cycles success: the independent verifier callback is
explicitly test-only. Existing real Blender supervisor owns native process
acceptance. These tests prove measured admission, user shot grouping,
zero-resource hold, per-shot authority, and crash-safe queue state.
"""
from __future__ import annotations
from dataclasses import replace
import tempfile
import unittest

from backend.nvp_resource_guard import (
    GPUResource,ResourceSnapshot)
from backend.nvp_usd_film01s_adaptive_batch import (
    BatchPreferences,Shot,plan_batches,preview_batch_layout,safe_parallelism,
    DurableShotBatchQueue,PREVIEW,FINAL)


def host(total=8192,available=6144,gpus=(),pressure=0):
    return ResourceSnapshot(
        sampled_at=1000,ram_total_mb=total,
        ram_available_mb=available,memory_psi_full10=pressure,
        gpus=tuple(gpus),warnings=())


def sample_shots(count=9):
    return [Shot(f"Shot{i:02d}",f"Cam{i:02d}",i*10,i*10+10)
            for i in range(count)]


class HardwareBatchPlannerTest(unittest.TestCase):
    def test_ui_estimate_counts_only_no_fake_filmindex_or_execution(self):
        report=preview_batch_layout(
            9,3,BatchPreferences(shots_per_batch=4,
                parallel_worker_limit=1,preview_worker_ram_mb=512),
            host(4096,2800),cpu_threads=2)
        self.assertEqual(report["format"],
            "nvp.film01s.read_only_batch_capacity_preview.v1")
        self.assertEqual(report["shots_per_batch"],4)
        self.assertEqual([x["shot_count"] for x in
            report["lowfi_preview_batches"]],[4,4,1])
        self.assertEqual([x["shot_count"] for x in
            report["hifi_selected_shot_batches"]],[3])
        self.assertEqual(report["render_jobs_started"],0)
        self.assertFalse(report["source_film_index_take_verified"])
        self.assertTrue(report["browser_has_no_native_render_authority"])

    def test_low_pc_automatically_limits_concurrency_without_losing_cameras(self):
        snap=host(4096,2800)
        pref=BatchPreferences(preview_worker_ram_mb=512)
        plan=plan_batches("SmallPC","a"*64,sample_shots(9),pref,
                          snap,cpu_threads=2)["plan"]
        self.assertEqual(plan["shots_per_batch"],2)
        self.assertEqual(plan["capacity_at_plan_time"]["lofi"]["safe_workers"],1)
        self.assertEqual(plan["capacity_at_plan_time"]["hifi"]["safe_workers"],0)
        self.assertEqual(len(plan["source_shots"]),9)
        self.assertEqual(len([b for b in plan["batches"]
            if b["quality"]=="lofi"]),5)
        self.assertEqual(plan["batches"][4]["planned_shot_count"],1)
        self.assertEqual(len(plan["batches"]),10)

    def test_fast_pc_automatically_scales_and_director_can_choose_grouping(self):
        snap=host(32768,28000)
        auto=plan_batches("LargePC","b"*64,sample_shots(21),
            BatchPreferences(preview_worker_ram_mb=512),snap,
            cpu_threads=16)["plan"]
        self.assertEqual(auto["shots_per_batch"],16)
        self.assertEqual(auto["capacity_at_plan_time"]["lofi"]["safe_workers"],8)
        self.assertEqual(auto["capacity_at_plan_time"]["hifi"]["safe_workers"],4)
        manual=plan_batches("ManualPC","b"*64,sample_shots(21),
            BatchPreferences(shots_per_batch=7,parallel_worker_limit=2),
            snap,cpu_threads=16)["plan"]
        self.assertEqual(manual["shots_per_batch"],7)
        self.assertEqual(len(manual["batches"]),6)
        self.assertEqual(manual["capacity_at_plan_time"]["lofi"]["safe_workers"],2)
        self.assertEqual(manual["capacity_at_plan_time"]["hifi"]["safe_workers"],2)

    def test_user_can_queue_twelve_shots_while_only_one_worker_runs(self):
        plan=plan_batches("LowPCManual","c"*64,sample_shots(12),
            BatchPreferences(shots_per_batch=12,preview_worker_ram_mb=512),
            host(4096,2800),cpu_threads=2)["plan"]
        self.assertEqual(plan["shots_per_batch"],12)
        self.assertEqual(plan["batches"][0]["planned_shot_count"],12)
        self.assertEqual(plan["batches"][0]["safe_parallel_workers_at_plan_time"],1)

    def test_data_first_many_viewpoint_previews_only_selected_shots_final(self):
        names=sample_shots(9)
        plan=plan_batches(
            "SelectiveEdit","d"*64,names,
            BatchPreferences(shots_per_batch=3,parallel_worker_limit=2),
            host(32768,27000),cpu_threads=12,
            final_shot_ids=["Shot01","Shot04","Shot08"])["plan"]
        preview=[batch for batch in plan["batches"]
                 if batch["quality"]==PREVIEW]
        final=[batch for batch in plan["batches"]
               if batch["quality"]==FINAL]
        self.assertEqual(len(preview),3)
        self.assertEqual(len(final),1)
        self.assertEqual(sum(x["planned_shot_count"] for x in preview),9)
        self.assertEqual(sum(x["planned_shot_count"] for x in final),3)
        self.assertEqual(plan["selected_final_shot_ids"],
                         ["Shot01","Shot04","Shot08"])
        with self.assertRaises(ValueError):
            plan_batches("InvalidSelected","d"*64,names,BatchPreferences(),
                         host(32768,27000),cpu_threads=12,
                         final_shot_ids=["DoesNotExist"])

    def test_missing_verified_gpu_backend_queues_even_with_reported_vram(self):
        gpu=GPUResource("nvidia:0","GPU","nvml_global",16384,1000,True)
        policy=BatchPreferences(renderer="gpu",gpu_device_id="nvidia:0")
        unknown=safe_parallelism(host(32768,28000,(gpu,)),
            policy,quality=FINAL,cpu_threads=16)
        self.assertEqual(unknown["safe_workers"],0)
        self.assertIn("independently verified",unknown["reason"])
        known=safe_parallelism(host(32768,28000,(gpu,)),
            policy,quality=FINAL,cpu_threads=16,
            verified_cycles_gpu_ids={"nvidia:0"})
        self.assertGreaterEqual(known["safe_workers"],1)
        dxgi=GPUResource("dxgi:0","AMD",
            "windows_dxgi_process_budget",16384,1000,False)
        limited=safe_parallelism(host(32768,28000,(dxgi,)),
            BatchPreferences(renderer="gpu",gpu_device_id="dxgi:0"),
            quality=FINAL,cpu_threads=16,
            verified_cycles_gpu_ids={"dxgi:0"})
        self.assertEqual(limited["safe_workers"],1)
        self.assertEqual(limited["gpu_budget_scope"],
                         "limited_process_budget_only")

    def test_other_nvp_reservations_reduce_camera_worker_admission(self):
        snapshot=host(32768,28000)
        p=BatchPreferences(preview_worker_ram_mb=768)
        normal=safe_parallelism(snapshot,p,quality=PREVIEW,
            cpu_threads=16)
        reserved=safe_parallelism(snapshot,p,quality=PREVIEW,
            cpu_threads=16,reserved_ram_mb=22000)
        self.assertGreater(normal["safe_workers"],0)
        self.assertEqual(reserved["safe_workers"],0)
        self.assertIn("RAM headroom",reserved["reason"])

    def test_unknown_ram_or_memory_pressure_does_not_start_worker(self):
        policy=BatchPreferences()
        missing=host(8192,5000)
        missing=replace(missing,ram_available_mb=None)
        self.assertEqual(safe_parallelism(missing,policy,
            quality=PREVIEW,cpu_threads=8)["safe_workers"],0)
        self.assertEqual(safe_parallelism(host(8192,7000,pressure=7),
            policy,quality=PREVIEW,cpu_threads=8)["safe_workers"],0)


class DurableBatchQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="nvp-shot-batches-")
        self.queue=DurableShotBatchQueue(self.tmp.name)
        self.snapshot=host(32768,28000)
        self.preferences=BatchPreferences(shots_per_batch=2,
            parallel_worker_limit=1)
        self.plan=plan_batches("OneOriginalScene","e"*64,
            sample_shots(3),self.preferences,self.snapshot,cpu_threads=8)
        self.queue.enqueue(self.plan,director_event="APPROVE_PLAN",
            authorize=lambda event,scope:(
                event=="APPROVE_PLAN" and
                scope["operation"]==
                    "nvp.film01s.enqueue_virtual_shot_batches.v1"
                and scope["shots_per_batch"]==2))

    def tearDown(self):
        self.tmp.cleanup()

    def _claim(self,quality,shot,attempt=1,auth="APPROVE_SHOT",
               custody=lambda *_:False,snapshot=None):
        return self.queue.claim("OneOriginalScene",
            quality=quality,shot_id=shot,attempt=attempt,
            authorizer=lambda event,scope:(
                event=="APPROVE_SHOT" and
                scope["operation"]==
                    "nvp.film01s.claim_one_source_shot.v1"
                and scope["source_performance_sha256"]=="e"*64),
            director_event=auth,prove_prior_worker_stopped=custody,
            snapshot=snapshot or self.snapshot,cpu_threads=8)

    def test_preview_before_final_and_verified_complete_required(self):
        early=self._claim(FINAL,"Shot00")
        self.assertFalse(early["admitted"])
        self.assertEqual(early["state"],"QUEUED_FOR_PREVIEW")
        first=self._claim(PREVIEW,"Shot00")
        self.assertTrue(first["admitted"])
        self.assertEqual(first["state"],"RUNNING")
        other=self._claim(PREVIEW,"Shot01")
        self.assertFalse(other["admitted"])
        self.assertEqual(other["state"],"QUEUED_FOR_RESOURCES")
        with self.assertRaises(PermissionError):
            self.queue.finish("OneOriginalScene",
                quality=PREVIEW,shot_id="Shot00",attempt=1,
                verified_receipt_sha256="f"*64,
                verify_native_renderer_result=lambda *_:False)
        self.assertTrue(self.queue.finish("OneOriginalScene",
            quality=PREVIEW,shot_id="Shot00",attempt=1,
            verified_receipt_sha256="f"*64,
            verify_native_renderer_result=lambda scope:(
                scope["quality"]==PREVIEW
                and scope["source_performance_sha256"]=="e"*64)))
        self.assertTrue(self._claim(FINAL,"Shot00")["admitted"])

    def test_crash_recovery_does_not_replay_old_worker_or_old_consent(self):
        self.assertTrue(self._claim(PREVIEW,"Shot00")["admitted"])
        self.assertEqual(
            DurableShotBatchQueue(self.tmp.name).recover_interrupted(
                "OneOriginalScene"),1)
        self.assertEqual(self.queue.status(
            "OneOriginalScene")["states"]["INTERRUPTED"],1)
        with self.assertRaises(PermissionError):
            self._claim(PREVIEW,"Shot00",attempt=1)
        with self.assertRaises(PermissionError):
            self._claim(PREVIEW,"Shot00",attempt=2)
        with self.assertRaises(PermissionError):
            self._claim(PREVIEW,"Shot00",attempt=2,
                custody=lambda *_:True,auth="NOT_APPROVED")
        new=self._claim(PREVIEW,"Shot00",attempt=2,
                        custody=lambda *_:True)
        self.assertTrue(new["admitted"])
        self.assertEqual(new["attempt"],2)

    def test_refreshing_hw_on_every_dispatch_holds_when_ram_drops(self):
        shrunk=host(8192,1000)
        response=self._claim(PREVIEW,"Shot00",snapshot=shrunk)
        self.assertFalse(response["admitted"])
        self.assertEqual(response["state"],"QUEUED_FOR_RESOURCES")
        self.assertEqual(self.queue.status(
            "OneOriginalScene")["states"]["QUEUED"],6)

    def test_old_plan_is_immutable_and_reopen_retains_receipts(self):
        with self.assertRaises(RuntimeError):
            self.queue.enqueue(self.plan,director_event="APPROVE_PLAN",
                authorize=lambda *_:True)
        self._claim(PREVIEW,"Shot00")
        self.queue.finish("OneOriginalScene",quality=PREVIEW,
            shot_id="Shot00",attempt=1,
            verified_receipt_sha256="1"*64,
            verify_native_renderer_result=lambda *_:True)
        restarted=DurableShotBatchQueue(self.tmp.name)
        status=restarted.status("OneOriginalScene")
        self.assertEqual(status["states"]["SUCCEEDED"],1)
        self.assertEqual(status["states"]["QUEUED"],5)
        self.assertEqual(status["progress_required"],6)



if __name__ == '__main__':
    unittest.main()
