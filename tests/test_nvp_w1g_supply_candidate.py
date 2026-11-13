"""No third-party redistribution permission can be invented by tooling."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from tools.nvp_w1g_supply_candidate import (
    candidate_wheel_lock,candidate_redistribution_review,
    candidate_native_worker_roster,
)
from tools.nvp_w1g_native_dependencies import validate_lock
from tools.nvp_w1g_reviewed_release import verify_signed_release_review
from tools.nvp_w1g_worker_package import ROLES
from test_nvp_e2e01e_package_guard import make_pe


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



    def test_five_distinct_pe_shaped_candidates_inventoried_but_not_approved(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            mapping={}
            for role in sorted(ROLES):
                filename=role+".exe"
                exe=root/filename
                make_pe(exe,subsystem=3)
                mapping[role]=filename
            candidate=candidate_native_worker_roster(
                root,mapping,platform="windows-amd64")
            self.assertFalse(candidate["redistribution_approved"])
            self.assertFalse(candidate["creator_review_completed"])
            self.assertFalse(candidate["native_executables_executed"])
            roster=candidate["roster"]
            self.assertEqual({x["role"] for x in roster["workers"]},set(ROLES))
            for row in roster["workers"]:
                self.assertEqual(row["sha256"],
                    sha256((root/row["filename"]).read_bytes()).hexdigest())
            (root/"audio.exe").write_bytes(b"not a compiled native PE")
            with self.assertRaises(RuntimeError):
                candidate_native_worker_roster(root,mapping,platform="windows-amd64")

    def test_missing_role_reused_executable_and_bad_platform_are_refused(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            exe=root/"worker.exe"
            make_pe(exe,subsystem=3)
            with self.assertRaisesRegex(RuntimeError,"All five"):
                candidate_native_worker_roster(
                    root,{"scene_render":"worker.exe"},platform="windows-amd64")
            mapping={role:"worker.exe" for role in ROLES}
            with self.assertRaisesRegex(RuntimeError,"Untrusted or duplicate"):
                candidate_native_worker_roster(root,mapping,platform="windows-amd64")
            mapping={role:role+".exe" for role in ROLES}
            with self.assertRaises(RuntimeError):
                candidate_native_worker_roster(root,mapping,platform="linux-amd64")

if __name__=="__main__":
    unittest.main()
