"""NVP: FFMS2+FFmpeg release license classification and evidence gates."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.nvp_ffms2_license_audit import classify_ffmpeg_build, inspect, sha_file


class NativeLicenseAuditTests(unittest.TestCase):
    def test_ffmpeg_license_flags(self):
        self.assertEqual(classify_ffmpeg_build("configuration: --enable-gpl"),
                         "GPL_COMPONENTS_ENABLED")
        self.assertEqual(classify_ffmpeg_build("configuration: --enable-nonfree --enable-gpl"),
                         "NONFREE_REVIEW_STOP")
        self.assertEqual(classify_ffmpeg_build("configuration: --enable-version3"),
                         "LGPL_VERSION3_CANDIDATE")
        self.assertEqual(classify_ffmpeg_build("configuration: --disable-gpl"),
                         "LGPL_CANDIDATE_UNVERIFIED_LINKAGE")
        self.assertEqual(classify_ffmpeg_build(""), "BUILD_CONFIG_UNKNOWN")

    def test_release_requires_matching_sha_provenance_and_policy(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ffmpeg = root / "ffmpeg.exe"
            ffms2 = root / "libffms2.dll"
            ffmpeg.write_bytes(b"synthetic ffmpeg binary fixture")
            ffms2.write_bytes(b"synthetic ffms2 binary fixture")
            class Result:
                stdout = b"configuration: --enable-gpl --enable-version3"
                returncode = 0
            with patch("tools.nvp_ffms2_license_audit.subprocess.run",
                       return_value=Result()):
                unapproved = inspect(ffmpeg, ffms2)
                self.assertFalse(unapproved["distribution_approved"])
                manifest = {
                    "ffmpeg_executable_sha256": sha_file(ffmpeg),
                    "ffms2_library_sha256": sha_file(ffms2),
                    "ffmpeg_config_sha256": unapproved["ffmpeg_config_sha256"],
                    "ffmpeg_source_commit": "1234567890abcdef",
                    "ffms2_source_commit": "fedcba9876543210",
                    "reviewed_binary_linkage": True,
                    "license_notices_included": True,
                    "corresponding_sources_available": True,
                    "release_license_review_approved": True,
                    "distribution_policy": "LGPL_COMPLIANT_REVIEWED",
                }
                path = root / "manifest.json"
                path.write_text(json.dumps(manifest))
                wrong_policy = inspect(ffmpeg, ffms2, release_manifest=path)
                self.assertFalse(wrong_policy["distribution_approved"])
                manifest["distribution_policy"] = "GPL_COMPLIANT_REVIEWED"
                path.write_text(json.dumps(manifest))
                accepted_for_review = inspect(ffmpeg, ffms2, release_manifest=path)
                self.assertTrue(accepted_for_review["distribution_approved"])
                ffms2.write_bytes(b"binary modified after legal review")
                altered = inspect(ffmpeg, ffms2, release_manifest=path)
                self.assertFalse(altered["distribution_approved"])

    def test_nonfree_build_cannot_pass_release(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ffmpeg, ffms2 = root / "ffmpeg", root / "libffms2"
            ffmpeg.write_bytes(b"ffmpeg")
            ffms2.write_bytes(b"lib")
            class Result:
                stdout = b"configuration: --enable-nonfree --enable-gpl"
                returncode = 0
            with patch("tools.nvp_ffms2_license_audit.subprocess.run",
                       return_value=Result()):
                report = inspect(ffmpeg, ffms2)
                self.assertEqual(report["ffmpeg_build_classification"],
                                 "NONFREE_REVIEW_STOP")
                self.assertFalse(report["distribution_approved"])


if __name__ == "__main__":
    unittest.main()
