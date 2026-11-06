"""INDEX-TIME-06 actual native window import and contained source PNG.

The window is a controlled OS-dialog fixture; the FFmpeg, native FilmIndex,
SQLite source index and original NVP OS-contained worker are real. Installed
WebView2 JavaScript is independently exercised by --smoke-window, and the
frozen app/child process by --smoke-source.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_index_time06_native_desktop import TrustedFootageDesktop

ORIGIN="http://127.0.0.1:7777"


class Window:
    def __init__(self,movie):
        self.movie=movie
        self.accept=True
        self.url=ORIGIN+"/"
        self.confirmed=0
        self.picked=0
    def get_current_url(self):
        return self.url
    def create_file_dialog(self,**options):
        assert options["allow_multiple"] is False
        self.picked+=1
        return (str(self.movie),)
    def create_confirmation_dialog(self,title,message):
        self.confirmed+=1
        assert "NVP" in title
        return self.accept


class NativeFootageTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        if not (self.ffmpeg and self.ffprobe):
            self.fail("Actual native FFmpeg and FFprobe are required")
        self.temp=TemporaryDirectory(prefix="nvp-index06-tests-")
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.movie=root/"original.mov"
        subprocess.run([
            self.ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
            "-frames:v","65",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr","-c:v","mpeg4",
            "-bf","2","-g","16","-q:v","5","-y",str(self.movie),
        ],check=True,timeout=90)
        self.original_sha=hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.studio=Studio(root/"nvp_studio.sqlite3")
        self.pid=self.studio.create_project("Real indexed video","")["id"]
        self.window=Window(self.movie)
        self.bridge=TrustedFootageDesktop(
            self.studio,origin=ORIGIN,
            tools=(Path(self.ffmpeg),Path(self.ffprobe)))
        self.bridge._attach_window(self.window)
        self.addCleanup(self.bridge._close)

    def import_original(self):
        result=self.bridge.pick_and_import_footage(self.pid)
        self.assertEqual(result["status"],"IMPORTED")
        self.assertFalse(result["original_modified"])
        self.assertFalse(result["original_copied"])
        self.assertTrue(result["source_hash_verified_at_import"])
        self.assertGreater(int(result["indexed_source_frames"]),10)
        self.assertEqual(
            int(result["indexed_source_frames"])-1,
            int(result["placed_frames"]))
        return result

    def selection(self,result):
        return self.bridge.reader.seek(
            self.pid,result["edit_id"],result["edit_revision"],
            expected_edit_sha256=result["edit_document_sha256"],tick=0)

    def request(self,result,selected):
        return {
            "project_id":self.pid,
            "edit_id":result["edit_id"],"edit_revision":result["edit_revision"],
            "edit_document_sha256":result["edit_document_sha256"],
            "source_tick":"0",
            "source_frame_zero":selected["source_frame_zero"],
            "source_pts":selected["source_pts"],
        }

    def completed(self,token):
        until=time.monotonic()+160
        while time.monotonic()<until:
            answer=self.bridge.poll_source_frame_preview(token)
            if answer["status"]!="QUEUED":return answer
            time.sleep(.2)
        self.fail("Native OS-contained exact frame review timed out")

    def test_real_import_exact_pts_native_consent_and_verified_png(self):
        imported=self.import_original()
        selected=self.selection(imported)
        self.assertEqual(selected["status"],"INDEXED_SOURCE_FRAME_SELECTED")
        self.assertEqual(selected["source_frame_zero"],"0")
        ticket=self.bridge.request_source_frame_preview(
            self.request(imported,selected))
        self.assertEqual(ticket["status"],"QUEUED")
        answer=self.completed(ticket["ticket_id"])
        self.assertEqual(answer["status"],"READY",answer)
        self.assertEqual(answer["format"],"nvp.index_time06.verified_png.v1")
        self.assertEqual(answer["source_pts"],selected["source_pts"])
        self.assertEqual(answer["source_tick"],"0")
        self.assertTrue(answer["image_data_url"].startswith(
            "data:image/png;base64,"))
        self.assertEqual(answer["edit_document_sha256"],
                         imported["edit_document_sha256"])
        self.assertEqual(self.window.confirmed,2)
        self.assertFalse(answer["film_master_approved"])
        self.assertFalse(answer["original_modified"])
        self.assertEqual(hashlib.sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)
        self.assertEqual(FilmIndex(self.studio).read_revision(
            self.pid,imported["source_id"],1)["document_sha256"],
            imported["source_document_sha256"])

    def test_denied_dialog_bad_origin_and_browser_supplied_path_fail_closed(self):
        self.window.accept=False
        denied=self.bridge.pick_and_import_footage(self.pid)
        self.assertEqual(denied["status"],"DENIED")
        self.assertEqual(FilmIndex(self.studio).list_objects(
            self.pid,kind="asset"),[])
        self.window.url="https://attacker.example/"
        blocked=self.bridge.pick_and_import_footage(self.pid)
        self.assertEqual(blocked["status"],"FAILED")
        self.assertNotIn(str(self.movie),str(blocked))
        self.window.url=ORIGIN+"/"
        self.window.accept=True
        imported=self.import_original()
        selected=self.selection(imported)
        command=self.request(imported,selected)
        command["source_path"]=str(self.movie)
        blocked=self.bridge.request_source_frame_preview(command)
        self.assertEqual(blocked["status"],"FAILED")
        self.assertNotIn(str(self.movie),str(blocked))

    def test_sealed_edit_and_original_bytes_reject_stale_preview(self):
        imported=self.import_original()
        selected=self.selection(imported)
        command=self.request(imported,selected)
        command["edit_document_sha256"]="f"*64
        self.assertEqual(self.bridge.request_source_frame_preview(
            command)["status"],"FAILED")
        self.assertEqual(self.window.confirmed,1)
        # Changed original bytes can never silently turn into a verified PNG.
        with self.movie.open("ab") as fp:
            fp.write(b"changed original")
        self.assertEqual(self.bridge.request_source_frame_preview(
            self.request(imported,selected))["status"],"FAILED")

    def test_queued_creator_cancellation_never_leaks_picture(self):
        imported=self.import_original()
        selected=self.selection(imported)
        gate=threading.Event()
        blocker=self.bridge._executor.submit(lambda:gate.wait(20))
        try:
            ticket=self.bridge.request_source_frame_preview(
                self.request(imported,selected))
            self.assertEqual(ticket["status"],"QUEUED")
            cancelled=self.bridge.cancel_source_frame_preview(
                ticket["ticket_id"])
            self.assertEqual(cancelled["status"],"CANCELLATION_REQUESTED")
        finally:
            gate.set()
            blocker.result(timeout=10)
        result=self.completed(ticket["ticket_id"])
        self.assertEqual(result["status"],"CANCELLED")
        self.assertNotIn("image_data_url",result)
        self.assertEqual(hashlib.sha256(self.movie.read_bytes()).hexdigest(),
                         self.original_sha)

    def test_tampered_completed_png_never_delivered(self):
        imported=self.import_original()
        selected=self.selection(imported)
        ticket=self.bridge.request_source_frame_preview(
            self.request(imported,selected))
        self.assertEqual(self.completed(ticket["ticket_id"])["status"],"READY")
        task=self.bridge._tickets[ticket["ticket_id"]]["task_id"]
        private=self.bridge._get_host()._row(task)
        png=Path(private["destination"])/"review_000000001.png"
        with png.open("ab") as fd:fd.write(b"bad review evidence")
        tampered=self.bridge.poll_source_frame_preview(ticket["ticket_id"])
        self.assertEqual(tampered["status"],"RECOVERY_REQUIRED")
        self.assertNotIn("image_data_url",tampered)


if __name__=="__main__":
    unittest.main()
