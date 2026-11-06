"""AUDIO-01K eight actual publication boundaries are not paper tests."""
from pathlib import Path
import unittest
from backend.nvp_audio01k_fault_matrix import BOUNDARIES
ROOT=Path(__file__).resolve().parents[1]

class BoundaryCoverage(unittest.TestCase):
    def test_each_declared_checkpoint_exactly_once(self):
        code="\n".join((ROOT/p).read_text("utf8") for p in (
            "backend/nvp_audio01k_distribution.py",
            "backend/nvp_audio01k_native_host.py"))
        self.assertEqual(len(BOUNDARIES),8)
        self.assertEqual(len(BOUNDARIES),len(set(BOUNDARIES)))
        for point in BOUNDARIES:
            with self.subTest(point=point):
                self.assertEqual(code.count('crash_after("'+point+'")'),1)


if __name__=="__main__":
    unittest.main()
