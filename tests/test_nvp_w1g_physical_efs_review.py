"""Physical EFS review signature contracts; CI never claims owner recovery."""
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from tools.nvp_w1g_physical_efs_review import (
    FORMAT, validate_signed_efs_review,verify_current_windows_efs_scratch,
)
from tools.nvp_w1g_reviewed_release import _canonical


class PhysicalEFSReviewContractTests(unittest.TestCase):
    def _sign_test_statement(self,root):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        now=int(time.time())
        data={
            "format":FORMAT,
            "scratch_root":str(root.resolve()),
            "prepared_windows_token_sid":"S-1-5-21-111-222-333-1000",
            "recovery_windows_token_sid":"S-1-5-21-111-222-333-2000",
            "nonsecret_test_sha256":"a"*64,
            "post_reboot_same_user_reopen_verified":True,
            "cross_principal_efs_decryption_verified":True,
            "offline_efs_key_backup_independently_reviewed":True,
            "reviewer_reference":"Independent physical review fixture",
            "reviewed_at_unix":now,
        }
        private=Ed25519PrivateKey.generate()
        key=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        signed={"payload":data,"signature_base64":base64.b64encode(
            private.sign(_canonical(data))).decode("ascii")}
        return signed,key,now

    def test_ephemeral_signed_external_review_never_claims_live_os_proof(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            signed,key,now=self._sign_test_statement(root)
            result=validate_signed_efs_review(
                signed,scratch_root=root,
                preparer_sid=signed["payload"]["prepared_windows_token_sid"],
                reviewer_public_key=key,now_unix=now)
            self.assertTrue(result["independently_signed_efs_review_verified"])
            self.assertEqual(len(result["signed_efs_review_sha256"]),64)
            with self.assertRaises(RuntimeError):
                if __import__("os").name!="nt":
                    verify_current_windows_efs_scratch(root)
                else:
                    raise RuntimeError("Actual Windows EFS acceptance is not a CI fixture")

    def test_wrong_key_same_principal_future_age_and_root_fail(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            other=root/"other";other.mkdir()
            signed,key,now=self._sign_test_statement(root)
            for kwargs in (
                {"reviewer_public_key":b"x"*32},
                {"preparer_sid":"S-1-5-21-111-222-333-2000"},
                {"scratch_root":other},
                {"now_unix":now+32*24*3600},
            ):
                args={
                    "scratch_root":root,
                    "preparer_sid":signed["payload"]["prepared_windows_token_sid"],
                    "reviewer_public_key":key,
                    "now_unix":now,
                }
                args.update(kwargs)
                with self.subTest(kwargs=kwargs),self.assertRaises(PermissionError):
                    validate_signed_efs_review(signed,**args)

    def test_unsigned_or_falsified_recovery_receipt_is_denied(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            signed,key,now=self._sign_test_statement(root)
            args={"scratch_root":root,
                  "preparer_sid":signed["payload"]["prepared_windows_token_sid"],
                  "reviewer_public_key":key,"now_unix":now}
            with self.assertRaises(PermissionError):
                validate_signed_efs_review(
                    {"payload":signed["payload"],"signature_base64":None},**args)
            signed["payload"]["offline_efs_key_backup_independently_reviewed"]=False
            with self.assertRaises(PermissionError):
                validate_signed_efs_review(signed,**args)


if __name__=="__main__":
    unittest.main()
