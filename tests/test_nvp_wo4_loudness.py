"""WO4 K-weighted gated loudness: timing, source integrity and LFE exclusion."""
from hashlib import sha256
import math
import unittest

from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_loudness import measure_pcm24_loudness


def make(frames, channels, sample_fn):
    raw=bytearray()
    for i in range(frames*2000):
        for ch in range(channels):
            raw.extend(sample_fn(i,ch).to_bytes(3,"little",signed=True))
    return bytes(raw)


def master(raw,frames,layout):
    return master_pcm24_candidate(
        raw,source_sha256=sha256(raw).hexdigest(),
        original_take_sha256="a"*64,cinema_frames=frames,
        channel_layout=layout,creator_approved=True)


class NativeLoudnessTests(unittest.TestCase):
    def test_stereo_sine_has_finite_gated_result(self):
        raw=make(24,2,lambda i,ch:
                 int(600000*math.sin(2*math.pi*1000*i/48000)))
        result=measure_pcm24_loudness(master(raw,24,"stereo"))
        self.assertTrue(result["measured"])
        self.assertGreater(result["lufs"],-35)
        self.assertLess(result["lufs"],-10)
        self.assertFalse(result["true_peak_measured"])
        self.assertFalse(result["production_audio_accepted"])

    def test_short_reel_refuses_to_invent_lufs(self):
        raw=make(3,2,lambda i,ch:1000)
        result=measure_pcm24_loudness(master(raw,3,"stereo"))
        self.assertFalse(result["measured"])
        self.assertIsNone(result["lufs"])

    def test_lfe_only_is_excluded_from_integrated_loudness(self):
        raw=make(12,6,lambda i,ch:600000 if ch==3 else 0)
        result=measure_pcm24_loudness(master(raw,12,"5.1"))
        self.assertFalse(result["measured"])
        self.assertIsNone(result["lufs"])
        self.assertTrue(result["lfe_excluded"] if "lfe_excluded" in result else
                        result["status"]=="K_WEIGHTED_GATE_MEASURED")

    def test_pcm_hash_mismatch_is_rejected(self):
        raw=make(12,2,lambda i,ch:1000)
        changed=dict(master(raw,12,"stereo"),master_pcm_sha256="f"*64)
        with self.assertRaises(PermissionError):
            measure_pcm24_loudness(changed)

if __name__=="__main__":
    unittest.main()
