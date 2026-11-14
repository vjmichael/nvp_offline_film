"""W1-G exact-byte offline wheelhouse signed redistribution admission.

A lock file's free-text "license_review" is not an independent approval. The
owner must supply actual wheel bytes plus an external Ed25519 reviewer signature
covering every wheel and the complete exact lock. No network, signing-key
generation, wheel download or legal approval occurs in this module.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from tools.nvp_w1g_native_dependencies import validate_lock
from tools.nvp_w1g_reviewed_release import (
    FORMAT as SIGNED_FORMAT, license_review_digest, verify_signed_release_review,
)

FORMAT = "nvp.w1g.signed_offline_wheelhouse_payload.v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def actual_wheelhouse_receipt(lock: dict, wheelhouse: Path, *, platform: str) -> dict:
    root=Path(wheelhouse)
    verified=validate_lock(lock,root,platform=platform)
    files={}
    names=set()
    for wheel in verified:
        name=wheel["filename"]
        if name.casefold() in names:
            raise RuntimeError("Wheelhouse has duplicate or case-colliding locked filenames")
        names.add(name.casefold())
        binary=root/name
        if binary.is_symlink() or not binary.is_file():
            raise RuntimeError("Reviewed wheel image disappeared or was linked")
        files[name]={"sha256":wheel["sha256"],"bytes":binary.stat().st_size}
    discovered=[p.name for p in root.iterdir()
                if p.is_file() or p.is_symlink()]
    locked={row["filename"] for row in verified}
    if len(discovered)!=len(locked) or set(discovered)!=locked:
        raise RuntimeError("Offline wheelhouse includes unreviewed extra files or lacks locked wheels")
    return {
        "format":FORMAT,"platform":platform,
        # Scope the independent signature to the EXACT transitive lock, not
        # just the wheel bytes. A different lock/architecture cannot be reused.
        "app_sha256":sha256(_canonical(lock)).hexdigest(),
        "files":files,
    }


def unsigned_wheelhouse_review_candidate(lock: dict, wheelhouse: Path,
                                         *, platform: str) -> dict:
    receipt=actual_wheelhouse_receipt(lock,wheelhouse,platform=platform)
    return {
        "status":"UNSIGNED_WHEELHOUSE_REVIEW_CANDIDATE_NOT_APPROVED",
        "receipt":receipt,
        "signed_review":{
            "payload":{
                "format":SIGNED_FORMAT,
                "platform":platform,
                "payload_sha256":license_review_digest(receipt),
                "reviewer_reference":"REVIEW_REQUIRED",
                "reviewed_artifacts":[{
                    "file":name,"sha256":row["sha256"],
                    "spdx_license":"REVIEW_REQUIRED",
                    "redistribution_reference":"REVIEW_REQUIRED"}
                    for name,row in sorted(receipt["files"].items())],
            },
            "signature_base64":None,
        },
        "redistribution_approved":False,
    }


def verify_signed_offline_wheelhouse(lock: dict, wheelhouse: Path,
                                     signed_review: dict, *,
                                     platform: str,
                                     pinned_reviewer_public_key: bytes) -> dict:
    receipt=actual_wheelhouse_receipt(lock,wheelhouse,platform=platform)
    result=verify_signed_release_review(
        receipt,signed_review,
        pinned_reviewer_public_key=pinned_reviewer_public_key)
    # Do not allow one unsigned description in the lock to contradict the
    # independently signed per-wheel redistribution evidence.
    signed={item["file"]:item for item in
            signed_review["payload"]["reviewed_artifacts"]}
    if any(signed[row["filename"]]["redistribution_reference"] !=
           row["license_review"] for row in lock["wheels"]):
        raise PermissionError("Offline wheel lock is inconsistent with signed reviewer references")
    return {
        "status":"EXTERNAL_OFFLINE_WHEELHOUSE_REVIEW_VERIFIED",
        "wheel_lock_sha256":receipt["app_sha256"],
        "review_scope_sha256":license_review_digest(receipt),
        "wheel_count":result["reviewed_artifact_count"],
        "reviewer_signature_verified":True,
        "native_executable_workers_verified":False,
        "physical_owner_or_efs_recovery_verified":False,
        "production_upgrade_authorized":False,
    }


def _read_json(path: Path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise PermissionError("Owner-supplied absolute unsigned/signed evidence file required")
    if path.stat().st_size>4*1024*1024:
        raise PermissionError("Unbounded external wheel review file")
    return json.loads(path.read_text("utf8"))


def verify_from_paths(*, lock_path: Path, wheelhouse: Path,
                      signed_review_path: Path, reviewer_key: bytes,
                      platform: str) -> dict:
    if not all(isinstance(p,Path) and p.is_absolute() for p in
               (lock_path,wheelhouse,signed_review_path)):
        raise PermissionError("Absolute local offline supply paths required")
    return verify_signed_offline_wheelhouse(
        _read_json(lock_path),wheelhouse,_read_json(signed_review_path),
        platform=platform,pinned_reviewer_public_key=reviewer_key)


def main(argv=None):
    ap=argparse.ArgumentParser(description="Read-only offline wheelhouse review")
    ap.add_argument("action",choices=("candidate","verify"))
    ap.add_argument("--platform",choices=("windows-amd64","linux-amd64"),required=True)
    ap.add_argument("--wheel-lock",type=Path,required=True)
    ap.add_argument("--wheelhouse",type=Path,required=True)
    ap.add_argument("--signed-review",type=Path)
    ap.add_argument("--pinned-reviewer-key",type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args(argv)
    if args.action=="candidate":
        if args.output is None or args.output.exists() or args.output.is_symlink():
            ap.error("An unused output path is required for unsigned candidates")
        candidate=unsigned_wheelhouse_review_candidate(
            _read_json(args.wheel_lock),args.wheelhouse,platform=args.platform)
        args.output.write_text(json.dumps(candidate,sort_keys=True,indent=2)+"\n",encoding="utf8")
        print(json.dumps({"status":candidate["status"],"output":str(args.output)}))
    else:
        if args.signed_review is None or args.pinned_reviewer_key is None:
            ap.error("Independent signed review and external pinned public key required")
        if (args.pinned_reviewer_key.is_symlink() or
            not args.pinned_reviewer_key.is_file() or
            args.pinned_reviewer_key.stat().st_size!=32):
            raise PermissionError("Owner's external pinned 32-byte Ed25519 public key missing")
        result=verify_from_paths(
            lock_path=args.wheel_lock,wheelhouse=args.wheelhouse,
            signed_review_path=args.signed_review,
            reviewer_key=args.pinned_reviewer_key.read_bytes(),
            platform=args.platform)
        print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
