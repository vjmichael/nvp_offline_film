"""WO6-04: read-only, source-and-approved-Bible-bound production impact preview.

A PREVIEW is evidence for a director's decision, not an edit command, AI
authorization, render request, native worker reservation, release receipt,
or claim that all unindexed FeatureJournal derivatives were discovered.

Uses existing FilmIndex revision edges (including normalized large-editor
and sparse temporal references), accepted Production/Story Bible digest,
existing WO4 scratch estimates and strictly bounded native read queries.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
import re

from backend.nvp_bible_context import canon_snapshot
from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_studio import Studio
from backend.nvp_wo4_resource_budget import plan_feature

FORMAT = "nvp.wo6.source_impact_and_approval_preview.v1"
CAPABILITY = {
    "id": "nvp.film.preview_source_impact.v1",
    "description": "Read-only original revision, bounded indexed downstream "
                   "consumers, approved Production Bible and required grants "
                   "for proposed scene/Take/film changes",
    "effect": "read",
    "requires_host_authorization": True,
    "executable_by_model": False,
    "preview_does_not_authorize_any_native_operation": True,
    "input_schema": {
        "project_id": "existing creator-authorized project",
        "source_id": "exact FilmIndex object identity",
        "source_revision": "exact positive FilmIndex revision",
        "source_sha256": "exact existing FilmIndex revision SHA",
        "change_kind": "one of supported typed non-executable proposals",
        "scene_id": "optional explicitly linked screenplay scene ID",
        "screenplay_revision": "exact current revision with scene_id",
        "bible_fact_id": "optional exact approved Story Bible fact",
        "expected_bible_digest": "optional previously observed approved canon SHA",
        "max_nodes": "bounded 1..64",
        "delivery": "optional bounded 24fps output frames, DCP profile, channels",
    },
    "result_schema": FORMAT,
}
MAX_NODES = 64
MAX_BIBLE_LINKED_SCENES = 64
KIND_ACCEPTS = {
    "revise_scene": {"scene"},
    "revise_actor_performance": {"scene", "performance", "actor"},
    "revise_camera": {"scene", "camera", "temporal"},
    "revise_sound": {"audio", "dialogue", "temporal"},
    "revise_edit": {"edit", "presentation"},
    "revise_color": {"take", "style", "presentation", "master"},
    "retake": {"scene", "take"},
    "remaster": {"master", "audio", "presentation"},
    "republish_dcp": {"presentation", "master"},
    "revise_bible_fact": {"scene", "actor", "performance"},
}
DOMAIN_EFFECTS = {
    "revise_scene": ("world", "performance", "camera", "lighting", "take",
                     "edit", "picture", "master", "dcp"),
    "revise_actor_performance": ("actor", "performance", "take", "edit",
                                 "picture", "sound", "master", "dcp"),
    "revise_camera": ("camera", "shot", "edit", "picture", "master", "dcp"),
    "revise_sound": ("sound", "mix", "master", "dcp"),
    "revise_edit": ("edit", "picture", "sound", "master", "dcp"),
    "revise_color": ("color", "picture", "master", "dcp"),
    "retake": ("scene", "performance", "take", "edit", "picture",
               "sound", "master", "dcp"),
    "remaster": ("mix", "master", "dcp"),
    "republish_dcp": ("dcp", "quality_control", "theatrical"),
    "revise_bible_fact": ("canon", "continuity", "scene", "actor",
                          "take", "edit", "master", "dcp"),
}
BIBLE_CORE = frozenset({
    "bible_entities", "bible_facts", "bible_names", "bible_scene_links",
})
BIBLE_FULL = BIBLE_CORE | frozenset({
    "timeline_edges", "timeline_scene_marks", "timeline_knowledge",
    "scene_mind_beats", "scene_mind_changes", "scene_mind_statements",
    "scene_mind_suggestion_reviews",
    "timeline_state", "scene_mind_state",
})


def _canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def _project_screenplay_revision(studio, project_id, revision, scene_id):
    if (scene_id is None) != (revision is None):
        raise ValueError("Screenplay scene and revision must be selected together")
    if scene_id is None:
        return None
    _id(scene_id, "approved screenplay scene")
    if type(revision) is not int or revision < 0:
        raise ValueError("Current exact screenplay revision required")
    project = studio.get_project(project_id)
    if project["revision"] != revision:
        raise RuntimeError("Screenplay changed; impact preview must refresh")
    if not any(s["id"] == scene_id for s in project["scenes"]):
        raise KeyError("Screenplay scene absent in current project")
    return revision


def _bible_snapshot(studio, project_id, scene_id, revision, expected_digest):
    if expected_digest is not None:
        _sha(expected_digest)
    if scene_id is None:
        if expected_digest is not None:
            raise ValueError("Exact scene scope required for approved Bible digest")
        return {
            "status": "NO_SCENE_SELECTED_BIBLE_IMPACT_UNRESOLVED",
            "digest": None, "screenplay_scene_id": None,
            "accepted_facts_total": None, "accepted_facts_in_packet": 0,
            "approved_facts_text": None, "story_order_verified": False,
            "character_knowledge_verified": False, "complete_canon_loaded": False,
            "continuity_requires_creator_review": True,
        }
    with studio._connection() as db:
        names = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not BIBLE_FULL.issubset(names):
            if expected_digest is not None:
                raise RuntimeError("Approved Bible digest cannot be verified without initialized Bible")
            return {
                "status": "PRODUCTION_BIBLE_NOT_FULLY_INITIALIZED",
                "digest": None, "screenplay_scene_id": scene_id,
                "accepted_facts_total": None, "accepted_facts_in_packet": 0,
                "approved_facts_text": None,
                "missing_schema_components": sorted(BIBLE_FULL - names),
                "story_order_verified": False,
                "character_knowledge_verified": False,
                "complete_canon_loaded": False,
                "continuity_requires_creator_review": True,
            }
        snap = canon_snapshot(db, project_id, scene_id)
    if expected_digest is not None and snap["digest"] != expected_digest:
        raise RuntimeError("Production Bible approved canon changed")
    return {
        "status": "APPROVED_SCENE_PRODUCTION_BIBLE_SNAPSHOT",
        "digest": snap["digest"],
        "screenplay_scene_id": scene_id,
        "screenplay_revision": revision,
        "accepted_facts_total": snap["facts_total"],
        "accepted_facts_in_packet": snap["facts_included"],
        "approved_facts_text": snap["text"],
        "approved_facts_omitted": snap["facts_total"] - snap["facts_included"],
        "story_order_verified": True,
        "character_knowledge_verified": True,
        "complete_canon_loaded": False,  # prompt may truncate; digest is full
        "continuity_requires_creator_review": True,
        "approval_not_inferred_from_story_scope_labels": True,
        "character_belief_not_objective_truth": True,
    }


def _fact_impact(studio, project_id, scene_id, bible_fact_id):
    if bible_fact_id is None:
        return None
    if scene_id is None:
        raise ValueError("Bible fact impact requires an exact screenplay scene")
    if type(bible_fact_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", bible_fact_id):
        raise ValueError("Approved Story Bible fact ID must be a stable 32-hex UUID")
    with studio._connection() as db:
        existing = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not BIBLE_CORE.issubset(existing):
            raise PermissionError("Approved Story Bible has not been initialized")
        row = db.execute("""
            SELECT f.id,f.entity_id,f.fact_key,f.story_scope,f.status,
                   e.name,e.kind,e.revision
            FROM bible_facts f JOIN bible_entities e ON
              e.id=f.entity_id AND e.project_id=f.project_id
            WHERE f.project_id=? AND f.id=?
        """, (project_id, bible_fact_id)).fetchone()
        if row is None or row["status"] != "accepted":
            raise PermissionError("Only an existing creator-accepted fact can be previewed")
        links = [dict(x) for x in db.execute("""
            SELECT scene_id,scene_sha,screenplay_revision FROM bible_scene_links
            WHERE project_id=? AND entity_id=? ORDER BY scene_id LIMIT ?
        """, (project_id, row["entity_id"], MAX_BIBLE_LINKED_SCENES + 1))]
        if scene_id not in {x["scene_id"] for x in links}:
            # Scope cannot be widened by a model or the similarity of names.
            raise PermissionError("Approved fact does not have an explicit scene link")
    return {
        "fact_id": row["id"], "entity_id": row["entity_id"],
        "entity_name": row["name"], "entity_kind": row["kind"],
        "entity_revision": row["revision"],
        "fact_key": row["fact_key"], "story_scope": row["story_scope"],
        "old_fact_value_exposed": False,
        "accepted_fact_may_be_superseded_only_by_creator": True,
        "known_linked_scenes": links[:MAX_BIBLE_LINKED_SCENES],
        "known_linked_scenes_truncated": len(links) > MAX_BIBLE_LINKED_SCENES,
        "automatic_story_time_scope_inference": False,
    }


def _source_lifecycle_state(index, project_id, oid):
    # FilmSourceLifecycle.__init__ creates schema, so a read-only impact
    # preview queries the existing lifecycle table directly instead.
    with index.studio._connection() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='nvp_film_source_retirements'").fetchone()
        if not exists:
            return "ACTIVE_LEGACY_UNTRACKED"
        row = db.execute("""SELECT state FROM nvp_film_source_retirements
            WHERE project_id=? AND object_id=?""",(project_id,oid)).fetchone()
        return row["state"] if row else "ACTIVE"


def _indexed_consumers(index, project_id, oid, revision, doc_sha, limit):
    """Bound reads on all three existing FilmIndex consumer edge surfaces."""
    if type(limit) is not int or limit < 1 or limit > MAX_NODES:
        raise ValueError("Bounded consumer read budget required")
    rows = []
    overflow = False
    with index.studio._connection() as db:
        # Source edges: film_dependencies is an ordinary normalized index.
        queries = [("""
            SELECT source_id AS object_id,source_revision AS revision
            FROM film_dependencies WHERE project_id=?
              AND target_id=? AND target_revision=?
            ORDER BY source_id,source_revision LIMIT ?
        """, (project_id, oid, revision, limit + 1))]
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "scale_editorial_source_bindings" in tables:
            queries.append(("""SELECT b.edit_id AS object_id,b.revision AS revision
                FROM scale_editorial_source_bindings b
                JOIN film_object_revisions r
                  ON r.project_id=b.project_id AND r.object_id=b.edit_id
                  AND r.revision=b.revision
                WHERE b.project_id=? AND b.source_id=?
                  AND b.source_revision=? AND b.source_document_sha256=?
                ORDER BY b.edit_id,b.revision LIMIT ?""",
                            (project_id, oid, revision, doc_sha, limit + 1)))
        if "nvp_temporal_events" in tables:
            queries.append(("""SELECT DISTINCT e.timeline_id AS object_id,
                       e.revision AS revision
                    FROM nvp_temporal_events e JOIN film_object_revisions r
                      ON r.project_id=e.project_id AND r.object_id=e.timeline_id
                     AND r.revision=e.revision
                    WHERE e.project_id=? AND e.source_id=?
                      AND e.source_revision=? AND e.source_document_sha256=?
                    ORDER BY e.timeline_id,e.revision LIMIT ?""",
                            (project_id, oid, revision, doc_sha, limit + 1)))
        for query, params in queries:
            entries = [dict(r) for r in db.execute(query, params)]
            if len(entries) > limit:
                overflow = True
            rows.extend(entries)
    unique = {(r["object_id"], r["revision"]) for r in rows}
    if len(unique) > limit:
        overflow = True
    return sorted(unique)[:limit], overflow


def _impact_chain(index, project_id, source, limit):
    queued = deque([(source["object_id"], source["revision"], 0,
                     source["document_sha256"])])
    seen = {(source["object_id"], source["revision"])}
    results = []
    partial = False
    while queued:
        if len(results) >= limit:
            partial = True
            break
        oid, rev, depth, digest = queued.popleft()
        free = limit - len(results)
        direct, truncated = _indexed_consumers(
            index, project_id, oid, rev, digest, free)
        partial |= truncated
        for key in direct:
            if key in seen:
                continue
            if len(results) >= limit:
                partial = True
                break
            seen.add(key)
            record = index.read_revision(project_id, key[0], key[1])
            results.append({
                "object_id": record["object_id"], "revision": record["revision"],
                "kind": record["kind"], "document_sha256": record["document_sha256"],
                "depth": depth + 1,
                "original_revision_not_automatically_invalidated": True,
                "new_derived_revision_may_be_required": True,
            })
            queued.append((record["object_id"], record["revision"],
                           depth + 1, record["document_sha256"]))
    return results, partial


def _required_approval_gates(change_kind, affected_kinds, bible_available):
    """UI-ready gate topology. Never a bearer grant or a permission token."""
    gates = []
    def add(gate_id, authority, subject):
        gates.append({
            "gate_id": gate_id,
            "authority": authority,
            "subject": subject,
            "state": "NOT_REQUESTED",
            "approval_token": None,
            "approval_issued_by_ai": False,
            "condition_automatically_satisfied": False,
        })
    add("director_creative_change", "human_director",
        "Review the actual changed scene, performance, timing and intent")
    if change_kind == "revise_bible_fact" or not bible_available:
        add("creator_canon_and_continuity", "human_creator",
            "Confirm approved Story Bible facts and knowledge scope")
    if change_kind in ("retake", "revise_scene", "revise_actor_performance",
                       "revise_camera", "revise_bible_fact"):
        add("new_immutable_take", "human_director",
            "Approve creation of a new source revision and Digital Take ID")
    if "edit" in affected_kinds or change_kind in (
            "revise_edit", "retake", "revise_scene"):
        add("editorial_cut_review", "human_director",
            "Approve revised cut and source/derived timeline references")
    if change_kind in ("revise_sound", "remaster", "retake", "revise_edit") or (
            "master" in affected_kinds):
        add("sound_mix_and_master_review", "human_director",
            "Hear original and remastered soundtrack before delivery")
    if change_kind == "revise_color" or "presentation" in affected_kinds:
        add("picture_color_and_reel_review", "human_director",
            "Watch independently rendered picture/color across cuts/reels")
    if change_kind in ("republish_dcp","remaster") or (
            "presentation" in affected_kinds):
        add("final_delivery_and_cinema_qc", "human_director_and_independent_qc",
            "Approve a NEW publication, independent theater ingest and DCP QC")
    add("native_tool_permission", "trusted_native_host",
        "Grant exact per-turn worker operations after creator review")
    add("native_capacity_and_recovery", "trusted_native_host",
        "Recheck real disk/RAM/VRAM, durable job cancel/restart and rollback")
    return gates


def preview_source_impact(index: FilmIndex, project_id: str, source_id: str,
                          source_revision: int, source_sha256: str,
                          change_kind: str, *, scene_id=None,
                          screenplay_revision=None, bible_fact_id=None,
                          expected_bible_digest=None, max_nodes: int = 32,
                          delivery=None) -> dict:
    """Preview the proposed impact; do not apply, persist or authorize it."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Trusted existing FilmIndex is required")
    _require_pid(project_id)
    _id(source_id, "selected source")
    _sha(source_sha256)
    if type(source_revision) is not int or source_revision < 1:
        raise ValueError("Exact positive source revision required")
    if type(change_kind) is not str or change_kind not in KIND_ACCEPTS:
        raise ValueError("Unsupported typed original film change")
    if type(max_nodes) is not int or not 1 <= max_nodes <= MAX_NODES:
        raise ValueError("Bounded indexed impact node count required")
    if bible_fact_id is not None and change_kind != "revise_bible_fact":
        raise ValueError("Only a Bible fact change can target a Bible fact ID")
    if change_kind == "revise_bible_fact" and bible_fact_id is None:
        raise ValueError("A Bible fact change must pin its approved fact ID")
    _project_screenplay_revision(index.studio, project_id,
                                 screenplay_revision, scene_id)
    source = index.read_revision(project_id, source_id, source_revision)
    if source["document_sha256"] != source_sha256:
        raise PermissionError("Expected original source revision SHA mismatched")
    if source["kind"] not in KIND_ACCEPTS[change_kind]:
        raise ValueError("Proposed change does not apply to this source kind")
    # Read exact historical source and current head separately. Old Takes
    # stay valid, but a new proposed edit cannot be "approved current".
    current = index.read_revision(project_id, source_id)
    lifecycle = _source_lifecycle_state(index, project_id, source_id)
    retired = lifecycle in ("RETIRED", "PURGED")
    current_head = current["revision"] == source_revision
    graph, partial = _impact_chain(index, project_id, source, max_nodes)
    bible = _bible_snapshot(index.studio, project_id, scene_id,
                            screenplay_revision, expected_bible_digest)
    fact = _fact_impact(index.studio, project_id, scene_id, bible_fact_id)
    if change_kind == "revise_bible_fact" and bible["digest"] is None:
        raise PermissionError("Approved scene Production Bible is needed")
    resource = None
    if delivery is not None:
        if (type(delivery) is not dict or
                set(delivery) != {"frames", "profile", "channels"}):
            raise ValueError("Resource estimate needs exact frame/profile/channel")
        planned = plan_feature(
            frames=delivery["frames"], profile=delivery["profile"],
            channels=delivery["channels"])
        resource = {
            "status": "CREATOR_SUPPLIED_ESTIMATE_NOT_HOST_ADMISSION",
            "profile": planned["profile"], "channels": planned["channels"],
            "frame_count": planned["frames"],
            "reel_count": planned["reel_count"],
            "scratch_upper_estimate_bytes": planned[
                "estimated_upper_scratch_bytes"],
            "individual_frame_resident_upper_bytes": planned[
                "single_frame_resident_bytes_upper_bound"],
            "actual_free_disk_checked": False,
            "current_ram_or_vram_checked": False,
            "actual_runtime_admitted": False,
            "throughput_measured": False,
        }
    affected_kinds = sorted({entry["kind"] for entry in graph})
    # The graph captures indexed recorded derivatives of the ORIGINAL
    # source, not what would be changed by a not-yet-approved future edit.
    boundaries = ["Indexed FilmIndex dependency edges only",
                  "Unindexed FeatureJournal/multireel outputs may exist",
                  "This preview did not reopen a finished DCP or inspect media",
                  "FilmIndex changes do not infer character story knowledge",
                  "A proposed change is not an approved creative decision"]
    needs_refresh = not current_head or retired
    if bible["status"] != "APPROVED_SCENE_PRODUCTION_BIBLE_SNAPSHOT":
        boundaries.append("Full approved scene Production Bible unavailable")
    result = {
        "format": FORMAT,
        "status": ("RETIRED_SOURCE_NOT_ADMISSIBLE_FOR_NEW_WORK"
                   if retired else "HISTORICAL_SOURCE_REFRESH_REQUIRED"
                   if needs_refresh else
                   "READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT"),
        "project_id": project_id,
        "change_kind": change_kind,
        "proposal_source": {
            "object_id": source_id, "revision": source_revision,
            "kind": source["kind"], "document_sha256": source_sha256,
            "head_revision_observed": current["revision"],
            "current_head_sha256": current["document_sha256"],
            "is_current_head": current_head,
            "lifecycle_state": lifecycle,
            "retired_or_purged": retired,
        },
        "potentially_affected_domains": list(DOMAIN_EFFECTS[change_kind]),
        "indexed_downstream": graph,
        "indexed_downstream_truncated": partial,
        "indexed_downstream_kinds": affected_kinds,
        "all_downstream_outputs_proven": False,
        "feature_journal_outputs_reconciled": False,
        "other_unindexed_derivatives_possible": True,
        "old_source_and_derived_revisions_remain_immutable": True,
        "approved_production_bible": bible,
        "approved_bible_fact_impact": fact,
        "resource_estimate": resource,
        "native_capability_requirements": [
            "Retake or scene/camera edit: validated OpenUSD/temporal native sources",
            "Native file workers: exact host tool/license pins and per-turn scope",
            "Sound/mix: saved sound sources, independently verified mastering",
            "Reassembly: new editorial/presentation revisions and revision custody",
            "DCP: new native picture/PCM24 MXF, CPL/PKL/AssetMap and QC",
        ],
        "approval_gate_preview": _required_approval_gates(
            change_kind, affected_kinds,
            bible["status"] == "APPROVED_SCENE_PRODUCTION_BIBLE_SNAPSHOT"),
        "native_execution_admissible_from_this_preview": False,
        "required_director_decisions": [
            "Review exact proposed creative difference and approved Bible scope",
            "Approve whether to create a NEW original Take or source revision",
            "Review replacement shot/edit, mix, color and mastering consequences",
            "Approve final delivery/release separately after actual QC",
        ],
        "required_native_worker_grants": [
            "Current per-turn creator and exact project authorization",
            "Exact operation-specific native tool permission",
            "Fresh capacity/resource/disk admission at actual execution",
            "Durable worker journal, cancellation/restart and rollback policy",
        ],
        "approval_blockers": (
            (["Original source is retired or purged; restore through native creator policy first"]
             if retired else [])
            + (["Original source is not the current working head"]
               if not current_head else [])
            + (["Approved scene Bible is missing/incomplete or unselected"]
               if bible["status"] != "APPROVED_SCENE_PRODUCTION_BIBLE_SNAPSHOT"
               else [])
            + (["Indexed impact graph truncated; search further before approval"]
               if partial else [])
            + ["Full unindexed film/delivery custody has not been reconciled",
               "No creator approval or native worker admission has occurred"]
        ),
        "exact_source_revision_refreshed_after_preview": False,
        "new_source_revision_written": False,
        "new_take_created": False,
        "new_sound_mix_created": False,
        "final_dcp_replaced": False,
        "native_worker_executed": False,
        "model_granted_execution_authority": False,
        "creator_approved": False,
        "side_effects_performed": False,
        "provenance_limitations": boundaries,
    }
    # Read-only race guard. If the old source was already superseded, the
    # historical preview remains explicitly stale, never executable.
    again = index.read_revision(project_id, source_id)
    if _source_lifecycle_state(index, project_id, source_id) != lifecycle:
        raise RuntimeError("Film source lifecycle changed during impact preview")
    if (again["revision"] != current["revision"] or
            again["document_sha256"] != current["document_sha256"]):
        raise RuntimeError("Selected original source head changed during preview")
    if scene_id is not None:
        _project_screenplay_revision(index.studio, project_id,
                                     screenplay_revision, scene_id)
        latest = _bible_snapshot(index.studio, project_id, scene_id,
                                 screenplay_revision, None)
        if latest["digest"] != bible["digest"] or latest["status"] != bible["status"]:
            raise RuntimeError("Approved Production Bible changed during preview")
    result["exact_source_revision_refreshed_after_preview"] = True
    result["preview_sha256"] = sha256(_canon(result)).hexdigest()
    return result
