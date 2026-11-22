"""W1-G actual PE64/ELF64 imported-library parser refusal contracts."""
from pathlib import Path
import unittest

from tools.nvp_w1g_native_link_audit import parse_native_imports


class NativeLinkEvidenceContracts(unittest.TestCase):
    def test_actual_msvc_runtime_imports_separate_from_python_wheels(self):
        dump=(
            "Dump of file original_capture.exe\n"
            "  Image has the following dependencies:\n"
            "    bcrypt.dll\n    MSVCP140.dll\n    KERNEL32.dll\n"
            "    VCRUNTIME140.dll\n    VCRUNTIME140_1.dll\n"
            "  Summary\n"
        )
        libs=parse_native_imports(dump,"windows-amd64")
        self.assertIn("MSVCP140.dll",libs)
        self.assertIn("VCRUNTIME140.dll",libs)
        self.assertIn("bcrypt.dll",libs)
        self.assertNotIn("original_capture.exe",libs)

    def test_real_elf_dynamic_imports_require_libcrypto_in_release_review(self):
        needed=(
            " 0x0000000000000001 (NEEDED) Shared library: [libcrypto.so.3]\n"
            " 0x0000000000000001 (NEEDED) Shared library: [libstdc++.so.6]\n"
            " 0x0000000000000001 (NEEDED) Shared library: [libc.so.6]\n"
        )
        libs=parse_native_imports(needed,"linux-amd64")
        self.assertEqual(set(libs),
            {"libcrypto.so.3","libstdc++.so.6","libc.so.6"})

    def test_missing_duplicate_or_unbounded_imports_are_refused(self):
        with self.assertRaisesRegex(RuntimeError,"missing or ambiguous"):
            parse_native_imports("No native imports","windows-amd64")
        with self.assertRaisesRegex(RuntimeError,"missing or ambiguous"):
            parse_native_imports("  bcrypt.dll\n  BCRYPT.DLL\n","windows-amd64")
        with self.assertRaisesRegex(RuntimeError,"missing or ambiguous"):
            parse_native_imports("  C:\\untrusted\\payload.dll\n","windows-amd64")
        with self.assertRaisesRegex(RuntimeError,"absent or unbounded"):
            parse_native_imports("x"*4194305,"linux-amd64")


if __name__=="__main__":
    unittest.main()
