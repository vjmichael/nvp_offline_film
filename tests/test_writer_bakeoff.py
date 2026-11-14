import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nvp_writer_bakeoff", HERE / "benchmarks/nvp_writer_bakeoff.py")
bakeoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bakeoff)

class BakeoffTest(unittest.TestCase):
    def test_loopback_only(self):
        self.assertEqual(bakeoff.validate_endpoint("http://127.0.0.1:8080/v1/chat/completions"),
                         "http://127.0.0.1:8080/v1/chat/completions")
        for address in ["https://127.0.0.1:8080/v1/chat/completions", "http://example.com:8080/v1/chat/completions", "http://127.0.0.1:8080/v1/other", "http://127.0.0.1:8080/v1/chat/completions?token=x"]:
            with self.assertRaises(ValueError, msg=address):
                bakeoff.validate_endpoint(address)

    def test_hard_constraints(self):
        prefix = "INT. HALLWAY - NIGHT\n\nMARA holds a wet umbrella.\n\nMARA\n"
        suffix = "\n\nJON\nThe bus never came.\n\nMARA closes the umbrella.\n\nJON\nDid the lights go out here, too?"
        findings = bakeoff.evaluate_hard_constraints([{"id": "protected_edit", "output": prefix + "Did you stay later than you said?" + suffix, "error": None},
                                                      {"id": "scene_to_structure", "output": '{"location":"kitchen"}', "error": None}])
        self.assertTrue(all(f["passed"] for f in findings))

    def test_local_mock_server_not_needed_for_scoring(self):
        findings = bakeoff.evaluate_hard_constraints([{"id": "protected_edit", "output": "replaced everything", "error": None},
                                                      {"id": "nonlinear_continuity", "output": "not json", "error": None}])
        self.assertFalse(any(f["passed"] for f in findings))

if __name__ == "__main__":
    unittest.main()
