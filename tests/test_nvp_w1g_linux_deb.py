"""W1-G Linux package admission tests: candidates are not live acceptance."""
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_w1g_linux_deb import check_real_linux_bundle, build_deb


class LinuxPackagingTests(unittest.TestCase):
    def bundle(self, root):
        root.mkdir()
        exe = root/"NVP"
        binary = bytearray(150000)
        binary[:4] = b"\x7fELF"
        binary[4:6] = b"\x02\x01"
        struct.pack_into("<H", binary, 16, 3)
        struct.pack_into("<H", binary, 18, 62)
        exe.write_bytes(binary)
        (root/"_internal"/"frontend"/"dist"/"assets").mkdir(parents=True)
        (root/"_internal"/"base_library.zip").write_bytes(b"python runtime fixture")
        (root/"_internal"/"frontend"/"dist"/"index.html").write_text(
            '<div id="root"></div><script src="/assets/a.js"></script>')
        (root/"_internal"/"frontend"/"dist"/"assets"/"a.js").write_text("a")
        return exe

    def test_real_architecture_and_offline_gui_required(self):
        with TemporaryDirectory() as td:
            root = Path(td)/"bundle"
            exe = self.bundle(root)
            # Test-only synthetic ELF must never be represented as executed NVP.
            self.assertEqual(len(check_real_linux_bundle(root)["files"]), 4)
            data = bytearray(exe.read_bytes())
            struct.pack_into("<H", data, 18, 183)  # AArch64, not AMD64
            exe.write_bytes(data)
            with self.assertRaisesRegex(RuntimeError, "ELF64"):
                check_real_linux_bundle(root)

    def test_missing_ui_and_ffmpeg_bundle_fail(self):
        with TemporaryDirectory() as td:
            root = Path(td)/"bundle"
            self.bundle(root)
            (root/"_internal"/"frontend"/"dist"/"index.html").unlink()
            with self.assertRaisesRegex(RuntimeError, "runtime or offline React"):
                check_real_linux_bundle(root)
            (root/"_internal"/"frontend"/"dist"/"index.html").write_text(
                '<div id="root"></div><script src="/assets/a.js"></script>')
            (root/"_internal"/"ffprobe").write_bytes(b"forbidden")
            with self.assertRaisesRegex(RuntimeError, "FFmpeg"):
                check_real_linux_bundle(root)

    def test_untrusted_version_maintainer_and_output_are_refused(self):
        with TemporaryDirectory() as td:
            root = Path(td)/"bundle"
            self.bundle(root)
            out = Path(td)/"nvp.deb"
            out.write_bytes(b"preexisting-release")
            with self.assertRaises(FileExistsError):
                build_deb(root, out, version="0.1.0", maintainer="NVP <a@b.co>")
            out.unlink()
            with self.assertRaises(ValueError):
                build_deb(root, out, version="0.1.0\nInjected: field",
                          maintainer="NVP <a@b.co>")
            with self.assertRaises(ValueError):
                build_deb(root, out, version="0.1.0",
                          maintainer="NVP\nInjected: field")


if __name__ == "__main__":
    unittest.main()
