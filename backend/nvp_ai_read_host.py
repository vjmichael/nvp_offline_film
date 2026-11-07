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
from backend.nvp_film_index import FilmIndex
from backend.nvp_wo6_creator_plan import (
    capability_descriptor as wo6_retake_descriptor, plan_source_retake)
from backend.nvp_wo6_impact_preview import (
    CAPABILITY as IMPACT_PREVIEW_CAPABILITY, preview_source_impact)
from backend.nvp_wo6_scene_context import (
    CAPABILITY as SCENE_CREW_CAPABILITY, assemble_film_crew_context)
from backend.nvp_wo6_tool_readiness import (
    TrustedToolInventory, FORMAT as TOOLS_FORMAT, preflight_tool_inventory)

MAX_REQUEST_BYTES = 8192
_READ_LINES = "nvp.screenplay.read_lines.v1"
_CONTEXT = "nvp.context.assemble.v1"
_RETAKE_PLAN = "nvp.film.plan_retake.v1"
_FEATURE_SOURCE = "nvp.film.resolve_published_sources.v1"
_SCENE_CREW = "nvp.film.read_scene_crew_context.v1"
_TOOL_PREFLIGHT = "nvp.tools.inspect_host_pinned.v1"
_IMPACT_PREVIEW = "nvp.film.preview_source_impact.v1"


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

    def __init__(self, studio: Studio, *, authorize_read: Callable,
                 feature_journal=None, trusted_tool_inventory=None):
        if not isinstance(studio, Studio) or not callable(authorize_read):
            raise TypeError("Studio and trusted read policy callback required")
        if feature_journal is not None:
            from backend.nvp_wo4_feature_journal import FeatureJournal
            if not isinstance(feature_journal, FeatureJournal):
                raise TypeError("Only a host-owned native FeatureJournal is allowed")
        if (trusted_tool_inventory is not None and
                not isinstance(trusted_tool_inventory, TrustedToolInventory)):
            raise TypeError("Native tool inventory must be host-built, not model JSON")
        self._studio = studio
        self._authorize_read = authorize_read
        self._feature_journal = feature_journal
        self._trusted_tool_inventory = trusted_tool_inventory

    def catalog(self) -> dict:
        # Public discovery grants nothing and cannot execute handlers.
        result = discover_capabilities()
        result["capabilities"].append(wo6_retake_descriptor())
        from copy import deepcopy
        result["capabilities"].append(deepcopy(SCENE_CREW_CAPABILITY))
        result["capabilities"].append(deepcopy(IMPACT_PREVIEW_CAPABILITY))
        if self._trusted_tool_inventory is not None:
            result["capabilities"].append({
                "id": _TOOL_PREFLIGHT,
                "description": "SHA and license file probe of host-pinned native "
                               "tool installations; never executes or installs tools",
                "effect": "read",
                "input_schema": {"project_id": "current host-authorized project"},
                "result_schema": TOOLS_FORMAT,
                "requires_host_authorization": True,
                "executable_by_model": False,
                "tool_execution_authorized": False,
            })
        if self._feature_journal is not None:
            from backend.nvp_wo6_feature_origins import CAPABILITY
            from copy import deepcopy
            result["capabilities"].append(deepcopy(CAPABILITY))
        return result

    def execute_read(self, scope: TrustedReadScope, request: dict) -> dict:
        if not isinstance(scope, TrustedReadScope):
            raise PermissionError("Trusted native scope required")
        raw = _canonical(request)
        capability = request.get("capability_id")
        allowed = {_READ_LINES, _CONTEXT, _RETAKE_PLAN, _SCENE_CREW,
                   _IMPACT_PREVIEW}
        if self._trusted_tool_inventory is not None:
            allowed.add(_TOOL_PREFLIGHT)
        if self._feature_journal is not None:
            allowed.add(_FEATURE_SOURCE)
        if type(capability) is not str or capability not in allowed:
            raise ValueError("Unknown or non-read capability")
        expected = {
            _READ_LINES: {"capability_id", "project_id", "source_revision",
                          "scene_id", "start_line", "end_line", "max_lines",
                          "require_current"},
            _CONTEXT: {"capability_id", "project_id", "source_revision",
                       "task", "scene_id", "max_lines"},
            _RETAKE_PLAN: {"capability_id", "project_id",
                           "object_id", "revision", "max_nodes"},
            _FEATURE_SOURCE: {"capability_id", "project_id", "feature_id"},
            _SCENE_CREW: {"capability_id", "project_id", "take_id",
                          "take_revision", "tick", "source_revision",
                          "screenplay_scene_id", "max_prims", "max_events",
                          "shot_sequence_id", "shot_sequence_revision"},
            _TOOL_PREFLIGHT: {"capability_id", "project_id"},
            _IMPACT_PREVIEW: {"capability_id", "project_id", "source_id",
                              "source_revision", "source_sha256",
                              "change_kind", "scene_id", "screenplay_revision",
                              "bible_fact_id", "expected_bible_digest",
                              "max_nodes", "delivery"},
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
        elif capability == _CONTEXT:
            result = assemble_task_context(
                self._studio, scope.project_id, request["source_revision"],
                request["task"], scene_id=request.get("scene_id"),
                max_lines=request.get("max_lines", 120),
            )
        elif capability == _RETAKE_PLAN:
            # Same trusted per-turn read-policy callback and exact-project
            # scope as existing screenplay/crew context: NOT a new model
            # tool executor or independent permission authority.
            result = plan_source_retake(
                FilmIndex(self._studio), scope.project_id,
                request["object_id"], request["revision"],
                max_nodes=request.get("max_nodes", 64),
            )
        elif capability == _SCENE_CREW:
            result = assemble_film_crew_context(
                FilmIndex(self._studio), scope.project_id,
                request["take_id"], request["take_revision"], request["tick"],
                source_revision=request.get("source_revision"),
                screenplay_scene_id=request.get("screenplay_scene_id"),
                shot_sequence_id=request.get("shot_sequence_id"),
                shot_sequence_revision=request.get("shot_sequence_revision"),
                max_prims=request.get("max_prims", 32),
                max_events=request.get("max_events", 24),
            )
            if self._trusted_tool_inventory is not None:
                result["native_tool_readiness"] = preflight_tool_inventory(
                    self._trusted_tool_inventory)
            else:
                result["native_tool_readiness"] = {
                    "status": "HOST_HAS_NOT_PINNED_NATIVE_TOOL_INSTALLATIONS",
                    "tools": [], "tool_execution_authorized": False,
                    "missing_tools_assumed_available": False,
                }
        elif capability == _TOOL_PREFLIGHT:
            result = preflight_tool_inventory(self._trusted_tool_inventory)
        elif capability == _IMPACT_PREVIEW:
            # Read-only, digest bound and scoped like all existing internal
            # AI reads. The returned approval checklist is descriptive; it
            # cannot approve or start any native operation.
            result = preview_source_impact(
                FilmIndex(self._studio), scope.project_id,
                request["source_id"], request["source_revision"],
                request["source_sha256"], request["change_kind"],
                scene_id=request.get("scene_id"),
                screenplay_revision=request.get("screenplay_revision"),
                bible_fact_id=request.get("bible_fact_id"),
                expected_bible_digest=request.get("expected_bible_digest"),
                max_nodes=request.get("max_nodes", 32),
                delivery=request.get("delivery"),
            )
        else:
            # Heavy source/essence re-verification is available only when a
            # trusted native host injected the real durable FeatureJournal.
            # Merely guessing a feature ID or discovering this read method
            # grants no rights. The same per-call policy callback runs.
            from backend.nvp_wo6_feature_origins import (
                resolve_published_feature_origins)
            result = resolve_published_feature_origins(
                FilmIndex(self._studio), self._feature_journal,
                scope.project_id, request["feature_id"],
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
