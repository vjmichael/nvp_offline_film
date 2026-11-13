"""SLATE-06: higher-fidelity, source-composed native OpenUSD presentation.

This milestone renders actual NVP-authored USD Cube/Sphere/triangulated Mesh
geometry, computed world transforms, a selected native UsdGeom.Camera and
UsdLux.SphereLight controls at ONE source tick with SHOT-01 overrides.

It does NOT pretend Xform-only actors are skinned meshes, infer actor faces,
resolve arbitrary external references, apply UsdShade networks/textures,
deform skeletal skin, render jaw/eye animation, or approve a master.
Unsupported 3D data are reported, not silently relabeled photoreal.
The only executable is this NVP-owned fixed first-party Blender recipe.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex
from backend.nvp_slate_proxy_recipe import canonical,sha
from backend.nvp_slate_lazy_preview import SlateLazyPreview
from backend.nvp_openusd_scene import OpenUSDSceneBridge,_usd
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_openusd_native_schemas import MM_PER_CAMERA_UNIT

FORMAT="nvp.slate.native_openusd_scene_presentation.v1"
RENDERER_VERSION="nvp.slate.geometry_cycles.01"
DIMENSIONS={"thumbnail":(320,180),"interactive":(640,360),
            "inspection":(960,540)}
MAX_OBJECTS=48
MAX_VERTICES=1200
MAX_FACES=2500
MAX_SOURCE_BYTES=128*1024
VALID_ROLES=frozenset(("actor","prop","environment","anchor","camera","light"))


def _bounded_number(value,bound=1_000_000):
    n=float(value)
    if not math.isfinite(n) or abs(n)>bound:
        raise RuntimeError("Invalid source OpenUSD geometric quantity")
    return n


def _matrix(world):
    """Gf.Matrix4d uses row vectors; Blender Matrix uses column vectors."""
    values=[[_bounded_number(world[c][r]) for c in range(4)]
            for r in range(4)]
    if any(abs(values[3][c]-float(c==3))>1e-5 for c in range(4)):
        raise RuntimeError("Only finite affine OpenUSD world transforms are renderable")
    return values


def _get_display_color(prim,UsdGeom,t):
    if not prim.IsA(UsdGeom.Gprim):
        return [0.65,0.68,0.73]
    raw=UsdGeom.Gprim(prim).GetDisplayColorPrimvar().Get(t)
    if raw is not None and len(raw)>0:
        return [min(1.0,max(0.0,_bounded_number(x))) for x in raw[0]]
    return [0.65,0.68,0.73]


def _visible(prim,UsdGeom,t):
    imageable=UsdGeom.Imageable(prim)
    return bool(imageable) and str(imageable.ComputeVisibility(t))!="invisible"


def _mesh(prim,UsdGeom,t):
    if prim.IsA(UsdGeom.Cube):
        n=_bounded_number(UsdGeom.Cube(prim).GetSizeAttr().Get(t))
        if not 0<n<=1000:
            raise RuntimeError("USD Cube source size exceeds high-fidelity budget")
        return {"kind":"cube","size":n}
    if prim.IsA(UsdGeom.Sphere):
        radius=_bounded_number(UsdGeom.Sphere(prim).GetRadiusAttr().Get(t))
        if not 0<radius<=500:
            raise RuntimeError("USD Sphere source radius exceeds preview budget")
        return {"kind":"sphere","radius":radius}
    if not prim.IsA(UsdGeom.Mesh):
        raise RuntimeError("Unsupported authored geometry type")
    mesh=UsdGeom.Mesh(prim)
    raw_points=mesh.GetPointsAttr().Get(t)
    counts=mesh.GetFaceVertexCountsAttr().Get(t)
    indices=mesh.GetFaceVertexIndicesAttr().Get(t)
    if raw_points is None or counts is None or indices is None:
        raise RuntimeError("Native USD Mesh topology is incomplete")
    if not 3<=len(raw_points)<=MAX_VERTICES or not 1<=len(counts)<=MAX_FACES:
        raise RuntimeError("OpenUSD Mesh outside bounded preview vertex/face budget")
    if sum(counts)!=len(indices):
        raise RuntimeError("OpenUSD Mesh face topology is malformed")
    points=[[_bounded_number(v) for v in p] for p in raw_points]
    tris=[]
    offset=0
    for count in counts:
        if type(count) not in (int,) or not 3<=count<=64:
            raise RuntimeError("Unsupported degenerate/oversized source USD polygon")
        face=[int(n) for n in indices[offset:offset+count]]
        if any(i<0 or i>=len(points) for i in face):
            raise RuntimeError("Out-of-range source USD mesh vertex index")
        offset+=count
        for j in range(1,len(face)-1):
            tris.append([face[0],face[j],face[j+1]])
            if len(tris)>MAX_FACES:
                raise RuntimeError("OpenUSD triangulation exceeds preview budget")
    return {"kind":"mesh","points":points,"triangles":tris}


def preview_cache_key(ticket,quality,*,camera_path=None):
    """No USD load: SHA-key exact Take/SHOT/tick, native camera and renderer."""
    if type(ticket) is not dict or ticket.get("status")!="SOURCE_REFERENCE_SELECTED":
        raise ValueError("Exact committed source ticket required")
    if quality not in DIMENSIONS:
        raise ValueError("Unknown high-fidelity preview quality")
    if camera_path is not None and (
        type(camera_path) is not str or len(camera_path)>240 or
        not camera_path.startswith("/World/")):
        raise ValueError("Camera path is not a bounded source prim identity")
    return sha(canonical({
        "format":FORMAT,"version":RENDERER_VERSION,
        "take_sha":ticket["source_take_document_sha256"],
        "shot_sha":ticket["source_shot_document_sha256"],
        "tick":ticket["source_tick"],
        "camera_path":camera_path,
        "resolution":DIMENSIONS[quality],
        "script_sha":sha(BLENDER_SCRIPT.encode("utf8")),
    }))


def capture_geometry(index:FilmIndex,ticket,*,camera_path=None):
    """Reopen one SHOT-overlaid OpenUSD scene. No arbitrary user asset files."""
    if not isinstance(index,FilmIndex) or type(ticket) is not dict:
        raise TypeError("Trusted FilmIndex and source selection required")
    lazy=SlateLazyPreview(index)
    fresh=lazy.select(ticket["project_id"],ticket["edit_id"],
                      ticket["edit_revision"],film_tick=ticket["timeline_tick"],
                      quality=ticket["preview_quality"])
    if fresh!=ticket:
        raise RuntimeError("Frozen source ticket changed before geometry snapshot")
    take=index.read_revision(ticket["project_id"],ticket["source_take_id"],
                             ticket["source_take_revision"])
    if ticket["source_shot_id"] is None:
        scene,stage=OpenUSDSceneBridge(index).open(
            ticket["project_id"],take["data"]["scene_id"],
            take["data"]["scene_revision"])
    else:
        shot,scene,stage=OpenUSDShotOverrides(
            index,verify_director_action=lambda *_:False).open_shot(
                ticket["project_id"],ticket["source_shot_id"],
                ticket["source_shot_revision"],tick=ticket["source_tick"])
        if shot["document_sha256"]!=ticket["source_shot_document_sha256"]:
            raise RuntimeError("Shot revision SHA changed")
    if scene["document_sha256"]!=take["data"]["scene_document_sha256"]:
        raise RuntimeError("Scene revision SHA changed")
    return extract_composed_stage(
        stage,scene["data"],tick=ticket["source_tick"],
        source_take_sha=ticket["source_take_document_sha256"],
        source_shot_sha=ticket["source_shot_document_sha256"],
        cache_key=ticket["cache_key"],camera_path=camera_path)


def extract_composed_stage(stage,scene_data,*,tick,source_take_sha=None,
                           source_shot_sha=None,cache_key=None,camera_path=None):
    """Read ONE already-open source stage, no FilmIndex mutation.

    Frozen Takes and pre-Take camera exploration share this exact native
    geometry/lighting/skin extraction. Draft scenes have no Take SHA.
    """
    source_tick=tick
    _,_,Usd,UsdGeom=_usd()
    from pxr import UsdLux
    timecode=Usd.TimeCode(float(source_tick))
    roles=scene_data["prim_roles"]
    # The current NVP-authored geometry layer supports only internal,
    # SHA-addressed assets. No untrusted resolver or external USD file access.
    if scene_data.get("contains_external_references") is not False:
        raise PermissionError("External USD scene references are not allowed")
    if not scene_data.get("native_schema_version"):
        raise RuntimeError("High-fidelity mode needs an authored native USD Camera")
    up_axis=str(UsdGeom.GetStageUpAxis(stage))
    if up_axis not in ("Y","Z"):
        raise RuntimeError("Unexpected native USD scene up-axis")
    cameras=[]
    lights=[]
    geometry=[]
    missing_actors=[]
    skinned_meshes=[]
    for root,role in sorted(roles.items()):
        if role not in VALID_ROLES:
            raise RuntimeError("Unexpected source role during geometry composition")
        prim=stage.GetPrimAtPath(root)
        if not prim or not prim.IsDefined():
            raise RuntimeError("FilmIndex prim missing from frozen composed scene")
        if not _visible(prim,UsdGeom,timecode):
            continue
        if role=="camera":
            if not prim.IsA(UsdGeom.Camera):
                raise RuntimeError("Native authored camera must use UsdGeom.Camera")
            camera=UsdGeom.Camera(prim)
            projection=str(camera.GetProjectionAttr().Get(timecode))
            if projection!="perspective":
                raise RuntimeError("Only native perspective USD camera currently supported")
            lens=_bounded_number(camera.GetFocalLengthAttr().Get(timecode))
            aperture=_bounded_number(camera.GetHorizontalApertureAttr().Get(timecode))
            if lens<=0 or aperture<=0:
                raise RuntimeError("Invalid USD native camera optics")
            cameras.append({
                "path":root,"matrix":_matrix(
                    UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(timecode)),
                "focal_length_mm":lens*MM_PER_CAMERA_UNIT,
                "sensor_width_mm":aperture*MM_PER_CAMERA_UNIT,
                "f_stop":_bounded_number(
                    camera.GetFStopAttr().Get(timecode)),
                "focus_distance_m":_bounded_number(
                    camera.GetFocusDistanceAttr().Get(timecode)),
                "projection":"perspective",
            })
            continue
        if role=="light":
            if not prim.IsA(UsdLux.SphereLight):
                raise RuntimeError("Unsupported non-sphere native light type")
            light=UsdLux.SphereLight(prim)
            api=UsdLux.LightAPI(prim)
            intensity=_bounded_number(api.GetIntensityAttr().Get(timecode))
            radius=_bounded_number(light.GetRadiusAttr().Get(timecode))
            if not 0<=intensity<=1_000_000 or not 0<=radius<=1000:
                raise RuntimeError("Source light outside bounded preview limits")
            raw=api.GetColorAttr().Get(timecode)
            color=[_bounded_number(x,1) for x in raw] if raw is not None else [1.,1.,1.]
            lights.append({
                "path":root,
                "matrix":_matrix(
                    UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(timecode)),
                "intensity":intensity,"radius":radius,
                "color":color,"usd_photometric_parity":False,
            })
            continue
        authored=False
        # Traverse only children belonging to THIS source role. Geometry
        # from the SHA-pinned reusable asset appears under /Geometry.
        for child in Usd.PrimRange(prim):
            if not child.IsDefined() or not _visible(child,UsdGeom,timecode):
                continue
            if not (child.IsA(UsdGeom.Cube) or
                    child.IsA(UsdGeom.Sphere) or
                    child.IsA(UsdGeom.Mesh)):
                continue
            authored=True
            geo=_mesh(child,UsdGeom,timecode)
            if child.IsA(UsdGeom.Mesh):
                from pxr import UsdSkel
                if child.HasAPI(UsdSkel.BindingAPI):
                    if role!="actor":
                        raise RuntimeError("Only an actor source can bind native skeletal skin")
                    from backend.nvp_openusd_skinning import evaluate_skin
                    posed=evaluate_skin(stage,child,root,source_tick)
                    if len(posed["deformed_points"])!=len(geo["points"]):
                        raise RuntimeError("Native posed actor vertex count changed")
                    geo["points"]=posed["deformed_points"]
                    geo["skinning_mode"]="native_UsdSkel_linear_blend"
                    skinned_meshes.append(posed["source_mesh_path"])
            geometry.append({
                "path":str(child.GetPath()),"source_role":role,
                "world_matrix":_matrix(
                    UsdGeom.Xformable(child).ComputeLocalToWorldTransform(timecode)),
                "geometry":geo,
                "display_color":_get_display_color(child,UsdGeom,timecode),
                "material_model":"USD_displayColor_only",
            })
            if len(geometry)>MAX_OBJECTS:
                raise RuntimeError("Visible source geometry exceeds bounded scene budget")
        if role=="actor" and not authored:
            missing_actors.append(root)
    if camera_path is not None:
        candidates=[x for x in cameras if x["path"]==camera_path]
        if not candidates:
            raise ValueError("Selected camera path is not an active source camera")
    else:
        candidates=cameras
        if len(candidates)!=1:
            raise ValueError("Multiple/missing native cameras; director must choose a camera")
    chosen=candidates[0]
    if not geometry:
        raise RuntimeError("No actual authored geometry exists; use SLATE-05 proxy")
    rig_count=len(scene_data.get("skeleton_rigs",[]))
    summary={
        "format":FORMAT,
        "source_take_sha256":source_take_sha,
        "source_shot_sha256":source_shot_sha,
        "source_tick":source_tick,
        "cache_key":cache_key,
        "camera":chosen,"lights":lights,"objects":geometry,
        "up_axis":up_axis,
        "unmeshed_actors":missing_actors,
        "skeletal_rig_count":rig_count,
        "skinned_mesh_paths":sorted(skinned_meshes),
        "skinning_evaluated":bool(skinned_meshes),
        "facial_animation_evaluated":False,
        "usd_material_networks_evaluated":False,
        "usd_light_photometry_exact":False,
        "source_data_modified":False,"final_presentation_approved":False,
    }
    if len(canonical(summary))>MAX_SOURCE_BYTES-256:
        raise RuntimeError("Native source geometry recipe would exceed bounded worker input")
    return summary

def recipe(snapshot,quality):
    if type(snapshot) is not dict or snapshot.get("format")!=FORMAT:
        raise ValueError("Unsupported source-geometry presentation recipe")
    if quality not in DIMENSIONS:
        raise ValueError("Unknown higher-fidelity preview resolution")
    return {
        **snapshot,"quality":quality,
        "width":DIMENSIONS[quality][0],"height":DIMENSIONS[quality][1],
        "renderer_version":RENDERER_VERSION,
        "worker_script_sha256":sha(BLENDER_SCRIPT.encode("utf8")),
    }


# A fixed, first-party Blender script. It does NOT open an external USD file,
# import arbitrary user scripts, run network calls, or touch original sources.
# The worker pins this exact string and bounded JSON before admission.
BLENDER_SCRIPT=r'''
import bpy, json, math, os, sys
from mathutils import Matrix,Vector

args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
def required(name):
    if name not in args: raise RuntimeError("Missing sealed NVP argument")
    pos=args.index(name)+1
    if pos>=len(args): raise RuntimeError("Incomplete sealed preview argument")
    value=args[pos]
    # Only the host supervisor can supply these exact absolute paths after
    # source/output verification. Blender's cwd is the sealed job directory.
    # A crafted path, foreign source, renamed output or traversal is denied.
    expected={"--manifest":"slate_source_preview.json",
              "--preview":"preview.png"}.get(name)
    if (expected is None or not os.path.isabs(value) or
        os.path.normcase(os.path.normpath(value))!=
            os.path.normcase(os.path.join(os.getcwd(),expected))):
        raise RuntimeError("Untrusted preview output path")
    return expected
manifest=required("--manifest");output=required("--preview")
with open(os.path.join(os.getcwd(),manifest),"r",encoding="utf8") as handle:
    src=json.load(handle)
if src.get("format")!="nvp.slate.native_openusd_scene_presentation.v1":
    raise RuntimeError("Wrong NVP authored geometry presentation format")
if not 1<=len(src["objects"])<=48:
    raise RuntimeError("Invalid source mesh count")
if not src["width"] in (320,640,960) or not src["height"] in (180,360,540):
    raise RuntimeError("Unbounded or unmatched preview dimensions")
if src["up_axis"]=="Y":
    # USD stage world is Y-up: convert to Blender Z-up for this
    # temporary derivative render, never the immutable USD source.
    convert=Matrix(((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1)))
elif src["up_axis"]=="Z":
    convert=Matrix.Identity(4)
else: raise RuntimeError("Unknown stage up axis")
def matrix(rows):
    if len(rows)!=4 or any(len(row)!=4 for row in rows):
        raise RuntimeError("Invalid native USD source transform")
    values=[float(v) for row in rows for v in row]
    if not all(math.isfinite(v) and abs(v)<=1000000 for v in values):
        raise RuntimeError("Non-finite source transform")
    return convert @ Matrix(rows)
def material(color,name):
    if len(color)!=3: raise RuntimeError("Source displayColor must be RGB")
    rgb=[float(x) for x in color]
    if not all(math.isfinite(x) and 0<=x<=1 for x in rgb):
        raise RuntimeError("Source USD color outside [0,1]")
    mat=bpy.data.materials.new(name)
    mat.diffuse_color=tuple(rgb)+(1.0,)
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf: bsdf.inputs["Base Color"].default_value=tuple(rgb)+(1.0,)
    return mat

bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.engine="CYCLES"
scene.cycles.device="CPU"
scene.cycles.samples=int({"thumbnail":8,"interactive":16,
                          "inspection":24}[src["quality"]])
scene.render.resolution_x=src["width"]
scene.render.resolution_y=src["height"]
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.render.image_settings.color_mode="RGB"
scene.render.film_transparent=False
world=bpy.data.worlds.new("NVP_ReadOnly_Derivative_World")
world.use_nodes=True
world.node_tree.nodes.get("Background").inputs["Color"].default_value=(0.12,0.12,0.12,1)
world.node_tree.nodes.get("Background").inputs["Strength"].default_value=0.8
scene.world=world

for idx,item in enumerate(src["objects"]):
    g=item["geometry"]
    kind=g["kind"]
    if kind=="cube":
        bpy.ops.mesh.primitive_cube_add(size=float(g["size"]))
        obj=bpy.context.object
    elif kind=="sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,
            radius=float(g["radius"]))
        obj=bpy.context.object
    elif kind=="mesh":
        points=g["points"];faces=g["triangles"]
        if len(points)>1200 or len(faces)>2500:
            raise RuntimeError("Oversize USD source mesh")
        mesh=bpy.data.meshes.new("NVP_SourceMesh_"+str(idx))
        mesh.from_pydata(points,[],faces);mesh.update()
        obj=bpy.data.objects.new("NVP_SourceMesh_"+str(idx),mesh)
        scene.collection.objects.link(obj)
    else: raise RuntimeError("Unknown authored source geometry")
    obj.name="NVP_SourceGeometry_"+str(idx)
    obj.matrix_world=matrix(item["world_matrix"])
    obj.data.materials.append(material(
        item["display_color"],"NVP_DisplayColor_"+str(idx)))

for idx,item in enumerate(src["lights"]):
    data=bpy.data.lights.new("NVP_USD_Light_"+str(idx),type="POINT")
    # USD light intensity units do not equal Blender watts; this is an
    # explicit direct-light PREVIEW approximation, not photometric parity.
    data.energy=max(0.0,min(5000.0,float(item["intensity"])))
    data.shadow_soft_size=max(0.01,min(100.0,float(item["radius"])))
    data.color=tuple(float(x) for x in item["color"])
    obj=bpy.data.objects.new(data.name,data)
    scene.collection.objects.link(obj)
    obj.matrix_world=matrix(item["matrix"])

camera=src["camera"]
data=bpy.data.cameras.new("NVP_Authored_USD_Camera")
data.type="PERSP"
data.lens=float(camera["focal_length_mm"])
data.sensor_width=float(camera["sensor_width_mm"])
data.sensor_fit="HORIZONTAL"
f_stop=float(camera.get("f_stop",0))
focus=float(camera.get("focus_distance_m",0))
if f_stop>0 and focus>0:
    data.dof.use_dof=True
    data.dof.aperture_fstop=f_stop
    data.dof.focus_distance=focus
obj=bpy.data.objects.new("NVP_Authored_USD_Camera",data)
scene.collection.objects.link(obj)
obj.matrix_world=matrix(camera["matrix"])
scene.camera=obj
scene.render.filepath=os.path.join(os.getcwd(),output)
bpy.ops.render.render(write_still=True)
if not os.path.isfile(scene.render.filepath):
    raise RuntimeError("Higher-fidelity OpenUSD derivative PNG not generated")
'''
