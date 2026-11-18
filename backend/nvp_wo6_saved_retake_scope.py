"""WO6-B source-bound native admission preparation.

A saved planning decision is NOT a worker grant. This module is private
host-side validation only; it does not launch a worker or mutate a film.
The initial operation is an exact-source new frozen Take, not interpretation
of the creative intention or an automatically applied scene/edit change.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_openusd_take import OpenUSDTakeCapture, MAX_CHECKPOINTS
from backend.nvp_wo6_creator_planning_desktop import (
    RECEIPT, ROLES, digest, preview_source_impact,
)

FORMAT = "nvp.wo6.saved_retake_scope.v1"
OPERATION = "nvp.film.create_frozen_take.v1"


def _current(index, pid, oid, revision, expected_sha, kind):
    row = index.read_revision(pid, oid, revision)
    if row["kind"] != kind or row["document_sha256"] != expected_sha:
        raise PermissionError("Exact original source identity does not match")
    if not any(r["object_id"] == oid and r["head_revision"] == revision
               for r in index.list_objects(pid, kind=kind)):
        raise PermissionError("Original source is retired or superseded")
    return row


def prepare_saved_retake(index, *, project_id, plan_id, plan_sha256,
                         new_take_id):
    """Reopen exact saved plan AND real OpenUSD Take before any worker grant.

    The host must separately authorize this entire returned scope, including the
    new identity, and recompute it before admission. No boolean in the receipt
    constitutes native execution authority. Scope is intentionally restricted
    to an existing frozen Take and its unchanged scene/timeline/checkpoints.
    """
    if not isinstance(index, FilmIndex):
        raise TypeError("Trusted FilmIndex required")
    pid = _require_pid(project_id)
    oid = _id(plan_id, "saved plan")
    output = _id(new_take_id, "new Take")
    row = _current(index, pid, oid, 1, _sha(plan_sha256), "presentation")
    data = row["data"]
    if (data.get("format") != RECEIPT or
        data.get("creator_confirmed_planning_only") is not True or
        any(data.get(k) is not False for k in
            ("worker_authorized", "worker_executed", "film_approved"))):
        raise PermissionError("Not a planning-only creator receipt")
    plan = data["plan"]
    proposal = plan["request"]
    if (plan["project_id"] != pid or proposal["project_id"] != pid or
        proposal["change_kind"] != "retake" or
        plan["source"]["kind"] != "take"):
        raise PermissionError("Only exact saved frozen-Take retake plans supported")
    fresh = preview_source_impact(index, proposal)
    if fresh != plan or not fresh["planning_approval_available"]:
        raise PermissionError("Saved creative plan is stale or incomplete")
    source = plan["source"]
    original = _current(index, pid, source["object_id"], source["revision"],
                        source["document_sha256"], "take")
    if original["revision"] != 1 or row["dependencies"] != [{
        "object_id": original["object_id"], "revision": 1,
        "role": ROLES["take"]}]:
        raise PermissionError("Saved plan is not bound to exact immutable Take")
    manifest = original["data"]
    scene = _current(index, pid, manifest["scene_id"],
                     manifest["scene_revision"], manifest["scene_document_sha256"], "scene")
    timeline = _current(index, pid, manifest["timeline_id"],
                        manifest["timeline_revision"], manifest["timeline_document_sha256"], "temporal")
    if output in {oid, original["object_id"], scene["object_id"], timeline["object_id"]}:
        raise PermissionError("New Take must have a distinct unused identity")
    try:
        index.read_revision(pid, output)
    except KeyError:
        pass
    else:
        raise PermissionError("Take identity already exists; never overwrite")
    ticks = manifest["sample_ticks"]
    duration = timeline["data"]["duration_tick"]
    if (type(ticks) is not list or not 1 <= len(ticks) <= MAX_CHECKPOINTS or
        any(type(t) is not int or not 0 <= t < duration for t in ticks) or
        ticks != sorted(set(ticks))):
        raise PermissionError("Invalid immutable Film Time checkpoints")
    evidence = OpenUSDTakeCapture(index, verify_creator_action=lambda *_: False).verify_take(
        pid, original["object_id"])
    if (evidence["status"] != "VERIFIED_FROZEN_DATA_TAKE" or
        evidence["take_document_sha256"] != source["document_sha256"] or
        evidence["scene_document_sha256"] != scene["document_sha256"] or
        evidence["timeline_document_sha256"] != timeline["document_sha256"] or
        evidence["checkpoint_count"] != len(ticks)):
        raise PermissionError("Native Take re-open did not verify exact source")
    # Recheck after expensive native reopen; later admission must repeat this.
    _current(index, pid, oid, 1, plan_sha256, "presentation")
    _current(index, pid, scene["object_id"], scene["revision"],
             scene["document_sha256"], "scene")
    _current(index, pid, timeline["object_id"], timeline["revision"],
             timeline["document_sha256"], "temporal")
    if preview_source_impact(index, proposal) != fresh:
        raise PermissionError("Creative plan changed during native reopening")
    scope = {
        "format": FORMAT, "operation": OPERATION, "project_id": pid,
        "plan_id": oid, "plan_document_sha256": plan_sha256,
        "preview_sha256": fresh["preview_sha256"],
        "original_take_id": original["object_id"],
        "original_take_sha256": source["document_sha256"],
        "new_take_id": output, "sample_ticks": list(ticks),
        "scene_id": scene["object_id"], "scene_revision": scene["revision"],
        "scene_sha256": scene["document_sha256"],
        "timeline_id": timeline["object_id"], "timeline_revision": timeline["revision"],
        "timeline_sha256": timeline["document_sha256"],
        "story_context": fresh["story_context"],
        "native_take_reopened": True, "worker_authorized": False,
        "worker_executed": False, "film_approved": False,
    }
    scope["scope_sha256"] = digest(scope)
    return scope



def check_saved_retake_current(index, scope):
    """Read-only guard for the FilmIndex write transaction before publication."""
    pid=scope["project_id"]
    row=_current(index,pid,scope["plan_id"],1,scope["plan_document_sha256"],"presentation")
    plan=row["data"]["plan"]
    _current(index,pid,scope["original_take_id"],1,scope["original_take_sha256"],"take")
    _current(index,pid,scope["scene_id"],scope["scene_revision"],scope["scene_sha256"],"scene")
    _current(index,pid,scope["timeline_id"],scope["timeline_revision"],scope["timeline_sha256"],"temporal")
    if (preview_source_impact(index,plan["request"])!=plan or
        plan["preview_sha256"]!=scope["preview_sha256"] or
        plan["story_context"]!=scope["story_context"]):
        raise PermissionError("Saved creative plan changed before publication")
    try:
        index.read_revision(pid,scope["new_take_id"])
    except KeyError:
        return
    raise PermissionError("New Take identity already committed")
