"""NVP: read-only release build provenance and hash-bound GPG manifest gate.

Does not access secrets, create signing keys, install software, or publish releases.
Private-key GPG operations happen only in an approved GitHub environment job.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import struct

INSTALLER_NAME = "NVP-Alpha-Setup.exe"
ARTIFACT_NAME = "nvp-data-av01-native-windows-installer"
BUILD_WORKFLOW_ID = 409862454  # Existing DATA-AV installed Windows NSIS build workflow.
FORMAT = "nvp.release.detached_gpg_candidate.v1"
HEX40 = re.compile(r"[0-9a-fA-F]{40}\Z")
HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


def _hex(value: str, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value.lower()


def _run_id(value: object) -> int:
    if type(value) is str and value.isascii() and value.isdecimal() and 5 <= len(value) <= 15:
        return int(value)
    if type(value) is int and value > 0:
        return value
    raise ValueError("Invalid source workflow run identifier")


def validate_build_run(info: dict, *, repo: str, source_sha: str, run_id: int) -> dict:
    """Admit only successful same-repository installed Windows build on main."""
    sha = _hex(source_sha, HEX40, "exact source SHA")
    if not isinstance(info, dict) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise PermissionError("Missing trusted repository/run metadata")
    if info.get("id") != _run_id(run_id) or info.get("workflow_id") != BUILD_WORKFLOW_ID:
        raise PermissionError("Run is not the approved installed Windows build workflow")
    if (info.get("status") != "completed" or info.get("conclusion") != "success"
            or info.get("head_sha") != sha or info.get("head_branch") != "main"
            or info.get("event") not in ("push", "workflow_dispatch")):
        raise PermissionError("Build is not successful, exact-source, main-branch admission")
    repository = info.get("repository")
    if not isinstance(repository, dict) or repository.get("full_name") != repo:
        raise PermissionError("Build source repository differs from exact first-party repository")
    return {
        "source_sha": sha, "build_run_id": info["id"],
        "build_workflow_id": BUILD_WORKFLOW_ID,
        "build_event": info["event"], "build_branch": "main",
        "repository": repo,
    }


def validate_artifacts(document: dict, *, source_run_id: int) -> dict:
    artifacts = document.get("artifacts") if isinstance(document, dict) else None
    if type(artifacts) is not list:
        raise PermissionError("Source run artifact enumeration unavailable")
    found = [a for a in artifacts if isinstance(a, dict) and a.get("name") == ARTIFACT_NAME]
    if len(found) != 1 or found[0].get("expired") is not False:
        raise PermissionError("Missing, expired or ambiguous exact installer artifact")
    a = found[0]
    if (type(a.get("size_in_bytes")) is not int or a["size_in_bytes"] < 1_000_000
            or type(a.get("id")) is not int or a["id"] <= 0):
        raise PermissionError("Installer artifact is implausible or lacks unique identity")
    # Optional owner run reference from GitHub artifact API; do not accept a mismatch.
    wr = a.get("workflow_run")
    if wr is not None and (not isinstance(wr, dict) or wr.get("id") != _run_id(source_run_id)):
        raise PermissionError("Installer artifact belongs to a different workflow run")
    return {"artifact_id": a["id"], "artifact_name": ARTIFACT_NAME}


def verify_installer(path: Path, expected_sha256: str) -> tuple[int, str]:
    expected = _hex(expected_sha256, HEX64, "installer SHA-256")
    path = Path(path)
    if path.name != INSTALLER_NAME or path.is_symlink() or not path.is_file():
        raise PermissionError("Expected one actual NVP-Alpha-Setup.exe regular file")
    if set(p.name for p in path.parent.iterdir()) != {INSTALLER_NAME}:
        raise PermissionError("Downloaded artifact must contain only the exact installer")
    size = path.stat().st_size
    if size < 1_000_000:
        raise PermissionError("Installer smaller than genuine NSIS acceptance minimum")
    with path.open("rb") as f:
        dos = f.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise PermissionError("Downloaded installer does not have a Windows PE DOS header")
        offset = struct.unpack_from("<I", dos, 60)[0]
        if offset < 64 or offset > min(size - 24, 8_000_000):
            raise PermissionError("Invalid Windows PE header pointer")
        f.seek(offset)
        nt = f.read(24)
        if len(nt) != 24 or nt[:4] != b"PE\x00\x00":
            raise PermissionError("Downloaded installer has no Windows PE signature")
        machine = struct.unpack_from("<H", nt, 4)[0]
        if machine not in (0x14C, 0x8664):
            raise PermissionError("Unsupported NSIS Windows installer machine")
        f.seek(0)
        digest = sha256()
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise PermissionError("Installer bytes disagree with independently supplied SHA-256")
    return size, expected


def create_candidate_manifest(*, installer: Path, expected_sha256: str,
                              run_metadata: dict, signer_fingerprint: str,
                              version: str, signing_sha: str, output: Path) -> dict:
    if not isinstance(run_metadata, dict):
        raise PermissionError("Verified source run metadata missing")
    source_sha = _hex(run_metadata.get("source_sha"), HEX40, "source SHA")
    signing_sha = _hex(signing_sha, HEX40, "signing workflow SHA")
    signer = _hex(signer_fingerprint, HEX40, "signer public key fingerprint")
    if source_sha != signing_sha:
        raise PermissionError("Installer source must match the exact signing workflow source")
    if not VERSION.fullmatch(version):
        raise ValueError("Exact approved numeric release version required")
    if run_metadata.get("repository") != "vjmichael/nvp_offline_film":
        raise PermissionError("Wrong signing repository")
    size, digest = verify_installer(installer, expected_sha256)
    artifact_id = run_metadata.get("artifact_id")
    if type(artifact_id) is not int or artifact_id <= 0:
        raise PermissionError("Verified artifact ID required")
    if (run_metadata.get("build_workflow_id") != BUILD_WORKFLOW_ID
            or run_metadata.get("build_branch") != "main"):
        raise PermissionError("No release-approved first-party build record")
    obj = {
        "format": FORMAT, "release_version": version,
        "repository": run_metadata["repository"],
        "source_sha": source_sha,
        "build_run_id": run_metadata["build_run_id"],
        "build_workflow_id": BUILD_WORKFLOW_ID,
        "build_artifact_id": artifact_id,
        "build_artifact_name": ARTIFACT_NAME,
        "build_event": run_metadata["build_event"],
        "build_branch": "main",
        "installer_filename": INSTALLER_NAME,
        "installer_bytes": size, "installer_sha256": digest,
        "signing_workflow_sha": signing_sha,
        "signer_primary_fingerprint": signer,
        "claim": "cryptographic_integrity_and_issuer_key_only",
        "independent_license_review_certified": False,
        "physical_r9700_ltx_accepted": False,
        "production_release_published": False,
    }
    out = Path(output)
    if out.exists() or out.is_symlink():
        raise FileExistsError("Release candidate manifest must be created once")
    out.write_text(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf8")
    return obj


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-run")
    check.add_argument("--run-json", type=Path, required=True)
    check.add_argument("--artifacts-json", type=Path, required=True)
    check.add_argument("--run-id", required=True)
    check.add_argument("--sha", required=True)
    check.add_argument("--repo", required=True)
    check.add_argument("--output", type=Path, required=True)
    prep = sub.add_parser("manifest")
    prep.add_argument("--verified-run", type=Path, required=True)
    prep.add_argument("--installer", type=Path, required=True)
    prep.add_argument("--installer-sha256", required=True)
    prep.add_argument("--signer-fingerprint", required=True)
    prep.add_argument("--source-sha", required=True)
    prep.add_argument("--version", required=True)
    prep.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    if a.command == "check-run":
        if a.output.exists() or a.output.is_symlink():
            raise FileExistsError("Cannot overwrite run provenance")
        rid = _run_id(a.run_id)
        doc = validate_build_run(json.loads(a.run_json.read_text("utf8")), repo=a.repo, source_sha=a.sha, run_id=rid)
        doc.update(validate_artifacts(json.loads(a.artifacts_json.read_text("utf8")), source_run_id=rid))
        a.output.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf8")
        print("NVP_RELEASE_FIRST_PARTY_BUILD_PROVENANCE_PASS_NOT_LICENSE_OR_RELEASE")
    else:
        info = json.loads(a.verified_run.read_text("utf8"))
        doc = create_candidate_manifest(installer=a.installer, expected_sha256=a.installer_sha256,
                                         run_metadata=info, signer_fingerprint=a.signer_fingerprint,
                                         version=a.version, signing_sha=a.source_sha, output=a.output)
        print("NVP_RELEASE_EXACT_INSTALLER_MANIFEST_PASS_GPG_SIGNATURE_PENDING", doc["installer_sha256"])


if __name__ == "__main__":
    main()
