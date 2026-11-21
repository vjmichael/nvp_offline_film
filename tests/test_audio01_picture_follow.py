"""AUDIO-01A acceptance: true WAV sample copying, provenance and edit revisions."""
import hashlib
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from backend.nvp_audio01_picture_follow import (
    RATE, SAMPLES_PER_FRAME, source_mapping, conform_pcm_audio, verify_pcm_audio
)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


class AudioFrameMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "studio.sqlite3"
        self.capture = DigitalCapture(Studio(self.db))
        self.pid = self.capture.studio.create_project("Dialog test", "An edited performance")["id"]
        self.take_id = "source_take"
        self.delivery_id = "source_delivery"
        self.edit_id = "source_edit"
        self.capture.index.register_revision(self.pid, self.take_id, "take",
                                             {"format": "test.take", "frozen": True})
        frame_meta = []
        for n in range(1, 4):
            frame_meta.append({
                "frame": n, "shot_id": "shot_A" if n != 3 else "shot_B",
                "png16_sha256": hashlib.sha256(f"png-{n}".encode()).hexdigest(),
                "rgb48_sha256": hashlib.sha256(f"rgb-{n}".encode()).hexdigest(),
                "source_exr_sha256": hashlib.sha256(f"exr-{n}".encode()).hexdigest(),
            })
        delivery = self.capture.index.register_revision(
            self.pid,self.delivery_id,"presentation",
            {"format":"test.delivery","frame_count":3,"media_frames":frame_meta},
            dependencies=[{"object_id":self.take_id,"revision":1,"role":"source_take"}])
        ordered = [3,1,1,2]
        frame_map = []
        for n,source in enumerate(ordered,1):
            r=frame_meta[source-1]
            frame_map.append({
                "edit_frame":n,"source_frame":source,"shot_id":r["shot_id"],
                "original_png16_sha256":r["png16_sha256"],
                "original_rgb48_sha256":r["rgb48_sha256"],
                "original_float32_sha256":r["source_exr_sha256"],
            })
        edit_data={
            "source_delivery_id":self.delivery_id,
            "source_delivery_sha256":delivery["document_sha256"],
            "source_take_id":self.take_id,
            "source_take_sha256":self.capture.index.read_revision(
                self.pid,self.take_id,1)["document_sha256"],
            "editorial_map":{"fps":24,"frame_count":4,"frame_map":frame_map}
        }
        self.capture.index.register_revision(self.pid,self.edit_id,"edit",edit_data,
            dependencies=[{"object_id":self.delivery_id,"revision":1,"role":"presentation"}])
        self.source = self.root/"source.wav"
        with wave.open(str(self.source),"wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            for n in (1,2,3):
                w.writeframesraw(struct.pack("<hh", n*100, -n*100)*SAMPLES_PER_FRAME)

    def tearDown(self):
        self.tmp.cleanup()

    def test_trim_repeat_reorder_copy_exact_samples_and_restart(self):
        out=self.root/"edited_audio"
        result=conform_pcm_audio(self.capture,self.pid,self.edit_id,1,
                                self.source,out,"dialogue_conform")
        self.assertEqual(result["samples"],4*SAMPLES_PER_FRAME)
        self.assertEqual(result["discontinuities"],2)
        with wave.open(str(out/"edited_picture_follow_pcm48.wav"),"rb") as w:
            self.assertEqual(w.getnframes(),8000)
            samples=w.readframes(w.getnframes())
        for i,n in enumerate([3,1,1,2]):
            assert_chunk=samples[i*SAMPLES_PER_FRAME*4:(i+1)*SAMPLES_PER_FRAME*4]
            self.assertEqual(assert_chunk,struct.pack("<hh",n*100,-n*100)*SAMPLES_PER_FRAME)
        reopened=DigitalCapture(Studio(self.db))
        verification=verify_pcm_audio(reopened,self.pid,"dialogue_conform",out)
        self.assertEqual(verification["status"],"VERIFIED_AUDIO_PICTURE_FRAME_MAPPING")
        self.assertFalse(verification["audio_mixed"])

    def test_invalid_source_sample_count_cannot_publish(self):
        with wave.open(str(self.source),"wb") as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE)
            w.writeframes(bytes(8000))
        with self.assertRaisesRegex(RuntimeError,"not aligned"):
            conform_pcm_audio(self.capture,self.pid,self.edit_id,1,
                              self.source,self.root/"invalid","bad_audio")
        with self.assertRaises(KeyError):
            self.capture.index.read_revision(self.pid,"bad_audio")

    def test_tampered_audio_is_rejected_after_restart(self):
        out=self.root/"tampered_audio"
        conform_pcm_audio(self.capture,self.pid,self.edit_id,1,
                          self.source,out,"tamper_audio")
        file=out/"edited_picture_follow_pcm48.wav"
        with file.open("r+b") as h:
            h.seek(100)
            h.write(b"nope")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            verify_pcm_audio(DigitalCapture(Studio(self.db)),self.pid,"tamper_audio",out)

    def test_missing_source_frame_and_duplicate_destination_fail(self):
        edit=self.capture.index.read_revision(self.pid,self.edit_id,1)["data"]
        original=self.capture.index.read_revision(self.pid,self.delivery_id,1)["data"]
        self.assertEqual(source_mapping(edit,original),[(1,3),(2,1),(3,1),(4,2)])
        edit["editorial_map"]["frame_map"][1]["edit_frame"]=3
        with self.assertRaisesRegex(RuntimeError,"contiguous"):
            source_mapping(edit,original)

    def test_existing_output_is_not_overwritten(self):
        out=self.root/"existing"
        out.mkdir()
        with self.assertRaisesRegex(RuntimeError,"absent"):
            conform_pcm_audio(self.capture,self.pid,self.edit_id,1,
                              self.source,out,"existing_audio")


if __name__=="__main__":
    unittest.main()
