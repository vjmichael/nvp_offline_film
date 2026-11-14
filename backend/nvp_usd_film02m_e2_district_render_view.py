"""02M-E2 — disposable Blender-compatible view of original USD district.

Original PointInstancer remains authoritative. This bounded camera/render
working set resolves only selected visible instances into native USD
references for Blender interoperability. Never stores a substitute source
district or overwrites director/manual layers. No false GPU instancing
performance claim is made about expanded Blender render geometry.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil

from backend.nvp_film_index import FilmIndex,_require_pid,_id
from backend.nvp_usd_film02m_e_district import OriginalFilmDistrict
from backend.nvp_usd_film02m_modular_buildings import _sha

FORMAT="nvp.usd_film02m_e2.blender_compatible_district_view.v1"
MAX_RENDER_INSTANCES=24
MAX_RENDER_USD_BYTES=64*1024*1024


def _digest(path):
    h=sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1048576),b""):
            h.update(part)
    return h.hexdigest()


@contextmanager
def source_district_render_view(index,pid,district_id,revision):
    _require_pid(pid);_id(district_id,"immutable original film district")
    if not isinstance(index,FilmIndex):
        raise TypeError("Only first-party FilmIndex can authorize USD source")
    author=OriginalFilmDistrict(
        index,verify_director_action=lambda *_:False)
    with author.open(pid,district_id,revision) as original:
        from pxr import Usd,UsdGeom,Sdf,Gf,UsdShade
        plan=original["plan"]
        source=original["root_dir"]
        src_stage=original["stage"]
        point=UsdGeom.PointInstancer.Get(
            src_stage,"/World/GeneratedBuildings")
        if not point:
            raise RuntimeError("True source USD PointInstancer disappeared")
        source_ids=list(point.GetIdsAttr().Get() or [])
        prototype_indices=list(point.GetProtoIndicesAttr().Get() or [])
        source_positions=list(point.GetPositionsAttr().Get() or [])
        hidden=set(point.GetInvisibleIdsAttr().Get() or [])
        if (source_ids!=[r["instance_id"]
                        for r in plan["generated_instances"]] or
            len(prototype_indices)!=len(source_ids) or
            len(source_positions)!=len(source_ids) or
            hidden!=set(plan["director_invisible_instance_ids"])):
            raise RuntimeError("Original generated/stronger layer changed before render")
        visible=[]
        for i,instance_id in enumerate(source_ids):
            if instance_id in hidden:continue
            original_row=plan["generated_instances"][i]
            if (prototype_indices[i]!=original_row["prototype_index"] or
                max(abs(float(a)-b) for a,b in zip(
                    source_positions[i],original_row[
                        "position_local_m"]))>1e-5):
                raise PermissionError("Source instance index/placement differs from approved FilmIndex")
            proto=plan["original_prototypes"][prototype_indices[i]]
            visible.append({
                "prim_id":"Generated_"+str(instance_id),
                "original_source_instance_id":int(instance_id),
                "source_prototype":proto,
                "position_local_m":[float(x) for x in source_positions[i]],
                "yaw_deg":original_row["yaw_deg"],
                "director_hand_placed":False})
        by_id={p["building_id"]:p for p in plan["original_prototypes"]}
        for row in plan["director_manual_overrides"]:
            original_building=by_id[row["building_id"]]
            if row["source_building_sha256"]!=original_building[
                    "building_sha256"]:
                raise RuntimeError("Approved manual source building changed")
            visible.append({
                "prim_id":"Director_"+row["name"],
                "original_source_instance_id":None,
                "source_prototype":original_building,
                "position_local_m":row["position_m"],
                "yaw_deg":row["yaw_deg"],
                "director_hand_placed":True})
        if not 1<=len(visible)<=MAX_RENDER_INSTANCES:
            raise MemoryError("Source district exceeds reviewed Blender material look bounds")
        with TemporaryDirectory(prefix="nvp-02me2-render-view-") as temp:
            root=Path(temp)
            shutil.copytree(source/"sources",root/"sources")
            material_layers={}
            total=0
            for asset in (root/"sources"/"assets").glob("*.usda"):
                if asset.is_symlink() or _digest(asset)!=asset.stem:
                    raise RuntimeError("Original district shared mesh/material asset changed")
                material_layers[asset.stem]=asset.name
                total+=asset.stat().st_size
            for item in plan["original_prototypes"]:
                name=item["original_usd_sha256"]
                path=root/"sources"/(name+".usda")
                if path.is_symlink() or _digest(path)!=name:
                    raise RuntimeError("Original district building prototype source bytes changed")
                total+=path.stat().st_size
            if total>MAX_RENDER_USD_BYTES:
                raise MemoryError("Original source district staging memory over review bound")
            path=root/"district_render_view.usda"
            stage=Usd.Stage.CreateNew(str(path))
            UsdGeom.SetStageMetersPerUnit(stage,1.0)
            UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
            base=UsdGeom.Xform.Define(stage,"/World")
            stage.SetDefaultPrim(base.GetPrim())
            UsdGeom.Scope.Define(stage,"/World/VisibleBuildings")
            expected=0
            for piece in visible:
                proto=piece["source_prototype"]
                node=UsdGeom.Xform.Define(
                    stage,"/World/VisibleBuildings/"+piece["prim_id"])
                if not node.GetPrim().GetReferences().AddReference(
                        "./sources/"+proto["original_usd_sha256"]+".usda",
                        Sdf.Path("/World/Buildings")):
                    raise RuntimeError("Reviewed original building reference could not compose")
                api=UsdGeom.XformCommonAPI(node)
                api.SetTranslate(Gf.Vec3d(*piece["position_local_m"]))
                api.SetRotate(Gf.Vec3f(0.,0.,float(piece["yaw_deg"])))
                expected+=proto["mesh_count"]
            if not stage.GetRootLayer().Save():
                raise RuntimeError("Bounded derived district render view could not save")
            original_sha=_digest(path)
            reopened=Usd.Stage.Open(str(path))
            if reopened is None:
                raise RuntimeError("Source-connected Blender film district view cannot reopen")
            native_meshes=[
                p for p in reopened.Traverse() if p.IsA(UsdGeom.Mesh)]
            if len(native_meshes)!=expected:
                raise RuntimeError("Blender district view failed to compose source meshes")
            bound_materials=0
            for mesh in native_meshes:
                if (not UsdShade.MaterialBindingAPI(
                        mesh).ComputeBoundMaterial()[0]):
                    raise RuntimeError("Original building module lost native USD PBR material")
                bound_materials+=1
            manifest={
                "format":FORMAT,
                "original_project_id":pid,
                "original_district_id":district_id,
                "original_district_revision":revision,
                "original_district_document_sha256":original["record"][
                    "document_sha256"],
                "original_point_instancer_root_sha256":original["receipt"][
                    "district_root_sha256"],
                "original_generated_layer_sha256":original["receipt"][
                    "generated_layer_sha256"],
                "original_director_layer_sha256":original["receipt"][
                    "director_override_layer_sha256"],
                "render_view_usd_sha256":original_sha,
                "referenced_original_building_usd_shas":[
                    p["original_usd_sha256"]
                    for p in plan["original_prototypes"]],
                "pinned_source_asset_layers":sorted(material_layers),
                "source_original_point_instances":len(source_ids),
                "source_original_invisible_ids":sorted(hidden),
                "source_visible_and_hand_placed_instances":len(visible),
                "source_approved_world_origin_m":plan["world_origin_m"],
                "render_view_local_origin_m":[0.,0.,0.],
                "source_visible_transform_receipts":visible,
                "expected_actual_original_meshes":expected,
                "original_native_usd_pbr_bound_meshes":bound_materials,
                "compiled_from_source_no_actor_performance_modification":True,
                "did_not_modify_original_generated_or_director_layers":True,
                "native_blender_cycles_parity_verified":False,
                "gpu_instancing_performance_verified":False,
                "cinematic_picture_approved":False}
            (root/"manifest.json").write_text(
                json.dumps(manifest,sort_keys=True,separators=(",",":"),
                           allow_nan=False),"utf8")
            yield {
                "root":root,"manifest":manifest,
                "manifest_sha256":_digest(root/"manifest.json"),
                "native_source_view_sha256":original_sha,
                "visible_original_instances":visible,
                "original_point_instancer_retained_as_authority":True}
