"""USD-FILM-01: project-scoped, SHA-verified reusable film world composition.

Reuses existing FilmIndex source scene / asset revisions, not another 3D
asset database. Source authoring metadata contains ONLY exact project-local
IDs/revisions and SHA-256 digests. Relative USD asset paths are created in
private per-open staging and destroyed on context exit. Source stage snapshots
are temporarily flattened so original legacy in-memory USD references are
resolved under the existing FilmIndex authority, while new world-level
references, payload arcs, variants and PointInstancers remain native USD.

This is an editable film set/world source, not a renderer, asset importer,
game engine, legal subsystem, physics solver or digital twin.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from time import perf_counter

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge, _usd
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT = "nvp.usd_film01.composed_film_world.v1"
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,49}\Z")
MAX_SETS = 8
MAX_PROPS = 40
MAX_VARIANTS = 8
MAX_INSTANCERS = 12
MAX_INSTANCES = 2048
MAX_TOTAL_INSTANCES = 4096
MAX_STAGING_BYTES = 128 * 1024 * 1024
MAX_LAYER_BYTES = 24 * 1024 * 1024
MAX_SCENE_PRIMS = 256
COORDINATE_SYSTEM = "meters_Z_up"
ALLOWED_SOURCE_TYPES = {"asset", "scene"}


def _token(value, what):
    if type(value) is not str or not TOKEN.fullmatch(value):
        raise ValueError("Invalid film world " + what)
    return value


def _exact_rev(value):
    if type(value) is not int or value < 1:
        raise ValueError("Film world sources need an existing exact revision")
    return value


def _position(value):
    if (type(value) is not list or len(value) != 3 or
        any(type(x) not in (int, float) or not math.isfinite(x)
            or abs(x) > 1_000_000 for x in value)):
        raise ValueError("Bounded real scene coordinates in meters required")
    return [float(x) for x in value]


def _record_source(index, pid, kind, source_id, revision, *,
                   sealed_scene=None):
    _id(source_id, "film source")
    _exact_rev(revision)
    if sealed_scene is not None:
        # Only used for NOT-YET-LOADED source scene payloads. Verify the
        # authoritative FilmIndex document cheaply without reopening the
        # original USD scene, geometry and its images until explicitly loaded.
        record = index.read_revision(pid,source_id,revision)
        if (kind != "scene" or record["kind"] != "scene" or
            sealed_scene.get("kind") != "scene" or
            sealed_scene.get("id") != source_id or
            sealed_scene.get("revision") != revision or
            sealed_scene.get("document_sha256") != record["document_sha256"] or
            sealed_scene.get("source_blob_sha256") !=
                record["data"]["layout_layer_sha256"] or
            sealed_scene.get("root_prim") != "/World" or
            type(sealed_scene.get("layer_sha256")) is not str):
            raise PermissionError("Lazy source set is not a sealed FilmIndex scene")
        _sha(sealed_scene["layer_sha256"])
        return {**sealed_scene,"bytes":None,"texture_files":{}}
    texture_files = {}
    if kind == "scene":
        record, stage = OpenUSDSceneBridge(index).open(pid, source_id, revision)
        from pxr import UsdGeom
        if (record["kind"] != "scene" or
            abs(UsdGeom.GetStageMetersPerUnit(stage) - 1.0) > 1e-9 or
            str(UsdGeom.GetStageUpAxis(stage)) != "Z"):
            raise ValueError("Film world requires native 1-meter, Z-up source scenes")
        if (len(record["data"]["prim_roles"]) > MAX_SCENE_PRIMS or
            any(v.get("asset_id") == source_id for v in
                record["data"].get("asset_bindings", []))):
            raise ValueError("Unsupported or cyclic original scene source")
        # This is a temporary snapshot of NVP's *already-composed* original
        # scene, not the authoritative edited scene. Its actual original
        # revisions remain referenced individually by the world document.
        flattened = stage.Flatten(addSourceFileComment=False)
        plain = _usd()[2].Stage.Open(flattened)
        root = plain.GetPrimAtPath("/World")
        if not root or not root.IsDefined():
            raise RuntimeError("Original NVP scene lacks a native /World root")
        plain.SetDefaultPrim(root)
        from backend.nvp_usd_film01c_texture import (
            derive_texture_resolved_layer,
        )
        contents, texture_files = derive_texture_resolved_layer(
            index,pid,plain,source_kind="scene",source_record=record)
        root_prim = "/World"
    else:
        record, layer = OpenUSDAssetRegistry(index).open(pid, source_id, revision)
        if record["kind"] != "asset":
            raise ValueError("World asset source is not genuine NVP asset")
        from backend.nvp_usd_film01c_texture import (
            derive_texture_resolved_layer,
        )
        from pxr import Usd
        contents, texture_files = derive_texture_resolved_layer(
            index,pid,Usd.Stage.Open(layer),
            source_kind="asset",source_record=record)
        root_prim = "/Asset"
    if not 0 < len(contents) <= MAX_LAYER_BYTES:
        raise RuntimeError("Actual source USD exceeds bounded staging size")
    descriptor = {
        "kind": kind,
        "id": source_id,
        "revision": revision,
        "document_sha256": record["document_sha256"],
        "layer_sha256": sha256(contents).hexdigest(),
        "source_blob_sha256": (
            record["data"]["layer_sha256"] if kind == "asset"
            else record["data"]["layout_layer_sha256"]),
        "root_prim": root_prim,
        "bytes": contents,
        "texture_files": texture_files,
    }
    if texture_files:
        descriptor["texture_sha256"] = sorted(texture_files)
    return descriptor


def _normalize(index, pid, sets, props, variants, instancers,
               *, sealed_sources=None):
    if (type(sets) is not list or not 1 <= len(sets) <= MAX_SETS
        or type(props) is not list or len(props) > MAX_PROPS
        or type(variants) is not list or len(variants) > MAX_VARIANTS
        or type(instancers) is not list or len(instancers) > MAX_INSTANCERS):
        raise ValueError("Film world assembly exceeds typed spatial budgets")
    seen = set()
    sources = {}
    def use(kind, source_id, revision):
        key = (kind, source_id, revision)
        if key not in sources:
            pinned = (sealed_sources or {}).get(
                "|".join(map(str,key))) if kind == "scene" else None
            if sealed_sources is not None and kind == "scene" and pinned is None:
                raise PermissionError("Unrecognized scene payload in saved FilmIndex world")
            sources[key] = _record_source(
                index, pid, kind, source_id, revision,
                sealed_scene=pinned)
        return sources[key]
    def name(item, required, category):
        if type(item) is not dict or set(item) != required:
            raise ValueError("Incorrect " + category + " source specification")
        token = _token(item["name"], category + " name")
        if (category, token) in seen:
            raise ValueError("Duplicate destination in original world")
        seen.add((category, token))
        return token
    assembled = {"sets": [], "props": [], "variants": [], "instancers": []}
    for item in sets:
        token = name(item, {"name", "scene_id", "scene_revision"}, "set")
        src = use("scene", item["scene_id"], item["scene_revision"])
        assembled["sets"].append({
            "name": token, "scene_id": src["id"],
            "scene_revision": src["revision"],
            "scene_sha256": src["document_sha256"],
        })
    for item in props:
        token = name(
            item, {"name", "asset_id", "asset_revision", "position_m", "load"},
            "prop")
        if item["load"] not in ("reference", "payload"):
            raise ValueError("Props use native reference or payload mode")
        src = use("asset", item["asset_id"], item["asset_revision"])
        assembled["props"].append({
            "name": token, "asset_id": src["id"],
            "asset_revision": src["revision"],
            "asset_sha256": src["document_sha256"],
            "position_m": _position(item["position_m"]),
            "load": item["load"],
        })
    for item in variants:
        token = name(item, {"name", "position_m", "options", "selected"}, "variant")
        choices = item["options"]
        if (type(choices) is not list or not 2 <= len(choices) <= 6
            or type(item["selected"]) is not str):
            raise ValueError("Film variant requires two to six real source options")
        labels = set()
        entries = []
        for choice in choices:
            if type(choice) is not dict or set(choice) != {
                "name", "asset_id", "asset_revision"
            }:
                raise ValueError("Variant source must be an exact NVP asset")
            label = _token(choice["name"], "look name")
            if label in labels:
                raise ValueError("Duplicate variant options")
            labels.add(label)
            src = use("asset", choice["asset_id"], choice["asset_revision"])
            entries.append({
                "name": label, "asset_id": src["id"],
                "asset_revision": src["revision"],
                "asset_sha256": src["document_sha256"],
            })
        if item["selected"] not in labels:
            raise ValueError("No original selected director variant")
        assembled["variants"].append({
            "name": token, "selected": item["selected"],
            "position_m": _position(item["position_m"]),
            "options": sorted(entries, key=lambda o:o["name"]),
        })
    total_instances = 0
    for item in instancers:
        token = name(
            item, {"name", "asset_id", "asset_revision", "positions_m"},
            "instancer")
        positions = item["positions_m"]
        if type(positions) is not list or not 1 <= len(positions) <= MAX_INSTANCES:
            raise ValueError("Bounded environment instances required")
        total_instances += len(positions)
        if total_instances > MAX_TOTAL_INSTANCES:
            raise ValueError("Too many world instances for one working set")
        src = use("asset", item["asset_id"], item["asset_revision"])
        assembled["instancers"].append({
            "name": token, "asset_id": src["id"],
            "asset_revision": src["revision"],
            "asset_sha256": src["document_sha256"],
            "positions_m": [_position(p) for p in positions],
        })
    for entries in assembled.values():
        entries.sort(key=lambda x:x["name"])
    if len(sources) > 70:
        raise ValueError("World exceeds typed FilmIndex source dependency budget")
    return assembled, sources


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",",":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _rss_bytes():
    """Native process RSS snapshot, not process-attributable USD peak VRAM."""
    try:
        if os.name == "posix":
            status = Path("/proc/self/status")
            if status.is_file():
                for line in status.read_text("ascii").splitlines():
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        elif os.name == "nt":
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            c = Counters()
            c.cb = ctypes.sizeof(c)
            proc = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                proc, ctypes.byref(c), c.cb):
                return int(c.WorkingSetSize)
    except (OSError, ValueError, ImportError, AttributeError):
        pass
    return None


class WorldSession:
    """One bounded real USD working set. Always use with context manager."""
    def __init__(self, tmp, record, stage, structure, sources, staged_bytes,
                 stage_initial_ms):
        self._tmp = tmp
        self.record = record
        self.stage = stage
        self.structure = structure
        self.sources = sources
        self.staged_bytes = staged_bytes
        self.stage_initial_ms = stage_initial_ms
        self.closed = False
        self.load_receipts = []
        self.rss_unloaded_bytes = _rss_bytes()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if not self.closed:
            self.stage = None
            if self._tmp is not None:
                self._tmp.cleanup()
            self.closed = True

    def _check(self):
        if self.closed or self.stage is None:
            raise RuntimeError("Expired native world staging cannot be reused")

    def load(self, set_names):
        self._check()
        if (type(set_names) is not list or
            any(type(x) is not str for x in set_names) or
            len(set_names) != len(set(set_names))):
            raise ValueError("Explicit unique scene payload set names required")
        valid = {item["name"] for item in self.structure["sets"]}
        if not set(set_names) <= valid:
            raise PermissionError("No original scene payload has that name")
        before = _rss_bytes()
        started = perf_counter()
        paths = []
        for name in set_names:
            path = "/World/Sets/" + name
            self.stage.Load(path)
            prim = self.stage.GetPrimAtPath(path)
            if not prim or not prim.IsLoaded():
                raise RuntimeError("Native OpenUSD payload did not become loaded")
            paths.append(path)
        duration_ms = round(1000 * (perf_counter()-started),3)
        after = _rss_bytes()
        receipt = {
            "operation": "load", "sets": sorted(set_names),
            "elapsed_ms": duration_ms,
            "rss_before_bytes": before, "rss_after_bytes": after,
            "native_process_rss_not_usd_only": True,
            "native_gpu_vram_measured": False,
        }
        self.load_receipts.append(receipt)
        return receipt

    def unload(self, set_names):
        self._check()
        valid = {item["name"] for item in self.structure["sets"]}
        if (type(set_names) is not list or len(set_names) != len(set(set_names))
            or not set(set_names) <= valid):
            raise ValueError("Only genuine unique source sets can be unloaded")
        start = perf_counter()
        for name in set_names:
            path = "/World/Sets/" + name
            self.stage.Unload(path)
            prim = self.stage.GetPrimAtPath(path)
            if not prim or prim.IsLoaded():
                raise RuntimeError("Native USD set payload did not unload")
        result = {"operation": "unload", "sets": sorted(set_names),
                  "elapsed_ms": round(1000*(perf_counter()-start),3),
                  "rss_after_bytes": _rss_bytes(),
                  "native_gpu_vram_measured": False}
        self.load_receipts.append(result)
        return result

    def _prop_payload_action(self, prop_names, *, load):
        self._check()
        allowed = {
            item["name"] for item in self.structure["props"]
            if item["load"] == "payload"
        }
        if (type(prop_names) is not list or
            any(type(x) is not str for x in prop_names) or
            len(prop_names) != len(set(prop_names)) or
            not set(prop_names) <= allowed):
            raise ValueError("Only explicitly authored lazy prop payloads may be changed")
        started = perf_counter()
        for name in prop_names:
            path = "/World/Props/" + name
            if load:
                self.stage.Load(path)
            else:
                self.stage.Unload(path)
            prim = self.stage.GetPrimAtPath(path)
            if not prim or bool(prim.IsLoaded()) != bool(load):
                raise RuntimeError("Native prop payload load/unload did not complete")
        receipt = {
            "operation": "load_props" if load else "unload_props",
            "props": sorted(prop_names),
            "elapsed_ms": round(1000*(perf_counter()-started),3),
            "rss_after_bytes": _rss_bytes(),
            "rendered_frames": False,
        }
        self.load_receipts.append(receipt)
        return receipt

    def load_props(self, prop_names):
        return self._prop_payload_action(prop_names,load=True)

    def unload_props(self, prop_names):
        return self._prop_payload_action(prop_names,load=False)

    def switch_variant(self, name, choice):
        """Ephemeral shot look selection; publishing requires NEW world revision."""
        self._check()
        options = {
            item["name"]: item for item in self.structure["variants"]
        }
        if type(name) is not str or type(choice) is not str or name not in options:
            raise ValueError("Director look must target an authored world variant")
        allowed = {item["name"] for item in options[name]["options"]}
        if choice not in allowed:
            raise ValueError("Director look is not a source-authored variant")
        prim = self.stage.GetPrimAtPath("/World/Variants/" + name)
        variant = prim.GetVariantSets().GetVariantSet("look")
        if (not variant or not variant.SetVariantSelection(choice) or
            variant.GetVariantSelection() != choice):
            raise RuntimeError("Native original world look did not switch")
        return {
            "variant": name, "selected": choice,
            "persists_only_if_new_world_revision_published": True,
            "original_source_take_changed": False,
        }

    def receipt(self):
        self._check()
        return {
            "format": "nvp.usd_film01.native_world_working_set.v1",
            "world_document_sha256": self.record["document_sha256"],
            "loaded_set_names": [s["name"] for s in self.structure["sets"]
                 if self.stage.GetPrimAtPath(
                     "/World/Sets/" + s["name"]).IsLoaded()],
            "source_staging_file_count": len(self.sources),
            "source_staging_bytes": self.staged_bytes,
            "usd_stage_load_none_ms": self.stage_initial_ms,
            "rss_unloaded_bytes": self.rss_unloaded_bytes,
            "rss_current_bytes": _rss_bytes(),
            "load_history": list(self.load_receipts),
            "usd_delegates_or_pixels_rendered": False,
            "usd_native_gpu_memory_verified": False,
            "original_frozen_take_modified": False,
        }


class OpenUSDWorldComposer:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Original film index is required")
        self.index = index

    def _assemble(self, pid, doc, staging_dir):
        Gf, Sdf, Usd, UsdGeom = _usd()
        from pxr import Vt
        # A committed manifest contains verified source hashes in addition
        # to the public authoring arguments. Strip ONLY those exact pinned
        # hash fields, re-derive from real FilmIndex source bytes, then
        # require byte-for-byte semantic equality to the stored manifest.
        authored_sets = [
            {k:v for k,v in x.items() if k != "scene_sha256"}
            for x in doc["sets"]]
        authored_props = [
            {k:v for k,v in x.items() if k != "asset_sha256"}
            for x in doc["props"]]
        authored_variants = [
            {**{k:v for k,v in x.items() if k not in ("options",)},
             "options":[{k:v for k,v in opt.items()
                         if k != "asset_sha256"} for opt in x["options"]]}
            for x in doc["variants"]]
        authored_instancers = [
            {k:v for k,v in x.items() if k != "asset_sha256"}
            for x in doc["instancers"]]
        pieces, sources = _normalize(
            self.index, pid, authored_sets, authored_props,
            authored_variants, authored_instancers,
            sealed_sources=(doc["sources"] if doc.get("world_root_sha256")
                            else None))
        if pieces != {key: doc[key] for key in pieces}:
            raise PermissionError("World original source manifest changed since commit")
        for key, src in sources.items():
            if doc["sources"].get("|".join(map(str,key))) != {
                    k:v for k,v in src.items()
                    if k not in ("bytes","texture_files")}:
                raise PermissionError("Original FilmIndex world asset hashes changed")
        if len(doc["sources"]) != len(sources):
            raise PermissionError("Original world source set was replaced")
        staging = Path(staging_dir)
        (staging / "scenes").mkdir()
        (staging / "assets").mkdir()
        (staging / "textures").mkdir()
        from backend.nvp_usd_film01c_texture import write_verified_texture_files
        written = set()
        total_bytes = 0
        paths = {}
        for key, src in sorted(sources.items()):
            kind = src["kind"]
            base = ("scenes" if kind == "scene" else "assets")
            rel = base + "/" + src["layer_sha256"] + ".usda"
            dest = staging / rel
            if rel not in written:
                data = src["bytes"]
                if data is not None:
                    total_bytes += len(data)
                    if total_bytes > MAX_STAGING_BYTES:
                        raise RuntimeError("Bounded private world staging budget exceeded")
                    with dest.open("xb") as output:
                        output.write(data)
                    written.add(rel)
                    write_verified_texture_files(
                        staging / "textures",src.get("texture_files",{}))
            paths[key] = "./" + rel
        dest = staging / "world.usda"
        stage = Usd.Stage.CreateNew(str(dest))
        stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
        UsdGeom.SetStageMetersPerUnit(stage,1.0)
        UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
        world = UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(world.GetPrim())
        for group in ("Sets","Props","Variants","Prototypes","Instancers"):
            UsdGeom.Xform.Define(stage, "/World/" + group)
        for item in pieces["sets"]:
            path = "/World/Sets/" + item["name"]
            prim = UsdGeom.Xform.Define(stage,path).GetPrim()
            arc = paths[("scene",item["scene_id"],item["scene_revision"])]
            if not prim.GetPayloads().AddPayload(arc,Sdf.Path("/World")):
                raise RuntimeError("Could not author native film set payload")
        for item in pieces["props"]:
            path = "/World/Props/" + item["name"]
            prim = UsdGeom.Xform.Define(stage,path)
            if not UsdGeom.XformCommonAPI(prim).SetTranslate(
                    Gf.Vec3d(*item["position_m"])):
                raise RuntimeError("Could not position reusable film set prop")
            arc = paths[("asset",item["asset_id"],item["asset_revision"])]
            if item["load"] == "reference":
                success = prim.GetPrim().GetReferences().AddReference(
                    arc,Sdf.Path("/Asset"))
            else:
                success = prim.GetPrim().GetPayloads().AddPayload(
                    arc,Sdf.Path("/Asset"))
            if not success:
                raise RuntimeError("Actual source-locked prop could not compose")
        for item in pieces["variants"]:
            path = "/World/Variants/" + item["name"]
            geom = UsdGeom.Xform.Define(stage,path)
            if not UsdGeom.XformCommonAPI(geom).SetTranslate(
                    Gf.Vec3d(*item["position_m"])):
                raise RuntimeError("Native variant prop position missing")
            choices = geom.GetPrim().GetVariantSets().AddVariantSet("look")
            for option in item["options"]:
                choices.AddVariant(option["name"])
                if not choices.SetVariantSelection(option["name"]):
                    raise RuntimeError("Could not select native source look")
                with choices.GetVariantEditContext():
                    arc = paths[("asset",option["asset_id"],option["asset_revision"])]
                    if not stage.GetPrimAtPath(path).GetReferences().AddReference(
                            arc,Sdf.Path("/Asset")):
                        raise RuntimeError("Could not author variant source reference")
            if not choices.SetVariantSelection(item["selected"]):
                raise RuntimeError("Director-selected look is not a native variant")
        for item in pieces["instancers"]:
            prototype_path = "/World/Prototypes/" + item["name"]
            proto = UsdGeom.Xform.Define(stage,prototype_path)
            arc = paths[("asset",item["asset_id"],item["asset_revision"])]
            if not proto.GetPrim().GetReferences().AddReference(
                    arc,Sdf.Path("/Asset")):
                raise RuntimeError("Instancer prototype source unavailable")
            inst = UsdGeom.PointInstancer.Define(
                stage,"/World/Instancers/" + item["name"])
            if not inst.CreatePrototypesRel().SetTargets(
                    [Sdf.Path(prototype_path)]):
                raise RuntimeError("PointInstancer has no original prototype")
            if not inst.CreateProtoIndicesAttr().Set(
                    Vt.IntArray([0] * len(item["positions_m"]))):
                raise RuntimeError("Could not assign native prototype indices")
            if not inst.CreatePositionsAttr().Set(
                    Vt.Vec3fArray([
                        Gf.Vec3f(*p) for p in item["positions_m"]])):
                raise RuntimeError("Could not author instance positions")
        layer_string = stage.GetRootLayer().ExportToString().encode("utf8")
        if len(layer_string) > MAX_LAYER_BYTES:
            raise RuntimeError("Original world root USD layer too large")
        original_sha = sha256(layer_string).hexdigest()
        if doc.get("world_root_sha256") not in (None, original_sha):
            raise PermissionError("Source-authored world composition changed since commit")
        if not stage.GetRootLayer().Save():
            raise RuntimeError("Original film world USD root not saved")
        init_start = perf_counter()
        reopened = Usd.Stage.Open(str(dest),load=Usd.Stage.LoadNone)
        elapsed = round(1000*(perf_counter()-init_start),3)
        if not reopened or not reopened.GetPrimAtPath("/World").IsDefined():
            raise RuntimeError("Original world USD cannot be reopened unloaded")
        for item in pieces["sets"]:
            prim = reopened.GetPrimAtPath("/World/Sets/" + item["name"])
            if not prim or prim.IsLoaded():
                raise RuntimeError("World source set payload must start unloaded")
        return reopened, original_sha, pieces, sources, total_bytes, elapsed

    def publish(self, pid, world_id, *, sets, props=None, variants=None,
                instancers=None, expected_revision=0):
        _require_pid(pid)
        _id(world_id,"persistent film world")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Invalid expected film-world revision")
        props = [] if props is None else props
        variants = [] if variants is None else variants
        instancers = [] if instancers is None else instancers
        pieces, sources = _normalize(
            self.index,pid,sets,props,variants,instancers)
        doc = {
            "format": FORMAT, "coordinate_system": COORDINATE_SYSTEM,
            "ticks_per_second": TICKS_PER_SECOND,
            **pieces,
            "sources": {
                "|".join(map(str,key)):{
                    field: val for field,val in source.items()
                    if field not in ("bytes","texture_files")
                } for key,source in sorted(sources.items())
            },
            "external_source_paths_authoritative": False,
            "film_frozen_takes_modified": False,
            "lazy_sets_default_unloaded": True,
            "renderer_pixels_verified": False,
        }
        with TemporaryDirectory(prefix="nvp-usd-world-author-") as tmp:
            stage, source_sha, _, _, _, _ = self._assemble(pid,doc,tmp)
            if stage is None:
                raise RuntimeError("Real native USD composition failed")
            doc["world_root_sha256"] = source_sha
        edges = [
            {"object_id":kind_id, "revision":rev, "role":kind}
            for kind,kind_id,rev in sorted(sources)
        ]
        def guard(db):
            for src in sources.values():
                row = db.execute("""
                    SELECT document_sha FROM film_object_revisions
                    WHERE project_id=? AND object_id=? AND revision=?
                """,(pid,src["id"],src["revision"])).fetchone()
                if row is None or row["document_sha"] != src["document_sha256"]:
                    raise RuntimeError("World source changed before FilmIndex commit")
        return self.index.register_revision(
            pid,world_id,"world",doc,
            expected_revision=expected_revision,
            dependencies=edges,precommit_guard=guard)

    @contextmanager
    def open(self, pid, world_id, revision):
        _require_pid(pid)
        _id(world_id,"persistent film world")
        _exact_rev(revision)
        record = self.index.read_revision(pid,world_id,revision)
        doc = record["data"]
        if (record["kind"] != "world" or doc.get("format") != FORMAT or
            doc.get("coordinate_system") != COORDINATE_SYSTEM or
            doc.get("ticks_per_second") != TICKS_PER_SECOND or
            doc.get("external_source_paths_authoritative") is not False or
            doc.get("lazy_sets_default_unloaded") is not True or
            doc.get("renderer_pixels_verified") is not False or
            type(doc.get("sources")) is not dict):
            raise PermissionError("Not an original, source-locked NVP USD world revision")
        with TemporaryDirectory(prefix="nvp-usd-world-open-") as tmp:
            stage, _, structure, sources, staged_bytes, stage_ms = \
                self._assemble(pid,doc,tmp)
            session = WorldSession(
                None,record,stage,structure,sources,staged_bytes,stage_ms)
            # This context owns all real USD staging. Keep stage alive only
            # while the private workspace and its checked files exist.
            try:
                yield session
            finally:
                session.stage = None
                session.closed = True
