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
KINDS = frozenset(("cube", "sphere", "mesh"))
MAX_MESH_VERTICES = 2048
MAX_MESH_TRIANGLES = 4096
MAX_SIZE_METERS = 1000.0


class OpenUSDAssetRegistry:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Native FilmIndex required")
        self.index = index

    def publish(self, project_id, asset_id, *, shape, size_m,
                expected_revision=0, points=None, triangles=None,
                preview_material=None):
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
        if shape=="mesh":
            if (type(points) is not list or
                    not 3<=len(points)<=MAX_MESH_VERTICES or
                    type(triangles) is not list or
                    not 1<=len(triangles)<=MAX_MESH_TRIANGLES):
                raise ValueError("Bounded authored mesh vertices/triangles required")
            if any(type(p) is not list or len(p)!=3 or
                   any(type(v) not in (int,float) or
                       not math.isfinite(v) or abs(v)>size_m
                       for v in p) for p in points):
                raise ValueError("Mesh vertices must be finite local positions")
            if any(type(t) is not list or len(t)!=3 or
                   any(type(i) is not int or i<0 or i>=len(points)
                       for i in t) or len(set(t))!=3 for t in triangles):
                raise ValueError("Mesh needs nondegenerate triangle indices")
        elif points is not None or triangles is not None:
            raise ValueError("Procedural cube/sphere does not accept mesh data")
        authored_material=None
        if preview_material is not None:
            if (type(preview_material) is not dict or
                set(preview_material)!={
                    "base_color_rgb","roughness","metallic"}):
                raise ValueError("Only typed source USD surface parameters allowed")
            rgb=preview_material["base_color_rgb"]
            if (type(rgb) is not list or len(rgb)!=3 or
                any(type(v) not in (int,float) or not math.isfinite(v) or
                    not 0<=v<=1 for v in rgb)):
                raise ValueError("Asset source color must be finite RGB reflectance")
            controls={}
            for key in ("roughness","metallic"):
                v=preview_material[key]
                if type(v) not in (int,float) or not math.isfinite(v) or (
                        not 0<=v<=1):
                    raise ValueError("Original USD material parameter invalid: "+key)
                controls[key]=float(v)
            authored_material={"format":"nvp.original_usd_preview_surface.v1",
                "base_color_rgb":[float(x) for x in rgb],
                **controls,"material_path":"/Asset/Material",
                "roughness_metallic_authored":True,
                "texture_images_loaded":False,
                "original_source_modified":False}
        Gf, Sdf, Usd, UsdGeom = _usd()
        layer = Sdf.Layer.CreateAnonymous("nvp_asset.usda")
        stage = Usd.Stage.Open(layer)
        root = UsdGeom.Xform.Define(stage, "/Asset")
        stage.SetDefaultPrim(root.GetPrim())
        if shape == "cube":
            obj = UsdGeom.Cube.Define(stage, "/Asset/Geometry")
            obj.GetSizeAttr().Set(float(size_m))
        elif shape=="sphere":
            obj = UsdGeom.Sphere.Define(stage, "/Asset/Geometry")
            obj.GetRadiusAttr().Set(float(size_m) / 2)
        else:
            obj = UsdGeom.Mesh.Define(stage, "/Asset/Geometry")
            obj.GetPointsAttr().Set([Gf.Vec3f(*p) for p in points])
            obj.GetFaceVertexCountsAttr().Set([3]*len(triangles))
            obj.GetFaceVertexIndicesAttr().Set([
                v for triangle in triangles for v in triangle])
            obj.CreateSubdivisionSchemeAttr().Set("none")
            obj.CreateDoubleSidedAttr().Set(True)
        if authored_material is not None:
            from pxr import UsdShade
            material=UsdShade.Material.Define(stage,"/Asset/Material")
            shader=UsdShade.Shader.Define(
                stage,"/Asset/Material/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(*authored_material["base_color_rgb"]))
            for name in ("roughness","metallic"):
                shader.CreateInput(name,Sdf.ValueTypeNames.Float).Set(
                    authored_material[name])
            shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
            material.CreateSurfaceOutput().ConnectToSource(
                shader.ConnectableAPI(),"surface")
            if not UsdShade.MaterialBindingAPI.Apply(
                    obj.GetPrim()).Bind(material):
                raise RuntimeError("Cannot bind real original USD PreviewSurface")
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
        if authored_material is not None:
            document["preview_material"]=authored_material
        if shape=="mesh":
            # Keep canonical, bounded source topology alongside the verified
            # original USD layer for the ephemeral native WebGL renderer.
            document["points"]=[[float(x) for x in p] for p in points]
            document["triangles"]=[list(t) for t in triangles]
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

    def open(self, project_id, asset_id, revision):
        record = self.index.read_revision(project_id, asset_id, revision)
        doc = record["data"]
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
        expected_type = {"cube":UsdGeom.Cube,"sphere":UsdGeom.Sphere,
                         "mesh":UsdGeom.Mesh}[doc["shape"]]
        if not geometry or not geometry.IsA(expected_type):
            raise RuntimeError("NVP asset geometry differs from frozen type")
        if doc["shape"]=="mesh":
            points=doc.get("points");triangles=doc.get("triangles")
            if (type(points) is not list or not 3<=len(points)<=MAX_MESH_VERTICES or
                    type(triangles) is not list or
                    not 1<=len(triangles)<=MAX_MESH_TRIANGLES):
                raise RuntimeError("Bounded original mesh topology missing")
            mesh=UsdGeom.Mesh(geometry)
            actual_points=mesh.GetPointsAttr().Get()
            counts=list(mesh.GetFaceVertexCountsAttr().Get())
            indices=list(mesh.GetFaceVertexIndicesAttr().Get())
            if (len(actual_points)!=len(points) or
                    counts!=[3]*len(triangles) or
                    indices!=[i for triangle in triangles for i in triangle] or
                    any(not all(math.isclose(float(v),float(expected),
                            rel_tol=1e-5,abs_tol=1e-5)
                            for v,expected in zip(actual,p))
                        for actual,p in zip(actual_points,points))):
                raise RuntimeError("Frozen USD triangle topology differs from indexed source")
        else:
            observed = (UsdGeom.Cube(geometry).GetSizeAttr().Get()
                        if doc["shape"] == "cube" else
                        2 * UsdGeom.Sphere(geometry).GetRadiusAttr().Get())
            if not math.isclose(float(observed),float(size),
                                rel_tol=0,abs_tol=1e-7):
                raise RuntimeError("USD asset dimensions disagree with FilmIndex")
        original_material=doc.get("preview_material")
        if original_material is not None:
            if (type(original_material) is not dict or
                original_material.get("format")!=
                    "nvp.original_usd_preview_surface.v1" or
                original_material.get("material_path")!="/Asset/Material" or
                original_material.get("original_source_modified") is not False or
                original_material.get("texture_images_loaded") is not False):
                raise RuntimeError("Original USD preview material scope invalid")
            from pxr import UsdShade
            binding=UsdShade.MaterialBindingAPI(geometry)
            bound,_=binding.ComputeBoundMaterial()
            if not bound or str(bound.GetPath())!="/Asset/Material":
                raise RuntimeError("USD asset material binding changed")
            shader=UsdShade.Shader(
                stage.GetPrimAtPath("/Asset/Material/PreviewSurface"))
            if not shader or shader.GetIdAttr().Get()!="UsdPreviewSurface":
                raise RuntimeError("USD asset surface shader changed")
            for key in ("roughness","metallic","base_color_rgb"):
                source=("diffuseColor" if key=="base_color_rgb" else key)
                inp=shader.GetInput(source)
                if not inp:
                    raise RuntimeError("Original material shader input missing")
                actual=inp.Get()
                expected=original_material[key]
                actuals=(list(actual) if key=="base_color_rgb" else [actual])
                expecteds=(expected if key=="base_color_rgb" else [expected])
                if any(not math.isclose(float(v),float(e),
                        rel_tol=1e-5,abs_tol=1e-5)
                    for v,e in zip(actuals,expecteds)):
                    raise RuntimeError("Original USD material differs from frozen manifest")
        return record, layer
