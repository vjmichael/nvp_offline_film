"""W1-G independent offline wheelhouse signature verification contracts.

The test key is ephemeral and the wheel content is synthetic: no test grants
real dependency redistribution rights or production upgrade permission.
"""
import base64
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from tools.nvp_w1g_native_dependencies import FORMAT as WHEEL_FORMAT
from tools.nvp_w1g_reviewed_release import _canonical
from tools.nvp_w1g_signed_wheelhouse import (
    unsigned_wheelhouse_review_candidate, verify_signed_offline_wheelhouse,
)


class SignedOfflineWheelhouseContracts(unittest.TestCase):
    def fixture(self, root):
        name="sample_pkg-1.0-py3-none-any.whl"
        wheel=root/name
        with zipfile.ZipFile(wheel,"w") as archive:
            archive.writestr(
                "sample_pkg-1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: sample-pkg\nVersion: 1.0\n")
        lock={
            "format":WHEEL_FORMAT,"platform":"windows-amd64",
            "wheels":[{
                "name":"sample-pkg","version":"1.0","filename":name,
                "sha256":sha256(wheel.read_bytes()).hexdigest(),
                "license_review":"Independent reviewer record 001"}]
        }
        return lock,wheel

    def sign_test_only(self,lock,root):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        candidate=unsigned_wheelhouse_review_candidate(
            lock,root,platform="windows-amd64")
        self.assertFalse(candidate["redistribution_approved"])
        private=Ed25519PrivateKey.generate()
        public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        payload=candidate["signed_review"]["payload"]
        payload["reviewer_reference"]="Ephemeral CI reviewer test record"
        for row in payload["reviewed_artifacts"]:
            row["spdx_license"]="MIT"
            row["redistribution_reference"]="Independent reviewer record 001"
        signature=base64.b64encode(private.sign(_canonical(payload))).decode("ascii")
        return {"payload":payload,"signature_base64":signature},public

    def test_exact_real_wheel_bytes_lock_and_test_signature_verified(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            lock,wheel=self.fixture(root)
            signed,public=self.sign_test_only(lock,root)
            result=verify_signed_offline_wheelhouse(
                lock,root,signed,platform="windows-amd64",
                pinned_reviewer_public_key=public)
            self.assertEqual(result["wheel_count"],1)
            self.assertTrue(result["reviewer_signature_verified"])
            self.assertFalse(result["production_upgrade_authorized"])
            self.assertFalse(result["physical_owner_or_efs_recovery_verified"])
            self.assertFalse(result["native_executable_workers_verified"])

    def test_wheel_tamper_extra_files_and_architecture_refused(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            lock,wheel=self.fixture(root)
            signed,key=self.sign_test_only(lock,root)
            (root/"unreviewed-extra.whl").write_bytes(b"unsigned")
            with self.assertRaisesRegex(RuntimeError,"unreviewed extra"):
                verify_signed_offline_wheelhouse(
                    lock,root,signed,platform="windows-amd64",
                    pinned_reviewer_public_key=key)
            (root/"unreviewed-extra.whl").unlink()
            wheel.write_bytes(wheel.read_bytes()+b"changed")
            with self.assertRaises(RuntimeError):
                verify_signed_offline_wheelhouse(
                    lock,root,signed,platform="windows-amd64",
                    pinned_reviewer_public_key=key)
            with self.assertRaises(RuntimeError):
                verify_signed_offline_wheelhouse(
                    lock,root,signed,platform="linux-amd64",
                    pinned_reviewer_public_key=key)

    def test_case_variant_extra_wheel_never_evades_offline_file_inventory(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            lock,_=self.fixture(root)
            signed,key=self.sign_test_only(lock,root)
            extra=root/lock["wheels"][0]["filename"].upper()
            extra.write_bytes(b"unreviewed")
            with self.assertRaisesRegex(RuntimeError,"unreviewed extra"):
                verify_signed_offline_wheelhouse(
                    lock,root,signed,platform="windows-amd64",
                    pinned_reviewer_public_key=key)

    def test_reviewer_signature_and_lock_binding_cannot_be_reused(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            lock,_=self.fixture(root)
            signed,key=self.sign_test_only(lock,root)
            with self.assertRaises(PermissionError):
                verify_signed_offline_wheelhouse(
                    lock,root,signed,platform="windows-amd64",
                    pinned_reviewer_public_key=b"bad"*10+b"zz")
            lock["wheels"][0]["license_review"]="Unsigned changed review reference"
            with self.assertRaises(PermissionError):
                verify_signed_offline_wheelhouse(
                    lock,root,signed,platform="windows-amd64",
                    pinned_reviewer_public_key=key)


if __name__=="__main__":
    unittest.main()
