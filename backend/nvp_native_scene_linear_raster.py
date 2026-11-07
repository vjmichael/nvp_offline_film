"""DA-06D: source-authored OpenUSD -> bounded native FLOAT32 scene-linear review.

This is a first-party rasterizer and an honest *uncalibrated* working-space
preview, not a Hydra renderer, material-texture shader, light-transport
simulator, photometrically calibrated HDR camera or cinema master.

Source authority: only a verified frozen original Digital Take, exact Film
Time, composed native USD camera and verified USD asset/Skel geometry.
All output is ephemeral FLOAT32 RGBA from independently depth-tested
triangles. No source frame, Blender, external renderer, FFmpeg or asset path
can enter this pipeline. Source color is treated as linear Rec.709 preview
working RGB, NOT a verified camera/scene-color characterization.
"""
from __future__ import annotations

from hashlib import sha256
import math

from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_data_av_visual import visual_state
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_native_cpu_raster import _apply,_inverse,_cube_vertices
from backend.nvp_temporal_ledger import _int

FORMAT="nvp.data_first.usd_scene_linear_float32.v1"
WIDTH=640
HEIGHT=360
MAX_TRIANGLES=8192
NEAR=0.05
DEFAULT_MATERIAL=(0.45,0.45,0.45)
LIGHT_REFERENCE=100.0
AMBIENT_REVIEW=0.035

CUBE_FACES=(
    (0,1,2),(0,2,3),(4,7,6),(4,6,5),
    (0,4,5),(0,5,1),(1,5,6),(1,6,2),
    (2,6,7),(2,7,3),(3,7,4),(3,4,0),
)


def _sphere():
    # Derived surface tessellation only from original USD Sphere radius.
    points=[]
    for latitude in range(13):
        theta=math.pi*latitude/12
        for longitude in range(25):
            phi=2*math.pi*longitude/24
            points.append((
                .5*math.sin(theta)*math.cos(phi),
                .5*math.cos(theta),
                .5*math.sin(theta)*math.sin(phi)))
    triangles=[]
    for i in range(12):
        for j in range(24):
            a=i*25+j;b=a+25
            if i>0:triangles.append((a,b,a+1))
            if i<11:triangles.append((a+1,b,b+1))
    return points,triangles


SPHERE_POINTS,SPHERE_FACES=_sphere()


def _array3(values):
    if (not isinstance(values,(tuple,list)) or len(values)!=3 or
            any(type(v) not in (int,float) or
                not math.isfinite(v) for v in values)):
        raise RuntimeError("Unbounded original USD point/color source")
    return tuple(float(v) for v in values)


def _triangles(obj):
    shape=obj["shape"]
    if shape=="cube":
        return [tuple(v*obj["size_m"] for v in p)
                for p in _cube_vertices(1.)],CUBE_FACES
    if shape=="sphere":
        return [tuple(v*obj["size_m"] for v in p)
                for p in SPHERE_POINTS],SPHERE_FACES
    if shape in ("mesh","skinned_mesh"):
        points=obj["mesh_points"]
        faces=obj["mesh_triangles"]
        if (type(points) is not list or type(faces) is not list or
                not 3<=len(points)<=2048 or
                not 1<=len(faces)<=4096 or
                any(type(f) is not list or len(f)!=3 or
                    len(set(f))!=3 or
                    any(type(i) is not int or i<0 or i>=len(points)
                        for i in f) for f in faces)):
            raise RuntimeError("Original USD mesh topology cannot be projected")
        return [_array3(p) for p in points],faces
    raise RuntimeError("No original surface mesh available for source color")


def _camera(snapshot,camera_path):
    cameras={o["path"]:o for o in snapshot["objects"]
             if o["semantic_role"]=="camera"}
    if camera_path not in cameras:
        raise RuntimeError("Only the original composed USD scene camera is allowed")
    native=[
        x for x in snapshot.get("native_scene_schemas",[])
        if x["prim_path"]==camera_path and x["schema"]=="UsdGeom.Camera"]
    if len(native)!=1 or native[0].get("projection") not in (
            "perspective",):
        raise RuntimeError("Real native perspective UsdGeom.Camera required")
    f=native[0]["focal_length_mm"]
    if type(f) not in (int,float) or not math.isfinite(f) or not 1<=f<=400:
        raise RuntimeError("Untrusted source lens focal length")
    return _inverse(cameras[camera_path]["world_matrix"]),float(f)


def _lights(snapshot):
    schema={
        item["prim_path"]:item
        for item in snapshot.get("native_scene_schemas",[])
        if item["schema"]=="UsdLux.SphereLight"
    }
    light=[]
    for obj in snapshot["objects"]:
        if obj["semantic_role"]!="light":continue
        entry=schema.get(obj["path"])
        if entry is None:
            raise RuntimeError("Source scene light lacks real native USD schema")
        intensity=entry["intensity"]
        if (type(intensity) not in (int,float) or
            not math.isfinite(intensity) or not 0<=intensity<=100000):
            raise RuntimeError("Untrusted original USD light power")
        # The actual USD color temperature is exposed as metadata, but
        # applying a blackbody spectral conversion without calibration
        # would invent source spectral data. Use neutral intensity only.
        light.append((_array3(obj["world_translation"]),float(intensity)))
    if len(light)>16:
        raise RuntimeError("Bounded native original lights exceeded")
    return light


def _base_color(obj):
    if obj["shape"]=="skinned_mesh":
        mat=obj.get("source_material")
        if (type(mat) is not dict or
            mat.get("original_source_modified") is not False or
            mat.get("format") not in (
                "nvp.original_usd_preview_surface.v1",
                "nvp.original_usd_displaycolor_preview.v1")):
            raise RuntimeError("Actor material must come from original USD")
        color=_array3(mat["base_color_rgb"])
        if any(not 0<=v<=1 for v in color):
            raise RuntimeError("Unbounded original USD surface reflectance")
        return color,False
    return DEFAULT_MATERIAL,True


def _shade(points,color,lights):
    a,b,c=points
    u=[b[i]-a[i] for i in range(3)]
    v=[c[i]-a[i] for i in range(3)]
    n=(u[1]*v[2]-u[2]*v[1],
       u[2]*v[0]-u[0]*v[2],
       u[0]*v[1]-u[1]*v[0])
    length=math.sqrt(sum(x*x for x in n))
    if length<1e-9:return None
    n=tuple(x/length for x in n)
    center=tuple((a[i]+b[i]+c[i])/3. for i in range(3))
    value=AMBIENT_REVIEW
    for loc,intensity in lights:
        vector=[loc[i]-center[i] for i in range(3)]
        dist2=sum(x*x for x in vector)
        if dist2<=1e-9:continue
        # Two-sided original USD geometry is not a Lambert backface:
        # this bounded neutral preview is not photometric simulation.
        value+=intensity/LIGHT_REFERENCE*max(
            0.,abs(sum(n[i]*vector[i] for i in range(3)))/math.sqrt(dist2)
        )/(1.+dist2)
    return tuple(x*value for x in color)


def _paint(zbuf,pixels,world,view,tri,color,np):
    vertices=[]
    for point in world:
        x,y,z=_apply(view,point)
        if not all(math.isfinite(v) for v in (x,y,z)) or z>=-NEAR:
            return False  # No fake near-plane geometry.
        vertices.append((WIDTH/2 + x*(50./36.)*WIDTH/(-z),
                         HEIGHT/2-y*(50./36.)*WIDTH/(-z),-z))
    # Use the actual focal length from the camera as projection input:
    # triangle clipping and Z evaluation are independent of that source.
    raise RuntimeError("Internal projection must supply original camera focal")


def _draw_triangle(buffer,depth,tri,world_points,color,lights,np):
    a,b,c=tri
    x0,y0,z0=a;x1,y1,z1=b;x2,y2,z2=c
    if (not all(math.isfinite(v) for v in (
            x0,y0,z0,x1,y1,z1,x2,y2,z2)) or
            min(z0,z1,z2)<=NEAR):
        return False
    lo_x=max(0,int(math.floor(min(x0,x1,x2))))
    hi_x=min(WIDTH-1,int(math.ceil(max(x0,x1,x2))))
    lo_y=max(0,int(math.floor(min(y0,y1,y2))))
    hi_y=min(HEIGHT-1,int(math.ceil(max(y0,y1,y2))))
    if lo_x>hi_x or lo_y>hi_y:return False
    denom=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
    if abs(denom)<1e-8:return False
    shade=_shade(world_points,color,lights)
    if shade is None:return False
    xs=np.arange(lo_x,hi_x+1,dtype=np.float64)+.5
    ys=np.arange(lo_y,hi_y+1,dtype=np.float64)+.5
    gx,gy=np.meshgrid(xs,ys)
    w0=((y1-y2)*(gx-x2)+(x2-x1)*(gy-y2))/denom
    w1=((y2-y0)*(gx-x2)+(x0-x2)*(gy-y2))/denom
    w2=1-w0-w1
    inside=(w0>=-1e-9)&(w1>=-1e-9)&(w2>=-1e-9)
    inv=w0/z0+w1/z1+w2/z2
    zz=np.divide(1.,inv,out=np.full_like(inv,np.inf),where=inv>0)
    crop=depth[lo_y:hi_y+1,lo_x:hi_x+1]
    visible=inside&(zz<crop)
    if not np.any(visible):return False
    crop[visible]=zz[visible]
    out=buffer[lo_y:hi_y+1,lo_x:hi_x+1,:3]
    out[visible]=shade
    return True


class NativeSceneLinearRaster:
    """Produce ephemeral float32 RGB from the SHA-verified source at one tick."""

    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Trusted original FilmIndex required")
        self.index=index

    def render(self,project_id,take_id,take_sha256,*,tick,camera_path):
        _require_pid(project_id);_id(take_id,"original USD Take");_sha(take_sha256)
        _int(tick,"original scene Film Time")
        if type(camera_path) is not str or not camera_path.startswith("/World/"):
            raise ValueError("A source-authored USD camera is required")
        import numpy as np
        source=FrozenSceneAV(
            self.index,project_id,take_id,
            expected_take_sha256=take_sha256,listener_path=camera_path)
        try:
            if tick>=source.duration:
                raise ValueError("Color review tick is outside frozen Take")
            snapshot=source.snapshot(tick)
            original=source.data
            if (snapshot["scene_document_sha256"]!=original["scene_document_sha256"] or
                snapshot["timeline_document_sha256"]!=original["timeline_document_sha256"]):
                raise RuntimeError("Native source Film Time state changed")
            visual=visual_state(
                self.index,project_id,snapshot,
                scene_id=original["scene_id"],
                scene_revision=original["scene_revision"])
            view,focal=_camera(snapshot,camera_path)
            lights=_lights(snapshot)
            color=np.zeros((HEIGHT,WIDTH,4),dtype=np.float32)
            color[:,:,3]=1.
            depth=np.full((HEIGHT,WIDTH),np.inf,dtype=np.float32)
            polygons=0
            rasterized=0
            default_materials=0
            actor_shapes=0
            for obj in visual["objects"]:
                if obj["semantic_role"] in ("light","camera"):continue
                if obj["shape"] in ("gizmo","missing_rig_geometry"):
                    if obj["semantic_role"]=="actor":
                        raise RuntimeError(
                            "Original captured actor has no real USD surface")
                    continue
                raw,faces=_triangles(obj)
                polygons+=len(faces)
                if polygons>MAX_TRIANGLES:
                    raise RuntimeError("Source-authoritative color triangle budget exceeded")
                source_color,default=_base_color(obj)
                default_materials+=int(default)
                actor_shapes+=int(obj["shape"]=="skinned_mesh")
                transformed=[_array3(_apply(obj["world_matrix"],p)) for p in raw]
                projected=[]
                for p in transformed:
                    x,y,z=_apply(view,p)
                    if not all(math.isfinite(v) for v in (x,y,z)) or z>=-NEAR:
                        projected.append(None)
                    else:
                        factor=(focal/36.0)*WIDTH/(-z)
                        projected.append((WIDTH*.5+x*factor,
                                          HEIGHT*.5-y*factor,-z))
                for face in faces:
                    verts=[projected[i] for i in face]
                    if any(v is None for v in verts):continue
                    original_points=[transformed[i] for i in face]
                    if _draw_triangle(
                        color,depth,verts,original_points,
                        source_color,lights,np):
                        rasterized+=1
            receipt={
                "format":FORMAT,"time_tick":str(tick),
                "original_take_sha256":take_sha256,
                "scene_document_sha256":snapshot["scene_document_sha256"],
                "timeline_document_sha256":snapshot["timeline_document_sha256"],
                "scene_snapshot_sha256":snapshot["snapshot_sha256"],
                "scene_linear_rgba_sha256":sha256(color.tobytes()).hexdigest(),
                "width":WIDTH,"height":HEIGHT,
                "source_geometry_triangles":polygons,
                "rasterized_triangles":rasterized,
                "actual_usd_skinned_actors":actor_shapes,
                "original_usd_sphere_lights":len(lights),
                "neutral_default_material_count":default_materials,
                "source_working_space":"Linear Rec.709 (sRGB)",
                "source_color_appearance_calibrated":False,
                "actual_usd_light_spectrum_calibrated":False,
                "unclipped_linear_float_output":True,
                "source_modified":False,
                "ffmpeg_used":False,
                "master_approved":False,
            }
            if self.index.read_revision(
                    project_id,take_id,1)["document_sha256"]!=take_sha256:
                raise RuntimeError("Original Digital Take changed during projection")
            return color,receipt
        finally:
            source.close()
