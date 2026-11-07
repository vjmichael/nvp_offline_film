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
                preview_material=None, mesh_uvs=None, face_uvs=None,
                texture_png=None,material_slots=None,pbr_maps_png=None):
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
        elif points is not None or triangles is not None or mesh_uvs is not None or face_uvs is not None:
            raise ValueError("Procedural cube/sphere does not accept mesh data")
        if mesh_uvs is not None and face_uvs is not None:
            raise ValueError("USD st UV interpolation must be unambiguous")
        if face_uvs is not None:
            if (shape!="mesh" or type(face_uvs) is not list or
                len(face_uvs)!=len(triangles) or
                any(type(face) is not list or len(face)!=3 or
                    any(type(uv) is not list or len(uv)!=2 or
                        any(type(v) not in (int,float) or
                            not math.isfinite(v) or abs(v)>1024
                            for v in uv) for uv in face)
                    for face in face_uvs)):
                raise ValueError("USD face-varying UVs must match each triangle corner")
        if mesh_uvs is not None:
            if (shape!="mesh" or type(mesh_uvs) is not list or
                len(mesh_uvs)!=len(points) or
                any(type(uv) is not list or len(uv)!=2 or
                    any(type(v) not in (int,float) or
                        not math.isfinite(v) or abs(v)>1024
                        for v in uv) for uv in mesh_uvs)):
                raise ValueError("Authored mesh UVs must be bounded per-vertex coordinates")
        if material_slots is not None and shape!="mesh":
            raise ValueError("Only original triangle meshes accept material subsets")
        from backend.nvp_wo2_material_slots import normalize_material_slots
        authored_slots=normalize_material_slots(
            material_slots,len(triangles)) if material_slots is not None else None
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
        if texture_png is not None:
            if shape!="mesh" or (mesh_uvs is None and face_uvs is None) or authored_material is None:
                raise ValueError("Original PNG texture requires UV mesh and source material")
            from backend.nvp_native_usd_texture import publish_texture
            texture=publish_texture(self.index,project_id,texture_png)
            authored_material["texture"]=texture
            authored_material["texture_images_loaded"]=True
        if pbr_maps_png is not None:
            if shape!="mesh" or authored_material is None:
                raise ValueError("PBR source maps require a real UV mesh material")
            from backend.nvp_wo2_pbr_channels import publish_pbr_maps
            authored_material["pbr_maps"]=publish_pbr_maps(
                self.index,project_id,pbr_maps_png,
                has_uv=mesh_uvs is not None or face_uvs is not None)
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
            if mesh_uvs is not None:
                # Source-stable USD primvar, not a browser-generated UV proxy.
                st=UsdGeom.PrimvarsAPI(obj).CreatePrimvar(
                    "st",Sdf.ValueTypeNames.TexCoord2fArray,"vertex")
                st.Set([Gf.Vec2f(*uv) for uv in mesh_uvs])
            if face_uvs is not None:
                st=UsdGeom.PrimvarsAPI(obj).CreatePrimvar(
                    "st",Sdf.ValueTypeNames.TexCoord2fArray,"faceVarying")
                st.Set([Gf.Vec2f(*uv) for face in face_uvs for uv in face])
        if authored_material is not None:
            from pxr import UsdShade
            material=UsdShade.Material.Define(stage,"/Asset/Material")
            shader=UsdShade.Shader.Define(
                stage,"/Asset/Material/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(*authored_material["base_color_rgb"]))
            if "texture" in authored_material:
                tex=UsdShade.Shader.Define(stage,"/Asset/Material/Texture")
                tex.CreateIdAttr("UsdUVTexture")
                tex.CreateInput("file",Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath(authored_material["texture"]["usd_asset_path"]))
                tex.CreateInput("sourceColorSpace",Sdf.ValueTypeNames.Token).Set(
                    "sRGB")
                tex.CreateInput("wrapS",Sdf.ValueTypeNames.Token).Set("repeat")
                tex.CreateInput("wrapT",Sdf.ValueTypeNames.Token).Set("repeat")
                coords=UsdShade.Shader.Define(stage,"/Asset/Material/Primvar")
                coords.CreateIdAttr("UsdPrimvarReader_float2")
                coords.CreateInput("varname",Sdf.ValueTypeNames.Token).Set("st")
                tex.CreateInput("st",Sdf.ValueTypeNames.Float2).ConnectToSource(
                    coords.CreateOutput("result",Sdf.ValueTypeNames.Float2))
                shader.GetInput("diffuseColor").ConnectToSource(
                    tex.CreateOutput("rgb",Sdf.ValueTypeNames.Float3))
            for name in ("roughness","metallic"):
                shader.CreateInput(name,Sdf.ValueTypeNames.Float).Set(
                    authored_material[name])
            shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
            material.CreateSurfaceOutput().ConnectToSource(
                shader.ConnectableAPI(),"surface")
            if "texture" in authored_material:
                from backend.nvp_wo2_openpbr import author_openpbr_texture
                author_openpbr_texture(
                    stage,"/Asset/Material",material,
                    authored_material["texture"],
                    authored_material["roughness"],
                    authored_material["metallic"])
            else:
                from backend.nvp_wo2_openpbr import author_openpbr_scalar
                author_openpbr_scalar(
                    stage,"/Asset/Material",material,
                    authored_material["base_color_rgb"],
                    authored_material["roughness"],
                    authored_material["metallic"])
            if authored_material.get("pbr_maps"):
                from backend.nvp_wo2_pbr_channels import author_pbr_maps
                author_pbr_maps(stage,"/Asset/Material",shader,
                    UsdShade.Shader(stage.GetPrimAtPath(
                        "/Asset/Material/OpenPBR")),
                    authored_material["pbr_maps"])
            if not UsdShade.MaterialBindingAPI.Apply(
                    obj.GetPrim()).Bind(material):
                raise RuntimeError("Cannot bind real original USD PreviewSurface")
        if authored_slots is not None:
            from backend.nvp_wo2_material_slots import author_material_slots
            author_material_slots(stage,obj,authored_slots)
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
        if authored_slots is not None:
            document["material_slots"]=authored_slots
        if shape=="mesh":
            # Keep canonical, bounded source topology alongside the verified
            # original USD layer for the ephemeral native WebGL renderer.
            document["points"]=[[float(x) for x in p] for p in points]
            document["triangles"]=[list(t) for t in triangles]
            if mesh_uvs is not None:
                document["mesh_uvs"]=[[float(x) for x in uv] for uv in mesh_uvs]
            if face_uvs is not None:
                document["face_uvs"]=[[[float(x) for x in uv]
                                      for uv in face] for face in face_uvs]
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
            uv=doc.get("mesh_uvs")
            per_face=doc.get("face_uvs")
            primvar=UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
            if uv is not None and per_face is not None:
                raise RuntimeError("Original mesh UV interpolation is ambiguous")
            if per_face is not None:
                if (type(per_face) is not list or
                    len(per_face)!=len(triangles) or
                    not primvar or primvar.GetInterpolation()!="faceVarying"):
                    raise RuntimeError("Original face UV topology changed")
                wanted=[x for face in per_face for x in face]
                if (any(type(face) is not list or len(face)!=3 or
                        any(type(x) is not list or len(x)!=2 or
                            any(type(v) not in (int,float) or
                                not math.isfinite(v) or abs(v)>1024
                                for v in x) for x in face)
                        for face in per_face)):
                    raise RuntimeError("Invalid frozen face UVs")
                actual=primvar.Get()
                if actual is None or len(actual)!=len(wanted) or any(
                        not all(math.isclose(float(x),float(y),
                            rel_tol=1e-5,abs_tol=1e-5)
                            for x,y in zip(got,expected))
                        for got,expected in zip(actual,wanted)):
                    raise RuntimeError("Frozen USD face-varying UVs changed")
            elif uv is not None:
                if (type(uv) is not list or len(uv)!=len(points) or
                    any(type(p) is not list or len(p)!=2 or
                        any(type(x) not in (int,float) or
                            not math.isfinite(x) or abs(x)>1024 for x in p)
                        for p in uv) or
                    not primvar or primvar.GetInterpolation()!="vertex"):
                    raise RuntimeError("Original USD mesh UV source missing")
                observed_uv=primvar.Get()
                if (observed_uv is None or len(observed_uv)!=len(uv) or
                    any(not all(math.isclose(float(x),float(y),
                        rel_tol=1e-5,abs_tol=1e-5)
                        for x,y in zip(u,v))
                        for u,v in zip(observed_uv,uv))):
                    raise RuntimeError("Original USD UV primvar differs from FilmIndex")
            elif primvar:
                raise RuntimeError("Unindexed source USD UV primvar detected")
        else:
            observed = (UsdGeom.Cube(geometry).GetSizeAttr().Get()
                        if doc["shape"] == "cube" else
                        2 * UsdGeom.Sphere(geometry).GetRadiusAttr().Get())
            if not math.isclose(float(observed),float(size),
                                rel_tol=0,abs_tol=1e-7):
                raise RuntimeError("USD asset dimensions disagree with FilmIndex")
        original_slots=doc.get("material_slots")
        if original_slots is not None:
            if doc["shape"]!="mesh":
                raise RuntimeError("Nonmesh cannot bind USD material face subsets")
            from backend.nvp_wo2_material_slots import verify_material_slots
            verify_material_slots(stage,geometry,original_slots,
                                  len(doc["triangles"]))
        original_material=doc.get("preview_material")
        if original_material is not None:
            if (type(original_material) is not dict or
                original_material.get("format")!=
                    "nvp.original_usd_preview_surface.v1" or
                original_material.get("material_path")!="/Asset/Material" or
                original_material.get("original_source_modified") is not False or
                original_material.get("texture_images_loaded") is not (
                    "texture" in original_material)):
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
            # New scalar-only source graphs carry both universal PreviewSurface
            # and MaterialX OpenPBR terminal. Legacy frozen layers remain valid.
            openpbr=stage.GetPrimAtPath("/Asset/Material/OpenPBR")
            if openpbr:
                if "texture" in original_material:
                    from backend.nvp_wo2_openpbr import verify_openpbr_texture
                    verify_openpbr_texture(
                        stage,"/Asset/Material",bound,
                        original_material["texture"],
                        original_material["roughness"],
                        original_material["metallic"])
                else:
                    from backend.nvp_wo2_openpbr import verify_openpbr_scalar
                    verify_openpbr_scalar(
                        stage,"/Asset/Material",bound,
                        original_material["base_color_rgb"],
                        original_material["roughness"],
                        original_material["metallic"])
            if original_material.get("pbr_maps"):
                from backend.nvp_wo2_pbr_channels import (
                    verify_pbr_maps,verify_pbr_map_graph)
                maps=verify_pbr_maps(
                    self.index,project_id,original_material["pbr_maps"])
                verify_pbr_map_graph(
                    stage,"/Asset/Material",shader,
                    UsdShade.Shader(stage.GetPrimAtPath(
                        "/Asset/Material/OpenPBR")),maps)
            if "texture" in original_material:
                from backend.nvp_native_usd_texture import verified_texture
                texture=original_material["texture"]
                verified_texture(self.index,project_id,texture)
                node=UsdShade.Shader(
                    stage.GetPrimAtPath("/Asset/Material/Texture"))
                reader=UsdShade.Shader(
                    stage.GetPrimAtPath("/Asset/Material/Primvar"))
                if (not node or node.GetIdAttr().Get()!="UsdUVTexture" or
                    not reader or reader.GetIdAttr().Get()!="UsdPrimvarReader_float2" or
                    reader.GetInput("varname").Get()!="st" or
                    str(node.GetInput("file").Get().path)!=
                        texture["usd_asset_path"] or
                    node.GetInput("sourceColorSpace").Get()!="sRGB" or
                    node.GetInput("wrapS").Get()!="repeat" or
                    node.GetInput("wrapT").Get()!="repeat"):
                    raise RuntimeError("Frozen USD texture shader graph changed")
                connected=shader.GetInput("diffuseColor").GetConnectedSource()
                if not connected or str(connected[0].GetPrim().GetPath())!=(
                        "/Asset/Material/Texture") or connected[1]!="rgb":
                    raise RuntimeError("Texture no longer drives USD diffuseColor")
                uv_input=node.GetInput("st").GetConnectedSource()
                if not uv_input or str(uv_input[0].GetPrim().GetPath())!=(
                        "/Asset/Material/Primvar") or uv_input[1]!="result":
                    raise RuntimeError("USD texture lost original st UV binding")
            for key in ("roughness","metallic","base_color_rgb"):
                source=("diffuseColor" if key=="base_color_rgb" else key)
                inp=shader.GetInput(source)
                if not inp:
                    raise RuntimeError("Original material shader input missing")
                # Source-authored fallback remains on the USD attribute
                # when a PBR image supplies this input's live value.
                actual=inp.GetAttr().Get()
                expected=original_material[key]
                actuals=(list(actual) if key=="base_color_rgb" else [actual])
                expecteds=(expected if key=="base_color_rgb" else [expected])
                if any(not math.isclose(float(v),float(e),
                        rel_tol=1e-5,abs_tol=1e-5)
                    for v,e in zip(actuals,expecteds)):
                    raise RuntimeError("Original USD material differs from frozen manifest")
        return record, layer
