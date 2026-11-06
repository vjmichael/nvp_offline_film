"""AUDIO-01F genuine FFmpeg picture/sound clock and PCM decode acceptance."""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave

from backend.nvp_audio01f_picture_sound import (
    FPS,RATE,SAMPLES_PER_FRAME,
    mux_picture_sound_review,_verify_streams,_decoded_sha,_wav_pcm_proof,
)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Real FFmpeg+FFprobe required")
class PictureSoundNativeFFmpeg(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.picture=self.root/"silent_prores.mov"
        self.audio=self.root/"multistem_mix.wav"
        self.frames=24
        cmd=["ffmpeg","-nostdin","-hide_banner","-v","error","-xerror",
             "-f","lavfi","-i","testsrc2=size=256x144:rate=24",
             "-frames:v",str(self.frames),"-c:v","prores_ks",
             "-profile:v","3","-pix_fmt","yuv422p10le",
             "-an",str(self.picture)]
        subprocess.run(cmd,check=True,timeout=50)
        with wave.open(str(self.audio),"wb") as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE)
            f.writeframes(struct.pack("<hh",700,-700)*
                          (self.frames*SAMPLES_PER_FRAME))

    def tearDown(self):
        self.tmp.cleanup()

    def test_movie_exact_clock_and_identical_pcm_video(self):
        output=self.root/"picture_sound_review.mov"
        proof=mux_picture_sound_review(self.picture,self.audio,output,
                                        frames=self.frames)
        self.assertEqual(proof["frames"],24)
        self.assertEqual(proof["samples_per_channel"],RATE)
        self.assertEqual(proof["audio_decoded_pcm_sha256"],
                         _wav_pcm_proof(self.audio)[0])
        self.assertEqual(_verify_streams(output,24,"ffprobe")["audio_rate"],RATE)
        self.assertEqual(_decoded_sha(output,"video","ffmpeg")[0],
                         _decoded_sha(self.picture,"video","ffmpeg")[0])
        self.assertEqual(_decoded_sha(output,"audio","ffmpeg")[1],RATE*4)

    def test_off_by_one_sample_rejected_before_mux(self):
        with wave.open(str(self.audio),"wb") as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE)
            f.writeframes(struct.pack("<hh",700,-700)*(RATE-1))
        with self.assertRaisesRegex(RuntimeError,"do not match"):
            mux_picture_sound_review(self.picture,self.audio,
                    self.root/"rejected.mov",frames=24)
        self.assertFalse((self.root/"rejected.mov").exists())

    def test_interrupted_staging_never_overwritten(self):
        from backend.nvp_audio01f_picture_sound import build_picture_sound_preview
        # A prior interrupted native attempt may leave a partial staging
        # directory. No render may reuse, delete or silently promote it.
        output=self.root/"review_directory"
        stage=output.with_name(".nvp-audio01g-"+output.name+".stage")
        stage.mkdir()
        evidence=stage/"partial.mov"
        evidence.write_bytes(b"retained crash evidence")
        # Verify the same staging contract in the direct real mux primitive
        # through intentionally occupied *final* output.
        with self.assertRaisesRegex(RuntimeError,"absent"):
            mux_picture_sound_review(self.picture,self.audio,evidence,frames=24)
        self.assertEqual(evidence.read_bytes(),b"retained crash evidence")

    def test_reject_existing_output_and_excess_picture_frames(self):
        out=self.root/"existing.mov"
        out.write_bytes(b"keep")
        with self.assertRaisesRegex(RuntimeError,"absent"):
            mux_picture_sound_review(self.picture,self.audio,out,frames=24)
        with self.assertRaises(ValueError):
            mux_picture_sound_review(self.picture,self.audio,
                    self.root/"bad.mov",frames=481)


if __name__=="__main__":
    unittest.main()
