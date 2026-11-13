"""SLATE-05: source-bounded low-fi preview, true Take SHA and cache trust tests.

Native pxr is required. The full Blender worker smoke runs separately on
machines with NVP_NATIVE_BLENDER_EXECUTABLE set. Fake preview output tests
must NEVER be described as independent native rendering acceptance.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zlib

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_slate_lazy_preview import SlateLazyPreview
from backend.nvp_slate_proxy_recipe import (
    capture_proxy,preview_cache_key,BLENDER_SCRIPT,sha,recipe)
from backend.nvp_slate_preview_cache import SlatePreviewCache
from backend.nvp_slate_preview_host import NativeSlatePreviewHost
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot

T=TICKS_PER_SECOND


def _png(width,height):
    """A properly CRC-encoded tiny RGB PNG fixture. Not a native render."""
    def part(name,data):
        return (struct.pack(">I",len(data))+name+data+
                struct.pack(">I",zlib.crc32(name+data)&0xffffffff))
    scan=b"".join(b"\x00"+b"\x84\xac\xd2"*(width) for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"+
        part(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+
        part(b"IDAT",zlib.compress(scan,9))+
        part(b"IEND",b""))


def _measured():
    return ResourceSnapshot(1,32768,25000,0,())


class Slate05NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.studio=Studio(root/"film.sqlite")
        self.pid=self.studio.create_project("Native source clip editor","")["id"]
        self.index=FilmIndex(self.studio)
        self.scene=OpenUSDSceneBridge(self.index)
        self.ledger=TemporalLedger(self.index)
        self.captures=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,context:
            event=="freeze_this_take")
        self.shots=OpenUSDShotOverrides(
            self.index,verify_director_action=lambda event,context:
            event=="approve_blocking")
        self.slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        self.editor=SlateSequenceAssembly(
            self.slate,verify_editor_action=lambda event,context:
            event=="make_active" and
            context["operation"]=="nvp.slate.commit_assembled_edit.v1")
        self.scene.publish(self.pid,"scene",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Chair","role":"prop","position":[2,0,0]},
            {"path":"/World/Camera","role":"camera","position":[1,-7,4]},
            {"path":"/World/Key","role":"light","position":[1,-2,5]},
        ],curves=[{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":2*T,"position":[4,0,0]},
        ]}])
        self.index.register_revision(
            self.pid,"actor_source","performance",
            {"format":"nvp.slate05.actor_fixture","actor":"human"})
        self.ledger.publish(self.pid,"performance",[
            {"event_id":"act","event_kind":"action","subject_id":"Actor",
             "start_tick":0,"end_tick":2*T,
             "source_id":"actor_source","source_revision":1,
             "payload":{"usd_prim_path":"/World/Actor","action":"walk"}},
        ],duration_tick=3*T)
        self.captures.freeze(
            self.pid,"take_one",scene_id="scene",scene_revision=1,
            timeline_id="performance",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="freeze_this_take")
        self.shots.publish(
            self.pid,"close_angle",take_id="take_one",
            start_tick=0,end_tick=2*T,
            changes=[
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[2,0,0]}],
            purpose="framing",continuity_policy="intentional_cheat",
            reason="Camera needs actor offset for clear facial framing",
            creator_event="approve_blocking")
        original={
            "branch_id":"take_root","kind":"performance",
            "parent_id":None,"fork_tick":None,
            "group_id":"closeup","primary":True,"take_id":"take_one",
            "source_start_tick":0,"source_end_tick":3*T,
            "shot_id":None,"shot_revision":None,
            "slate":{"scene":"01","setup":"A","shot":"01A",
                     "camera":"A","take_number":1,"wild":False,
                     "script_revision":"script_01","notes":"Original"}}
        coverage={
            "branch_id":"shot_A","kind":"coverage","parent_id":"take_root",
            "fork_tick":0,"group_id":"closeup","primary":False,
            "take_id":"take_one","source_start_tick":0,
            "source_end_tick":2*T,
            "shot_id":"close_angle","shot_revision":1,
            "slate":{"scene":"01","setup":"A","shot":"01A",
                     "camera":"A","take_number":1,"wild":False,
                     "script_revision":"script_01","notes":"Close camera"}}
        self.assertIs(type(original),dict)
        self.assertIs(type(coverage),dict)
        self.slate.publish_graph(self.pid,"slate",
            scene_id="scene",scene_label="01",nodes=[original,coverage])
        self.editor.commit(
            self.pid,"cut",graph_id="slate",graph_revision=1,
            segments=[
                {"segment_id":"first","branch_id":"shot_A",
                 "source_in_tick":0,"source_out_tick":T},
                {"segment_id":"second","branch_id":"take_root",
                 "source_in_tick":T,"source_out_tick":2*T},
            ],editor_event="make_active")
        self.cache=SlatePreviewCache(root/"preview_cache",max_ready=1)
        self.task_ledger=TaskLedger(root/"activity",sampler=_measured)
        exe=Path(sys.executable).resolve()
        self.supervisor=BlenderWorkerSupervisor(
            root/"worker",blender_executable=exe,
            blender_sha256=sha_file(exe),blender_version="Blender Test",
            activity_ledger=self.task_ledger)
        self.trusted_event=object()
        self.host=NativeSlatePreviewHost(
            self.index,self.supervisor,self.task_ledger,self.cache,
            verify_creator_action=lambda event,context:
            event is self.trusted_event and
            context["operation"] in (
                "nvp.slate.authorize_lowfi_preview.v1",
                "nvp.slate.cancel_lowfi_preview.v1"))
        self.lazy=SlateLazyPreview(self.index)

    def _request(self,tick=0,quality="thumbnail"):
        return self.host.request(
            self.pid,"cut",1,film_tick=tick,quality=quality,
            creator_event=self.trusted_event)

    def _complete_fixture(self,request):
        """Simulate only a verified worker receipt, never fake a render pass."""
        row=self.cache._job(request["job_id"])
        source=self.supervisor.root/request["job_id"]/"preview.png"
        source.write_bytes(_png(row["width"],row["height"]))
        digest=sha_file(source)
        bytes_count=source.stat().st_size
        with patch.object(self.supervisor,"verify_completed",return_value={
            "state":"SUCCEEDED","outputs":{"preview.png":{
                "kind":"png","sha256":digest,"bytes":bytes_count}}}):
            return self.cache.accept_verified(self.supervisor,request["job_id"])

    def test_only_selected_take_is_loaded_and_proxy_camera_blocking_applies(self):
        ticket=self.lazy.select(self.pid,"cut",1,film_tick=T//2)
        snapshot=capture_proxy(self.index,ticket)
        actor=next(x for x in snapshot["objects"] if x["role"]=="actor")
        self.assertAlmostEqual(actor["xyz"][0],3.0,places=4)
        self.assertFalse(snapshot["original_actor_mesh_rendered"])
        self.assertEqual(snapshot["source_shot_sha256"],
                         ticket["source_shot_document_sha256"])
        key=preview_cache_key(ticket,"thumbnail")
        self.assertEqual(len(key),64)
        doc=recipe(snapshot,"thumbnail")
        self.assertEqual((doc["width"],doc["height"]),(256,144))
        self.assertIn("bpy.ops.render.render(write_still=True)",BLENDER_SCRIPT)
        self.assertTrue(doc["worker_script_sha256"])

    def test_unapproved_review_no_native_stage_or_dispatch(self):
        before=self.index.read_revision(self.pid,"take_one",1)
        with self.assertRaises(PermissionError):
            self.host.request(
                self.pid,"cut",1,film_tick=0,quality="thumbnail",
                creator_event={"clicked":True})
        self.assertEqual(
            self.index.read_revision(self.pid,"take_one",1)["document_sha256"],
            before["document_sha256"])
        self.assertEqual(self.task_ledger.snapshot()["tasks"],[])

    def test_one_approved_preview_queue_and_verified_disk_cache_hit(self):
        request=self._request()
        self.assertEqual(request["status"],"QUEUED")
        self.assertFalse(request["native_worker_started"])
        ticket=self.lazy.select(self.pid,"cut",1,film_tick=0,quality="thumbnail")
        key=preview_cache_key(ticket,"thumbnail")
        self.assertEqual(key,request["cache_key"])
        self.assertIsNone(self.cache.lookup(self.pid,key))
        png=self._complete_fixture(request)
        self.assertEqual(png["status"],"READY")
        self.assertEqual(png["cache_key"],key)
        self.assertEqual((png["width"],png["height"]),(256,144))
        delivered=self.host.read_preview_png(self.pid,key)
        self.assertEqual(delivered["mime_type"],"image/png")
        self.assertEqual(sha(delivered["png_bytes"]),png["image_sha256"])
        self.assertTrue(delivered["lowfi_proxy_only"])
        self.assertFalse(delivered["full_film_frame_approved"])
        with patch.object(self.host,"_approval_check",
                          side_effect=AssertionError("cache hit minted consent")), \
             patch("backend.nvp_slate_preview_host.capture_proxy",
                   side_effect=AssertionError("cache hit loaded OpenUSD")):
            hit=self.host.request(
                self.pid,"cut",1,film_tick=0,quality="thumbnail",
                creator_event=None)
        self.assertEqual(hit["status"],"CACHE_HIT")
        self.assertEqual(hit["image_sha256"],png["image_sha256"])
        self.assertFalse(hit["new_task_started"])

    def test_cancel_queue_no_worker_and_never_ready(self):
        request=self._request()
        receipt=self.host.cancel(request["job_id"],
                                creator_event=self.trusted_event)
        self.assertEqual(receipt["state"],"CANCELLED_QUEUED")
        self.assertFalse(receipt["worker_started"])
        self.assertIsNone(self.cache.lookup(self.pid,request["cache_key"]))
        self.assertEqual(self.task_ledger.get_task(request["task_id"])["state"],
                         "CANCELLED")

    def test_pending_preview_after_crash_is_not_auto_success_or_replayed(self):
        request=self._request()
        recovered=self.cache.recover(self.supervisor)
        self.assertEqual(recovered,[{
            "job_id":request["job_id"],"state":"INTERRUPTED",
            "output_accepted":False}])
        self.assertIsNone(self.cache.lookup(self.pid,request["cache_key"]))
        status=self.cache._job(request["job_id"])
        self.assertEqual(status["state"],"INTERRUPTED")

    def test_host_recovery_cancels_stale_queued_preview_without_worker_start(self):
        request=self._request()
        report=self.host.recover()
        self.assertEqual(report["native_worker_interrupted_job_ids"],[])
        self.assertFalse(report["native_jobs_replayed"])
        self.assertEqual(
            report["preview_cache_reconciliation"][0]["state"],"INTERRUPTED")
        self.assertTrue(report["preview_cache_reconciliation"][0][
            "queued_native_task_cancelled"])
        self.assertEqual(
            self.task_ledger.get_task(request["task_id"])["state"],"CANCELLED")
        self.assertIsNone(self.cache.lookup(self.pid,request["cache_key"]))

    def test_corrupted_png_never_served_and_lru_evicts_only_derived_bytes(self):
        first=self._request()
        verified=self._complete_fixture(first)
        path=Path(verified["png_path"])
        path.write_bytes(b"corrupted")
        self.assertIsNone(self.cache.lookup(self.pid,first["cache_key"]))
        self.assertNotEqual(self.cache._job(first["job_id"])["state"],"READY")
        # Second clean cache project source at another source tick.
        second=self._request(tick=T)
        ready=self._complete_fixture(second)
        self.assertEqual(ready["status"],"READY")
        original=self.index.read_revision(self.pid,"take_one",1)
        self.assertTrue(self.cache.lookup(self.pid,second["cache_key"]))
        self.assertEqual(
            self.index.read_revision(self.pid,"take_one",1)["document_sha256"],
            original["document_sha256"])

    def test_lru_evicts_only_old_derivative_preview_not_frozen_take(self):
        take=self.index.read_revision(self.pid,"take_one",1)
        one=self._request(tick=0)
        before=self._complete_fixture(one)
        self.assertTrue(Path(before["png_path"]).exists())
        two=self._request(tick=T)
        after=self._complete_fixture(two)
        self.assertEqual(after["status"],"READY")
        self.assertEqual(self.cache._job(one["job_id"])["state"],"EVICTED")
        self.assertFalse(Path(before["png_path"]).exists())
        self.assertTrue(Path(after["png_path"]).exists())
        self.assertEqual(
            self.index.read_revision(self.pid,"take_one",1)["document_sha256"],
            take["document_sha256"])

    def test_worker_succeeded_but_host_crashed_before_cache_publish(self):
        request=self._request()
        row=self.cache._job(request["job_id"])
        output=self.supervisor.root/request["job_id"]/"preview.png"
        output.write_bytes(_png(row["width"],row["height"]))
        digest=sha_file(output)
        with patch.object(self.supervisor,"verify_completed",return_value={
            "state":"SUCCEEDED","outputs":{"preview.png":{
                "kind":"png","sha256":digest,
                "bytes":output.stat().st_size}}}):
            recovered=self.cache.recover(self.supervisor)
        self.assertEqual(recovered,[{
            "job_id":request["job_id"],"state":"READY",
            "cache_key":request["cache_key"]}])
        self.assertEqual(
            self.cache.lookup(self.pid,request["cache_key"])["status"],"READY")
        self.assertFalse(
            self.cache.lookup(self.pid,request["cache_key"])[
                "source_data_modified"])

    def test_stale_source_ticket_and_worker_spec_fail_closed(self):
        request=self._request()
        with self.task_ledger._db() as db:
            row=db.execute("""SELECT approval_id,spec_sha256
                FROM nvp_slate_preview_consents WHERE task_id=?""",
                (request["task_id"],)).fetchone()
        operation_doc=self.task_ledger.get_task(request["task_id"])
        self.assertTrue(operation_doc)
        staged=self.supervisor.root/request["job_id"]/"slate_source_preview.json"
        staged.write_bytes(staged.read_bytes()+b" ")
        from backend.nvp_blender_worker import BlenderOperation
        with self.task_ledger._db() as db:
            raw=db.execute("""SELECT spec_json FROM authorized_task_specs
                WHERE task_id=?""",(request["task_id"],)).fetchone()[0]
        self.assertFalse(self.host._approval_check(row[0],row[1],__import__("json").loads(raw)))


@unittest.skipUnless(os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE"),
                     "Real native Blender smoke fixture not configured")
class Slate05RealBlenderSmoke(Slate05NativeTests):
    """Installed Blender + real contained process run; no mocked output."""
    def test_actual_contained_blender_produces_sha_verified_proxy_png(self):
        native=Path(os.environ["NVP_NATIVE_BLENDER_EXECUTABLE"]).resolve()
        if not native.is_file():
            self.skipTest("No actual installed Blender executable")
        version=subprocess.run(
            [str(native),"-b","--version"],capture_output=True,
            text=True,check=True,timeout=30).stdout.splitlines()[0]
        supervisor=BlenderWorkerSupervisor(
            Path(self.temp.name)/"real_blender",
            blender_executable=native,blender_sha256=sha_file(native),
            blender_version=version,activity_ledger=self.task_ledger)
        real_cache=SlatePreviewCache(Path(self.temp.name)/"real_cache")
        from backend.nvp_resource_guard import collect_resources
        actual_ledger=TaskLedger(
            Path(self.temp.name)/"real_activity",sampler=collect_resources)
        # The genuine native smoke must use OS-observed resource admission,
        # unlike the deterministic unit tests' intentionally mocked sensor.
        supervisor=BlenderWorkerSupervisor(
            Path(self.temp.name)/"real_blender",
            blender_executable=native,blender_sha256=sha_file(native),
            blender_version=version,activity_ledger=actual_ledger)
        host=NativeSlatePreviewHost(
            self.index,supervisor,actual_ledger,real_cache,
            verify_creator_action=lambda event,context:
            event is self.trusted_event and
            context["operation"]=="nvp.slate.authorize_lowfi_preview.v1")
        request=host.request(
            self.pid,"cut",1,film_tick=0,quality="thumbnail",
            creator_event=self.trusted_event,ram_mb=3072,timeout_seconds=180)
        result=host.run_next()
        self.assertEqual(result["state"],"SUCCEEDED",result)
        png=real_cache.lookup(self.pid,request["cache_key"])
        self.assertEqual(png["status"],"READY")
        self.assertEqual((png["width"],png["height"]),(256,144))
        self.assertTrue(Path(png["png_path"]).is_file())
        self.assertTrue(png["lowfi_proxy_only"])


if __name__=="__main__":
    unittest.main()
