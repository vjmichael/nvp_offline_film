"""Focused AUDIO-01H automation invariants, no external media packages."""
import math
import unittest
from array import array
from backend.nvp_audio01h_automation import (
    apply_pcm16_stereo, pcm16_peak_dbfs, validate_automation
)


def stereo(samples):
    a = array("h", [v for sample in samples for v in (sample, -sample)])
    import sys
    if sys.byteorder != "little":
        a.byteswap()
    return a.tobytes()


class Audio01HAutomationTests(unittest.TestCase):
    def test_unity_is_bit_identical(self):
        source = stereo([0, 100, -200, 1000, 32767])
        self.assertEqual(apply_pcm16_stereo(
            source, [[0, 0], [4, 0]], total_samples=5), source)

    def test_bounded_gain_and_endpoint(self):
        source = stereo([1000] * 5)
        rendered = apply_pcm16_stereo(
            source, [[0, -6], [4, 0]], total_samples=5)
        self.assertEqual(len(rendered), len(source))
        self.assertNotEqual(rendered, source)
        self.assertEqual(rendered[-4:], source[-4:])

    def test_reject_clipping_without_limiter(self):
        with self.assertRaisesRegex(ValueError, "clip"):
            apply_pcm16_stereo(stereo([32000, 32000]),
                               [[0, 6], [1, 6]], total_samples=2)

    def test_reject_invalid_controls(self):
        source = stereo([100, 100, 100])
        for points in (
            [[0, 0], [0, 0], [2, 0]],
            [[0, float("nan")], [2, 0]],
            [[1, 0], [2, 0]],
            [[0, 0], [1, 0]],
            [[0, 0], [3, 0]],
            [[0, 25], [2, 0]],
            [[True, 0], [2, 0]],
        ):
            with self.subTest(points=points), self.assertRaises(ValueError):
                apply_pcm16_stereo(source, points, total_samples=3)

    def test_wrong_length_rejected(self):
        with self.assertRaises(ValueError):
            apply_pcm16_stereo(stereo([100]), [[0, 0], [2, 0]], total_samples=3)

    def test_sample_peak_is_not_true_peak(self):
        self.assertEqual(pcm16_peak_dbfs(stereo([0, 0])), float("-inf"))
        self.assertTrue(math.isclose(pcm16_peak_dbfs(stereo([16384, 0])),
                                     -6.020599913, abs_tol=1e-6))


if __name__ == "__main__":
    unittest.main()
