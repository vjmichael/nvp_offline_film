"""DA-00 regression: native runtime must refuse FFmpeg family imports."""
import ast
import subprocess
import sys
import textwrap
import tempfile
from pathlib import Path
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

    def test_forbidden_from_import_symbols(self):
        for source in ("from . import av", "from ..shared import ffmpeg",
                       "from safe import libavcodec", "from av import codec"):
            with self.subTest(source=source):
                tree = ast.parse(source)
                with patch.object(audit, "reached_runtime",
                                  return_value=iter([("backend/scenes/shot.py", tree)])):
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

    def test_forbidden_executable_library_dispatch(self):
        # A command dispatch to a libav library must not bypass the audit
        # merely because its name is not ffmpeg or ffprobe.
        for library in ("libavcodec", "libavformat", "libavutil",
                        "libavfilter", "libavdevice", "libswscale",
                        "libswresample"):
            with self.subTest(library=library):
                tree = ast.parse("import subprocess\nsubprocess.run(['" + library + "'])")
                with patch.object(audit, "reached_runtime",
                                  return_value=iter([("backend/fixture.py", tree)])):
                    self.assertTrue(any("forbidden executable codec dispatch" in issue[2]
                                        for issue in audit.violations()))

    def test_package_initializers_are_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend" / "scenes").mkdir(parents=True)
            (root / "backend" / "__init__.py").write_text("import av\n")
            (root / "backend" / "scenes" / "__init__.py").write_text("import libavcodec\n")
            (root / "backend" / "scenes" / "shot.py").write_text("import wave\n")
            with patch.object(audit, "ROOT", root), patch.object(
                audit, "ENTRYPOINTS", ("backend/scenes/shot.py",)
            ):
                reached = dict(audit.reached_runtime())
                self.assertIn("backend/__init__.py", reached)
                self.assertIn("backend/scenes/__init__.py", reached)
                self.assertTrue(any("forbidden imported codec" in reason
                                    for _, _, reason in audit.violations()))

    def test_package_module_resolves_initializer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend" / "scenes").mkdir(parents=True)
            (root / "backend" / "scenes" / "__init__.py").write_text("")
            with patch.object(audit, "ROOT", root):
                self.assertEqual(root / "backend" / "scenes" / "__init__.py",
                                 audit.source_path("backend.scenes"))

    def test_internal_data_av_source_is_not_false_positive_pyav(self):
        # PyAV's external top-level 'av' is prohibited. Our native
        # backend.nvp_data_av_scene is a first-party source, not PyAV.
        self.assertFalse(audit.BAN.search("backend.nvp_data_av_scene"))
        self.assertTrue(audit.BAN.search("av"))
        self.assertTrue(audit.BAN.search("av.codec"))
        self.assertTrue(audit.BAN.search("backend.scenes.av"))

    def test_active_runtime_does_not_reach_retired_editorial_codecs(self):
        # Merely importing PCM conform used to pull B12/B14 video producers
        # into the active runtime. Keep the original historical implementations
        # intact, but ensure no active entrypoint reaches them.
        retired = {
            "backend/nvp_b11_editorial.py",
            "backend/nvp_b12_editorial_delivery.py",
            "backend/nvp_b13_editorial_roundtrip.py",
            "backend/nvp_b14_picture_conform.py",
            "backend/nvp_color_mastering.py",
            "backend/nvp_color_ocio.py",
            "backend/nvp_presentation_pipeline.py",
        }
        reached = dict(audit.reached_runtime())
        self.assertIn("backend/nvp_audio01_picture_follow.py", reached)
        self.assertIn("backend/nvp_editorial_frame_map.py", reached)
        self.assertFalse(retired.intersection(reached))
        self.assertEqual([], audit.violations())

    def test_actual_pcm_conform_with_retired_codec_imports_denied(self):
        # Fresh process: do not let an earlier test's module cache mask a
        # forbidden import. Exercise the original sample-exact WAV and
        # immutable-source regressions rather than only a mock import graph.
        code = textwrap.dedent("""
            import importlib.abc
            import sys
            import unittest

            retired = {
                'backend.nvp_b11_editorial',
                'backend.nvp_b12_editorial_delivery',
                'backend.nvp_b13_editorial_roundtrip',
                'backend.nvp_b14_picture_conform',
                'backend.nvp_color_mastering',
                'backend.nvp_color_ocio',
                'backend.nvp_presentation_pipeline',
            }
            class RefuseLegacyCodec(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if (fullname in retired or fullname.split('.')[0] in
                            {'ffmpeg', 'ffprobe', 'imageio_ffmpeg', 'av'}):
                        raise AssertionError('Retired codec import: ' + fullname)

            sys.meta_path.insert(0, RefuseLegacyCodec())
            suite = unittest.defaultTestLoader.discover(
                'tests', pattern='test_audio01_picture_follow.py')
            assert suite.countTestCases() >= 5, 'Original PCM tests missing'
            result = unittest.TextTestRunner().run(suite)
            if not result.wasSuccessful() or result.skipped:
                sys.exit(1)
            assert not retired.intersection(sys.modules)
            print('PCM_CONFORM_WITHOUT_LEGACY_CODECS_PASS')
        """)
        run = subprocess.run([sys.executable, "-c", code], cwd=audit.ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("PCM_CONFORM_WITHOUT_LEGACY_CODECS_PASS", run.stdout)

    def test_clean_native_import(self):
        tree = ast.parse("import wave\nimport pathlib\n")
        with patch.object(audit, "reached_runtime",
                          return_value=iter([("backend/fixture.py", tree)])):
            self.assertFalse(any("forbidden imported codec" in issue[2]
                                 for issue in audit.violations()))


if __name__ == "__main__":
    unittest.main()
