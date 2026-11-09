"""USD-FILM-01M: editable, source-preserving virtual director camera rigs.

One frozen original actor performance supports a configurable number of
independent film cameras. Add/remove/replace operations create new FilmIndex
revisions; old camera/editor choices remain playable. Cameras are native
UsdGeom.Camera prims with no geometry or physics collider. A camera may be
placed through walls: ONLY explicitly selected camera-primary-ray exclusions
can affect its picture. Original world visibility is never edited.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01e_world_take import (
    OpenUSDWorldTakeCapture, FORMAT as TAKE_FORMAT)
from backend.nvp_usd_film01i_ninecam_take import (
    _performance_source, _digest)
from backend.nvp_usd_film01_world import OpenUSDWorldComposer

FORMAT = "nvp.usd_film01m.director_revisable_virtual_camera_bank.v1"
MAX_CAMERAS = 96
MAX_CAMERA_KEYS = 48
MAX_EXCLUDED_PRIMS = 16
CAMERA_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,49}$")
SETUP_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9 _/-]{0,63}$")
CAMERA_FIELDS = frozenset({
    "camera_id", "setup", "framing", "position_m",
    "rotation_euler_deg", "focal_length_mm", "focus_distance_m",
    "clip_range_m", "move_keys", "camera_ray_exclusions"
})


def _hash(value):
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _vec(value, *, limit=1000000.0):
    if (type(value) is not list or len(value) != 3 or
        any(type(n) not in (int, float) or not math.isfinite(n)
            or abs(n) > limit for n in value)):
        raise ValueError("Bounded finite 3D vector required")
    return [float(x) for x in value]


def _camera(camera, *, duration_ticks):
    if type(camera) is not dict or set(camera) != CAMERA_FIELDS:
        raise ValueError("Camera needs exact typed director fields")
    identity = camera["camera_id"]
    if type(identity) is not str or not CAMERA_TOKEN.fullmatch(identity):
        raise ValueError("Invalid native camera identity")
    for key in ("setup", "framing"):
        value = camera[key]
        if type(value) is not str or not SETUP_TOKEN.fullmatch(value):
            raise ValueError("Camera setup/framing must be a short director label")
    pos = _vec(camera["position_m"])
    rotation = _vec(camera["rotation_euler_deg"], limit=360)
    focal = camera["focal_length_mm"]
    focus = camera["focus_distance_m"]
    clip = camera["clip_range_m"]
    if (type(focal) not in (int, float) or
        type(focus) not in (int, float) or
        not math.isfinite(focal) or not 8 <= focal <= 300 or
        not math.isfinite(focus) or not .05 <= focus <= 100000 or
        type(clip) is not list or len(clip) != 2 or
        any(type(n) not in (int, float) or not math.isfinite(n)
            for n in clip) or
        not .001 <= clip[0] < clip[1] <= 1000000):
        raise ValueError("Invalid native optics, focus or clipping range")
    keys = camera["move_keys"]
    if type(keys) is not list or len(keys) > MAX_CAMERA_KEYS:
        raise ValueError("Bounded camera keyframes required")
    prev = -1
    normalized_keys = []
    for key in keys:
        if type(key) is not dict or set(key) != {
            "tick", "position_m", "rotation_euler_deg"
        }:
            raise ValueError("Camera movement key has incorrect fields")
        tick = key["tick"]
        if type(tick) is not int or not prev < tick <= duration_ticks:
            raise ValueError("Camera movement must use strictly increasing Film Time")
        prev = tick
        normalized_keys.append({
            "tick": tick,
            "position_m": _vec(key["position_m"]),
            "rotation_euler_deg": _vec(key["rotation_euler_deg"], limit=360)})
    excluded = camera["camera_ray_exclusions"]
    if (type(excluded) is not list or len(excluded) > MAX_EXCLUDED_PRIMS or
        len(set(excluded)) != len(excluded) or
        any(type(p) is not str or len(p) > 240 or
            not p.startswith("/World/") or
            any(section in ("", "..", ".") for section in p.split("/")[1:])
            for p in excluded)):
        raise ValueError("Camera exclusions must be bounded native source prim paths")
    return {
        "camera_id": identity,
        "setup": camera["setup"],
        "framing": camera["framing"],
        "position_m": pos, "rotation_euler_deg": rotation,
        "focal_length_mm": float(focal),
        "focus_distance_m": float(focus),
        "clip_range_m": [float(n) for n in clip],
        "move_keys": normalized_keys,
        "camera_ray_exclusions": list(excluded),
    }


def _original_source(index, pid, take_id):
    _require_pid(pid)
    _id(take_id, "immutable original world performance")
    original = OpenUSDWorldTakeCapture(
        index, verify_creator_action=lambda *_: False)
    original.verify_take(pid, take_id)
    record = index.read_revision(pid, take_id, 1)
    doc = record["data"]
    if doc.get("format") != TAKE_FORMAT or len(doc["original_scene_takes"]) != 1:
        raise PermissionError("Director camera bank needs one shared frozen source performance")
    duration = doc["original_scene_takes"][0]["duration_tick"]
    if type(duration) is not int or duration <= 0:
        raise RuntimeError("Original source Take has invalid performance duration")
    return record, duration, _digest(_performance_source(doc))


def _check_exclusions(index, pid, take, cameras):
    """Never hide an original actor, camera, light or an unverified world prim."""
    paths = {p for camera in cameras for p in camera["camera_ray_exclusions"]}
    if not paths:
        return
    from pxr import UsdGeom, Usd
    source = take["data"]
    actor_paths = [x["composed_actor_prim"]
                   for x in source["canonical_original_actors"]]
    geometries = (
        UsdGeom.Mesh, UsdGeom.Cube, UsdGeom.Sphere,
        UsdGeom.Cylinder, UsdGeom.Cone, UsdGeom.Capsule)
    with OpenUSDWorldComposer(index).open(
            pid, source["world_id"], source["world_revision"]) as world:
        world.load([source["original_scene_takes"][0]["set"]])
        for path in paths:
            if any(
                actor == path or actor.startswith(path + "/") or
                path.startswith(actor + "/")
                for actor in actor_paths):
                raise PermissionError(
                    "Director cannot hide ActorID performance with a camera-wall exception")
            prim = world.stage.GetPrimAtPath(path)
            if not prim or not prim.IsDefined():
                raise PermissionError("Camera-ray exclusion is not original source geometry")
            if prim.IsA(UsdGeom.Camera):
                raise PermissionError("Cannot mark original cameras as occluder geometry")
            children = list(Usd.PrimRange(prim))
            if not any(any(child.IsA(kind) for kind in geometries)
                       for child in children):
                raise PermissionError("Camera-ray exception must target real source geometry")
            if any(child.IsA(UsdGeom.Camera) for child in children):
                raise PermissionError("Cannot hide a camera-containing source subtree")


class DirectorCameraBank:
    """Revisions are non-destructive; there is no fixed 3×3 requirement."""

    def __init__(self, index: FilmIndex, *, verify_director_action):
        if (not isinstance(index, FilmIndex) or
            not callable(verify_director_action)):
            raise TypeError("Existing FilmIndex and authenticated director callback required")
        self.index = index
        self.approve = verify_director_action

    def _prepare(self, pid, take_id, cameras, *, previous=None):
        source, duration, performance_sha = _original_source(
            self.index, pid, take_id)
        if type(cameras) is not list or len(cameras) > MAX_CAMERAS:
            raise ValueError("At most 96 active director cameras per bank")
        clean = [_camera(c, duration_ticks=duration) for c in cameras]
        ids = [c["camera_id"] for c in clean]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate director camera identities")
        _check_exclusions(self.index, pid, source, clean)
        return {
            "format": FORMAT,
            "world_take_id": take_id,
            "world_take_sha256": source["document_sha256"],
            "source_world_sha256": source["data"]["world_document_sha256"],
            "source_performance_sha256": performance_sha,
            "source_duration_ticks": duration,
            "source_ticks_per_second": T,
            "camera_count": len(clean),
            "cameras": clean,
            "previous_bank_revision_sha256": previous,
            "director_camera_geometry_rendered": False,
            "director_camera_physical_collision": False,
            "camera_exclusions_only_apply_to_selected_render_view": True,
            "original_source_visibility_unchanged": True,
        }

    def _store(self, pid, bank_id, take_id, cameras, *, expected_revision,
               previous, director_event):
        _id(bank_id, "director camera bank")
        doc = self._prepare(pid, take_id, cameras, previous=previous)
        scope = {
            "operation": "nvp.film.director_camera_bank_revision.v1",
            "project_id": pid, "camera_bank_id": bank_id,
            "expected_revision": expected_revision,
            "world_take_sha256": doc["world_take_sha256"],
            "source_performance_sha256": doc["source_performance_sha256"],
            "proposed_camera_bank_sha256": _hash(doc),
            "camera_ids": [c["camera_id"] for c in cameras],
        }
        if self.approve(director_event, scope) is not True:
            raise PermissionError("Exact director camera revision not authorized")
        return self.index.register_revision(
            pid, bank_id, "presentation", doc,
            expected_revision=expected_revision,
            dependencies=[{
                "object_id": take_id, "revision": 1,
                "role": "source_take"
            }])

    def create(self, pid, bank_id, *, world_take_id, cameras, director_event):
        return self._store(
            pid, bank_id, world_take_id, cameras,
            expected_revision=0, previous=None, director_event=director_event)

    def create_standard_nine_preset(self, pid, bank_id, *,
                                    original_nine_rig_id, director_event):
        """Use nine ALREADY verified original 01I source camera placements.

        This preset is optional. Later edits can add/remove/reframe any view
        without changing the one original actor performance.
        """
        from backend.nvp_usd_film01i_ninecam_take import OriginalNineCameraFilmSet
        _id(original_nine_rig_id, "original nine-camera preset source")
        OriginalNineCameraFilmSet(
            self.index, verify_creator_action=lambda *_: False).verify(
                pid, original_nine_rig_id)
        source = self.index.read_revision(pid, original_nine_rig_id, 1)["data"]
        cameras = []
        for cam in source["cameras"]:
            cameras.append({
                "camera_id": "Cam_" + cam["angle"] + "_" + cam["framing"],
                "setup": "Angle " + cam["angle"],
                "framing": cam["framing"],
                "position_m": list(cam["source_world_positions_m"][0]),
                "rotation_euler_deg": list(cam["rotation_euler_deg"]),
                "focal_length_mm": cam["focal_length_mm"],
                "focus_distance_m": 11.0,
                "clip_range_m": [.01, 10000.0],
                "move_keys": [],
                "camera_ray_exclusions": [],
            })
        return self.create(
            pid, bank_id, world_take_id=source["world_take_id"],
            cameras=cameras, director_event=director_event)

    def revise(self, pid, bank_id, *, expected_revision, changes, director_event):
        _require_pid(pid)
        _id(bank_id, "original director camera bank")
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Exact current rig revision required")
        current = self.verify(pid, bank_id, expected_revision)
        record = self.index.read_revision(pid, bank_id, expected_revision)
        if type(changes) is not list or not 1 <= len(changes) <= MAX_CAMERAS:
            raise ValueError("One bounded director camera edit batch required")
        cameras = list(current["cameras"])
        for action in changes:
            if type(action) is not dict or action.get("op") not in (
                    "add", "remove", "replace"):
                raise ValueError("Only add, remove and replace camera actions allowed")
            operation = action["op"]
            if operation in ("add", "replace"):
                if set(action) != {"op", "camera"}:
                    raise ValueError("Camera addition/replacement requires full typed source")
                candidate = _camera(
                    action["camera"],
                    duration_ticks=current["source_duration_ticks"])
                at = next((i for i,c in enumerate(cameras)
                           if c["camera_id"] == candidate["camera_id"]), None)
                if operation == "add":
                    if at is not None:
                        raise ValueError("Camera ID already exists; replace explicitly")
                    cameras.append(candidate)
                else:
                    if at is None:
                        raise KeyError("Cannot replace missing director camera")
                    cameras[at] = candidate
            else:
                if set(action) != {"op", "camera_id"}:
                    raise ValueError("Removal requires exact original camera ID")
                target = action["camera_id"]
                at = next((i for i,c in enumerate(cameras)
                           if c["camera_id"] == target), None)
                if at is None:
                    raise KeyError("Director camera removal ID not found")
                cameras.pop(at)
        return self._store(
            pid, bank_id, current["world_take_id"], cameras,
            expected_revision=expected_revision,
            previous=record["document_sha256"], director_event=director_event)

    def verify(self, pid, bank_id, revision):
        _require_pid(pid)
        _id(bank_id, "original director camera bank")
        if type(revision) is not int or revision < 1:
            raise ValueError("Exact source camera bank revision required")
        stored = self.index.read_revision(pid, bank_id, revision)
        doc = stored["data"]
        if stored["kind"] != "presentation" or doc.get("format") != FORMAT:
            raise PermissionError("Not a source-verified director camera bank")
        previous = None
        if revision > 1:
            old = self.index.read_revision(pid, bank_id, revision - 1)
            previous = old["document_sha256"]
            if old["kind"] != "presentation" or (
                old["data"].get("world_take_id") != doc["world_take_id"]):
                raise RuntimeError("Source performance changed during camera revision")
        rebuilt = self._prepare(
            pid, doc["world_take_id"], doc["cameras"], previous=previous)
        if doc != rebuilt:
            raise RuntimeError("Frozen camera bank/source/occlusion records altered")
        return doc

    @contextmanager
    def open_source_views(self, pid, bank_id, revision):
        """Session-layer ONLY native cameras; source USD never mutated."""
        from pxr import Gf, Usd, UsdGeom
        from backend.nvp_usd_film01_world import OpenUSDWorldComposer
        from backend.nvp_usd_film01e_world_take import FORMAT as TAKE_FORMAT
        from backend.nvp_usd_film01e_world_take import OpenUSDWorldTakeCapture
        from backend.nvp_usd_film01_world import OpenUSDWorldComposer
        from backend.nvp_usd_film01d_shot_working_set import _camera_native
        from backend.nvp_openusd_native_schemas import (
            MM_PER_CAMERA_UNIT, METERS_PER_UNIT)
        doc = self.verify(pid, bank_id, revision)
        take = self.index.read_revision(pid, doc["world_take_id"], 1)["data"]
        with OpenUSDWorldComposer(self.index).open(
                pid, take["world_id"], take["world_revision"]) as world:
            world.load([take["original_scene_takes"][0]["set"]])
            root = "/World/NVPDirectorCameraRig"
            if world.stage.GetPrimAtPath(root).IsDefined():
                raise PermissionError("Original world already defines director rig namespace")
            with Usd.EditContext(world.stage, world.stage.GetSessionLayer()):
                UsdGeom.Scope.Define(world.stage, root)
                for c in doc["cameras"]:
                    cam = UsdGeom.Camera.Define(
                        world.stage, root + "/NVPDirector_" + c["camera_id"])
                    cam.GetFocalLengthAttr().Set(
                        c["focal_length_mm"] / MM_PER_CAMERA_UNIT)
                    # USD camera dimensions use scene units; the project
                    # native_schema conversion is exactly mm/100 here.
                    # Both low-fi THREE projection and native Cycles import
                    # must use this reviewed 36 × 20.25 mm sensor aperture.
                    cam.GetHorizontalApertureAttr().Set(
                        36.0 / MM_PER_CAMERA_UNIT)
                    cam.GetVerticalApertureAttr().Set(
                        20.25 / MM_PER_CAMERA_UNIT)
                    cam.GetFocusDistanceAttr().Set(
                        c["focus_distance_m"] / METERS_PER_UNIT)
                    cam.GetClippingRangeAttr().Set(Gf.Vec2f(*c["clip_range_m"]))
                    shift = cam.AddTranslateOp()
                    turn = cam.AddRotateXYZOp()
                    shift.Set(Gf.Vec3d(*c["position_m"]))
                    turn.Set(Gf.Vec3f(*c["rotation_euler_deg"]))
                    for key in c["move_keys"]:
                        t = Usd.TimeCode(float(key["tick"]))
                        shift.Set(Gf.Vec3d(*key["position_m"]), t)
                        turn.Set(Gf.Vec3f(*key["rotation_euler_deg"]), t)
            # Native camera prims are not polygonal geometry and have no
            # physics collider. Source occluders remain unchanged globally.
            yield {
                "original_world": world,
                "stage": world.stage,
                "camera_paths": {
                    c["camera_id"]: root + "/NVPDirector_" + c["camera_id"]
                    for c in doc["cameras"]},
                "camera_source_manifest": doc,
                "camera_has_physical_collision": False,
                "camera_occlusion_masks_applied_globally": False,
            }
