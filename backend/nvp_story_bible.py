"""NVP story bible: project-scoped, creator-reviewed canon and scene impact tracking.

Film-only SQLite domain service; no inference, Lu, renderer, or outside network.
The report detects exact typed-slot disputes and changed linked scenes. It does
NOT claim semantic understanding of screenplay prose or character motivation.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from backend.nvp_studio import Studio, parse_screenplay

KINDS = frozenset({"character", "location", "prop", "event"})
KEY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
SCOPE = re.compile(r"[a-z][a-z0-9_:-]{0,95}\Z")
MAX_ENTITY_NAME = 150
MAX_FACT = 2000


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def checked_text(value: str, maximum: int, field: str, *, required=True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = value.strip()
    if (required and not value) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{field} is empty or too long")
    return value


def sha_scene(scene: dict) -> str:
    return hashlib.sha256(scene["text"].encode("utf-8")).hexdigest()


class StoryBible:
    def __init__(self, studio: Studio):
        self.studio = studio
        with self.studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS bible_entities (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                kind TEXT NOT NULL CHECK(kind IN ('character','location','prop','event')),
                name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS bible_entity_project ON bible_entities(project_id,kind);
            CREATE TABLE IF NOT EXISTS bible_names (
                project_id TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES bible_entities(id) ON DELETE CASCADE,
                kind TEXT NOT NULL, display_name TEXT NOT NULL, normalized_name TEXT NOT NULL,
                is_primary INTEGER NOT NULL CHECK(is_primary IN (0,1)),
                PRIMARY KEY(project_id,kind,normalized_name)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS bible_one_primary_name ON bible_names(entity_id) WHERE is_primary=1;
            CREATE TABLE IF NOT EXISTS bible_facts (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                entity_id TEXT NOT NULL REFERENCES bible_entities(id) ON DELETE CASCADE,
                fact_key TEXT NOT NULL, fact_value TEXT NOT NULL, story_scope TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected','superseded')),
                origin TEXT NOT NULL CHECK(origin IN ('creator','ai_proposal')),
                source_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS bible_facts_entity ON bible_facts(project_id,entity_id,status);
            CREATE UNIQUE INDEX IF NOT EXISTS bible_active_fact_slot
              ON bible_facts(entity_id,fact_key,story_scope) WHERE status='accepted';
            CREATE TABLE IF NOT EXISTS bible_scene_links (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                entity_id TEXT NOT NULL REFERENCES bible_entities(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, scene_heading TEXT NOT NULL, scene_sha TEXT NOT NULL,
                screenplay_revision INTEGER NOT NULL, note TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(project_id,entity_id,scene_id)
            );
            CREATE TABLE IF NOT EXISTS bible_changes (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                entity_id TEXT NOT NULL REFERENCES bible_entities(id) ON DELETE CASCADE,
                new_fact_id TEXT NOT NULL REFERENCES bible_facts(id),
                old_fact_id TEXT REFERENCES bible_facts(id),
                reviewed_revision INTEGER, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS bible_changes_project ON bible_changes(project_id,created_at);
            """)

    @staticmethod
    def _project(db, project_id):
        record = db.execute("SELECT id,revision,screenplay FROM projects WHERE id=?", (project_id,)).fetchone()
        if record is None:
            raise KeyError("Film project not found")
        return record

    @staticmethod
    def _entity(db, project_id, entity_id):
        row = db.execute("SELECT * FROM bible_entities WHERE id=? AND project_id=?",
                         (entity_id, project_id)).fetchone()
        if row is None:
            raise KeyError("Story Bible entity not found in this film")
        return row

    @staticmethod
    def _require_revision(row, expected_revision):
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or row["revision"] != expected_revision:
            raise RuntimeError("Story Bible entry changed; reload before saving")

    @staticmethod
    def _touch(db, entity_id):
        db.execute("UPDATE bible_entities SET revision=revision+1,updated_at=? WHERE id=?",
                   (timestamp(),entity_id))

    @staticmethod
    def _reserve_name(db, project_id, entity_id, kind, label, primary):
        normalized = label.casefold()
        found = db.execute("SELECT entity_id FROM bible_names WHERE project_id=? AND kind=? AND normalized_name=?",
                           (project_id,kind,normalized)).fetchone()
        if found is not None:
            if found["entity_id"] != entity_id:
                raise RuntimeError("Name or alias already belongs to another story entity")
            if primary:
                db.execute("UPDATE bible_names SET is_primary=1 WHERE project_id=? AND kind=? AND normalized_name=?",
                           (project_id,kind,normalized))
            return
        db.execute("INSERT INTO bible_names VALUES (?,?,?,?,?,?)",
                   (project_id,entity_id,kind,label,normalized,int(primary)))

    def create_entity(self, project_id: str, kind: str, name: str, description: str = "") -> dict:
        if kind not in KINDS:
            raise ValueError("Unknown Story Bible entity type")
        name = checked_text(name, MAX_ENTITY_NAME, "name")
        description = checked_text(description, 3000, "description", required=False)
        entity_id, now = uuid.uuid4().hex, timestamp()
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._project(db,project_id)
            db.execute("INSERT INTO bible_entities (id,project_id,kind,name,description,created_at,updated_at) "
                       "VALUES (?,?,?,?,?,?,?)",(entity_id,project_id,kind,name,description,now,now))
            self._reserve_name(db,project_id,entity_id,kind,name,True)
        return self.get_entity(project_id,entity_id)

    def rename_entity(self, project_id: str, entity_id: str, name: str, expected_revision: int) -> dict:
        name=checked_text(name,MAX_ENTITY_NAME,"name")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._entity(db,project_id,entity_id)
            self._require_revision(row,expected_revision)
            if row["name"].casefold() != name.casefold():
                self._reserve_name(db,project_id,entity_id,row["kind"],name,False)
            db.execute("UPDATE bible_names SET is_primary=0 WHERE entity_id=?",(entity_id,))
            db.execute("UPDATE bible_names SET is_primary=1 WHERE entity_id=? AND normalized_name=?",
                       (entity_id,name.casefold()))
            db.execute("UPDATE bible_entities SET name=? WHERE id=?",(name,entity_id))
            self._touch(db,entity_id)
        return self.get_entity(project_id,entity_id)

    def add_alias(self, project_id: str, entity_id: str, alias: str, expected_revision: int) -> dict:
        alias=checked_text(alias,MAX_ENTITY_NAME,"alias")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._entity(db,project_id,entity_id)
            self._require_revision(row,expected_revision)
            self._reserve_name(db,project_id,entity_id,row["kind"],alias,False)
            self._touch(db,entity_id)
        return self.get_entity(project_id,entity_id)

    def propose_fact(self, project_id: str, entity_id: str, key: str, value: str,
                     scope: str = "global", origin: str = "creator", source_note: str = "") -> dict:
        if not isinstance(key,str) or not KEY.fullmatch(key):
            raise ValueError("Fact key must be snake_case")
        if not isinstance(scope,str) or not SCOPE.fullmatch(scope):
            raise ValueError("Invalid story time/context scope")
        if origin not in ("creator","ai_proposal"):
            raise ValueError("Invalid fact origin")
        value=checked_text(value,MAX_FACT,"fact value")
        source_note=checked_text(source_note,500,"source note",required=False)
        fact_id,stamp=uuid.uuid4().hex,timestamp()
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._entity(db,project_id,entity_id)
            db.execute("INSERT INTO bible_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (fact_id,project_id,entity_id,key,value,scope,"proposed",origin,source_note,stamp,stamp))
            self._touch(db,entity_id)
        return self.get_fact(project_id,fact_id)

    def get_fact(self, project_id: str, fact_id: str) -> dict:
        with self.studio._connection() as db:
            row=db.execute("SELECT * FROM bible_facts WHERE project_id=? AND id=?",(project_id,fact_id)).fetchone()
        if row is None:
            raise KeyError("Story Bible fact not found")
        return dict(row)

    def decide_fact(self, project_id: str, fact_id: str, decision: str, expected_entity_revision: int,
                    replaces_fact_id: str | None = None) -> dict:
        if decision not in ("accept","reject"):
            raise ValueError("Choose accept or reject")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            fact=db.execute("SELECT * FROM bible_facts WHERE project_id=? AND id=?",(project_id,fact_id)).fetchone()
            if fact is None: raise KeyError("Fact not found")
            if fact["status"] != "proposed": raise RuntimeError("Fact was already reviewed")
            entity=self._entity(db,project_id,fact["entity_id"])
            self._require_revision(entity,expected_entity_revision)
            existing=db.execute("SELECT id,fact_value FROM bible_facts WHERE entity_id=? AND fact_key=? "
                                "AND story_scope=? AND status='accepted'",
                                (fact["entity_id"],fact["fact_key"],fact["story_scope"])).fetchone()
            if decision == "accept":
                if existing is not None and (not replaces_fact_id or existing["id"] != replaces_fact_id):
                    raise RuntimeError("Conflicting accepted fact exists; explicitly choose the fact to replace")
                if existing is None and replaces_fact_id is not None:
                    raise RuntimeError("Replacement fact is no longer current")
                if existing is not None:
                    db.execute("UPDATE bible_facts SET status='superseded',updated_at=? WHERE id=?",
                               (timestamp(),existing["id"]))
            elif replaces_fact_id is not None:
                raise ValueError("Rejected facts cannot supersede accepted facts")
            db.execute("UPDATE bible_facts SET status=?,updated_at=? WHERE id=?",
                       ("accepted" if decision=="accept" else "rejected",timestamp(),fact_id))
            if decision=="accept":
                db.execute("INSERT INTO bible_changes VALUES (?,?,?,?,?,?,?)",
                           (uuid.uuid4().hex,project_id,fact["entity_id"],fact_id,
                            existing["id"] if existing is not None else None,None,timestamp()))
            self._touch(db,fact["entity_id"])
        return self.get_fact(project_id,fact_id)

    def link_scene(self, project_id: str, entity_id: str, scene_id: str,
                   expected_entity_revision: int, note: str = "") -> dict:
        note=checked_text(note,1000,"scene link note",required=False)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            entity=self._entity(db,project_id,entity_id)
            self._require_revision(entity,expected_entity_revision)
            project=self._project(db,project_id)
            scene=next((s for s in parse_screenplay(project["screenplay"]) if s["id"]==scene_id),None)
            if scene is None: raise KeyError("Scene is not present in the current screenplay")
            link=db.execute("SELECT id FROM bible_scene_links WHERE project_id=? AND entity_id=? AND scene_id=?",
                            (project_id,entity_id,scene_id)).fetchone()
            link_id=link["id"] if link else uuid.uuid4().hex
            stamp=timestamp()
            if link:
                db.execute("UPDATE bible_scene_links SET scene_heading=?,scene_sha=?,screenplay_revision=?,"
                           "note=?,updated_at=? WHERE id=?",
                           (scene["heading"],sha_scene(scene),project["revision"],note,stamp,link_id))
            else:
                db.execute("INSERT INTO bible_scene_links VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (link_id,project_id,entity_id,scene_id,scene["heading"],sha_scene(scene),
                            project["revision"],note,stamp,stamp))
            self._touch(db,entity_id)
        return self.get_entity(project_id,entity_id)

    def acknowledge_change(self, project_id: str, change_id: str, expected_screenplay_revision: int):
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            project=self._project(db,project_id)
            if project["revision"]!=expected_screenplay_revision:
                raise RuntimeError("Screenplay changed; reopen the impact report")
            result=db.execute("UPDATE bible_changes SET reviewed_revision=? WHERE project_id=? AND id=? "
                              "AND reviewed_revision IS NULL",
                              (project["revision"],project_id,change_id))
            if result.rowcount!=1: raise RuntimeError("Change already reviewed or not in project")
        return {"id":change_id,"reviewed_revision":expected_screenplay_revision}

    def get_entity(self, project_id: str, entity_id: str) -> dict:
        with self.studio._connection() as db:
            row=self._entity(db,project_id,entity_id)
            return self._hydrate(db,dict(row))

    @staticmethod
    def _hydrate(db, row):
        entity_id=row["id"]
        row["aliases"]=[r["display_name"] for r in db.execute(
            "SELECT display_name FROM bible_names WHERE entity_id=? AND is_primary=0 ORDER BY display_name",
            (entity_id,)).fetchall()]
        row["facts"]=[dict(r) for r in db.execute("SELECT * FROM bible_facts WHERE entity_id=? ORDER BY created_at,id",
                                                   (entity_id,)).fetchall()]
        row["scene_links"]=[dict(r) for r in db.execute("SELECT * FROM bible_scene_links WHERE entity_id=? ORDER BY created_at,id",
                                                        (entity_id,)).fetchall()]
        return row

    def list_entities(self, project_id: str) -> list[dict]:
        with self.studio._connection() as db:
            self._project(db,project_id)
            rows=db.execute("SELECT * FROM bible_entities WHERE project_id=? ORDER BY kind,name,id",
                            (project_id,)).fetchall()
            return [self._hydrate(db,dict(row)) for row in rows]

    def report(self, project_id: str) -> dict:
        """Conservative exact-match report, not a neural/semantic truth claim."""
        with self.studio._connection() as db:
            project=self._project(db,project_id)
            scenes={s["id"]:s for s in parse_screenplay(project["screenplay"])}
            all_shots=db.execute("SELECT scene_id,shot_id,status FROM shots WHERE project_id=?",
                                 (project_id,)).fetchall()
            shots_by_scene={}
            for shot in all_shots:
                shots_by_scene.setdefault(shot["scene_id"],[]).append(dict(shot))
            entities=self.list_entities(project_id)
            issues=[]
            for entity in entities:
                for link in entity["scene_links"]:
                    current=scenes.get(link["scene_id"])
                    status=("scene_removed" if current is None else
                            "scene_changed" if sha_scene(current)!=link["scene_sha"] else "current")
                    if status != "current":
                        issues.append({"type":status,"entity_id":entity["id"],"entity_name":entity["name"],
                                       "scene_id":link["scene_id"],"stored_heading":link["scene_heading"],
                                       "current_heading":current["heading"] if current else None,
                                       "shot_ids":[s["shot_id"] for s in shots_by_scene.get(link["scene_id"],[])]})
                active={(f["fact_key"],f["story_scope"]):f for f in entity["facts"] if f["status"]=="accepted"}
                for proposed in (f for f in entity["facts"] if f["status"]=="proposed"):
                    previous=active.get((proposed["fact_key"],proposed["story_scope"]))
                    if previous and previous["fact_value"]!=proposed["fact_value"]:
                        issues.append({"type":"proposed_fact_conflict","entity_id":entity["id"],
                                       "entity_name":entity["name"],"fact_id":proposed["id"],
                                       "accepted_fact_id":previous["id"],"key":proposed["fact_key"],
                                       "scope":proposed["story_scope"]})
            changes=[dict(r) for r in db.execute("SELECT * FROM bible_changes WHERE project_id=? "
                                                 "ORDER BY created_at,id",(project_id,)).fetchall()]
            for change in changes:
                # Explicitly acknowledged updates are still kept as audit records, not alerts.
                if change["reviewed_revision"] is not None: continue
                entity=next(e for e in entities if e["id"]==change["entity_id"])
                references=[{"scene_id":link["scene_id"],
                             "shot_ids":[s["shot_id"] for s in shots_by_scene.get(link["scene_id"],[])]}
                            for link in entity["scene_links"]]
                issues.append({"type":"canon_change_impact","change_id":change["id"],
                               "entity_id":entity["id"],"entity_name":entity["name"],
                               "new_fact_id":change["new_fact_id"],"old_fact_id":change["old_fact_id"],
                               "affected_scenes":references})
            return {"project_id":project_id,"screenplay_revision":project["revision"],
                    "entity_count":len(entities),"issues":issues,
                    "unreviewed_count":len(issues),"changes":changes,
                    "limitations":"Exact approved fact slots and manually linked scenes only; not semantic screenplay analysis"}
