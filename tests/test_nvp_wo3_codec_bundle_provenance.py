"""WO3 release-gate security checks; fixtures are not real codec binaries."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from backend.nvp_wo3_codec_bundle_provenance import (
    verify_native_codec_bundle, FORMAT, REQUIRED)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


class CodecBundleProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        tools = {}
        for role, (product, license_id) in REQUIRED.items():
            data = (role.encode() + b"binary-fixture")*20
            filename = role+".bin"
            notice = product+".LICENSE"
            (self.root/filename).write_bytes(data)
            notice_data = (product+" complete legal notice fixture ")*10
            (self.root/notice).write_text(notice_data)
            tools[role] = {"product": product, "license": license_id,
                           "filename": filename, "sha256": sha(data),
                           "license_notice": notice,
                           "license_sha256": sha(notice_data.encode())}
        self.manifest = {"format": FORMAT, "tools": tools}

    def test_both_codecs_require_full_license_and_sha_manifest(self):
        result = verify_native_codec_bundle(self.root, self.manifest)
        self.assertEqual(result["status"],
                         "BUNDLE_CONTENTS_AND_NOTICES_HASH_VERIFIED")
        self.assertFalse(result["signed_release_provenance_verified"])
        self.assertFalse(result["production_dcp_accepted"])

    def test_missing_or_corrupt_binary_fails_closed(self):
        path = self.root/"asdcp-wrap.bin"
        path.write_bytes(b"modified")
        with self.assertRaises(PermissionError):
            verify_native_codec_bundle(self.root, self.manifest)

    def test_missing_license_notice_fails_closed(self):
        (self.root/"OpenJPEG.LICENSE").unlink()
        with self.assertRaises(PermissionError):
            verify_native_codec_bundle(self.root, self.manifest)

    def test_incomplete_manifest_fails_closed(self):
        del self.manifest["tools"]["asdcp-info"]
        with self.assertRaises(PermissionError):
            verify_native_codec_bundle(self.root, self.manifest)

    def test_manifest_cannot_escape_installed_bundle(self):
        self.manifest["tools"]["asdcp-unwrap"]["filename"] = "../outside"
        with self.assertRaises(PermissionError):
            verify_native_codec_bundle(self.root, self.manifest)


if __name__ == "__main__":
    unittest.main()
