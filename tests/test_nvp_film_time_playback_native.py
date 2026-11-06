"""INDEX-TIME-04 native PTS-driven Film Time seek/playback selection.

Real native VFR/long-GOP indexed source + FilmIndex placement. The seek
itself must never decode a PNG or authorize worker execution. The optional
stage_review_at path MUST route through existing creator-authorized native
source window host and OS-contained decoder.
"""
from __future__ import annotations

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
from backend.nvp_film_time_playback import FilmTimePlaybackResolver
from backend.nvp_film_time_window_host import NativeFilmTimeWindowHost
from backend.nvp_film_time_window_preflight import FilmTimeWindowPreflight
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

T=TICKS_PER_SECOND


def resource_sample():
    return ResourceSnapshot(time.time(),32768,28000,0.0,())


class FilmTimePlaybackNativeTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.fail("Native FFmpeg/FFprobe required for Film Time seek acceptance")
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.volume=self.home/"volume"
        self.volume.mkdir()
        self.movie=self.volume/"vfr_original.mov"
        subprocess.run([
            self.ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
            "-frames:v","120",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr","-c:v","mpeg4",
            "-bf","2","-g","24","-q:v","4","-y",str(self.movie)
        ],check=True,timeout=90)
        self.db_path=self.home/"nvp.sqlite"
        self.studio=Studio(self.db_path)
        self.project=self.studio.create_project("Index Playback","VFR source")["id"]
        self.index=FilmIndex(self.studio)
        self.catalog=ExternalMediaCatalog(self.studio)
        self.inventory=SourceMediaInventory(self.catalog)
        self.inventory.register_volume(self.project,"card",self.volume,label="Camera")
        self.catalog.register(
            self.project,"source_camera",self.movie,media_type="video/quicktime")
        self.inventory.enrich(
            self.project,"source_camera","card",ffprobe=self.ffprobe)
        self.bridge=SourceFilmBridge(self.index,self.inventory)
        self.bridge.register_source_revision(self.project,"source_camera")
        self.cache_root=self.home/"frames_index"
        self.native=NVPFrameIndex(self.cache_root,ffprobe=Path(self.ffprobe))
        self.edit=FilmTimeEditorialPublisher(self.index,self.bridge,self.native)
        self.edit.publish(self.project,"edit",[
            {"source_id":"source_camera","source_revision":1,
             "source_in_frame_zero":10,"source_out_frame_zero":40,
             "film_in_tick":5*T,"rounding":"exact"},
            {"source_id":"source_camera","source_revision":1,
             "source_in_frame_zero":60,"source_out_frame_zero":85,
             "film_in_tick":20*T,"rounding":"exact"},
        ])
        self.seek=FilmTimePlaybackResolver(self.edit)

    def test_actual_vfr_tick_to_correct_held_source_frame(self):
        page=self.edit.clips(self.project,"edit",1)
        clip=page["clips"][0]
        self.assertEqual(clip["source_in_frame_zero"],10)
        first=self.seek.resolve(self.project,"edit",1,tick=5*T)
        self.assertEqual(first["status"],"INDEXED_SOURCE_FRAME_SELECTED")
        self.assertEqual(first["source_frame_zero"],10)
        self.assertEqual(first["source_pts"],clip["source_in_pts"])
        self.assertEqual(first["frame_film_start_tick"],5*T)
        self.assertTrue(first["frame_film_end_tick"]>5*T)
        self.assertFalse(first["picture_rendered"])
        self.assertFalse(first["review_task_started"])
        self.assertFalse(first["source_sha_verified_this_operation"])
        self.assertLess(first["frame_index_pts_reads"],20)
        self.assertEqual(list(self.home.rglob("review_*.png")),[])
        middle=(first["frame_film_start_tick"]+
                first["frame_film_end_tick"]-1)//2
        held=self.seek.resolve(self.project,"edit",1,tick=middle)
        self.assertEqual(held["source_frame_zero"],10)
        next_frame=self.seek.resolve(
            self.project,"edit",1,tick=first["frame_film_end_tick"])
        self.assertEqual(next_frame["source_frame_zero"],11)
        self.assertEqual(next_frame["frame_film_start_tick"],
                         first["frame_film_end_tick"])

    def test_exact_end_exclusion_gaps_and_nonzero_second_placement(self):
        clip=self.edit.clips(self.project,"edit",1)["clips"][0]
        last=self.seek.resolve(
            self.project,"edit",1,tick=clip["film_end_tick"]-1)
        self.assertEqual(last["source_frame_zero"],39)
        self.assertEqual(last["next_source_frame_zero"],40)
        self.assertEqual(last["frame_film_end_tick"],clip["film_end_tick"])
        for empty_tick in (0,4*T,clip["film_end_tick"],10*T,19*T):
            gap=self.seek.resolve(self.project,"edit",1,tick=empty_tick)
            self.assertEqual(gap["status"],"EMPTY_IMPORTED_VIDEO_GAP")
            self.assertIsNone(gap["source_frame_zero"])
        second=self.seek.resolve(self.project,"edit",1,tick=20*T)
        self.assertEqual(second["clip_ordinal"],1)
        self.assertEqual(second["source_frame_zero"],60)
        self.assertEqual(second["frame_film_start_tick"],20*T)

    def test_same_source_has_distinct_film_times_across_edit_revisions(self):
        first=self.seek.resolve(self.project,"edit",1,tick=5*T)
        self.edit.publish(self.project,"edit",[
            {"source_id":"source_camera","source_revision":1,
             "source_in_frame_zero":10,"source_out_frame_zero":40,
             "film_in_tick":45*T,"rounding":"exact"},
        ],expected_revision=1)
        old=self.seek.resolve(self.project,"edit",1,tick=5*T)
        self.assertEqual(old["source_pts"],first["source_pts"])
        self.assertEqual(old["frame_film_start_tick"],5*T)
        changed=self.seek.resolve(self.project,"edit",2,tick=45*T)
        self.assertEqual(changed["source_pts"],first["source_pts"])
        self.assertEqual(changed["source_frame_zero"],first["source_frame_zero"])
        self.assertEqual(changed["frame_film_start_tick"],45*T)
        self.assertNotEqual(old["edit_document_sha256"],
                            changed["edit_document_sha256"])

    def test_restart_and_original_mutation_fail_closed(self):
        original=self.seek.resolve(self.project,"edit",1,tick=5*T)
        reopened_studio=Studio(self.db_path)
        reopened_index=FilmIndex(reopened_studio)
        reopened=FilmTimePlaybackResolver(
            FilmTimeEditorialPublisher(
                reopened_index,SourceFilmBridge(
                    reopened_index,SourceMediaInventory(
                        ExternalMediaCatalog(reopened_studio))),
                NVPFrameIndex(self.cache_root,ffprobe=Path(self.ffprobe))))
        again=reopened.resolve(self.project,"edit",1,tick=5*T)
        self.assertEqual(original["source_pts"],again["source_pts"])
        self.assertEqual(original["frame_film_end_tick"],
                         again["frame_film_end_tick"])
        with self.movie.open("r+b") as src:
            src.seek(150)
            src.write(b"ALTERED_ORIGINAL_FOOTAGE")
        with self.assertRaises(RuntimeError):
            reopened.resolve(self.project,"edit",1,tick=5*T)
        # Saved metadata can still be navigated without accepting the bytes.
        self.assertEqual(reopened.edit.clips(
            self.project,"edit",1)["clips"][0]["film_start_tick"],5*T)

    def test_only_existing_host_can_authorize_native_tick_selected_preview(self):
        ledger=TaskLedger(self.home/"ledger",sampler=resource_sample)
        host=NativeFilmTimeWindowHost(
            FilmTimeWindowPreflight(self.edit),ledger,
            self.home/"jobs",verify_creator_action=lambda event,scope:
            event=="director_approves_preview" and
            scope["operation"]=="nvp.native.film_time.review.v1" and
            scope["final_master"] is False,
            ffmpeg_path=Path(self.ffmpeg),ffprobe_path=Path(self.ffprobe),
            index_root=self.cache_root)
        gap=self.seek.stage_review_at(
            host,self.project,"edit",1,tick=10*T,
            destination=self.home/"no_media",creator_event="director_approves_preview")
        self.assertIsNone(gap["task_id"])
        self.assertFalse((self.home/"no_media").exists())
        with self.assertRaises(PermissionError):
            self.seek.stage_review_at(
                host,self.project,"edit",1,tick=5*T,
                destination=self.home/"denied",creator_event="stranger")
        selection=self.seek.stage_review_at(
            host,self.project,"edit",1,tick=5*T,
            destination=self.home/"approved_review",
            creator_event="director_approves_preview")
        self.assertEqual(selection["status"],"INDEXED_REVIEW_TASK_QUEUED")
        self.assertFalse(selection["review_task_started"])
        self.assertEqual(ledger.get_task(selection["task_id"])["state"],"QUEUED")
        result=host.run_next(timeout_seconds=90)
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertEqual(result["review_frames"],1)
        receipt=json.loads(
            (self.home/"approved_review"/"review_receipt.json").read_text())
        self.assertEqual(receipt["frames"][0]["source_frame_zero"],
                         selection["source_frame_zero"])
        self.assertEqual(receipt["frames"][0]["film_time_tick"],
                         selection["frame_film_start_tick"])
        self.assertFalse(receipt["approved_final"])
        self.assertEqual(host.verify_completed(
            selection["task_id"])["status"],
            "VERIFIED_UNAPPROVED_FILM_TIME_REVIEW")

    def test_no_cross_project_source_or_false_approval(self):
        other=self.studio.create_project("Foreign","")["id"]
        with self.assertRaises((KeyError,RuntimeError)):
            self.seek.resolve(other,"edit",1,tick=5*T)


if __name__=="__main__":
    unittest.main()
