"""P1-F finite, immutable imported 3D environment asset with PBR material audit.

This is data-first real authored geometry with bounded native USD materials,
not a cube/sphere replacement, synthetic film or an AI-generated location.
All layers, meshes and material definitions are internally self-contained;
arbitrary USD references, texture URLs, variant/payload arcs, executable
paths and asset-resolver network access are forbidden.
"""
from __future__ import annotations

from hashlib import sha256
import math

from backend.nvp_film_index import FilmIndex,_require_pid,_id
from backend.nvp_openusd_scene import _usd,_layer_from_text,LAYER_TYPE,MAX_USD_LAYER_BYTES
from backend.nvp_p1f_imported_actor import FORBIDDEN

FORMAT="nvp.asset.openusd.imported_pbr_environment.v1"
MAX_MESHES=128
MAX_POINTS=250000
MAX_FACES=250000
MAX_MATERIALS=128
MAX_VERTICES_PER_POLYGON=128


def _audit(source):
    if (type(source) is not bytes or not 100<=len(source)<=MAX_USD_LAYER_BYTES or
            not source.lstrip().startswith(b"#usda 1.0") or
            b"@" in source or b"\x00" in source):
        raise ValueError("Environment must be a finite self-contained USDA scene")
    text=source.decode("utf8","strict")
    if FORBIDDEN.search(text):
        raise ValueError("Imported environment cannot author external USD composition arcs")
    Gf,Sdf,Usd,UsdGeom=_usd()
    from pxr import UsdShade
    layer=_layer_from_text(text,"reviewed_environment.usda",Sdf)
    if layer.subLayerPaths or layer.GetExternalReferences():
        raise ValueError("External environment layer references are forbidden")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if not stage or stage.GetDefaultPrim().GetPath()!=Sdf.Path("/Asset"):
        raise ValueError("Original location stage requires /Asset default prim")
    root=stage.GetPrimAtPath("/Asset")
    group=stage.GetPrimAtPath("/Asset/Geometry")
    if (not root.IsA(UsdGeom.Xform) or
            not group.IsA(UsdGeom.Xform) or
            not math.isclose(UsdGeom.GetStageMetersPerUnit(stage),1.,abs_tol=1e-12) or
            str(UsdGeom.GetStageUpAxis(stage))!="Z"):
        raise ValueError("Environment source must author meter/Z-up USD geometry")
    meshes=0;points=0;faces=0;materials=set()
    for prim in stage.TraverseAll():
        path=str(prim.GetPath())
        if path in ("/Asset","/Asset/Geometry","/Asset/Looks"):
            if not prim.IsA(UsdGeom.Xform):
                raise ValueError("Imported environment root hierarchy changed")
            continue
        if path.startswith("/Asset/Geometry/"):
            if prim.IsA(UsdGeom.Xform):
                continue
            if not prim.IsA(UsdGeom.Mesh):
                raise ValueError("Imported location contains non-mesh executable/unsupported data")
            mesh=UsdGeom.Mesh(prim)
            p=mesh.GetPointsAttr().Get()
            count=mesh.GetFaceVertexCountsAttr().Get()
            indices=mesh.GetFaceVertexIndicesAttr().Get()
            if (p is None or count is None or indices is None or
                    len(p)<3 or not count or sum(count)!=len(indices) or
                    any(n<3 or n>MAX_VERTICES_PER_POLYGON for n in count) or
                    any(i<0 or i>=len(p) for i in indices) or
                    any(not math.isfinite(float(v)) or abs(float(v))>1_000_000
                        for xyz in p for v in xyz)):
                raise ValueError("Original environment mesh topology is not bounded/finite")
            meshes+=1;points+=len(p);faces+=len(count)
            if (meshes>MAX_MESHES or points>MAX_POINTS or faces>MAX_FACES):
                raise ValueError("Imported environment exceeds verified native mesh budget")
            binding=UsdShade.MaterialBindingAPI(prim)
            targets=binding.GetDirectBindingRel().GetTargets()
            if len(targets)>1:
                raise ValueError("Ambiguous imported environment PBR material binding")
            for target in targets:
                if not str(target).startswith("/Asset/Looks/"):
                    raise ValueError("Materials must be local to reviewed environment bytes")
                materials.add(str(target))
            continue
        if path.startswith("/Asset/Looks/"):
            if prim.IsA(UsdShade.Material):
                continue
            if prim.IsA(UsdShade.Shader):
                shader=UsdShade.Shader(prim)
                if str(shader.GetIdAttr().Get())!="UsdPreviewSurface":
                    raise ValueError("Only native USD PreviewSurface materials allowed")
                for key in ("metallic","roughness"):
                    source_attr=shader.GetInput(key)
                    if source_attr:
                        value=source_attr.Get()
                        if value is not None and (
                                not math.isfinite(float(value)) or
                                not 0<=float(value)<=1):
                            raise ValueError("PBR material parameters out of finite range")
                        if source_attr.GetConnectedSources()[0]:
                            raise ValueError("No shader graph/textures outside reviewed PBR values")
                diffuse=shader.GetInput("diffuseColor")
                if diffuse:
                    v=diffuse.Get()
                    if v is not None and any(
                            not math.isfinite(float(x)) or not 0<=float(x)<=1
                            for x in v):
                        raise ValueError("PBR diffuseColor must be finite linear RGB")
                    if diffuse.GetConnectedSources()[0]:
                        raise ValueError("External shader connections are forbidden")
                continue
        raise ValueError("Imported environment contains unreviewed USD prim type")
    if not 1<=meshes<=MAX_MESHES:
        raise ValueError("Location needs actual imported mesh geometry")
    for path in materials:
        mat=stage.GetPrimAtPath(path)
        if not mat.IsA(UsdShade.Material):
            raise ValueError("Bound source material no longer exists")
    return layer,{"mesh_count":meshes,"point_count":points,
                  "polygon_count":faces,
                  "material_count":len(materials),
                  "pbr_model":"USD_PreviewSurface_no_external_textures"}


def publish_environment(index:FilmIndex,pid,asset_id,source,*,
                        location_id,approve_import,creator_event):
    if not isinstance(index,FilmIndex) or not callable(approve_import):
        raise TypeError("Native FilmIndex and independent location creator approval required")
    _require_pid(pid)
    _id(asset_id,"original imported location asset")
    _id(location_id,"original location identity")
    layer,geometry=_audit(source)
    digest=sha256(source).hexdigest()
    scope={"operation":"nvp.p1f.import_authored_3d_environment.v1",
           "project_id":pid,"asset_id":asset_id,
           "location_id":location_id,"source_sha256":digest,
           "geometry":geometry}
    if approve_import(creator_event,dict(scope)) is not True:
        raise PermissionError("Creator did not approve these exact location asset bytes")
    blob=index.put_blob(pid,source,media_type=LAYER_TYPE)
    if blob!=digest:
        raise RuntimeError("Reviewed imported environment blob digest mismatch")
    doc={"format":FORMAT,"location_id":location_id,
         "source":"reviewed_self_contained_openusd_location",
         "layer_sha256":blob,"root_prim":"/Asset",
         "external_references":False,"geometry":geometry}
    def guard(db):
        if db.execute("""SELECT 1 FROM film_blob_refs
            WHERE project_id=? AND sha256=?""",(pid,blob)).fetchone() is None:
            raise RuntimeError("Location source blob missing before immutable publication")
    return index.register_revision(pid,asset_id,"asset",doc,
                                   expected_revision=0,dependencies=[],
                                   precommit_guard=guard)


def open_environment(index:FilmIndex,pid,asset_id,revision):
    record=index.read_revision(pid,asset_id,revision)
    doc=record["data"]
    if (record["kind"]!="asset" or doc.get("format")!=FORMAT or
            doc.get("source")!="reviewed_self_contained_openusd_location" or
            doc.get("external_references") is not False or
            doc.get("root_prim")!="/Asset"):
        raise RuntimeError("Not an approved immutable imported environment")
    source=index.get_blob(pid,doc["layer_sha256"])
    layer,observed=_audit(source)
    if observed!=doc["geometry"]:
        raise RuntimeError("Original location geometry/PBR manifest changed")
    return record,layer
