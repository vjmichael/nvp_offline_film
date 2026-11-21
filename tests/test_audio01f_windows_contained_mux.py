"""Windows: run real AUDIO-01F technical mux inside existing Job Object.

This proves constrained process execution and shutdown of a real FFmpeg mux.
It is not yet the creator-authorized production AUDIO-01F native scheduler.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave

from backend.nvp_worker_containment import launch_contained
from backend.nvp_audio01f_picture_sound import mux_picture_sound_review


@unittest.skipUnless(os.name=="nt" and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Requires Windows + actual FFmpeg")
class NativeContainedPictureSound(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.picture=self.root/"silent.mov"
        self.sound=self.root/"mix.wav"
        subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-xerror",
            "-f","lavfi","-i","testsrc2=size=256x144:rate=24",
            "-frames:v","24","-c:v","prores_ks","-profile:v","3",
            "-pix_fmt","yuv422p10le","-an",str(self.picture)],
            check=True,timeout=60)
        with wave.open(str(self.sound),"wb") as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
            w.writeframes(struct.pack("<hh",250,-250)*48000)

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_contained_ffmpeg_mux_exact_picture_and_sound(self):
        out=self.root/"sync.mov"
        repo=Path(__file__).resolve().parents[1]
        script=(
            "import sys;"
            "from backend.nvp_audio01f_picture_sound import mux_picture_sound_review;"
            "mux_picture_sound_review(sys.argv[1],sys.argv[2],sys.argv[3],frames=24)"
        )
        with (self.root/"stdout").open("wb") as stdout, (self.root/"stderr").open("wb") as stderr:
            proc=launch_contained([sys.executable,"-c",script,
                str(self.picture),str(self.sound),str(out)],
                cwd=str(repo),stdout=stdout,stderr=stderr,memory_mb=1024)
            try:
                self.assertEqual(proc.wait(timeout=90),0)
            finally:
                proc.close()
        self.assertTrue(out.is_file())
        # Fresh independent host verification, not worker-provided claims.
        from backend.nvp_audio01f_picture_sound import _verify_streams,_decoded_sha,_wav_pcm_proof
        self.assertEqual(_verify_streams(out,24,"ffprobe")["samples_per_channel"],48000)
        self.assertEqual(_decoded_sha(out,"audio","ffmpeg")[0],
                         _wav_pcm_proof(self.sound)[0])

    def test_actual_contained_mux_worker_can_be_killed(self):
        # Place a real worker inside Job Object and hold it AFTER completing a
        # verified mux; the host must still be able to terminate the worker.
        out=self.root/"interrupted.mov"
        marker=self.root/"mux_completed.ready"
        repo=Path(__file__).resolve().parents[1]
        script=(
            "import sys,time;"
            "from pathlib import Path;"
            "from backend.nvp_audio01f_picture_sound import mux_picture_sound_review;"
            "mux_picture_sound_review(sys.argv[1],sys.argv[2],sys.argv[3],frames=24);"
            "Path(sys.argv[4]).write_text('ready');"
            "time.sleep(120)"
        )
        with (self.root/"stdout").open("wb") as stdout, (self.root/"stderr").open("wb") as stderr:
            proc=launch_contained([sys.executable,"-c",script,
                str(self.picture),str(self.sound),str(out),str(marker)],
                cwd=str(repo),stdout=stdout,stderr=stderr,memory_mb=1024)
            try:
                deadline=time.monotonic()+55
                while time.monotonic()<deadline and not marker.exists():
                    if proc.poll() is not None:
                        raise RuntimeError("Mux child exited before termination marker")
                    time.sleep(.05)
                self.assertTrue(marker.exists(),"Mux child did not reach OS termination point")
                proc.terminate_tree()
                self.assertIsNotNone(proc.poll())
            finally:
                if proc.poll() is None:
                    proc.terminate_tree()
                proc.close()
        self.assertTrue(out.is_file())


if __name__=="__main__":
    unittest.main()
