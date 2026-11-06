"""INDEX-TIME-09 actual native picture/sound review acceptance.

Real FFmpeg/FFprobe source inputs: long GOP variable-PTS video with audible
camera PCM source sound, another silent original, and an editorial black gap.
No synthetic stubs for video decoding, mux, audio duration or original hash.
The native OS file/consent dialog is a test fixture only.
"""
from __future__ import annotations

from hashlib import sha256
import base64
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
from backend.nvp_index_time06_native_desktop import TrustedFootageDesktop
from backend.nvp_index_time09_av_proxy import (
    FORMAT,RECEIPT_FORMAT,plan,execute,verify,TICKS_PER_SECOND)
from backend.nvp_index_time09_native_host import STATUS_FORMAT

T=TICKS_PER_SECOND


class NativeWindow:
    def __init__(self):
        self.allow=True
        self.url="http://127.0.0.1:7788/"
        self.prompts=0
    def get_current_url(self):return self.url
    def create_file_dialog(self,**opts):
        raise AssertionError("A/V play cannot request an arbitrary original path")
    def create_confirmation_dialog(self,title,body):
        self.prompts+=1
        assert "Original" in body or "original" in body
        return self.allow


class SourceAudioVideoTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.fail("Native FFmpeg/FFprobe are mandatory")
        self.temp=TemporaryDirectory(prefix="index09-native-real-")
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.audible=root/"camera_with_sound.mov"
        self.silent=root/"silent_camera.mov"
        def run(args):
            result=subprocess.run(args,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,timeout=120)
            if result.returncode:
                self.fail(result.stderr.decode("utf8","replace")[-1000:])
        run([
            self.ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
            "-f","lavfi","-i","sine=frequency=440:sample_rate=48000",
            "-frames:v","90",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr",
            "-c:v","mpeg4","-bf","2","-g","12","-q:v","5",
            "-c:a","aac","-shortest","-y",str(self.audible),
        ])
        run([
            self.ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
            "-frames:v","90","-c:v","mpeg4",
            "-bf","2","-g","12","-q:v","5","-y",str(self.silent),
        ])
        self.source_hashes={
            "sound":sha256(self.audible.read_bytes()).hexdigest(),
            "silent":sha256(self.silent.read_bytes()).hexdigest(),
        }
        self.studio=Studio(root/"nvp_studio.sqlite3")
        self.pid=self.studio.create_project("Native actual A/V","")["id"]
        index=FilmIndex(self.studio)
        catalog=ExternalMediaCatalog(self.studio)
        inventory=SourceMediaInventory(catalog)
        inventory.register_volume(self.pid,"volume",root,label="Camera drive")
        for sid,path in (("sound",self.audible),("silent",self.silent)):
            catalog.register(self.pid,sid,path,media_type="video/quicktime")
            inventory.enrich(self.pid,sid,"volume",ffprobe=self.ffprobe)
        bridge=SourceFilmBridge(index,inventory)
        for sid in ("sound","silent"):
            bridge.register_source_revision(self.pid,sid)
        native=NVPFrameIndex(root/".native-source-review"/"indexes",
                             ffprobe=Path(self.ffprobe))
        self.publisher=FilmTimeEditorialPublisher(index,bridge,native)
        saved=self.publisher.publish(self.pid,"assembly",[
            {"source_id":"sound","source_revision":1,
             "source_in_frame_zero":4,"source_out_frame_zero":28,
             "film_in_tick":0,"rounding":"nearest"},
            {"source_id":"silent","source_revision":1,
             "source_in_frame_zero":10,"source_out_frame_zero":34,
             "film_in_tick":2*T,"rounding":"nearest"},
        ])
        self.sha=saved["document_sha256"]
        self.window=NativeWindow()
        self.desktop=TrustedFootageDesktop(
            self.studio,origin="http://127.0.0.1:7788",
            tools=(Path(self.ffmpeg),Path(self.ffprobe)))
        self.desktop._attach_window(self.window)
        self.addCleanup(self.desktop._close)

    def req(self):
        return {
            "project_id":self.pid,"edit_id":"assembly",
            "edit_revision":1,"edit_document_sha256":self.sha,
            "start_tick":"0",
        }

    def accept(self):
        selected=self.desktop.start_synchronized_av_review(self.req())
        self.assertEqual(selected["format"],STATUS_FORMAT)
        self.assertEqual(selected["status"],"QUEUED",selected)
        self.assertFalse(selected["master_approved"])
        self.assertEqual(self.window.prompts,1)
        return selected

    def ready(self,ticket):
        until=time.monotonic()+200
        while time.monotonic()<until:
            status=self.desktop.poll_synchronized_av_review(ticket)
            if status["status"] in ("READY","RECOVERY_REQUIRED","CANCELLED"):
                if status["status"]=="RECOVERY_REQUIRED":
                    host=self.desktop._get_av_host()
                    item=host._tickets.get(ticket)
                    if item is not None:
                        folder=host.root/item["task"]
                        error_file=folder/"stderr.log"
                        stderr=(error_file.read_text("utf8","replace")[-3500:]
                                if error_file.is_file() else "(no worker stderr)")
                        task_state=host.ledger.get_task(item["task"])
                        self.fail("Native A/V recovery; task="+
                                  repr(task_state)+
                                  "; worker stderr="+stderr)
                return status
            time.sleep(.25)
        self.fail("OS-contained audio/video render never completed")

    def test_plan_tracks_real_vfr_original_pts_and_black_silent_gap(self):
        self.desktop.reader._seek_resolver()
        mapped=plan(
            self.studio,self.desktop.reader,self.pid,"assembly",1,self.sha,0,
            ffprobe=Path(self.ffprobe))
        self.assertEqual(mapped["format"],FORMAT)
        self.assertEqual([p["kind"] for p in mapped["parts"]],
                         ["source","gap","source"])
        self.assertTrue(mapped["parts"][0]["has_audio"])
        self.assertFalse(mapped["parts"][2]["has_audio"])
        self.assertEqual(mapped["sources"]["sound"]["content_sha256"],
                         self.source_hashes["sound"])
        self.assertEqual(mapped["sources"]["silent"]["content_sha256"],
                         self.source_hashes["silent"])
        self.assertLess(mapped["parts"][0]["duration_tick"],2*T)
        self.assertGreater(mapped["parts"][1]["duration_tick"],0)
        self.assertFalse(mapped["master_approved"])

    def test_actual_kernel_contained_audio_video_and_bounded_chunk_sha(self):
        approved=self.accept()
        token=approved["ticket_id"]
        done=self.ready(token)
        self.assertEqual(done["status"],"READY",done)
        self.assertEqual(done["edit_document_sha256"],self.sha)
        self.assertEqual(done["sample_rate"],48000)
        self.assertEqual(done["channels"],2)
        self.assertGreater(done["video_frames"],24)
        self.assertLess(float(done["av_drift_ms"]),50)
        parts=[]
        offset=0
        while offset<done["size_bytes"]:
            chunk=self.desktop.get_synchronized_av_chunk(token,offset)
            self.assertEqual(chunk["status"],"VERIFIED_CHUNK")
            self.assertFalse(chunk["original_modified"])
            raw=base64.b64decode(chunk["data_base64"],validate=True)
            self.assertEqual(sha256(raw).hexdigest(),chunk["sha256"])
            self.assertLessEqual(len(raw),1024*1024)
            parts.append(raw)
            offset=chunk["next_offset"]
        self.assertEqual(sha256(b"".join(parts)).hexdigest(),
                         done["media_sha256"])
        movie=self.desktop._get_av_host()._row(
            self.desktop._get_av_host()._tickets[token]["task"])["destination"]
        preview=Path(movie)/"source_review.mp4"
        # A real decoded audio waveform must be nonzero during audible clip.
        pcm=subprocess.run([
            self.ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-i",str(preview),"-t","0.3",
            "-map","0:a:0","-f","s16le","-ac","1",
            "-ar","48000","pipe:1",
        ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,
          timeout=90).stdout
        self.assertTrue(any(pcm))
        for sid,path in (("sound",self.audible),("silent",self.silent)):
            self.assertEqual(sha256(path.read_bytes()).hexdigest(),
                             self.source_hashes[sid])

    def test_native_denial_foreign_origin_and_source_stamp_refusal(self):
        self.window.allow=False
        denied=self.desktop.start_synchronized_av_review(self.req())
        self.assertEqual(denied["status"],"DENIED",denied)
        self.window.allow=True
        self.window.url="https://untrusted.example/"
        bad=self.desktop.start_synchronized_av_review(self.req())
        self.assertEqual(bad["status"],"REFRESH_REQUIRED")
        self.window.url="http://127.0.0.1:7788/"
        with self.audible.open("ab") as f:f.write(b"modified")
        changed=self.desktop.start_synchronized_av_review(self.req())
        self.assertEqual(changed["status"],"REFRESH_REQUIRED")
        self.assertEqual(self.window.prompts,1)

    def test_early_stop_never_publishes_late_native_media(self):
        selected=self.accept()
        ticket=selected["ticket_id"]
        halted=self.desktop.stop_synchronized_av_review(ticket)
        self.assertEqual(halted["status"],"CANCELLATION_REQUESTED")
        host=self.desktop._get_av_host()
        future=host._tickets[ticket]["future"]
        future.result(timeout=90)
        denied=self.desktop.poll_synchronized_av_review(ticket)
        self.assertEqual(denied["status"],"CANCELLED")
        self.assertEqual(self.desktop.get_synchronized_av_chunk(ticket,0)[
            "status"],"RECOVERY_REQUIRED")
        row=host._row(host._tickets[ticket]["task"])
        self.assertFalse((Path(row["destination"])/"source_review.mp4").exists())
        self.assertEqual(sha256(self.audible.read_bytes()).hexdigest(),
                         self.source_hashes["sound"])

    def test_new_edit_revision_cannot_reuse_old_av_proxy_ticket(self):
        selected=self.accept()
        self.assertEqual(self.ready(selected["ticket_id"])["status"],"READY")
        latest=self.publisher.publish(self.pid,"assembly",[{
            "source_id":"sound","source_revision":1,
            "source_in_frame_zero":8,"source_out_frame_zero":35,
            "film_in_tick":0,"rounding":"nearest",
        }],expected_revision=1)
        self.assertEqual(latest["revision"],2)
        obsolete=self.desktop.poll_synchronized_av_review(selected["ticket_id"])
        self.assertEqual(obsolete["status"],"RECOVERY_REQUIRED")
        self.assertEqual(self.desktop.get_synchronized_av_chunk(
            selected["ticket_id"],0)["status"],"RECOVERY_REQUIRED")
        self.assertEqual(sha256(self.audible.read_bytes()).hexdigest(),
                         self.source_hashes["sound"])

    def test_native_stop_revokes_original_video_proxy_and_source_unmodified(self):
        opened=self.accept()
        token=opened["ticket_id"]
        self.assertEqual(self.ready(token)["status"],"READY")
        before=self.desktop._get_av_host()._row(
            self.desktop._get_av_host()._tickets[token]["task"])
        movie=Path(before["destination"])/"source_review.mp4"
        self.assertTrue(movie.is_file())
        closed=self.desktop.stop_synchronized_av_review(token)
        self.assertEqual(closed["status"],"CANCELLATION_REQUESTED")
        self.assertFalse(movie.exists())
        self.assertEqual(self.desktop.get_synchronized_av_chunk(token,0)["status"],
                         "RECOVERY_REQUIRED")
        self.assertEqual(sha256(self.audible.read_bytes()).hexdigest(),
                         self.source_hashes["sound"])
        self.assertEqual(sha256(self.silent.read_bytes()).hexdigest(),
                         self.source_hashes["silent"])


if __name__=="__main__":
    unittest.main()
