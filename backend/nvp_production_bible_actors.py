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
from backend.nvp_studio import Studio, parse_screenplay
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
    "wardrobe": {"bible_prop", "filmindex", "mesh_glb", "rigged_glb"},
    "prop": {"bible_prop", "filmindex", "mesh_glb"},
    "model": {"filmindex", "mesh_glb", "rigged_glb"},
    "mesh": {"filmindex", "mesh_glb", "rigged_glb"},
    "texture": {"filmindex", "texture_blob"},
    "rig": {"filmindex", "rigged_glb"},
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
                "sample_count": (rec["data"].get("sample_count")
                                 if item["kind"]=="audio" else None),
            })
        props = [
            {"family": "bible_prop", "target_id": e["id"],
             "target_revision": e["revision"], "kind": "prop",
             "name": e["name"]}
            for e in self.bible.list_entities(project_id)
            if e["kind"] == "prop"
        ]
        # Already imported NVP GLB asset catalogs are also authoritative.
        # Their immutable content-addressed original blobs must still be
        # reverified when a director creates a canonical ActorID relation.
        from backend.nvp_mesh_assets import MeshAssets
        from backend.nvp_character_assets import CharacterAssets
        imported = [
            {"family": "mesh_glb", "target_id": row["asset_id"],
             "target_revision": 1, "kind": "asset",
             "sha256": row["sha256"], "name": row["asset_id"]}
            for row in MeshAssets(self.studio).list(project_id)
        ] + [
            {"family": "rigged_glb", "target_id": row["asset_id"],
             "target_revision": 1, "kind": "asset",
             "sha256": row["sha256"], "name": row["asset_id"]}
            for row in CharacterAssets(self.studio).list(project_id)
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
            "sources": scenes + props + film + imported,
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
        if family in ("mesh_glb", "rigged_glb"):
            if revision != 1:
                raise ValueError("Original imported GLB identity has immutable revision 1")
            if type(oid) is not str or not oid.strip() or len(oid) > 120:
                raise ValueError("Invalid original imported GLB asset ID")
            from backend.nvp_mesh_assets import MeshAssets
            from backend.nvp_character_assets import CharacterAssets
            source = (MeshAssets(self.studio) if family == "mesh_glb"
                      else CharacterAssets(self.studio))
            entry = next((x for x in source.list(project_id)
                          if x["asset_id"] == oid), None)
            if entry is None:
                raise KeyError("Imported GLB asset does not exist in this project")
            digest = entry["sha256"]
            blob = source.root / (digest + ".glb")
            if (not blob.is_file() or blob.is_symlink() or
                    hashlib.sha256(blob.read_bytes()).hexdigest() != digest):
                raise PermissionError("Imported GLB original bytes no longer match catalog SHA")
            snapshot = {
                "source_family": family, "asset_id": oid, "revision": 1,
                "original_blob_sha256": digest,
                "license": entry.get("license"),
                "attribution": entry.get("attribution"),
                "source": entry.get("source"),
                "redistribution_legally_approved": False,
            }
            return digest, snapshot
        if family == "texture_blob":
            if role != "texture" or revision != 1 or (
                    type(oid) is not str or not SHA.fullmatch(oid)):
                raise ValueError("Exact source texture SHA and immutable revision 1 required")
            from backend.nvp_native_usd_texture import decode_png
            original = self.index.get_blob(project_id, oid)
            width, height, _ = decode_png(original)
            snapshot = {
                "format": "nvp.original.usd_texture_png.v1",
                "original_blob_sha256": oid, "revision": 1,
                "pixel_width": width, "pixel_height": height,
                "source_material_reauthored": False,
                "license_approved": False,
            }
            return oid, snapshot
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

    @staticmethod
    def _source_guard_in_actor_transaction(db, pid, family, oid, revision,
                                           sha, snapshot):
        """No nested schema-writing registry initialization under write lease."""
        if family == "screenplay_scene":
            row = db.execute(
                "SELECT screenplay,revision FROM projects WHERE id=?", (pid,)
            ).fetchone()
            if row is None or row["revision"] != revision:
                raise RuntimeError("Screenplay changed during ActorID source approval")
            scene = next((s for s in parse_screenplay(row["screenplay"])
                          if s["id"] == oid), None)
            if (scene is None or sha_scene(scene) != snapshot["scene_sha256"]
                    or _sha(snapshot) != sha):
                raise RuntimeError("Screenplay scene differs from approved ActorID source")
        elif family == "bible_prop":
            row = db.execute(
                "SELECT kind,revision FROM bible_entities WHERE id=? AND project_id=?",
                (oid,pid)).fetchone()
            if row is None or row["kind"] != "prop" or row["revision"] != revision:
                raise RuntimeError("Original production prop changed during ActorID link")
        elif family == "filmindex":
            row = db.execute(
                "SELECT document_sha FROM film_object_revisions WHERE "
                "project_id=? AND object_id=? AND revision=?",
                (pid,oid,revision)).fetchone()
            if row is None or row["document_sha"] != sha:
                raise RuntimeError("Immutable FilmIndex source changed while linking actor")
        elif family in ("mesh_glb","rigged_glb"):
            table = ("prod_mesh_bindings" if family=="mesh_glb"
                     else "prod_character_assets")
            row = db.execute(
                "SELECT " + ("sha256" if family=="mesh_glb" else "sha") +
                " AS digest FROM " + table +
                " WHERE project_id=? AND asset_id=?", (pid,oid)).fetchone()
            if row is None or row["digest"] != sha:
                raise RuntimeError("Real imported GLB source identity changed")
        elif family == "texture_blob":
            # FilmIndex's content-addressed blob is checked through
            # get_blob/PNG decoder before this transaction; SHA cannot be
            # reassigned under a different ID by a project editor.
            if sha != oid or snapshot["original_blob_sha256"] != sha:
                raise RuntimeError("Texture source SHA changed")
        else:
            raise ValueError("Unknown original actor source family")

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
            # Re-read the source identity while holding the actor's SQLite
            # write lease. A screenplay/StoryBible revision cannot slip in
            # between preflight and durable relationship creation.
            self._source_guard_in_actor_transaction(
                db, project_id, source_family, target_id, target_revision,
                sha, snapshot)
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

    def casting_coverage(self, project_id, take_id):
        """Audit EVERY authored OpenUSD actor against canonical Bible ActorIDs.

        No automatic fake character creation: an actor in a source Take must
        be manually cast/linked and signed off as an actual Bible character.
        Uncast actors are visible and block full source-cast completeness.
        """
        _require_pid(project_id)
        _id(take_id, "real frozen scene Take")
        take = self.index.read_revision(project_id, take_id, 1)
        if take["kind"] != "take" or take["data"].get("frozen") is not True:
            raise PermissionError("Casting coverage requires a genuine frozen Digital Take")
        scene, _ = OpenUSDSceneBridge(self.index).open(
            project_id, take["data"]["scene_id"],
            take["data"]["scene_revision"])
        if scene["document_sha256"] != take["data"]["scene_document_sha256"]:
            raise PermissionError("Source actor prims differ from frozen Take")
        paths = sorted(path for path, role in scene["data"]["prim_roles"].items()
                       if role == "actor")
        if not paths:
            raise ValueError("No castable OpenUSD actors in source")
        assignments = {}
        with self.studio._connection() as db:
            last = db.execute("""
                SELECT a.actor_id,a.actor_prim_path,a.source_sha256,a.status
                  FROM nvp_bible_actor_links a
                  JOIN (SELECT actor_id,link_id,MAX(link_revision) revision
                          FROM nvp_bible_actor_links WHERE project_id=?
                            AND role='actor_prim' AND source_family='filmindex'
                            AND target_id=? AND target_revision=1
                         GROUP BY actor_id,link_id) latest
                    ON latest.actor_id=a.actor_id
                   AND latest.link_id=a.link_id
                   AND latest.revision=a.link_revision
                 WHERE a.project_id=? AND a.role='actor_prim'
                   AND a.target_id=? AND a.target_revision=1
                """, (project_id,take_id,project_id,take_id)).fetchall()
            for row in last:
                if row["status"] != "active":
                    continue
                if row["source_sha256"] != take["document_sha256"]:
                    raise RuntimeError("Cast member link has wrong source Take SHA")
                canonical = db.execute("""
                    SELECT kind FROM bible_entities WHERE id=? AND project_id=?""",
                    (row["actor_id"],project_id)).fetchone()
                if not canonical or canonical["kind"] != "character":
                    raise RuntimeError("Source cast points to a non-character Bible entry")
                assignments.setdefault(row["actor_prim_path"],set()).add(row["actor_id"])
        if any(path not in paths for path in assignments):
            raise RuntimeError("Stored actor link addresses an absent native prim")
        ambiguous = {p:sorted(ids) for p,ids in assignments.items() if len(ids)>1}
        missing = [p for p in paths if p not in assignments]
        return {
            "format": "nvp.film03.production_bible_actor_cast_coverage.v1",
            "project_id": project_id, "take_id": take_id,
            "take_sha256": take["document_sha256"],
            "source_scene_sha256": scene["document_sha256"],
            "authored_actor_prims": paths,
            "actor_id_by_prim": {p:next(iter(ids)) for p,ids in assignments.items()
                                 if len(ids)==1},
            "uncast_prim_paths": missing,
            "ambiguous_prim_bindings": ambiguous,
            "complete": not missing and not ambiguous,
            "all_actor_ids_in_authoritative_story_bible": True,
            "automatic_casting_or_recasting": False,
        }

    def require_complete_cast(self, project_id, take_id):
        proof = self.casting_coverage(project_id,take_id)
        if not proof["complete"]:
            raise RuntimeError("Cannot accept scene cast with missing/ambiguous StoryBible ActorIDs")
        return proof

    def audit_actor_asset_package(self, project_id, actor_id, *, take_id=None,
                                  performance_id=None):
        """Read every current ActorID resource source, not only its labels.

        A reused generic mesh or shared prop is not necessarily an identity
        violation; relationships are per-ActorID, while actual actor casting,
        recorded voice approval and script binding have stricter ownership.
        Stale but immutable source revisions remain as history and trigger
        a director review, not destructive relinking.
        """
        self._actor(project_id,actor_id)
        current=self.actor(project_id,actor_id)
        details=[]
        failures=[]
        needs_review=[]
        for link in current["active_links"]:
            item={
                "link_id":link["link_id"],
                "link_revision":link["link_revision"],
                "actor_id":actor_id,"role":link["role"],
                "source_family":link["source_family"],
                "source_id":link["target_id"],
                "source_revision":link["target_revision"],
                "recorded_sha256":link["source_sha256"],
                "source_verified_now":False,
                "historical_source_preserved":True,
                "needs_director_review":bool(
                    link.get("needs_director_source_review")),
            }
            if item["needs_director_review"]:
                needs_review.append({
                    "link_id":item["link_id"],"role":item["role"],
                    "reason":"Source head changed; historical link cannot be silently updated"})
            else:
                try:
                    sha,_=self._target(
                        project_id,link["role"],link["source_family"],
                        link["target_id"],link["target_revision"],
                        link["actor_prim_path"])
                    if sha!=link["source_sha256"]:
                        raise RuntimeError("Saved ActorID source SHA disagrees with original bytes")
                    item["source_verified_now"]=True
                except (KeyError,ValueError,PermissionError,RuntimeError,OSError) as exc:
                    failures.append({
                        "link_id":item["link_id"],"role":item["role"],
                        "reason":"Verified original asset source missing/changed",
                        "error_kind":type(exc).__name__,
                    })
            details.append(item)
        casting=None
        if take_id is not None:
            casting=self.casting_coverage(project_id,take_id)
            if (not casting["complete"] or
                    actor_id not in casting["actor_id_by_prim"].values()):
                failures.append({
                    "role":"actor_prim","link_id":None,
                    "reason":"This ActorID is not unambiguously cast into the real source Take",
                })
        voice=None
        if performance_id is not None:
            from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity
            voice=ProductionBibleVoiceIdentity(
                self.index,verify_creator_action=lambda *_:False
            ).verify_delivery(
                project_id,actor_id,performance_id,require_current_cast=True)
            perf=self.index.read_revision(project_id,performance_id,1)["data"]
            required_links=(
                ("performance",performance_id,1),
                ("dialogue",perf["script_id"],perf["script_revision"]),
                ("voice",voice["original_audio_id"],voice["original_audio_revision"]),
            )
            for role,oid,rev in required_links:
                if not any(x["role"]==role and
                           x["source_family"]=="filmindex" and
                           x["target_id"]==oid and
                           x["target_revision"]==rev and
                           x["source_verified_now"] for x in details):
                    failures.append({
                        "role":role,"link_id":None,
                        "reason":"Approved voice delivery lacks this ActorID's active verified original source link",
                    })
            # The VoiceID only authorizes a candidate source; final speech
            # still needs the exact scripted selection/time in dialogue router.
        elif current["current_voice_identity"] is None:
            needs_review.append({
                "role":"voice","link_id":None,
                "reason":"ActorID has no approved current VoiceID; generic audio asset link is not voice identity"})
        result={
            "format":"nvp.film03.actor_asset_source_audit.v1",
            "project_id":project_id,"actor_id":actor_id,
            "actor_bible_revision":current["bible_revision"],
            "all_current_sources_physically_verified":
                not failures and not needs_review and bool(details),
            "links":[*details],
            "source_failures":failures,
            "director_review_required":needs_review,
            "source_take_casting":casting,
            "approved_voice_take":voice,
            "current_voice_id":(
                current["current_voice_identity"]["voice_id"]
                if current["current_voice_identity"] else None),
            "generic_voice_source_not_identity_approval":True,
            "cross_actor_generic_prop_reuse_not_automatically_forbidden":True,
            "acoustic_timbre_same_speaker_not_machine_proven":True,
            "no_assets_or_takes_modified":True,
            "effect":"read_only_verified_actor_package",
        }
        return result

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
        # Audit whether a historically valid source link still follows the
        # current screenplay/Bible revision. A stale link is never deleted or
        # silently remapped to the newly written scene or costume.
        screenplay = self.studio.get_project(project_id)
        for entry in current:
            family = entry["source_family"]
            needs_review = False
            if family == "screenplay_scene":
                source = next((s for s in screenplay["scenes"]
                               if s["id"] == entry["target_id"]), None)
                needs_review = (
                    source is None or
                    entry["target_revision"] != screenplay["revision"] or
                    source is not None and sha_scene(source) !=
                    entry["source_snapshot"]["scene_sha256"])
            elif family == "bible_prop":
                try:
                    source = self.bible.get_entity(project_id, entry["target_id"])
                    needs_review = source["revision"] != entry["target_revision"]
                except KeyError:
                    needs_review = True
            elif family == "filmindex":
                try:
                    source = self.index.read_revision(
                        project_id, entry["target_id"])
                    needs_review = source["revision"] != entry["target_revision"]
                except KeyError:
                    needs_review = True
            entry["needs_director_source_review"] = bool(needs_review)
            entry["historical_original_link_retained"] = True
        # The voice registry belongs to the SAME production Bible actor,
        # and is independent of per-recording "voice" asset links. A source
        # WAV link alone never establishes a consistent character VoiceID.
        with self.studio._connection() as db:
            voice_table=db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='nvp_bible_voice_casts'").fetchone()
            voice_history=([dict(x) for x in db.execute(
                """SELECT * FROM nvp_bible_voice_casts
                   WHERE project_id=? AND actor_id=?
                   ORDER BY cast_revision""", (project_id, actor_id))]
                if voice_table else [])
        with self.studio._connection() as db:
            identity_table=db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='nvp_bible_actor_identity_profiles'").fetchone()
            identity_history=([dict(x) for x in db.execute(
                """SELECT actor_id,profile_revision,document_sha256,
                          profile_json,voice_id,voice_cast_revision,
                          voice_reference_sha256,source_bible_revision,
                          director_note,created_at
                   FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=?
                   ORDER BY profile_revision""",(project_id,actor_id))]
                if identity_table else [])
        for identity in identity_history:
            identity["profile"]=json.loads(identity.pop("profile_json"))
        return {
            "format": FORMAT,
            "project_id": project_id, "actor_id": actor["id"],
            "current_identity_profile": (
                identity_history[-1] if identity_history else None),
            "immutable_identity_profile_history": identity_history,
            "appearance_behavior_movement_voice_type_share_canonical_actorid": True,
            "current_voice_identity": (voice_history[-1] if voice_history else None),
            "immutable_voice_cast_history": voice_history,
            "audio_asset_link_alone_cannot_approve_actors_voice": True,
            "actor_name": actor["name"], "bible_revision": actor["revision"],
            "aliases": actor["aliases"], "production_bible_entity_id": actor["id"],
            "character_canon_revision": actor["revision"],
            "active_links": current, "history": history,
            "all_relations_versioned_not_destroyed": True,
            "source_actor_id_stable_across_recast_rename_script_change": True,
            "asset_link_is_not_material_license_or_render_acceptance": True,
        }
