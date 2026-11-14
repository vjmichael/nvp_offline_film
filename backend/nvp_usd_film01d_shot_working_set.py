"""USD-FILM-01D: director-authored camera-aware OpenUSD film working sets.

FilmIndex's original world, scenes, actor source and frozen Takes remain the
only authorities. A shot stores *which original camera* and required world
sets. Optional spatial envelopes may PREFETCH extra sets but NEVER decide
whether a director-required scene disappears from the picture.

Native USD reads camera transforms and evaluates typed variants. Only an
ephemeral Stage working set is mutated. No AI-written USDA, global resolver,
MCP dependency, physics runtime, headset compiler or renderer is added.

Persistent "presentation" receipts describe host-side USD load outcomes,
not image fidelity, GPU stage memory, installed UI responsiveness or films.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from time import perf_counter

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK
from backend.nvp_usd_film01_world import (
    OpenUSDWorldComposer, _rss_bytes,
)

FORMAT = "nvp.usd_film01d.director_camera_working_set.v1"
RECEIPT_FORMAT = "nvp.usd_film01d.native_shot_working_set_receipt.v1"
MAX_CAMERA_SAMPLES = 16
MAX_SPATIAL_HINTS = 8
MAX_SCENE_QUERY = 128
MAX_PREFETCH_M = 10000.0


def native_gpu_device_sampler(device_id):
    """Use NVP's EXISTING OS GPU measurement, never estimate VRAM from USD.

    Linux AMD DRM/NVML provide device-global usage. Windows DXGI provides
    an OS per-process video budget and usage, not total physical VRAM.
    Neither is GPU memory attributable solely to the active USD Stage.
    """
    if type(device_id) is not str or not device_id or len(device_id) > 64:
        raise ValueError("Explicit trusted host GPU device identity required")
    def sample():
        from backend.nvp_resource_guard import collect_resources
        snap = collect_resources()
        found = [g for g in snap.gpus if g.device_id == device_id]
        if len(found) != 1:
            raise RuntimeError("Selected GPU budget unavailable or ambiguous")
        g = found[0]
        if (type(g.used_mb) is not int or type(g.budget_mb) is not int
            or not 0 <= g.used_mb <= g.budget_mb):
            raise RuntimeError("Verified OS GPU memory values are invalid")
        return {
            "device_id":g.device_id,
            "used_bytes":g.used_mb * 1024 * 1024,
            "total_bytes":g.budget_mb * 1024 * 1024,
            "source":g.source,
            "scope":("device_global" if g.globally_measured
                     else "os_process_video_budget"),
        }
    return sample


def _position(vector, label):
    if (type(vector) is not list or len(vector) != 3 or
        any(type(x) not in (int, float) or not math.isfinite(x)
            or abs(x) > 1_000_000 for x in vector)):
        raise ValueError("Invalid bounded three-dimensional " + label)
    return [float(x) for x in vector]


def _ticks(value):
    if (type(value) is not list or not 1 <= len(value) <= MAX_CAMERA_SAMPLES
        or any(type(x) is not int or not 0 <= x <= MAX_USD_EXACT_TICK
               for x in value)
        or any(a >= b for a, b in zip(value, value[1:]))):
        raise ValueError("Shot requires 1–16 unique increasing exact film ticks")
    return value


def _max_sets(value, allowed):
    if type(value) is not int or not 1 <= value <= min(8, allowed):
        raise ValueError("Working-set budget exceeds original world set count")
    return value


def _camera_native(world, set_name, camera_prim, time_ticks):
    """Read a verified source UsdGeom.Camera, not a supplied position guess."""
    from pxr import Usd, UsdGeom
    if type(camera_prim) is not str or not camera_prim.startswith("/World/"):
        raise ValueError("Camera must be an original absolute source prim path")
    shot_path = "/World/Sets/" + set_name + camera_prim[len("/World"):]
    prim = world.stage.GetPrimAtPath(shot_path)
    camera = UsdGeom.Camera(prim)
    if not camera or not prim.IsDefined():
        raise RuntimeError("Exact original shot camera missing after USD set load")
    xform = UsdGeom.Xformable(prim)
    positions = []
    for tick in time_ticks:
        transform = xform.ComputeLocalToWorldTransform(Usd.TimeCode(float(tick)))
        vec = transform.ExtractTranslation()
        positions.append(_position([float(vec[i]) for i in range(3)],
                                   "native USD camera position"))
    return shot_path, positions


def _plan_payload(index, pid, world_id, world_revision, *, camera_set,
                  camera_prim, sample_ticks, required_sets,
                  spatial_hints, prefetch_distance_m, max_loaded_sets,
                  director_looks):
    if not isinstance(index, FilmIndex):
        raise TypeError("Original NVP FilmIndex is required")
    _require_pid(pid)
    _id(world_id, "source film world")
    if type(world_revision) is not int or world_revision < 1:
        raise ValueError("World shot must reference one exact published revision")
    ticks = _ticks(sample_ticks)
    world = index.read_revision(pid, world_id, world_revision)
    data = world["data"]
    if world["kind"] != "world" or data.get("format") != (
            "nvp.usd_film01.composed_film_world.v1"):
        raise PermissionError("Shot may only use a genuine frozen NVP USD film world")
    names = {entry["name"]: entry for entry in data["sets"]}
    if type(camera_set) is not str or camera_set not in names:
        raise ValueError("Director camera must belong to an authored world set")
    if (type(required_sets) is not list or
        any(type(x) is not str or x not in names for x in required_sets) or
        len(set(required_sets)) != len(required_sets)):
        raise ValueError("Director-required film sets must be original distinct names")
    required = sorted(set(required_sets) | {camera_set})
    _max_sets(max_loaded_sets, len(names))
    if len(required) > max_loaded_sets:
        raise ValueError("Working-set budget cannot omit a director-required set")
    if (type(prefetch_distance_m) not in (int, float) or
        not math.isfinite(prefetch_distance_m) or
        not 0 <= prefetch_distance_m <= MAX_PREFETCH_M):
        raise ValueError("Shot prefetch distance outside bounded meters")
    if (type(spatial_hints) is not list or len(spatial_hints) > MAX_SPATIAL_HINTS):
        raise ValueError("Bounded original set prefetch hints required")
    normalized_hints = {}
    for raw in spatial_hints:
        if type(raw) is not dict or set(raw) != {"set", "center_m", "radius_m"}:
            raise ValueError("Spatial hints require typed source set envelope")
        name = raw["set"]
        radius = raw["radius_m"]
        if (name not in names or name in normalized_hints or
            type(radius) not in (int, float) or not math.isfinite(radius)
            or not 0 <= radius <= 100000):
            raise ValueError("Unknown/duplicate/unbounded set envelope")
        normalized_hints[name] = {
            "set": name, "center_m": _position(raw["center_m"], "set hint"),
            "radius_m": float(radius),
        }
    looks = {}
    valid_looks = {v["name"]: v for v in data["variants"]}
    if type(director_looks) is not dict or len(director_looks) > 8:
        raise ValueError("Only typed, source-authored director looks supported")
    for name, choice in director_looks.items():
        if name not in valid_looks or type(choice) is not str or choice not in {
            opt["name"] for opt in valid_looks[name]["options"]
        }:
            raise ValueError("Director look not present in original USD world")
        looks[name] = choice
    selected_set = names[camera_set]
    source = index.read_revision(
        pid, selected_set["scene_id"], selected_set["scene_revision"])
    if (source["document_sha256"] != selected_set["scene_sha256"] or
        source["kind"] != "scene" or
        source["data"]["prim_roles"].get(camera_prim) != "camera" or
        source["data"]["native_schema_version"] is None):
        raise PermissionError("Shot camera is not an original native source camera")
    with OpenUSDWorldComposer(index).open(pid, world_id, world_revision) as session:
        session.load([camera_set])
        actual_path, actual_positions = _camera_native(
            session, camera_set, camera_prim, ticks)
        if session.receipt()["loaded_set_names"] != [camera_set]:
            raise RuntimeError("Native source shot camera admission loaded unexpected sets")
    return {
        "format": FORMAT,
        "world_id": world_id, "world_revision": world_revision,
        "world_document_sha256": world["document_sha256"],
        "source_camera_scene_id": selected_set["scene_id"],
        "source_camera_scene_revision": selected_set["scene_revision"],
        "source_camera_scene_sha256": source["document_sha256"],
        "camera_set": camera_set, "camera_prim_path": camera_prim,
        "native_composed_camera_path": actual_path,
        "camera_sample_ticks": list(ticks),
        "original_camera_positions_m": actual_positions,
        "director_required_sets": required,
        "optional_spatial_hints_not_proven_visibility": [
            normalized_hints[k] for k in sorted(normalized_hints)],
        "prefetch_distance_m": float(prefetch_distance_m),
        "max_loaded_sets": max_loaded_sets,
        "director_looks": dict(sorted(looks.items())),
        "not_a_renderer_or_visibility_occlusion_solution": True,
        "original_actor_identity_unchanged": True,
    }


class FilmWorldShotPlanner:
    def __init__(self, index):
        if not isinstance(index, FilmIndex):
            raise TypeError("Original NVP project FilmIndex is required")
        self.index = index

    def publish(self, pid, shot_id, *, world_id, world_revision,
                camera_set, camera_prim, sample_ticks, required_sets,
                spatial_hints=None, prefetch_distance_m=0.0,
                max_loaded_sets=2, director_looks=None, expected_revision=0):
        _id(shot_id, "film camera shot working set")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Film shot revision must be an exact integer")
        doc = _plan_payload(
            self.index, pid, world_id, world_revision,
            camera_set=camera_set, camera_prim=camera_prim,
            sample_ticks=sample_ticks, required_sets=required_sets,
            spatial_hints=[] if spatial_hints is None else spatial_hints,
            prefetch_distance_m=prefetch_distance_m,
            max_loaded_sets=max_loaded_sets,
            director_looks={} if director_looks is None else director_looks)
        return self.index.register_revision(
            pid, shot_id, "camera", doc,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id": world_id, "revision": world_revision,
                 "role": "world"},
                {"object_id": doc["source_camera_scene_id"],
                 "revision": doc["source_camera_scene_revision"], "role": "scene"},
            ])

    def inspect(self, pid, shot_id, revision, *, expected_world_sha=None):
        _require_pid(pid)
        _id(shot_id, "film camera shot working set")
        if type(revision) is not int or revision < 1:
            raise ValueError("Exact published camera shot revision required")
        record = self.index.read_revision(pid, shot_id, revision)
        doc = record["data"]
        if record["kind"] != "camera" or doc.get("format") != FORMAT:
            raise PermissionError("Not a source-locked director camera working set")
        if (expected_world_sha is not None and
                doc["world_document_sha256"] != expected_world_sha):
            raise PermissionError("Shot belongs to a different immutable world")
        fresh_world = self.index.read_revision(
            pid, doc["world_id"], doc["world_revision"])
        if (fresh_world["kind"] != "world" or
            fresh_world["document_sha256"] != doc["world_document_sha256"]):
            raise PermissionError("Shot original world identity no longer matches")
        source_scene = self.index.read_revision(
            pid, doc["source_camera_scene_id"],
            doc["source_camera_scene_revision"])
        if (source_scene["document_sha256"] != doc["source_camera_scene_sha256"]
            or source_scene["data"]["prim_roles"].get(doc["camera_prim_path"]) != "camera"):
            raise PermissionError("Shot has lost authoritative original camera")
        return record


def _preload_choices(doc):
    """Prefetch based on authored HINTS; never cull a director-required set."""
    required = list(doc["director_required_sets"])
    capacity = doc["max_loaded_sets"] - len(required)
    near = []
    for item in doc["optional_spatial_hints_not_proven_visibility"]:
        if item["set"] in required:
            continue
        closest = min(
            math.dist(item["center_m"], p) - item["radius_m"]
            for p in doc["original_camera_positions_m"])
        if closest <= doc["prefetch_distance_m"]:
            near.append((max(0.,closest), item["set"]))
    near.sort(key=lambda item: (item[0],item[1]))
    return {
        "required_sets": sorted(required),
        "prefetched_sets": [s for _,s in near[:capacity]],
        "skipped_optional_set_names": [s for _,s in near[capacity:]],
        "only_conservative_director_requirements_guaranteed": True,
    }


def _source_query(index, pid, world, loaded_sets):
    """Bounded semantic query for models/directors, not a full stage dump."""
    source = world.record["data"]
    selected = {item["name"]: item for item in source["sets"]}
    result = []
    for name in sorted(loaded_sets):
        item = selected[name]
        record = index.read_revision(
            pid, item["scene_id"], item["scene_revision"])
        if record["document_sha256"] != item["scene_sha256"]:
            raise PermissionError("Loaded scene semantic inventory differs from source")
        for path, role in sorted(record["data"]["prim_roles"].items()):
            if len(result) >= MAX_SCENE_QUERY:
                return {"entries": result, "truncated": True,
                        "authoritative_source_only": True}
            full_path = "/World/Sets/" + name + path[len("/World"):]
            if not world.stage.GetPrimAtPath(full_path).IsDefined():
                raise RuntimeError("Authoritative actor/camera/prop not present in USD")
            result.append({"set": name, "path": full_path, "role": role})
    return {"entries": result, "truncated": False,
            "authoritative_source_only": True}


class FilmShotWorkingSet:
    """A host-owned, ephemeral USD working set with durable preview receipts.

    Incomplete transitions are fail-closed and close the private USD session.
    After interruption, a NEW session reopens the sealed FilmIndex world and
    can replay a source-locked camera shot. No long-lived model context, worker
    processes or unreviewed USD edits are required.
    """

    def __init__(self, index, pid, world_id, revision, *,
                 max_process_rss_bytes=None, gpu_probe=None,
                 max_device_gpu_used_bytes=None):
        if not isinstance(index, FilmIndex):
            raise TypeError("Original NVP FilmIndex required")
        _require_pid(pid)
        _id(world_id,"original film world")
        if type(revision) is not int or revision < 1:
            raise ValueError("Exact source world revision required")
        if (max_process_rss_bytes is not None and
            (type(max_process_rss_bytes) is not int or
             not 32 * 1024 * 1024 <= max_process_rss_bytes <= 2**42)):
            raise ValueError("Trusted host process RSS budget invalid")
        if max_device_gpu_used_bytes is not None and (
            type(max_device_gpu_used_bytes) is not int or
            not 0 <= max_device_gpu_used_bytes <= 2**42 or
            not callable(gpu_probe)):
            raise ValueError("GPU budget requires trusted device sampler")
        self.index = index
        self.pid = pid
        self.world_id = world_id
        self.revision = revision
        self.max_process_rss_bytes = max_process_rss_bytes
        self.gpu_probe = gpu_probe
        self.max_device_gpu_used_bytes = max_device_gpu_used_bytes
        self._context = None
        self.session = None
        self.closed = False
        self._last_receipt = None
        self._planner = FilmWorldShotPlanner(index)
        self._shot_layer = None
        self._shot_layer_sha256 = None

    def __enter__(self):
        if self.closed or self.session is not None:
            raise RuntimeError("World shot working-set session may only open once")
        self._context = OpenUSDWorldComposer(self.index).open(
            self.pid, self.world_id, self.revision)
        self.session = self._context.__enter__()
        return self

    def close(self):
        if not self.closed:
            if self._context is not None:
                self._context.__exit__(None,None,None)
            self._shot_layer = None
            self.session = None
            self.closed = True

    def _new_disposable_shot_layer(self):
        """Separate stronger preview opinions from the source USD world."""
        from pxr import Sdf
        self.session._check()
        stage = self.session.stage
        # USD root-layer opinions are stronger than their own sublayers.
        # The Stage SESSION layer is stronger than the world root; using a
        # sublayer of it makes a genuine non-destructive shot override.
        session_layer = stage.GetSessionLayer()
        if self._shot_layer is not None:
            old_id = self._shot_layer.identifier
            if old_id in session_layer.subLayerPaths:
                session_layer.subLayerPaths.remove(old_id)
        layer = Sdf.Layer.CreateAnonymous("nvp_film01d_director_look.usda")
        session_layer.subLayerPaths.insert(0,layer.identifier)
        self._shot_layer = layer
        self._shot_layer_sha256 = sha256(
            layer.ExportToString().encode("utf8")).hexdigest()
        return layer

    def discard_temporary_look(self):
        """Undo ONLY preview opinions; never change FilmIndex source USD."""
        if self.closed or self.session is None:
            raise RuntimeError("Original source shot working set is closed")
        self._new_disposable_shot_layer()
        return {
            "state":"DIRECTOR_PREVIEW_REVERTED",
            "original_world_unchanged":True,
            "film_take_modified":False,
        }

    def query_loaded_scene(self):
        """Short semantic source query, not an editable raw USD dump."""
        if self.closed or self.session is None:
            raise RuntimeError("Original USD film session is closed")
        loaded=self.session.receipt()["loaded_set_names"]
        return _source_query(self.index,self.pid,self.session,loaded)

    def __exit__(self, *args):
        self.close()

    def _resource_sample(self):
        rss = _rss_bytes()
        if self.max_process_rss_bytes is not None:
            if rss is None:
                raise RuntimeError("Real OS process RSS unavailable; cannot enforce budget")
            if rss > self.max_process_rss_bytes:
                raise MemoryError("Measured NVP process RSS exceeds editor shot budget")
        result = {"rss_process_bytes": rss,
                  "rss_is_process_wide_not_usd_only": True,
                  "gpu_device_used_bytes": None,
                  "gpu_device_total_bytes": None,
                  "gpu_is_stage_attributable": False}
        if self.gpu_probe is not None:
            raw = self.gpu_probe()
            if (type(raw) is not dict or
                set(raw) not in (
                    {"device_id","used_bytes","total_bytes"},
                    {"device_id","used_bytes","total_bytes","source","scope"},
                ) or
                type(raw["device_id"]) is not str or not raw["device_id"] or
                type(raw["used_bytes"]) is not int or
                type(raw["total_bytes"]) is not int or
                not 0 <= raw["used_bytes"] <= raw["total_bytes"]):
                raise RuntimeError("Trusted GPU device measurement is not valid")
            result["gpu_device_used_bytes"] = raw["used_bytes"]
            result["gpu_device_total_bytes"] = raw["total_bytes"]
            result["gpu_device_id"] = raw["device_id"]
            result["gpu_telemetry_source"] = raw.get("source","unlabeled_host_callback")
            result["gpu_measurement_scope"] = raw.get("scope","host_callback")
            if (self.max_device_gpu_used_bytes is not None and
                raw["used_bytes"] > self.max_device_gpu_used_bytes):
                raise MemoryError("Actual GPU device use exceeds requested working-set budget")
        return result

    def _persist(self, receipt_id, doc, shot_id, shot_revision):
        return self.index.register_revision(
            self.pid, receipt_id, "presentation", doc,
            expected_revision=0,
            dependencies=[
                {"object_id":self.world_id, "revision":self.revision,
                 "role":"world"},
                {"object_id":shot_id,"revision":shot_revision,"role":"camera"},
            ])

    def transition(self, shot_id, shot_revision, *, receipt_id,
                   should_cancel=None):
        if self.closed or self.session is None:
            raise RuntimeError("An active original USD film working set is required")
        _id(receipt_id,"durable shot working-set receipt")
        if should_cancel is not None and not callable(should_cancel):
            raise TypeError("Trusted host cancellation callback required")
        original = self._planner.inspect(
            self.pid,shot_id,shot_revision,
            expected_world_sha=self.session.record["document_sha256"])
        doc = original["data"]
        choice = _preload_choices(doc)
        required = set(choice["required_sets"])
        selected = required | set(choice["prefetched_sets"])
        start = perf_counter()
        deps = {
            "format": RECEIPT_FORMAT,
            "source_camera_plan_sha256": original["document_sha256"],
            "source_world_sha256": self.session.record["document_sha256"],
            "original_camera_set": doc["camera_set"],
            "original_camera_prim": doc["camera_prim_path"],
            "director_required_sets": sorted(required),
            "prefetched_sets": choice["prefetched_sets"],
            "skipped_optional_set_names": choice["skipped_optional_set_names"],
            "renderer_frames_produced": False,
            "installed_editor_ui_verified": False,
            "source_frozen_take_modified": False,
        }
        try:
            before = self._resource_sample()
            current = set(self.session.receipt()["loaded_set_names"])
            if should_cancel is not None and should_cancel():
                raise InterruptedError("Trusted director interrupted shot set preparation")
            # Preflight works from ONLY source-pinned world set names.
            if not selected <= {x["name"] for x in self.session.structure["sets"]}:
                raise PermissionError("Shot requested a source world set that does not exist")
            # Unload non-required sets first to bound transient working-set
            # pressure; the new camera must be re-verified before receipt.
            if current - selected:
                self.session.unload(sorted(current - selected))
            if should_cancel is not None and should_cancel():
                raise InterruptedError("Director interrupted before loading next camera set")
            needed = selected - set(self.session.receipt()["loaded_set_names"])
            if needed:
                self.session.load(sorted(needed))
            if should_cancel is not None and should_cancel():
                raise InterruptedError("Director interrupted after loading original set")
            actual_path, actual_positions = _camera_native(
                self.session,doc["camera_set"],doc["camera_prim_path"],
                doc["camera_sample_ticks"])
            if (actual_path != doc["native_composed_camera_path"] or
                len(actual_positions) != len(doc["original_camera_positions_m"])
                or any(math.dist(p,q) > 1e-6 for p,q in zip(
                    actual_positions,doc["original_camera_positions_m"]))):
                raise PermissionError("Original moving camera no longer matches shot source")
            from pxr import Usd
            overlay=self._new_disposable_shot_layer()
            # The model/director only passes typed, source-verified look
            # choices. USD writes every opinion to a dedicated ephemeral
            # shot layer that can be discarded without touching originals.
            with Usd.EditContext(self.session.stage, overlay):
                for name, look in doc["director_looks"].items():
                    self.session.switch_variant(name,look)
            self._shot_layer_sha256=sha256(
                overlay.ExportToString().encode("utf8")).hexdigest()
            after = self._resource_sample()
            selected_actual = sorted(self.session.receipt()["loaded_set_names"])
            if not required <= set(selected_actual) or len(selected_actual) > doc["max_loaded_sets"]:
                raise RuntimeError("Native USD shot omitted an original required set")
            scene_query = _source_query(
                self.index,self.pid,self.session,selected_actual)
            result = {
                **deps,
                "state": "SUCCEEDED_SOURCE_WORKING_SET",
                "sets_actually_loaded": selected_actual,
                "camera_positions_reopened_exactly": True,
                "director_disposable_look_layer_sha256":self._shot_layer_sha256,
                "director_look_layer_authoritative":False,
                "source_semantic_scene_summary": scene_query,
                "load_transition_seconds": round(perf_counter()-start,6),
                "resource_before":before,"resource_after":after,
                "actual_native_working_set_receipt":self.session.receipt(),
                "gpu_attributable_to_stage_verified":False,
                "native_renderer_pixels_verified":False,
            }
            self._persist(receipt_id,result,shot_id,shot_revision)
            self._last_receipt = result
            return result
        except Exception as exc:
            # A failed in-memory transition may have partially loaded USD;
            # destroy this disposable context. Never label it successful.
            self.close()
            state = "INTERRUPTED" if isinstance(exc,InterruptedError) else "FAILED"
            try:
                self._persist(receipt_id,{
                    **deps,"state":state,
                    "native_working_set_not_accepted":True,
                    "failure_type":type(exc).__name__,
                    "recoverable_from_original_film_sources":True,
                    "native_renderer_pixels_verified":False,
                },shot_id,shot_revision)
            except Exception:
                # Preserve the actual error rather than hiding that durable
                # recording itself failed. Next host must query the original
                # receipt identity rather than assume a record exists.
                raise
            raise

    @property
    def last_receipt(self):
        return self._last_receipt
