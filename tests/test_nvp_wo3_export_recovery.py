"""WO3 restart reconciliation: no automatic deletion or false cinema approvals."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.nvp_wo3_export_recovery import reconcile_dcp_exports


class ExportRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.name = "DCP_" + str(uuid4())
        self.folder = self.root / self.name
        self.folder.mkdir()
        self.files = {}
        for name in ("picture.mxf", "sound.mxf", "CPL.xml",
                     "PKL.xml", "ASSETMAP.xml", "VOLINDEX.xml"):
            data = ("immutable:" + name).encode()
            (self.folder / name).write_bytes(data)
            self.files[name] = hashlib.sha256(data).hexdigest()
        self.audit = {"status": "STRUCTURE_AND_SHA_VERIFIED",
                      "assets": {str(i): {"filename": name,
                                         "sha256": self.files[name]}
                                 for i, name in enumerate(
                                     ("picture.mxf", "sound.mxf", "CPL.xml"))}}

    def scan(self, receipts=()):
        with patch("backend.nvp_wo3_export_recovery.inspect_dcp_structure",
                   return_value=self.audit):
            return reconcile_dcp_exports(self.root, receipts)

    def test_publication_with_no_ledger_never_auto_claims_commit(self):
        before = sorted(p.name for p in self.folder.iterdir())
        record = self.scan()["exports"][0]
        self.assertEqual(record["status"],
                         "PUBLISHED_WITHOUT_LEDGER_REVIEW_REQUIRED")
        self.assertFalse(record["may_auto_delete"])
        self.assertFalse(record["production_dcp_accepted"])
        self.assertEqual(before, sorted(p.name for p in self.folder.iterdir()))

    def test_exact_trusted_receipt_is_verified_not_dci_approved(self):
        record = self.scan([{"destination_name": self.name,
                             "file_sha256": self.files}])["exports"][0]
        self.assertEqual(record["status"],
                         "PUBLISHED_LEDGER_AND_STRUCTURE_VERIFIED")
        self.assertFalse(record["production_dcp_accepted"])

    def test_changed_metadata_is_not_silently_reconciled(self):
        (self.folder / "ASSETMAP.xml").write_bytes(b"tampered")
        record = self.scan([{"destination_name": self.name,
                             "file_sha256": self.files}])["exports"][0]
        self.assertEqual(record["status"], "LEDGER_HASH_MISMATCH")

    def test_missing_export_is_reported_and_never_created(self):
        name = "DCP_" + str(uuid4())
        record = self.scan([{"destination_name": name,
                             "file_sha256": self.files}])["exports"]
        self.assertIn("LEDGER_EXPORT_MISSING", [x["status"] for x in record])
        self.assertFalse((self.root / name).exists())

    def test_abandoned_stage_is_read_only(self):
        stage = self.root / ".nvp-wo3-abandoned"
        stage.mkdir()
        with patch("backend.nvp_wo3_export_recovery.inspect_dcp_structure",
                   side_effect=ValueError("partial write")):
            rows = reconcile_dcp_exports(self.root)["exports"]
        self.assertIn("UNSAFE_OR_INCOMPLETE", [x["status"] for x in rows])
        self.assertTrue(stage.exists())

    def test_symlink_is_not_followed(self):
        link = self.root / ("DCP_" + str(uuid4()))
        try:
            link.symlink_to(self.folder, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Host cannot create symlinks")
        rows = self.scan()["exports"]
        self.assertEqual(next(x for x in rows if x["name"] == link.name)["status"],
                         "UNSAFE_OR_INCOMPLETE")

    def test_rejects_duplicate_and_forged_receipt_shape(self):
        r = {"destination_name": self.name, "file_sha256": self.files}
        with self.assertRaises(ValueError):
            self.scan([r, r])
        with self.assertRaises(ValueError):
            self.scan([{"destination_name": "../escape",
                        "file_sha256": self.files}])


if __name__ == "__main__":
    unittest.main()
