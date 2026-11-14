"""Native supply intake joins actual PE/ELF bytes with linker/role provenance.

Copies the local CPython executable as a genuine native-image *test fixture*.
This does not represent any of NVP's five compiled film-role workers, OS
process custody, signed redistribution review, ADCs or EFS.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from tools.nvp_w1g_compile_first_party_workers import SOURCE, SOURCE_ROOT
from tools.nvp_w1g_compiled_supply_chain_intake import (
    original_compiled_native_review_intake,
)
from tools.nvp_w1g_native_link_audit import FORMAT as IMPORT_FORMAT
from tools.nvp_w1g_worker_package import FORMAT as ROSTER_FORMAT, ROLES


def _sha(path):
    return sha256(path.read_bytes()).hexdigest()


class ExactNativeSupplyIntakeTests(unittest.TestCase):
    def fixture(self, root):
        binary_dir = root / "compiled"
        binary_dir.mkdir()
        platform = "windows-amd64" if sys.platform == "win32" else "linux-amd64"
        # Ubuntu CPython launcher can be a ~18 KiB ELF shim; use a genuine
        # nontrivial system executable meeting native worker size bounds.
        executable = Path(sys.executable if platform == "windows-amd64"
                          else "/bin/bash").resolve(strict=True)
        image_sha = _sha(executable)
        workers = []
        imports = []
        for role in sorted(ROLES):
            filename = role + (".exe" if platform == "windows-amd64" else "")
            dst = binary_dir / filename
            shutil.copyfile(executable, dst)
            workers.append({"role": role, "filename": filename, "sha256": _sha(dst)})
            imports.append({
                "role": role, "filename": filename,
                "executable_sha256": _sha(dst),
                "imported_libraries": (["KERNEL32.dll", "VCRUNTIME140.dll"]
                                      if platform == "windows-amd64" else
                                      ["libc.so.6", "libstdc++.so.6"]),
            })
        build = {
            "status": "FIVE_REAL_NATIVE_EXECUTABLES_COMPILED_CANDIDATE",
            "native_executables_compiled": True,
            "production_native_roles_complete": False,
            "role_count": 5,
            "source_sha256": _sha(SOURCE),
            "compiler_image_sha256": image_sha,
            "host_os": "Fixture OS only",
            "host_architecture": "Fixture arch only",
            "role_translation_unit_sha256": {
                r: _sha(SOURCE_ROOT / "native" / (r + ".cpp")) for r in ROLES
            },
            "roster": {"format": ROSTER_FORMAT, "platform": platform, "workers": workers},
        }
        linked = {
            "format": IMPORT_FORMAT,
            "platform": platform,
            "source_sha256": build["source_sha256"],
            "status": "NATIVE_LINKER_DEPENDENCY_CANDIDATE_ONLY",
            "imports": imports,
            "runtime_library_bytes_pinned": False,
            "external_native_dependency_license_reviewed": False,
        }
        (binary_dir / "build-candidate.json").write_text(json.dumps(build), "utf8")
        import_path = root / "native-imports.json"
        import_path.write_text(json.dumps(linked), "utf8")
        return binary_dir, import_path, build, linked

    def test_exact_five_real_header_bytes_join_without_approving_redistribution(self):
        with tempfile.TemporaryDirectory() as td:
            binary_dir, imports, _build, _links = self.fixture(Path(td))
            proof = original_compiled_native_review_intake(binary_dir, imports)
            self.assertEqual(len(proof["worker_executable_sha256_by_role"]), 5)
            self.assertEqual(len(proof["imported_native_libraries_by_role"]), 5)
            self.assertTrue(proof["five_compiled_worker_bytes_and_direct_imports_joined"])
            for flag in ("production_readiness_accepted",
                         "externally_signed_release_or_wheelhouse_verified",
                         "external_native_library_redistribution_approved",
                         "physical_microphone_or_dual_adc_verified",
                         "physical_windows_efs_cross_principal_recovery_verified",
                         "native_role_complete_film_pipeline_verified",
                         "creator_nsis_or_rollback_authorized"):
                self.assertFalse(proof[flag], flag)
            self.assertGreaterEqual(len(proof["review_required"]), 5)

    def test_changed_executable_or_swapped_linked_identity_denied(self):
        with tempfile.TemporaryDirectory() as td:
            binary_dir, imports, _build, links = self.fixture(Path(td))
            path = binary_dir / links["imports"][0]["filename"]
            path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(PermissionError, "changed"):
                original_compiled_native_review_intake(binary_dir, imports)
        with tempfile.TemporaryDirectory() as td:
            binary_dir, imports, _build, links = self.fixture(Path(td))
            links["imports"][0]["executable_sha256"] = "0"*64
            imports.write_text(json.dumps(links), "utf8")
            with self.assertRaisesRegex(PermissionError, "not bound"):
                original_compiled_native_review_intake(binary_dir, imports)

    def test_missing_or_ambiguous_native_imports_and_role_sources_denied(self):
        with tempfile.TemporaryDirectory() as td:
            binary_dir, imports, build, links = self.fixture(Path(td))
            links["imports"].pop()
            imports.write_text(json.dumps(links), "utf8")
            with self.assertRaisesRegex(PermissionError, "matching native import audit"):
                original_compiled_native_review_intake(binary_dir, imports)
        with tempfile.TemporaryDirectory() as td:
            binary_dir, imports, build, links = self.fixture(Path(td))
            links["imports"][0]["imported_libraries"] = ["bcrypt.dll", "BCRYPT.DLL"]
            imports.write_text(json.dumps(links), "utf8")
            with self.assertRaisesRegex(PermissionError, "ambiguous"):
                original_compiled_native_review_intake(binary_dir, imports)
        with tempfile.TemporaryDirectory() as td:
            binary_dir, imports, build, links = self.fixture(Path(td))
            build["role_translation_unit_sha256"]["audio"] = "f"*64
            (binary_dir / "build-candidate.json").write_text(json.dumps(build), "utf8")
            with self.assertRaisesRegex(PermissionError, "compiler source"):
                original_compiled_native_review_intake(binary_dir, imports)


if __name__ == "__main__":
    unittest.main()
