"""No third-party redistribution permission can be invented by tooling."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from tools.nvp_w1g_supply_candidate import (
    candidate_wheel_lock,candidate_redistribution_review,
)
from tools.nvp_w1g_native_dependencies import validate_lock
from tools.nvp_w1g_reviewed_release import verify_signed_release_review


class ActualByteInventoryNotLicenseApproval(unittest.TestCase):
    def test_unreviewed_candidate_requires_real_human_provenance(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            wheel=root/"first_party_candidate-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel,"w") as z:
                z.writestr("first_party_candidate-1.0.dist-info/METADATA",
                           "Metadata-Version: 2.1\nName: first-party-candidate\nVersion: 1.0\n")
            lock=candidate_wheel_lock(root,platform="windows-amd64")
            self.assertEqual(lock["wheels"][0]["sha256"],sha256(wheel.read_bytes()).hexdigest())
            self.assertFalse(lock["redistribution_approved"])
            with self.assertRaisesRegex(RuntimeError,"license-review"):
                validate_lock(lock,root,platform="windows-amd64")
            receipt={"platform":"windows-amd64","app_sha256":"a"*64,
                     "files":{"NVP.exe":{"bytes":100,"sha256":"a"*64}}}
            review=candidate_redistribution_review(receipt)
            self.assertIsNone(review["signature_base64"])
            with self.assertRaises(PermissionError):
                verify_signed_release_review(
                    receipt,review,pinned_reviewer_public_key=b"a"*32)


if __name__=="__main__":
    unittest.main()
