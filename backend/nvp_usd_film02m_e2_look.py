"""USD-FILM-02M-E2 — source-authoritative Cycles look and geometry LOD pack.

An approved 02M building world is the ONLY geometric source. The actual
original near USD layer and SHA-pinned asset layers are copied unchanged.
Mid/far are *explicitly approximate* geometry authored from independently
reopened original USD bounds; their loss of openings is disclosed and they
must never be used for doorway/inside/camera-critical near views.

The illumination/rendering settings are a first-party reviewed contract,
not browser-provided Blender Python. This adapter produces source inputs
and an immutable review manifest, NOT a pretend rendered image.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import math
import shutil

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_usd_film02m_modular_buildings import OriginalBuildingKit,_sha
from backend.nvp_openusd_scene import _usd

FORMAT="nvp.usd_film02m_e2.referenced_lod_look_review.v1"
PROFILES=(
    {"id":"near_front","lod":"near","camera":"front",
     "resolution":[640,360],"cycles_samples":16,
     "lighting":"soft_day"},
    {"id":"near_rear","lod":"near","camera":"rear",
     "resolution":[640,360],"cycles_samples":24,
     "lighting":"soft_day"},
    {"id":"mid_oblique","lod":"mid","camera":"oblique",
     "resolution":[480,270],"cycles_samples":8,
     "lighting":"soft_day"},
    {"id":"far_street","lod":"far","camera":"far",
     "resolution":[320,180],"cycles_samples":4,
     "lighting":"soft_day"},
    {"id":"near_front_relight","lod":"near","camera":"front",
     "resolution":[640,360],"cycles_samples":24,
     "lighting":"warm_side"})
SOURCE_BUDGET=64*1024*1024
ALLOWED_RGB_MAX=1.
MAX_MODULES=48


def _hex(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _mesh_box(lower,upper):
    """12 real triangles around a reviewed 3D source bounding extent."""
    x0,y0,z0=(float(x) for x in lower)
    x1,y1,z1=(float(x) for x in upper)
    if not all(math.isfinite(x) for x in (x0,y0,z0,x1,y1,z1)):
        raise ValueError("Nonfinite source bounds")
    if min(x1-x0,y1-y0,z1-z0)<=0:
        raise ValueError("Cannot derive genuine 3D geometry from empty source")
    vertices=[
        [x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
        [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]]
    faces=[
        [0,2,1],[0,3,2],[4,5,6],[4,6,7],
        [0,1,5],[0,5,4],[3,7,6],[3,6,2],
        [0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    return vertices,faces


def _source_material(index,pid,placement):
    source=OpenUSDAssetRegistry(index).open(
        pid,placement["asset_id"],placement["asset_revision"])[0]
    doc=source["data"]
    if (source["document_sha256"]!=placement["asset_document_sha256"] or
        doc["layer_sha256"]!=placement["source_layer_sha256"] or
        doc.get("shape")!="mesh"):
        raise RuntimeError("Immutable first-party building module mesh changed")
    material=doc.get("preview_material")
    if (type(material) is not dict or
        material.get("format")!="nvp.original_usd_preview_surface.v1" or
        material.get("material_path")!="/Asset/Material"):
        raise RuntimeError("02M E2 requires native USD-authored PBR PreviewSurface")
    color=material["base_color_rgb"]
    roughness=material["roughness"]
    metallic=material["metallic"]
    if (type(color) is not list or len(color)!=3 or
        any(type(v) not in (float,int) or
            not math.isfinite(v) or not 0<=v<=1 for v in color) or
        any(type(v) not in (float,int) or not math.isfinite(v) or
            not 0<=v<=1 for v in (roughness,metallic))):
        raise RuntimeError("Original PBR source contains invalid numeric values")
    return {
        "node_id":placement["node_id"],
        "source_mesh_document_sha256":source["document_sha256"],
        "source_usd_layer_sha256":doc["layer_sha256"],
        "usd_preview_material_path":material["material_path"],
        "base_color_rgb":[float(v) for v in color],
        "roughness":float(roughness),"metallic":float(metallic),
        "has_source_texture":bool(material.get("texture")),
        "has_source_pbr_maps":bool(material.get("pbr_maps"))}


def _make_lod(stage_path,boxes,*,lod,source_bounds,materials):
    Gf,Sdf,Usd,UsdGeom=_usd()
    from pxr import UsdShade
    stage=Usd.Stage.CreateNew(str(stage_path))
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.)
    root=UsdGeom.Xform.Define(stage,"/World")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.Scope.Define(stage,"/World/LOD")
    if lod=="mid":
        data=[(p["node_id"],p["world_bounds_m"],
               materials[p["node_id"]]) for p in boxes]
    elif lod=="far":
        # Far skyline intentionally collapses all real apertures and
        # individual source parts into one original-world bounding hull.
        facade=next((p for p in boxes if p["role"]=="facade"),boxes[0])
        data=[("SkylineHull",source_bounds,materials[facade["node_id"]])]
    else:
        raise ValueError("Only reviewed derived mid/far LOD geometry")
    receipt=[]
    for node,bounds,material in data:
        verts,faces=_mesh_box(*bounds)
        mesh=UsdGeom.Mesh.Define(stage,"/World/LOD/"+node)
        mesh.GetPointsAttr().Set([Gf.Vec3f(*v) for v in verts])
        mesh.GetFaceVertexCountsAttr().Set([3]*len(faces))
        mesh.GetFaceVertexIndicesAttr().Set([
            i for face in faces for i in face])
        mesh.CreateSubdivisionSchemeAttr().Set("none")
        material_path="/World/Materials/"+node
        look=UsdShade.Material.Define(stage,material_path)
        shader=UsdShade.Shader.Define(stage,material_path+"/Preview")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*material["base_color_rgb"]))
        shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(
            material["roughness"])
        shader.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(
            material["metallic"])
        shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
        look.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(),"surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(look)
        receipt.append({
            "mesh_prim":str(mesh.GetPath()),
            "original_module_id":node,
            "original_material_node_id":material["node_id"],
            "vertices":len(verts),"triangles":len(faces),
            "source_derived_not_original_hero_geometry":True})
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Derived source-bound LOD USD layer could not save")
    checked=Usd.Stage.Open(str(stage_path))
    if not checked:
        raise RuntimeError("Derived original-source LOD stage cannot reopen")
    for item in receipt:
        mesh=UsdGeom.Mesh.Get(checked,item["mesh_prim"])
        if (not mesh or len(mesh.GetPointsAttr().Get() or [])!=8 or
            len(mesh.GetFaceVertexCountsAttr().Get() or [])!=12):
            raise RuntimeError("Derived original source geometry was not actually authored")
        if not UsdShade.MaterialBindingAPI(
                mesh.GetPrim()).ComputeBoundMaterial()[0]:
            raise RuntimeError("Derived LOD material binding lost at USD reopen")
    return receipt


class OriginalBuildingLookReview:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Original FilmIndex source required")
        self.index=index
        self.kit=OriginalBuildingKit(
            index,verify_director_action=lambda *_:False)

    @contextmanager
    def prepare(self,pid,building_id,revision):
        _require_pid(pid);_id(building_id,"original look review building")
        if type(revision) is not int or revision<1:
            raise ValueError("Exact frozen original building revision")
        with self.kit.open_building(pid,building_id,revision) as original:
            doc=original["building"]
            components=doc["placements"]
            if not 6<=len(components)<=MAX_MODULES:
                raise RuntimeError("Bounded reviewed native film set required")
            materials={p["node_id"]:_source_material(
                self.index,pid,p) for p in components}
            if not any(p["role"]=="facade" for p in components):
                raise RuntimeError("No original source street face")
            from pxr import UsdGeom,UsdShade
            stage=original["stage"]
            source_triangles=0
            for p in components:
                mesh=UsdGeom.Mesh.Get(
                    stage,"/World/Buildings/"+p["node_id"]+"/Geometry")
                if (not mesh or
                    not UsdShade.MaterialBindingAPI(
                        mesh.GetPrim()).ComputeBoundMaterial()[0]):
                    raise RuntimeError(
                        "Actual original near surface lacks source USD PBR material")
                source_triangles+=len(mesh.GetFaceVertexCountsAttr().Get() or [])
            bounds=[
                [min(p["world_bounds_m"][0][i] for p in components)
                 for i in range(3)],
                [max(p["world_bounds_m"][1][i] for p in components)
                 for i in range(3)]]
            with TemporaryDirectory(prefix="nvp-source-02me2-look-") as temp:
                root=Path(temp)
                source=Path(stage.GetRootLayer().realPath)
                path=root/"near.usda"
                if _hex(source)!=original["root_layer_sha256"]:
                    raise RuntimeError("Original immutable near-stage SHA mismatch")
                shutil.copyfile(source,path)
                resources=root/"assets"
                shutil.copytree(source.parent/"assets",resources)
                source_layer_hashes={}
                for p in resources.glob("*.usda"):
                    if p.is_symlink() or _hex(p)!=p.stem:
                        raise RuntimeError("Original material/geometry source asset SHA mismatch")
                    source_layer_hashes[p.stem]=p.name
                source_bytes=sum(p.stat().st_size for p in root.rglob("*.usda"))
                if source_bytes>SOURCE_BUDGET:
                    raise MemoryError("Reviewed original film look source exceeds file budget")
                derived={}
                for lod in ("mid","far"):
                    output=root/(lod+".usda")
                    derived[lod]=_make_lod(
                        output,components,lod=lod,
                        source_bounds=bounds,materials=materials)
                actual_counts={
                    "near":source_triangles,
                    "mid":sum(x["triangles"] for x in derived["mid"]),
                    "far":sum(x["triangles"] for x in derived["far"])}
                if not (actual_counts["far"]<actual_counts["mid"] and
                        actual_counts["mid"]<=actual_counts["near"]):
                    raise RuntimeError(
                        "Reviewed near/mid/far source complexity did not decrease")
                manifest={
                    "format":FORMAT,
                    "project_id":pid,
                    "building_id":building_id,
                    "building_revision":revision,
                    "building_document_sha256":original["record"][
                        "document_sha256"],
                    "original_near_stage_sha256":_hex(path),
                    "mid_lod_stage_sha256":_hex(root/"mid.usda"),
                    "far_lod_stage_sha256":_hex(root/"far.usda"),
                    "source_assets":source_layer_hashes,
                    "source_material_contract":[materials[p["node_id"]]
                        for p in components],
                    "world_source_bounds_m":bounds,
                    "actual_geometry_triangle_counts":actual_counts,
                    "first_party_reviewed_profiles":list(PROFILES),
                    "original_world_take_unchanged":True,
                    "source_look_model":"UsdPreviewSurface",
                    "materialx_parity_verified":False,
                    "native_blender_material_import_verified":False,
                    "ocio_aces_config_verified":False,
                    "exr_multilayer_rendered":False,
                    "cinematic_picture_approved":False,
                    "source_near_includes_real_openings":True,
                    "mid_far_are_approximate_hulls_not_camera_valid_near":True}
                (root/"manifest.json").write_text(
                    json.dumps(manifest,sort_keys=True,
                               separators=(",",":"),allow_nan=False),"utf8")
                yielded={
                    "root":root,"manifest":manifest,
                    "source_layer_hashes":source_layer_hashes,
                    "manifest_sha256":_hex(root/"manifest.json"),
                    "mid_components":derived["mid"],
                    "far_components":derived["far"],
                    "source_has_actual_pbr_surfaces":True,
                    "original_source_never_modified":True}
                yield yielded
