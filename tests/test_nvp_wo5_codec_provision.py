from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend.nvp_wo5_codec_provision import (
    FORMAT, ROSTER, MANIFEST, verify_payload, provision_immutable, check_installed,
    require_machine_codec_scope, deploy_machine,
)


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'machine'
        self.root.mkdir()
        self.source = self.root.parent / 'source'
        self.source.mkdir()
        self.pin = self.fixture(self.source)

    def fixture(self, folder, suffix=b'a'):
        tools = {}
        for role, (product, license_id, name, notice) in ROSTER.items():
            binary = name.encode() * 40 + suffix
            text = notice.encode() * 20
            (folder / name).write_bytes(binary)
            (folder / notice).write_bytes(text)
            tools[role] = dict(product=product, license=license_id, filename=name,
                               sha256=sha256(binary).hexdigest(), license_notice=notice,
                               license_sha256=sha256(text).hexdigest())
        raw = json.dumps(dict(format=FORMAT, tools=tools), sort_keys=True,
                         separators=(',', ':'), ensure_ascii=True).encode('ascii')
        (folder / MANIFEST).write_bytes(raw)
        return sha256(raw).hexdigest()

    def install(self, source=None, pin=None):
        return provision_immutable(source or self.source, pin or self.pin, self.root,
                                   mkdir_secure=lambda p:p.mkdir(), check_secure=lambda p:None,
                                   seal_new_file=lambda p:None)

    def test_idempotent_and_side_by_side(self):
        first = self.install()
        self.assertEqual(first, self.install())
        other = self.root.parent / 'second'
        other.mkdir()
        next_pin = self.fixture(other, b'b')
        second = self.install(other, next_pin)
        self.assertNotEqual(first, second)
        self.assertEqual(len(verify_payload(first, self.pin)), 8)
        self.assertEqual(len(verify_payload(second, next_pin)), 8)

    def test_bad_pin(self):
        with self.assertRaises(PermissionError):
            self.install(pin='0'*64)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_extra_binary(self):
        (self.source/'unreviewed.dll').write_bytes(b'x')
        with self.assertRaises(PermissionError):
            self.install()

    def test_changed_notice(self):
        (self.source/'openjpeg.BSD-2-Clause.LICENSE').write_bytes(b'bad')
        with self.assertRaises(PermissionError):
            self.install()

    def test_no_replacement_of_tampered_install(self):
        target = self.install()
        name = next(iter(ROSTER.values()))[2]
        (target/name).write_bytes(b'bad')
        with self.assertRaises(PermissionError):
            self.install()
        self.assertEqual((target/name).read_bytes(), b'bad')

    def test_linked_source_refused(self):
        name = next(iter(ROSTER.values()))[2]
        original = self.source/name
        external = self.root.parent/'external'
        original.rename(external)
        original.symlink_to(external)
        with self.assertRaises(PermissionError):
            self.install()

    def test_interrupted_stage_not_admitted(self):
        with patch('backend.nvp_wo5_codec_provision._copy_verified', side_effect=OSError('interruption')):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse((self.root/self.pin).exists())
        self.assertTrue(any(p.name.startswith('.pending-') for p in self.root.iterdir()))
        self.assertEqual(self.install().name, self.pin)

    def test_exact_machine_scope_only(self):
        target = self.install()
        exe = target / next(iter(ROSTER.values()))[2]
        with patch('backend.nvp_wo5_codec_provision.check_installed', return_value=target):
            self.assertEqual(require_machine_codec_scope([target], [], exe,
                pin=self.pin, compiled_pin=self.pin, frozen=True), target)
            for roots, files, binary, frozen, pin in (
                ([self.root], [], exe, True, self.pin),
                ([target, self.root], [], exe, True, self.pin),
                ([target], [exe], exe, True, self.pin),
                ([target], [], target/'unapproved.exe', True, self.pin),
                ([target], [], exe, False, self.pin),
                ([target], [], exe, True, '0'*64),
            ):
                with self.subTest(roots=roots, files=files, frozen=frozen, pin=pin):
                    with self.assertRaises(PermissionError):
                        require_machine_codec_scope(roots, files, binary,
                            pin=pin, compiled_pin=self.pin, frozen=frozen)

    def test_deploy_prepares_exact_ingress_and_preserves_old_release(self):
        root = self.root
        app = root.parent / 'ProgramFilesNVP'
        app.mkdir()
        class LocalACL:
            def __init__(self):
                self.app = app
                self.root = root
            def ensure_root(self):
                return self.root
            def check(self, path, **kwargs):
                if not Path(path).exists():
                    raise FileNotFoundError(path)
            def mkdir(self, path):
                path.mkdir()
            def seal_file(self, path):
                self.check(path)
        with patch('backend.nvp_wo5_codec_provision._MachineACL', LocalACL):
            first = deploy_machine(self.source, self.pin)
            other = self.root.parent / 'second'
            other.mkdir()
            second_pin = self.fixture(other, b'b')
            second = deploy_machine(other, second_pin)
            self.assertEqual(first, root/self.pin)
            self.assertEqual(second, root/second_pin)
            self.assertEqual(len(verify_payload(app/'codec-payloads'/self.pin, self.pin)), 8)
            self.assertEqual(len(verify_payload(first, self.pin)), 8)
            self.assertEqual(deploy_machine(other, second_pin), second)

    def test_deploy_bad_payload_never_opens_machine_authority(self):
        with patch('backend.nvp_wo5_codec_provision._MachineACL', side_effect=AssertionError('must not open machine root')):
            with self.assertRaises(PermissionError):
                deploy_machine(self.source, '0'*64)

    def test_non_windows_machine_gate(self):
        import os
        if os.name != 'nt':
            with self.assertRaises(PermissionError):
                check_installed(self.pin)
