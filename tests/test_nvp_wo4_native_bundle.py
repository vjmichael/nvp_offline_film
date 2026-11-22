"""WO4 synthetic binary/legal evidence tests, NOT actual upstream legal audit."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_wo4_native_bundle import (
    audit_native_bundle,publish_native_bom)


class NativeDependencyBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.bin=self.root/"libcodec.bin"
        self.lic=self.root/"LICENSE.txt"
        self.notice=self.root/"NOTICE.txt"
        self.bin.write_bytes(b"TEST_BINARY_NOT_REDISTRIBUTABLE")
        self.lic.write_text("Synthetic open-source license test text only.")
        self.notice.write_text("Synthetic dependency copyright notice test only.")
        self.record={
            "name":"OpenJPEG-test","version":"2.5.4",
            "binary_path":"libcodec.bin",
            "binary_sha256":sha256(self.bin.read_bytes()).hexdigest(),
            "license_path":"LICENSE.txt",
            "license_sha256":sha256(self.lic.read_bytes()).hexdigest(),
            "notice_path":"NOTICE.txt",
            "notice_sha256":sha256(self.notice.read_bytes()).hexdigest(),
            "requires":[]}

    def test_exact_version_hash_license_notice_and_no_overwrite(self):
        receipt=audit_native_bundle(self.root,[self.record])
        self.assertEqual(receipt["status"],"EVIDENCE_HASHES_VERIFIED")
        self.assertFalse(receipt["upstream_license_legal_review_passed"])
        self.assertFalse(receipt["native_binary_dependency_scan_passed"])
        self.assertEqual(receipt["component_count"],1)
        output=publish_native_bom(self.root,[self.record])
        self.assertEqual(output["status"],"BOM_WRITTEN_NO_REPLACE")
        with self.assertRaises(FileExistsError):
            publish_native_bom(self.root,[self.record])

    def test_missing_transitive_dependency_rejected(self):
        changed=dict(self.record,requires=["LibMissing"])
        with self.assertRaises(PermissionError):
            audit_native_bundle(self.root,[changed])

    def test_tampered_codec_or_notice_refused(self):
        self.bin.write_bytes(b"MODIFIED_BINARY")
        with self.assertRaises(PermissionError):
            audit_native_bundle(self.root,[self.record])
        self.bin.write_bytes(b"TEST_BINARY_NOT_REDISTRIBUTABLE")
        self.notice.write_text("Changed notice content")
        with self.assertRaises(PermissionError):
            audit_native_bundle(self.root,[self.record])

    def test_symlink_and_path_traversal_refused(self):
        for path in ("../private.bin","/etc/passwd","C:/Windows/system32.dll"):
            with self.subTest(path=path):
                changed=dict(self.record,binary_path=path)
                with self.assertRaises(PermissionError):
                    audit_native_bundle(self.root,[changed])
        link=self.root/"symlink.bin"
        try:link.symlink_to(self.bin)
        except OSError:self.skipTest("Native platform disallows symlinks")
        with self.assertRaises(PermissionError):
            audit_native_bundle(self.root,[dict(self.record,binary_path="symlink.bin")])


if __name__=="__main__":
    unittest.main()
