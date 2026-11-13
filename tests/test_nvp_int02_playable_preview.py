"""INT-02D real playable AVI/PCM and explicit no-fabrication authority tests."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from unittest import TestCase
from unittest.mock import patch
import wave
from PIL import Image

from backend.nvp_int02_playable_preview import (
    _write_interleaved_avi, _verify_avi_structure,
    export_playable_edited_avi, SAMPLES_PER_FRAME,
)
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly


class PlayableAVIContract(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.frames=[]
        for i in range(3):
            png=self.path/("frame"+str(i)+".png")
            Image.new("RGB",(64,48),(i*70+10,60,100)).save(png)
            self.frames.append(png)
        self.audio=self.path/"sound.wav"
        with wave.open(str(self.audio),"wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(struct.pack("<hh",777,-777)*3*SAMPLES_PER_FRAME)

    def test_real_one_file_seekable_video_and_exact_pcm(self):
        movie=self.path/"movie.avi"
        result=_write_interleaved_avi(
            movie,self.frames,self.audio,[64,48],
            expected_sha=[sha256(x.read_bytes()).hexdigest()
                          for x in self.frames])
        self.assertEqual(result["pcm_sample_frames"],6000)
        self.assertTrue(_verify_avi_structure(
            movie,3,result["pcm_sha256"],[64,48])["complete_interleave"])
        # FFprobe is only an independent test observer, not a runtime tool.
        probe=shutil.which("ffprobe")
        if probe:
            meta=subprocess.run(
                [probe,"-v","error","-show_streams","-of","json",str(movie)],
                capture_output=True,text=True,timeout=20,check=True)
            streams=json.loads(meta.stdout)["streams"]
            self.assertEqual([x["codec_name"] for x in streams],
                             ["mjpeg","pcm_s16le"])
            self.assertEqual(streams[0]["r_frame_rate"],"24/1")
            self.assertEqual(streams[0]["nb_frames"],"3")
            self.assertEqual(streams[1]["sample_rate"],"48000")

    def test_corrupted_packet_and_false_audio_receipt_refused(self):
        movie=self.path/"movie.avi"
        proof=_write_interleaved_avi(movie,self.frames,self.audio,[64,48])
        with self.assertRaisesRegex(RuntimeError,"PCM differs"):
            _verify_avi_structure(movie,3,"0"*64,[64,48])
        raw=bytearray(movie.read_bytes())
        i=raw.find(b"01wb")
        self.assertGreater(i,0)
        raw[i:i+4]=b"02wb"
        movie.write_bytes(raw)
        with self.assertRaisesRegex(RuntimeError,"PCM interleave"):
            _verify_avi_structure(movie,3,proof["pcm_sha256"],[64,48])

    def test_cancel_never_completes_staged_movie(self):
        movie=self.path/"cancelled.avi"
        with self.assertRaises(InterruptedError):
            _write_interleaved_avi(
                movie,self.frames,self.audio,[64,48],cancelled=lambda:True)
        with self.assertRaises(RuntimeError):
            _verify_avi_structure(movie,3,"0"*64,[64,48])

    def test_host_refuses_without_separate_approval(self):
        derivative=self.path/"NVPEdit30_ProductionOne"
        derivative.mkdir()
        (derivative/"manifest.json").write_text(
            json.dumps({"presentation_id":"ProductionOne"}))
        authority=object.__new__(SlateSequenceAssembly)
        original={"edit_sha256":"e"*64,"manifest_sha256":"f"*64}
        with patch("backend.nvp_int02_playable_preview.verify_edited_film",
                   return_value=original):
            with self.assertRaisesRegex(PermissionError,"declined"):
                export_playable_edited_avi(
                    authority,"a"*32,"EditedFilm",1,derivative,
                    approve=lambda _:False)
        self.assertFalse((self.path/"NVPPreview30_ProductionOne").exists())

    def test_source_changed_during_approval_not_published(self):
        derivative=self.path/"NVPEdit30_ProductionOne"
        derivative.mkdir()
        (derivative/"manifest.json").write_text(
            json.dumps({"presentation_id":"ProductionOne"}))
        authority=object.__new__(SlateSequenceAssembly)
        with patch("backend.nvp_int02_playable_preview.verify_edited_film",
                   side_effect=[{"edit_sha256":"e"*64,"manifest_sha256":"f"*64},
                                {"edit_sha256":"e"*64,"manifest_sha256":"b"*64}]):
            with self.assertRaisesRegex(RuntimeError,"changed"):
                export_playable_edited_avi(
                    authority,"a"*32,"EditedFilm",1,derivative,
                    approve=lambda _:True)
        self.assertFalse((self.path/"NVPPreview30_ProductionOne").exists())
