"""USD-FILM-02M-A/B/C: original reusable architecture and socket assembly.

The authoritative source remains project-local FilmIndex OpenUSD mesh assets.
Every module pins an exact original mesh revision/SHA, meter/Z-up bounds and
director-defined sockets. A deterministic, reviewed blueprint produces an
immutable ordered module choice/placement world revision. Native OpenUSD
references compose the source geometry; never browser-generated paths.

This is source geometry composition, not a physics load test, an inhabited
building model, a real-world survey or accepted Cycles movie imagery.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import math
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import _usd,LAYER_TYPE

MODULE_FORMAT="nvp.usd_film02m.original_module.v1"
BUILD_FORMAT="nvp.usd_film02m.original_module_assembly.v1"
ROLES={"floor","facade","rear","side","roof","core","corner",
       "bay","window","interior","trim","storefront"}
REQUIRED_BUILDING={"floor","facade","rear","side","roof"}
GENDERS={"male","female","universal"}
ORIENTATIONS=(0,90,180,270)
MAX_NODES=48
MAX_OPTIONS=8
MAX_SOCKETS=16
MAX_ASSEMBLIES=4
MAX_STAGE_BYTES=8*1024*1024
MIN_SIZE=.025
MAX_SIZE=500
MAX_STAGING=32*1024*1024
EPS=.001
PRIM_TOKEN=re.compile(r'[A-Za-z][A-Za-z0-9_]{0,49}\Z')


def _sha(payload):
    return sha256(json.dumps(payload,sort_keys=True,
        separators=(",",":"),ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()


def _vector(value,what,*,max_abs=1_000_000):
    if (type(value) is not list or len(value)!=3 or
        any(type(x) not in (int,float) or
            not math.isfinite(x) or abs(x)>max_abs
            for x in value)):
        raise ValueError("Finite typed three-axis "+what+" required")
    return [float(x) for x in value]


def _dims(value):
    dims=_vector(value,"dimensions",max_abs=MAX_SIZE)
    if any(v<MIN_SIZE for v in dims):
        raise ValueError("Real building modules require positive metre dimensions")
    return dims


def _rotate(point,yaw):
    x,y,z=point
    if yaw==0:return [x,y,z]
    if yaw==90:return [-y,x,z]
    if yaw==180:return [-x,-y,z]
    if yaw==270:return [y,-x,z]
    raise ValueError("Only quarter-turn Z-up assembly rotations")


def _translate(a,b):
    return [round(x+y,6) for x,y in zip(a,b)]


def _bbox(local_size,position,yaw):
    a,b,c=local_size
    if yaw in (90,270):a,b=b,a
    return [[round(position[i]-v/2,6) for i,v in enumerate((a,b,c))],
            [round(position[i]+v/2,6) for i,v in enumerate((a,b,c))]]


def _sockets(items,dims):
    if (type(items) is not list or not 1<=len(items)<=MAX_SOCKETS):
        raise ValueError("Bounded source-authored module sockets required")
    result=[]
    seen=set()
    half=[x/2 for x in dims]
    for item in items:
        if type(item) is not dict or set(item)!={
                "name","connector_type","gender","at_m",
                "normal","span_m","tolerance_m"}:
            raise ValueError("Typed local module socket contract required")
        name=_id(item["name"],"source connector")
        connector=_id(item["connector_type"],"socket connector type")
        if name in seen or item["gender"] not in GENDERS:
            raise ValueError("Duplicate/unknown connector")
        seen.add(name)
        at=_vector(item["at_m"],"local connector position",max_abs=MAX_SIZE)
        normal=_vector(item["normal"],"local socket outward normal",max_abs=1)
        if (tuple(normal) not in ((1.,0.,0.),(-1.,0.,0.),
                                  (0.,1.,0.),(0.,-1.,0.),
                                  (0.,0.,1.),(0.,0.,-1.))):
            raise ValueError("Original building socket normal must be cardinal Z-up")
        if any(abs(at[i])>half[i]+EPS for i in range(3)):
            raise ValueError("Socket lies outside real authored mesh bounds")
        axis=next(i for i,x in enumerate(normal) if x)
        if abs(at[axis]-normal[axis]*half[axis])>.02:
            raise ValueError("Socket must lie on the declared geometry's outward face")
        span=item["span_m"]
        tol=item["tolerance_m"]
        if (type(span) not in (int,float) or not math.isfinite(span) or
            not .025<=span<=500 or type(tol) not in (int,float) or
            not math.isfinite(tol) or not 0<=tol<=.02):
            raise ValueError("Measured connector span/tolerance outside approved range")
        result.append({
            "name":name,"connector_type":connector,
            "gender":item["gender"],
            "at_m":at,"normal":normal,
            "span_m":float(span),"tolerance_m":float(tol)})
    return result


def _snap(parent,parent_yaw,parent_pos,child,child_yaw,
          parent_socket,child_socket):
    a=next((x for x in parent["sockets"]
            if x["name"]==parent_socket),None)
    b=next((x for x in child["sockets"]
            if x["name"]==child_socket),None)
    if a is None or b is None:
        raise PermissionError("Cannot join nonexistent original building connectors")
    if (a["connector_type"]!=b["connector_type"] or
        (a["gender"]==b["gender"] and a["gender"]!="universal")):
        raise ValueError("Incompatible connector types/genders")
    tol=max(a["tolerance_m"],b["tolerance_m"])
    if abs(a["span_m"]-b["span_m"])>tol:
        raise ValueError("Building connector spans do not physically fit")
    n1=_rotate(a["normal"],parent_yaw)
    n2=_rotate(b["normal"],child_yaw)
    if any(abs(n1[i]+n2[i])>1e-6 for i in range(3)):
        raise ValueError("Assembly socket orientations are not opposing")
    destination=_translate(parent_pos,_rotate(a["at_m"],parent_yaw))
    child_rot=_rotate(b["at_m"],child_yaw)
    result=[round(destination[i]-child_rot[i],6) for i in range(3)]
    return result,{
        "parent_socket":parent_socket,"own_socket":child_socket,
        "connector_type":a["connector_type"],
        "joint_position_m":destination,
        "normal_pair":[n1,n2],
        "span_m":[a["span_m"],b["span_m"]],
        "tolerance_m":tol}


class OriginalBuildingKit:
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("Real original FilmIndex and host-held director approval")
        self.index=index
        self.approve=verify_director_action

    def module(self,pid,module_id,revision):
        _require_pid(pid);_id(module_id,"original building module")
        record=self.index.read_revision(pid,module_id,revision)
        doc=record["data"]
        if record["kind"]!="style" or doc.get("format")!=MODULE_FORMAT:
            raise PermissionError("Not a real original reusable building module")
        asset=self.index.read_revision(
            pid,doc["asset_id"],doc["asset_revision"])
        dependencies=[{"object_id":doc["asset_id"],
                       "revision":doc["asset_revision"],"role":"asset"}]
        detail=doc.get("geometry_detail")
        if detail is not None:
            if type(detail) is not dict or set(detail)!={
                    "detail_id","revision","document_sha256"}:
                raise PermissionError("Original source geometry detail cannot be loose")
            from backend.nvp_usd_film02m_d_openings import verify_detail
            detail_row=verify_detail(
                self.index,pid,detail["detail_id"],detail["revision"],
                asset_id=doc["asset_id"],asset_revision=doc["asset_revision"])
            if detail_row["document_sha256"]!=detail["document_sha256"]:
                raise RuntimeError("Original doorway/interior procedural source changed")
            if ((doc["role"] in ("facade","storefront") and
                 detail_row["data"]["geometry_kind"]!="wall_with_real_apertures") or
                (doc["role"]=="interior" and
                 detail_row["data"]["geometry_kind"]!="genuine_room_interior_shell")):
                raise PermissionError("Source geometry detail has wrong building role")
            dependencies.append({
                "object_id":detail["detail_id"],
                "revision":detail["revision"],"role":"presentation"})
        dependencies.sort(key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if (asset["kind"]!="asset" or
            asset["document_sha256"]!=doc["asset_document_sha256"] or
            doc["source_layer_sha256"]!=asset["data"].get("layer_sha256") or
            record["dependencies"]!=dependencies):
            raise RuntimeError("Building module lost its immutable asset dependencies")
        source_record,layer=OpenUSDAssetRegistry(self.index).open(
            pid,doc["asset_id"],doc["asset_revision"])
        points=source_record["data"].get("points")
        if source_record["data"]["shape"]!="mesh" or not points:
            raise RuntimeError("Native architecture must use actual source mesh topology")
        minimum=[min(v[i] for v in points) for i in range(3)]
        maximum=[max(v[i] for v in points) for i in range(3)]
        dims=[maximum[i]-minimum[i] for i in range(3)]
        if (any(abs(dims[i]-doc["size_m"][i])>0.002 for i in range(3)) or
            any(abs((maximum[i]+minimum[i])/2)>0.002 for i in range(3))):
            raise RuntimeError("Frozen original module geometry bounds changed")
        expected=_sockets(doc["sockets"],doc["size_m"])
        if expected!=doc["sockets"]:
            raise RuntimeError("Original socket dimensions changed")
        return {**doc,"module_id":module_id,"revision":revision,
                "document_sha256":record["document_sha256"]}

    def publish_module(self,pid,module_id,*,asset_id,asset_revision,
                       role,style_family,size_m,sockets,
                       expected_revision=0,director_event,
                       geometry_detail_id=None,geometry_detail_revision=None):
        _require_pid(pid)
        _id(module_id,"original module ID")
        _id(asset_id,"original NVP geometry asset")
        style=_id(style_family,"architectural style family")
        if role not in ROLES:
            raise ValueError("Unknown first-party film architecture part")
        dims=_dims(size_m)
        sockets=_sockets(sockets,dims)
        record,layer=OpenUSDAssetRegistry(self.index).open(
            pid,asset_id,asset_revision)
        source=record["data"]
        if source["shape"]!="mesh":
            raise PermissionError("Film modular building needs genuine authored mesh")
        points=source["points"]
        if not 8<=len(points)<=2048 or len(source["triangles"])<12:
            raise ValueError("Architecture must have genuine bounded 3D mesh faces")
        bounds=[[min(p[i] for p in points),max(p[i] for p in points)]
                for i in range(3)]
        if any(abs(bounds[i][1]-bounds[i][0]-dims[i])>.002 or
               abs((bounds[i][0]+bounds[i][1])/2)>.002 for i in range(3)):
            raise PermissionError("Director declared sizes must match actual USD vertices")
        detail=None
        dependencies=[{"object_id":asset_id,
                       "revision":asset_revision,"role":"asset"}]
        if geometry_detail_id is not None:
            if type(geometry_detail_revision) is not int or geometry_detail_revision<1:
                raise ValueError("Exact first-party source geometry detail revision needed")
            from backend.nvp_usd_film02m_d_openings import verify_detail
            row=verify_detail(
                self.index,pid,geometry_detail_id,geometry_detail_revision,
                asset_id=asset_id,asset_revision=asset_revision)
            detail={"detail_id":geometry_detail_id,
                    "revision":geometry_detail_revision,
                    "document_sha256":row["document_sha256"]}
            if ((role in ("facade","storefront") and
                 row["data"]["geometry_kind"]!="wall_with_real_apertures") or
                (role=="interior" and
                 row["data"]["geometry_kind"]!="genuine_room_interior_shell") or
                role not in ("facade","storefront","interior")):
                raise PermissionError("Source geometry detail incompatible with module role")
            dependencies.append({"object_id":geometry_detail_id,
                                 "revision":geometry_detail_revision,
                                 "role":"presentation"})
        elif geometry_detail_revision is not None:
            raise ValueError("Dangling original geometry detail revision")
        dependencies.sort(key=lambda x:(x["object_id"],x["revision"],x["role"]))
        proposal={
            "format":MODULE_FORMAT,"role":role,"style_family":style,
            "size_m":dims,"coordinate_system":"meters_Z_up",
            "asset_id":asset_id,"asset_revision":asset_revision,
            "asset_document_sha256":record["document_sha256"],
            "source_layer_sha256":source["layer_sha256"],
            "sockets":sockets,
            "source_mesh_real":True,"uniform_scale_required":True,
            "openusd_external_paths_authoritative":False,
            "cycles_pixels_reviewed":False}
        if detail is not None:
            proposal["geometry_detail"]=detail
        scope={
            "operation":"nvp.film02m.publish_original_building_module.v1",
            "project_id":pid,"module_id":module_id,
            "expected_revision":expected_revision,
            "asset_id":asset_id,"asset_revision":asset_revision,
            "asset_sha256":record["document_sha256"],
            "proposed_module_sha256":_sha(proposal)}
        if self.approve(director_event,scope) is not True:
            raise PermissionError("An AI proposal cannot authorize geometry modules")
        return self.index.register_revision(
            pid,module_id,"style",proposal,
            expected_revision=expected_revision,
            dependencies=dependencies)

    def _resolve(self,pid,seed,blueprint):
        if type(seed) is not int or not 0<=seed<2**63:
            raise ValueError("Explicit bounded deterministic director seed required")
        if type(blueprint) is not list or not 6<=len(blueprint)<=MAX_NODES:
            raise ValueError("One bounded exterior building requires six or more parts")
        placements=[]
        by_id={}
        role_counts={}
        dependencies={}
        for i,part in enumerate(blueprint):
            if type(part) is not dict or set(part)!={
                    "node_id","options","parent_id","parent_socket",
                    "own_socket","yaw_deg","root_position_m"}:
                raise ValueError("Typed ordered building assembly node required")
            node=_id(part["node_id"],"original building node")
            if not PRIM_TOKEN.fullmatch(node):
                raise ValueError("Building node ID must be a safe native USD prim token")
            if node in by_id:
                raise ValueError("Duplicate piece in original building")
            yaw=part["yaw_deg"]
            if type(yaw) is not int or yaw not in ORIENTATIONS:
                raise ValueError("Architecture needs cardinal Z-up orientation")
            options=part["options"]
            if (type(options) is not list or not 1<=len(options)<=MAX_OPTIONS or
                any(type(o) is not dict or set(o)!={
                    "module_id","revision"} for o in options)):
                raise ValueError("Only explicit exact approved source module alternatives")
            available=[self.module(pid,o["module_id"],o["revision"])
                       for o in options]
            styles={x["style_family"] for x in available}
            roles={x["role"] for x in available}
            dims={tuple(x["size_m"]) for x in available}
            if len(styles)!=1 or len(roles)!=1 or len(dims)!=1:
                raise ValueError("Substitutable modules must preserve style, role, actual dimensions")
            choice=int(sha256((
                str(seed)+"|"+node+"|"+_sha(options)).encode("ascii")
                ).hexdigest(),16)%len(available)
            module=available[choice]
            role=module["role"]
            role_counts[role]=role_counts.get(role,0)+1
            if i==0:
                if (role!="floor" or part["parent_id"] is not None or
                    part["parent_socket"] is not None or
                    part["own_socket"] is not None):
                    raise ValueError("Original building root must be a real floor")
                position=_vector(part["root_position_m"],"building root position")
                joint=None
            else:
                if part["root_position_m"] is not None:
                    raise ValueError("Only original floor may own a world-space root")
                parent=by_id.get(part["parent_id"])
                if parent is None:
                    raise ValueError("Original module parent must already exist")
                position,joint=_snap(
                    parent["module"],parent["yaw_deg"],
                    parent["position_m"],module,yaw,
                    part["parent_socket"],part["own_socket"])
            extent=_bbox(module["size_m"],position,yaw)
            for prev in placements:
                # Actual module mesh bounds checked at source. AABB broad
                # phase rejects volumetric overlaps; face/corner seams touch.
                prev_extent=prev["world_bounds_m"]
                overlaps=[min(extent[1][j],prev_extent[1][j])-
                          max(extent[0][j],prev_extent[0][j]) for j in range(3)]
                if all(x>0.021 for x in overlaps):
                    raise ValueError(
                        "Original building parts interpenetrate as solids: "+
                        node+" and "+prev["node_id"])
            placed={
                "node_id":node,"role":role,
                "module_id":module["module_id"],
                "module_revision":module["revision"],
                "module_document_sha256":module["document_sha256"],
                "asset_id":module["asset_id"],
                "asset_revision":module["asset_revision"],
                "asset_document_sha256":module["asset_document_sha256"],
                "source_layer_sha256":module["source_layer_sha256"],
                "style_family":module["style_family"],
                "module_size_m":module["size_m"],
                "yaw_deg":yaw,"position_m":position,
                "world_bounds_m":extent,"parent_id":part["parent_id"],
                "connector_fit":joint,"option_index":choice,
                "options":options}
            placements.append(placed)
            by_id[node]={"module":module,"yaw_deg":yaw,
                         "position_m":position}
            dependencies[(module["module_id"],module["revision"])]={
                "object_id":module["module_id"],
                "revision":module["revision"],"role":"style"}
        if not REQUIRED_BUILDING.issubset(role_counts):
            raise ValueError("Original building needs floor, facade, rear, side and roof")
        if role_counts["side"]<2:
            raise ValueError("Building requires two 3D sides for reverse-angle shooting")
        styles={x["style_family"] for x in placements}
        if len(styles)!=1:
            raise ValueError("All original building pieces must share an approved style")
        return placements,sorted(
            dependencies.values(),key=lambda x:(
                x["object_id"],x["revision"],x["role"]))

    def publish_building(self,pid,building_id,*,seed,blueprint,
                         expected_revision=0,director_event):
        _require_pid(pid);_id(building_id,"assembled original building")
        placed,edges=self._resolve(pid,seed,blueprint)
        doc={
            "format":BUILD_FORMAT,"coordinate_system":"meters_Z_up",
            "meters_per_unit":1.0,"building_id":building_id,
            "seed":seed,"blueprint":blueprint,"placements":placed,
            "module_count":len(placed),"style_family":placed[0]["style_family"],
            "source_dependencies_only":True,"original_actors_untouched":True,
            "real_3d_source_not_flat_facade":True,
            "external_usd_paths_authoritative":False,
            "renderer_pixels_verified":False,
            "source_geometry_quality_accepted":False}
        with self.open_proposal(pid,doc) as source:
            doc["original_usd_root_sha256"]=source["root_layer_sha256"]
            doc["actual_reopened_mesh_count"]=source["mesh_count"]
            doc["source_references_reopened"]=source["referenced_modules"]
        scope={
            "operation":"nvp.film02m.publish_original_architecture.v1",
            "project_id":pid,"building_id":building_id,
            "expected_revision":expected_revision,
            "seed":seed,"selected_modules_sha256":_sha(placed),
            "original_usd_root_sha256":doc["original_usd_root_sha256"],
            "proposed_assembly_sha256":_sha(doc)}
        if self.approve(director_event,scope) is not True:
            raise PermissionError("Director must approve exact original building world")
        return self.index.register_revision(
            pid,building_id,"world",doc,
            expected_revision=expected_revision,dependencies=edges)

    @contextmanager
    def open_proposal(self,pid,doc):
        # All asset paths are derived from SHA-pinned project FilmIndex blobs,
        # never accepted from external USD, a web request or an LLM script.
        if not isinstance(doc,dict) or doc.get("format")!=BUILD_FORMAT:
            raise ValueError("Only original source-locked module assemblies")
        Gf,Sdf,Usd,UsdGeom=_usd()
        with TemporaryDirectory(prefix="nvp-original-02m-building-") as location:
            root=Path(location)
            assets=root/"assets"
            assets.mkdir()
            seen={}
            for row in doc["placements"]:
                module=self.module(pid,row["module_id"],row["module_revision"])
                if (module["document_sha256"]!=row["module_document_sha256"] or
                    module["source_layer_sha256"]!=row["source_layer_sha256"] or
                    module["asset_id"]!=row["asset_id"] or
                    module["asset_revision"]!=row["asset_revision"]):
                    raise RuntimeError("Source building module was replaced")
                if row["source_layer_sha256"] not in seen:
                    payload=self.index.get_blob(
                        pid,row["source_layer_sha256"])
                    if len(payload)>MAX_STAGING:
                        raise RuntimeError("Film building asset stage budget exceeded")
                    target=assets/(row["source_layer_sha256"]+".usda")
                    target.write_bytes(payload)
                    seen[row["source_layer_sha256"]]=target
            stage_path=root/"building.usda"
            stage=Usd.Stage.CreateNew(str(stage_path))
            UsdGeom.SetStageMetersPerUnit(stage,1.)
            UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
            world=UsdGeom.Xform.Define(stage,"/World")
            stage.SetDefaultPrim(world.GetPrim())
            pieces=UsdGeom.Xform.Define(stage,"/World/Buildings")
            from pxr import Gf
            for row in doc["placements"]:
                source_path=(
                    "./assets/"+row["source_layer_sha256"]+".usda")
                prim=UsdGeom.Xform.Define(
                    stage,"/World/Buildings/"+row["node_id"])
                api=UsdGeom.XformCommonAPI(prim)
                if not api.SetTranslate(Gf.Vec3d(*row["position_m"])):
                    raise RuntimeError("Native module translation not authored")
                if not api.SetRotate(Gf.Vec3f(0.,0.,float(row["yaw_deg"]))):
                    raise RuntimeError("Original 3D module quarter-turn rotation failed")
                if not prim.GetPrim().GetReferences().AddReference(
                        source_path,Sdf.Path("/Asset")):
                    raise RuntimeError("Native OpenUSD module reference did not compose")
            layer=stage.GetRootLayer()
            raw=layer.ExportToString().encode("utf8")
            if len(raw)>MAX_STAGE_BYTES:
                raise RuntimeError("Reusable building USD stage exceeds review bound")
            if not layer.Save():
                raise RuntimeError("Original building USD layer not saved")
            # Persist and verify actual source USD BYTES that Blender consumes,
            # not an unsaved in-memory serialization that might differ.
            root_sha=sha256(stage_path.read_bytes()).hexdigest()
            reopened=Usd.Stage.Open(str(stage_path))
            if reopened is None or not reopened.GetPrimAtPath(
                    "/World/Buildings").IsDefined():
                raise RuntimeError("Original architecture USD stage cannot reopen")
            mesh_count=0
            referenced=[]
            for row in doc["placements"]:
                prim=reopened.GetPrimAtPath(
                    "/World/Buildings/"+row["node_id"])
                geom=reopened.GetPrimAtPath(
                    "/World/Buildings/"+row["node_id"]+"/Geometry")
                if not prim.IsDefined() or not geom.IsA(UsdGeom.Mesh):
                    raise RuntimeError("Camera-facing or rear original mesh missing")
                mesh=UsdGeom.Mesh(geom)
                points=mesh.GetPointsAttr().Get()
                faces=mesh.GetFaceVertexCountsAttr().Get()
                if not points or len(points)<8 or not faces or len(faces)<12:
                    raise RuntimeError("No real original mesh for architecture module")
                # The USD external source layer was staged from FilmIndex only;
                # genuine composed instances expose the same authored data.
                mesh_count+=1
                referenced.append({
                    "node_id":row["node_id"],
                    "module_document_sha256":row["module_document_sha256"],
                    "usd_prim_path":str(prim.GetPath()),
                    "source_layer_sha256":row["source_layer_sha256"],
                    "source_mesh_triangle_count":len(faces)})
            if len(referenced)!=doc["module_count"]:
                raise RuntimeError("A modular building lost source geometry")
            yield {
                "stage":reopened,"root_layer_sha256":root_sha,
                "mesh_count":mesh_count,
                "referenced_modules":referenced,
                "source_paths_temporary":True,
                "original_source_meshes_reopened":True}

    @contextmanager
    def open_building(self,pid,building_id,revision):
        _require_pid(pid);_id(building_id,"published building")
        record=self.index.read_revision(pid,building_id,revision)
        doc=record["data"]
        if record["kind"]!="world" or doc.get("format")!=BUILD_FORMAT:
            raise PermissionError("Original modular architecture world not published")
        placed,edges=self._resolve(pid,doc["seed"],doc["blueprint"])
        if (doc.get("coordinate_system")!="meters_Z_up" or
            doc.get("meters_per_unit")!=1.0 or
            doc.get("source_dependencies_only") is not True or
            doc.get("original_actors_untouched") is not True or
            doc.get("real_3d_source_not_flat_facade") is not True or
            doc.get("external_usd_paths_authoritative") is not False or
            doc.get("renderer_pixels_verified") is not False or
            doc.get("source_geometry_quality_accepted") is not False or
            doc.get("style_family")!=placed[0]["style_family"] or
            doc.get("placements")!=placed or
            doc.get("module_count")!=len(placed) or
            doc.get("building_id")!=building_id or
            record["dependencies"]!=edges):
            raise RuntimeError("Original module selection manifest was substituted")
        with self.open_proposal(pid,doc) as result:
            if (result["root_layer_sha256"]!=doc["original_usd_root_sha256"] or
                result["mesh_count"]!=doc["actual_reopened_mesh_count"] or
                result["referenced_modules"]!=doc["source_references_reopened"]):
                raise RuntimeError("Previously approved native 3D module world changed")
            yield {**result,"record":record,"building":doc}
