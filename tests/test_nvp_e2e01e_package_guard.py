"""Tests for NVP Windows payload audit, independent of Windows execution.

Synthetic PE fixtures test only structural rejection. They are never
presented as legitimate NVP installers or verified executable runtime.
"""
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_e2e01e_validate_installer_payload import verify_bundle, verify_pe64_gui


def make_pe(path, *, machine=0x8664, magic=0x20B, subsystem=2):
    buf = bytearray(150_000)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, 0x80)
    buf[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", buf, 0x84, machine)
    struct.pack_into("<H", buf, 0x80+20, 240)
    struct.pack_into("<H", buf, 0x80+24, magic)
    struct.pack_into("<H", buf, 0x80+24+68, subsystem)
    path.write_bytes(buf)


class PackageGuardTests(unittest.TestCase):
    def test_missing_and_placeholder_binary_fail(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/"NVP.exe"
            with self.assertRaises(RuntimeError):
                verify_pe64_gui(path)
            path.write_bytes(b"MZ" + b"placeholder")
            with self.assertRaisesRegex(RuntimeError, "placeholder"):
                verify_pe64_gui(path)

    def test_architecture_and_gui_subsystem_are_required(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/"NVP.exe"
            for machine, magic, sub in (
                (0x14C, 0x10B, 2),
                (0x8664, 0x10B, 2),
                (0x8664, 0x20B, 3),
            ):
                with self.subTest(machine=machine, magic=magic, subsystem=sub):
                    make_pe(path, machine=machine, magic=magic, subsystem=sub)
                    with self.assertRaises(RuntimeError):
                        verify_pe64_gui(path)

    def test_even_correct_pe_header_requires_packaged_runtime_and_ui(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_pe(root/"NVP.exe")
            self.assertEqual(verify_pe64_gui(root/"NVP.exe")["subsystem"],
                             "Windows GUI")
            with self.assertRaisesRegex(RuntimeError, "one-directory"):
                verify_bundle(root)
            internal = root/"_internal"
            internal.mkdir()
            with self.assertRaisesRegex(RuntimeError, "base_library"):
                verify_bundle(root)
            (internal/"base_library.zip").write_bytes(b"minimal test")
            with self.assertRaisesRegex(RuntimeError, "Python Windows runtime"):
                verify_bundle(root)
            (internal/"python311.dll").write_bytes(b"minimal test")
            with self.assertRaisesRegex(RuntimeError, "React"):
                verify_bundle(root)


if __name__ == "__main__":
    unittest.main()
