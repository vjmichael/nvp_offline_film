"""NVP-AI-03: trusted-host read operation dispatcher.

No model-facing server, token issuer, local HTTP handler or creator approval
authority is introduced. The embedding native desktop host must authenticate
the caller and supply an authorization callback that checks the *current*
scope on every invocation. Mutation and native worker admission remain owned
by their established NVP hosts and ApprovedTaskBindings.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

from backend.nvp_ai_context import assemble_task_context, discover_capabilities
from backend.nvp_ai_refs import read_screenplay_lines
from backend.nvp_studio import Studio

MAX_REQUEST_BYTES = 8192
_READ_LINES = "nvp.screenplay.read_lines.v1"
_CONTEXT = "nvp.context.assemble.v1"


def _canonical(document: dict) -> bytes:
    if type(document) is not dict:
        raise TypeError("Typed operation request must be a dictionary")
    try:
        data = json.dumps(document, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Request cannot be sealed") from exc
    if not 0 < len(data) <= MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds maximum size")
    return data


@dataclass(frozen=True)
class TrustedReadScope:
    """Constructed ONLY by the embedding trusted host after authentication.

    This value is a request context, never a bearer token or proof of access.
    The policy callback must independently check the current identity,
    project, operation and digest; an arbitrary dataclass is not authority.
    """
    actor_id: str
    project_id: str
    turn_id: str

    def __post_init__(self):
        for field in (self.actor_id, self.project_id, self.turn_id):
            if type(field) is not str or not 1 <= len(field) <= 160:
                raise ValueError("Invalid trusted scope field")


class NativeAiReadHost:
    """Authorized, bounded read dispatch with deterministic operation receipts.

    authorize_read(scope, capability_id, request_sha256, request) must
    validate current trusted actor/project/turn access; it must return the
    literal boolean True. An LLM must never supply this callback.
    """

    def __init__(self, studio: Studio, *, authorize_read: Callable):
        if not isinstance(studio, Studio) or not callable(authorize_read):
            raise TypeError("Studio and trusted read policy callback required")
        self._studio = studio
        self._authorize_read = authorize_read

    def catalog(self) -> dict:
        # Public discovery grants nothing and cannot execute handlers.
        return discover_capabilities()

    def execute_read(self, scope: TrustedReadScope, request: dict) -> dict:
        if not isinstance(scope, TrustedReadScope):
            raise PermissionError("Trusted native scope required")
        raw = _canonical(request)
        capability = request.get("capability_id")
        allowed = {_READ_LINES, _CONTEXT}
        if type(capability) is not str or capability not in allowed:
            raise ValueError("Unknown or non-read capability")
        expected = {
            _READ_LINES: {"capability_id", "project_id", "source_revision",
                          "scene_id", "start_line", "end_line", "max_lines",
                          "require_current"},
            _CONTEXT: {"capability_id", "project_id", "source_revision",
                       "task", "scene_id", "max_lines"},
        }[capability]
        if set(request) - expected:
            raise ValueError("Unrecognized operation fields")
        if request.get("project_id") != scope.project_id:
            raise PermissionError("Cross-project access denied")
        digest = hashlib.sha256(raw).hexdigest()
        # No read occurs before the host's current policy decision.
        if self._authorize_read(scope, capability, digest, json.loads(raw)) is not True:
            raise PermissionError("Current host read authorization denied")
        if capability == _READ_LINES:
            if "require_current" in request and request["require_current"] is not True:
                raise ValueError("Current revision is mandatory for this host operation")
            result = read_screenplay_lines(
                self._studio, scope.project_id, request["source_revision"],
                scene_id=request.get("scene_id"),
                start_line=request.get("start_line"),
                end_line=request.get("end_line"),
                max_lines=request.get("max_lines", 120),
                require_current=True,
            )
        else:
            result = assemble_task_context(
                self._studio, scope.project_id, request["source_revision"],
                request["task"], scene_id=request.get("scene_id"),
                max_lines=request.get("max_lines", 120),
            )
        result_sha = hashlib.sha256(_canonical_result(result)).hexdigest()
        return {
            "format": "nvp.ai.read_receipt.v1",
            "capability_id": capability,
            "project_id": scope.project_id,
            "turn_id": scope.turn_id,
            "request_sha256": digest,
            "result_sha256": result_sha,
            "result": result,
            "authorization_outcome": "authorized_at_dispatch",
            "authority_granted_to_model": False,
            "creator_approval_granted": False,
            "durable_execution_record": False,
            "side_effects_performed": False,
        }


def _canonical_result(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
