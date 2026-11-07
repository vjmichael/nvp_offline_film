"""WO6-01: read-only, source-bound film/retake planning for NVP's AI crew.

This adds NO model executor, HTTP write route, free-form shell, approval
authority, or second persistence database. An authenticated host can use
FilmIndex's existing immutable revision edges to tell a filmmaker exactly
which sources are known, which may be missing, and what a retake would
affect BEFORE proposing an actual native edit.

A theatrical DCP's flattened picture/sound cannot reconstruct a USD scene.
Source navigation is only claimed where real project FilmIndex records
link exact Digital Take -> scene/temporal revisions. Unindexed FeatureJournal
reel jobs may require a separate resolver; absence in FilmIndex is not
proof that source custody was lost.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from hashlib import sha256
import json

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_take import FORMAT as USD_TAKE_FORMAT

FORMAT = "nvp.wo6.source_bound_creator_retake_preview.v1"
MAX_GRAPH_NODES = 64
MAX_DIRECT_DEPENDENTS = 64
PLAN_CAPABILITY = {
    "id": "nvp.film.plan_retake.v1",
    "description": (
        "Read the exact FilmIndex presentation/Take source graph, identify "
        "available OpenUSD source revisions and summarize bounded indexed "
        "retake effects without making any creative or production changes"
    ),
    "effect": "read",
    "input_schema": {
        "project_id": "existing creator-authorized project ID",
        "object_id": "exact immutable FilmIndex presentation/edit/Take ID",
        "revision": "exact existing positive FilmIndex revision",
        "max_nodes": "optional integer from 4 to 64",
    },
    "result_schema": FORMAT,
    "requires_host_authorization": True,
    "executable_by_model": False,
    "creator_approval_supplied_by_discovery": False,
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _validate_source_take(index, pid, record):
    """Check actual pinned FilmIndex source edges, NOT a source blob render."""
    if (record["kind"] != "take" or
            record["data"].get("format") != USD_TAKE_FORMAT or
            record["data"].get("frozen") is not True):
        return None
    d = record["data"]
    required = (
        ("scene", "scene_id", "scene_revision", "scene_document_sha256"),
        ("temporal", "timeline_id", "timeline_revision",
         "timeline_document_sha256"),
    )
    found = []
    for role, oid_key, rev_key, sha_key in required:
        oid, rev, digest = d.get(oid_key), d.get(rev_key), d.get(sha_key)
        if (type(oid) is not str or type(rev) is not int or
                type(digest) is not str or len(digest) != 64 or
                {"object_id": oid, "revision": rev, "role": role}
                not in record["dependencies"]):
            raise PermissionError("Frozen Take source dependency is not traceable")
        source = index.read_revision(pid, oid, rev)
        if (source["document_sha256"] != digest or
                source["kind"] != role):
            raise PermissionError("Frozen Take source SHA or kind changed")
        found.append({
            "object_id": oid, "revision": rev, "kind": role,
            "document_sha256": digest,
            "source_verified_to_index_revision": True,
            "native_usd_or_audio_reopened_here": False,
        })
    return {
        "take_id": record["object_id"],
        "take_revision": record["revision"],
        "take_document_sha256": record["document_sha256"],
        "source_scene": found[0],
        "source_timeline": found[1],
        "creator_approval_required_for_new_take": True,
        "existing_take_mutated": False,
        "source_media_reopened_in_this_read": False,
    }


def _bounded_dependents(index, pid, origin, limit=MAX_DIRECT_DEPENDENTS):
    """One-hop consumers only; do not imply unindexed film outputs are covered."""
    rows = index.direct_dependents(
        pid, origin["object_id"], origin["revision"])
    return (
        rows[:limit],
        len(rows) > limit
    )


def plan_source_retake(index: FilmIndex, project_id: str, object_id: str,
                       revision: int, *, max_nodes: int = MAX_GRAPH_NODES):
    """Bounded read-only plan: exact presentation/edit/Take -> source USD.

    All film project data comes from the real existing FilmIndex; this
    function has no authorization of its own. Call it only after host
    scope authorization. It never writes, renders or self-approves.
    """
    if not isinstance(index, FilmIndex):
        raise TypeError("Existing trusted FilmIndex is required")
    _require_pid(project_id)
    _id(object_id, "original film object")
    if type(revision) is not int or revision < 1:
        raise ValueError("Choose an exact positive film revision")
    if type(max_nodes) is not int or not 4 <= max_nodes <= MAX_GRAPH_NODES:
        raise ValueError("Bounded source graph size must be 4..64")
    selected = index.read_revision(project_id, object_id, revision)
    if selected["kind"] not in ("presentation", "edit", "take", "master"):
        raise ValueError("Choose an indexed finished film, edit, master or Take")
    source_sha = selected["document_sha256"]
    pending = deque([(object_id, revision)])
    enqueued = {(object_id, revision)}
    visited = set()
    graph = []
    takes = []
    incomplete = False
    while pending:
        if len(visited) >= max_nodes:
            incomplete = True
            break
        oid, rev = pending.popleft()
        if (oid, rev) in visited:
            continue
        record = index.read_revision(project_id, oid, rev)
        visited.add((oid, rev))
        edges = record["dependencies"]
        graph.append({
            "object_id": oid,
            "revision": rev,
            "kind": record["kind"],
            "document_sha256": record["document_sha256"],
            "indexed_parent_count": len(edges),
        })
        take = _validate_source_take(index, project_id, record)
        if take is not None:
            takes.append(take)
        for dep in edges:
            key = (dep["object_id"], dep["revision"])
            if key not in enqueued:
                enqueued.add(key)
                pending.append(key)
    # NVP's historically committed reels can be represented in
    # FeatureJournal without a FilmIndex edge to their original Digital
    # Takes. Do not assert that "no linked take" means "DCP-only".
    takes.sort(key=lambda x: (x["take_id"], x["take_revision"]))
    affected = []
    dependent_truncated = False
    if takes:
        origin = takes[0]["source_scene"]
        affected, dependent_truncated = _bounded_dependents(
            index, project_id, origin)
    # Immutable exact FilmIndex objects are safe to reopen; verify the
    # selected source has not changed even if another writer commits a
    # distinct, newer revision during this read.
    if (index.read_revision(project_id, object_id, revision)[
            "document_sha256"] != source_sha):
        raise RuntimeError("Selected film source changed during planning")
    complete = not incomplete and not dependent_truncated
    metadata_ready = bool(takes) and complete
    state = (
        "PINNED_USD_RETAKE_SOURCES_FOUND_NOT_AUTHORIZED"
        if metadata_ready else
        "INCOMPLETE_OR_UNLINKED_RETAKE_SOURCE_EVIDENCE"
    )
    result = {
        "format": FORMAT,
        "status": state,
        "project_id": project_id,
        "selected": {
            "object_id": object_id,
            "revision": revision,
            "kind": selected["kind"],
            "document_sha256": source_sha,
        },
        "indexed_lineage": graph,
        "indexed_lineage_complete": not incomplete,
        "indexed_lineage_omitted_at_least": len(pending) if incomplete else 0,
        "source_takes": takes,
        "source_take_count": len(takes),
        "indexed_direct_scene_consumers": affected,
        "indexed_direct_scene_consumers_truncated": dependent_truncated,
        "complete_downstream_impact_coverage": False,
        "feature_journal_custody_followed": False,
        "unindexed_reels_or_outputs_may_exist": True,
        "authored_usd_files_independently_reopened": False,
        "new_take_possible_from_bound_metadata": metadata_ready,
        "new_take_recorded": False,
        "new_scene_revision_recorded": False,
        "published_dcp_mutated": False,
        "original_take_mutated": False,
        "proposed_next_steps": [
            "Confirm the exact original scene, temporal events and chosen source Take",
            "Have the NVP native scene reader independently reopen source USD and media",
            "Preview the proposed director changes and all known dependent outputs",
            "Request creator approval from the trusted native host",
            "Record a NEW scene revision / NEW immutable Digital Take ID",
            "Reassemble, remaster and publish a NEW derived final DCP if authorized",
            "Retain previous source Takes, revisions and the earlier DCP",
        ],
        "creator_grant_received": False,
        "worker_executed": False,
        "model_executed": False,
        "approved_for_distribution": False,
        "source_read_side_effects": False,
    }
    result["plan_sha256"] = sha256(_canonical(result)).hexdigest()
    return result


def capability_descriptor():
    return deepcopy(PLAN_CAPABILITY)
