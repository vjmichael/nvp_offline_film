"""W1-G physical EFS recovery policy gate — external sign-off plus live OS EFS.

A GitHub job, same-user reboot, JSON callback or test private key is not a
physical key-recovery witness. The independent reviewer must inspect the real
owner-machine recovery procedure and sign the bounded nonsecret evidence.
This module checks that independent signature, exact Windows root and live EFS
inheritance; it never loads, creates, exports or uploads private EFS keys.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time

from backend.nvp_w1g_encrypted_source import require_efs_stage, verify_efs_inputs
from tools.nvp_w1g_windows_efs_proof import _windows_process_token_sid
from tools.nvp_w1g_reviewed_release import _canonical

FORMAT="nvp.w1g.independent_physical_efs_recovery_review.v1"
MAX_REVIEW_AGE_SECONDS=30*24*3600


def validate_signed_efs_review(signed_review: dict, *,
                               scratch_root: Path,
                               preparer_sid: str,
                               reviewer_public_key: bytes,
                               now_unix: float | None=None) -> dict:
    """Cryptographically verify an EXTERNAL reviewer statement, not OS proof."""
    if (type(reviewer_public_key) is not bytes or
        len(reviewer_public_key)!=32 or type(signed_review) is not dict or
        set(signed_review)!={"payload","signature_base64"}):
        raise PermissionError("Independent signed physical EFS recovery review is required")
    data=signed_review["payload"]
    if type(data) is not dict or set(data)!={
            "format","scratch_root","prepared_windows_token_sid",
            "recovery_windows_token_sid","nonsecret_test_sha256",
            "post_reboot_same_user_reopen_verified",
            "cross_principal_efs_decryption_verified",
            "offline_efs_key_backup_independently_reviewed",
            "reviewer_reference","reviewed_at_unix"}:
        raise PermissionError("Incomplete external physical EFS recovery review")
    root=Path(scratch_root)
    expected_root=str(root.resolve(strict=True))
    date=data["reviewed_at_unix"]
    now=time.time() if now_unix is None else now_unix
    if (data["format"]!=FORMAT or
        data["scratch_root"]!=expected_root or
        data["prepared_windows_token_sid"]!=preparer_sid or
        type(preparer_sid) is not str or not preparer_sid.startswith("S-1-") or
        type(data["recovery_windows_token_sid"]) is not str or
        not data["recovery_windows_token_sid"].startswith("S-1-") or
        data["recovery_windows_token_sid"]==preparer_sid or
        type(data["nonsecret_test_sha256"]) is not str or
        len(data["nonsecret_test_sha256"])!=64 or
        any(c not in "0123456789abcdef" for c in data["nonsecret_test_sha256"]) or
        data["post_reboot_same_user_reopen_verified"] is not True or
        data["cross_principal_efs_decryption_verified"] is not True or
        data["offline_efs_key_backup_independently_reviewed"] is not True or
        type(data["reviewer_reference"]) is not str or
        not 8<=len(data["reviewer_reference"])<=256 or
        type(date) not in (int,float) or type(now) not in (int,float) or
        not now-MAX_REVIEW_AGE_SECONDS<=date<=now+300):
        raise PermissionError("Physical EFS recovery review is stale, unbound or incomplete")
    try:
        signature=base64.b64decode(signed_review["signature_base64"],validate=True)
        if len(signature)!=64:
            raise ValueError("Invalid Ed25519 signature length")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(reviewer_public_key).verify(
            signature,_canonical(data))
    except Exception as error:
        raise PermissionError("External physical EFS review signature invalid") from error
    return {
        "independently_signed_efs_review_verified":True,
        "signed_efs_review_sha256":sha256(_canonical(data)).hexdigest(),
        "signed_recovery_reviewer_reference":data["reviewer_reference"],
        "key_backup_origin_verified_only_by_independent_reviewer":True,
    }


def verify_current_windows_efs_scratch(scratch_root: Path) -> dict:
    """Write only a disposable nonsecret nonce in a fresh encrypted directory."""
    if os.name!="nt":
        raise RuntimeError("Physical EFS admission requires actual Windows kernel")
    root=Path(scratch_root)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise PermissionError("Owner's dedicated EFS scratch root unavailable")
    stage=Path(tempfile.mkdtemp(prefix="nvp-w1g-live-efs-",dir=root))
    try:
        require_efs_stage(stage)
        data=b"NVP-NONSECRET-LIVE-EFS-TEST:"+secrets.token_bytes(32)
        sample=stage/"nonsecret-review-probe"
        with sample.open("xb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        verify_efs_inputs(stage,(sample.name,))
        if sample.read_bytes()!=data:
            raise PermissionError("Native Windows EFS nonce decryption failed")
        return {
            "native_windows_efs_scratch_verified":True,
            "physical_efs_recovery_proved_by_current_probe":False,
            "source_film_data_used":False,
        }
    finally:
        shutil.rmtree(stage,ignore_errors=False)


def verify_physical_efs_supply(*, scratch_root: Path,
                               signed_review_path: Path,
                               reviewer_public_key: bytes) -> dict:
    if os.name!="nt":
        raise RuntimeError("Native physical Windows EFS recovery required")
    review_path=Path(signed_review_path)
    if (not review_path.is_absolute() or review_path.is_symlink() or
        not review_path.is_file() or review_path.stat().st_size>65536):
        raise PermissionError("External physical EFS reviewer attestation missing")
    signed=json.loads(review_path.read_text("utf8"))
    original_sid=_windows_process_token_sid()
    proof=validate_signed_efs_review(
        signed,scratch_root=scratch_root,preparer_sid=original_sid,
        reviewer_public_key=reviewer_public_key)
    live=verify_current_windows_efs_scratch(scratch_root)
    return {
        "status":"W1G_NATIVE_EFS_WITH_EXTERNAL_RECOVERY_REVIEW_VERIFIED",
        **proof,**live,
        "creator_nsis_upgrade_authorized":False,
        "physical_owner_consent_obtained":False,
    }
