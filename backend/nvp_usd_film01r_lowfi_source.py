"""USD-FILM-01R: source-authentic *geometry* low-fi director viewport.

This is a bounded, read-only sampling service, not a film renderer and not an
alternative simulation. At one original Film Time it evaluates the exact 01E
world Take and 01M revisioned director camera in OpenUSD. Native mesh points
are used when bounded; otherwise it exposes an explicitly labeled geometry
bounding-box proxy. Perspective and actor identity come from source USD.

A low-powered PC may request ONE viewpoint/frame at a time. No camera video,
Blender worker, performance resimulation or source revision is created.
"""
from __future__ import annotations

import math

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_usd_film01m_director_camera_bank import (
    DirectorCameraBank,FORMAT as CAMERA_FORMAT)
from backend.nvp_usd_film01q_selected_view_edit import (
    OriginalSelectedViewEdit,EDIT_FORMAT)
from backend.nvp_usd_film01o_original_camera_roll_source import FPS,FRAMES
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T

FORMAT="nvp.usd_film01r.source_3d_lofi_viewpoint.v1"
CATALOG="nvp.usd_film01r.original_world_viewpoint_catalog.v1"
MAX_OBJECTS=128
MAX_MESH_VERTICES=1500
MAX_MESH_TRIANGLES=2500
MAX_TOTAL_VERTICES=12000
MAX_TOTAL_TRIANGLES=18000
MAX_SCANNED_PRIMS=6000


class SourceViewpointWorkspace:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Real original source FilmIndex required")
        self.index=index

    def catalog(self,pid):
        """Only actual published native camera-bank and selected edit revisions."""
        _require_pid(pid)
        banks=[]
        edits=[]
        for row in self.index.list_objects(pid,kind="presentation")[:192]:
            record=self.index.read_revision(pid,row["object_id"],
                                            row["head_revision"])
            if record["data"].get("format")!=CAMERA_FORMAT:
                continue
            doc=DirectorCameraBank(
                self.index,verify_director_action=lambda *_:False).verify(
                    pid,row["object_id"],row["head_revision"])
            banks.append({
                "camera_bank_id":row["object_id"],
                "revision":record["revision"],
                "document_sha256":record["document_sha256"],
                "original_world_take_id":doc["world_take_id"],
                "original_performance_sha256":doc["source_performance_sha256"],
                "cameras":[{
                    "camera_id":camera["camera_id"],
                    "setup":camera["setup"],"framing":camera["framing"],
                    "position_m":camera["position_m"],
                    "rotation_euler_deg":camera["rotation_euler_deg"],
                    "focal_length_mm":camera["focal_length_mm"],
                    "camera_ray_exclusions":camera["camera_ray_exclusions"]}
                    for camera in doc["cameras"]],
            })
        for row in self.index.list_objects(pid,kind="edit")[:192]:
            record=self.index.read_revision(pid,row["object_id"],
                                            row["head_revision"])
            if record["data"].get("format")!=EDIT_FORMAT:
                continue
            doc=OriginalSelectedViewEdit(
                self.index,verify_director_action=lambda *_:False).verify(
                    pid,row["object_id"],row["head_revision"])
            edits.append({
                "edit_id":row["object_id"],"revision":record["revision"],
                "document_sha256":record["document_sha256"],
                "camera_bank_id":doc["camera_bank_id"],
                "camera_bank_revision":doc["camera_bank_revision"],
                "original_performance_sha256":doc[
                    "original_performance_sha256"],
                "cuts":doc["cuts"]})
        return {
            "format":CATALOG,"project_id":pid,
            "camera_banks":banks[:64],"edits":edits[:64],
            "read_only":True,"camera_video_rolls_loaded":False,
            "blender_worker_started":False,
            "no_original_performance_modified":True}

    def snapshot(self,pid,bank_id,revision,*,camera_id,frame):
        from pxr import Usd,UsdGeom,Gf
        _require_pid(pid)
        _id(bank_id,"original film viewpoint source")
        _id(camera_id,"director selected viewpoint")
        if (type(revision) is not int or revision<1 or
            type(frame) is not int or not 0<=frame<FRAMES):
            raise ValueError("One exact camera-bank revision and 0–719 film frame")
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda *_:False)
        original=bank.verify(pid,bank_id,revision)
        chosen=next((x for x in original["cameras"]
                     if x["camera_id"]==camera_id),None)
        if chosen is None:
            raise PermissionError("Camera not in immutable original director rig")
        record=self.index.read_revision(pid,bank_id,revision)
        source_take=self.index.read_revision(
            pid,original["world_take_id"],1)
        tick=frame*T//FPS
        time=Usd.TimeCode(float(tick))
        count=0
        proxies=0
        vertices=0
        triangles=0
        skipped=0
        objects=[]
        source_actors=source_take["data"]["canonical_original_actors"]
        actor_roots={
            item["composed_actor_prim"]:item["actor_id"]
            for item in source_actors}
        exclusions=tuple(chosen["camera_ray_exclusions"])
        with bank.open_source_views(pid,bank_id,revision) as view:
            stage=view["stage"]
            camera_path=view["camera_paths"][camera_id]
            camera_prim=stage.GetPrimAtPath(camera_path)
            camera=UsdGeom.Camera(camera_prim)
            if not camera or not camera_prim.IsDefined():
                raise RuntimeError("Approved source viewport camera disappeared")
            matrix=UsdGeom.Xformable(
                camera_prim).ComputeLocalToWorldTransform(time)
            if not all(math.isfinite(float(matrix[r][c]))
                       for r in range(4) for c in range(4)):
                raise RuntimeError("Original camera generated invalid transform")
            camera_native=matrix
            focal=camera.GetFocalLengthAttr().Get(time)
            aperture=camera.GetVerticalApertureAttr().Get(time)
            if (focal is None or aperture is None or
                not 0.001<float(focal)<5000 or
                not 0.001<float(aperture)<5000):
                raise RuntimeError("Invalid original native lens for low-fi projection")
            fov=math.degrees(2*math.atan(
                float(aperture)/(2*float(focal))))
            fov=max(2.0,min(150.0,fov))
            bounds=UsdGeom.BBoxCache(
                time,[UsdGeom.Tokens.default_,UsdGeom.Tokens.render,
                      UsdGeom.Tokens.proxy],useExtentsHint=True)
            for prim in stage.Traverse():
                count+=1
                if count>MAX_SCANNED_PRIMS:
                    skipped+=1
                    break
                path=str(prim.GetPath())
                if (path.startswith("/World/NVPDirectorCameraRig") or
                    any(path==x or path.startswith(x+"/") for x in exclusions)):
                    continue
                typ=None
                if prim.IsA(UsdGeom.Mesh):typ="mesh"
                elif prim.IsA(UsdGeom.Sphere):typ="sphere_proxy"
                elif prim.IsA(UsdGeom.Cube):typ="box_proxy"
                elif prim.IsA(UsdGeom.Cylinder):typ="cylinder_proxy"
                elif prim.IsA(UsdGeom.Cone):typ="cone_proxy"
                if typ is None:
                    continue
                if len(objects)>=MAX_OBJECTS:
                    skipped+=1
                    continue
                actor_id=next((actor for root,actor in actor_roots.items()
                    if path==root or path.startswith(root+"/")),None)
                item={"prim_path":path,"actor_id":actor_id,
                      "geometry_kind":typ,"source":True}
                if typ=="mesh":
                    mesh=UsdGeom.Mesh(prim)
                    points=mesh.GetPointsAttr().Get(time) or []
                    facecounts=mesh.GetFaceVertexCountsAttr().Get(time) or []
                    indices=mesh.GetFaceVertexIndicesAttr().Get(time) or []
                    faces=sum(max(0,int(n)-2) for n in facecounts)
                    if (points and facecounts and indices and
                        len(points)<=MAX_MESH_VERTICES and
                        faces<=MAX_MESH_TRIANGLES and
                        vertices+len(points)<=MAX_TOTAL_VERTICES and
                        triangles+faces<=MAX_TOTAL_TRIANGLES and
                        sum(facecounts)==len(indices) and
                        all(0<=int(i)<len(points) for i in indices)):
                        xf=UsdGeom.Xformable(
                            prim).ComputeLocalToWorldTransform(time)
                        world_points=[]
                        for p in points:
                            vec=xf.Transform(Gf.Vec3d(
                                float(p[0]),float(p[1]),float(p[2])))
                            world_points.append([
                                round(float(vec[k]),6) for k in range(3)])
                        faces_indices=[]
                        offset=0
                        for n in facecounts:
                            for j in range(1,n-1):
                                faces_indices.extend([
                                    int(indices[offset]),int(indices[offset+j]),
                                    int(indices[offset+j+1])])
                            offset+=n
                        item["points"]=world_points
                        item["triangle_indices"]=faces_indices
                        vertices+=len(world_points)
                        triangles+=len(faces_indices)//3
                    else:
                        item["geometry_kind"]="bbox_proxy"
                try:
                    aligned=bounds.ComputeWorldBound(
                        prim).ComputeAlignedRange()
                    minimum=aligned.GetMin()
                    maximum=aligned.GetMax()
                    xyz=[round(float(minimum[k]),6) for k in range(3)]
                    maximum_xyz=[round(float(maximum[k]),6) for k in range(3)]
                    if not all(math.isfinite(n) for n in xyz+maximum_xyz):
                        raise RuntimeError("Invalid source authored geometric bounds")
                    item["world_bbox_min_m"]=xyz
                    item["world_bbox_max_m"]=maximum_xyz
                except (RuntimeError,ValueError):
                    if "points" not in item:
                        skipped+=1
                        continue
                proxies+=item["geometry_kind"]!="mesh"
                objects.append(item)
        if len(objects)==0:
            raise RuntimeError("Authoritative original scene has no bounded preview geometry")
        return {
            "format":FORMAT,"project_id":pid,
            "camera_bank_id":bank_id,"camera_bank_revision":revision,
            "camera_bank_sha256":record["document_sha256"],
            "original_world_take_sha256":source_take["document_sha256"],
            "original_performance_sha256":original["source_performance_sha256"],
            "camera_id":camera_id,"source_camera_prim":camera_path,
            "frame":frame,"fps":FPS,"original_film_tick":tick,
            "camera_world_matrix_rows":[[
                round(float(camera_native[r][c]),9) for c in range(4)]
                for r in range(4)],
            "camera_vertical_fov_degrees":round(fov,6),
            "camera_focal_length_native_units":float(focal),
            "primary_ray_exclusions":list(exclusions),
            "objects":objects,
            "total_native_mesh_vertices_sent":vertices,
            "total_native_mesh_triangles_sent":triangles,
            "proxy_objects":proxies,"truncated_prims":skipped,
            "original_actor_ids":sorted(actor_roots.values()),
            "source_geometry_approximated":proxies>0 or skipped>0,
            "preview_is_source_derived_not_final_cycles_image":True,
            "preview_does_not_simulate_shadows_or_view_dependent_lighting":True,
            "native_blender_workers_started":0,
            "original_world_and_actor_performance_unchanged":True,
        }
