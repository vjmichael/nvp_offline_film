"""Security-negative tests: private signing remains impossible on unapproved inputs."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.nvp_release_gpg import (ARTIFACT_NAME, BUILD_WORKFLOW_ID, INSTALLER_NAME,
    create_candidate_manifest, validate_artifacts, validate_build_run, verify_installer)

SOURCE = 'a' * 40
FPR = 'b' * 40


def sample_run():
    return {
        'id': 12345678, 'workflow_id': BUILD_WORKFLOW_ID,
        'status': 'completed', 'conclusion': 'success',
        'head_sha': SOURCE, 'head_branch': 'main', 'event': 'workflow_dispatch',
        'repository': {'full_name': 'vjmichael/nvp_offline_film'},
    }


def sample_artifact():
    return {'artifacts': [{'id': 87654321, 'name': ARTIFACT_NAME,
                           'size_in_bytes': 64000000, 'expired': False,
                           'workflow_run': {'id': 12345678}}]}


class AdmissionTests(unittest.TestCase):
    def test_first_party_main_run_allowed(self):
        verified = validate_build_run(sample_run(), repo='vjmichael/nvp_offline_film',
                                      source_sha=SOURCE, run_id=12345678)
        self.assertEqual(verified['build_workflow_id'], BUILD_WORKFLOW_ID)
        self.assertEqual(validate_artifacts(sample_artifact(), source_run_id=12345678)['artifact_id'], 87654321)

    def test_untrusted_run_denials(self):
        for change in (
            {'id': 34567890}, {'workflow_id': 123}, {'conclusion': 'failure'},
            {'status': 'in_progress'}, {'head_sha': 'c'*40},
            {'head_branch': 'nvp/mainline-convergence-20261113'},
            {'event': 'pull_request'}, {'event': 'workflow_run'},
            {'repository': {'full_name': 'other/repo'}},
        ):
            with self.subTest(change=change):
                d = sample_run(); d.update(change)
                with self.assertRaises(PermissionError):
                    validate_build_run(d, repo='vjmichael/nvp_offline_film',
                                       source_sha=SOURCE, run_id=12345678)

    def test_mismatched_artifact_denials(self):
        for change in (
            {'name': 'another-installer'}, {'expired': True},
            {'size_in_bytes': 10}, {'workflow_run': {'id': 77777777}},
        ):
            with self.subTest(change=change):
                d = sample_artifact(); d['artifacts'][0].update(change)
                with self.assertRaises(PermissionError):
                    validate_artifacts(d, source_run_id=12345678)
        d = sample_artifact(); d['artifacts'].append(d['artifacts'][0])
        with self.assertRaises(PermissionError):
            validate_artifacts(d, source_run_id=12345678)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbox = self.root / "input"
        self.inbox.mkdir()
        self.exe = self.inbox / INSTALLER_NAME
        with self.exe.open('wb') as f:
            # Synthetic PE header for verifier unit tests only. Not a package.
            hdr = bytearray(512)
            hdr[:2] = b'MZ'
            struct.pack_into('<I', hdr, 60, 128)
            hdr[128:132] = b'PE\0\0'
            struct.pack_into('<H', hdr, 132, 0x14C)
            f.write(hdr)
            f.write(b'X' * 1_000_000)
        self.digest = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.provenance = dict(validate_build_run(sample_run(), repo='vjmichael/nvp_offline_film',
                                                  source_sha=SOURCE, run_id=12345678))
        self.provenance.update(validate_artifacts(sample_artifact(), source_run_id=12345678))

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, **kwargs):
        d=dict(installer=self.exe, expected_sha256=self.digest, run_metadata=self.provenance,
               signer_fingerprint=FPR, version='0.1.0', signing_sha=SOURCE,
               output=self.root/'NVP-Release-Manifest.json')
        d.update(kwargs)
        return create_candidate_manifest(**d)

    def test_manifest_positive_is_not_release_admission(self):
        self.assertEqual(verify_installer(self.exe, self.digest)[1], self.digest)
        manifest=self.manifest()
        self.assertEqual(manifest['source_sha'], SOURCE)
        self.assertFalse(manifest['production_release_published'])
        self.assertFalse(manifest['independent_license_review_certified'])
        self.assertFalse(manifest['physical_r9700_ltx_accepted'])
        self.assertEqual(json.loads((self.root/'NVP-Release-Manifest.json').read_text())['installer_sha256'], self.digest)
        with self.assertRaises(FileExistsError):
            self.manifest()

    def test_wrong_digest_denied(self):
        with self.assertRaises(PermissionError):
            self.manifest(expected_sha256='0'*64)

    def test_sha_mismatch_denied(self):
        with self.assertRaises(PermissionError):
            self.manifest(signing_sha='f'*40)

    def test_untrusted_source_denied(self):
        src=dict(self.provenance);src['repository']='other/repo'
        with self.assertRaises(PermissionError):
            self.manifest(run_metadata=src)

    def test_foreign_file_denied(self):
        (self.inbox/'foreign.exe').write_bytes(b'abc')
        with self.assertRaises(PermissionError):
            self.manifest()

    def test_symlink_denied(self):
        new=self.root/'other'/INSTALLER_NAME
        new.parent.mkdir()
        new.symlink_to(self.exe)
        with self.assertRaises(PermissionError):
            verify_installer(new, self.digest)

    def test_truncation_denied(self):
        self.exe.write_bytes(b'MZ')
        with self.assertRaises(PermissionError):
            self.manifest()

    def test_wrong_version_denied(self):
        with self.assertRaises(ValueError):
            self.manifest(version='0.1.0-beta && echo secret')


if __name__ == '__main__':
    unittest.main()
