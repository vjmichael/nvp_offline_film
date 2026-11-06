"""AUDIO-01J real native picture+final PCM24 MOV E2E.

Real FFmpeg ProRes video, 2-stem synthesized real PCM, AUDIO-01H worker,
creator mix ACCEPT, AUDIO-01I mastering + approved audio delivery, explicit
B14 picture lock, OS-contained final AV mux, decoded frame/sample comparison.
The upstream B14 source-conform verifier is substituted ONLY for the already
prepared real ProRes fixture; native mux and FilmIndex operations are real.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_audio01j_native_host import NativeAudio01JHost
from backend.nvp_audio01j_final_av import verify_final_av
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_b14_edited_movie import FORMAT as B14_FORMAT
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from test_audio01i_native_master_delivery import setup_approved,ledger


def source_picture(cap,pid,root):
    video=root/"prores_422_hq_mov.mov"
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-xerror",
        "-f","lavfi","-i","testsrc2=size=128x72:rate=24",
        "-frames:v","24","-an","-c:v","prores_ks","-profile:v","3",
        "-pix_fmt","yuv422p10le",str(video)],check=True,timeout=120)
    digest=hashlib.sha256(video.read_bytes()).hexdigest()
    cap.index.put_media_file(pid,video,"video/quicktime")
    cap.index.register_revision(pid,"picture","presentation",{
        "format":B14_FORMAT,"status":"unapproved_silent_technical_edited_movie",
        "profile":"prores_422_hq_mov","frame_count":24,
        "movie_sha256":digest,"audio_included":False,
        "picture_locked":False,"approved_final_master":False},
        expected_revision=0,dependencies=[])
    return video


class NativeAudio01JEndToEnd(unittest.TestCase):
    def test_approved_final_picture_and_audio_make_exact_24fps_48khz_mov(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cap,pid,_=setup_approved(root)
            audio_host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            job=audio_host.stage(pid,"mixdecision",1,"candidate",
                "archive_pcm24_v1",root/"master_candidate.wav","master_create")
            self.assertEqual(audio_host.run_next(timeout_seconds=180)["state"],"SUCCEEDED")
            published=audio_host.deliver(pid,"candidate","audiofinal",
                root/"audiofinal","human_approves_audio")
            self.assertTrue(published["final_master"])
            picture_file=source_picture(cap,pid,root)
            original_picture_hash=hashlib.sha256(picture_file.read_bytes()).hexdigest()
            original_audio_hash=hashlib.sha256((root/"audiofinal"/"master.wav").read_bytes()).hexdigest()
            av=NativeAudio01JHost(cap,ledger(root),root/"avhost",
                verify_creator_action=lambda *_:True,audio_host=audio_host,
                strict_linux_tree=False)
            with patch("backend.nvp_audio01j_picture_lock.verify_edited_technical_mov",
                       return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE",
                                     "frames":24,"movie_sha256":original_picture_hash}):
                locked=av.approve_picture(pid,"picture","picturelock",root,root,root,
                    "human_locks_picture")
            self.assertEqual(locked["status"],"CREATOR_PICTURE_LOCKED")
            queued=av.stage(pid,"picturelock","audiofinal",root,
                root/"audiofinal",root/"final_av","finalfilm",
                "human_approves_final_av")
            self.assertEqual(queued["state"],"QUEUED")
            result=av.run_next(timeout_seconds=180)
            self.assertEqual(result["state"],"SUCCEEDED")
            self.assertTrue(result["final_master"])
            self.assertFalse(result["dcp_delivered"])
            self.assertEqual(result["frames"],24)
            reopened=NativeAudio01JHost(
                DigitalCapture(Studio(root/"studio.sqlite3")),ledger(root),
                root/"avhost",verify_creator_action=lambda *_:False,
                audio_host=NativeAudio01IHost(
                    DigitalCapture(Studio(root/"studio.sqlite3")),
                    ledger(root),root/"audioi",
                    verify_creator_action=lambda *_:False,strict_linux_tree=False),
                strict_linux_tree=False)
            check=reopened.verify_published(pid,"finalfilm",
                root/"final_av",root,root/"audiofinal",
                ffmpeg="ffmpeg",ffprobe="ffprobe")
            self.assertEqual(check["status"],"VERIFIED_FINAL_AV_MASTER")
            recovery=reopened.recover_completed(queued["job_id"])
            self.assertEqual(recovery["state"],"SUCCEEDED")
            self.assertFalse(recovery["rerendered"])
            with self.assertRaises(PermissionError):
                av.stage(pid,"picturelock","audiofinal",root,
                    root/"audiofinal",root/"another_av","anotherfilm",
                    "human_approves_final_av")
            self.assertEqual(hashlib.sha256(picture_file.read_bytes()).hexdigest(),
                             original_picture_hash)
            self.assertEqual(hashlib.sha256((root/"audiofinal"/"master.wav").read_bytes()).hexdigest(),
                             original_audio_hash)
            indexed=reopened.capture.index.read_revision(pid,"finalfilm",1)
            self.assertEqual(indexed["kind"],"master")
            self.assertEqual(len(indexed["dependencies"]),3)
            candidate_id=__import__("backend.nvp_audio01j_final_av",
                fromlist=["candidate_id_for"]).candidate_id_for(pid,"finalfilm")
            candidate=reopened.capture.index.read_revision(pid,candidate_id,1)
            self.assertFalse(candidate["data"]["final_master"])
            self.assertFalse(candidate["data"]["director_approved"])
            self.assertEqual(candidate["kind"],"presentation")
            self.assertFalse(indexed["data"]["dcp_delivered"])
            # A published MOV is not automatically trustworthy after byte
            # mutation: the native host must fail independent re-verification.
            with (root/"final_av"/"final_picture_sound.mov").open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaises(RuntimeError):
                reopened.verify_published(pid,"finalfilm",
                    root/"final_av",root,root/"audiofinal",
                    ffmpeg="ffmpeg",ffprobe="ffprobe")

    def test_revoked_approved_mix_cannot_be_used_for_final_av(self):
        from backend.nvp_audio01h_native_host import NativeAudio01HHost
        from backend.nvp_audio01h_loudness import analyze_wav
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cap,pid,original_host=setup_approved(root)
            audio_host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            audio_host.stage(pid,"mixdecision",1,"candidate",
                "archive_pcm24_v1",root/"master_candidate.wav","master_create")
            self.assertEqual(audio_host.run_next(timeout_seconds=180)["state"],"SUCCEEDED")
            audio_host.deliver(pid,"candidate","audiofinal",
                root/"audiofinal","human_audio_publish")
            source_picture(cap,pid,root)
            av=NativeAudio01JHost(cap,ledger(root),root/"avhost",
                verify_creator_action=lambda *_:True,audio_host=audio_host,
                strict_linux_tree=False)
            with patch("backend.nvp_audio01j_picture_lock.verify_edited_technical_mov",
                       return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE"}):
                av.approve_picture(pid,"picture","picturelock",root,root,root,
                    "human_locks_picture")
            evidence=analyze_wav(root/"processed.wav",expected_samples=48000)
            original_host.creator_decision(pid,"automatedmix","mixdecision",evidence,
                decision="REVOKE",creator_event="human_revokes_mix")
            with self.assertRaises(PermissionError):
                av.stage(pid,"picturelock","audiofinal",root,
                    root/"audiofinal",root/"blocked","finalfilm",
                    "human_final_export")
            self.assertFalse((root/"blocked").exists())

    def test_no_unapproved_sources_may_be_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cap,pid,_=setup_approved(root)
            source_picture(cap,pid,root)
            audio_host=NativeAudio01IHost(cap,ledger(root),root/"audioi",
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            av=NativeAudio01JHost(cap,ledger(root),root/"avhost",
                verify_creator_action=lambda *_:True,audio_host=audio_host,
                strict_linux_tree=False)
            with self.assertRaises(KeyError):
                av.stage(pid,"picture","missing_audio",root,root,
                    root/"blocked","master","forged")
            self.assertFalse((root/"blocked").exists())


if __name__=="__main__":
    unittest.main()
