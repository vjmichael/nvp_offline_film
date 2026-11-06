"""NVP-AI-02: typed read-only capability catalog and bounded context assembler.

This is an internal trusted-host service, NOT a model-exposed endpoint.
An authenticated caller must authorize project access before invoking it.
No write/approval/worker execution capability is exported.
"""
from __future__ import annotations

from hashlib import sha256

from backend.nvp_ai_refs import MAX_READ_LINES, read_screenplay_lines
from backend.nvp_studio import Studio, parse_screenplay

TASKS = ("screenplay_review", "scene_coverage", "shot_review")
CAPABILITIES = (
    {
        "id": "nvp.screenplay.read_lines.v1",
        "description": "Read numbered, revision-bound screenplay text",
        "effect": "read",
        "input_schema": {
            "project_id": "nonempty string",
            "source_revision": "nonnegative integer",
            "scene_id": "optional string",
            "start_line": "optional positive integer",
            "end_line": "optional positive integer",
            "max_lines": "integer from 1 to 120",
        },
        "result_schema": "nvp.ai.screenplay_source_ref.v1",
        "requires_host_authorization": True,
        "executable_by_model": False,
    },
    {
        "id": "nvp.context.assemble.v1",
        "description": "Assemble bounded task-specific screenplay and shot context",
        "effect": "read",
        "input_schema": {
            "project_id": "nonempty string",
            "source_revision": "nonnegative integer",
            "task": "screenplay_review | scene_coverage | shot_review",
            "scene_id": "required for scene_coverage or shot_review",
            "max_lines": "integer from 1 to 120",
        },
        "result_schema": "nvp.ai.task_context.v1",
        "requires_host_authorization": True,
        "executable_by_model": False,
    },
)


def discover_capabilities() -> dict:
    """Return stable descriptors, not permission grants or callable handlers."""
    return {
        "format": "nvp.ai.capabilities.v1",
        "capabilities": [dict(c) for c in CAPABILITIES],
        "execution_authority": "trusted_nvp_host_only",
        "authorization_provided": False,
    }


def assemble_task_context(
    studio: Studio, project_id: str, source_revision: int, task: str, *,
    scene_id: str | None = None, max_lines: int = MAX_READ_LINES,
) -> dict:
    """Construct a bounded packet for one AI planning task.

    Every packet pins screenplay revision and hash; the source reader rejects
    stale revisions to prevent accidental planning against a changed script.
    The project and shots are read from existing Studio storage only.
    """
    if not isinstance(studio, Studio):
        raise TypeError("Trusted Studio instance required")
    if task not in TASKS:
        raise ValueError("Unsupported AI task")
    if type(source_revision) is not int or source_revision < 0:
        raise ValueError("Exact nonnegative screenplay revision required")
    if type(max_lines) is not int or not 1 <= max_lines <= MAX_READ_LINES:
        raise ValueError("max_lines must be between 1 and 120")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("Nonempty project ID required")
    if task != "screenplay_review" and (not isinstance(scene_id, str) or not scene_id):
        raise ValueError("This task requires a selected scene")
    if scene_id is not None and (not isinstance(scene_id, str) or not scene_id):
        raise ValueError("Invalid scene ID")

    # Pin revision immediately. The reader rechecks it when fetching source.
    with studio._connection() as db:
        row = db.execute(
            "SELECT title,revision,screenplay FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Film project not found")
        if row["revision"] != source_revision:
            raise RuntimeError("Screenplay changed; refresh context before proceeding")
        script = row["screenplay"]
        scenes = parse_screenplay(script)
        selected = next((s for s in scenes if s["id"] == scene_id), None)
        if scene_id is not None and selected is None:
            raise KeyError("Scene not present in exact screenplay revision")
        shots = []
        if selected is not None:
            shot_rows = db.execute(
                "SELECT shot_id,framing,subject,intent,notes,status FROM shots "
                "WHERE project_id=? AND scene_id=? ORDER BY shot_id LIMIT 100",
                (project_id, scene_id),
            ).fetchall()
            shots = [dict(s) for s in shot_rows]

    reference = read_screenplay_lines(
        studio, project_id, source_revision, scene_id=scene_id,
        max_lines=max_lines, require_current=True,
    )
    expected_hash = sha256(script.encode("utf-8")).hexdigest()
    if reference["source_sha256"] != expected_hash:
        raise RuntimeError("Screenplay changed while assembling AI context")
    if reference["current_revision_observed"] != source_revision:
        raise RuntimeError("Screenplay revision changed during context assembly")

    # Review tasks receive navigation metadata, not the rest of the raw script.
    manifest = [
        {"scene_id": s["id"], "heading": s["heading"],
         "start_line": s["start_line"], "end_line": s["end_line"]}
        for s in scenes[:300]
    ]
    return {
        "format": "nvp.ai.task_context.v1",
        "task": task,
        "project": {"id": project_id, "title": row["title"]},
        "source_revision": source_revision,
        "source_sha256": expected_hash,
        "source": reference,
        "scene_manifest": manifest,
        "scene_manifest_truncated": len(scenes) > 300,
        "selected_scene": (
            {"id": selected["id"], "heading": selected["heading"],
             "characters": selected["characters"],
             "start_line": selected["start_line"], "end_line": selected["end_line"]}
            if selected else None
        ),
        "shots": shots if task == "shot_review" else [],
        "shots_truncated": task == "shot_review" and len(shots) == 100,
        "approval_status": "not_inferred",
        "proposal_only": True,
        "authorization_provided": False,
        "side_effects_performed": False,
    }
