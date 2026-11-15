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
MAX_MESH_VERTICES=2048
MAX_MESH_TRIANGLES=4096
MAX_SIZE_METERS = 1000.0
# Internal Python-only capability; never passed through WebView JSON or tools.
_ORIGINAL_NATIVE_WO2_SOURCE_ADMISSION=object()


class OpenUSDAssetRegistry:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Native FilmIndex required")
        self.index = index

    def publish(self, project_id, asset_id, *, shape, size_m,
                expected_revision=0, points=None, triangles=None,
                preview_material=None, mesh_uvs=None, face_uvs=None,
                texture_png=None,material_slots=None,pbr_maps_png=None,
                _original_native_source_admission=None):
        _require_pid(project_id)
        _id(asset_id, "reusable asset ID")
        if shape not in KINDS:
            raise ValueError("Unsupported native authored geometry")
        if (any(x is not None for x in
                (texture_png,pbr_maps_png,material_slots)) and
                _original_native_source_admission is not
                    _ORIGINAL_NATIVE_WO2_SOURCE_ADMISSION):
            raise PermissionError(
                "Original Film01 generic geometry publisher cannot authorize "
                "unreviewed texture/PBR/material slots")
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
        authored_slots=None
        if material_slots is not None:
            from backend.nvp_wo2_material_slots import normalize_material_slots
            authored_slots=normalize_material_slots(material_slots,len(triangles))
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
            # Only a separately approved original PNG source receives its
            # historic authored MaterialX image node here. The generic scalar
            # path remains PreviewSurface-only and cannot admit hidden inputs.
            if (_original_native_source_admission is
                    _ORIGINAL_NATIVE_WO2_SOURCE_ADMISSION and
                    "texture" in authored_material):
                from backend.nvp_wo2_openpbr import author_openpbr_texture
                author_openpbr_texture(
                    stage,"/Asset/Material",material,
                    authored_material["texture"],
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

    def publish_native_selected_mesh_texture(self,project_id,asset_id,*,
            expected_source_revision,expected_source_document_sha256,
            selected_path,approve_native):
        """One OS-picked original PNG -> ONE immutable revised UV-mesh source.

        This is NOT the generic asset publisher and has no arbitrary file,
        browser-provided image bytes, shader, rights or Blender authority.
        Existing mesh points/UVs/preview scalar values are copied from
        independently reopened FilmIndex, never from untrusted JSON.
        """
        from backend.nvp_film_index import _sha
        from backend.nvp_native_usd_texture import (
            import_native_selected_png,verified_texture)
        _require_pid(project_id)
        _id(asset_id,"verified original source asset")
        _sha(expected_source_document_sha256)
        if (type(expected_source_revision) is not int or
            expected_source_revision<1 or not callable(approve_native)):
            raise PermissionError("Exact original revision and native OS approval required")
        old,_=self.open(project_id,asset_id,expected_source_revision)
        data=old["data"]
        if (old["document_sha256"]!=expected_source_document_sha256 or
            data.get("shape")!="mesh" or
            data.get("external_references") is not False or
            not (data.get("mesh_uvs") or data.get("face_uvs")) or
            data.get("material_slots") or
            not isinstance(data.get("preview_material"),dict) or
            any(k in data["preview_material"] for k in
                ("pbr_maps","texture"))):
            raise PermissionError(
                "Only unchanged source-authentic UV mesh with scalar material")
        used=False
        def review(original):
            nonlocal used
            if used:
                return False
            used=True
            exact={
                "operation":"nvp.wo2.native_import_original_mesh_texture.v1",
                "project_id":project_id,
                "asset_id":asset_id,
                "source_revision":expected_source_revision,
                "source_asset_sha256":expected_source_document_sha256,
                "source_png_sha256":original["sha256"],
                "width":original["width"],"height":original["height"],
                "size_bytes":original["size_bytes"]}
            return approve_native(exact) is True
        imported=import_native_selected_png(
            self.index,project_id,selected_path,approve=review)
        if imported["status"]=="DENIED":
            return {"status":"NATIVE_DENIED","original_modified":False,
                    "source_asset_modified":False}
        if imported["status"]!="ORIGINAL_TEXTURE_IMPORTED":
            raise RuntimeError("OS picker did not return independently verified PNG")
        original_again,_=self.open(project_id,asset_id,expected_source_revision)
        if original_again["document_sha256"]!=expected_source_document_sha256:
            raise RuntimeError("Source asset changed during native original import")
        png,_=verified_texture(self.index,project_id,imported["texture"])
        mat=data["preview_material"]
        published=self.publish(
            project_id,asset_id,
            shape="mesh",size_m=data["size_m"],
            expected_revision=expected_source_revision,
            points=data["points"],triangles=data["triangles"],
            mesh_uvs=data.get("mesh_uvs"),face_uvs=data.get("face_uvs"),
            preview_material={
                "base_color_rgb":mat["base_color_rgb"],
                "roughness":mat["roughness"],
                "metallic":mat["metallic"]},
            texture_png=png,
            _original_native_source_admission=
                _ORIGINAL_NATIVE_WO2_SOURCE_ADMISSION)
        reopened,_=self.open(
            project_id,asset_id,published["revision"])
        if (reopened["document_sha256"]!=published["document_sha256"] or
            reopened["data"]["preview_material"]["texture"]!=
                imported["texture"]):
            raise RuntimeError(
                "Native approved source PNG and revised USD mesh differ")
        return {
            "format":"nvp.wo2.native_approved_original_mesh_texture.v1",
            "status":"ORIGINAL_SOURCE_TEXTURE_BOUND",
            "asset_id":asset_id,
            "source_revision":expected_source_revision,
            "source_asset_sha256":expected_source_document_sha256,
            "revision":published["revision"],
            "document_sha256":published["document_sha256"],
            "original_png_sha256":imported["texture"]["sha256"],
            "native_source_reopened":True,
            "original_modified":False,"film_master_approved":False}

    def publish_native_selected_mesh_roughness(self,project_id,asset_id,*,
            expected_source_revision,expected_source_document_sha256,
            selected_path,approve_native):
        """One native-selected original roughness image on one approved UV mesh.

        A second original source authorization is required after approved
        base-color texture publication. The original texture and geometry
        are reopened from FilmIndex, not accepted from a browser request.
        This authoring operation is not P1-F licensed production clearance.
        """
        from backend.nvp_film_index import _sha
        from backend.nvp_native_usd_texture import (
            import_native_selected_png,verified_texture)
        _require_pid(project_id)
        _id(asset_id,"original PBR source asset")
        _sha(expected_source_document_sha256)
        if (type(expected_source_revision) is not int or
            expected_source_revision<1 or not callable(approve_native)):
            raise PermissionError("Exact native original roughness import required")
        prior,_=self.open(project_id,asset_id,expected_source_revision)
        data=prior["data"]
        mat=data.get("preview_material")
        if (prior["document_sha256"]!=expected_source_document_sha256 or
            data.get("shape")!="mesh" or
            data.get("external_references") is not False or
            not (data.get("mesh_uvs") or data.get("face_uvs")) or
            data.get("material_slots") or not isinstance(mat,dict) or
            "texture" not in mat or "pbr_maps" in mat):
            raise PermissionError(
                "Original roughness requires a reviewed source-textured UV mesh")
        original_png,_=verified_texture(
            self.index,project_id,mat["texture"])
        used=False
        def review(image):
            nonlocal used
            if used:
                return False
            used=True
            scope={
                "operation":"nvp.wo2.native_import_original_roughness_map.v1",
                "project_id":project_id,"asset_id":asset_id,
                "source_revision":expected_source_revision,
                "source_asset_sha256":expected_source_document_sha256,
                "original_base_png_sha256":mat["texture"]["sha256"],
                "source_png_sha256":image["sha256"],
                "width":image["width"],"height":image["height"],
                "size_bytes":image["size_bytes"],"channel":"roughness"}
            return approve_native(scope) is True
        def only_original_grayscale(width,height,rgba):
            if any(rgba[i]!=rgba[i+1] or rgba[i]!=rgba[i+2]
                   for i in range(0,len(rgba),4)):
                raise ValueError("Original roughness must be grayscale PNG")
        imported=import_native_selected_png(
            self.index,project_id,selected_path,approve=review,
            validate_source=only_original_grayscale)
        if imported["status"]=="DENIED":
            return {"status":"NATIVE_DENIED","original_modified":False,
                    "source_asset_modified":False}
        if imported["status"]!="ORIGINAL_TEXTURE_IMPORTED":
            raise RuntimeError("Native roughness picker did not return PNG source")
        roughness_png,_=verified_texture(
            self.index,project_id,imported["texture"])
        # Original PBR map publishing independently checks scalar pixel
        # contracts again before authoring a real MaterialX/USD graph.
        current,_=self.open(project_id,asset_id,expected_source_revision)
        if current["document_sha256"]!=expected_source_document_sha256:
            raise RuntimeError("Original mesh source changed during PBR import")
        result=self.publish(
            project_id,asset_id,shape="mesh",
            size_m=data["size_m"],expected_revision=expected_source_revision,
            points=data["points"],triangles=data["triangles"],
            mesh_uvs=data.get("mesh_uvs"),face_uvs=data.get("face_uvs"),
            preview_material={
                "base_color_rgb":mat["base_color_rgb"],
                "roughness":mat["roughness"],"metallic":mat["metallic"]},
            texture_png=original_png,
            pbr_maps_png={"roughness":roughness_png},
            _original_native_source_admission=
                _ORIGINAL_NATIVE_WO2_SOURCE_ADMISSION)
        reopened,_=self.open(project_id,asset_id,result["revision"])
        new_mat=reopened["data"]["preview_material"]
        if (reopened["document_sha256"]!=result["document_sha256"] or
            new_mat["texture"]!=mat["texture"] or
            new_mat["pbr_maps"]["roughness"]!=imported["texture"]):
            raise RuntimeError("Approved original material and PBR revision differ")
        return {
            "format":"nvp.wo2.native_approved_original_roughness_map.v1",
            "status":"ORIGINAL_ROUGHNESS_SOURCE_BOUND",
            "asset_id":asset_id,"source_revision":expected_source_revision,
            "source_asset_sha256":expected_source_document_sha256,
            "revision":result["revision"],
            "document_sha256":result["document_sha256"],
            "original_base_png_sha256":mat["texture"]["sha256"],
            "original_roughness_png_sha256":imported["texture"]["sha256"],
            "native_source_reopened":True,
            "original_modified":False,"film_master_approved":False}

    def import_rigged_actor(self, project_id, asset_id, source, *,
                            actor_id, approve_import, creator_event):
        """Import reviewed original USD; no external files or model authority."""
        from backend.nvp_p1f_imported_actor import import_actor
        return import_actor(
            self.index, project_id, asset_id, source, actor_id=actor_id,
            approve_import=approve_import, creator_event=creator_event)

    def import_environment(self,project_id,asset_id,source,*,
                           location_id,approve_import,creator_event):
        """A reviewed original source, not a new procedural NVP placeholder."""
        from backend.nvp_p1f_imported_environment import publish_environment
        return publish_environment(
            self.index,project_id,asset_id,source,location_id=location_id,
            approve_import=approve_import,creator_event=creator_event)

    def import_reviewed_pbr_materials(self,project_id,material_set_id,**reviewed):
        """Import human-approved PNG/PBR UV maps with original rights evidence.

        This does not authorize filesystem access, Blender execution,
        commercial licensing or a finished film master.
        """
        from backend.nvp_p1f_reviewed_pbr_materials import P1FReviewedPBRMaterials
        return P1FReviewedPBRMaterials(self.index).publish(
            project_id,material_set_id,**reviewed)

    def review_production_character(self, project_id, package_id, glb_bytes, **reviewed):
        """Bind a user-supplied rigged GLB to an original USD ActorID.

        Source rights, calibration and the exact joint map require a separate
        creator approval. This does not grant Blender or film-master rights.
        """
        from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
        return P1FReviewedProductionCharacters(self.index).publish(
            project_id, package_id, glb_bytes, **reviewed)

    def cast_production_character(self, project_id, cast_id, **reviewed):
        """Pin a reviewed GLB package to one original OpenUSD scene/ActorID."""
        from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
        return P1FReviewedProductionCharacters(self.index).cast(
            project_id, cast_id, **reviewed)

    def open(self, project_id, asset_id, revision):
        record = self.index.read_revision(project_id, asset_id, revision)
        doc = record["data"]
        # Preserve the independently reviewed production import pathways from
        # the converged registry: original Film01 sources never bypass them.
        from backend.nvp_p1f_imported_actor import FORMAT as RIGGED_FORMAT,open_actor
        from backend.nvp_p1f_imported_environment import (
            FORMAT as ENV_FORMAT,open_environment)
        if doc.get("format")==RIGGED_FORMAT:
            return open_actor(self.index,project_id,asset_id,revision)
        if doc.get("format")==ENV_FORMAT:
            return open_environment(self.index,project_id,asset_id,revision)
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
                        original_material["metallic"],
                        pbr_maps=original_material.get("pbr_maps"))
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
