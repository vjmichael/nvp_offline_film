import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_wo5_install_contract import (
    DISABLED, compiled_source_pin, verify_install_request, build_contract,
)


class InstallerContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.app = self.root / 'NVP'
        self.app.mkdir()
        self.pin_file = self.root / 'pin.py'
        self.pin = 'a' * 64
        self.write_pin('')

    def write_pin(self, value):
        self.pin_file.write_text('"""Build-only literal."""\nRELEASE_CODEC_MANIFEST_SHA256 = '+repr(value)+'\n', encoding='utf-8')

    def check_machine(self, pin):
        self.assertEqual(pin, self.pin)
        return self.root / 'native-codecs' / pin

    def no_machine(self, pin):
        self.fail('Disabled release attempted machine codec admission')

    def test_disabled_release(self):
        self.assertEqual(compiled_source_pin(self.pin_file), DISABLED)
        self.assertEqual(verify_install_request(DISABLED, compiled='', frozen=True, check_machine=self.no_machine), DISABLED)
        result = build_contract(expected=DISABLED, pin_module=self.pin_file, app_bundle=self.app)
        self.assertEqual(result['machine_payload_files_verified'], 0)
        self.assertFalse(result['frozen_pin_and_machine_admission_verified'])

    def test_frozen_pin_must_match_before_machine_access(self):
        for requested, compiled, frozen in ((DISABLED,self.pin,True),(self.pin,'',True),(self.pin,'b'*64,True),(self.pin,self.pin,False),('bad','bad',True)):
            with self.subTest(requested=requested, compiled=compiled, frozen=frozen), self.assertRaises(PermissionError):
                verify_install_request(requested, compiled=compiled, frozen=frozen, check_machine=self.no_machine)

    def test_matching_frozen_pin_requires_machine_verification(self):
        self.assertEqual(verify_install_request(self.pin, compiled=self.pin, frozen=True, check_machine=self.check_machine), self.pin)
        with self.assertRaises(PermissionError):
            verify_install_request(self.pin, compiled=self.pin, frozen=True, check_machine=lambda _: self.root/'wrong')
        with self.assertRaises(FileNotFoundError):
            verify_install_request(self.pin, compiled=self.pin, frozen=True, check_machine=lambda _: (self.root/'missing').resolve(strict=True))

    def test_build_rejects_unreviewed_source_pin_and_executable_pin_module(self):
        self.write_pin(self.pin)
        with self.assertRaises(PermissionError):
            build_contract(expected=DISABLED, pin_module=self.pin_file, app_bundle=self.app)
        self.pin_file.write_text('RELEASE_CODEC_MANIFEST_SHA256 = str("a")\n')
        with self.assertRaises(PermissionError):
            compiled_source_pin(self.pin_file)

    def test_no_machine_files_in_per_user_payload(self):
        (self.app/'_internal').mkdir()
        (self.app/'_internal'/'opj_decompress.exe').write_bytes(b'fake')
        with self.assertRaises(PermissionError):
            build_contract(expected=DISABLED, pin_module=self.pin_file, app_bundle=self.app)

    def test_enabled_build_requires_independent_payload(self):
        self.write_pin(self.pin)
        with self.assertRaises(PermissionError):
            build_contract(expected=self.pin, pin_module=self.pin_file, app_bundle=self.app)
        with patch('backend.nvp_wo5_install_contract.verify_payload', return_value={str(i):None for i in range(8)}) as check:
            report = build_contract(expected=self.pin, pin_module=self.pin_file, app_bundle=self.app, codec_payload=self.root/'payload')
        check.assert_called_once_with(self.root/'payload', self.pin)
        self.assertEqual(report['machine_payload_files_verified'], 8)
        self.assertFalse(report['native_playback_accepted'])

    def test_disabled_build_refuses_codec_payload(self):
        with self.assertRaises(PermissionError):
            build_contract(expected=DISABLED, pin_module=self.pin_file, app_bundle=self.app, codec_payload=self.root/'payload')
