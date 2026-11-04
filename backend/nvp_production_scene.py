"""NVP-PROD-01: deterministic 3D scene staging and durable director-approved proxy layouts.

No LLM, Blender subprocess, external asset download, network, or Lu dependency.
The solver uses bounded deterministic backtracking on a 0.5m grid plus exact
wall/anchor seeds. Every layout is checked again by an independent validator.
All dimensions are metres, Z is up, and collision checks use conservative XY
footprint boxes (no articulated mesh or physics simulation is implied).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import re
import uuid

from backend.nvp_studio import Studio, parse_screenplay

NAME = re.compile(r"[\w][\w .,'()\-]{0,149}\Z", re.UNICODE)
INSTANCE_ID = re.compile(r"[a-zA-Z][a-zA-Z0-9_:-]{0,63}\Z")
ANCHOR = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
CATEGORIES = frozenset({"character", "furniture", "prop", "set_piece"})
WALLS = frozenset({"north", "south", "east", "west"})
ROTATIONS = (0, 90, 180, 270)
CLEARANCE = 0.1
MARGIN = 0.1
GRID = 0.5
MAX_INSTANCES = 18
MAX_NODES = 100000
MAX_CANDIDATES = 5000


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(compact(value).encode("utf-8")).hexdigest()


def positive(value, key: str, lo: float = 0.1, hi: float = 40.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} must be a finite number")
    if not lo <= value <= hi:
        raise ValueError(f"{key} must be in [{lo}, {hi}] metres")
    return round(float(value), 4)


def check_vec(values, key: str, bounds: tuple[float, float] = (0.1, 40)) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"{key} must be a three-element XYZ vector")
    return [positive(x, key, *bounds) for x in values]


def validate_room(room: list) -> list[float]:
    dims = check_vec(room, "room dimensions", (2.0, 16.0))
    if dims[2] < 2.2 or dims[2] > 8.0:
        raise ValueError("room height must be between 2.2 and 8 metres")
    return dims


def validate_asset(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("asset must be a JSON object")
    name, category = spec.get("name"), spec.get("category")
    if not isinstance(name, str) or not NAME.fullmatch(name.strip()):
        raise ValueError("asset name is invalid")
    if category not in CATEGORIES:
        raise ValueError("unknown asset category")
    dimensions = check_vec(spec.get("dimensions"), "asset dimensions", (0.1, 12))
    anchors = spec.get("anchors", {})
    if not isinstance(anchors, dict) or len(anchors) > 24:
        raise ValueError("anchors must be an object of at most 24 named locations")
    clean_anchors = {}
    for key, coordinates in anchors.items():
        if not isinstance(key, str) or not ANCHOR.fullmatch(key):
            raise ValueError("invalid spatial-anchor name")
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 3:
            raise ValueError("spatial anchors must be XYZ offsets from the asset centre")
        point = []
        for index, coordinate in enumerate(coordinates):
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not math.isfinite(coordinate):
                raise ValueError("anchor offsets must be finite")
            limit = dimensions[index] / 2 if index < 2 else dimensions[2]
            if (abs(coordinate) if index < 2 else coordinate) < (-1e-9 if index < 2 else 0) or (abs(coordinate) if index < 2 else coordinate) > limit + 1e-9:
                raise ValueError("spatial anchor lies outside its proxy bounds")
            point.append(round(float(coordinate), 4))
        clean_anchors[key] = point
    license_note = spec.get("license", "creator_procedural")
    if not isinstance(license_note, str) or not 1 <= len(license_note) <= 200 or "\x00" in license_note:
        raise ValueError("invalid asset provenance")
    return {"name": name.strip(), "category": category, "dimensions": dimensions,
            "anchors": clean_anchors, "source_kind": "procedural_proxy", "license": license_note}


def rotate_xy(x: float, y: float, rotation: int) -> tuple[float, float]:
    if rotation == 0:
        return x, y
    if rotation == 90:
        return -y, x
    if rotation == 180:
        return -x, -y
    if rotation == 270:
        return y, -x
    raise ValueError("rotation must be cardinal")


def extents(asset: dict, rotation: int) -> tuple[float, float]:
    width, depth = asset["dimensions"][:2]
    return (width / 2, depth / 2) if rotation in (0, 180) else (depth / 2, width / 2)


def world_anchor(pose: dict, asset: dict, anchor_name: str) -> tuple[float, float, float]:
    if anchor_name not in asset["anchors"]:
        raise ValueError(f"Unknown anchor: {anchor_name}")
    ax, ay, az = asset["anchors"][anchor_name]
    rx, ry = rotate_xy(ax, ay, pose["rotation"])
    return pose["x"] + rx, pose["y"] + ry, az


def geometry_ok(pose: dict, asset: dict, room: list[float]) -> bool:
    hx, hy = extents(asset, pose["rotation"])
    return (pose["x"] - hx >= MARGIN - 1e-7 and pose["x"] + hx <= room[0] - MARGIN + 1e-7
            and pose["y"] - hy >= MARGIN - 1e-7 and pose["y"] + hy <= room[1] - MARGIN + 1e-7
            and asset["dimensions"][2] <= room[2] - 0.05 + 1e-7)


def collision(a: dict, aa: dict, b: dict, bb: dict) -> bool:
    ax, ay = extents(aa, a["rotation"])
    bx, by = extents(bb, b["rotation"])
    return (abs(a["x"] - b["x"]) < ax + bx + CLEARANCE - 1e-7
            and abs(a["y"] - b["y"]) < ay + by + CLEARANCE - 1e-7)


def check_relation(instance: dict, pose: dict, asset: dict, poses: dict, assets: dict, room: list[float]) -> bool:
    wall = instance.get("wall")
    if wall:
        hx, hy = extents(asset, pose["rotation"])
        d = {"north": room[1] - MARGIN - (pose["y"] + hy),
             "south": pose["y"] - hy - MARGIN,
             "east": room[0] - MARGIN - (pose["x"] + hx),
             "west": pose["x"] - hx - MARGIN}[wall]
        if not -1e-6 <= d <= 0.26:
            return False
    attachment = instance.get("attachment")
    if attachment:
        target = attachment["target_instance"]
        if target not in poses:
            return False
        current_anchor = world_anchor(pose, asset, attachment["self_anchor"])
        target_pose = poses[target]
        target_asset = assets[target_pose["asset_id"]]
        target_anchor = world_anchor(target_pose, target_asset, attachment["target_anchor"])
        if math.dist(current_anchor[:2], target_anchor[:2]) > attachment["max_gap"] + 1e-6:
            return False
    return True


def validate_instances(instances: list[dict], assets: dict) -> list[dict]:
    if not isinstance(instances, list) or len(instances) > MAX_INSTANCES:
        raise ValueError("scene must contain at most 18 instances")
    seen = set()
    for item in instances:
        if not isinstance(item, dict) or not isinstance(item.get("instance_id"), str) or not INSTANCE_ID.fullmatch(item["instance_id"]):
            raise ValueError("invalid scene instance ID")
        if item["instance_id"] in seen:
            raise ValueError("duplicate instance ID")
        seen.add(item["instance_id"])
        if item.get("asset_id") not in assets:
            raise KeyError("asset does not belong to this film project")
        if item.get("wall") is not None and item["wall"] not in WALLS:
            raise ValueError("unknown named room wall")
        rel = item.get("attachment")
        if rel is not None:
            if not isinstance(rel, dict) or set(rel) != {"target_instance", "target_anchor", "self_anchor", "max_gap"}:
                raise ValueError("attachment requires target_instance/target_anchor/self_anchor/max_gap")
            if not isinstance(rel["target_instance"], str) or rel["target_instance"] == item["instance_id"]:
                raise ValueError("invalid anchor target")
            if not isinstance(rel["self_anchor"], str) or rel["self_anchor"] not in assets[item["asset_id"]]["anchors"]:
                raise ValueError("self anchor absent from asset")
            rel["max_gap"] = positive(rel["max_gap"], "anchor max_gap", .05, 1.5)
    lookup = {i["instance_id"]: i for i in instances}
    for item in instances:
        rel = item.get("attachment")
        if rel:
            target = lookup.get(rel["target_instance"])
            if target is None:
                raise ValueError("attachment target does not exist")
            if rel["target_anchor"] not in assets[target["asset_id"]]["anchors"]:
                raise ValueError("target anchor absent from asset")
    # Topological ordering and explicit cycle rejection, with stable tie-breaking.
    output = []
    remaining = dict(lookup)
    while remaining:
        ready = [i for i in remaining.values()
                 if not i.get("attachment") or i["attachment"]["target_instance"] not in remaining]
        if not ready:
            raise ValueError("scene attachment dependencies form a cycle")
        ready.sort(key=lambda i: i["instance_id"])
        for item in ready:
            output.append(item)
            del remaining[item["instance_id"]]
    return output


def sample_grid(low: float, high: float, centre: float) -> list[float]:
    positions = [round(x * GRID, 4) for x in range(math.ceil(low / GRID), math.floor(high / GRID) + 1)]
    if low <= centre <= high:
        positions.append(round(centre, 4))
    return sorted(set(positions), key=lambda x: (abs(x - centre), x))


def candidate_poses(item: dict, asset: dict, room: list, placed: dict, assets: dict):
    for rotation in ROTATIONS:
        hx, hy = extents(asset, rotation)
        xlo, xhi = hx + MARGIN, room[0] - hx - MARGIN
        ylo, yhi = hy + MARGIN, room[1] - hy - MARGIN
        if xlo > xhi or ylo > yhi or asset["dimensions"][2] > room[2] - .05:
            continue
        xs = sample_grid(xlo, xhi, room[0] / 2)
        ys = sample_grid(ylo, yhi, room[1] / 2)
        wall = item.get("wall")
        if wall == "north":
            ys = [round(yhi, 4)]
        elif wall == "south":
            ys = [round(ylo, 4)]
        elif wall == "east":
            xs = [round(xhi, 4)]
        elif wall == "west":
            xs = [round(xlo, 4)]
        attachment = item.get("attachment")
        if attachment:
            target = placed[attachment["target_instance"]]
            target_point = world_anchor(target, assets[target["asset_id"]], attachment["target_anchor"])
            offset = rotate_xy(*asset["anchors"][attachment["self_anchor"]][:2], rotation)
            focus_x, focus_y = target_point[0] - offset[0], target_point[1] - offset[1]
            xs = sorted(set(xs + [round(focus_x + x, 4) for x in (-.5, -.25, 0, .25, .5)]), key=lambda x: (abs(x - focus_x), x))
            ys = sorted(set(ys + [round(focus_y + y, 4) for y in (-.5, -.25, 0, .25, .5)]), key=lambda y: (abs(y - focus_y), y))
            xs = [x for x in xs if xlo - 1e-6 <= x <= xhi + 1e-6 and abs(x - focus_x) <= attachment["max_gap"]]
            ys = [y for y in ys if ylo - 1e-6 <= y <= yhi + 1e-6 and abs(y - focus_y) <= attachment["max_gap"]]
        for x, y in itertools.product(xs, ys):
            yield {"asset_id": item["asset_id"], "x": x, "y": y, "z": 0.0, "rotation": rotation}


def verify_layout(room: list, instances: list[dict], poses: dict[str, dict], assets: dict) -> dict:
    """Independent post-solve checks: dimensional validity, collisions, relations."""
    validate_room(room)
    ordered = validate_instances(instances, assets)
    if set(poses) != {i["instance_id"] for i in instances}:
        raise ValueError("layout is missing instances or includes unrequested placements")
    processed = {}
    for item in ordered:
        p = poses[item["instance_id"]]
        if not isinstance(p, dict) or p.get("asset_id") != item["asset_id"] or p.get("rotation") not in ROTATIONS:
            raise ValueError("layout pose or asset identity invalid")
        if not all(k in p and isinstance(p[k], (int, float)) and not isinstance(p[k], bool)
                   and math.isfinite(p[k]) for k in ("x", "y", "z")) or abs(p["z"]) > 1e-7:
            raise ValueError("non-finite coordinates or unsupported elevation")
        if not geometry_ok(p, assets[p["asset_id"]], room):
            raise ValueError("placed asset outside room boundaries")
        if not check_relation(item, p, assets[p["asset_id"]], processed, assets, room):
            raise ValueError("wall or anchor relation not satisfied")
        for other in processed.values():
            if collision(p, assets[p["asset_id"]], other, assets[other["asset_id"]]):
                raise ValueError("placed assets overlap or violate clearance")
        processed[item["instance_id"]] = p
    return {"status": "valid", "checked_instances": len(ordered), "pair_count": len(ordered) * (len(ordered) - 1) // 2,
            "limitations": ["Proxy XY footprint collision only; articulated geometry and animated motion not checked",
                            "Anchor proximity is in XY only; contact, grip and IK are not checked",
                            "No camera occlusion or photorealistic rendering has been verified"]}


def solve_layout(room: list, instances: list[dict], assets: dict, *, max_nodes: int = MAX_NODES) -> dict:
    room = validate_room(room)
    ordered = validate_instances(instances, assets)
    if isinstance(max_nodes, bool) or not 1 <= max_nodes <= MAX_NODES:
        raise ValueError("invalid solver search budget")
    attempts = 0
    exhausted = False
    placed = {}

    def backtrack(index: int) -> bool:
        nonlocal attempts, exhausted
        if index == len(ordered):
            return True
        item = ordered[index]
        asset = assets[item["asset_id"]]
        candidates = 0
        for pose in candidate_poses(item, asset, room, placed, assets):
            candidates += 1
            if candidates > MAX_CANDIDATES or attempts >= max_nodes:
                exhausted = True
                break
            attempts += 1
            if not geometry_ok(pose, asset, room) or not check_relation(item, pose, asset, placed, assets, room):
                continue
            if any(collision(pose, asset, other, assets[other["asset_id"]]) for other in placed.values()):
                continue
            placed[item["instance_id"]] = pose
            if backtrack(index + 1):
                return True
            del placed[item["instance_id"]]
            if exhausted:
                break
        return False

    if not backtrack(0):
        raise RuntimeError("Layout search budget exceeded; reduce scene complexity" if exhausted else
                           "No feasible layout satisfies all room, collision and anchor constraints")
    validated = verify_layout(room, instances, placed, assets)
    return {"placements": {key: placed[key] for key in sorted(placed)}, "checked": validated,
            "solver": "bounded_deterministic_grid_backtracking", "candidates_checked": attempts,
            "search_limit": max_nodes}


class ProductionScene:
    def __init__(self, studio: Studio):
        self.studio = studio
        with self.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prod_assets (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL, category TEXT NOT NULL, spec_json TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(project_id, name))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_plans (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, scene_sha TEXT NOT NULL, screenplay_revision INTEGER NOT NULL,
                plan_revision INTEGER NOT NULL, approval_state TEXT NOT NULL,
                room_json TEXT NOT NULL, instances_json TEXT NOT NULL,
                layout_json TEXT, layout_sha TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, scene_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_plan_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, plan_revision INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL, archived_at TEXT NOT NULL,
                PRIMARY KEY(project_id, scene_id, plan_revision))""")

    def _project_scene(self, project_id: str, scene_id: str):
        project = self.studio.get_project(project_id)
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if scene is None:
            raise KeyError("Screenplay scene not found or no longer active")
        return project, scene

    def _assets(self, db, project_id: str) -> dict:
        return {r["id"]: json.loads(r["spec_json"]) for r in db.execute(
            "SELECT id,spec_json FROM prod_assets WHERE project_id=? ORDER BY id", (project_id,))}

    def create_asset(self, project_id: str, spec: dict):
        clean = validate_asset(spec)
        self.studio.get_project(project_id)
        aid = "AS_" + uuid.uuid4().hex
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Immutable asset geometry for a stage plan. New geometry = new asset ID.
            existing_names = db.execute("SELECT name FROM prod_assets WHERE project_id=?", (project_id,)).fetchall()
            if any(row["name"].casefold() == clean["name"].casefold() for row in existing_names):
                raise RuntimeError("A production asset with this name already exists in this project")
            db.execute("INSERT INTO prod_assets(id,project_id,name,category,spec_json,created_at) VALUES (?,?,?,?,?,?)",
                       (aid, project_id, clean["name"], clean["category"], compact(clean), stamp()))
        return {"asset_id": aid, **clean}

    def list_assets(self, project_id: str):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            rows = db.execute("SELECT id,spec_json FROM prod_assets WHERE project_id=? ORDER BY name,id", (project_id,)).fetchall()
            return [{"asset_id": row["id"], **json.loads(row["spec_json"])} for row in rows]

    def get_plan(self, project_id: str, scene_id: str):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            row = db.execute("SELECT * FROM prod_plans WHERE project_id=? AND scene_id=?", (project_id, scene_id)).fetchone()
            if row is None:
                raise KeyError("Production scene not staged")
            return self._unpack(row)

    @staticmethod
    def _unpack(row):
        obj = dict(row)
        obj["room"] = json.loads(obj.pop("room_json"))
        obj["instances"] = json.loads(obj.pop("instances_json"))
        obj["layout"] = json.loads(obj.pop("layout_json")) if obj.get("layout_json") else None
        obj.pop("layout_json", None)
        return obj

    @staticmethod
    def _db_scene(db, project_id: str, scene_id: str):
        # Read the authoritative text in the SAME SQLite transaction as the
        # plan. A screenplay edit cannot sneak between validation and save.
        source = db.execute("SELECT screenplay,revision FROM projects WHERE id=?", (project_id,)).fetchone()
        if source is None:
            raise KeyError("Film project not found")
        scene = next((item for item in parse_screenplay(source["screenplay"])
                      if item["id"] == scene_id), None)
        if scene is None:
            raise KeyError("Screenplay scene is not active")
        return source["revision"], scene

    def _current(self, db, project: dict, scene: dict, expected_revision: int | None = None):
        row = db.execute("SELECT * FROM prod_plans WHERE project_id=? AND scene_id=?",
                         (project["id"], scene["id"])).fetchone()
        if row is None:
            raise KeyError("Production scene not staged")
        plan = self._unpack(row)
        _revision, current_scene = self._db_scene(db, project["id"], scene["id"])
        if plan["scene_sha"] != hashlib.sha256(current_scene["text"].encode()).hexdigest():
            raise RuntimeError("Source scene changed; explicitly resynchronize the stage")
        if expected_revision is not None and plan["plan_revision"] != expected_revision:
            raise RuntimeError("Production plan changed elsewhere; reload before editing")
        return plan

    def stage_scene(self, project_id: str, scene_id: str, room: list | None = None):
        project, scene = self._project_scene(project_id, scene_id)
        room = validate_room(room if room is not None else [8, 6, 3])
        source_hash = hashlib.sha256(scene["text"].encode()).hexdigest()
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current_revision, current_scene = self._db_scene(db, project_id, scene_id)
            if current_revision != project["revision"] or current_scene["text"] != scene["text"]:
                raise RuntimeError("Screenplay changed during staging; reload the current scene")
            prior = db.execute("SELECT 1 FROM prod_plans WHERE project_id=? AND scene_id=?", (project_id, scene_id)).fetchone()
            if prior is not None:
                raise RuntimeError("Production scene already staged; use its existing plan or explicitly resynchronize")
            assets = self._assets(db, project_id)
            characters = {a["name"].casefold(): aid for aid, a in assets.items() if a["category"] == "character"}
            instances, unresolved = [], []
            for cue in scene["characters"]:
                aid = characters.get(cue.casefold())
                if aid is None:
                    unresolved.append(cue)
                else:
                    instances.append({"instance_id": "cast_" + str(len(instances) + 1), "asset_id": aid,
                                      "wall": None, "attachment": None})
            db.execute("""INSERT INTO prod_plans(project_id,scene_id,scene_sha,screenplay_revision,
                        plan_revision,approval_state,room_json,instances_json,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                       (project_id, scene_id, source_hash, project["revision"], 0, "proposed",
                        compact(room), compact(instances), stamp()))
        return {**self.get_plan(project_id, scene_id), "unresolved_cast": unresolved,
                "source_heading": scene["heading"]}

    def _archive(self, db, plan):
        db.execute("""INSERT INTO prod_plan_history(project_id,scene_id,plan_revision,snapshot_json,archived_at)
                    VALUES (?,?,?,?,?)""",
                   (plan["project_id"], plan["scene_id"], plan["plan_revision"], compact(plan), stamp()))

    def resync_scene(self, project_id: str, scene_id: str, expected_plan_revision: int):
        project, scene = self._project_scene(project_id, scene_id)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current_revision, current_scene = self._db_scene(db, project_id, scene_id)
            row = db.execute("SELECT * FROM prod_plans WHERE project_id=? AND scene_id=?", (project_id, scene_id)).fetchone()
            if row is None:
                raise KeyError("Production scene not staged")
            plan = self._unpack(row)
            if plan["plan_revision"] != expected_plan_revision:
                raise RuntimeError("Production plan changed elsewhere; reload before editing")
            self._archive(db, plan)
            # Explicit resync retains director-selected asset instances, but invalidates
            # old geometry and approval. Scene cues are not silently reinterpreted.
            db.execute("""UPDATE prod_plans SET scene_sha=?,screenplay_revision=?,plan_revision=plan_revision+1,
                       approval_state='proposed',layout_json=NULL,layout_sha=NULL,updated_at=?
                       WHERE project_id=? AND scene_id=?""",
                       (hashlib.sha256(current_scene["text"].encode()).hexdigest(), current_revision, stamp(), project_id, scene_id))
        return self.get_plan(project_id, scene_id)

    def add_instance(self, project_id: str, scene_id: str, asset_id: str, instance_id: str,
                     expected_plan_revision: int, *, wall: str | None = None, attachment: dict | None = None):
        project, scene = self._project_scene(project_id, scene_id)
        if not isinstance(instance_id, str) or not INSTANCE_ID.fullmatch(instance_id):
            raise ValueError("Invalid instance ID")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            plan = self._current(db, project, scene, expected_plan_revision)
            if plan["approval_state"] == "approved":
                raise RuntimeError("Approved layout is immutable; resync explicitly to propose changes")
            instances = plan["instances"] + [{"instance_id": instance_id, "asset_id": asset_id,
                                              "wall": wall, "attachment": attachment}]
            assets = self._assets(db, project_id)
            validate_instances(instances, assets)
            self._archive(db, plan)
            db.execute("""UPDATE prod_plans SET instances_json=?,layout_json=NULL,layout_sha=NULL,
                        plan_revision=plan_revision+1,updated_at=? WHERE project_id=? AND scene_id=?""",
                       (compact(instances), stamp(), project_id, scene_id))
        return self.get_plan(project_id, scene_id)

    def solve_scene(self, project_id: str, scene_id: str, expected_plan_revision: int, max_nodes: int = MAX_NODES):
        project, scene = self._project_scene(project_id, scene_id)
        with self.studio._connection() as db:
            plan = self._current(db, project, scene, expected_plan_revision)
            if plan["approval_state"] == "approved":
                raise RuntimeError("Approved layout is immutable; resync explicitly to propose changes")
            assets = self._assets(db, project_id)
        # Expensive bounded search runs OUTSIDE an SQLite write lock.
        layout = solve_layout(plan["room"], plan["instances"], assets, max_nodes=max_nodes)
        signature = digest({"scene_sha": plan["scene_sha"], "room": plan["room"],
                            "instances": plan["instances"], "layout": layout["placements"],
                            "assets": {i["asset_id"]: assets[i["asset_id"]] for i in plan["instances"]}})
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = self._current(db, project, scene, expected_plan_revision)
            if latest["approval_state"] != "proposed":
                raise RuntimeError("Production plan was approved while layout was solving")
            if latest["instances"] != plan["instances"] or latest["room"] != plan["room"]:
                raise RuntimeError("Production scene changed while layout was solving")
            self._archive(db, latest)
            db.execute("""UPDATE prod_plans SET layout_json=?,layout_sha=?,plan_revision=plan_revision+1,
                       updated_at=? WHERE project_id=? AND scene_id=?""",
                       (compact(layout), signature, stamp(), project_id, scene_id))
        return self.get_plan(project_id, scene_id)

    def _verified(self, plan, assets):
        if plan["layout"] is None or not plan["layout_sha"]:
            raise RuntimeError("Solve the production scene before approval or export")
        verify_layout(plan["room"], plan["instances"], plan["layout"]["placements"], assets)
        signature = digest({"scene_sha": plan["scene_sha"], "room": plan["room"],
                            "instances": plan["instances"], "layout": plan["layout"]["placements"],
                            "assets": {i["asset_id"]: assets[i["asset_id"]] for i in plan["instances"]}})
        if signature != plan["layout_sha"]:
            raise RuntimeError("Staged layout digest mismatch: refuse to export corrupted data")

    def approve_scene(self, project_id: str, scene_id: str, expected_plan_revision: int):
        project, scene = self._project_scene(project_id, scene_id)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            plan = self._current(db, project, scene, expected_plan_revision)
            if plan["approval_state"] != "proposed":
                raise RuntimeError("This production layout was already approved")
            self._verified(plan, self._assets(db, project_id))
            self._archive(db, plan)
            db.execute("""UPDATE prod_plans SET approval_state='approved',plan_revision=plan_revision+1,
                       updated_at=? WHERE project_id=? AND scene_id=?""", (stamp(), project_id, scene_id))
        return self.get_plan(project_id, scene_id)

    def export_manifest(self, project_id: str, scene_id: str):
        project, scene = self._project_scene(project_id, scene_id)
        with self.studio._connection() as db:
            plan = self._current(db, project, scene)
            if plan["approval_state"] != "approved":
                raise RuntimeError("Director must approve layout before Blender export")
            assets = self._assets(db, project_id)
            self._verified(plan, assets)
            return {"format": "nvp.production.proxy.v1", "project_id": project_id,
                    "scene_id": scene_id, "scene_heading": scene["heading"],
                    "screenplay_revision": plan["screenplay_revision"],
                    "source_scene_sha256": plan["scene_sha"], "layout_sha256": plan["layout_sha"],
                    "room_m": plan["room"], "instances": [{"instance_id": item["instance_id"],
                      "asset_id": item["asset_id"], **assets[item["asset_id"]],
                      "pose": plan["layout"]["placements"][item["instance_id"]]}
                      for item in sorted(plan["instances"], key=lambda x: x["instance_id"])],
                    "limitations": ["Procedural geometric proxies only, no licensed external mesh imported",
                                    "Static staging, not evaluated animation or camera occlusion"]}

    def export_blender_script(self, project_id: str, scene_id: str) -> str:
        return blender_script(self.export_manifest(project_id, scene_id))

    def history(self, project_id: str, scene_id: str):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [json.loads(row["snapshot_json"]) for row in db.execute(
                "SELECT snapshot_json FROM prod_plan_history WHERE project_id=? AND scene_id=? ORDER BY plan_revision DESC",
                (project_id, scene_id))]


def blender_script(manifest: dict) -> str:
    """Self-contained Blender 4+/5 bpy scene script. Does not execute on export.

    Names and user notes are encoded as JSON *data*, never interpreted as Python.
    Run: blender -b -P scene.py -- --output /chosen/path/scene.blend
    No external assets are read; all geometry is local primitive proxies.
    """
    json_data = compact(manifest)
    payload = repr(json_data)
    return '''# NVP-PROD-01 deterministic procedural proxy scene, generated data only.
# Requires Blender (bpy). Nothing is rendered until Blender executes this script.
import bpy
import json
import math
import sys

manifest = json.loads(''' + payload + ''')
assert manifest["format"] == "nvp.production.proxy.v1"
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
room = manifest["room_m"]

def box(name, location, dimensions, color):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    obj.color = (*color, 1.0)
    obj["nvp_proxy"] = True
    return obj

box("NVP_FLOOR", (room[0]/2, room[1]/2, -0.05), (room[0], room[1], 0.10), (0.2, 0.2, 0.23))
# Low room-border guides avoid blocking the establishing camera.
box("NVP_NORTH_GUIDE", (room[0]/2, room[1], .06), (room[0], .06, .12), (.5, .5, .5))
box("NVP_WEST_GUIDE", (0, room[1]/2, .06), (.06, room[1], .12), (.5, .5, .5))
box("NVP_EAST_GUIDE", (room[0], room[1]/2, .06), (.06, room[1], .12), (.5, .5, .5))
colors = {"character": (.18, .55, .82), "furniture": (.58, .40, .25),
          "prop": (.85, .70, .25), "set_piece": (.35, .65, .4)}
for item in manifest["instances"]:
    pose = item["pose"]
    height = item["dimensions"][2]
    obj = box("NVP_" + item["instance_id"],
              (pose["x"], pose["y"], height / 2),
              item["dimensions"], colors[item["category"]])
    obj.rotation_euler.z = math.radians(pose["rotation"])
    # Persistent director visibility edits must affect the actual Blender
    # world, not only the JSON hash / NVP 2D planning preview.
    hidden = item.get("visible", True) is False
    obj.hide_render = hidden
    obj.hide_viewport = hidden
    obj["nvp_asset_id"] = item["asset_id"]
    obj["nvp_instance_id"] = item["instance_id"]
    obj["nvp_original_name"] = item["name"]
    for anchor_name, xyz in item["anchors"].items():
        marker = bpy.data.objects.new("ANCHOR_" + item["instance_id"] + "_" + anchor_name, None)
        bpy.context.collection.objects.link(marker)
        marker.empty_display_type = "SPHERE"
        marker.empty_display_size = .12
        marker.parent = obj
        marker.location = (xyz[0], xyz[1], xyz[2] - height/2)
        marker["nvp_spatial_anchor"] = anchor_name

camera_data = bpy.data.cameras.new("NVP_Establishing_Camera")
camera_obj = bpy.data.objects.new("NVP_Establishing_Camera", camera_data)
bpy.context.collection.objects.link(camera_obj)
camera_obj.location = (room[0]/2, -max(room[0], room[1]) * 1.35, room[2] * 1.8)
from mathutils import Vector
forward = Vector((room[0]/2, room[1]/2, room[2] * .35)) - camera_obj.location
camera_obj.rotation_euler = forward.to_track_quat("-Z", "Y").to_euler()
camera_data.type = "PERSP"
camera_data.lens = 35
bpy.context.scene.camera = camera_obj
light_data = bpy.data.lights.new("NVP_Overhead_Key", "AREA")
light_data.energy = 1000
light_data.shape = "DISK"
light_data.size = 5
light_obj = bpy.data.objects.new("NVP_Overhead_Key", light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.location = (room[0]/2, room[1]/2, room[2] - .25)
bpy.context.scene.render.resolution_x = 960
bpy.context.scene.render.resolution_y = 540
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene["nvp_manifest_sha"] = manifest["layout_sha256"]
bpy.context.scene["nvp_source_sha"] = manifest["source_scene_sha256"]

args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
if "--output" in args:
    ix = args.index("--output")
    if ix + 1 >= len(args) or not args[ix+1].lower().endswith(".blend"):
        raise ValueError("--output requires a .blend path")
    bpy.ops.wm.save_as_mainfile(filepath=args[ix+1])
else:
    print("NVP: scene constructed in Blender memory; pass --output filename.blend to save")
'''
