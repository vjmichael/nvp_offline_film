"""FILM03-02: canonical project-scoped ActorID and source-verified production Bible.

ONE canonical ActorID = an existing StoryBible character entity ID (stable
over rename, script change, actor recast or outfit revision). Nothing is copied
into a competing character database.

Relationships to dialogue, scene, props, wardrobe, models, meshes, textures,
rigs, recorded voice, performances and frozen Takes are exact-version,
SHA-pinned append-only records. Replacing/removing a relationship adds a new
history entry; no source, old link, audio or Take is overwritten.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_story_bible import StoryBible, sha_scene
from backend.nvp_studio import Studio
from backend.nvp_openusd_scene import OpenUSDSceneBridge

FORMAT = "nvp.film03.production_bible_actor_links.v1"
MAX_ACTORS = 10000
MAX_LINKS = 1024
MAX_NOTE = 1200
SHA = re.compile(r"[a-f0-9]{64}\Z")
PRIM = re.compile(r"/World(?:/[A-Za-z_][A-Za-z0-9_]*){1,12}\Z")
ROLE_FAMILIES = {
    "scene": {"screenplay_scene", "filmindex"},
    "dialogue": {"filmindex"},
    "performance": {"filmindex"},
    "voice": {"filmindex"},
    "wardrobe": {"bible_prop", "filmindex"},
    "prop": {"bible_prop", "filmindex"},
    "model": {"filmindex"},
    "mesh": {"filmindex"},
    "texture": {"filmindex"},
    "rig": {"filmindex"},
    "take": {"filmindex"},
    "actor_prim": {"filmindex"},
}
FILM_KINDS = {
    "scene": {"scene"},
    "dialogue": {"dialogue"},
    "performance": {"performance"},
    "voice": {"audio"},
    "wardrobe": {"asset", "prop"},
    "prop": {"asset", "prop"},
    "model": {"asset"},
    "mesh": {"asset"},
    "texture": {"asset"},
    "rig": {"asset"},
    "take": {"take"},
    "actor_prim": {"take"},
}


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def _sha(obj):
    return hashlib.sha256(_canon(obj)).hexdigest()


def _scope(value, field="scope", maximum=120):
    if type(value) is not str or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError("Invalid actor production " + field)
    return value.strip()


class ProductionBibleActors:
    def __init__(self, studio: Studio):
        if not isinstance(studio, Studio):
            raise TypeError("Existing NVP Studio must own the actor registry")
        self.studio = studio
        self.bible = StoryBible(studio)
        self.index = FilmIndex(studio)
        with studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS nvp_bible_actor_links (
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              actor_id TEXT NOT NULL REFERENCES bible_entities(id),
              link_id TEXT NOT NULL,
              link_revision INTEGER NOT NULL CHECK(link_revision > 0),
              actor_bible_revision INTEGER NOT NULL,
              role TEXT NOT NULL,
              source_family TEXT NOT NULL,
              target_id TEXT NOT NULL,
              target_revision INTEGER NOT NULL,
              source_sha256 TEXT NOT NULL,
              source_snapshot_json TEXT NOT NULL,
              actor_prim_path TEXT,
              production_scope TEXT NOT NULL,
              director_note TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('active','retired')),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(project_id,actor_id,link_id,link_revision)
            );
            CREATE INDEX IF NOT EXISTS nvp_bible_actor_links_by_actor
              ON nvp_bible_actor_links(project_id,actor_id,role,link_id,link_revision);
            """)

    def _actor(self, project_id, actor_id):
        _require_pid(project_id)
        # A canonically stable production ActorID IS the existing StoryBible
        # character ID. There must be no independent random ActorID that could
        # accidentally refer to a different character in a second registry.
        actor = self.bible.get_entity(project_id, actor_id)
        if actor["kind"] != "character":
            raise PermissionError("Only a StoryBible character can be a cast ActorID")
        return actor

    def catalog(self, project_id):
        _require_pid(project_id)
        self.studio.get_project(project_id)
        film = []
        for item in self.index.list_objects(project_id):
            if item["kind"] not in {
                    "scene", "dialogue", "performance", "audio", "asset", "prop", "take"}:
                continue
            rec = self.index.read_revision(
                project_id, item["object_id"], item["head_revision"])
            film.append({
                "family": "filmindex", "target_id": item["object_id"],
                "target_revision": item["head_revision"],
                "kind": item["kind"], "sha256": rec["document_sha256"],
            })
        props = [
            {"family": "bible_prop", "target_id": e["id"],
             "target_revision": e["revision"], "kind": "prop",
             "name": e["name"]}
            for e in self.bible.list_entities(project_id)
            if e["kind"] == "prop"
        ]
        project = self.studio.get_project(project_id)
        scenes = [
            {"family": "screenplay_scene", "target_id": s["id"],
             "target_revision": project["revision"], "kind": "scene",
             "name": s["heading"], "sha256": sha_scene(s)}
            for s in project["scenes"]
        ]
        return {
            "format": FORMAT, "project_id": project_id,
            "actors": [{"actor_id": e["id"], "name": e["name"],
                        "bible_revision": e["revision"]}
                       for e in self.bible.list_entities(project_id)
                       if e["kind"] == "character"],
            "sources": scenes + props + film,
            "supported_roles": sorted(ROLE_FAMILIES),
            "source_revision_verified": True,
            "model_mesh_texture_roles_do_not_claim_rendered_or_license_approved": True,
        }

    def _target(self, project_id, role, family, oid, revision, prim):
        if role not in ROLE_FAMILIES or family not in ROLE_FAMILIES[role]:
            raise ValueError("Invalid typed actor resource/role combination")
        if type(revision) is not int or revision < 0:
            raise ValueError("Expected exact actor source revision")
        if prim is not None:
            if role != "actor_prim" or not PRIM.fullmatch(prim):
                raise ValueError("Only an authentic OpenUSD actor binding accepts a prim path")
        elif role == "actor_prim":
            raise ValueError("An authored OpenUSD actor prim path is required")
        if family == "screenplay_scene":
            project = self.studio.get_project(project_id)
            if revision != project["revision"]:
                raise RuntimeError("Script changed: refresh exact scene reference")
            scene = next((s for s in project["scenes"] if s["id"] == oid), None)
            if scene is None:
                raise KeyError("Scene no longer exists in the selected screenplay revision")
            snapshot = {
                "scene_id": oid, "screenplay_revision": revision,
                "scene_heading": scene["heading"], "scene_sha256": sha_scene(scene),
            }
            return _sha(snapshot), snapshot
        if family == "bible_prop":
            ent = self.bible.get_entity(project_id, oid)
            if ent["kind"] != "prop" or ent["revision"] != revision:
                raise RuntimeError("Production prop revision changed or identity invalid")
            # Snapshot the full editable StoryBible prop source; its old
            # revision may not have an independent FilmIndex document yet.
            snapshot = {
                "entity_id": ent["id"], "kind": "prop",
                "entity_revision": ent["revision"], "name": ent["name"],
                "aliases": ent["aliases"], "facts": ent["facts"],
            }
            return _sha(snapshot), snapshot
        if family == "filmindex":
            if revision < 1:
                raise ValueError("FilmIndex source requires exact positive revision")
            _id(oid, "FilmIndex resource")
            rec = self.index.read_revision(project_id, oid, revision)
            if rec["kind"] not in FILM_KINDS[role]:
                raise PermissionError("Source resource type disagrees with actor link role")
            if role == "actor_prim":
                take = rec["data"]
                if take.get("frozen") is not True:
                    raise PermissionError("Only a frozen original Take binds a scene actor")
                scene, _ = OpenUSDSceneBridge(self.index).open(
                    project_id, take["scene_id"], take["scene_revision"])
                if scene["data"]["prim_roles"].get(prim) != "actor":
                    raise PermissionError("Target OpenUSD prim is not an actor in frozen Take")
                if scene["document_sha256"] != take["scene_document_sha256"]:
                    raise RuntimeError("Actual OpenUSD scene source changed")
            snapshot = {
                "object_id": oid, "kind": rec["kind"], "revision": revision,
                "document_sha256": rec["document_sha256"],
                "actor_prim_path": prim,
            }
            return rec["document_sha256"], snapshot
        raise ValueError("Unknown production actor source family")

    def link(self, project_id, actor_id, *, role, source_family, target_id,
             target_revision, expected_actor_revision, production_scope="global",
             director_note="", actor_prim_path=None, link_id=None,
             expected_link_revision=0):
        actor = self._actor(project_id, actor_id)
        if (type(expected_actor_revision) is not int or
                expected_actor_revision != actor["revision"]):
            raise RuntimeError("StoryBible ActorID changed; refresh before linking")
        if (type(expected_link_revision) is not int or expected_link_revision < 0):
            raise ValueError("Exact expected actor relationship revision required")
        scope = _scope(production_scope)
        if type(director_note) is not str or len(director_note) > MAX_NOTE:
            raise ValueError("Actor relationship note is too long")
        sha, snapshot = self._target(
            project_id, role, source_family, target_id,
            target_revision, actor_prim_path)
        lid = link_id if link_id is not None else uuid.uuid4().hex
        if type(lid) is not str or not re.fullmatch(r"[a-f0-9]{32}", lid):
            raise ValueError("Stable relationship identity must be 32 lowercase hex characters")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT kind,revision FROM bible_entities WHERE project_id=? AND id=?",
                (project_id,actor_id)).fetchone()
            if (not current or current["kind"] != "character" or
                    current["revision"] != expected_actor_revision):
                raise RuntimeError("Actor changed concurrently; don't replace earlier work")
            previous = db.execute("""SELECT role,link_revision FROM nvp_bible_actor_links
                WHERE project_id=? AND actor_id=? AND link_id=?
                ORDER BY link_revision DESC LIMIT 1""",
                (project_id,actor_id,lid)).fetchone()
            prev_rev = previous["link_revision"] if previous else 0
            if prev_rev != expected_link_revision:
                raise RuntimeError("Actor resource link changed concurrently")
            if previous and previous["role"] != role:
                raise ValueError("An existing relationship cannot change its category")
            count = db.execute("""SELECT COUNT(DISTINCT link_id) FROM nvp_bible_actor_links
                WHERE project_id=? AND actor_id=?""", (project_id,actor_id)).fetchone()[0]
            if count >= MAX_LINKS and previous is None:
                raise ValueError("Actor link limit reached; use project asset catalog")
            new_revision = prev_rev + 1
            db.execute("""INSERT INTO nvp_bible_actor_links
                (project_id,actor_id,link_id,link_revision,actor_bible_revision,
                role,source_family,target_id,target_revision,source_sha256,
                source_snapshot_json,actor_prim_path,production_scope,director_note,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id,actor_id,lid,new_revision,expected_actor_revision+1,
                 role,source_family,target_id,target_revision,sha,
                 _canon(snapshot).decode("ascii"),actor_prim_path,scope,
                 director_note,"active"))
            db.execute("""UPDATE bible_entities SET revision=revision+1,
                updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND id=? AND revision=?""",
                (project_id,actor_id,expected_actor_revision))
        return self.actor(project_id, actor_id)

    def retire(self, project_id, actor_id, link_id, *, expected_actor_revision,
               expected_link_revision, reason):
        self._actor(project_id, actor_id)
        if type(reason) is not str or not reason.strip() or len(reason)>MAX_NOTE:
            raise ValueError("Director must explain a non-destructive actor link retirement")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            owner = db.execute(
                "SELECT revision,kind FROM bible_entities WHERE project_id=? AND id=?",
                (project_id,actor_id)).fetchone()
            if (owner is None or owner["kind"] != "character" or
                    owner["revision"] != expected_actor_revision):
                raise RuntimeError("Actor changed during source link retirement")
            row = db.execute("""SELECT * FROM nvp_bible_actor_links
                WHERE project_id=? AND actor_id=? AND link_id=?
                ORDER BY link_revision DESC LIMIT 1""",
                (project_id,actor_id,link_id)).fetchone()
            if row is None:
                raise KeyError("No linked actor resource")
            if (row["link_revision"] != expected_link_revision or
                    row["status"] != "active"):
                raise RuntimeError("Link changed or already retired; reload before applying")
            db.execute("""INSERT INTO nvp_bible_actor_links
                (project_id,actor_id,link_id,link_revision,actor_bible_revision,
                role,source_family,target_id,target_revision,source_sha256,
                source_snapshot_json,actor_prim_path,production_scope,director_note,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id,actor_id,link_id,expected_link_revision+1,
                 expected_actor_revision+1,row["role"],row["source_family"],
                 row["target_id"],row["target_revision"],row["source_sha256"],
                 row["source_snapshot_json"],row["actor_prim_path"],
                 row["production_scope"],reason.strip(),"retired"))
            db.execute("""UPDATE bible_entities SET revision=revision+1,
                updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND id=? AND revision=?""",
                (project_id,actor_id,expected_actor_revision))
        return self.actor(project_id,actor_id)

    def actor(self, project_id, actor_id):
        actor = self._actor(project_id, actor_id)
        with self.studio._connection() as db:
            history = [dict(row) for row in db.execute(
                """SELECT * FROM nvp_bible_actor_links
                WHERE project_id=? AND actor_id=?
                ORDER BY role,link_id,link_revision""",
                (project_id,actor_id))]
        by_id = {}
        for row in history:
            row["source_snapshot"] = json.loads(row.pop("source_snapshot_json"))
            by_id[row["link_id"]] = row
        current = sorted((row for row in by_id.values() if row["status"] == "active"),
                         key=lambda r:(r["role"],r["link_id"]))
        return {
            "format": FORMAT,
            "project_id": project_id, "actor_id": actor["id"],
            "actor_name": actor["name"], "bible_revision": actor["revision"],
            "aliases": actor["aliases"], "production_bible_entity_id": actor["id"],
            "character_canon_revision": actor["revision"],
            "active_links": current, "history": history,
            "all_relations_versioned_not_destroyed": True,
            "source_actor_id_stable_across_recast_rename_script_change": True,
            "asset_link_is_not_material_license_or_render_acceptance": True,
        }
