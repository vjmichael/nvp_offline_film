"""AUDIO-01I all 17 crash points must be real and independently exercised."""
from pathlib import Path
import unittest
from backend.nvp_audio01i_fault_matrix import BOUNDARIES
from test_audio01i_master_host_crash_matrix import HOST_POINTS
from test_audio01i_master_worker_crash_matrix import POINTS as WORKER_POINTS
from test_audio01i_delivery_crash_matrix import DELIVERY_POINTS

ROOT=Path(__file__).resolve().parents[1]


class Audio01IProductionCrashCoverage(unittest.TestCase):
    def test_declared_points_present_once_in_real_production_code(self):
        combined="\n".join((ROOT/path).read_text("utf8") for path in (
            "backend/nvp_audio01i_mastering.py",
            "backend/nvp_audio01i_native_host.py",
            "tools/nvp_audio01i_native_worker.py"))
        self.assertEqual(len(BOUNDARIES),len(set(BOUNDARIES)))
        for name in BOUNDARIES:
            with self.subTest(name=name):
                self.assertEqual(combined.count('crash_after("'+name+'")'),1)

    def test_each_point_has_an_actual_subprocess_injection_case(self):
        tested=(*HOST_POINTS,*WORKER_POINTS,*DELIVERY_POINTS)
        self.assertEqual(len(tested),len(set(tested)))
        self.assertEqual(set(tested),set(BOUNDARIES))


if __name__=="__main__":
    unittest.main()
