"""AUDIO-01J require every declared crash boundary in actual native tests."""
from pathlib import Path
import unittest
from backend.nvp_audio01j_fault_matrix import BOUNDARIES
from test_audio01j_final_av_crash_matrix import HOST_POINTS,WORKER_POINTS
from test_audio01j_picture_lock_crash_matrix import PICTURE_POINTS

ROOT=Path(__file__).resolve().parents[1]

class FinalAVFaultCoverage(unittest.TestCase):
    def test_all_twenty_native_effects_are_instrumented_once(self):
        files=["backend/nvp_audio01j_native_host.py",
               "backend/nvp_audio01j_final_av.py",
               "tools/nvp_audio01j_native_worker.py"]
        code="\n".join((ROOT/file).read_text("utf8") for file in files)
        self.assertEqual(len(BOUNDARIES),20)
        self.assertEqual(len(set(BOUNDARIES)),len(BOUNDARIES))
        for boundary in BOUNDARIES:
            with self.subTest(boundary=boundary):
                self.assertEqual(code.count('crash_after("'+boundary+'")'),1)

    def test_all_twenty_effects_have_subprocess_test_cases(self):
        cases=(*PICTURE_POINTS,*HOST_POINTS,*WORKER_POINTS)
        self.assertEqual(len(cases),len(set(cases)))
        self.assertEqual(set(cases),set(BOUNDARIES))


if __name__=="__main__":
    unittest.main()
