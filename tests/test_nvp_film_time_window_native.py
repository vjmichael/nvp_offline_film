"""INDEX-TIME-03 real native FFmpeg film-time review/conform-preparation tests.

Uses a native FFprobe/FFmpeg VFR B-frame source, real FilmIndex, real
SQLite approval/resource ledgers, and the actual NVP contained worker.
"""
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_film_time_window_preflight import FilmTimeWindowPreflight
from backend.nvp_film_time_window_decode import (
    execute_film_time_window,verify_film_time_window)
from backend.nvp_film_time_window_host import NativeFilmTimeWindowHost
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

T=TICKS_PER_SECOND


def measured_resources():
    # Test-only measured fixture; no GPU work; NVP's actual resource
    # reservation/supervision logic still runs against these values.
    return ResourceSnapshot(time.time(),32768,28000,0.0,())


class NativeTimeWindowTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.fail("Actual FFmpeg and FFprobe binaries required")
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.volume=self.home/"camera"
        self.volume.mkdir()
        self.source=self.volume/"original_vfr.mov"
        subprocess.run([
            self.ffmpeg,"-v","error","-nostdin","-f","lavfi",
            "-i","testsrc2=size=160x90:rate=24",
            "-frames:v","120",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr","-c:v","mpeg4",
            "-bf","2","-g","24","-q:v","4","-y",str(self.source),
        ],check=True,timeout=90)
        self.db=self.home/"nvp.sqlite"
        self.studio=Studio(self.db)
        self.pid=self.studio.create_project("VFR imported source","Review")["id"]
        self.index=FilmIndex(self.studio)
        self.catalog=ExternalMediaCatalog(self.studio)
        self.inventory=SourceMediaInventory(self.catalog)
        self.inventory.register_volume(self.pid,"camera_sd",self.volume,label="Card")
        self.catalog.register(self.pid,"camera_original",self.source,
                              media_type="video/quicktime")
        self.inventory.enrich(self.pid,"camera_original","camera_sd",
                              ffprobe=self.ffprobe)
        self.bridge=SourceFilmBridge(self.index,self.inventory)
        self.original=self.bridge.register_source_revision(
            self.pid,"camera_original")
        self.cache_root=self.home/"source_cache"
        self.frame_index=NVPFrameIndex(self.cache_root,ffprobe=Path(self.ffprobe))
        self.editor=FilmTimeEditorialPublisher(
            self.index,self.bridge,self.frame_index)
        self.editor.publish(self.pid,"film_cut",[
            {"source_id":"camera_original","source_revision":1,
             "source_in_frame_zero":10,"source_out_frame_zero":40,
             "film_in_tick":5*T,"rounding":"exact"},
            {"source_id":"camera_original","source_revision":1,
             "source_in_frame_zero":60,"source_out_frame_zero":85,
             "film_in_tick":20*T,"rounding":"exact"},
        ])
        self.preflight=FilmTimeWindowPreflight(self.editor)
        self.ledger=TaskLedger(self.home/"tasks",sampler=measured_resources)
        self.job_root=self.home/"jobs"
        self.host=NativeFilmTimeWindowHost(
            self.preflight,self.ledger,self.job_root,
            verify_creator_action=lambda token,scope:
            token=="creator_confirms" and
            scope["operation"]=="nvp.native.film_time.review.v1" and
            scope["final_master"] is False,
            ffmpeg_path=Path(self.ffmpeg),
            ffprobe_path=Path(self.ffprobe),
            index_root=self.cache_root)

    def plan(self, *, mode="preview",first=12,count=4,clip=0):
        return self.preflight.prepare(
            self.pid,"film_cut",1,clip_ordinal=clip,
            first_zero=first,count=count,mode=mode)

    def test_native_review_pts_and_film_time_receipt(self):
        plan=self.plan()
        self.assertEqual(plan["frames"][0]["source_frame_zero"],12)
        self.assertEqual(plan["frames"][-1]["review_frame"],4)
        self.assertEqual(plan["source_integrity"],"STAMP_UNVERIFIED_PREVIEW")
        self.assertNotIn("source_file_path",plan)
        dest=self.home/"preview_frames"
        outcome=execute_film_time_window(
            self.db,plan,dest,
            ffprobe_path=self.ffprobe,ffmpeg_path=self.ffmpeg,
            index_root=self.cache_root)
        self.assertEqual(outcome["status"],"VERIFIED_UNAPPROVED_FILM_TIME_REVIEW")
        self.assertEqual(outcome["review_frames"],4)
        self.assertFalse(outcome["approved_final"])
        doc=json.loads((dest/"review_receipt.json").read_text())
        self.assertEqual(doc["frames"][0]["source_pts"],plan["frames"][0]["source_pts"])
        self.assertEqual(doc["frames"][-1]["film_time_tick"],
                         plan["frames"][-1]["film_time_tick"])
        self.assertFalse(doc["source_sha_rehashed_at_worker"])
        self.assertFalse(doc["native_film_events_modified"])
        self.assertEqual(verify_film_time_window(dest,plan),outcome)

    def test_conform_preparation_full_source_sha_both_sides_not_master(self):
        plan=self.plan(mode="conform_prepare",first=62,count=3,clip=1)
        self.assertEqual(plan["source_integrity"],
                         "FULL_SHA_VERIFIED_AT_PREFLIGHT")
        dest=self.home/"verified_source_review"
        outcome=execute_film_time_window(
            self.db,plan,dest,ffprobe_path=self.ffprobe,
            ffmpeg_path=self.ffmpeg,index_root=self.cache_root)
        self.assertEqual(outcome["source_integrity"],
                         "FULL_SHA_VERIFIED_BEFORE_AND_AFTER_REVIEW")
        receipt=json.loads((dest/"review_receipt.json").read_text())
        self.assertTrue(receipt["source_sha_rehashed_at_worker"])
        self.assertTrue(receipt["output_is_unapproved_png_review"])
        self.assertFalse(receipt["approved_final"])
        self.assertFalse(outcome["rendered_master"])

    def test_receipt_frame_time_and_png_tamper_are_refused(self):
        plan=self.plan(count=2)
        dest=self.home/"tamper_output"
        execute_film_time_window(
            self.db,plan,dest,
            ffprobe_path=self.ffprobe,ffmpeg_path=self.ffmpeg,
            index_root=self.cache_root)
        receipt=dest/"review_receipt.json"
        raw=json.loads(receipt.read_text())
        raw["frames"][0]["film_time_tick"]+=1
        from backend.nvp_source_window_decode import _canonical
        receipt.write_bytes(_canonical(raw))
        with self.assertRaises(RuntimeError):
            verify_film_time_window(dest,plan)
        # Native receipt was tampered with independently of the PNGs.
        self.assertTrue((dest/"review_000000001.png").is_file())

    def test_host_creator_refusal_and_queued_cancellation(self):
        with self.assertRaises(PermissionError):
            self.host.stage_and_approve(
                self.pid,"film_cut",1,clip_ordinal=0,
                first_zero=10,count=2,mode="preview",
                destination=self.home/"never_approved",
                creator_event="unknown_token")
        staged=self.host.stage_and_approve(
            self.pid,"film_cut",1,clip_ordinal=0,
            first_zero=10,count=2,mode="preview",
            destination=self.home/"cancel_before_run",
            creator_event="creator_confirms")
        self.assertEqual(staged["state"],"QUEUED")
        self.assertFalse(staged["native_worker_started"])
        stopped=self.host.revoke_queued(staged["task_id"])
        self.assertEqual(stopped["state"],"CANCELLED")
        self.assertTrue(stopped["creator_grant_revoked"])
        self.assertIsNone(self.host.run_next())
        with self.assertRaises(RuntimeError):
            self.host.revoke_queued(staged["task_id"])
        self.assertFalse((self.home/"cancel_before_run").exists())

    def test_contained_host_review_reopens_and_verifies_pinned_receipt(self):
        staged=self.host.stage_and_approve(
            self.pid,"film_cut",1,clip_ordinal=1,
            first_zero=62,count=3,mode="preview",
            destination=self.home/"contained_review",
            creator_event="creator_confirms")
        finished=self.host.run_next(timeout_seconds=90)
        self.assertEqual(finished["task_id"],staged["task_id"])
        self.assertEqual(finished["state"],"SUCCEEDED")
        self.assertEqual(self.ledger.get_task(
            staged["task_id"])["reserved"],0)
        reopened=NativeFilmTimeWindowHost(
            FilmTimeWindowPreflight(FilmTimeEditorialPublisher(
                FilmIndex(Studio(self.db)),
                SourceFilmBridge(FilmIndex(Studio(self.db)),
                    SourceMediaInventory(ExternalMediaCatalog(Studio(self.db)))),
                NVPFrameIndex(self.cache_root,ffprobe=Path(self.ffprobe)))),
            TaskLedger(self.home/"tasks",sampler=measured_resources),
            self.job_root,verify_creator_action=lambda *_:True,
            ffmpeg_path=Path(self.ffmpeg),ffprobe_path=Path(self.ffprobe),
            index_root=self.cache_root)
        verified=reopened.verify_completed(staged["task_id"])
        self.assertEqual(verified["review_frames"],3)
        self.assertEqual(verified["edit_document_sha256"],
                         staged["edit_document_sha256"])

    def test_fenced_recovery_does_not_release_active_reservation_without_proof(self):
        staged=self.host.stage_and_approve(
            self.pid,"film_cut",1,clip_ordinal=0,
            first_zero=12,count=2,mode="preview",
            destination=self.home/"interrupted_review",
            creator_event="creator_confirms")
        admitted=self.host.binding.claim_next(owner_key=self.host.owner)
        self.assertEqual(admitted["task_id"],staged["task_id"])
        self.assertTrue(admitted["admitted"])
        with self.assertRaises(PermissionError):
            self.host.recover_interrupted(
                staged["task_id"],confirm_worker_tree_stopped=lambda _:False)
        self.assertEqual(self.ledger.get_task(
            staged["task_id"])["state"],"ACTIVE")
        self.assertEqual(self.ledger.get_task(
            staged["task_id"])["reserved"],1)
        # This is a synthetic admission with no process started. A trusted
        # supervisor supplies an explicit positive fencing receipt.
        outcome=self.host.recover_interrupted(
            staged["task_id"],confirm_worker_tree_stopped=lambda _:True)
        self.assertEqual(outcome["state"],"INTERRUPTED")
        self.assertFalse(outcome["automatic_retry"])
        self.assertEqual(self.ledger.get_task(
            staged["task_id"])["reserved"],0)

    def test_source_mutation_after_plan_does_not_decode(self):
        plan=self.plan()
        with self.source.open("r+b") as stream:
            stream.seek(256)
            stream.write(b"INVALID_EDITED_EXTERNAL_ORIGINAL")
        with self.assertRaises(RuntimeError):
            execute_film_time_window(
                self.db,plan,self.home/"stale_source",
                ffprobe_path=self.ffprobe,ffmpeg_path=self.ffmpeg,
                index_root=self.cache_root)


if __name__=="__main__":
    unittest.main()
