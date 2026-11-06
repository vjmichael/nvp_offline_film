import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from backend.nvp_audio01h_loudness import analyze_wav


def wav(path, samples=48000, value=4096):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(int(value).to_bytes(2, "little", signed=True) * (2 * samples))


class Audio01HLoudnessTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_real_native_loudnorm_and_immutable_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "audio.wav"
            wav(p)
            before = p.read_bytes()
            measurement = analyze_wav(p, expected_samples=48000)
            self.assertEqual(p.read_bytes(), before)
            self.assertTrue(-70 < measurement["integrated_lufs"] < 0)
            self.assertTrue(-70 < measurement["true_peak_dbtp"] < 1)
            self.assertFalse(measurement["final_mix"])
            self.assertFalse(measurement["normalized"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_silence_cannot_earn_measured_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "silent.wav"
            wav(p, value=0)
            with self.assertRaises(RuntimeError):
                analyze_wav(p)

    def test_mismatched_picture_clock_rejected_before_native_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sound.wav"
            wav(p, samples=24)
            with patch("subprocess.run", side_effect=AssertionError("FFmpeg called")):
                with self.assertRaises(ValueError):
                    analyze_wav(p, expected_samples=25)


if __name__ == "__main__":
    unittest.main()
