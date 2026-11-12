"""Development-only NVP film prompt port, not the native Lu Protobuf client.

The real Lu-owned core bridge is in vjmichael/jan_alt:
src-tauri/lu-core/src/nvp_film_bridge.rs. This Python port remains a test
harness to evaluate film-writing prompt/revision behavior while the Tauri
Workspace UI/transport is under development. No consumer NVP server ships.

NVP's first Lu Workspace port: film logic without a second model runtime.

The Lu host must supply a real, host-issued opaque scope and an implementation
of LuFilmHostPort; this module is neither a DLC installer nor a credential
issuer. It deliberately does not import network, filesystem or model loaders.

No NVP process can authorize itself by constructing a scope. The production Lu
adapter is responsible for validating user/instance/task identity on *every*
port operation, typed Protobuf codec, permissions and worker/effect journal.
"""
from __future__ import annotations

from typing import Any, Protocol

from backend.nvp_studio import parse_screenplay, SCENE_HEADING
from backend.nvp_creative_schema import STAGES, MAX_DRAFT, MAX_NOTES

MAX_CONTEXT_CHARS = 1_000_000
MAX_OUTPUT_TOKENS = 2_800


class LuHostError(Exception):
    """Host refusal / unavailable authenticated Lu workspace service."""


class LuFilmHostPort(Protocol):
    """Trusted Lu broker, not a model- or WebView-implemented service.

    All calls accept the host-issued scope only as an opaque value. The port
    validates it against current trusted instance/profile/task records.
    It MUST NOT trust project IDs or authority fields supplied by NVP.
    """

    def read_project(self, scope: object) -> dict[str, Any]:
        """Host-authorized read from project storage chosen by Lu."""

    def generate_story(self, scope: object, system: str, user: str,
                       *, max_new_tokens: int) -> str:
        """Inference through Lu's already-loaded model, scoped and cancellable."""

    def save_proposal(self, scope: object, *, stage: str, content: str,
                      instructions: str, expected_revision: int) -> dict[str, Any]:
        """Host-journaled creation of a *proposed* film draft only."""


def _check_stage(stage: str, instructions: str) -> None:
    if stage not in STAGES:
        raise ValueError("Unknown NVP creative-writing stage")
    if not isinstance(instructions, str) or len(instructions) > MAX_NOTES:
        raise ValueError("Creative guidance must be text under 5000 characters")


def build_writer_messages(project: dict[str, Any], stage: str,
                          instructions: str = "", scene_id: str | None = None) -> tuple[str, str]:
    """Film-specific creative prompt; no host permissions or model paths."""
    _check_stage(stage, instructions)
    title = project.get("title")
    idea = project.get("idea")
    screenplay = project.get("screenplay")
    scenes = project.get("scenes")
    revision = project.get("revision")
    if (not isinstance(title, str) or not isinstance(idea, str)
            or not isinstance(screenplay, str) or not isinstance(scenes, list)
            or not isinstance(revision, int) or isinstance(revision, bool)
            or revision < 0 or len(screenplay) > MAX_CONTEXT_CHARS):
        raise ValueError("Lu provided invalid or unbounded film project data")
    if scene_id is not None:
        if not isinstance(scene_id, str) or len(scene_id) > 128 or not scene_id:
            raise ValueError("Invalid scene reference")
        scene = next((s for s in scenes if isinstance(s, dict) and s.get("id") == scene_id), None)
        if scene is None:
            raise KeyError("Selected scene not found in authorized project")
        heading, excerpt = scene.get("heading"), scene.get("text")
        if not isinstance(heading, str) or not isinstance(excerpt, str):
            raise ValueError("Invalid authorized scene text")
        context = f"Selected scene ({heading[:200]}):\n{excerpt[:12000]}"
    elif len(screenplay) > 16000:
        context = ("Screenplay excerpt only; full script is longer than this local writing request. "
                   "Do not pretend to have read the whole script.\n" + screenplay[:16000])
    else:
        context = screenplay or "No screenplay yet"
    system = ("You are NVP's collaborative screenplay-development assistant, hosted by Lu. "
              "The creator decides the story. Preserve established characters and known plot facts. "
              "Offer filmable action, natural dramatic dialogue and continuity-aware proposals. "
              "For screenplay output use Fountain-style INT./EXT. headings, action and character cues. "
              "Never claim that video was generated, a file was written, or a tool ran. "
              "Output the draft only; no markdown fences.")
    user = (f"Movie: {title[:150]}\nOriginal creator idea: {idea[:10000]}\n"
            f"Writing stage: {stage}\nCreator's instructions: {instructions or 'Preserve creator intent'}\n"
            f"Existing script/context:\n{context}\n"
            "Write a focused proposal for creator review; do not silently approve it.")
    return system, user


def validate_draft(stage: str, content: str) -> str:
    if not isinstance(content, str) or not content.strip() or len(content) > MAX_DRAFT:
        raise ValueError("Lu's writing result must be nonempty text under 120000 characters")
    if stage == "screenplay":
        if not any(SCENE_HEADING.fullmatch(line.strip()) for line in content.splitlines()):
            raise ValueError("Screenplay proposal requires an INT./EXT. scene heading")
        parse_screenplay(content)
    return content.strip()


class NvpLuWorkspace:
    """No direct network, model-loader, credential, filesystem or tool dispatch.

    The scope is obtained from a trusted Lu caller and remains opaque to NVP.
    Calling this constructor does not grant a new workspace or any permissions.
    """

    def __init__(self, host: LuFilmHostPort, *,
                 require_completed_receipt: bool = False):
        self._host = host
        # The original development-only port has older simulated proposal
        # receipts. The production Film Home MUST explicitly require Lu's
        # consumed, completed generation witness. Never silently up-convert
        # a development stub to source authority.
        self._require_completed_receipt = require_completed_receipt

    def propose(self, scope: object, *, stage: str, instructions: str = "",
                scene_id: str | None = None) -> dict[str, Any]:
        _check_stage(stage, instructions)
        # Host validates active Workspace, ownership, read access and the
        # current task before returning any private film data.
        project = self._host.read_project(scope)
        system, user = build_writer_messages(project, stage, instructions, scene_id)
        # This call rechecks host scope and uses Lu's loaded model. NVP has
        # neither a model ID to load nor a URL to call.
        content = self._host.generate_story(
            scope, system, user, max_new_tokens=MAX_OUTPUT_TOKENS)
        content = validate_draft(stage, content)
        # The host must validate scope + revision again, journal the effect,
        # and store only a proposal. A model cannot auto-accept screenplay.
        result = self._host.save_proposal(
            scope, stage=stage, content=content,
            instructions=instructions, expected_revision=project["revision"])
        if not isinstance(result,dict) or result.get("status")!="proposed":
            raise LuHostError("Host did not acknowledge a proposed draft")
        if not self._require_completed_receipt:
            return result  # Development-only legacy harness; no native grant.
        from hashlib import sha256
        expected_sha=sha256(content.encode("utf8")).hexdigest()
        if (result.get("source_mutated") is not False or
                result.get("consumed_proposal_sha256")!=expected_sha or
                (result.get("content") is not None and
                 result["content"]!=content)):
            raise LuHostError("Host did not consume this exact completed proposal")
        # Lu need not echo potentially private film text; NVP uses only the
        # verified generated content already matched to the Lu host's consumed
        # SHA. The director has not approved it as screenplay or source.
        return {**result,"content":content}
