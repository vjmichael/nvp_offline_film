"""NVP-AI-01: revision-bound, read-only screenplay reference adapter.

Not a tool executor, AI permission broker, or source-of-canon approval.
Uses Studio's existing project and screenplay_revisions tables. Does not
create new tables, parse natural-language authority, or mutate a film.
"""
from __future__ import annotations

from hashlib import sha256

from backend.nvp_studio import Studio, parse_screenplay

MAX_READ_LINES = 120


def read_screenplay_lines(
    studio: Studio, project_id: str, source_revision: int, *,
    scene_id: str | None = None, start_line: int | None = None,
    end_line: int | None = None, max_lines: int = MAX_READ_LINES,
    require_current: bool = False,
) -> dict:
    """Return exact original lines (inclusive), with stable revision metadata.

    Global 1-based line numbers include blank and trailing lines. Explicit
    source_revision prevents accidental edits to whichever version happens to
    be current. Only an authorized/trusted caller should expose this over IPC.

    Bounded pages return next_line when more text remains. A caller cannot
    infer omitted content or creator approvals from this response.
    """
    if not isinstance(studio, Studio):
        raise TypeError("An existing trusted Studio instance is required")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("A nonempty project ID is required")
    if type(source_revision) is not int or source_revision < 0:
        raise ValueError("A nonnegative exact screenplay revision is required")
    if type(require_current) is not bool:
        raise ValueError("require_current must be boolean")
    if type(max_lines) is not int or not 1 <= max_lines <= MAX_READ_LINES:
        raise ValueError("Requested line page size must be between 1 and 120")
    for label, value in (("start_line", start_line), ("end_line", end_line)):
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError(label + " must be a 1-based positive integer")
    if scene_id is not None and (not isinstance(scene_id, str) or not scene_id):
        raise ValueError("Selected scene identity is invalid")

    # Read only within the existing project and history tables; this method
    # deliberately performs zero INSERT/UPDATE/DELETE/worker operations.
    with studio._connection() as db:
        current = db.execute(
            "SELECT revision, screenplay FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if current is None:
            raise KeyError("Film project not found")
        current_revision = current["revision"]
        if require_current and source_revision != current_revision:
            raise RuntimeError("Source revision is stale; refresh before preparing an edit")
        if source_revision == current_revision:
            script = current["screenplay"]
        else:
            historical = db.execute(
                "SELECT screenplay FROM screenplay_revisions "
                "WHERE project_id=? AND revision=?", (project_id, source_revision)
            ).fetchone()
            if historical is None:
                raise KeyError("Requested exact source revision not found")
            script = historical["screenplay"]

    original_sha = sha256(script.encode("utf-8")).hexdigest()
    lines = script.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    available_start, available_end = 1, len(lines)
    selected = None
    if scene_id is not None:
        selected = next((scene for scene in parse_screenplay(script)
                         if scene["id"] == scene_id), None)
        if selected is None:
            raise KeyError("Selected scene is not present in that source revision")
        available_start, available_end = selected["start_line"], selected["end_line"]
    first = start_line if start_line is not None else available_start
    last = end_line if end_line is not None else available_end
    if first < available_start or first > available_end or last < first or last > available_end:
        raise ValueError("Requested lines must be inside the exact source or selected scene")
    included_end = min(last, first + max_lines - 1)
    records = [{"line": index, "text": lines[index - 1]}
               for index in range(first, included_end + 1)]
    width = max(2, len(str(len(lines))))
    excerpt = "\n".join(
        f"L{item['line']:0{width}d} | {item['text']}" for item in records
    )
    return {
        "format": "nvp.ai.screenplay_source_ref.v1",
        "project_id": project_id,
        "source_revision": source_revision,
        "source_sha256": original_sha,
        "current_revision_observed": current_revision,
        "current_at_read": source_revision == current_revision,
        "scene_id": scene_id,
        "scene_heading": selected["heading"] if selected is not None else None,
        "source_line_count": len(lines),
        "requested_start_line": first,
        "requested_end_line": last,
        "returned_start_line": first,
        "returned_end_line": included_end,
        "next_line": included_end + 1 if included_end < last else None,
        "lines_omitted": max(0, last - included_end),
        "lines": records,
        "numbered_excerpt": excerpt,
        "approval_status": "not_asserted_by_this_read_adapter",
        "side_effects_performed": False,
    }
