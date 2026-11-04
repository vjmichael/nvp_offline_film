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
        host=(ROOT/"tests/test_audio01h_native_crash_matrix.py").read_text("utf8")
        worker=(ROOT/"tests/test_audio01h_worker_crash_matrix.py").read_text("utf8")
        creator=(ROOT/"tests/test_audio01h_creator_crash_matrix.py").read_text("utf8")
        names=[]
        from backend.nvp_audio01h_fault_matrix import BOUNDARIES
        from ast import literal_eval
        # Count each point by literal in the explicit test files; no wildcard
        # or dynamic generator is counted as genuine coverage.
        for point in BOUNDARIES:
            count=sum(text.count('"'+point+'"') for text in (host,worker,creator))
            with self.subTest(point=point):
                self.assertEqual(count,1)


if __name__=="__main__":
    unittest.main()
