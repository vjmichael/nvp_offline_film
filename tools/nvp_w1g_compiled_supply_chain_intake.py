"""W1-G original five-worker native/compiler/import review intake, NOT approval.

Joins the actual executable bytes, compiler provenance, all five role source
translation units and independently inspected PE/ELF native linker imports.
Emits an unsigned candidate for a real outside reviewer; never signs,
supplies a license, assumes runtime libraries exist, or authorizes NSIS.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from tools.nvp_w1g_compile_first_party_workers import SOURCE, SOURCE_ROOT, digest_file
from tools.nvp_w1g_native_link_audit import FORMAT as LINK_FORMAT, LIBRARY
from tools.nvp_w1g_worker_package import ROLES, _check_roster, _verify_binary

FORMAT = "nvp.w1g.compiled_native_supply_review_intake.v1"
REQUIRED_DIGEST = set("0123456789abcdef")


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _read(path):
    if (path.is_symlink() or not path.is_file() or
        not 0 < path.stat().st_size <= 512 * 1024):
        raise PermissionError("Original bounded regular native supply receipt required")
    return json.loads(path.read_text("utf8"))


def _sha(value):
    return (type(value) is str and len(value) == 64 and
            set(value) <= REQUIRED_DIGEST)


def original_compiled_native_review_intake(binary_dir: Path, import_receipt: Path):
    binary_dir = Path(binary_dir)
    if not binary_dir.is_dir() or binary_dir.is_symlink():
        raise PermissionError("Original native compiled candidate directory unavailable")
    build = _read(binary_dir / "build-candidate.json")
    links = _read(Path(import_receipt))
    if (type(build) is not dict or
        build.get("status") != "FIVE_REAL_NATIVE_EXECUTABLES_COMPILED_CANDIDATE" or
        build.get("native_executables_compiled") is not True or
        build.get("production_native_roles_complete") is not False or
        build.get("role_count") != 5):
        raise PermissionError("Unreviewed exact five-role native compilation proof required")
    roster = _check_roster(build.get("roster"))
    roles = {row["role"]: row for row in roster["workers"]}
    if (len(roles) != 5 or set(roles) != set(ROLES) or
        not _sha(build.get("source_sha256")) or
        build["source_sha256"] != digest_file(SOURCE)):
        raise PermissionError("Native compiler original source identity not established")
    src = build.get("role_translation_unit_sha256")
    if type(src) is not dict or set(src) != set(ROLES):
        raise PermissionError("Five compiler translation-unit identities required")
    for role in ROLES:
        unit = SOURCE_ROOT / "native" / (role + ".cpp")
        if (unit.is_symlink() or not unit.is_file() or
            not _sha(src[role]) or src[role] != digest_file(unit)):
            raise PermissionError("Original role compiler source changed: " + role)
    if (not _sha(build.get("compiler_image_sha256")) or
        type(build.get("host_architecture")) is not str or
        not build["host_architecture"] or
        type(build.get("host_os")) is not str or not build["host_os"]):
        raise PermissionError("Compiler binary SHA and host provenance required")
    # The CI native linker tool independently reads the actual program image.
    # A copied/supplied import JSON cannot be accepted against another build.
    if (type(links) is not dict or links.get("format") != LINK_FORMAT or
        links.get("status") != "NATIVE_LINKER_DEPENDENCY_CANDIDATE_ONLY" or
        links.get("platform") != roster["platform"] or
        links.get("source_sha256") != build["source_sha256"] or
        type(links.get("imports")) is not list or len(links["imports"]) != 5 or
        links.get("external_native_dependency_license_reviewed") is not False or
        links.get("runtime_library_bytes_pinned") is not False):
        raise PermissionError("Actual matching native import audit is required")
    imports = {}
    for row in links["imports"]:
        if (type(row) is not dict or set(row) !=
            {"role", "filename", "executable_sha256", "imported_libraries"}):
            raise PermissionError("Unknown original linker import record fields")
        role = row["role"]
        if role not in roles or role in imports:
            raise PermissionError("Duplicated or unregistered original linker role")
        expected = roles[role]
        if ((row["filename"], row["executable_sha256"]) !=
            (expected["filename"], expected["sha256"])):
            raise PermissionError("Native linker audit not bound to executable: " + role)
        libs = row["imported_libraries"]
        if (type(libs) is not list or not 1 <= len(libs) <= 128 or
            any(type(lib) is not str or not LIBRARY.fullmatch(lib) for lib in libs) or
            len({lib.casefold() for lib in libs}) != len(libs)):
            raise PermissionError("Unreviewed/ambiguous native linked dependency list")
        executable = binary_dir / expected["filename"]
        _verify_binary(executable, roster["platform"])
        if digest_file(executable) != expected["sha256"]:
            raise PermissionError("Original compiled PE/ELF executable changed: " + role)
        imports[role] = sorted(libs, key=str.casefold)
    if set(imports) != set(ROLES):
        raise PermissionError("Native imported-library report lacks a worker role")
    # Imported SONAME/DLL names alone cannot establish resolved library bytes,
    # runtime availability, platform provenance or legal redistribution.
    unique_libraries = sorted(
        {lib for rows in imports.values() for lib in rows}, key=str.casefold)
    intake = {
        "format": FORMAT,
        "status": "EXACT_NATIVE_COMPILER_AND_LINK_IMPORTS_UNREVIEWED",
        "platform": roster["platform"],
        "original_native_source_sha256": build["source_sha256"],
        "role_translation_unit_sha256": src,
        "compiler_executable_sha256": build["compiler_image_sha256"],
        "compiler_host_os": build["host_os"],
        "compiler_host_architecture": build["host_architecture"],
        "worker_executable_sha256_by_role":
            {role: roles[role]["sha256"] for role in sorted(ROLES)},
        "imported_native_libraries_by_role": imports,
        "all_direct_native_imports": unique_libraries,
        "native_import_inventory_sha256": _digest(links),
        "compiled_binary_receipt_sha256": _digest(build),
        "five_compiled_worker_bytes_and_direct_imports_joined": True,
        "imported_runtime_library_bytes_resolved": False,
        "transitive_native_runtime_dependencies_inventoried": False,
        "external_native_library_redistribution_approved": False,
        "externally_signed_release_or_wheelhouse_verified": False,
        "physical_microphone_or_dual_adc_verified": False,
        "physical_windows_efs_cross_principal_recovery_verified": False,
        "native_role_complete_film_pipeline_verified": False,
        "creator_nsis_or_rollback_authorized": False,
        "review_required": [
            "Resolve every native DLL/SONAME and transitive runtime dependency to installed bytes, versions and origin",
            "Obtain independent native/runtime license, redistribution and signing review",
            "Provide complete pinned transitive offline Python wheelhouse with signed exact-byte review",
            "Replace five bounded capability slices with original complete filmmaking-role implementations",
            "Obtain physical mono microphone and independent dual-ADC clock, overflow/unplug and Take restart evidence",
            "Obtain creator-PC EFS post-reboot and separate recovery-SID key-backup proof",
            "Reverify installed owner roots and request distinct native one-use upgrade and rollback authorizations",
        ],
        "production_readiness_accepted": False,
    }
    return intake


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only UNSIGNED W1-G compiler/linker intake")
    parser.add_argument("--binary-dir", type=Path, required=True)
    parser.add_argument("--native-imports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Cannot overwrite original reviewer intake evidence")
    intake = original_compiled_native_review_intake(args.binary_dir, args.native_imports)
    with args.output.open("x", encoding="utf8") as out:
        json.dump(intake, out, indent=2, sort_keys=True)
        out.write("\n")
    print(json.dumps({
        "status": intake["status"], "platform": intake["platform"],
        "role_count": len(intake["worker_executable_sha256_by_role"]),
        "native_imported_libraries": intake["all_direct_native_imports"],
        "production_readiness_accepted": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
