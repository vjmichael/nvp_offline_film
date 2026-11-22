"""W1-G reviewed release and encrypted USD staging refusal regressions.

Positive signature tests use throwaway local Ed25519 keys, never claim actual
creator legal approval. Native EFS acceptance remains a physical Windows gate.
"""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_w1g_reviewed_release import (
    FORMAT, _canonical, license_review_digest, verify_signed_release_review,
)
from backend.nvp_w1g_encrypted_source import require_efs_stage, verify_efs_inputs
from tools.nvp_w1g_windows_efs_proof import (
    _require_new_boot,_require_efs_recovery_principal,
)


class SignedNativeReleaseReviewContracts(unittest.TestCase):
    def receipt(self):
        return {"format":"nvp.w1g.native_payload.v1",
            "platform":"windows-amd64",
            "app_sha256":"a"*64,
            "files":{"NVP.exe":{"bytes":3,"sha256":"a"*64},
                     "_internal/render.exe":{"bytes":7,"sha256":"b"*64}}}

    def reviewed_payload(self, receipt):
        return {"format":FORMAT,
            "payload_sha256":license_review_digest(receipt),
            "platform":"windows-amd64",
            "reviewer_reference":"Independent license review No. 123",
            "reviewed_artifacts":[
                {"file":path,"sha256":row["sha256"],
                 "spdx_license":"MIT",
                 "redistribution_reference":"approved native license record"}
                for path,row in receipt["files"].items()]}

    def test_missing_public_key_never_accepted(self):
        with self.assertRaisesRegex(PermissionError,"pinned"):
            verify_signed_release_review(
                self.receipt(),{},pinned_reviewer_public_key=b"")

    def test_unreviewed_binary_and_forged_signature_fail_closed(self):
        receipt=self.receipt()
        data=self.reviewed_payload(receipt)
        with self.assertRaises(PermissionError):
            verify_signed_release_review(receipt,
                {"payload":data,"signature_base64":base64.b64encode(
                    b"\\0"*64).decode()},
                pinned_reviewer_public_key=b"a"*32)
        data["reviewed_artifacts"].pop()
        with self.assertRaisesRegex(PermissionError,"Every bundled"):
            verify_signed_release_review(receipt,
                {"payload":data,"signature_base64":base64.b64encode(
                    b"\\0"*64).decode()},
                pinned_reviewer_public_key=b"a"*32)

    def test_ephemeral_reviewer_signature_binds_every_bundle_byte(self):
        # This is a REQUIRED release-verifier test. A missing verifier is
        # a test failure, never a quietly skipped licensing security gate.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        key=Ed25519PrivateKey.generate()
        public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        receipt=self.receipt()
        review=self.reviewed_payload(receipt)
        signed={"payload":review,
                "signature_base64":base64.b64encode(key.sign(
                    _canonical(review))).decode("ascii")}
        valid=verify_signed_release_review(receipt,signed,
                    pinned_reviewer_public_key=public)
        self.assertTrue(valid["redistribution_licenses_verified"])
        self.assertEqual(valid["reviewed_artifact_count"],2)
        receipt["files"]["_internal/render.exe"]["sha256"]="c"*64
        with self.assertRaisesRegex(PermissionError,"scoped"):
            verify_signed_release_review(receipt,signed,
                    pinned_reviewer_public_key=public)


class EncryptedScratchContracts(unittest.TestCase):
    def test_reject_symlinks_and_missing_protection(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(PermissionError,"dedicated nonlinked"):
                require_efs_stage(root/"not-created")
            if os.name!="nt":
                with self.assertRaisesRegex(PermissionError,"Windows"):
                    require_efs_stage(root)
                with self.assertRaises(PermissionError):
                    verify_efs_inputs(root)



class EFSDistinctBootAcceptanceContracts(unittest.TestCase):
    def test_same_boot_and_untrusted_receipt_never_accepted(self):
        with self.assertRaisesRegex(PermissionError,"distinct Windows boot"):
            _require_new_boot({"windows_boot_estimate_epoch":1700000000},1700000000)
        with self.assertRaisesRegex(PermissionError,"distinct Windows boot"):
            _require_new_boot({"windows_boot_estimate_epoch":1700000000},1700000030)
        with self.assertRaisesRegex(PermissionError,"boot observation"):
            _require_new_boot({},1700003000)
        with self.assertRaisesRegex(PermissionError,"boot observation"):
            _require_new_boot({"windows_boot_estimate_epoch":True},1700003000)

    def test_cross_principal_evidence_refuses_same_windows_token(self):
        original={"original_windows_token_sid":"S-1-5-21-123-456-789-1000"}
        with self.assertRaisesRegex(PermissionError,"different Windows token"):
            _require_efs_recovery_principal(
                original,"S-1-5-21-123-456-789-1000",cross_principal=True)
        with self.assertRaisesRegex(PermissionError,"original Windows token"):
            _require_efs_recovery_principal(
                original,"S-1-5-21-123-456-789-2000",cross_principal=False)
        with self.assertRaisesRegex(PermissionError,"token identity missing"):
            _require_efs_recovery_principal(
                {}, "S-1-5-21-123-456-789-2000",cross_principal=True)
        self.assertTrue(_require_efs_recovery_principal(
            original,"S-1-5-21-123-456-789-2000",cross_principal=True))
        self.assertTrue(_require_efs_recovery_principal(
            original,"S-1-5-21-123-456-789-1000",cross_principal=False))

    def test_conservative_observed_new_boot_is_only_a_reopen_gate(self):
        # This is a deterministic logic fixture, NOT a real Windows restart
        # or a certificate backup/restore witness.
        self.assertTrue(_require_new_boot(
            {"windows_boot_estimate_epoch":1700000000},1700001000))

if __name__=="__main__":
    unittest.main()
