"""DA-00 regression: native runtime must refuse FFmpeg family imports."""
import ast
import unittest
from unittest.mock import patch

from tools import nvp_no_ffmpeg_contract as audit


class ZeroFFmpegContractTests(unittest.TestCase):
    def test_forbidden_imports(self):
        for module in ("av", "av.codec", "libavfilter", "libavdevice",
                       "libswscale", "libswresample", "imageio_ffmpeg",
                       "ffmpeg", "ffprobe"):
            with self.subTest(module=module):
                tree = ast.parse("import " + module)
                with patch.object(audit, "reached_runtime",
                                  return_value=iter([("backend/fixture.py", tree)])):
                    self.assertTrue(any("forbidden imported codec" in issue[2]
                                        for issue in audit.violations()))

    def test_clean_native_import(self):
        tree = ast.parse("import wave\nimport pathlib\n")
        with patch.object(audit, "reached_runtime",
                          return_value=iter([("backend/fixture.py", tree)])):
            self.assertFalse(any("forbidden imported codec" in issue[2]
                                 for issue in audit.violations()))


if __name__ == "__main__":
    unittest.main()
