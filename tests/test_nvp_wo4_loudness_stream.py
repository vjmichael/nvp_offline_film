"""WO4 bounded-memory WAV loudness must agree with in-memory diagnostics."""
from hashlib import sha256
from math import sin,pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_loudness import measure_pcm24_loudness
from backend.nvp_wo4_loudness_stream import measure_streamed_pcm24_loudness


class StreamedLoudnessParity(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.out=self.root/"master"
        self.out.mkdir()
        self.file=self.root/"source.pcm"

    def prepare(self,frames,channels,source):
        self.file.write_bytes(source)
        source_hash=sha256(source).hexdigest()
        legacy=master_pcm24_candidate(
            source,source_sha256=source_hash,
            original_take_sha256="a"*64,
            cinema_frames=frames,channel_layout=("stereo" if channels==2 else "5.1"),
            creator_approved=True)
        disk=stream_master_pcm24_candidate(
            self.file,source_sha256=source_hash,original_take_sha256="a"*64,
            cinema_frames=frames,channel_layout=("stereo" if channels==2 else "5.1"),
            output_root=self.out,approve=lambda _:True)
        return legacy,disk

    def test_real_sine_wave_loudness_matches_in_memory_algorithm(self):
        sample_bytes=bytearray()
        for i in range(24*2000):
            v=int(650000*sin(2*pi*1000*i/48000))
            sample=v.to_bytes(3,"little",signed=True)
            sample_bytes.extend(sample+sample)
        memory,disk=self.prepare(24,2,bytes(sample_bytes))
        first=measure_pcm24_loudness(memory)
        streamed=measure_streamed_pcm24_loudness(disk)
        self.assertTrue(first["measured"])
        self.assertTrue(streamed["measured"])
        self.assertAlmostEqual(first["lufs"],streamed["lufs"],places=5)
        self.assertAlmostEqual(first["sample_peak_dbfs"],
                               streamed["sample_peak_dbfs"],places=6)
        self.assertFalse(streamed["whole_track_loaded_into_ram"])
        self.assertEqual(streamed["maximum_window_samples"],19200)
        self.assertFalse(streamed["production_audio_accepted"])

    def test_unmeasurably_short_and_silent_reels(self):
        for value in (0,1500):
            with self.subTest(value=value):
                raw=(value.to_bytes(3,"little",signed=True)*2)*6000
                _,disk=self.prepare(3,2,raw)
                result=measure_streamed_pcm24_loudness(disk)
                self.assertFalse(result["measured"])
                self.assertIsNone(result["lufs"])

    def test_source_change_is_refused_without_partial_qc_success(self):
        raw=(12345).to_bytes(3,"little",signed=True)*12000
        _,disk=self.prepare(3,2,raw)
        file=Path(disk["destination"])
        file.write_bytes(file.read_bytes()[:-3]+b"\x00\x00\x00")
        with self.assertRaises(PermissionError):
            measure_streamed_pcm24_loudness(disk)

    def test_multichannel_lfe_only_is_excluded(self):
        raw=b"".join(
            (100000 if ch==3 else 0).to_bytes(3,"little",signed=True)
            for i in range(24000) for ch in range(6))
        _,disk=self.prepare(12,6,raw)
        result=measure_streamed_pcm24_loudness(disk)
        self.assertFalse(result["measured"])
        self.assertTrue(result["lfe_excluded"])


if __name__=="__main__":
    unittest.main()
