"""USD-FILM-02M-D: source-verified architecture cells with hysteresis.

Camera distance is a prefetch HINT only, not a visibility algorithm.
Director-required and immediately-next-shot sets always win.
Original source module geometry/FilmIndex revisions never change.
USD payloads load/unload real 3D building sources, not proxy pictures.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import json
import math
import shutil

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_scene import _usd
from backend.nvp_usd_film02m_modular_buildings import (
    OriginalBuildingKit,BUILD_FORMAT,_sha,_vector)

FORMAT="nvp.usd_film02m.original_building_camera_cells.v1"
MAX_CELLS=16
MAX_SCENE_SOURCE_BYTES=96*1024*1024
MAX_CAMERA_SAMPLES=16


def _bounds(placements):
    lower=[min(p["world_bounds_m"][0][i] for p in placements)
           for i in range(3)]
    upper=[max(p["world_bounds_m"][1][i] for p in placements)
           for i in range(3)]
    return [
        [round(float(x),6) for x in lower],
        [round(float(x),6) for x in upper]]


def _dist_to_aabb(p,bounds):
    return math.sqrt(sum(
        max(bounds[0][i]-p[i],0.,p[i]-bounds[1][i])**2
        for i in range(3)))


class OriginalBuildingCells:
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("Only real FilmIndex and NVP host director authority")
        self.index=index
        self.approve=verify_director_action
        self.kit=OriginalBuildingKit(
            index,verify_director_action=lambda *_:False)

    def _resolve(self,pid,cells):
        if type(cells) is not list or not 1<=len(cells)<=MAX_CELLS:
            raise ValueError("Bounded source original building cell catalog")
        result=[]
        edges=[]
        names=set()
        for cell in cells:
            if type(cell) is not dict or set(cell)!={
                    "cell_id","building_id","building_revision"}:
                raise ValueError("Each cell references one exact published original building")
            cid=_id(cell["cell_id"],"original film building cell")
            if cid in names:
                raise ValueError("Duplicate cell cannot alias original building")
            names.add(cid)
            bid=_id(cell["building_id"],"original film building")
            revision=cell["building_revision"]
            if type(revision) is not int or revision<1:
                raise ValueError("Exact original building source revision required")
            with self.kit.open_building(pid,bid,revision) as original:
                row=original["record"]
                if row["kind"]!="world" or row["data"]["format"]!=BUILD_FORMAT:
                    raise PermissionError("Original cell not a source building revision")
                bounds=_bounds(original["building"]["placements"])
                result.append({
                    "cell_id":cid,
                    "building_id":bid,"building_revision":revision,
                    "building_sha256":row["document_sha256"],
                    "usd_layer_sha256":original["root_layer_sha256"],
                    "bounds_m":bounds,"original_mesh_count":original["mesh_count"]})
            edges.append({
                "object_id":bid,"revision":revision,"role":"world"})
        edges=sorted(edges,key=lambda x:(
            x["object_id"],x["revision"],x["role"]))
        return result,edges

    def publish(self,pid,cell_world_id,*,cells,director_event,
                expected_revision=0):
        _require_pid(pid)
        _id(cell_world_id,"project original architecture cell world")
        normalized,edges=self._resolve(pid,cells)
        doc={
            "format":FORMAT,"coordinate_system":"meters_Z_up",
            "meters_per_unit":1.0,
            "original_cells":normalized,
            "original_world_takes_modified":False,
            "director_required_cells_are_never_culled":True,
            "camera_distance_is_only_prefetch_hint":True,
            "renderer_quality_verified":False,
            "source_external_paths_authoritative":False}
        scope={
            "operation":"nvp.film02m.publish_original_building_cells.v1",
            "project_id":pid,"cell_world_id":cell_world_id,
            "expected_revision":expected_revision,
            "source_cell_sha256":_sha(normalized),
            "source_cell_manifest_sha256":_sha(doc)}
        if self.approve(director_event,scope) is not True:
            raise PermissionError("Director must approve exact original cell inventory")
        return self.index.register_revision(
            pid,cell_world_id,"presentation",doc,
            expected_revision=expected_revision,
            dependencies=edges)

    @contextmanager
    def open(self,pid,cell_world_id,revision):
        _require_pid(pid)
        _id(cell_world_id,"original camera-aware architecture world")
        record=self.index.read_revision(pid,cell_world_id,revision)
        doc=record["data"]
        if record["kind"]!="presentation" or doc.get("format")!=FORMAT:
            raise PermissionError("Not a real original approved building cell manifest")
        original=[
            {k:x[k] for k in ("cell_id","building_id","building_revision")}
            for x in doc["original_cells"]]
        normalized,edges=self._resolve(pid,original)
        if (normalized!=doc["original_cells"] or
            record["dependencies"]!=edges or
            doc["coordinate_system"]!="meters_Z_up" or
            doc["meters_per_unit"]!=1.0 or
            doc["original_world_takes_modified"] is not False or
            doc["director_required_cells_are_never_culled"] is not True or
            doc["camera_distance_is_only_prefetch_hint"] is not True or
            doc["renderer_quality_verified"] is not False or
            doc["source_external_paths_authoritative"] is not False):
            raise RuntimeError("Original cell layout or source revision has changed")
        with TemporaryDirectory(prefix="nvp-original-building-camera-cells-") as temp:
            root=Path(temp)
            building_dir=root/"buildings"
            asset_dir=building_dir/"assets"
            asset_dir.mkdir(parents=True)
            written=set()
            total=0
            for cell in normalized:
                with self.kit.open_building(
                        pid,cell["building_id"],
                        cell["building_revision"]) as built:
                    source=Path(
                        built["stage"].GetRootLayer().realPath).resolve(strict=True)
                    target=building_dir/(cell["cell_id"]+".usda")
                    body=source.read_bytes()
                    if sha256(body).hexdigest()!=cell["usd_layer_sha256"]:
                        raise RuntimeError("Original derived architecture source bytes changed")
                    total+=len(body)
                    target.write_bytes(body)
                    for asset in (source.parent/"assets").glob("*.usda"):
                        sha=asset.stem
                        if sha not in written:
                            raw=asset.read_bytes()
                            if sha256(raw).hexdigest()!=sha:
                                raise RuntimeError("Native original building asset SHA mismatch")
                            total+=len(raw)
                            written.add(sha)
                            (asset_dir/asset.name).write_bytes(raw)
                        if total>MAX_SCENE_SOURCE_BYTES:
                            raise RuntimeError("Original building cell staging exceeds memory budget")
            Gf,Sdf,Usd,UsdGeom=_usd()
            path=root/"cell_world.usda"
            stage=Usd.Stage.CreateNew(str(path))
            UsdGeom.SetStageMetersPerUnit(stage,1.)
            UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
            world=UsdGeom.Xform.Define(stage,"/World")
            stage.SetDefaultPrim(world.GetPrim())
            UsdGeom.Xform.Define(stage,"/World/Cells")
            for cell in normalized:
                prim=UsdGeom.Xform.Define(
                    stage,"/World/Cells/"+cell["cell_id"])
                if not prim.GetPrim().GetPayloads().AddPayload(
                        "./buildings/"+cell["cell_id"]+".usda",
                        Sdf.Path("/World")):
                    raise RuntimeError("Native original building payload failed")
            if not stage.GetRootLayer().Save():
                raise RuntimeError("Original native building cell world cannot be saved")
            original_stage_sha=sha256(path.read_bytes()).hexdigest()
            reopened=Usd.Stage.Open(str(path),load=Usd.Stage.LoadNone)
            if not reopened:
                raise RuntimeError("Original architecture cells cannot reopen unloaded")
            for item in normalized:
                prim=reopened.GetPrimAtPath(
                    "/World/Cells/"+item["cell_id"])
                if not prim.IsDefined() or prim.IsLoaded():
                    raise RuntimeError("Original building must start as unloaded USD payload")
            session=BuildingCellSession(
                reopened,record,normalized,
                source_root_sha256=original_stage_sha,
                original_asset_source_bytes=total)
            try:
                yield session
            finally:
                session.close()


class BuildingCellSession:
    def __init__(self,stage,record,original,
                 *,source_root_sha256,original_asset_source_bytes):
        self.stage=stage
        self.record=record
        self.original={x["cell_id"]:x for x in original}
        self.root_sha256=source_root_sha256
        self.staging_bytes=original_asset_source_bytes
        self.loaded=set()
        self.closed=False

    def close(self):
        self.closed=True
        self.stage=None
        self.loaded.clear()

    def transition(self,*,camera_positions_m,required_cell_ids,
                   next_shot_required_cell_ids=None,
                   load_distance_m,unload_distance_m,max_loaded_cells):
        if self.closed:
            raise RuntimeError("Original camera cell working set already closed")
        names=set(self.original)
        if (type(required_cell_ids) is not list or
            type(next_shot_required_cell_ids) not in (type(None),list) or
            not all(type(x) is str and x in names
                    for x in required_cell_ids) or
            not all(type(x) is str and x in names for x in
                    (next_shot_required_cell_ids or []))):
            raise ValueError("Every director-required source set must be original")
        if (type(camera_positions_m) is not list or
            not 1<=len(camera_positions_m)<=MAX_CAMERA_SAMPLES):
            raise ValueError("Bounded camera source samples required")
        camera=[_vector(p,"camera position") for p in camera_positions_m]
        if (type(load_distance_m) not in (int,float) or
            type(unload_distance_m) not in (int,float) or
            not math.isfinite(load_distance_m) or
            not math.isfinite(unload_distance_m) or
            not 0<=load_distance_m<unload_distance_m<=10000 or
            type(max_loaded_cells) is not int or
            not 1<=max_loaded_cells<=len(names)):
            raise ValueError("Hysteresis source distances and set budget invalid")
        always=set(required_cell_ids)|set(next_shot_required_cell_ids or [])
        if len(always)>max_loaded_cells:
            raise MemoryError("Available architecture cells cannot omit a director-required shot")
        near={}
        for id,row in self.original.items():
            near[id]=min(_dist_to_aabb(p,row["bounds_m"]) for p in camera)
        keep={id for id in self.loaded if
              id in always or near[id]<=unload_distance_m}
        keep|=always
        # Director's exact requirements are admitted before optional nearest
        # camera hints; no approximate frustum/occlusion claims.
        extra=sorted(
            (x for x in names-keep if near[x]<=load_distance_m),
            key=lambda x:(near[x],x))
        selected=set(keep)
        for id in extra:
            if len(selected)>=max_loaded_cells:break
            selected.add(id)
        if len(selected)>max_loaded_cells:
            # Safe, deterministic eviction of optional far cells while
            # preserving every director-required/source-forecast cell.
            optional=sorted(
                selected-always,key=lambda x:(near[x],x))
            selected=always|set(optional[:max_loaded_cells-len(always)])
        to_unload=sorted(self.loaded-selected)
        to_load=sorted(selected-self.loaded)
        for id in to_unload:
            self.stage.Unload("/World/Cells/"+id)
        for id in to_load:
            self.stage.Load("/World/Cells/"+id)
        checked=[]
        for id in sorted(names):
            prim=self.stage.GetPrimAtPath(
                "/World/Cells/"+id)
            if not prim or prim.IsLoaded()!=(id in selected):
                raise RuntimeError("Native cell payload load state disagrees with source requirement")
            if id in selected:
                geometry=list(self.stage.Traverse())
                child="/World/Cells/"+id+"/Buildings"
                if not self.stage.GetPrimAtPath(child).IsDefined():
                    raise RuntimeError("Original building meshes vanished from required cell")
                real_meshes=sum(
                    1 for p in geometry if p.GetPath().pathString.startswith(
                        child+"/") and p.IsA(__import__(
                            "pxr",fromlist=["UsdGeom"]).UsdGeom.Mesh))
                if real_meshes!=self.original[id]["original_mesh_count"]:
                    raise RuntimeError("Native required building lost referenced original meshes")
                checked.append({
                    "cell_id":id,"native_meshes_reopened":real_meshes,
                    "geometry_source_sha256":self.original[id][
                        "building_sha256"]})
        self.loaded=selected
        return {
            "format":FORMAT,"source_cell_manifest_sha256":self.record[
                "document_sha256"],
            "loaded_cell_ids":sorted(self.loaded),
            "unloaded_cell_ids":sorted(names-self.loaded),
            "newly_loaded":to_load,"newly_unloaded":to_unload,
            "director_required_cells":sorted(always),
            "director_required_geometry_retained":always<=self.loaded,
            "distance_based_prefetch_not_occlusion_proof":True,
            "native_usd_payload_load_verified":True,
            "source_original_building_mesh_receipts":checked,
            "original_actor_takes_unchanged":True,
            "renderer_pixels_generated":False,
            "camera_positions_m_are_hint_not_01d_identity":True}
