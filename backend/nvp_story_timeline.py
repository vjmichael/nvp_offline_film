"""Creator-authored partial story chronology and explicit character knowledge.

A screenplay's display order is *not* its story chronology. Event precedence is
an acyclic partial order with incomparability preserved. Scene anchoring is
explicit and revision-checked. Knowledge requires creator approval and a real
accepted Story Bible fact; lack of evidence never means a character doesn't know.

NVP-only film component: no Lu, LLM, network, or renderer dependencies.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import sqlite3
import uuid

from backend.nvp_studio import Studio, parse_screenplay
from backend.nvp_story_bible import StoryBible, checked_text, sha_scene, timestamp

MAX_EVENTS = 5000
MAX_EDGES = 20000
MAX_NOTE = 1000


def _stable_hash(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _reachable(edges: dict[str, set[str]], start: str, target: str) -> bool:
    if start == target:
        return True
    stack, seen = [start], {start}
    while stack:
        for nxt in edges.get(stack.pop(), ()):
            if nxt == target:
                return True
            if nxt not in seen:
                stack.append(nxt)
                seen.add(nxt)
    return False


def _edge_graph(edges) -> dict[str, set[str]]:
    graph = {}
    for edge in edges:
        graph.setdefault(edge["before_id"], set()).add(edge["after_id"])
    return graph


def _require_project(db, project_id):
    project = db.execute("SELECT id,screenplay,revision FROM projects WHERE id=?",
                         (project_id,)).fetchone()
    if project is None:
        raise KeyError("Film project not found")
    return project


def _require_entity(db, project_id, entity_id, kind):
    entity = db.execute("SELECT id,kind,name FROM bible_entities WHERE project_id=? AND id=?",
                        (project_id, entity_id)).fetchone()
    if entity is None or entity["kind"] != kind:
        raise KeyError(f"{kind} does not belong to this film")
    return entity


def _revision(db, project_id, expected_revision=None):
    _require_project(db, project_id)
    db.execute("INSERT OR IGNORE INTO timeline_state (project_id,revision) VALUES (?,0)",
               (project_id,))
    current = db.execute("SELECT revision FROM timeline_state WHERE project_id=?",
                         (project_id,)).fetchone()["revision"]
    if expected_revision is not None and (type(expected_revision) is not int
                                          or expected_revision != current):
        raise RuntimeError("Story timeline changed; refresh before editing")
    return current


def _bump(db, project_id):
    db.execute("UPDATE timeline_state SET revision=revision+1 WHERE project_id=?", (project_id,))


def _scene(db, project_id, scene_id):
    project = _require_project(db, project_id)
    scene = next((s for s in parse_screenplay(project["screenplay"])
                  if s["id"] == scene_id), None)
    if scene is None:
        raise KeyError("Scene missing from the current screenplay")
    return scene, project


def _knowledge_status(db, project_id, knowledge):
    fact = db.execute("SELECT status FROM bible_facts WHERE id=? AND project_id=?",
                      (knowledge["fact_id"], project_id)).fetchone()
    return "accepted" if fact is not None and fact["status"] == "accepted" else "source_fact_changed"


def _knowledge_as_of(graph, learned_at: str | None, marker: dict | None):
    if learned_at is None:
        return "known"  # explicitly approved known before the story begins
    if marker is None:
        return "unanchored"
    anchor, phase = marker["anchor_event_id"], marker["phase"]
    if learned_at == anchor:
        return "known" if phase == "after" else "not_yet"
    if _reachable(graph, learned_at, anchor):
        return "known"
    if _reachable(graph, anchor, learned_at):
        return "not_yet"
    return "indeterminate"  # the events are incomparable; don't invent order


def timeline_snapshot(db, project_id: str, scene_id: str | None = None,
                      *, relevant_entity_ids: set[str] | None = None) -> dict:
    """Read-only timeline projection from the caller's existing DB transaction.

    This function does not initialize tables: StoryTimeline(studio) is the
    explicit migration owner. Its 'digest_payload' includes accepted material
    regardless of the prompt's bounded presentation.
    """
    project = _require_project(db, project_id)
    events = [dict(row) for row in db.execute(
        "SELECT id,name FROM bible_entities WHERE project_id=? AND kind='event' ORDER BY id",
        (project_id,))]
    edges = [dict(row) for row in db.execute(
        "SELECT before_id,after_id FROM timeline_edges WHERE project_id=? ORDER BY before_id,after_id",
        (project_id,))]
    marks = [dict(row) for row in db.execute(
        "SELECT scene_id,anchor_event_id,phase,scene_sha FROM timeline_scene_marks "
        "WHERE project_id=? ORDER BY scene_id", (project_id,))]
    graph = _edge_graph(edges)
    marker = next((m for m in marks if m["scene_id"] == scene_id), None)
    if scene_id is not None:
        scene, _ = _scene(db, project_id, scene_id)
        if marker is not None and marker["scene_sha"] != sha_scene(scene):
            raise RuntimeError("Timeline scene anchor is stale; rebind to the current scene")
    facts = [dict(row) for row in db.execute("""SELECT k.id,k.character_id,k.fact_id,k.learned_at_event_id,
             c.name AS character_name, f.fact_key,f.fact_value,f.story_scope,
             f.status AS fact_status,e.name AS learned_at_name
             FROM timeline_knowledge k
             JOIN bible_entities c ON c.id=k.character_id AND c.project_id=k.project_id
             JOIN bible_facts f ON f.id=k.fact_id AND f.project_id=k.project_id
             LEFT JOIN bible_entities e ON e.id=k.learned_at_event_id AND e.project_id=k.project_id
             WHERE k.project_id=? AND k.status='accepted' ORDER BY k.character_id,k.fact_id,k.id""",
             (project_id,))]
    knowledge = []
    for row in facts:
        if scene_id is not None and relevant_entity_ids is not None and \
           row["character_id"] not in relevant_entity_ids:
            continue
        if row["fact_status"] != "accepted":
            status = "source_fact_changed"
        elif scene_id is not None:
            status = _knowledge_as_of(graph, row["learned_at_event_id"], marker)
        else:
            status = "event_scoped" if row["learned_at_event_id"] else "known_from_start"
        knowledge.append({key: row[key] for key in (
            "id", "character_id", "character_name", "fact_id", "fact_key", "fact_value",
            "story_scope", "learned_at_event_id", "learned_at_name")}
            | {"state": status})
    # Include all accepted knowledge in the fingerprint, not just displayed
    # scene-local text; a new relevant or preceding event can change state.
    selected_knowledge_ids = ({k["id"] for k in knowledge} if scene_id else
                              {k["id"] for k in facts})
    full_knowledge = [
        {key: r[key] for key in ("id", "character_id", "fact_id", "learned_at_event_id", "fact_status")}
        for r in facts if r["id"] in selected_knowledge_ids
    ]
    impact = {"events": events, "edges": edges,
              "marks": marks if scene_id is None else [marker] if marker else [],
              "knowledge": full_knowledge}
    authored = bool(events or edges or marks or full_knowledge)
    return {
        "project_id": project_id, "scene_id": scene_id,
        "events": events, "edges": edges, "scene_marker": marker,
        "knowledge": knowledge, "has_chronology": authored,
        "digest_payload": impact if authored else None,
        "limitations": (
            "Events have explicit partial ordering only. Screenplay scene number does not establish "
            "story time. 'known' means approved as acquired before this anchored scene point; "
            "'not_yet' requires proven ordering; 'indeterminate' means events are unordered. "
            "Missing knowledge records do not establish ignorance. 'unanchored' means this scene "
            "has no approved event anchor. A scene marker is an explicitly selected BEFORE or "
            "AFTER event point, not an inferred moment within the scene."
        ),
    }


class StoryTimeline:
    def __init__(self, studio: Studio):
        self.studio = studio
        StoryBible(studio)  # ensure event entities and accepted fact tables
        with studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS timeline_state (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0)
            );
            CREATE TABLE IF NOT EXISTS timeline_edges (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                before_id TEXT NOT NULL REFERENCES bible_entities(id),
                after_id TEXT NOT NULL REFERENCES bible_entities(id),
                note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                PRIMARY KEY (project_id,before_id,after_id), CHECK(before_id != after_id)
            );
            CREATE TABLE IF NOT EXISTS timeline_scene_marks (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, anchor_event_id TEXT NOT NULL REFERENCES bible_entities(id),
                phase TEXT NOT NULL CHECK(phase IN ('before','after')),
                scene_sha TEXT NOT NULL, screenplay_revision INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id)
            );
            CREATE TABLE IF NOT EXISTS timeline_knowledge (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                character_id TEXT NOT NULL REFERENCES bible_entities(id),
                fact_id TEXT NOT NULL REFERENCES bible_facts(id),
                learned_at_event_id TEXT REFERENCES bible_entities(id),
                status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected')),
                source_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, reviewed_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS timeline_one_accepted_knowledge
                ON timeline_knowledge(project_id,character_id,fact_id) WHERE status='accepted';
            CREATE INDEX IF NOT EXISTS timeline_knowledge_project
                ON timeline_knowledge(project_id,character_id,status);
            """)

    def revision(self, project_id: str) -> int:
        with self.studio._connection() as db:
            _require_project(db, project_id)
            row = db.execute("SELECT revision FROM timeline_state WHERE project_id=?",
                             (project_id,)).fetchone()
            return row["revision"] if row else 0

    def add_precedence(self, project_id: str, before_id: str, after_id: str,
                       expected_revision: int, note: str = "") -> dict:
        note = checked_text(note, MAX_NOTE, "order note", required=False)
        if before_id == after_id:
            raise ValueError("An event cannot precede itself")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rev = _revision(db, project_id, expected_revision)
            _require_entity(db, project_id, before_id, "event")
            _require_entity(db, project_id, after_id, "event")
            edges = [dict(r) for r in db.execute(
                "SELECT before_id,after_id FROM timeline_edges WHERE project_id=?",
                (project_id,))]
            if len(edges) >= MAX_EDGES:
                raise RuntimeError("Story event ordering limit reached")
            graph = _edge_graph(edges)
            if after_id in graph.get(before_id, set()):
                raise RuntimeError("This event ordering has already been recorded")
            if _reachable(graph, after_id, before_id):
                raise RuntimeError("Event order would create a temporal cycle")
            db.execute("INSERT INTO timeline_edges VALUES (?,?,?,?,?)",
                       (project_id, before_id, after_id, note, timestamp()))
            _bump(db, project_id)
        return self.snapshot(project_id)

    def remove_precedence(self, project_id: str, before_id: str, after_id: str,
                          expected_revision: int) -> dict:
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            row = db.execute("DELETE FROM timeline_edges WHERE project_id=? AND before_id=? AND after_id=?",
                             (project_id, before_id, after_id))
            if row.rowcount != 1:
                raise KeyError("Story-event order not found")
            _bump(db, project_id)
        return self.snapshot(project_id)

    def bind_scene(self, project_id: str, scene_id: str, anchor_event_id: str,
                   phase: str, expected_revision: int, note: str = "") -> dict:
        if phase not in ("before", "after"):
            raise ValueError("Scene point must be before or after its anchor event")
        note = checked_text(note, MAX_NOTE, "scene mark", required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            _require_entity(db, project_id, anchor_event_id, "event")
            scene, project = _scene(db, project_id, scene_id)
            db.execute("""INSERT INTO timeline_scene_marks
                (project_id,scene_id,anchor_event_id,phase,scene_sha,screenplay_revision,note,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,scene_id) DO UPDATE SET
                anchor_event_id=excluded.anchor_event_id,phase=excluded.phase,
                scene_sha=excluded.scene_sha,screenplay_revision=excluded.screenplay_revision,
                note=excluded.note,updated_at=excluded.updated_at""",
                (project_id,scene_id,anchor_event_id,phase,sha_scene(scene),project["revision"],
                 note,timestamp()))
            _bump(db, project_id)
        return self.snapshot(project_id)

    def unbind_scene(self, project_id: str, scene_id: str, expected_revision: int) -> dict:
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            deleted = db.execute("DELETE FROM timeline_scene_marks WHERE project_id=? AND scene_id=?",
                                 (project_id,scene_id))
            if deleted.rowcount != 1:
                raise KeyError("Scene event anchor not found")
            _bump(db, project_id)
        return self.snapshot(project_id)

    def propose_knowledge(self, project_id: str, character_id: str, fact_id: str,
                          learned_at_event_id: str | None = None,
                          source_note: str = "") -> dict:
        source_note = checked_text(source_note, MAX_NOTE, "knowledge source", required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _require_project(db, project_id)
            _require_entity(db, project_id, character_id, "character")
            if learned_at_event_id is not None:
                _require_entity(db, project_id, learned_at_event_id, "event")
            fact = db.execute("SELECT id,status FROM bible_facts WHERE id=? AND project_id=?",
                              (fact_id, project_id)).fetchone()
            if fact is None or fact["status"] != "accepted":
                raise RuntimeError("Knowledge must reference an approved fact in the same film")
            claim_id = uuid.uuid4().hex
            db.execute("INSERT INTO timeline_knowledge VALUES (?,?,?,?,?,?,?,?,?)",
                       (claim_id,project_id,character_id,fact_id,learned_at_event_id,
                        "proposed",source_note,timestamp(),None))
            _revision(db, project_id)
        return self.get_knowledge(project_id, claim_id)

    def decide_knowledge(self, project_id: str, claim_id: str, decision: str,
                         expected_revision: int) -> dict:
        if decision not in ("accept", "reject"):
            raise ValueError("Knowledge decisions must be accept or reject")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            row = db.execute("SELECT * FROM timeline_knowledge WHERE id=? AND project_id=?",
                             (claim_id,project_id)).fetchone()
            if row is None:
                raise KeyError("Knowledge proposal not found in this film")
            if row["status"] != "proposed":
                raise RuntimeError("Knowledge proposal has already been reviewed")
            if decision == "accept" and _knowledge_status(db, project_id, row) != "accepted":
                raise RuntimeError("Source fact changed; review before accepting knowledge")
            if decision == "accept":
                duplicate = db.execute("SELECT id FROM timeline_knowledge WHERE project_id=? "
                                       "AND character_id=? AND fact_id=? AND status='accepted'",
                                       (project_id,row["character_id"],row["fact_id"])).fetchone()
                if duplicate:
                    raise RuntimeError("Character knowledge for this fact is already approved")
            db.execute("UPDATE timeline_knowledge SET status=?,reviewed_at=? WHERE id=?",
                       ("accepted" if decision == "accept" else "rejected",timestamp(),claim_id))
            # Rejected claims do not affect accepted story context, but they do
            # advance editing revision for optimistic concurrency.
            _bump(db, project_id)
        return self.get_knowledge(project_id, claim_id)

    def get_knowledge(self, project_id: str, claim_id: str) -> dict:
        with self.studio._connection() as db:
            _require_project(db,project_id)
            row = db.execute("SELECT * FROM timeline_knowledge WHERE project_id=? AND id=?",
                             (project_id,claim_id)).fetchone()
            if row is None:
                raise KeyError("Knowledge assertion not found in this film")
            result = dict(row)
            result["reference_state"] = _knowledge_status(db, project_id,row)
            return result

    def snapshot(self, project_id: str, scene_id: str | None = None) -> dict:
        with self.studio._connection() as db:
            _require_project(db, project_id)
            view = timeline_snapshot(db, project_id, scene_id)
            view.pop("digest_payload")
            current = db.execute("SELECT revision FROM timeline_state WHERE project_id=?",
                                 (project_id,)).fetchone()
            view["revision"] = current["revision"] if current else 0
            view["scene_marks"] = [dict(row) for row in db.execute(
                "SELECT * FROM timeline_scene_marks WHERE project_id=? ORDER BY scene_id",
                (project_id,))]
            view["knowledge_proposals"] = [dict(row) for row in db.execute(
                "SELECT * FROM timeline_knowledge WHERE project_id=? ORDER BY created_at,id",
                (project_id,))]
            return view
