"""USD-FILM-01D — original USD camera shot streaming and durable restarts.

Actual NVP FilmIndex/UsdStage sources; no mock USD and no invented camera.
An authored spatial hint is NOT a visibility or occlusion solver, so director
required sets must remain loaded even when distant from the original camera.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from pxr import Usd, UsdGeom

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01d_shot_working_set import (
    FORMAT, RECEIPT_FORMAT, FilmWorldShotPlanner, FilmShotWorkingSet,
    native_gpu_device_sampler,
)
from test_nvp_usd_film01_world import NativeFilmWorld01


class RealUSDShotWorldStreaming(unittest.TestCase):
    def setUp(self):
        b = NativeFilmWorld01(
            "test_real_lazy_scene_payloads_and_original_authored_camera")
        b.setUp()
        self.addCleanup(b.tmp.cleanup)
        self.b = b
        self.original_world = b.publish()
        self.planner = FilmWorldShotPlanner(b.index)
        self.outside_shot = self.planner.publish(
            b.pid, "ShotOutside", world_id="TownWorld",
            world_revision=1, camera_set="Outside",
            camera_prim="/World/Camera", sample_ticks=[0,T],
            required_sets=["Outside"],max_loaded_sets=1)
        self.inside_shot = self.planner.publish(
            b.pid, "ShotInside", world_id="TownWorld",
            world_revision=1,camera_set="Inside",
            camera_prim="/World/InteriorCamera",sample_ticks=[0,T],
            required_sets=["Inside"],max_loaded_sets=1,
            director_looks={"Facade":"High"})

    def runtime(self, **kwargs):
        return FilmShotWorkingSet(
            self.b.index, self.b.pid, "TownWorld", 1, **kwargs)

    def test_camera_plan_is_original_timed_usd_camera_not_model_guess(self):
        b=self.b
        shot = self.planner.inspect(b.pid,"ShotOutside",1)
        self.assertEqual(shot["kind"],"camera")
        self.assertEqual(shot["data"]["format"],FORMAT)
        self.assertEqual(shot["data"]["camera_sample_ticks"],[0,T])
        self.assertEqual(shot["data"]["original_camera_positions_m"],
                         [[0.0,4.0,10.0],[0.0,4.0,10.0]])
        self.assertEqual(
            shot["data"]["source_camera_scene_sha256"],
            b.index.read_revision(b.pid,"Street",1)["document_sha256"])
        self.assertEqual(
            shot["data"]["world_document_sha256"],
            self.original_world["document_sha256"])
        self.assertTrue(
            shot["data"]["not_a_renderer_or_visibility_occlusion_solution"])
        with self.assertRaises((ValueError,PermissionError,RuntimeError)):
            self.planner.publish(
                b.pid, "ForgedShot",world_id="TownWorld",world_revision=1,
                camera_set="Outside",camera_prim="/World/StageActor",
                sample_ticks=[0],required_sets=["Outside"],
                max_loaded_sets=1)
        with self.assertRaises(KeyError):
            b.index.read_revision(b.pid,"ForgedShot",1)

    def test_two_shot_transitions_unload_previous_set_without_changing_source(self):
        b=self.b
        with self.runtime() as runtime:
            original_usd_root_sha = sha256(
                runtime.session.stage.GetRootLayer().ExportToString().
                encode("utf8")).hexdigest()
            first = runtime.transition(
                "ShotOutside",1,receipt_id="OutsideWorkingSet")
            self.assertEqual(first["state"],"SUCCEEDED_SOURCE_WORKING_SET")
            self.assertEqual(first["sets_actually_loaded"],["Outside"])
            self.assertEqual(first["original_camera_set"],"Outside")
            self.assertEqual(
                first["source_semantic_scene_summary"]["entries"][0]["set"],
                "Outside")
            self.assertTrue(first["camera_positions_reopened_exactly"])
            self.assertFalse(first["native_renderer_pixels_verified"])
            self.assertFalse(first["resource_after"]["gpu_is_stage_attributable"])
            second = runtime.transition(
                "ShotInside",1,receipt_id="InsideWorkingSet")
            self.assertEqual(second["sets_actually_loaded"],["Inside"])
            self.assertEqual(second["original_camera_set"],"Inside")
            self.assertFalse(runtime.session.stage.GetPrimAtPath(
                "/World/Sets/Outside").IsLoaded())
            self.assertTrue(runtime.session.stage.GetPrimAtPath(
                "/World/Sets/Inside/InteriorCamera").IsA(UsdGeom.Camera))
            self.assertEqual(
                runtime.session.stage.GetPrimAtPath(
                    "/World/Variants/Facade").GetVariantSets().
                    GetVariantSet("look").GetVariantSelection(),"High")
            self.assertEqual(second["resource_after"]["gpu_device_used_bytes"],None)
            self.assertFalse(second["director_look_layer_authoritative"])
            self.assertEqual(len(second["director_disposable_look_layer_sha256"]),64)
            self.assertEqual(
                sha256(runtime.session.stage.GetRootLayer().
                       ExportToString().encode("utf8")).hexdigest(),
                original_usd_root_sha)
            self.assertTrue(runtime.session.stage.GetSessionLayer().subLayerPaths)
            undo=runtime.discard_temporary_look()
            self.assertEqual(undo["state"],"DIRECTOR_PREVIEW_REVERTED")
            self.assertEqual(
                runtime.session.stage.GetPrimAtPath(
                    "/World/Variants/Facade").GetVariantSets().
                    GetVariantSet("look").GetVariantSelection(),"Low")
            summary=runtime.query_loaded_scene()
            self.assertIn("camera",{e["role"] for e in summary["entries"]})
        for receipt,source in (
            ("OutsideWorkingSet","ShotOutside"),
            ("InsideWorkingSet","ShotInside"),
        ):
            result=b.index.read_revision(b.pid,receipt,1)
            self.assertEqual(result["kind"],"presentation")
            self.assertEqual(result["data"]["format"],RECEIPT_FORMAT)
            self.assertEqual(result["data"]["state"],
                             "SUCCEEDED_SOURCE_WORKING_SET")
            self.assertEqual(
                result["data"]["source_camera_plan_sha256"],
                b.index.read_revision(b.pid,source,1)["document_sha256"])
        self.assertEqual(
            b.index.read_revision(b.pid,"TownWorld",1)["document_sha256"],
            self.original_world["document_sha256"])

    def test_proximity_is_only_prefetch_director_required_sources_win(self):
        b=self.b
        extra=self.planner.publish(
            b.pid,"ShotNearPrefetch",world_id="TownWorld",world_revision=1,
            camera_set="Outside",camera_prim="/World/Camera",
            sample_ticks=[0,T],required_sets=["Outside"],
            max_loaded_sets=2,spatial_hints=[
                {"set":"Inside","center_m":[0,3,8],"radius_m":2}
            ],prefetch_distance_m=4.)
        with self.runtime() as r:
            selected=r.transition(
                "ShotNearPrefetch",1,receipt_id="PrefetchReceipt")
            self.assertEqual(selected["sets_actually_loaded"],
                             ["Inside","Outside"])
            self.assertEqual(selected["prefetched_sets"],["Inside"])
            self.assertFalse(
                selected["source_semantic_scene_summary"]["truncated"])
        budget=self.planner.publish(
            b.pid,"ShotMandatory",world_id="TownWorld",world_revision=1,
            camera_set="Outside",camera_prim="/World/Camera",
            sample_ticks=[0],required_sets=["Inside"],
            max_loaded_sets=2,spatial_hints=[
                {"set":"Inside","center_m":[-90000,0,0],"radius_m":0}
            ])
        with self.runtime() as r:
            selected=r.transition(
                "ShotMandatory",1,receipt_id="RequiredReceipt")
            self.assertEqual(selected["sets_actually_loaded"],
                             ["Inside","Outside"])
            self.assertEqual(selected["director_required_sets"],
                             ["Inside","Outside"])
        with self.assertRaises(ValueError):
            self.planner.publish(
                b.pid,"ImpossibleBudget",world_id="TownWorld",world_revision=1,
                camera_set="Outside",camera_prim="/World/Camera",
                sample_ticks=[0],required_sets=["Inside"],
                max_loaded_sets=1)

    def test_interruption_destroys_partial_work_and_restart_reloads_from_original(self):
        b=self.b
        with self.runtime() as r:
            with self.assertRaises(InterruptedError):
                r.transition(
                    "ShotInside",1,receipt_id="InterruptedReceipt",
                    should_cancel=lambda:True)
            self.assertTrue(r.closed)
        aborted = b.index.read_revision(b.pid,"InterruptedReceipt",1)
        self.assertEqual(aborted["data"]["state"],"INTERRUPTED")
        self.assertTrue(
            aborted["data"]["recoverable_from_original_film_sources"])
        # This is a NEW native USD context, not revival of an orphan
        # process. Only original FilmIndex scene and exact camera are used.
        reopened=FilmShotWorkingSet(
            FilmIndex(Studio(b.db)),b.pid,"TownWorld",1)
        with reopened as r:
            recovered=r.transition(
                "ShotInside",1,receipt_id="RecoveredReceipt")
            self.assertTrue(recovered["camera_positions_reopened_exactly"])
            self.assertEqual(recovered["sets_actually_loaded"],["Inside"])
        self.assertEqual(
            b.index.read_revision(b.pid,"InterruptedReceipt",1)["data"]["state"],
            "INTERRUPTED")
        with self.assertRaises(RuntimeError):
            reopened.transition(
                "ShotInside",1,receipt_id="ShouldNotRunAfterClose")

    def test_resource_guard_fails_closed_and_does_not_admit_fake_gpu_proof(self):
        b=self.b
        with self.assertRaises(ValueError):
            self.runtime(max_device_gpu_used_bytes=1024)
        with self.runtime(
            gpu_probe=lambda:{
                "device_id":"CI-fixture-not-real-device",
                "used_bytes":2048,"total_bytes":4096,
            },max_device_gpu_used_bytes=1000) as r:
            with self.assertRaises(MemoryError):
                r.transition(
                    "ShotOutside",1,receipt_id="BudgetDeniedReceipt")
            self.assertTrue(r.closed)
        refused=b.index.read_revision(b.pid,"BudgetDeniedReceipt",1)
        self.assertEqual(refused["data"]["state"],"FAILED")
        self.assertEqual(refused["data"]["failure_type"],"MemoryError")
        with self.runtime() as r:
            result=r.transition(
                "ShotOutside",1,receipt_id="NoNativeGpuProbe")
            self.assertIsNone(result["resource_after"]["gpu_device_used_bytes"])
            self.assertFalse(result["gpu_attributable_to_stage_verified"])

    def test_other_project_or_wrong_world_cannot_receive_source_shot(self):
        b=self.b
        foreign=b.studio.create_project("Second independent film","")["id"]
        with self.assertRaises(KeyError):
            self.planner.inspect(foreign,"ShotOutside",1)
        b.world.publish(
            b.pid,"DifferentWorld",sets=b.sets,
            props=[],variants=[],instancers=[])
        with FilmShotWorkingSet(
            b.index,b.pid,"DifferentWorld",1) as r:
            with self.assertRaises(PermissionError):
                r.transition(
                    "ShotOutside",1,receipt_id="WrongWorldReceipt")
        with self.assertRaises(KeyError):
            b.index.read_revision(b.pid,"WrongWorldReceipt",1)

    def test_real_os_gpu_adapter_labels_windows_budget_vs_global_sensor(self):
        from backend.nvp_resource_guard import ResourceSnapshot, GPUResource
        snapshots=ResourceSnapshot(
            1.0,16384,12288,None,(
                GPUResource("dxgi:0","Test Windows Adapter",
                            "windows_dxgi_process_budget",2048,512,False),
                GPUResource("nvidia:0","Test NVIDIA Adapter",
                            "nvml_global",8192,3072,True),
            ))
        with patch("backend.nvp_resource_guard.collect_resources",
                   return_value=snapshots):
            dxgi=native_gpu_device_sampler("dxgi:0")()
            self.assertEqual(dxgi["scope"],"os_process_video_budget")
            self.assertEqual(dxgi["used_bytes"],512*1024*1024)
            self.assertEqual(dxgi["total_bytes"],2048*1024*1024)
            global_gpu=native_gpu_device_sampler("nvidia:0")()
            self.assertEqual(global_gpu["scope"],"device_global")
            with self.assertRaises(RuntimeError):
                native_gpu_device_sampler("missing:0")()
        # These are synthetic sensor contracts, NOT native hardware evidence.
        with self.runtime(gpu_probe=lambda:global_gpu) as runtime:
            done=runtime.transition(
                "ShotOutside",1,receipt_id="LabeledGpuContract")
            self.assertEqual(
                done["resource_after"]["gpu_measurement_scope"],
                "device_global")
            self.assertFalse(done["gpu_attributable_to_stage_verified"])

    def test_missing_required_os_rss_sensor_refuses_budget_bypass(self):
        with self.runtime(max_process_rss_bytes=100*1024*1024) as r:
            with patch("backend.nvp_usd_film01d_shot_working_set._rss_bytes",
                       return_value=None):
                with self.assertRaises(RuntimeError):
                    r.transition(
                        "ShotOutside",1,receipt_id="UnmeasuredMemoryRejected")
        row=self.b.index.read_revision(
            self.b.pid,"UnmeasuredMemoryRejected",1)
        self.assertEqual(row["data"]["state"],"FAILED")
        self.assertEqual(row["data"]["failure_type"],"RuntimeError")

    def test_typed_shot_rejects_spoofed_prim_unknown_set_or_broken_ticks(self):
        b=self.b
        base={
            "world_id":"TownWorld","world_revision":1,
            "camera_set":"Outside","camera_prim":"/World/Camera",
            "sample_ticks":[0,T],"required_sets":["Outside"],
            "max_loaded_sets":1,
        }
        variants=[
            {"sample_ticks":[T,0]},
            {"sample_ticks":[True]},
            {"required_sets":["Outside","Unknown"]},
            {"director_looks":{"Facade":"NotAnOriginalLook"}},
            {"spatial_hints":[{
                "set":"NotASet","center_m":[0,0,0],"radius_m":1
            }]},
            {"prefetch_distance_m":float("inf")},
            {"camera_prim":"/World/Key"},
            {"camera_prim":"/World/StreetLamp"},
        ]
        for i,change in enumerate(variants):
            with self.subTest(case=i):
                with self.assertRaises((ValueError,PermissionError,RuntimeError)):
                    self.planner.publish(
                        b.pid,"RejectedShot"+str(i),
                        **{**base,**change})
                with self.assertRaises(KeyError):
                    b.index.read_revision(
                        b.pid,"RejectedShot"+str(i),1)

    def test_concise_source_query_does_not_dump_usda_or_invent_actor_ids(self):
        with self.runtime() as r:
            record = r.transition(
                "ShotOutside",1,receipt_id="SemanticQuery")
            query=record["source_semantic_scene_summary"]
            self.assertLessEqual(len(query["entries"]),128)
            self.assertIn("camera",{x["role"] for x in query["entries"]})
            self.assertIn("actor",{x["role"] for x in query["entries"]})
            self.assertTrue(all(
                "ActorID" not in x and set(x)=={"set","path","role"}
                for x in query["entries"]))
            self.assertTrue(query["authoritative_source_only"])
            self.assertFalse(record["renderer_frames_produced"])


if __name__ == "__main__":
    unittest.main()
