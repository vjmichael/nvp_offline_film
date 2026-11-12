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

    def test_symlink_payload_rejected_before_install(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            bundle = base / "NVP"
            bundle.mkdir()
            make_pe(bundle / "NVP.exe")
            external = base / "unrelated-user-file.txt"
            external.write_text("never include this in installer", encoding="utf8")
            (bundle / "external.txt").symlink_to(external)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                verify_bundle(bundle)
            (bundle / "external.txt").unlink()
            (base / "linked-bundle").symlink_to(bundle, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                verify_bundle(base / "linked-bundle")

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


    def test_production_nsis_script_restricts_recursive_uninstall(self):
        script = (Path(__file__).resolve().parents[1] / "packaging" / "nvp-alpha.nsi").read_text(encoding="utf8")
        self.assertIn('StrCmp "$INSTDIR" "$LOCALAPPDATA\\Programs\\NVP" safe_remove', script)
        self.assertIn('IfFileExists "$INSTDIR\\nvp-alpha-install.marker" marker_present', script)
        self.assertIn('Abort "Refusing to remove an unexpected installation directory"', script)
        self.assertIn('File /r "${PACKAGE_FILES}\\*"', script)
        self.assertNotIn('MUI_PAGE_DIRECTORY', script)
        # W1-G may only switch dedicated program trees with retained old
        # executable evidence, exact marker bytes and version monotonicity.
        self.assertIn('!include "WordFunc.nsh"', script)
        self.assertIn('Function .onInit', script)
        # Installer may stage but NEVER infer that a live worker tree is empty.
        self.assertIn('kernel-verified recovery', script)
        self.assertNotIn('Rename "${PREVIOUS_DIR}" "$LOCALAPPDATA\\Programs\\NVP"', script)
        self.assertIn('${VersionCompare}', script)
        self.assertIn('FileRead $0 $2', script)
        self.assertNotIn('Rename "$INSTDIR" "${PREVIOUS_DIR}"', script)
        self.assertIn('StrCmp $1 "upgrade" needs_native_activation promote_new', script)
        self.assertIn('WriteUninstaller "${STAGE_DIR}\\Uninstall NVP.exe"', script)
        self.assertIn('Rename "${STAGE_DIR}" "$INSTDIR"', script)
        self.assertNotIn('RMDir /r "${PREVIOUS_DIR}"', script)
        self.assertNotIn('RMDir /r "${STAGE_DIR}"', script)



if __name__ == "__main__":
    unittest.main()
