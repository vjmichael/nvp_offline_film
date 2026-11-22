"""Verify a signed, one-use native SCM picture-result witness.

The signing key is never present in NVP/worker, and the pinned verifier key
must be loaded from trusted *installed* host policy (not UI, model or job).
Actual SCM service signing/provisioning and physical WFP/GPU evidence are
separate mandatory Windows acceptance, NOT implemented by this host reader.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

SCM_FORMAT = "nvp.post01f.scm_authenticated_picture_receipt.v1"
ALLOWED = frozenset(("format", "body", "signature"))
BODY = frozenset((
    "job_id", "project_id", "plan_sha256", "picture_sha256", "bootstrap_sha256",
    "model_stack_sha256", "worker_pid", "appcontainer_sid_sha256",
    "appcontainer_zero_network_caps_verified", "wfp_no_egress_verified",
    "efs_verified", "scm_service_custody_verified", "receipt_nonce",
))
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")


def verify_signed_scm_picture_result(envelope: dict, *,
                                     pinned_public_key: bytes,
                                     expected: dict,
                                     consume_once) -> dict:
    """Signed positive evidence, never a promise of an installed SCM server."""
    if (type(envelope) is not dict or set(envelope) != ALLOWED or
        envelope.get("format") != SCM_FORMAT or type(envelope.get("body")) is not dict or
        set(envelope["body"]) != BODY or not callable(consume_once)):
        raise PermissionError("Invalid signed SCM result envelope")
    body = envelope["body"]
    if (type(pinned_public_key) is not bytes or len(pinned_public_key) != 32 or
        type(envelope["signature"]) is not str or
        not re.fullmatch(r"[0-9a-f]{128}", envelope["signature"])):
        raise PermissionError("Missing installed SCM verifier key/signature")
    for field in ("job_id", "project_id", "plan_sha256", "picture_sha256",
                  "bootstrap_sha256", "model_stack_sha256", "worker_pid", "appcontainer_sid_sha256"):
        if field not in expected or type(body[field]) is not type(expected[field]) or body[field] != expected[field]:
            raise PermissionError("SCM result did not bind exact protected job/process/picture")
    for field in ("plan_sha256", "picture_sha256", "bootstrap_sha256", "model_stack_sha256", "appcontainer_sid_sha256"):
        if not isinstance(body[field], str) or not HEX64.fullmatch(body[field]):
            raise PermissionError("SCM source identity digest invalid")
    if (type(body["worker_pid"]) is not int or body["worker_pid"] <= 0 or
        type(body["receipt_nonce"]) is not str or not NONCE.fullmatch(body["receipt_nonce"]) or
        any(body.get(field) is not True for field in (
            "appcontainer_zero_network_caps_verified", "wfp_no_egress_verified",
            "efs_verified", "scm_service_custody_verified"))):
        raise PermissionError("Required native SCM/WFP/EFS authority not verified")
    signed = json.dumps({"format":SCM_FORMAT,"body":body},
                        sort_keys=True, separators=(",", ":"),
                        ensure_ascii=True, allow_nan=False).encode("ascii")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(pinned_public_key)
        key.verify(bytes.fromhex(envelope["signature"]), signed)
    except Exception as exc:
        raise PermissionError("SCM picture-result signature verification failed") from exc
    # Consume nonce only after verified signature and identity. Must be a
    # trusted, durable/replay-safe host-side operation; no process-local set.
    if consume_once(body["job_id"], body["receipt_nonce"], sha256(signed).hexdigest()) is not True:
        raise PermissionError("Stale/replayed SCM picture receipt")
    return {
        "process_tree_custody_verified": True,
        "appcontainer_zero_network_caps_verified": True,
        "wfp_no_egress_verified": True,
        "efs_verified": True,
        "scm_authenticated_receipt_verified": True,
        "job_id": body["job_id"],
        "worker_pid": body["worker_pid"],
        "plan_sha256": body["plan_sha256"],
        "picture_sha256": body["picture_sha256"],
        "scm_receipt_sha256": sha256(signed).hexdigest(),
    }


class SignedScmPictureWitness:
    """Host-side adapter for the already-authenticated SCM picture channel.

    `receive_from_scm` must return a finite signed envelope from a reviewed
    installed SCM service. It is not a worker-facing HTTP endpoint. A default
    SCM service implementation or private signing key is NOT provided here.
    """

    def __init__(self, *, pinned_public_key: bytes, receive_from_scm,
                 consume_once):
        if (type(pinned_public_key) is not bytes or len(pinned_public_key) != 32 or
            not callable(receive_from_scm) or not callable(consume_once)):
            raise TypeError("Installed SCM verifier/channel and durable nonce store required")
        self.key = pinned_public_key
        self.receive = receive_from_scm
        self.consume = consume_once

    def __call__(self, scope: dict, kernel: dict) -> dict:
        if (type(scope) is not dict or type(kernel) is not dict or
            kernel.get("format") != "nvp.post01f.windows_appcontainer_kernel_exit.v1" or
            kernel.get("process_tree_custody_verified") is not True or
            kernel.get("kernel_job_tree_reaped") is not True or
            kernel.get("release_fence_closed") is not True or
            type(kernel.get("worker_pid")) is not int):
            raise PermissionError("Original AppContainer kernel exit must be independently verified")
        for key in ("job_id", "project_id", "plan_sha256", "bootstrap_sha256",
                    "model_stack_sha256", "picture_sha256"):
            if key not in scope:
                raise PermissionError("Missing host-bound worker/result source identity")
        original = self.receive(scope["job_id"],kernel["worker_pid"])
        if type(original) is not bytes or not 2 <= len(original) <= 8192:
            raise PermissionError("Expected a bounded independently signed SCM transport response")
        try:
            envelope = json.loads(original)
        except (ValueError, UnicodeError) as exc:
            raise PermissionError("Invalid SCM signed picture transport response") from exc
        expected = {key: scope[key] for key in (
            "job_id", "project_id", "plan_sha256", "bootstrap_sha256",
            "model_stack_sha256", "picture_sha256")}
        expected.update({"worker_pid":kernel["worker_pid"],
                         "appcontainer_sid_sha256":kernel["appcontainer_sid_sha256"]})
        return verify_signed_scm_picture_result(
            envelope,pinned_public_key=self.key,expected=expected,
            consume_once=self.consume)
