"""Portable *negative/source* transport tests, NOT native installed Windows evidence."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'backend/nvp_post01f_installed_receipt_transport.py'
JOB = 'ltx_' + 'a' * 24


class ReceiptTransportBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Channel:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
        cls.Channel = Channel
        stubs = types.ModuleType('backend.nvp_post01f_scm_cng_v2')
        stubs.InstalledScmCngV2Channel = Channel
        stubs.load_installed_scm_verifier_key = lambda: b'PINNED-IN-REAL-WINDOWS-ONLY'
        backend = types.ModuleType('backend')
        backend.__path__ = []
        with mock.patch.dict(sys.modules, {'backend': backend,
                                           'backend.nvp_post01f_scm_cng_v2': stubs}):
            spec = importlib.util.spec_from_file_location('installed_receipt_test', SOURCE)
            cls.m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.m)

    def test_no_linux_or_unattended_fallback(self):
        with mock.patch.object(self.m.sys, 'platform', 'linux'):
            with self.assertRaises(PermissionError):
                self.m.receive_installed_scm_receipt(JOB, 120)
            with self.assertRaises(PermissionError):
                self.m.bind_installed_scm_receipt_channel(consume_once=lambda *_: True)

    def test_no_foreign_job_or_pid(self):
        with mock.patch.object(self.m.sys, 'platform', 'win32'):
            for job, pid in [('ltx_../escape', 12), ('ltx_' + 'A'*24, 12),
                             (JOB, 0), (JOB, True), (JOB, '12'), ('wrong', 1)]:
                with self.subTest(job=job, pid=pid), self.assertRaises(PermissionError):
                    self.m.receive_installed_scm_receipt(job, pid)

    def test_fixed_programdata_path_and_efs_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            files = []
            with (mock.patch.object(self.m, '_program_data', return_value=base),
                  mock.patch.object(self.m, '_attributes', return_value=self.m._FILE_ATTRIBUTE_DIRECTORY),
                  mock.patch.object(self.m, '_require_efs', side_effect=lambda p: files.append(p))):
                result = self.m._installed_receipt_path(JOB)
            self.assertEqual(result, base/'NVP'/'POST01F'/'SCMReceipts'/(JOB+'.v2.json'))
            self.assertEqual(files, [base/'NVP'/'POST01F'/'SCMReceipts'])

    def test_unencrypted_receipt_directory_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (mock.patch.object(self.m, '_program_data', return_value=pathlib.Path(tmp)),
                  mock.patch.object(self.m, '_attributes', return_value=self.m._FILE_ATTRIBUTE_DIRECTORY),
                  mock.patch.object(self.m, '_require_efs', side_effect=PermissionError('EFS absent'))):
                with self.assertRaisesRegex(PermissionError, 'EFS absent'):
                    self.m._installed_receipt_path(JOB)

    def test_regular_bounded_bytes_and_no_client_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp)/(JOB+'.v2.json')
            data = b'{"signed":"checked later by pinned v2 reader"}'
            f.write_bytes(data)
            with (mock.patch.object(self.m.sys, 'platform', 'win32'),
                  mock.patch.object(self.m, '_installed_receipt_path', return_value=f),
                  mock.patch.object(self.m, '_attributes', return_value=0),
                  mock.patch.object(self.m, '_require_efs')):
                self.assertEqual(self.m.receive_installed_scm_receipt(JOB, 123), data)
                f.write_bytes(b'!' * 8193)
                with self.assertRaises(PermissionError):
                    self.m.receive_installed_scm_receipt(JOB, 123)
                f.unlink()
                f.symlink_to(pathlib.Path(tmp)/'missing')
                with self.assertRaises((PermissionError, OSError)):
                    self.m.receive_installed_scm_receipt(JOB, 123)

    def test_python311_receipt_stat_uses_supported_os_interface(self):
        # Python 3.11 Path.stat has no follow_symlinks keyword argument.
        # This fails if the transport accidentally reintroduces that call.
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp)/(JOB+'.v2.json')
            payload=b'{}'
            f.write_bytes(payload)
            with (mock.patch.object(self.m.sys, 'platform', 'win32'),
                  mock.patch.object(self.m, '_installed_receipt_path', return_value=f),
                  mock.patch.object(self.m, '_attributes', return_value=0),
                  mock.patch.object(self.m, '_require_efs'),
                  mock.patch.object(pathlib.Path, 'stat', side_effect=TypeError(
                      "Path.stat() got an unexpected keyword argument 'follow_symlinks'"))):
                self.assertEqual(self.m.receive_installed_scm_receipt(JOB, 7),payload)

    def test_changed_receipt_during_read_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=pathlib.Path(tmp)/(JOB+'.v2.json')
            f.write_bytes(b'{}')
            original_read=self.m.os.read
            def tampering_read(fd,count):
                data=original_read(fd,count)
                # Force changed file size before post-read fstat; installed
                # receipt transport must never accept a mutable source.
                with f.open('ab') as out: out.write(b'x')
                return data
            with (mock.patch.object(self.m.sys, 'platform', 'win32'),
                  mock.patch.object(self.m, '_installed_receipt_path', return_value=f),
                  mock.patch.object(self.m, '_attributes', return_value=0),
                  mock.patch.object(self.m, '_require_efs'),
                  mock.patch.object(self.m.os, 'read', side_effect=tampering_read)):
                with self.assertRaises(PermissionError):
                    self.m.receive_installed_scm_receipt(JOB, 7)

    def test_no_caller_control_over_key_or_root(self):
        with mock.patch.object(self.m.sys, 'platform', 'win32'):
            spend = lambda *a: True
            result = self.m.bind_installed_scm_receipt_channel(consume_once=spend)
            self.assertIs(result.kwargs['receive_from_scm'], self.m.receive_installed_scm_receipt)
            self.assertIs(result.kwargs['consume_once'], spend)
            self.assertEqual(result.kwargs['pinned_p256_public'], b'PINNED-IN-REAL-WINDOWS-ONLY')
            with self.assertRaises(TypeError):
                self.m.bind_installed_scm_receipt_channel(consume_once=spend,
                                                          installed_root='/user/file')
            with self.assertRaises(PermissionError):
                self.m.bind_installed_scm_receipt_channel(consume_once=True)

    def test_production_knownfolder_not_environment_or_worker_value(self):
        code = SOURCE.read_text(encoding='utf8')
        self.assertIn('SHGetKnownFolderPath', code)
        self.assertIn('FileEncryptionStatusW', code)
        self.assertIn('SCMReceipts', code)
        self.assertIn("'.v2.json'", code)
        self.assertNotIn('getenv(', code)
        self.assertNotIn('environ[', code)
        self.assertNotIn('GetEnvironmentVariable', code)


if __name__ == '__main__':
    unittest.main()
