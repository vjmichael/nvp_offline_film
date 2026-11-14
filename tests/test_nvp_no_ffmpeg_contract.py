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

    def test_relative_import_resolution(self):
        tree = ast.parse("from . import local_codec\nfrom ..shared import audio\n")
        self.assertIn("backend.scenes.local_codec",
                      audit.imports(tree, "backend/scenes/shot.py"))
        self.assertIn("backend.shared.audio",
                      audit.imports(tree, "backend/scenes/shot.py"))
        self.assertNotIn("backend.scenes.local_codec",
                         audit.imports(tree, "backend/scenes/shot.py")[:1])

    def test_relative_import_does_not_escape_package(self):
        tree = ast.parse("from ....outside import codec\n")
        self.assertEqual([], audit.imports(tree, "backend/scenes/shot.py"))

    def test_clean_native_import(self):
        tree = ast.parse("import wave\nimport pathlib\n")
        with patch.object(audit, "reached_runtime",
                          return_value=iter([("backend/fixture.py", tree)])):
            self.assertFalse(any("forbidden imported codec" in issue[2]
                                 for issue in audit.violations()))


if __name__ == "__main__":
    unittest.main()
