"""INDEX-TIME-08: real variable-frame-rate original video review.

Uses real native FFmpeg, FilmIndex, SQLite, OS-contained native review workers
and independently audited PNG receipts. A fake window stands in only for the
interactive OS confirmation, which the installed GUI smoke tests separately.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_index_time06_native_desktop import TrustedFootageDesktop
from backend.nvp_index_time08_playback import FORMAT

T=TICKS_PER_SECOND


class FakeWindow:
    def __init__(self):
        self.allow=True
        self.confirmations=[]
        self.url="http://127.0.0.1:8888/"
    def get_current_url(self):
        return self.url
    def create_file_dialog(self,**kwargs):
        raise AssertionError("Playback does not open source file dialogs")
    def create_confirmation_dialog(self,title,message):
        self.confirmations.append((title,message))
        return self.allow


class OriginalAssemblyReviewTests(unittest.TestCase):
    def setUp(self):
        ffmpeg=shutil.which("ffmpeg")
        ffprobe=shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.fail("Native FFmpeg and FFprobe required for actual-source playback")
        self.temp=TemporaryDirectory(prefix="nvp-index08-real-")
        self.addCleanup(self.temp.cleanup)
        home=Path(self.temp.name)
        self.movie=home/"original.mov"
        subprocess.run([
            ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=128x72:rate=24",
            "-frames:v","64",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr","-c:v","mpeg4","-bf","2","-g","12",
            "-q:v","5","-y",str(self.movie),
        ],check=True,timeout=60)
        self.original_sha=sha256(self.movie.read_bytes()).hexdigest()
        self.studio=Studio(home/"studio.sqlite3")
        self.pid=self.studio.create_project("Original review", "Safe timeline")["id"]
        index=FilmIndex(self.studio)
        media=ExternalMediaCatalog(self.studio)
        inventory=SourceMediaInventory(media)
        inventory.register_volume(self.pid,"volume",home,label="Original camera drive")
        media.register(self.pid,"camera",self.movie,media_type="video/quicktime")
        inventory.enrich(self.pid,"camera","volume",ffprobe=ffprobe)
        bridge=SourceFilmBridge(index,inventory)
        bridge.register_source_revision(self.pid,"camera")
        frames=NVPFrameIndex(home/"indexes",ffprobe=Path(ffprobe))
        self.publisher=FilmTimeEditorialPublisher(index,bridge,frames)
        saved=self.publisher.publish(self.pid,"cut",[
            {"source_id":"camera","source_revision":1,
             "source_in_frame_zero":2,"source_out_frame_zero":9,
             "film_in_tick":0,"rounding":"nearest"},
            {"source_id":"camera","source_revision":1,
             "source_in_frame_zero":29,"source_out_frame_zero":47,
             "film_in_tick":2*T,"rounding":"nearest"},
        ])
        self.edit_sha=saved["document_sha256"]
        self.window=FakeWindow()
        self.desktop=TrustedFootageDesktop(
            self.studio,origin="http://127.0.0.1:8888",
            tools=(Path(ffmpeg),Path(ffprobe)))
        self.desktop._attach_window(self.window)
        self.addCleanup(self.desktop._close)

    def request(self):
        return {
            "project_id":self.pid,"edit_id":"cut",
            "edit_revision":1,"edit_document_sha256":self.edit_sha,
            "start_tick":"0",
        }

    def wait_done(self,ticket):
        until=time.monotonic()+200
        while time.monotonic()<until:
            value=self.desktop.poll_assembly_review(ticket)
            if value["status"] in ("COMPLETE","RECOVERY_REQUIRED","CANCELLED"):
                if value["status"]=="RECOVERY_REQUIRED":
                    session=self.desktop._get_review_playback()._sessions.get(ticket)
                    if session is not None:
                        self.fail("Real native original source playback failed: "+
                                  str(session.get("private_failure_detail",
                                                  "unknown cause")))
                return value
            time.sleep(.15)
        self.fail("Real native playback worker never reached terminal receipt")

    def test_real_crosscut_vfr_gap_and_bounded_verified_review_pictures(self):
        started=self.desktop.start_assembly_review(self.request())
        self.assertEqual(started["status"],"QUEUED",started)
        self.assertEqual(started["format"],FORMAT)
        self.assertEqual(started["planned_frames"],25)
        self.assertEqual(len(self.window.confirmations),1)
        self.assertIn("ORIGINAL video frames",self.window.confirmations[0][1])
        ticket=started["ticket_id"]
        completed=self.wait_done(ticket)
        self.assertEqual(completed["status"],"COMPLETE",completed)
        self.assertEqual(completed["ready_frames"],25)
        self.assertEqual(completed["project_id"],self.pid)
        self.assertFalse(completed["master_approved"])
        self.assertEqual(completed["source_integrity"],
                         "SOURCE_STAMP_UNVERIFIED_PREVIEW")
        listing=completed["frames"]
        self.assertEqual(listing[0]["source_frame_zero"],"2")
        self.assertEqual(listing[7]["source_frame_zero"],"29")
        self.assertEqual(listing[0]["clip_ordinal"],0)
        self.assertEqual(listing[7]["clip_ordinal"],1)
        self.assertEqual(listing[7]["film_time_tick"],str(2*T))
        self.assertLess(int(listing[6]["film_end_tick"]),
                        int(listing[7]["film_time_tick"]))
        self.assertTrue(all(int(f["film_time_tick"])<
                            int(f["film_end_tick"]) for f in listing))
        for index in (0,6,7,14,24):
            frame=self.desktop.get_assembly_review_frame(ticket,index)
            self.assertEqual(frame["status"],"VERIFIED_FRAME",frame)
            self.assertEqual(frame["source_pts"],listing[index]["source_pts"])
            self.assertEqual(frame["film_end_tick"],listing[index]["film_end_tick"])
            self.assertTrue(frame["image_data_url"].startswith(
                "data:image/png;base64,"))
            self.assertFalse(frame["original_modified"])
            self.assertFalse(frame["master_approved"])
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)
        reopened=FilmIndex(Studio(self.studio.db_path))
        self.assertEqual(reopened.read_revision(
            self.pid,"cut",1)["document_sha256"],self.edit_sha)

    def test_denied_consent_and_injected_media_path_never_launch_work(self):
        self.window.allow=False
        denied=self.desktop.start_assembly_review(self.request())
        self.assertEqual(denied["status"],"DENIED")
        self.assertEqual(len(self.window.confirmations),1)
        attack={**self.request(),"source_path":str(self.movie)}
        refused=self.desktop.start_assembly_review(attack)
        self.assertEqual(refused["status"],"REFRESH_REQUIRED")
        self.assertNotIn(str(self.movie),str(refused))
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)

    def test_creator_cancellation_excludes_frames_and_keeps_original(self):
        started=self.desktop.start_assembly_review(self.request())
        self.assertEqual(started["status"],"QUEUED")
        ticket=started["ticket_id"]
        cancelled=self.desktop.cancel_assembly_review(ticket)
        self.assertEqual(cancelled["status"],"CANCELLATION_REQUESTED")
        blocked=self.desktop.poll_assembly_review(ticket)
        self.assertEqual(blocked["status"],"CANCELLED")
        self.assertNotIn("frames",blocked)
        denied=self.desktop.get_assembly_review_frame(ticket,0)
        self.assertEqual(denied["status"],"RECOVERY_REQUIRED")
        self.assertNotIn("image_data_url",denied)
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)

    def test_tampered_png_and_superseded_edit_fail_closed(self):
        started=self.desktop.start_assembly_review(self.request())
        self.assertEqual(started["status"],"QUEUED")
        ticket=started["ticket_id"]
        self.assertEqual(self.wait_done(ticket)["status"],"COMPLETE")
        session=self.desktop._get_review_playback()._sessions[ticket]
        host=self.desktop._get_review_playback()._get_host()
        first=host._row(session["windows"][0]["task"])
        png=Path(first["destination"])/"review_000000001.png"
        with png.open("ab") as output:
            output.write(b"unapproved and altered")
        denied=self.desktop.get_assembly_review_frame(ticket,0)
        self.assertEqual(denied["status"],"RECOVERY_REQUIRED")
        self.assertNotIn("image_data_url",denied)
        self.publisher.publish(self.pid,"cut",[
            {"source_id":"camera","source_revision":1,
             "source_in_frame_zero":2,"source_out_frame_zero":9,
             "film_in_tick":T,"rounding":"nearest"},
        ],expected_revision=1)
        superseded=self.desktop.poll_assembly_review(ticket)
        self.assertEqual(superseded["status"],"RECOVERY_REQUIRED")
        self.assertNotIn("frames",superseded)
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)

    def test_temporary_preview_disposed_after_close_without_touching_capture(self):
        started=self.desktop.start_assembly_review(self.request())
        self.assertEqual(started["status"],"QUEUED")
        ticket=started["ticket_id"]
        self.assertEqual(self.wait_done(ticket)["status"],"COMPLETE")
        review=self.desktop._get_review_playback()
        session=review._sessions[ticket]
        host=review._get_host()
        receipt=host._row(session["windows"][0]["task"])
        folder=Path(receipt["destination"])
        self.assertTrue((folder/"review_000000001.png").is_file())
        original=FilmIndex(self.studio).read_revision(self.pid,"camera",1)
        self.desktop._close()
        self.assertFalse((folder/"review_000000001.png").exists())
        self.assertTrue(self.movie.is_file())
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)
        self.assertEqual(FilmIndex(Studio(self.studio.db_path)).read_revision(
            self.pid,"camera",1)["document_sha256"],
            original["document_sha256"])

    def test_stop_completed_review_disposes_pngs_not_frozen_source(self):
        started=self.desktop.start_assembly_review(self.request())
        self.assertEqual(started["status"],"QUEUED")
        ticket=started["ticket_id"]
        self.assertEqual(self.wait_done(ticket)["status"],"COMPLETE")
        review=self.desktop._get_review_playback()
        session=review._sessions[ticket]
        path=Path(review._get_host()._row(
            session["windows"][0]["task"])["destination"])
        self.assertTrue((path/"review_000000001.png").is_file())
        self.assertEqual(self.desktop.cancel_assembly_review(ticket)["status"],
                         "CANCELLATION_REQUESTED")
        self.assertFalse((path/"review_000000001.png").exists())
        denied=self.desktop.get_assembly_review_frame(ticket,0)
        self.assertEqual(denied["status"],"RECOVERY_REQUIRED")
        self.assertNotIn("image_data_url",denied)
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)

    def test_untrusted_window_origin_cannot_fetch_verified_original_pixels(self):
        started=self.desktop.start_assembly_review(self.request())
        self.assertEqual(started["status"],"QUEUED")
        ticket=started["ticket_id"]
        self.assertEqual(self.wait_done(ticket)["status"],"COMPLETE")
        self.window.url="https://other.example/"
        denied=self.desktop.get_assembly_review_frame(ticket,0)
        self.assertEqual(denied["status"],"RECOVERY_REQUIRED")
        self.assertNotIn("image_data_url",denied)
        self.window.url="http://127.0.0.1:8888/"
        self.assertEqual(self.desktop.get_assembly_review_frame(ticket,0)["status"],
                         "VERIFIED_FRAME")
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)

    def test_gap_start_seeks_next_source_clip_without_guessing_fps(self):
        session=self.desktop.start_assembly_review({
            **self.request(),"start_tick":str(T),
        })
        self.assertEqual(session["status"],"QUEUED")
        done=self.wait_done(session["ticket_id"])
        self.assertEqual(done["status"],"COMPLETE",done)
        self.assertEqual(done["frames"][0]["source_frame_zero"],"29")
        self.assertEqual(done["frames"][0]["film_time_tick"],str(2*T))
        self.assertEqual(sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)


if __name__=="__main__":
    unittest.main()
