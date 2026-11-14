"""W1-G package byte-identity and original-film preservation regressions.

Synthetic files test rejection only; they do not imply a release is accepted.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import shutil

from tools.nvp_w1g_native_package import (
    build_receipt, verify_installed, original_film_snapshot,
    verify_original_films_preserved,
)


class W1GNativePackageContracts(TestCase):
    def _payload(self, root):
        root.mkdir()
        (root/"_internal").mkdir()
        (root/"NVP.exe").write_bytes(b"real-binary-placeholder-for-negative-tests")
        (root/"_internal"/"base_library.zip").write_bytes(b"base")
        (root/"_internal"/"python311.dll").write_bytes(b"python")
        (root/"_internal"/"worker.dll").write_bytes(b"worker")

    def _admitted(self, root):
        with patch("tools.nvp_w1g_native_package.verify_bundle",
                   return_value={"exe":{"sha256":
                      __import__("hashlib").sha256(
                          (root/"NVP.exe").read_bytes()).hexdigest()}}):
            return build_receipt(root)

    def test_native_payload_matches_installed_bytes_and_rejects_worker_drift(self):
        with TemporaryDirectory() as td:
            parent = Path(td)
            bundle = parent/"built"
            installed = parent/"installed"
            self._payload(bundle)
            receipt = self._admitted(bundle)
            shutil.copytree(bundle, installed)
            (installed/"nvp-alpha-install.marker").write_bytes(b"marker")
            (installed/"Uninstall NVP.exe").write_bytes(b"uninstaller")
            self.assertEqual(
                verify_installed(receipt, installed)["status"],
                "W1G_INSTALLED_BYTES_MATCH_BUILD")
            (installed/"_internal"/"worker.dll").write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "byte mismatch"):
                verify_installed(receipt, installed)

    def test_unknown_files_or_ffmpeg_are_never_admitted(self):
        with TemporaryDirectory() as td:
            parent = Path(td)
            bundle = parent/"built"
            self._payload(bundle)
            receipt = self._admitted(bundle)
            (bundle/"extra.dll").write_bytes(b"unreviewed")
            with self.assertRaisesRegex(RuntimeError, "unexpected"):
                verify_installed(receipt, bundle)
            (bundle/"ffmpeg.exe").write_bytes(b"forbidden")
            with self.assertRaisesRegex(RuntimeError, "FFmpeg"):
                self._admitted(bundle)

    def test_original_film_preserved_across_uninstall(self):
        with TemporaryDirectory() as td:
            films = Path(td)/"creator-films"
            films.mkdir()
            (films/"original.take").write_bytes(b"immutable original")
            baseline = original_film_snapshot(films)
            self.assertEqual(
                verify_original_films_preserved(baseline, films)[
                    "original_files_verified"], 1)
            (films/"original.take").write_bytes(b"overwritten")
            with self.assertRaisesRegex(RuntimeError, "original film changed"):
                verify_original_films_preserved(baseline, films)
