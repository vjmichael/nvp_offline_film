"""AUDIO-01B: sample-exact independent sound edit, safety and immutable replay."""
import hashlib
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from backend.nvp_audio01b_dialogue_edit import (
    create_dialogue_preview, verify_dialogue_preview, render_audio_samples,
    validate_audio_plan,
)
from backend.nvp_audio01_picture_follow import RATE, SAMPLES_PER_FRAME
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def clip(start, end, source, fade_in=0, fade_out=0, gain=1000):
    return {"out_start": start, "out_end": end, "source_start": source,
            "fade_in": fade_in, "fade_out": fade_out, "gain_milli": gain}


class DialogueEdit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "studio.sqlite3"
        self.cap = DigitalCapture(Studio(self.db))
        self.pid = self.cap.studio.create_project("Sound", "J and L edits")["id"]
        self.cap.index.register_revision(self.pid, "take", "take",
                                         {"format": "test.take", "frozen": True})
        rows = []
        for n in (1, 2, 3):
            rows.append({"frame": n, "shot_id": "A" if n != 3 else "B",
                         "png16_sha256": hashlib.sha256(f"png{n}".encode()).hexdigest(),
                         "rgb48_sha256": hashlib.sha256(f"rgb{n}".encode()).hexdigest(),
                         "source_exr_sha256": hashlib.sha256(f"exr{n}".encode()).hexdigest()})
        delivery = self.cap.index.register_revision(
            self.pid, "delivery", "presentation",
            {"format": "test.delivery", "frame_count": 3, "media_frames": rows},
            dependencies=[{"object_id": "take", "revision": 1, "role": "source_take"}])
        frame_map = []
        for i, n in enumerate((1, 3, 2, 3), 1):
            r = rows[n-1]
            frame_map.append({
                "edit_frame": i, "source_frame": n, "shot_id": r["shot_id"],
                "original_png16_sha256": r["png16_sha256"],
                "original_rgb48_sha256": r["rgb48_sha256"],
                "original_float32_sha256": r["source_exr_sha256"]})
        self.cap.index.register_revision(
            self.pid, "edit", "edit", {
                "source_delivery_id": "delivery",
                "source_delivery_sha256": delivery["document_sha256"],
                "source_take_id": "take",
                "source_take_sha256": self.cap.index.read_revision(self.pid, "take", 1)["document_sha256"],
                "editorial_map": {"fps": 24, "frame_count": 4, "frame_map": frame_map}},
            dependencies=[{"object_id": "delivery", "revision": 1, "role": "presentation"}])
        self.wav = self.root / "source.wav"
        with wave.open(str(self.wav), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            for value in (1000, 2000, 3000):
                w.writeframesraw(struct.pack("<hh", value, -value) * SAMPLES_PER_FRAME)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        # Picture jumps at sample 2000; audio clip 1 trails it by 250
        # samples (L-cut), and new voice starts early at sample 1750 (J-cut).
        # Overlap gets a deterministic crossfade, not a forced picture sync.
        return {"clips": [
            clip(0, 2250, 0, fade_out=500),
            clip(1750, 7750, 0, fade_in=500),
        ]}

    def test_j_l_crossfade_and_restart_verified(self):
        original = self.wav.read_bytes()
        plan = self.plan()
        pcm = render_audio_samples(self.wav, plan, 3, 4)
        self.assertEqual(len(pcm), 8000 * 4)
        self.assertEqual(struct.unpack_from("<hh", pcm, 0), (1000, -1000))
        # The second clip starts earlier than the picture cut; at 2500
        # the source is sample 750 (still voice 1).
        self.assertEqual(struct.unpack_from("<hh", pcm, 2500*4), (1000, -1000))
        out = self.root / "preview"
        result = create_dialogue_preview(self.cap, self.pid, "edit", 1,
                                         self.wav, out, "sound01", plan)
        self.assertFalse(result["final_mix"])
        self.assertEqual(self.wav.read_bytes(), original)
        reopened = DigitalCapture(Studio(self.db))
        check = verify_dialogue_preview(reopened, self.pid, "sound01", out)
        self.assertEqual(check["status"], "VERIFIED_UNAPPROVED_AUDIO_EDITORIAL_PREVIEW")
        with self.assertRaises(RuntimeError):
            create_dialogue_preview(reopened, self.pid, "edit", 1,
                                    self.wav, out, "sound02", plan)

    def test_crossfade_measurably_changes_overlap(self):
        pcm = render_audio_samples(self.wav, self.plan(), 3, 4)
        # At 1900, outgoing voice is fading while incoming starts rising;
        # expected sum differs from ordinary uncut source and isn't clipped.
        value = struct.unpack_from("<h", pcm, 1900*4)[0]
        self.assertTrue(0 < value < 2000)
        self.assertEqual(struct.unpack_from("<h", pcm, 1900*4+2)[0], -value)

    def test_tampering_rejected(self):
        out = self.root / "preview"
        create_dialogue_preview(self.cap, self.pid, "edit", 1,
                                self.wav, out, "sound01", self.plan())
        path = out / "dialogue_edit_preview.wav"
        with path.open("r+b") as f:
            f.seek(120)
            f.write(b"tamper")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            verify_dialogue_preview(DigitalCapture(Studio(self.db)),
                                    self.pid, "sound01", out)

    def test_bad_ranges_and_excess_overlap(self):
        bad = {"clips": [clip(0, 8001, 0)]}
        with self.assertRaises(ValueError):
            validate_audio_plan(bad, 3, 4)
        with self.assertRaises(ValueError):
            validate_audio_plan({"clips": [clip(0, 2000, -1)]}, 3, 4)
        with self.assertRaises(ValueError):
            validate_audio_plan({"clips": [clip(0, 2000, 0, gain=1001)]}, 3, 4)
        with self.assertRaises(ValueError):
            validate_audio_plan({"clips": [clip(0, 2000, 0)]*9}, 3, 4)
        with self.assertRaises(ValueError):
            validate_audio_plan({"clips": [dict(clip(0, 2000, 0), unexpected=True)]}, 3, 4)

    def test_silence_and_intentional_gain(self):
        plan = {"clips": [clip(2000, 4000, 0, gain=500)]}
        pcm = render_audio_samples(self.wav, plan, 3, 4)
        self.assertEqual(struct.unpack_from("<hh", pcm, 0), (0, 0))
        self.assertEqual(struct.unpack_from("<hh", pcm, 2000*4), (500, -500))
        self.assertEqual(struct.unpack_from("<hh", pcm, 5000*4), (0, 0))


if __name__ == "__main__":
    unittest.main()
