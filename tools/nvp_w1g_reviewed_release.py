"""W1-G independent, SHA-bound cryptographic release license review gate.

The installer/build receipt cannot self-certify a redistribution license.
An OWNER-PINNED external Ed25519 reviewer key must validate a complete
release inventory and per-artifact license attribution. No private keys,
approval minting, downloads or network lookup occur in NVP.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path
import re

FORMAT="nvp.w1g.signed_redistribution_license_review.v1"
SHA=re.compile(r"[a-f0-9]{64}\Z")
SPDX=re.compile(r"[A-Za-z0-9.+()\- ]{2,128}\Z")


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def license_review_digest(receipt):
    if type(receipt) is not dict or type(receipt.get("files")) is not dict:
        raise ValueError("Original external installed payload receipt required")
    return sha256(_canonical({
        "platform":receipt.get("platform"),
        "app_sha256":receipt.get("app_sha256"),
        "files":receipt["files"],
    })).hexdigest()


def verify_signed_release_review(receipt, signed_review, *,
                                 pinned_reviewer_public_key: bytes):
    if (type(pinned_reviewer_public_key) is not bytes or
        len(pinned_reviewer_public_key)!=32):
        raise PermissionError("Exact owner-pinned 32-byte reviewer Ed25519 key unavailable")
    if (type(signed_review) is not dict or
        set(signed_review)!={"payload","signature_base64"} or
        type(signed_review["payload"]) is not dict):
        raise PermissionError("Signed release/license reviewer attestation required")
    data=signed_review["payload"]
    if (set(data)!={"format","payload_sha256","platform",
                   "reviewed_artifacts","reviewer_reference"} or
        data.get("format")!=FORMAT or
        data.get("platform")!=receipt.get("platform") or
        data.get("payload_sha256")!=license_review_digest(receipt) or
        type(data.get("reviewer_reference")) is not str or
        not 8<=len(data["reviewer_reference"])<=256):
        raise PermissionError("Reviewer signature is not scoped to this exact release")
    covered=data.get("reviewed_artifacts")
    files=receipt["files"]
    if type(covered) is not list or len(covered)!=len(files) or len(files)>20000:
        raise PermissionError("Every bundled payload artifact requires review coverage")
    seen=set()
    for row in covered:
        if (type(row) is not dict or
            set(row)!={"file","sha256","spdx_license","redistribution_reference"} or
            type(row.get("file")) is not str or
            row["file"] not in files or row["file"] in seen or
            type(row.get("sha256")) is not str or
            row["sha256"]!=files[row["file"]]["sha256"] or
            type(row.get("spdx_license")) is not str or
            not SPDX.fullmatch(row["spdx_license"]) or
            row["spdx_license"].strip().upper() in
                ("REVIEW_REQUIRED","UNKNOWN","TBD","NOASSERTION","UNLICENSED") or
            type(row.get("redistribution_reference")) is not str or
            row["redistribution_reference"].strip().upper() in
                ("REVIEW_REQUIRED","UNKNOWN","TBD","NOASSERTION") or
            not 8<=len(row["redistribution_reference"])<=500):
            raise PermissionError("Unreviewed native dependency, worker or distribution condition")
        seen.add(row["file"])
    if seen!=set(files):
        raise PermissionError("Reviewed license inventory omits installed runtime artifacts")
    try:
        signature=base64.b64decode(signed_review["signature_base64"],validate=True)
        if len(signature)!=64:
            raise ValueError("Not an Ed25519 signature")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(pinned_reviewer_public_key).verify(
            signature,_canonical(data))
    except (ImportError,ValueError,TypeError,Exception) as error:
        # Cryptographic verifier absent, bad signature, corrupt document,
        # or mismatched pinned reviewer key must ALL fail closed.
        raise PermissionError("Independent pinned reviewer signature is not valid") from error
    return {
        "license_review_signature_verified": True,
        "reviewed_artifact_count": len(files),
        "reviewed_payload_sha256":data["payload_sha256"],
        "reviewer_reference":data["reviewer_reference"],
        "redistribution_licenses_verified": True,
    }
