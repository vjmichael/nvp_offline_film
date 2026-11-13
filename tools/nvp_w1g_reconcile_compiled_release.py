"""W1-G first-party compiled worker + reviewed release exact-byte reconciliation.

This is READ-ONLY. There is no signing key, producer license approval, EFS key
or NSIS mutation here. Real Windows compiled role candidates are compared to
the actual staged NVP private worker binaries. Then independently signed
exact installed-bundle and offline dependency approvals are reverified.
A successful result does NOT attest feature-complete filmmaking, creator
consent, physical EFS recovery or a production deployment.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path

from tools.nvp_w1g_worker_package import (
    ROLES,_check_roster,_verify_binary,verify_native_workers,
)
from tools.nvp_w1g_native_package import verify_installed
from tools.nvp_w1g_reviewed_release import verify_signed_release_review
from tools.nvp_w1g_signed_wheelhouse import verify_signed_offline_wheelhouse


def _sha(path):
    h=sha256()
    with path.open("rb") as fd:
        for part in iter(lambda:fd.read(1048576),b""):
            h.update(part)
    return h.hexdigest()


def reconcile_original_native_bytes(compiled:Path, staged:Path) -> dict:
    compiled=Path(compiled);staged=Path(staged)
    if any(not p.is_dir() or p.is_symlink() for p in (compiled,staged)):
        raise PermissionError("Original native compile and staged release roots required")
    build_path=compiled/"build-candidate.json"
    if (not build_path.is_file() or build_path.is_symlink() or
        build_path.stat().st_size>128000):
        raise PermissionError("Actual native compiler candidate receipt required")
    build=json.loads(build_path.read_text("utf8"))
    if (type(build) is not dict or
        build.get("status")!="FIVE_REAL_NATIVE_EXECUTABLES_COMPILED_CANDIDATE" or
        build.get("native_executables_compiled") is not True or
        build.get("role_count")!=5 or
        build.get("production_native_roles_complete") is not False):
        raise PermissionError("Native compiler receipt is not an actual unapproved five-role candidate")
    roster=_check_roster(build.get("roster"))
    source=Path(__file__).resolve().parents[1]/"native"/"w1g_first_party_worker.cpp"
    if (not source.is_file() or source.is_symlink() or
        type(build.get("source_sha256")) is not str or
        _sha(source)!=build["source_sha256"]):
        raise PermissionError("Compiled native worker source identity differs from current audited source")
    if roster["platform"]!="windows-amd64":
        raise PermissionError("Windows installed NSIS byte reconciliation needs PE64 original workers")
    installed=verify_native_workers(staged,expected_platform="windows-amd64")
    if set(installed["roles"])!=set(ROLES):
        raise PermissionError("Signed installed release lacks complete five-role roster")
    manifest=json.loads((staged/"_internal"/"nvp_workers"/"manifest.json").read_text("utf8"))
    actual={w["role"]:w for w in manifest["workers"]}
    compiled_roles={w["role"]:w for w in roster["workers"]}
    if set(compiled_roles)!=set(ROLES) or set(actual)!=set(ROLES):
        raise PermissionError("Exact native worker role identities incomplete")
    for role in sorted(ROLES):
        original=compiled_roles[role]
        worker=actual[role]
        if original!=worker:
            raise PermissionError("Staged worker role/file/hash changed from original compiled candidate: "+role)
        a=compiled/original["filename"]
        b=staged/"_internal"/"nvp_workers"/worker["filename"]
        _verify_binary(a,"windows-amd64")
        if _sha(a)!=original["sha256"] or _sha(b)!=worker["sha256"]:
            raise PermissionError("Staged native executable bytes changed after compilation: "+role)
    return {
        "status":"FIVE_ACTUAL_COMPILED_WORKER_BYTES_MATCH_STAGED_NSIS",
        "source_sha256":build.get("source_sha256"),
        "worker_sha256_by_role":{r:compiled_roles[r]["sha256"] for r in sorted(ROLES)},
        "candidate_executable_bytes_bound_to_staged_release":True,
        "trusted_external_compiler_provenance_signature_verified":False,
        "full_native_film_role_completeness_proven":False,
        "independent_reviews_verified":False,
        "creator_authorization_obtained":False,
    }


def reconcile_independently_signed_release(*, compiled:Path, staged:Path,
        installed_receipt:dict, signed_release_review:dict,
        offline_lock:dict, wheelhouse:Path, signed_wheel_review:dict,
        pinned_external_reviewer_public_key:bytes) -> dict:
    exact=reconcile_original_native_bytes(compiled,staged)
    verified=verify_installed(installed_receipt,staged)
    if verified.get("native_worker_manifest_verified") is not True:
        raise PermissionError("Signed actual release lacks native worker inventory")
    signed_release=verify_signed_release_review(
        installed_receipt,signed_release_review,
        pinned_reviewer_public_key=pinned_external_reviewer_public_key)
    signed_wheels=verify_signed_offline_wheelhouse(
        offline_lock,wheelhouse,signed_wheel_review,
        platform="windows-amd64",
        pinned_reviewer_public_key=pinned_external_reviewer_public_key)
    # Verify source and private worker names also appeared in the signed
    # INSTALLED package file inventory, not only an independent roster.
    for role,digest in exact["worker_sha256_by_role"].items():
        row=next(w for w in json.loads(
            (staged/"_internal"/"nvp_workers"/"manifest.json").read_text("utf8"))["workers"]
                 if w["role"]==role)
        name="_internal/nvp_workers/"+row["filename"]
        packaged=installed_receipt["files"].get(name)
        if type(packaged) is not dict or packaged.get("sha256")!=digest:
            raise PermissionError("Signed release file inventory omits original compiled native worker: "+role)
    return {
        **exact,
        "status":"NVP_W1G_SIGNED_RELEASE_AND_OFFLINE_BYTES_RECONCILED",
        "signed_installed_file_count":signed_release["reviewed_artifact_count"],
        "signed_offline_wheel_count":signed_wheels["wheel_count"],
        "installed_host_sha256":installed_receipt["app_sha256"],
        "external_release_and_offline_signatures_verified":True,
        "full_native_film_role_completeness_proven":False,
        "physical_efs_recovery_verified":False,
        "creator_authorization_obtained":False,
        "production_upgrade_executed":False,
    }
