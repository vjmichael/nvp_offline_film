"""NVP-WRITE-06: creator-authorized intra-scene minds, unreliable beliefs and review.

The Story Bible is the source of *objective canon*. This service records a
character's beliefs and disclosures at explicitly chosen screenplay beats.
A deceptive statement does NOT change what its listener believes; a false
belief does NOT change the truth. None of these records is mined from dialogue.

Only accepted creator decisions enter writing context. Derived continuity
suggestions can be accepted for review or rejected, but neither decision
rewrites the screenplay, its shots, or accepted Story Bible facts.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible, checked_text, sha_scene, timestamp
from backend.nvp_story_timeline import StoryTimeline, _scene, _require_entity, _require_project

MODES = frozenset({"learn_truth", "believe", "doubt", "forget"})
INTENTS = frozenset({"deliberate_deception", "mistake", "bluff", "truthful_claim"})
MAX_BEATS_PER_SCENE = 256
MAX_RECORDS_PER_BEAT = 2048


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _revision(db, project_id: str, expected: int | None = None) -> int:
    _require_project(db, project_id)
    db.execute("INSERT OR IGNORE INTO scene_mind_state(project_id,revision) VALUES (?,0)",
               (project_id,))
    current = db.execute("SELECT revision FROM scene_mind_state WHERE project_id=?",
                         (project_id,)).fetchone()["revision"]
    if expected is not None and (type(expected) is not int or expected != current):
        raise RuntimeError("Scene knowledge changed; refresh before editing")
    return current


def _bump(db, project_id: str) -> None:
    db.execute("UPDATE scene_mind_state SET revision=revision+1 WHERE project_id=?", (project_id,))


def _beat(db, project_id: str, beat_id: str, *, live: bool = True) -> dict:
    row = db.execute("SELECT * FROM scene_mind_beats WHERE project_id=? AND id=?",
                     (project_id, beat_id)).fetchone()
    if row is None:
        raise KeyError("Beat does not belong to this film")
    beat = dict(row)
    if live:
        scene, _ = _scene(db, project_id, beat["scene_id"])
        if beat["scene_sha"] != sha_scene(scene):
            raise RuntimeError("Scene changed; re-anchor the beat before adding knowledge")
        if not 1 <= beat["line_number"] <= len(scene["text"].splitlines()):
            raise RuntimeError("Beat line is no longer in this scene")
    return beat


def _fact(db, project_id: str, fact_id: str, *, require_approved: bool = True) -> dict:
    row = db.execute("SELECT * FROM bible_facts WHERE project_id=? AND id=?",
                     (project_id, fact_id)).fetchone()
    if row is None:
        raise KeyError("Fact does not belong to this film")
    fact = dict(row)
    if require_approved and fact["status"] != "accepted":
        raise RuntimeError("Scene beliefs require a creator-approved Story Bible fact")
    return fact


def _beat_list(db, project_id: str, scene_id: str) -> list[dict]:
    return [dict(x) for x in db.execute(
        "SELECT * FROM scene_mind_beats WHERE project_id=? AND scene_id=? "
        "ORDER BY line_number,id", (project_id, scene_id))]


def _record_list(db, project_id: str, table: str, scene_id: str) -> list[dict]:
    # Table name is chosen exclusively by internal callers, never an argument
    # received across the HTTP/API boundary.
    if table not in {"scene_mind_changes", "scene_mind_statements"}:
        raise ValueError("Invalid internal record table")
    return [dict(row) for row in db.execute(
        f"SELECT r.*,b.line_number,b.label AS beat_label,b.scene_sha "
        f"FROM {table} r JOIN scene_mind_beats b ON b.id=r.beat_id "
        "WHERE r.project_id=? AND b.scene_id=? "
        "ORDER BY b.line_number,r.id", (project_id, scene_id))]


def _approved_canon(db, project_id: str) -> dict:
    return {row["id"]: dict(row) for row in db.execute(
        "SELECT id,entity_id,fact_key,fact_value,story_scope,status FROM bible_facts "
        "WHERE project_id=? AND status='accepted'", (project_id,))}


def scene_mind_snapshot(db, project_id: str, scene_id: str | None = None,
                        *, at_beat_id: str | None = None, phase: str = "before") -> dict:
    """Project or scene projection used by writer digest and reviewer.

    An at_beat_id query with phase=before returns a strict pre-beat state;
    phase=after includes that beat. A call without it returns the
    complete scene transition list and the computed state at the scene end.
    The scene's display order and dialogue never imply epistemic facts.
    """
    _require_project(db, project_id)
    if phase not in ("before", "after"):
        raise ValueError("Beat phase must be before or after")
    if scene_id is None and at_beat_id is not None:
        raise ValueError("A beat query requires an explicit scene")
    if scene_id is not None:
        _scene(db, project_id, scene_id)
    sql_scene = "AND b.scene_id=?" if scene_id is not None else ""
    args = (project_id, scene_id) if scene_id is not None else (project_id,)
    beats = [dict(row) for row in db.execute(
        "SELECT b.* FROM scene_mind_beats b WHERE b.project_id=? "
        + ("AND b.scene_id=? " if scene_id is not None else "")
        + "ORDER BY b.scene_id,b.line_number,b.id", args)]
    if at_beat_id is not None and not any(b["id"] == at_beat_id for b in beats):
        raise KeyError("Requested beat not in this scene")
    stale = []
    for beat in beats:
        try:
            scene, _ = _scene(db, project_id, beat["scene_id"])
            if beat["scene_sha"] != sha_scene(scene):
                stale.append(beat["id"])
        except KeyError:
            stale.append(beat["id"])
    # Reading a stale beat is permitted for the review report, but never
    # silently project its content as authoritative live scene chronology.
    if stale and scene_id is not None:
        raise RuntimeError("Scene knowledge beats are stale; re-anchor before drafting")
    changes = [dict(row) for row in db.execute(
        "SELECT c.*,b.scene_id,b.line_number FROM scene_mind_changes c "
        "JOIN scene_mind_beats b ON b.id=c.beat_id "
        "WHERE c.project_id=? " + sql_scene + " ORDER BY b.scene_id,b.line_number,c.id", args)]
    statements = [dict(row) for row in db.execute(
        "SELECT s.*,b.scene_id,b.line_number FROM scene_mind_statements s "
        "JOIN scene_mind_beats b ON b.id=s.beat_id "
        "WHERE s.project_id=? " + sql_scene + " ORDER BY b.scene_id,b.line_number,s.id", args)]
    canon = _approved_canon(db, project_id)
    for record in changes + statements:
        source = canon.get(record["fact_id"])
        record["source_state"] = "current" if source else "source_fact_changed"
        if source:
            record["fact_key"] = source["fact_key"]
            record["world_value"] = source["fact_value"]
            record["story_scope"] = source["story_scope"]
        else:
            record["fact_key"] = None
            record["world_value"] = None
            record["story_scope"] = None
    state: dict[tuple[str, str], dict] = {}
    limit_position = None
    if at_beat_id is not None:
        limit_position = next(b["line_number"] for b in beats if b["id"] == at_beat_id)
    for record in changes:
        if record["status"] != "accepted" or record["source_state"] != "current":
            continue
        if limit_position is not None and (record["line_number"] > limit_position if phase == "after"
                                           else record["line_number"] >= limit_position):
            continue
        value = record["belief_value"] if record["mode"] == "believe" else None
        new_state = {
            "character_id": record["character_id"], "fact_id": record["fact_id"],
            "fact_key": record["fact_key"], "world_value": record["world_value"],
            "beat_id": record["beat_id"], "mode": record["mode"],
            "belief_value": value, "scene_id": record["scene_id"],
            "line_number": record["line_number"],
        }
        if record["mode"] == "learn_truth":
            new_state["state"] = "knows_true"
        elif record["mode"] == "believe":
            new_state["state"] = ("believes_true" if value == record["world_value"]
                                  else "believes_false")
        elif record["mode"] == "doubt":
            new_state["state"] = "doubts"
        else:
            new_state["state"] = "does_not_recall"
        state[record["character_id"], record["fact_id"]] = new_state
    # No evidence != ignorance. Previous film scenes are not automatically
    # inherited; their order may be flashbacks or incomparable in story time.
    approved_transitions = [r for r in changes if r["status"] == "accepted"]
    approved_statements = [r for r in statements if r["status"] == "accepted"]
    # Only reviews of STILL-CURRENT deterministic issues are meaningful.
    # A changed fact or scene hash gives a distinct suggestion ID; an old
    # reviewer note cannot silently bless the new circumstances.
    current_scenes = ([scene_id] if scene_id is not None else
                      sorted({b["scene_id"] for b in beats}))
    candidate_ids = set()
    for this_scene in current_scenes:
        try:
            candidate_ids.update(s["id"] for s in
                                 SceneMind._candidates(db, project_id, this_scene))
        except KeyError:
            continue  # deleted scene: orphan beats are stale, not canon
    reviews = [dict(row) for row in db.execute(
        "SELECT id,decision,resolution,review_note FROM scene_mind_suggestion_reviews "
        "WHERE project_id=? ORDER BY id", (project_id,))
        if row["id"] in candidate_ids]
    payload = {
        "beats": beats,
        "changes": approved_transitions,
        "statements": approved_statements,
        "reviews": reviews,
        "stale_beats": stale,
        "scene_id": scene_id,
    }
    return {
        "scene_id": scene_id, "beats": beats, "changes": changes,
        "statements": statements, "reviews": reviews,
        "states": list(state.values()),
        "stale_beat_ids": stale,
        "digest_payload": payload if (beats or approved_transitions or approved_statements) else None,
        "limitations": (
            "Within-scene time follows explicit line-anchored beats only. A belief is not world truth; "
            "a deceptive statement is not automatically believed by its listener. "
            "The scene's position in the screenplay does not determine chronology, "
            "and an unwritten knowledge record never proves ignorance."
        ),
    }


class SceneMind:
    def __init__(self, studio: Studio):
        self.studio = studio
        StoryTimeline(studio)
        with studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS scene_mind_state (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0)
            );
            CREATE TABLE IF NOT EXISTS scene_mind_beats (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, line_number INTEGER NOT NULL CHECK(line_number > 0),
                label TEXT NOT NULL, scene_sha TEXT NOT NULL, screenplay_revision INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                UNIQUE(project_id,scene_id,line_number)
            );
            CREATE TABLE IF NOT EXISTS scene_mind_changes (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                beat_id TEXT NOT NULL REFERENCES scene_mind_beats(id),
                character_id TEXT NOT NULL REFERENCES bible_entities(id),
                fact_id TEXT NOT NULL REFERENCES bible_facts(id),
                mode TEXT NOT NULL CHECK(mode IN ('learn_truth','believe','doubt','forget')),
                belief_value TEXT, source_note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected')),
                created_at TEXT NOT NULL, reviewed_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS scene_mind_active_change_slot
               ON scene_mind_changes(beat_id,character_id,fact_id) WHERE status='accepted';
            CREATE TABLE IF NOT EXISTS scene_mind_statements (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                beat_id TEXT NOT NULL REFERENCES scene_mind_beats(id),
                speaker_id TEXT NOT NULL REFERENCES bible_entities(id),
                audience_id TEXT NOT NULL REFERENCES bible_entities(id),
                fact_id TEXT NOT NULL REFERENCES bible_facts(id),
                claimed_value TEXT NOT NULL,
                intent TEXT NOT NULL CHECK(intent IN ('deliberate_deception','mistake','bluff','truthful_claim')),
                source_note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected')),
                created_at TEXT NOT NULL, reviewed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS scene_mind_suggestion_reviews (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                decision TEXT NOT NULL CHECK(decision IN ('accept','reject')),
                resolution TEXT NOT NULL DEFAULT '', review_note TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS scene_mind_changes_project
                ON scene_mind_changes(project_id,character_id,status);
            CREATE INDEX IF NOT EXISTS scene_mind_statements_project
                ON scene_mind_statements(project_id,status);
            """)

    def revision(self, project_id: str) -> int:
        with self.studio._connection() as db:
            return _revision(db, project_id)

    def add_beat(self, project_id: str, scene_id: str, line_number: int,
                 label: str, expected_revision: int, note: str = "") -> dict:
        if type(line_number) is not int or line_number < 1:
            raise ValueError("Beat requires a positive scene-relative line number")
        label = checked_text(label, 150, "beat label")
        note = checked_text(note, 1000, "beat note", required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            scene, project = _scene(db, project_id, scene_id)
            if line_number > len(scene["text"].splitlines()):
                raise ValueError("Beat line must occur inside the selected scene")
            used = db.execute("SELECT COUNT(*) n FROM scene_mind_beats WHERE project_id=? AND scene_id=?",
                              (project_id, scene_id)).fetchone()["n"]
            if db.execute("SELECT 1 FROM scene_mind_beats WHERE project_id=? AND scene_id=? "
                          "AND line_number=?", (project_id, scene_id, line_number)).fetchone():
                raise RuntimeError("A scene beat is already anchored at that line")
            if used >= MAX_BEATS_PER_SCENE:
                raise RuntimeError("Too many explicit scene beats")
            beat_id = uuid.uuid4().hex
            db.execute("INSERT INTO scene_mind_beats VALUES (?,?,?,?,?,?,?,?,?)",
                       (beat_id, project_id, scene_id, line_number, label, sha_scene(scene),
                        project["revision"], note, timestamp()))
            _bump(db, project_id)
            return dict(db.execute("SELECT * FROM scene_mind_beats WHERE id=?", (beat_id,)).fetchone())

    def reanchor_beat(self, project_id: str, beat_id: str, line_number: int,
                      expected_revision: int) -> dict:
        if type(line_number) is not int or line_number < 1:
            raise ValueError("Beat requires a positive scene-relative line number")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            beat = _beat(db, project_id, beat_id, live=False)
            scene, project = _scene(db, project_id, beat["scene_id"])
            if line_number > len(scene["text"].splitlines()):
                raise ValueError("Beat line must be in the current scene")
            duplicate = db.execute("SELECT id FROM scene_mind_beats WHERE project_id=? "
                                   "AND scene_id=? AND line_number=? AND id<>?",
                                   (project_id, beat['scene_id'], line_number, beat_id)).fetchone()
            if duplicate:
                raise RuntimeError("Another scene beat is already anchored at that line")
            db.execute("UPDATE scene_mind_beats SET line_number=?,scene_sha=?,screenplay_revision=? "
                       "WHERE id=? AND project_id=?", (line_number, sha_scene(scene), project["revision"],
                                                        beat_id, project_id))
            _bump(db, project_id)
            return _beat(db, project_id, beat_id)

    def propose_change(self, project_id: str, beat_id: str, character_id: str, fact_id: str,
                       mode: str, belief_value: str | None = None, note: str = "") -> dict:
        if mode not in MODES:
            raise ValueError("Invalid within-scene knowledge change")
        if mode == "believe":
            belief_value = checked_text(belief_value, 2000, "believed value")
        elif belief_value is not None:
            raise ValueError("Only a belief has a claimed value")
        note = checked_text(note, 1000, "knowledge note", required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _beat(db, project_id, beat_id)
            _require_entity(db, project_id, character_id, "character")
            _fact(db, project_id, fact_id)
            count = db.execute("SELECT COUNT(*) n FROM scene_mind_changes WHERE project_id=? "
                               "AND beat_id=?", (project_id, beat_id)).fetchone()["n"]
            if count >= MAX_RECORDS_PER_BEAT:
                raise RuntimeError("Too many knowledge changes on this beat")
            record_id = uuid.uuid4().hex
            db.execute("INSERT INTO scene_mind_changes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (record_id,project_id,beat_id,character_id,fact_id,mode,
                        belief_value,note,"proposed",timestamp(),None))
            # A new proposal does not affect canon or invalidate AI generation.
            return dict(db.execute("SELECT * FROM scene_mind_changes WHERE id=?", (record_id,)).fetchone())

    def decide_change(self, project_id: str, change_id: str, decision: str,
                      expected_revision: int) -> dict:
        if decision not in {"accept", "reject"}:
            raise ValueError("Decision must be accept or reject")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            row = db.execute("SELECT * FROM scene_mind_changes WHERE project_id=? AND id=?",
                             (project_id, change_id)).fetchone()
            if row is None:
                raise KeyError("Scene knowledge proposal not found")
            if row["status"] != "proposed":
                raise RuntimeError("This knowledge change was already reviewed")
            if decision == "accept":
                _beat(db, project_id, row["beat_id"])
                _fact(db, project_id, row["fact_id"])
                if row["mode"] == "learn_truth" and row["belief_value"] is not None:
                    raise RuntimeError("Learning a fact cannot carry a contradictory belief value")
                prior = db.execute("SELECT id FROM scene_mind_changes "
                                   "WHERE beat_id=? AND character_id=? AND fact_id=? AND status='accepted'",
                                   (row["beat_id"], row["character_id"], row["fact_id"])).fetchone()
                if prior:
                    raise RuntimeError("Knowledge for this fact is already resolved at this beat")
            db.execute("UPDATE scene_mind_changes SET status=?,reviewed_at=? WHERE id=?",
                       ("accepted" if decision == "accept" else "rejected",timestamp(),change_id))
            if decision == "accept":
                _bump(db, project_id)
            return dict(db.execute("SELECT * FROM scene_mind_changes WHERE id=?", (change_id,)).fetchone())

    def propose_statement(self, project_id: str, beat_id: str, speaker_id: str,
                          audience_id: str, fact_id: str, claimed_value: str,
                          intent: str, note: str = "") -> dict:
        if intent not in INTENTS:
            raise ValueError("Unsupported statement intention")
        claimed_value = checked_text(claimed_value, 2000, "statement content")
        note = checked_text(note, 1000, "statement note", required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _beat(db, project_id, beat_id)
            _require_entity(db, project_id, speaker_id, "character")
            _require_entity(db, project_id, audience_id, "character")
            _fact(db, project_id, fact_id)
            if db.execute("SELECT COUNT(*) n FROM scene_mind_statements "
                          "WHERE project_id=? AND beat_id=?",
                          (project_id, beat_id)).fetchone()["n"] >= MAX_RECORDS_PER_BEAT:
                raise RuntimeError("Too many statements at this beat")
            statement_id = uuid.uuid4().hex
            db.execute("INSERT INTO scene_mind_statements VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (statement_id,project_id,beat_id,speaker_id,audience_id,fact_id,
                        claimed_value,intent,note,"proposed",timestamp(),None))
            return dict(db.execute("SELECT * FROM scene_mind_statements WHERE id=?",
                                   (statement_id,)).fetchone())

    def decide_statement(self, project_id: str, statement_id: str, decision: str,
                         expected_revision: int) -> dict:
        if decision not in {"accept", "reject"}:
            raise ValueError("Decision must be accept or reject")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            row = db.execute("SELECT * FROM scene_mind_statements WHERE project_id=? AND id=?",
                             (project_id, statement_id)).fetchone()
            if row is None:
                raise KeyError("Statement proposal not in this film")
            if row["status"] != "proposed":
                raise RuntimeError("Statement has already been reviewed")
            if decision == "accept":
                _beat(db, project_id, row["beat_id"])
                _fact(db, project_id, row["fact_id"])
            db.execute("UPDATE scene_mind_statements SET status=?,reviewed_at=? WHERE id=?",
                       ("accepted" if decision == "accept" else "rejected",timestamp(),statement_id))
            if decision == "accept":
                _bump(db, project_id)
            return dict(db.execute("SELECT * FROM scene_mind_statements WHERE id=?",
                                   (statement_id,)).fetchone())

    def snapshot(self, project_id: str, scene_id: str | None = None,
                 at_beat_id: str | None = None, phase: str = "before") -> dict:
        with self.studio._connection() as db:
            data = scene_mind_snapshot(db, project_id, scene_id, at_beat_id=at_beat_id, phase=phase)
            data.pop("digest_payload")
            state = db.execute("SELECT revision FROM scene_mind_state WHERE project_id=?",
                               (project_id,)).fetchone()
            data["revision"] = state["revision"] if state else 0
            return data

    @staticmethod
    def _candidates(db, project_id: str, scene_id: str) -> list[dict]:
        scene, _ = _scene(db, project_id, scene_id)
        beats = _beat_list(db, project_id, scene_id)
        canon = _approved_canon(db, project_id)
        changes = _record_list(db, project_id, "scene_mind_changes", scene_id)
        statements = _record_list(db, project_id, "scene_mind_statements", scene_id)
        candidates = []

        def append(kind, record, message, action):
            evidence = {"kind": kind, "record_id": record["id"],
                        "record_status": record["status"],
                        "beat_id": record["beat_id"],
                        "canon": canon.get(record["fact_id"]),
                        "scene_sha": sha_scene(scene),
                        "intent": record.get("intent"),
                        "belief_value": record.get("belief_value"),
                        "claimed_value": record.get("claimed_value")}
            return candidates.append({
                "id": _digest(evidence), "kind": kind,
                "record_id": record["id"], "beat_id": record["beat_id"],
                "message": message, "suggested_action": action,
                "scene_id": scene_id,
            })

        for beat in beats:
            if beat['scene_sha'] != sha_scene(scene):
                evidence = {'kind': 'stale_scene_beat', 'beat_id': beat['id'],
                            'old_sha': beat['scene_sha'], 'new_sha': sha_scene(scene)}
                candidates.append({'id': _digest(evidence), 'kind': 'stale_scene_beat',
                                   'record_id': beat['id'], 'beat_id': beat['id'],
                                   'scene_id': scene_id, 'message':
                                   'This story beat refers to an older screenplay scene.',
                                   'suggested_action': 'Re-anchor the beat at its current line'})
        for record in changes:
            if record["status"] != "accepted":
                continue
            source = canon.get(record["fact_id"])
            if source is None:
                append("knowledge_source_changed", record,
                       "An approved knowledge transition refers to a fact no longer in canon.",
                       "Review or replace the knowledge source")
            elif record["mode"] == "believe" and record["belief_value"] != source["fact_value"]:
                append("mistaken_belief", record,
                       "A character's explicitly approved belief differs from objective canon. "
                       "This may be intentional dramatic misunderstanding.",
                       "Confirm intended misunderstanding or plan a later reveal")
        for record in statements:
            if record["status"] != "accepted":
                continue
            source = canon.get(record["fact_id"])
            if source is None:
                append("statement_source_changed", record,
                       "An approved character statement references superseded canon.",
                       "Review and re-author the statement source")
            elif record["intent"] == "deliberate_deception" and record["claimed_value"] == source["fact_value"]:
                append("deception_matches_canon", record,
                       "A deliberately deceptive statement matches the objective fact. "
                       "It may be a deceptive omission, but cannot be verified as false wording.",
                       "Specify misleading context or revise the statement")
            elif record["intent"] == "truthful_claim" and record["claimed_value"] != source["fact_value"]:
                append("claimed_truth_conflicts_canon", record,
                       "A statement labelled truthful contradicts the approved story fact.",
                       "Reconsider intent or seek a creator-approved canon change")
            elif record["intent"] == "deliberate_deception" and record["claimed_value"] != source["fact_value"]:
                # Do not assert intent is impossible. Only identify a gap in
                # explicitly modelled character awareness before this beat.
                already_knows = any(c["status"] == "accepted"
                    and c["character_id"] == record["speaker_id"]
                    and c["fact_id"] == record["fact_id"]
                    and c["mode"] == "learn_truth"
                    and c["line_number"] < record["line_number"]
                    for c in changes)
                if not already_knows:
                    baseline = db.execute("SELECT 1 FROM timeline_knowledge "
                         "WHERE project_id=? AND character_id=? AND fact_id=? "
                         "AND status='accepted' AND learned_at_event_id IS NULL LIMIT 1",
                         (project_id, record["speaker_id"], record["fact_id"])).fetchone()
                    already_knows = baseline is not None
                if not already_knows:
                    append("deceptive_intent_unverified", record,
                           "The creator designated a deliberate lie, but this scene's prior "
                           "knowledge records do not establish that the speaker knew the truth. "
                           "The lie may still be intentional.",
                           "Approve the speaker's earlier knowledge or confirm deliberate concealment")
        return sorted(candidates, key=lambda row: (row["kind"], row["record_id"]))

    def suggestions(self, project_id: str, scene_id: str) -> dict:
        with self.studio._connection() as db:
            _scene(db, project_id, scene_id)
            current = self._candidates(db, project_id, scene_id)
            reviews = {r["id"]: dict(r) for r in db.execute(
                "SELECT * FROM scene_mind_suggestion_reviews WHERE project_id=?",
                (project_id,))}
            for item in current:
                review = reviews.get(item["id"])
                item["status"] = review["decision"] if review else "proposed"
                item["resolution"] = review["resolution"] if review else ""
                item["review_note"] = review["review_note"] if review else ""
            return {"scene_id": scene_id, "revision": _revision(db, project_id),
                    "suggestions": current,
                    "limitations": "Suggestions report structured evidence only. They do not edit screenplay, "
                                   "create knowledge automatically or claim full dialogue understanding."}

    def decide_suggestion(self, project_id: str, scene_id: str, suggestion_id: str,
                          decision: str, expected_revision: int,
                          resolution: str = "", review_note: str = "") -> dict:
        if decision not in {"accept", "reject"}:
            raise ValueError("Suggestion decision must be accept or reject")
        if resolution not in ("", "intentional", "fix_later"):
            raise ValueError("Resolution must be intentional or fix_later")
        if decision == "accept" and resolution not in ("intentional", "fix_later"):
            raise ValueError("Accepting a continuity suggestion needs an explicit resolution")
        resolution = resolution if decision == "accept" else ""
        review_note = checked_text(review_note, 1000, "review note", required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _revision(db, project_id, expected_revision)
            _scene(db, project_id, scene_id)
            match = next((r for r in self._candidates(db, project_id, scene_id)
                          if r["id"] == suggestion_id), None)
            if match is None:
                raise RuntimeError("Continuity suggestion changed; refresh before reviewing")
            if db.execute("SELECT 1 FROM scene_mind_suggestion_reviews WHERE project_id=? AND id=?",
                          (project_id, suggestion_id)).fetchone():
                raise RuntimeError("Continuity suggestion already reviewed")
            db.execute("INSERT INTO scene_mind_suggestion_reviews VALUES (?,?,?,?,?,?)",
                       (suggestion_id, project_id, decision, resolution, review_note, timestamp()))
            _bump(db, project_id)
        return self.suggestions(project_id, scene_id)
