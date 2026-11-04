"""AUDIO-01G real abrupt-exit filesystem + FilmIndex publication matrix.

Each case runs a separate Python process and os._exit(93) at the exact
instrumented production boundary. The media is a *real* one-second ProRes
picture + 48 kHz PCM WAV. Only the unrelated upstream B14/AUDIO-01E source
validation is stubbed; actual FFmpeg mux, SHA checks and FilmIndex storage run.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from backend.nvp_audio01f_picture_sound import build_picture_sound_preview
from backend.nvp_audio01e_wav_publication import FORMAT as AUDIO_FORMAT
from backend.nvp_audio01g_fault_matrix import EXIT_CODE
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio

FS_POINTS=(
    "stage_directory_created",
    "mov_bytes_written",
    "mov_independently_verified",
    "filmindex_media_ingested",
    "manifest_file_fsynced",
    "movie_file_fsynced",
    "staging_directory_promoted",
    "destination_parent_fsynced",
    "filmindex_presentation_registered",
)


def prepare_fixture(root):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    pid=cap.studio.create_project("AUDIO 01G crash fixture","Real media")["id"]
    picture=root/"silent.mov"
    sound=root/"mix_preview.wav"
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-xerror",
                    "-f","lavfi","-i","testsrc2=size=128x72:rate=24",
                    "-frames:v","24","-c:v","prores_ks","-profile:v","3",
                    "-pix_fmt","yuv422p10le","-an",str(picture)],
                   check=True,timeout=90)
    with wave.open(str(sound),"wb") as wav:
        wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
        wav.writeframes(struct.pack("<hh",700,-700)*48000)
    video_sha=hashlib.sha256(picture.read_bytes()).hexdigest()
    audio_sha=hashlib.sha256(sound.read_bytes()).hexdigest()
    cap.index.register_revision(pid,"sourceedit","edit",{"format":"test.edit"},
                                expected_revision=0,dependencies=[])
    cap.index.register_revision(pid,"picture","presentation",{
        "audio_included":False,"approved_final_master":False,
        "frame_count":24,"source_edit_id":"sourceedit",
        "source_edit_revision":1,"movie_path":"silent.mov",
        "movie_sha256":video_sha},expected_revision=0,dependencies=[])
    cap.index.register_revision(pid,"sound","audio",{
        "format":AUDIO_FORMAT,"picture_bound":False,"final_mix":False,
        "total_samples_per_channel":48000,
        "wav_outputs":[{"stem_id":None,"filename":"mix_preview.wav",
                        "sha256":audio_sha}]},expected_revision=0,dependencies=[])
    (root/"project_id.txt").write_text(pid)


def child(root,point):
    pid=(root/"project_id.txt").read_text()
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    with (patch("backend.nvp_audio01f_picture_sound.verify_edited_technical_mov",
                return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE"}),
          patch("backend.nvp_audio01f_picture_sound.verify_published_wavs",
                return_value={"status":"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW"})):
        build_picture_sound_preview(cap,pid,"picture","sound",
            root,root,root,root,{}, {},root,root/("review_"+point),
            "presentation"+point.replace("_",""),
            ffmpeg="ffmpeg",ffprobe="ffprobe")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Real FFmpeg/FFprobe required")
class NativeFilesystemCrashMatrix(unittest.TestCase):
    def test_every_filesystem_boundary_exits_and_preserves_filmindex_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            prepare_fixture(root)
            pid=(root/"project_id.txt").read_text()
            cap=DigitalCapture(Studio(root/"studio.sqlite3"))
            pristine=(root/"silent.mov").read_bytes(),(root/"mix_preview.wav").read_bytes()
            repo=Path(__file__).resolve().parents[1]
            for point in FS_POINTS:
                with self.subTest(boundary=point):
                    env=os.environ.copy()
                    env["PYTHONPATH"]=str(repo)
                    env["NVP_AUDIO01G_FAULT_TEST"]="enabled"
                    env["NVP_AUDIO01G_CRASH_AFTER"]=point
                    command=[sys.executable,str(Path(__file__).resolve()),
                             "--child",str(root),point]
                    if os.name=="nt":
                        # Actual Job Object contains the Python worker *and*
                        # FFmpeg descendants, even when the worker uses
                        # os._exit instead of running cleanup handlers.
                        from backend.nvp_worker_containment import launch_contained
                        with (root/(point+".out.log")).open("wb") as out, (
                             root/(point+".err.log")).open("wb") as err, (
                             patch.dict(os.environ,env,clear=False)):
                            process=launch_contained(command,cwd=str(repo),
                                stdout=out,stderr=err,memory_mb=1024)
                            try:
                                code=process.wait(timeout=120)
                            finally:
                                if process.poll() is None:
                                    process.terminate_tree()
                                process.close()
                        error=(root/(point+".err.log")).read_text(
                            "utf8",errors="replace")
                    else:
                        proc=subprocess.run(command,env=env,cwd=repo,
                                            capture_output=True,timeout=120)
                        code=proc.returncode
                        error=proc.stderr.decode("utf8","replace")
                    self.assertEqual(code,EXIT_CODE,error[-1600:])
                    output=root/("review_"+point)
                    stage=output.with_name(".nvp-audio01g-"+output.name+".stage")
                    registered=point=="filmindex_presentation_registered"
                    if point in ("staging_directory_promoted",
                                 "destination_parent_fsynced",
                                 "filmindex_presentation_registered"):
                        self.assertTrue(output.is_dir())
                        self.assertFalse(stage.exists())
                    else:
                        self.assertTrue(stage.is_dir())
                        self.assertFalse(output.exists())
                    presentation="presentation"+point.replace("_","")
                    if registered:
                        row=cap.index.read_revision(pid,presentation,1)
                        self.assertEqual(row["data"]["final_master"],False)
                    else:
                        with self.assertRaises(KeyError):
                            cap.index.read_revision(pid,presentation)
                    self.assertEqual((root/"silent.mov").read_bytes(),pristine[0])
                    self.assertEqual((root/"mix_preview.wav").read_bytes(),pristine[1])
                    # No second render is allowed to overwrite a crashed stage.
                    if stage.exists():
                        with self.assertRaises(RuntimeError):
                            child(root,point)


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        unittest.main()
