"""USD-FILM-02M-E1: bounded source-first reusable film district.

Deterministic layout over exact approved 02M building world revisions.
Actual USD PointInstancer for generated repetitions. An independent
stronger director overlay hides exact instance IDs and adds individually
approved source references without modifying the weaker generated layer.
One original immutable FilmIndex record pins both layers and source USD
layer hashes. Local metre offsets avoid putting large world coordinates
into float32 instancer arrays.

This is offline film stage authoring, NOT a VR/headset runtime, a
photorealistic Cycles acceptance, or a proof of actual GPU draw calls.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import math
import shutil

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_usd_film02m_modular_buildings import (
    OriginalBuildingKit,PRIM_TOKEN,_sha,_vector)

FORMAT="nvp.usd_film02m_e.original_layered_district.v1"
MAX_PROTOTYPES=8
MAX_INSTANCES=256
MAX_EDITS=64
MAX_STAGE_BYTES=96*1024*1024
MAX_SOURCE_TRIANGLES=2_000_000
MAX_SOURCE_MESHES=500_000
MAX_REGION_M=10_000
MIN_LOT_SPACING_M=4.0


def _source_rows(index,pid,references):
    if (type(references) is not list or
        not 1<=len(references)<=MAX_PROTOTYPES):
        raise ValueError("One to eight original building source prototypes")
    kit=OriginalBuildingKit(index,verify_director_action=lambda *_:False)
    found=[]
    seen=set()
    seen_building_ids=set()
    for item in references:
        if (type(item) is not dict or
            set(item)!={"building_id","revision"}):
            raise ValueError("Only exact original FilmIndex building refs")
        bid=_id(item["building_id"],"source building ID")
        revision=item["revision"]
        if (type(revision) is not int or revision<1 or
            (bid,revision) in seen or bid in seen_building_ids):
            raise ValueError("Duplicate/ambiguous original building prototype")
        seen.add((bid,revision))
        seen_building_ids.add(bid)
        with kit.open_building(pid,bid,revision) as original:
            doc=original["building"]
            if (doc["renderer_pixels_verified"] is not False or
                doc["source_dependencies_only"] is not True):
                raise PermissionError("District cannot launder a fake render as original source")
            # Original 02M building prototypes must be authored locally.
            # A nonzero old global offset would be duplicated by the
            # generated cell positioning and can introduce precision loss.
            root=doc["placements"][0]
            if any(abs(x)>1e-5 for x in root["position_m"]):
                raise ValueError("Reusable building prototypes must start at local origin")
            lower=[min(x["world_bounds_m"][0][i] for x in doc["placements"])
                   for i in range(3)]
            upper=[max(x["world_bounds_m"][1][i] for x in doc["placements"])
                   for i in range(3)]
            stage=original["stage"]
            from pxr import UsdGeom
            mesh_faces=0
            mesh_vertices=0
            for row in doc["placements"]:
                geom=UsdGeom.Mesh(stage.GetPrimAtPath(
                    "/World/Buildings/"+row["node_id"]+"/Geometry"))
                if not geom:
                    raise RuntimeError("Original building module mesh disappeared")
                mesh_faces+=len(geom.GetFaceVertexCountsAttr().Get() or [])
                mesh_vertices+=len(geom.GetPointsAttr().Get() or [])
            if mesh_faces<=0 or mesh_vertices<=0:
                raise RuntimeError("Actual first-party source mesh missing")
            found.append({
                "building_id":bid,"revision":revision,
                "building_sha256":original["record"]["document_sha256"],
                "original_usd_sha256":original["root_layer_sha256"],
                "mesh_count":original["mesh_count"],
                "source_triangles":mesh_faces,
                "source_vertices":mesh_vertices,
                "original_bounds_m":[lower,upper],
                "source_material_preview_only":True})
    return found


def _validate_overrides(steps,placements,source):
    if type(steps) is not list or len(steps)>MAX_EDITS:
        raise ValueError("Bounded stronger layer director operations required")
    available={row["building_id"]:row for row in source}
    ids={p["instance_id"] for p in placements}
    used=set()
    hidden=[]
    manual=[]
    for operation in steps:
        if type(operation) is not dict or operation.get("op") not in (
                "hide_generated","place_original"):
            raise PermissionError("Only typed source hide or hand-placement opinions")
        if operation["op"]=="hide_generated":
            if set(operation)!={"op","instance_id"}:
                raise ValueError("One exact original generated instance to hide")
            instance_id=operation["instance_id"]
            if (type(instance_id) is not int or
                instance_id not in ids or instance_id in used):
                raise ValueError("Original hidden instance must exist and be unique")
            used.add(instance_id)
            hidden.append(instance_id)
        else:
            if set(operation)!={"op","name","building_id","position_m","yaw_deg"}:
                raise ValueError("Typed original manual override placement")
            name=_id(operation["name"],"director override node")
            if not PRIM_TOKEN.fullmatch(name) or name in used:
                raise ValueError("Unique safe original USD override prim ID")
            used.add(name)
            building_id=operation["building_id"]
            if building_id not in available:
                raise PermissionError("Manual override must use one approved original prototype")
            pos=_vector(operation["position_m"],"local original film placement",
                        max_abs=MAX_REGION_M)
            yaw=operation["yaw_deg"]
            if type(yaw) is not int or yaw not in (0,90,180,270):
                raise ValueError("Source building turns must preserve reviewed 90-degree axes")
            manual.append({
                "name":name,"building_id":building_id,
                "position_m":pos,"yaw_deg":yaw,
                "source_building_sha256":available[building_id][
                    "building_sha256"]})
    return sorted(hidden),sorted(manual,key=lambda p:p["name"])


class OriginalFilmDistrict:
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("FilmIndex and host-controlled director consent needed")
        self.index=index
        self.approve=verify_director_action
        self.kit=OriginalBuildingKit(index,verify_director_action=lambda *_:False)

    def plan(self,pid,*,seed,source_buildings,grid_cols,grid_rows,
             lot_spacing_m,world_origin_m,
             source_triangle_budget,source_instance_budget,
             director_overrides=None):
        _require_pid(pid)
        if type(seed) is not int or not 0<=seed<2**63:
            raise ValueError("Fixed original district generator seed")
        if (type(grid_cols) is not int or type(grid_rows) is not int or
            not 1<=grid_cols<=16 or not 1<=grid_rows<=16 or
            grid_cols*grid_rows>MAX_INSTANCES):
            raise ValueError("Bounded 16x16 original film district")
        if (type(lot_spacing_m) not in (int,float) or
            not math.isfinite(lot_spacing_m) or
            not MIN_LOT_SPACING_M<=lot_spacing_m<=MAX_REGION_M):
            raise ValueError("Finite source lot spacing in metres required")
        origin=_vector(world_origin_m,"district world-space origin",
                       max_abs=100_000_000)
        if (type(source_triangle_budget) is not int or
            not 100<=source_triangle_budget<=MAX_SOURCE_TRIANGLES or
            type(source_instance_budget) is not int or
            not 1<=source_instance_budget<=MAX_INSTANCES):
            raise ValueError("Exact reviewed district source budgets required")
        original=_source_rows(self.index,pid,source_buildings)
        largest=max(max(
            row["original_bounds_m"][1][axis]-
            row["original_bounds_m"][0][axis] for axis in (0,1))
                    for row in original)
        spacing=float(lot_spacing_m)
        if spacing<largest+.25:
            raise ValueError("Physical source footprints collide across adjacent lots")
        chosen=[]
        for i in range(grid_cols*grid_rows):
            col,row=i%grid_cols,i//grid_cols
            x=(col-(grid_cols-1)/2)*spacing
            y=(row-(grid_rows-1)/2)*spacing
            # SHA-seeded stable slot selection needs no external AI action.
            index=int(sha256((
                str(seed)+"|"+str(i)+"|"+_sha(original)
                ).encode("ascii")).hexdigest(),16)%len(original)
            prototype=original[index]
            chosen.append({
                "instance_id":i+1,
                "prototype_index":index,
                "building_id":prototype["building_id"],
                "position_local_m":[round(x,6),round(y,6),0.],
                "yaw_deg":0,
                "original_building_sha256":prototype["building_sha256"]})
        hidden,manual=_validate_overrides(
            [] if director_overrides is None else director_overrides,
            chosen,original)
        if len(chosen)+len(manual)>source_instance_budget:
            raise MemoryError("District exceeds original instance count budget")
        face_estimate=sum(original[p["prototype_index"]][
            "source_triangles"] for p in chosen
                          if p["instance_id"] not in hidden)
        face_estimate+=sum(next(
            r["source_triangles"] for r in original
            if r["building_id"]==p["building_id"]) for p in manual)
        if face_estimate>source_triangle_budget:
            raise MemoryError("District exceeds real source triangle budget")
        mesh_estimate=sum(original[p["prototype_index"]][
            "mesh_count"] for p in chosen
                          if p["instance_id"] not in hidden)
        mesh_estimate+=sum(next(
            r["mesh_count"] for r in original
            if r["building_id"]==p["building_id"]) for p in manual)
        if mesh_estimate>MAX_SOURCE_MESHES:
            raise MemoryError("Instanced source mesh-equivalent count exceeds bound")
        # Check actual source AABB footprints before any world is approved.
        # Do not interpret this as full structural/collider validation.
        by_id={p["building_id"]:p for p in original}
        occupied=[]
        def footprint(row,pos,yaw):
            bounds=row["original_bounds_m"]
            xmin,ymin=bounds[0][:2]
            xmax,ymax=bounds[1][:2]
            xy=[(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)]
            from backend.nvp_usd_film02m_modular_buildings import _rotate
            points=[_rotate([x,y,0.],yaw) for x,y in xy]
            return [min(v[0] for v in points)+pos[0],
                    max(v[0] for v in points)+pos[0],
                    min(v[1] for v in points)+pos[1],
                    max(v[1] for v in points)+pos[1]]
        for item in chosen:
            if item["instance_id"] not in hidden:
                occupied.append((str(item["instance_id"]),footprint(
                    original[item["prototype_index"]],
                    item["position_local_m"],item["yaw_deg"])))
        for item in manual:
            proposed=footprint(by_id[item["building_id"]],
                               item["position_m"],item["yaw_deg"])
            for name,old in occupied:
                overlap_x=min(proposed[1],old[1])-max(proposed[0],old[0])
                overlap_y=min(proposed[3],old[3])-max(proposed[2],old[2])
                if overlap_x>.02 and overlap_y>.02:
                    raise ValueError(
                        "Manual director building collides with original "+
                        "prototype "+name)
            occupied.append((item["name"],proposed))
        return {
            "format":FORMAT,
            "coordinate_system":"meters_Z_up",
            "meters_per_unit":1.0,
            "world_origin_m":origin,
            "authoring_origin_is_double_precision":True,
            "instance_positions_are_local_metres":True,
            "seed":seed,
            "grid_cols":grid_cols,"grid_rows":grid_rows,
            "lot_spacing_m":spacing,
            "original_prototypes":original,
            "generated_instances":chosen,
            "director_invisible_instance_ids":hidden,
            "director_manual_overrides":manual,
            "original_director_operations":[
                dict(v) for v in
                ([] if director_overrides is None else director_overrides)],
            "source_triangle_budget":source_triangle_budget,
            "source_instance_budget":source_instance_budget,
            "actual_source_triangles_estimated":face_estimate,
            "actual_source_mesh_equivalents_estimated":mesh_estimate,
            "generated_repetition_uses_point_instancer":True,
            "hand_edits_are_separate_stronger_usd_layer":True,
            "material_only_look_variants_implemented":False,
            "actual_gpu_draw_calls_measured":False,
            "real_lod_mesh_variants_verified":False,
            "cinematic_cycles_picture_reviewed":False,
            "original_actor_performance_untouched":True}

    def _replan(self,pid,doc):
        return self.plan(
            pid,seed=doc["seed"],source_buildings=[
                {"building_id":p["building_id"],"revision":p["revision"]}
                for p in doc["original_prototypes"]],
            grid_cols=doc["grid_cols"],grid_rows=doc["grid_rows"],
            lot_spacing_m=doc["lot_spacing_m"],
            world_origin_m=doc["world_origin_m"],
            source_triangle_budget=doc["source_triangle_budget"],
            source_instance_budget=doc["source_instance_budget"],
            director_overrides=doc["original_director_operations"])

    @contextmanager
    def _stage(self,pid,doc):
        from pxr import Usd,UsdGeom,Sdf,Gf
        with TemporaryDirectory(prefix="nvp-original-02me-layered-district-") as tmp:
            base=Path(tmp)
            library=base/"sources"
            library.mkdir()
            assets=library/"assets"
            assets.mkdir()
            referenced={}
            staged_bytes=0
            for prototype in doc["original_prototypes"]:
                bid=prototype["building_id"]
                with self.kit.open_building(
                        pid,bid,prototype["revision"]) as building:
                    if (building["root_layer_sha256"]!=prototype[
                            "original_usd_sha256"] or
                        building["record"]["document_sha256"]!=prototype[
                            "building_sha256"]):
                        raise RuntimeError("Original district prototype changed")
                    src=Path(building["stage"].GetRootLayer().realPath)
                    content=src.read_bytes()
                    destination=library/(prototype[
                        "original_usd_sha256"]+".usda")
                    if not destination.exists():
                        destination.write_bytes(content)
                        staged_bytes+=len(content)
                    for path in (src.parent/"assets").glob("*.usda"):
                        if path.stem in referenced:
                            continue
                        payload=path.read_bytes()
                        if sha256(payload).hexdigest()!=path.stem:
                            raise RuntimeError("Original reusable module asset SHA invalid")
                        (assets/path.name).write_bytes(payload)
                        staged_bytes+=len(payload)
                        referenced[path.stem]=path.name
                    if staged_bytes>MAX_STAGE_BYTES:
                        raise MemoryError("USD original district source library over bounded RAM")
            generated_path=base/"generated.usda"
            generated=Usd.Stage.CreateNew(str(generated_path))
            UsdGeom.SetStageMetersPerUnit(generated,1.)
            UsdGeom.SetStageUpAxis(generated,UsdGeom.Tokens.z)
            world=UsdGeom.Xform.Define(generated,"/World")
            generated.SetDefaultPrim(world.GetPrim())
            # Place prototypes BELOW the actual PointInstancer prim;
            # an over-specifier parent prevents normal source traversals
            # from drawing uninstanced copies at the cell origin.
            instances=UsdGeom.PointInstancer.Define(
                generated,"/World/GeneratedBuildings")
            prototypes=UsdGeom.Scope.Define(
                generated,"/World/GeneratedBuildings/Prototypes")
            prototypes.GetPrim().SetSpecifier(Sdf.SpecifierOver)
            source_ids={}
            prototype_paths=[]
            for i,proto in enumerate(doc["original_prototypes"]):
                path="/World/GeneratedBuildings/Prototypes/Building_"+str(i)
                prototype_paths.append(path)
                primitive=UsdGeom.Xform.Define(generated,path)
                if not primitive.GetPrim().GetReferences().AddReference(
                        "./sources/"+proto["original_usd_sha256"]+".usda",
                        Sdf.Path("/World/Buildings")):
                    raise RuntimeError("USD source building prototype reference failed")
                source_ids[proto["building_id"]]=i
            instances.GetPrototypesRel().SetTargets(
                [Sdf.Path(s) for s in prototype_paths])
            instances.GetProtoIndicesAttr().Set([
                row["prototype_index"] for row in doc["generated_instances"]])
            instances.GetPositionsAttr().Set([
                Gf.Vec3f(*row["position_local_m"])
                for row in doc["generated_instances"]])
            instances.GetIdsAttr().Set([
                row["instance_id"] for row in doc["generated_instances"]])
            if not generated.GetRootLayer().Save():
                raise RuntimeError("Original generated district USD could not save")
            override_path=base/"director.usda"
            director=Usd.Stage.CreateNew(str(override_path))
            UsdGeom.SetStageMetersPerUnit(director,1.)
            UsdGeom.SetStageUpAxis(director,UsdGeom.Tokens.z)
            invisible=UsdGeom.PointInstancer.Define(
                director,"/World/GeneratedBuildings")
            invisible.GetInvisibleIdsAttr().Set(
                doc["director_invisible_instance_ids"])
            UsdGeom.Scope.Define(director,"/World/DirectorOverrides")
            for item in doc["director_manual_overrides"]:
                path="/World/DirectorOverrides/"+item["name"]
                inst=UsdGeom.Xform.Define(director,path)
                proto=doc["original_prototypes"][
                    source_ids[item["building_id"]]]
                if not inst.GetPrim().GetReferences().AddReference(
                        "./sources/"+proto["original_usd_sha256"]+".usda",
                        Sdf.Path("/World/Buildings")):
                    raise RuntimeError("Original manual source reference failed")
                api=UsdGeom.XformCommonAPI(inst)
                api.SetTranslate(Gf.Vec3d(*item["position_m"]))
                api.SetRotate(Gf.Vec3f(0.,0.,float(item["yaw_deg"])))
            if not director.GetRootLayer().Save():
                raise RuntimeError("Director stronger original layer cannot save")
            root_path=base/"district.usda"
            main=Usd.Stage.CreateNew(str(root_path))
            # The authoritative district root also has explicit units;
            # never trust composed or DCC-dependent implicit defaults.
            UsdGeom.SetStageMetersPerUnit(main,1.)
            UsdGeom.SetStageUpAxis(main,UsdGeom.Tokens.z)
            main.GetRootLayer().subLayerPaths=[
                "./director.usda","./generated.usda"]
            main.GetRootLayer().customLayerData={
                "nvpOriginalWorldOriginJSON":json.dumps(doc[
                    "world_origin_m"],separators=(",",":")),
                "nvpOriginalDistrictPlanSHA":_sha(doc)}
            if not main.GetRootLayer().Save():
                raise RuntimeError("Original layer-composition stage cannot save")
            loaded=Usd.Stage.Open(str(root_path))
            if loaded is None:
                raise RuntimeError("Original district layer stack did not compose")
            if (abs(UsdGeom.GetStageMetersPerUnit(loaded)-1.)>1e-9 or
                str(UsdGeom.GetStageUpAxis(loaded))!="Z" or
                list(loaded.GetRootLayer().subLayerPaths)!=[
                    "./director.usda","./generated.usda"]):
                raise RuntimeError("Original film district layer units or strength changed")
            point=UsdGeom.PointInstancer.Get(
                loaded,"/World/GeneratedBuildings")
            indices=list(point.GetProtoIndicesAttr().Get() or [])
            positions=list(point.GetPositionsAttr().Get() or [])
            original_ids=list(point.GetIdsAttr().Get() or [])
            hidden_ids=list(point.GetInvisibleIdsAttr().Get() or [])
            if (len(indices)!=len(doc["generated_instances"]) or
                len(positions)!=len(indices) or
                original_ids!=[x["instance_id"] for x in
                              doc["generated_instances"]] or
                hidden_ids!=doc["director_invisible_instance_ids"]):
                raise RuntimeError("True USD instancing/override composition altered")
            for i,proto in enumerate(doc["original_prototypes"]):
                path=(
                    "/World/GeneratedBuildings/Prototypes/Building_"+
                    str(i)+"/"+self._first_module_prim(pid,proto))
                # Prototypes live below a pure 'over' ancestor so USD
                # deliberately excludes them from default raw traversal.
                # Prim.IsDefined() is FALSE with that ancestor; inspect
                # the actual composed mesh topology instead.
                geom=UsdGeom.Mesh.Get(loaded,path)
                if (not geom or
                    len(geom.GetPointsAttr().Get() or [])<8 or
                    len(geom.GetFaceVertexCountsAttr().Get() or [])<12):
                    raise RuntimeError(
                        "Original instanced prototype mesh reference did not reopen")
            for item in doc["director_manual_overrides"]:
                if not loaded.GetPrimAtPath(
                        "/World/DirectorOverrides/"+item["name"]
                        ).IsDefined():
                    raise RuntimeError("Director original stronger layer did not compose")
            receipt={
                "district_root_sha256":sha256(root_path.read_bytes()).hexdigest(),
                "generated_layer_sha256":sha256(
                    generated_path.read_bytes()).hexdigest(),
                "director_override_layer_sha256":sha256(
                    override_path.read_bytes()).hexdigest(),
                "actual_native_usd_point_instancer_count":len(indices),
                "actual_native_usd_prototype_count":len(prototype_paths),
                "actual_native_usd_invisible_ids":hidden_ids,
                "actual_native_usd_manual_overrides":len(doc[
                    "director_manual_overrides"]),
                "actual_referenced_source_asset_layers":len(referenced),
                "native_usd_source_staging_bytes":staged_bytes,
                "director_layer_did_not_rewrite_generated_layer":True}
            yield {"stage":loaded,"root_dir":base,
                   "root_path":root_path,
                   "generated_path":generated_path,
                   "director_path":override_path,
                   "receipt":receipt}

    def _first_module_prim(self,pid,proto):
        with self.kit.open_building(
                pid,proto["building_id"],proto["revision"]) as result:
            return result["building"]["placements"][0]["node_id"]+"/Geometry"

    def publish(self,pid,district_id,*,seed,source_buildings,
                grid_cols,grid_rows,lot_spacing_m,world_origin_m,
                source_triangle_budget,source_instance_budget,
                director_overrides=None,expected_revision=0,director_event):
        _require_pid(pid)
        _id(district_id,"original film district ID")
        plan=self.plan(
            pid,seed=seed,source_buildings=source_buildings,
            grid_cols=grid_cols,grid_rows=grid_rows,
            lot_spacing_m=lot_spacing_m,world_origin_m=world_origin_m,
            source_triangle_budget=source_triangle_budget,
            source_instance_budget=source_instance_budget,
            director_overrides=director_overrides)
        with self._stage(pid,plan) as opened:
            receipt=opened["receipt"]
        record={**plan,"native_source_receipt":receipt}
        scope={
            "operation":"nvp.film02m_e.publish_original_layered_district.v1",
            "project_id":pid,"district_id":district_id,
            "expected_revision":expected_revision,
            "original_source_plan_sha256":_sha(plan),
            "native_original_layer_source_sha256":receipt[
                "district_root_sha256"],
            "exact_generated_instance_count":len(plan["generated_instances"]),
            "source_triangle_budget":source_triangle_budget}
        if self.approve(director_event,scope) is not True:
            raise PermissionError("Director must approve exact source district with all edits")
        dependencies=sorted([
            {"object_id":p["building_id"],"revision":p["revision"],
             "role":"world"} for p in plan["original_prototypes"]],
            key=lambda d:(d["object_id"],d["revision"],d["role"]))
        return self.index.register_revision(
            pid,district_id,"presentation",record,
            expected_revision=expected_revision,
            dependencies=dependencies)

    @contextmanager
    def open(self,pid,district_id,revision):
        _require_pid(pid);_id(district_id,"exact source film district")
        record=self.index.read_revision(pid,district_id,revision)
        document=record["data"]
        if record["kind"]!="presentation" or document.get("format")!=FORMAT:
            raise PermissionError("Only originally approved source film district")
        raw={k:v for k,v in document.items() if k!="native_source_receipt"}
        regenerated=self._replan(pid,document)
        if regenerated!=raw:
            raise RuntimeError("Original generator/override film district was altered")
        edges=sorted([
            {"object_id":p["building_id"],"revision":p["revision"],
             "role":"world"} for p in regenerated["original_prototypes"]],
            key=lambda d:(d["object_id"],d["revision"],d["role"]))
        if record["dependencies"]!=edges:
            raise PermissionError("Original building source dependency graph changed")
        with self._stage(pid,regenerated) as result:
            if result["receipt"]!=document["native_source_receipt"]:
                raise RuntimeError("Previously approved original USD layer/mesh SHA changed")
            yield {"record":record,"plan":regenerated,**result}
