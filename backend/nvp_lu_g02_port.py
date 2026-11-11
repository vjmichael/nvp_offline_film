"""G02: Lu host-owned model readiness and proposal-only NVP inference boundary.

NOT a Lu desktop transport, model server, installer, nor authority issuer.
Every operation delegates scope verification to an independently trusted Lu
host. The contract tests use fake host callbacks; they are not proof that
installed Lu exposes an external NVP workspace/inference API.
No network, sockets, model loading, process execution or filesystem here.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Protocol, Any

from backend.nvp_lu_alpha_contract import LuRuntimeView
from backend.nvp_lu_workspace import LuHostError
from backend.nvp_creative_schema import STAGES, MAX_NOTES

MODULE = "nvp.film"
OPAQUE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")
HEX_EPOCH = re.compile(r"^[a-f0-9]{32}$")
MAX_GENERATED = 120_000
MAX_REQUEST = 32_000
MAX_CHUNK = 4_096
MAX_EVENTS = 8_192
MAX_OUTPUT_TOKENS = 2_800
OPS = frozenset({"status", "read", "generate", "receipt", "save", "cancel"})


class NativeLuHostPort(Protocol):
    """Trusted Lu host only, never an arbitrary model/WebView implementation.

    verify_scope checks an opaque active workspace instance, user session,
    project and epoch against Lu host records on every call. Only the host
    may journal complete generation receipts or save revisioned proposals.
    """
    def verify_scope(self, scope: object, operation: str) -> dict[str, Any]: ...
    def read_runtime(self, scope: object) -> dict[str, Any]: ...
    def catalog_count(self, scope: object) -> int: ...
    def read_project(self, scope: object) -> dict[str, Any]: ...
    def generate_events(self, scope: object, system: str, user: str,
                        max_new_tokens: int): ...
    def record_generation(self, scope: object, receipt: dict[str, Any]) -> dict[str, Any]: ...
    def save_proposal(self, scope: object, *, stage: str, content: str,
                      instructions: str, expected_revision: int) -> dict[str, Any]:
        """Host atomically consumes the matching journaled complete generation
        and saves proposal-only content under source-revision CAS. It must
        reject direct, stale, different-project and duplicate receipt writes.
        Returns consumed_proposal_sha256 and source_mutated=False.
        """
    def cancel_active(self, scope: object) -> bool: ...


class LuG02FilmPort:
    """Trusted adapter for NvpLuWorkspace; model status is observational."""

    def __init__(self, trusted_host: NativeLuHostPort):
        if trusted_host is None or any(
            not callable(getattr(trusted_host, name, None)) for name in (
                "verify_scope", "read_runtime", "catalog_count", "read_project",
                "generate_events", "record_generation", "save_proposal",
                "cancel_active")):
            raise TypeError("A complete trusted Lu host API is required")
        self._host = trusted_host

    def _scope(self, scope: object, operation: str):
        if scope is None or operation not in OPS:
            raise LuHostError("Lu workspace authority unavailable")
        claim = self._host.verify_scope(scope, operation)
        if (type(claim) is not dict or set(claim) != {
                "module", "workspace", "project", "epoch", "state"} or
                claim["module"] != MODULE or claim["state"] != "active" or
                not isinstance(claim["workspace"], str) or
                not OPAQUE.fullmatch(claim["workspace"]) or
                not isinstance(claim["project"], str) or
                not OPAQUE.fullmatch(claim["project"]) or
                not isinstance(claim["epoch"], str) or
                not HEX_EPOCH.fullmatch(claim["epoch"])):
            raise LuHostError("Lu host returned no valid active film workspace")
        return claim

    def status(self, scope: object):
        """Conservative human status; it is NOT model-weights or VRAM proof."""
        self._scope(scope, "status")
        try:
            runtime = LuRuntimeView.from_trusted_host(self._host.read_runtime(scope))
            available = self._host.catalog_count(scope)
            if type(available) is not int or available < 0 or available > 100_000:
                raise ValueError("Untrusted Lu catalog observation")
            self._scope(scope, "status")
        except TimeoutError:
            return self._state("timed_out", "AI status timed out. Retry.")
        except (ConnectionError, OSError):
            return self._state("disconnected", "Lu is not connected.")
        except ValueError:
            return self._state("unavailable", "AI status could not be verified.")
        phases = {
            "Idle": ("available_unloaded" if available else "no_model"),
            "Loading": "loading",
            "Ready": "ready",
            "Generating": "busy",
            "Unloading": "unloading",
            "Failed": "failed",
        }
        state = phases[runtime.phase]
        if runtime.phase in ("Ready", "Generating") and not runtime.session_id:
            return self._state("unavailable", "AI session could not be verified.")
        messages = {
            "no_model": "No local AI model is available.",
            "available_unloaded": "A local model is available but not loaded.",
            "loading": "AI model is loading.",
            "ready": "AI is ready to help.",
            "busy": "AI is working.",
            "unloading": "AI model is unloading.",
            "failed": "AI could not start. Retry from Lu.",
        }
        return self._state(state, messages[state],
                           runtime.model_ref if state in {"ready", "busy"} else None)

    @staticmethod
    def _state(state, message, ref=None):
        return {"state": state, "message": message, "model_ref": ref,
                "host_reported_only": True,
                "weights_verified_here": False,
                "vram_verified_here": False,
                "inference_authorized_by_status": False}

    def read_project(self, scope: object):
        binding = self._scope(scope, "read")
        project = self._host.read_project(scope)
        self._scope(scope, "read")
        if (type(project) is not dict or project.get("id") != binding["project"] or
                type(project.get("revision")) is not int or project["revision"] < 0):
            raise LuHostError("Lu did not return an authorized project snapshot")
        return project

    def generate_story(self, scope: object, system: str, user: str,
                       *, max_new_tokens: int):
        original = self._scope(scope, "generate")
        if (type(system) is not str or not system or len(system) > MAX_REQUEST or
                type(user) is not str or not user or len(user) > MAX_REQUEST or
                type(max_new_tokens) is not int or
                not 1 <= max_new_tokens <= MAX_OUTPUT_TOKENS):
            raise ValueError("Unbounded or invalid Lu film inference request")
        state = self.status(scope)
        if state["state"] != "ready":
            raise LuHostError("Lu shared AI is not ready: " + state["state"])
        runtime = LuRuntimeView.from_trusted_host(self._host.read_runtime(scope))
        if runtime.model_ref != state["model_ref"] or not runtime.session_id:
            raise LuHostError("Loaded Lu model changed before inference")
        request_sha = sha256((system + "\x00" + user).encode("utf8")).hexdigest()
        output = []
        size = 0
        generation = None
        next_sequence = 1
        finished = False
        for event in self._host.generate_events(scope, system, user, max_new_tokens):
            current = self._scope(scope, "generate")
            if current != original:
                raise LuHostError("Workspace changed during Lu inference")
            core = {"v", "workspace", "project", "epoch", "modelRef",
                    "sessionId", "generationId", "sequence", "kind"}
            if (type(event) is not dict or not core <= set(event) or
                    event["v"] != 1 or event["workspace"] != original["workspace"] or
                    event["project"] != original["project"] or
                    event["epoch"] != original["epoch"] or
                    event["modelRef"] != runtime.model_ref or
                    event["sessionId"] != runtime.session_id or
                    type(event["sequence"]) is not int or
                    event["sequence"] != next_sequence or
                    type(event["generationId"]) is not str or
                    not OPAQUE.fullmatch(event["generationId"]) or
                    event["kind"] not in {"chunk", "finished", "failure"} or finished):
                raise LuHostError("Invalid or unbound Lu inference event")
            if generation is None:
                generation = event["generationId"]
            elif event["generationId"] != generation:
                raise LuHostError("Lu generation changed mid-stream")
            next_sequence += 1
            if next_sequence > MAX_EVENTS:
                raise LuHostError("Lu event stream exceeds limit")
            kind = event["kind"]
            fields = set(event)
            if kind == "chunk":
                chunk = event.get("text")
                if (fields != core | {"text"} or type(chunk) is not str or
                        not chunk or len(chunk) > MAX_CHUNK or
                        any(ord(x) < 32 and x not in "\n\t\r" for x in chunk)):
                    raise LuHostError("Lu returned an invalid text chunk")
                size += len(chunk)
                if size > MAX_GENERATED:
                    raise LuHostError("Lu text exceeds film proposal limit")
                output.append(chunk)
            elif kind == "failure":
                if fields != core | {"code"} or event["code"] not in {
                        "timed_out", "cancelled", "backend_failed",
                        "model_unavailable", "revoked"}:
                    raise LuHostError("Lu returned an invalid failure category")
                raise LuHostError("Lu inference " + event["code"])
            else:
                if fields != core | {"cancelled"} or type(event["cancelled"]) is not bool:
                    raise LuHostError("Missing Lu terminal completion witness")
                if event["cancelled"]:
                    raise LuHostError("Lu inference cancelled before completion")
                finished = True
        if not finished or not output or not "".join(output).strip():
            raise LuHostError("Lu inference ended without verified text completion")
        self._scope(scope, "receipt")
        generated = "".join(output)
        normalized_proposal = generated.strip()
        receipt = {
            "format": "nvp.g02.lu_completed_proposal.v1",
            "workspace": original["workspace"],
            "project": original["project"],
            "epoch": original["epoch"],
            "modelRef": runtime.model_ref,
            "sessionId": runtime.session_id,
            "generationId": generation,
            "request_sha256": request_sha,
            "generated_sha256": sha256(generated.encode("utf8")).hexdigest(),
            "proposal_sha256": sha256(normalized_proposal.encode("utf8")).hexdigest(),
            "output_characters": len(generated),
            "host_reported_finished": True,
            "model_weights_verified_here": False,
            "gpu_offload_verified_here": False,
            "source_mutation_authorized": False,
            "tool_execution_authorized": False,
        }
        saved = self._host.record_generation(scope, receipt)
        self._scope(scope, "receipt")
        if (type(saved) is not dict or saved.get("status") != "recorded" or
                saved.get("request_sha256") != request_sha or
                saved.get("generated_sha256") != receipt["generated_sha256"] or
                saved.get("proposal_sha256") != receipt["proposal_sha256"]):
            raise LuHostError("Lu did not durably journal the completed generation")
        return generated

    def save_proposal(self, scope: object, *, stage: str, content: str,
                      instructions: str, expected_revision: int):
        before = self._scope(scope, "save")
        if (type(expected_revision) is not int or expected_revision < 0 or
                type(content) is not str or not content or
                len(content) > MAX_GENERATED or
                stage not in STAGES or
                type(instructions) is not str or len(instructions) > MAX_NOTES):
            raise ValueError("Invalid proposed film draft")
        generated_sha = sha256(content.encode("utf8")).hexdigest()
        result = self._host.save_proposal(
            scope, stage=stage, content=content, instructions=instructions,
            expected_revision=expected_revision)
        after = self._scope(scope, "save")
        if (before != after or type(result) is not dict or
                result.get("status") != "proposed" or
                result.get("consumed_proposal_sha256") != generated_sha or
                result.get("source_mutated") is not False):
            raise LuHostError("Lu did not atomically consume the exact completed-generation receipt")
        return result

    def cancel(self, scope: object):
        before = self._scope(scope, "cancel")
        accepted = self._host.cancel_active(scope)
        after = self._scope(scope, "cancel")
        if before != after or type(accepted) is not bool or not accepted:
            raise LuHostError("Lu did not accept the cancellation request")
        return {"state": "cancellation_requested", "terminal_verified": False,
                "model_unloaded": False}
