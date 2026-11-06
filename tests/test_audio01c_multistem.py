"""AUDIO-01C: genuine four-source stems, sample timing, restart and tamper."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from backend.nvp_audio01_picture_follow import RATE, SAMPLES_PER_FRAME
from backend.nvp_audio01c_multistem import (
    create_multistem_preview, verify_multistem_preview, validate_stem_plan,
)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def clip(start, end, source=0, gain=1000, fade_in=0, fade_out=0):
    return {"out_start": start, "out_end": end, "source_start": source,
            "fade_in": fade_in, "fade_out": fade_out, "gain_milli": gain}


class MultistemAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root/"studio.sqlite3"
        self.cap = DigitalCapture(Studio(self.db))
        self.pid = self.cap.studio.create_project("Mixed film", "Sound edit")["id"]
        self.cap.index.register_revision(self.pid, "take", "take", {"frozen": True})
        media = []
        for i in (1,2,3):
            media.append({
                "frame": i, "shot_id": "A",
                "png16_sha256": hashlib.sha256(f"png-{i}".encode()).hexdigest(),
                "rgb48_sha256": hashlib.sha256(f"rgb-{i}".encode()).hexdigest(),
                "source_exr_sha256": hashlib.sha256(f"exr-{i}".encode()).hexdigest(),
            })
        delivery = self.cap.index.register_revision(
            self.pid, "delivery", "presentation",
            {"format": "test.delivery", "frame_count": 3, "media_frames": media},
            dependencies=[{"object_id": "take", "revision": 1, "role": "source_take"}])
        frame_map = []
        for n, source in enumerate((1,3,2,3),1):
            row = media[source-1]
            frame_map.append({
                "edit_frame": n, "source_frame": source, "shot_id": row["shot_id"],
                "original_png16_sha256": row["png16_sha256"],
                "original_rgb48_sha256": row["rgb48_sha256"],
                "original_float32_sha256": row["source_exr_sha256"],
            })
        self.cap.index.register_revision(self.pid, "edit", "edit", {
            "source_delivery_id": "delivery",
            "source_delivery_sha256": delivery["document_sha256"],
            "source_take_id": "take",
            "source_take_sha256": self.cap.index.read_revision(self.pid, "take", 1)["document_sha256"],
            "editorial_map": {"fps": 24, "frame_count": 4, "frame_map": frame_map},
        }, dependencies=[{"object_id": "delivery", "revision": 1, "role": "presentation"}])
        self.sources = {}
        for sid, value, nframes in (
            ("voice",1000,4), ("room",200,6), ("door",400,2), ("score",300,8)
        ):
            path = self.root/(sid+".wav")
            with wave.open(str(path), "wb") as out:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(RATE)
                out.writeframes(struct.pack("<hh",value,-value)*nframes*SAMPLES_PER_FRAME)
            self.sources[sid] = path

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self):
        return {"stems": [
            {"stem_id": "voice", "kind": "dialogue",
             "clips": [clip(0,4500,fade_out=500)]},
            {"stem_id": "room", "kind": "ambience",
             "clips": [clip(0,8000)]},
            {"stem_id": "door", "kind": "sfx",
             "clips": [clip(1800,3800,fade_in=300)]},
            {"stem_id": "score", "kind": "music",
             "clips": [clip(2000,8000,gain=500)]},
        ]}

    def test_four_stems_sample_values_and_restart(self):
        originals = {sid: hashlib.sha256(path.read_bytes()).hexdigest()
                     for sid,path in self.sources.items()}
        dest = self.root/"preview"
        result = create_multistem_preview(self.cap,self.pid,"edit",1,
                                          self.sources,self.plan(),dest,"mixA")
        self.assertEqual(result["stems"],4)
        self.assertEqual(result["samples_per_channel"],8000)
        self.assertFalse(result["final_mix"])
        for sid,path in self.sources.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),originals[sid])
        with wave.open(str(dest/"multistem_preview.wav"),"rb") as mixed:
            self.assertEqual(mixed.getnframes(),8000)
            self.assertEqual(struct.unpack("<hh",mixed.readframes(1)),(1200,-1200))
            mixed.setpos(2500)
            self.assertEqual(struct.unpack("<hh",mixed.readframes(1)),(1750,-1750))
            mixed.setpos(6000)
            self.assertEqual(struct.unpack("<hh",mixed.readframes(1)),(350,-350))
        with wave.open(str(dest/"stem_voice.wav"),"rb") as voice:
            voice.setpos(6000)
            self.assertEqual(struct.unpack("<hh",voice.readframes(1)),(0,0))
        reopened=DigitalCapture(Studio(self.db))
        self.assertEqual(verify_multistem_preview(reopened,self.pid,"mixA",dest)["stems"],4)
        with self.assertRaises(RuntimeError):
            create_multistem_preview(reopened,self.pid,"edit",1,self.sources,self.plan(),
                                     dest,"duplicate")

    def test_invalid_ranges_and_kinds_do_not_publish(self):
        bad = self.plan()
        bad["stems"][0]["clips"][0]["source_start"]=10**9
        with self.assertRaises(ValueError):
            create_multistem_preview(self.cap,self.pid,"edit",1,self.sources,
                                     bad,self.root/"bad","badMix")
        with self.assertRaises(KeyError):
            self.cap.index.read_revision(self.pid,"badMix")
        bad=self.plan()
        bad["stems"][0]["kind"]="unknown"
        with self.assertRaises(ValueError):
            validate_stem_plan(bad,self.sources,4)
        bad=self.plan()
        bad["stems"][0]["clips"][0]["gain_milli"]=1001
        with self.assertRaises(ValueError):
            validate_stem_plan(bad,self.sources,4)

    def test_reject_clipping_without_publishing(self):
        for path in self.sources.values():
            with wave.open(str(path),"wb") as out:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(RATE)
                out.writeframes(struct.pack("<hh",20000,-20000)*8000)
        high={"stems":[
            {"stem_id":sid,"kind":kind,"clips":[clip(0,2000)]}
            for sid,kind in (("voice","dialogue"),("room","ambience"),
                             ("door","sfx"),("score","music"))
        ]}
        with self.assertRaisesRegex(RuntimeError,"clip"):
            create_multistem_preview(self.cap,self.pid,"edit",1,self.sources,
                                     high,self.root/"clipped","clippedMix")
        with self.assertRaises(KeyError):
            self.cap.index.read_revision(self.pid,"clippedMix")

    def test_tampering_is_detected_after_restart(self):
        dest=self.root/"preview"
        create_multistem_preview(self.cap,self.pid,"edit",1,self.sources,
                                 self.plan(),dest,"mixA")
        with (dest/"stem_room.wav").open("r+b") as stream:
            stream.seek(400)
            stream.write(b"alter")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            verify_multistem_preview(DigitalCapture(Studio(self.db)),self.pid,"mixA",dest)

    def test_manifest_forgery_detected(self):
        dest=self.root/"preview"
        create_multistem_preview(self.cap,self.pid,"edit",1,self.sources,
                                 self.plan(),dest,"mixA")
        manifest=dest/"multistem_manifest.json"
        manifest.write_text(manifest.read_text().replace(
            "unapproved_multistem_audio_preview","final_mix"))
        with self.assertRaisesRegex(RuntimeError,"manifest changed"):
            verify_multistem_preview(DigitalCapture(Studio(self.db)),self.pid,"mixA",dest)


if __name__=="__main__":
    unittest.main()
