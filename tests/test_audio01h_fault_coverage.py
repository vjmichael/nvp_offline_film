"""AUDIO-01H crash gate instrumentation coverage: no phantom green cases."""
from pathlib import Path
import unittest
from backend.nvp_audio01h_fault_matrix import BOUNDARIES

ROOT=Path(__file__).resolve().parents[1]


class Audio01HCrashCoverage(unittest.TestCase):
    def test_all_boundaries_in_real_code_once(self):
        files=[
            ROOT/"backend/nvp_audio01h_native_host.py",
            ROOT/"backend/nvp_audio01h_stem_revision.py",
            ROOT/"tools/nvp_audio01h_native_worker.py",
        ]
        code="\n".join(p.read_text("utf8") for p in files)
        self.assertEqual(len(BOUNDARIES),len(set(BOUNDARIES)))
        for point in BOUNDARIES:
            with self.subTest(point=point):
                self.assertEqual(code.count('crash_after("'+point+'")'),1)

    def test_each_boundary_has_actual_crash_test(self):
        from test_audio01h_native_crash_matrix import HOST_POINTS
        from test_audio01h_worker_crash_matrix import POINTS as WORKER_POINTS
        from test_audio01h_creator_crash_matrix import POINTS as CREATOR_POINTS
        covered=(*HOST_POINTS,*WORKER_POINTS,*CREATOR_POINTS)
        self.assertEqual(len(covered),len(set(covered)))
        self.assertEqual(set(covered),set(BOUNDARIES))


if __name__=="__main__":
    unittest.main()
