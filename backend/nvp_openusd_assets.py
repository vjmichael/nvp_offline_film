"""USD-02A: immutable, reusable NVP-authored OpenUSD geometry.

Only typed procedural primitives are accepted in this first asset pathway.
No arbitrary USD file, external reference, texture or asset resolver can be
passed through the FilmIndex boundary. Source layers are SHA-addressed blobs.
"""
from __future__ import annotations

import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import (
    _usd, _layer_from_text, LAYER_TYPE, MAX_USD_LAYER_BYTES)

FORMAT = "nvp.asset.openusd.geometry.v1"
KINDS = frozenset(("cube", "sphere"))
MAX_SIZE_METERS = 1000.0


class OpenUSDAssetRegistry:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Native FilmIndex required")
        self.index = index

    def publish(self, project_id, asset_id, *, shape, size_m,
                expected_revision=0):
        _require_pid(project_id)
        _id(asset_id, "reusable asset ID")
        if shape not in KINDS:
            raise ValueError("Unsupported native authored geometry")
        if (type(size_m) not in (float, int) or
            not math.isfinite(size_m) or
            not 0 < size_m <= MAX_SIZE_METERS):
            raise ValueError("Geometry size must be finite and positive")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Invalid expected asset revision")
        Gf, Sdf, Usd, UsdGeom = _usd()
        layer = Sdf.Layer.CreateAnonymous("nvp_asset.usda")
        stage = Usd.Stage.Open(layer)
        root = UsdGeom.Xform.Define(stage, "/Asset")
        stage.SetDefaultPrim(root.GetPrim())
        if shape == "cube":
            obj = UsdGeom.Cube.Define(stage, "/Asset/Geometry")
            obj.GetSizeAttr().Set(float(size_m))
        else:
            obj = UsdGeom.Sphere.Define(stage, "/Asset/Geometry")
            obj.GetRadiusAttr().Set(float(size_m) / 2)
        payload = layer.ExportToString().encode("utf-8")
        if not 0 < len(payload) <= MAX_USD_LAYER_BYTES:
            raise RuntimeError("NVP-owned asset exceeds bounded USD layer size")
        blob_sha = self.index.put_blob(project_id, payload, media_type=LAYER_TYPE)
        document = {
            "format": FORMAT, "source": "nvp_authored_procedural_geometry",
            "shape": shape, "size_m": float(size_m),
            "layer_sha256": blob_sha, "root_prim": "/Asset",
            "external_references": False,
        }
        def guard(db):
            row = db.execute("""SELECT 1 FROM film_blob_refs
                WHERE project_id=? AND sha256=?""",
                (project_id, blob_sha)).fetchone()
            if row is None:
                raise RuntimeError("Referenced procedural USD layer missing at commit")
        return self.index.register_revision(
            project_id, asset_id, "asset", document,
            expected_revision=expected_revision, dependencies=[],
            precommit_guard=guard)

    def import_rigged_actor(self, project_id, asset_id, source, *,
                            actor_id, approve_import, creator_event):
        """Import reviewed original USD; no external files or model authority."""
        from backend.nvp_p1f_imported_actor import import_actor
        return import_actor(
            self.index, project_id, asset_id, source, actor_id=actor_id,
            approve_import=approve_import, creator_event=creator_event)

    def open(self, project_id, asset_id, revision):
        record = self.index.read_revision(project_id, asset_id, revision)
        doc = record["data"]
        from backend.nvp_p1f_imported_actor import FORMAT as RIGGED_FORMAT,open_actor
        if doc.get("format")==RIGGED_FORMAT:
            return open_actor(self.index,project_id,asset_id,revision)
        if (record["kind"] != "asset" or
            doc.get("format") != FORMAT or
            doc.get("source") != "nvp_authored_procedural_geometry" or
            doc.get("external_references") is not False or
            doc.get("root_prim") != "/Asset" or
            doc.get("shape") not in KINDS):
            raise RuntimeError("Object is not an approved NVP-authored USD primitive")
        size = doc.get("size_m")
        if type(size) not in (float, int) or not 0 < size <= MAX_SIZE_METERS:
            raise RuntimeError("Malformed immutable geometry asset size")
        _, Sdf, Usd, UsdGeom = _usd()
        blob = self.index.get_blob(project_id, doc["layer_sha256"])
        if not 0 < len(blob) <= MAX_USD_LAYER_BYTES:
            raise RuntimeError("Bounded USD asset layer corrupted")
        layer = _layer_from_text(blob.decode("utf-8"), "nvp_asset_reopen.usda", Sdf)
        if layer.subLayerPaths or layer.GetExternalReferences():
            raise RuntimeError("USD asset unexpectedly refers to external layers")
        stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
        root = stage.GetPrimAtPath("/Asset")
        geometry = stage.GetPrimAtPath("/Asset/Geometry")
        if not root or not root.IsA(UsdGeom.Xform):
            raise RuntimeError("Missing canonical reusable USD asset root")
        expected_type = UsdGeom.Cube if doc["shape"] == "cube" else UsdGeom.Sphere
        if not geometry or not geometry.IsA(expected_type):
            raise RuntimeError("NVP asset geometry differs from frozen type")
        observed = (UsdGeom.Cube(geometry).GetSizeAttr().Get()
                    if doc["shape"] == "cube" else
                    2 * UsdGeom.Sphere(geometry).GetRadiusAttr().Get())
        if not math.isclose(float(observed), float(size), rel_tol=0, abs_tol=1e-7):
            raise RuntimeError("USD asset dimensions disagree with FilmIndex")
        return record, layer
