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


def _surface(obj):
    """Read actual authored USD material. Defaults are labeled uncalibrated."""
    mat=obj.get("source_material")
    if mat is None:
        if obj["shape"]=="skinned_mesh":
            raise RuntimeError("Skinned source actor has no verified material")
        return DEFAULT_MATERIAL,.8,.05,True
    if (type(mat) is not dict or
        mat.get("original_source_modified") is not False or
        mat.get("format") not in (
            "nvp.original_usd_preview_surface.v1",
            "nvp.original_usd_displaycolor_preview.v1")):
        raise RuntimeError("Original USD surface was not SHA-bound")
    color=_array3(mat.get("base_color_rgb"))
    r=mat.get("roughness")
    m=mat.get("metallic")
    if (any(not 0<=x<=1 for x in color) or
        type(r) not in (int,float) or type(m) not in (int,float) or
        not math.isfinite(r) or not math.isfinite(m) or
        not 0<=r<=1 or not 0<=m<=1):
        raise RuntimeError("USD material shader parameters invalid")
    return color,float(r),float(m),False


def _dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def _unit(v):
    length=math.sqrt(_dot(v,v))
    if length<1e-12:return None
    return tuple(x/length for x in v)


def _shade(points,surface,lights,eye,virtual_lights=()):
    """Deterministic scalar GGX/Smith/Schlick source-preview shading.

    The untextured path deliberately uses Python scalars; per-texel maps
    are handled separately by _shade_texture_texels with NumPy arrays.
    """
    color,roughness,metallic,_=surface
    a,b,c=points
    u=tuple(b[i]-a[i] for i in range(3))
    v=tuple(c[i]-a[i] for i in range(3))
    n=_unit((u[1]*v[2]-u[2]*v[1],
             u[2]*v[0]-u[0]*v[2],
             u[0]*v[1]-u[1]*v[0]))
    if n is None:return None
    center=tuple((a[i]+b[i]+c[i])/3. for i in range(3))
    view=_unit(tuple(eye[i]-center[i] for i in range(3)))
    if view is None:return None
    if _dot(n,view)<0:n=tuple(-x for x in n)
    nv=max(0.,_dot(n,view))
    out=[AMBIENT_REVIEW*value*(1.-metallic) for value in color]
    f0=[.04*(1.-metallic)+metallic*x for x in color]
    alpha=max(.04,roughness*roughness)
    alpha2=alpha*alpha
    k=(roughness+1.)**2/8.
    ggx_view=nv/(nv*(1.-k)+k+1e-8)
    for light_position,intensity in lights:
        d=tuple(light_position[i]-center[i] for i in range(3))
        dsq=_dot(d,d)
        light=_unit(d)
        if light is None:continue
        nl=max(0.,_dot(n,light))
        if nl<=0 or nv<=0:continue
        h=_unit(tuple(light[i]+view[i] for i in range(3)))
        if h is None:continue
        nh=max(0.,_dot(n,h))
        vh=max(0.,_dot(view,h))
        denom=nh*nh*(alpha2-1.)+1.
        distribution=alpha2/(math.pi*denom*denom+1e-8)
        ggx_light=nl/(nl*(1.-k)+k+1e-8)
        geometry=ggx_view*ggx_light
        fresnel=[f+(1.-f)*(1.-vh)**5 for f in f0]
        strength=intensity/LIGHT_REFERENCE/(1.+dsq)
        for channel in range(3):
            diffuse=color[channel]*(1.-metallic)*(
                1.-fresnel[channel])/math.pi
            specular=(distribution*geometry*fresnel[channel]/
                      max(1e-6,4.*nv*nl))
            out[channel]+=strength*nl*(diffuse+specular)
    # Digital film cheats: direct per-object RGB fill with no reflector or
    # path-traced indirect light. Physical USD shading above is unchanged.
    for rgb,gain,direction in virtual_lights:
        facing=(max(0.,_dot(n,direction))
                if direction is not None else 1.)
        for channel in range(3):
            out[channel]+=color[channel]*(1.-metallic)*rgb[channel]*gain*facing
    if any(not math.isfinite(x) or x<0 for x in out):
        raise RuntimeError("Source USD microfacet preview produced invalid light")
    return tuple(out)


def _shade_texture_texels(points,surface,lights,eye,sampled_rgb,np,*,
                          roughness_texels=None,metallic_texels=None,
                          emission_texels=None,normal_texels=None,
                          uv_face=None,virtual_lights=()):
    """Evaluate bounded GGX/Schlick with the actual per-pixel source color.

    Avoid applying the sRGB base map to the *completed lighting result*:
    that incorrectly tints dielectric specular. This remains a source-only,
    face-normal preview, NOT a physically calibrated Hydra renderer.
    """
    tint,roughness,metallic,_=surface
    color=np.asarray(sampled_rgb,dtype=np.float64)*np.asarray(
        tint,dtype=np.float64)
    # Authored PBR image channels override the scalar fallback. This matches
    # UsdPreviewSurface, MaterialX and the WebGL material (factor 1 for maps).
    if roughness_texels is not None:
        roughness=np.clip(roughness_texels,.04,1.)
    if metallic_texels is not None:
        metallic=np.clip(metallic_texels,0.,1.)
    a,b,c=points
    u=tuple(b[i]-a[i] for i in range(3))
    v=tuple(c[i]-a[i] for i in range(3))
    n=_unit((u[1]*v[2]-u[2]*v[1],
             u[2]*v[0]-u[0]*v[2],
             u[0]*v[1]-u[1]*v[0]))
    center=tuple((a[i]+b[i]+c[i])/3 for i in range(3))
    view=_unit(tuple(eye[i]-center[i] for i in range(3)))
    if n is None or view is None:
        raise RuntimeError("Degenerate USD source texture triangle")
    if _dot(n,view)<0:n=tuple(-x for x in n)
    normal=np.asarray(n,dtype=np.float64)
    if normal_texels is not None:
        if uv_face is None or len(uv_face)!=3:
            raise RuntimeError("Normal map requires original USD face-corner st")
        dp1=np.asarray(u,dtype=np.float64)
        dp2=np.asarray(v,dtype=np.float64)
        uv0,uv1,uv2=(np.asarray(x,dtype=np.float64) for x in uv_face)
        du1,dv1=uv1-uv0
        du2,dv2=uv2-uv0
        determinant=du1*dv2-dv1*du2
        if abs(determinant)<1e-8:
            raise RuntimeError("Normal map has degenerate original UV tangent basis")
        tangent=(dp1*dv2-dp2*dv1)/determinant
        tangent=tangent-normal*np.dot(normal,tangent)
        length=np.linalg.norm(tangent)
        if length<1e-8:
            raise RuntimeError("Invalid source texture tangent")
        tangent=tangent/length
        bitangent=np.cross(normal,tangent)*(
            1. if determinant>=0 else -1.)
        tangent_rgb=2.*np.asarray(normal_texels,dtype=np.float64)-1.
        normal=(tangent_rgb[...,0,None]*tangent+
                tangent_rgb[...,1,None]*bitangent+
                tangent_rgb[...,2,None]*normal)
        normal=normal/np.maximum(
            np.linalg.norm(normal,axis=-1,keepdims=True),1e-8)
    nv=np.maximum(0.,np.sum(normal*np.asarray(view),axis=-1))
    metal=np.asarray(metallic,dtype=np.float64)
    out=AMBIENT_REVIEW*color*(1.-metal[...,None])
    f0=.04*(1.-metal[...,None])+metal[...,None]*color
    alpha=np.maximum(.04,roughness*roughness)
    alpha2=alpha*alpha
    k=(roughness+1.)**2/8.
    ggx_view=nv/(nv*(1.-k)+k+1e-8)
    for light_position,intensity in lights:
        d=tuple(light_position[i]-center[i] for i in range(3))
        dsq=_dot(d,d)
        light=_unit(d)
        if light is None:continue
        nl=np.maximum(0.,np.sum(normal*np.asarray(light),axis=-1))
        if not np.any(nl>0) or not np.any(nv>0):continue
        h=_unit(tuple(light[i]+view[i] for i in range(3)))
        if h is None:continue
        nh=np.maximum(0.,np.sum(normal*np.asarray(h),axis=-1))
        vh=max(0.,_dot(view,h))
        denom=nh*nh*(alpha2-1.)+1.
        distribution=alpha2/(math.pi*denom*denom+1e-8)
        ggx_light=nl/(nl*(1.-k)+k+1e-8)
        geometry=ggx_view*ggx_light
        fresnel=f0+(1.-f0)*(1.-vh)**5
        strength=intensity/LIGHT_REFERENCE/(1.+dsq)
        diffuse=color*(1.-metal[...,None])*(1.-fresnel)/math.pi
        specular=((distribution*geometry)[...,None]*fresnel/
                  np.maximum(1e-6,4.*nv*nl)[...,None])
        out=out+strength*nl[...,None]*(diffuse+specular)
    if emission_texels is not None:
        out=out+np.asarray(emission_texels,dtype=np.float64)
    for rgb,gain,direction in virtual_lights:
        tint=np.asarray(rgb,dtype=np.float64)
        if direction is None:
            out=out+color*(1.-metal[...,None])*tint*gain
        else:
            incidence=np.maximum(
                0.,np.sum(normal*np.asarray(direction),axis=-1))
            out=out+color*(1.-metal[...,None])*tint*gain*incidence[...,None]
    if not np.all(np.isfinite(out)) or np.any(out<0):
        raise RuntimeError("Invalid source USD textured microfacet shading")
    return out.astype(np.float32)


def _draw_triangle(buffer,depth,tri,world_points,surface,lights,eye,np,
                   texture=None,uv_face=None,pbr_maps=None,
                   virtual_lights=()):
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
    shade=_shade(world_points,surface,lights,eye,virtual_lights)
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
    out=buffer[lo_y:hi_y+1,lo_x:hi_x+1,:3]
    if texture is None and not pbr_maps:
        crop[visible]=zz[visible]
        out[visible]=shade
    else:
        if uv_face is None or len(uv_face)!=3:
            raise RuntimeError("Frozen source mesh texture is missing UVs")
        inv_safe=np.where(inv>0,inv,1.)
        u=sum(w*uv[0]/z for w,uv,z in (
            (w0,uv_face[0],z0),(w1,uv_face[1],z1),
            (w2,uv_face[2],z2)))/inv_safe
        v=sum(w*uv[1]/z for w,uv,z in (
            (w0,uv_face[0],z0),(w1,uv_face[1],z1),
            (w2,uv_face[2],z2)))/inv_safe
        def sample_map(image):
            height,width=image.shape[:2]
            xx=np.floor(np.mod(u,1.)*width).astype(np.int64)
            yy=(height-1)-np.floor(np.mod(v,1.)*height).astype(np.int64)
            return image[yy,xx,:3]
        sample=(sample_map(texture) if texture is not None
                else np.ones((*u.shape,3),dtype=np.float32))
        maps=pbr_maps or {}
        decoded={key:sample_map(img) for key,img in maps.items()}
        if "opacity" in decoded:
            visible=visible&(decoded["opacity"][...,0]>=.5)
            if not np.any(visible):return False
        crop[visible]=zz[visible]
        # Per-pixel sRGB-linear texel enters source base reflectance before
        # GGX/Schlick lighting. The HDR light/spectral model remains preview.
        lit=_shade_texture_texels(
            world_points,surface,lights,eye,sample,np,
            roughness_texels=(decoded["roughness"][...,0]
                              if "roughness" in decoded else None),
            metallic_texels=(decoded["metallic"][...,0]
                             if "metallic" in decoded else None),
            emission_texels=decoded.get("emission"),
            normal_texels=decoded.get("normal"),
            uv_face=uv_face,
            virtual_lights=virtual_lights)
        out[visible]=lit[visible]
    return True


class NativeSceneLinearRaster:
    """Produce ephemeral float32 RGB from the SHA-verified source at one tick."""

    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Trusted original FilmIndex required")
        self.index=index

    def render(self,project_id,take_id,take_sha256,*,tick,camera_path,
               source_session=None,source_snapshot=None,
               virtual_fx=None):
        _require_pid(project_id);_id(take_id,"original USD Take");_sha(take_sha256)
        _int(tick,"original scene Film Time")
        if type(camera_path) is not str or not camera_path.startswith("/World/"):
            raise ValueError("A source-authored USD camera is required")
        import numpy as np
        owns_session=source_session is None
        if owns_session:
            if source_snapshot is not None:
                raise PermissionError("External pixel snapshots cannot authorize ACES color")
            source=FrozenSceneAV(
                self.index,project_id,take_id,
                expected_take_sha256=take_sha256,listener_path=camera_path)
        else:
            source=source_session
            if (not isinstance(source,FrozenSceneAV) or
                source.index is not self.index or
                source.project_id!=project_id or
                source.take_id!=take_id or
                source.take["document_sha256"]!=take_sha256 or
                source.roles.get(camera_path)!="camera" or
                not isinstance(source_snapshot,dict)):
                raise PermissionError("Only trusted native Take session may reuse USD frame")
        try:
            if tick>=source.duration:
                raise ValueError("Color review tick is outside frozen Take")
            if owns_session:
                snapshot=source.snapshot(tick)
            else:
                source._current_take()
                snapshot=source_snapshot
                if (snapshot.get("time_tick")!=tick or
                    type(snapshot.get("snapshot_sha256")) is not str or
                    len(snapshot["snapshot_sha256"])!=64):
                    raise RuntimeError("Trusted scene-linear Film Time state is stale")
            original=source.data
            if (snapshot["scene_document_sha256"]!=original["scene_document_sha256"] or
                snapshot["timeline_document_sha256"]!=original["timeline_document_sha256"]):
                raise RuntimeError("Native source Film Time state changed")
            visual=visual_state(
                self.index,project_id,snapshot,
                scene_id=original["scene_id"],
                scene_revision=original["scene_revision"],
                include_texture_transport=False)
            view,focal=_camera(snapshot,camera_path)
            eye=next(_array3(o["world_translation"])
                     for o in snapshot["objects"] if o["path"]==camera_path)
            lights=_lights(snapshot)
            fxmap={}
            virtual_proof={
                "fx_source_sha256":None,"effect_count":0,
                "real_scene_pixel_shader_consumes_fx":False,
                "artist_approved_final_lighting":False,
            }
            if virtual_fx is not None:
                from backend.nvp_virtual_light_raster_adapter import (
                    evaluate_scene_virtual_lighting)
                targets=[
                    obj["path"] for obj in visual["objects"]
                    if obj["semantic_role"] not in ("light","camera") and
                       obj["shape"] not in ("gizmo","missing_rig_geometry")]
                fxmap,virtual_proof=evaluate_scene_virtual_lighting(
                    virtual_fx,targets,tick)
            color=np.zeros((HEIGHT,WIDTH,4),dtype=np.float32)
            color[:,:,3]=1.
            depth=np.full((HEIGHT,WIDTH),np.inf,dtype=np.float32)
            polygons=0
            rasterized=0
            default_materials=0
            actor_shapes=0
            textured_triangles=0
            texture_cache={}
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
                surface=_surface(obj)
                face_surfaces={}
                for slot in obj.get("source_material_slots") or []:
                    slot_color=_array3(slot["base_color_rgb"])
                    for face_number in slot["faces"]:
                        if face_number in face_surfaces:
                            raise RuntimeError("USD surface subset face overlap")
                        face_surfaces[face_number]=(
                            slot_color,float(slot["roughness"]),
                            float(slot["metallic"]),False)
                texture=None
                uvs=obj.get("mesh_uvs")
                face_uvs=obj.get("mesh_face_uvs")
                descriptor=(obj.get("source_material") or {}).get("texture")
                if descriptor is not None:
                    if (obj["shape"] not in ("mesh","skinned_mesh") or
                        (uvs is None and face_uvs is None) or
                        (uvs is not None and face_uvs is not None) or
                        (uvs is not None and len(uvs)!=len(raw)) or
                        (face_uvs is not None and len(face_uvs)!=len(faces))):
                        raise RuntimeError("USD texture requires original UV authority")
                    if (face_uvs is not None and any(
                        type(row) is not list or len(row)!=3
                        for row in face_uvs)):
                        raise RuntimeError("Malformed original face UV corners")
                    from backend.nvp_native_usd_texture import verified_texture
                    key=descriptor["sha256"]
                    if key not in texture_cache:
                        w,h,rgba=verified_texture(
                            self.index,project_id,descriptor)[1]
                        srgb=np.frombuffer(rgba,dtype=np.uint8).reshape(
                            h,w,4)[:,:,:3].astype(np.float32)/255.
                        texture_cache[key]=np.where(
                            srgb<=.04045,srgb/12.92,
                            ((srgb+.055)/1.055)**2.4).astype(np.float32)
                    texture=texture_cache[key]
                source_maps=(obj.get("source_material") or {}).get("pbr_maps") or {}
                material_maps={}
                if source_maps:
                    if ((uvs is None and face_uvs is None) or
                        (uvs is not None and len(uvs)!=len(raw)) or
                        (face_uvs is not None and len(face_uvs)!=len(faces))):
                        raise RuntimeError("PBR channel maps require real original UVs")
                    from backend.nvp_native_usd_texture import verified_texture
                    for channel,descriptor in source_maps.items():
                        key=descriptor["sha256"]
                        cache_key=("pbr",channel,key)
                        if cache_key not in texture_cache:
                            w,h,rgba=verified_texture(
                                self.index,project_id,descriptor)[1]
                            pixels=np.frombuffer(rgba,dtype=np.uint8).reshape(
                                h,w,4)[:,:,:3].astype(np.float32)/255.
                            texture_cache[cache_key]=(
                                np.where(pixels<=.04045,pixels/12.92,
                                    ((pixels+.055)/1.055)**2.4).astype(np.float32)
                                if channel=="emission" else pixels)
                        material_maps[channel]=texture_cache[cache_key]
                default_materials+=int(surface[3])
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
                for face_index,face in enumerate(faces):
                    verts=[projected[i] for i in face]
                    if any(v is None for v in verts):continue
                    original_points=[transformed[i] for i in face]
                    if _draw_triangle(
                        color,depth,verts,original_points,
                        face_surfaces.get(face_index,surface),
                        lights,eye,np,
                        texture=(texture if face_index not in face_surfaces
                                 else None),
                        uv_face=(face_uvs[face_index] if face_uvs is not None
                                 else [uvs[i] for i in face]
                                 if texture is not None or material_maps else None),
                        pbr_maps=(material_maps if
                                  face_index not in face_surfaces else None),
                         virtual_lights=fxmap.get(obj["path"],())):
                        rasterized+=1
                        textured_triangles+=int(
                            texture is not None and face_index not in face_surfaces)
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
                "source_uv_texture_rasterized_triangles":textured_triangles,
                "texture_shading_matches_hydra":False,
                "actual_usd_skinned_actors":actor_shapes,
                "original_usd_sphere_lights":len(lights),
                "neutral_default_material_count":default_materials,
                "usd_roughness_metallic_microfacet_evaluated":True,
                "ggx_microfacet_preview_calibrated":False,
                "source_working_space":"Linear Rec.709 (sRGB)",
                "source_color_appearance_calibrated":False,
                "actual_usd_light_spectrum_calibrated":False,
                "virtual_artistic_fx_applied_to_real_pixels":(
                    virtual_proof["real_scene_pixel_shader_consumes_fx"]),
                "virtual_artistic_fx_count":virtual_proof["effect_count"],
                "virtual_artistic_fx_source_sha256":virtual_proof["fx_source_sha256"],
                "virtual_fx_not_photometric_or_path_traced":True,
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
            if owns_session:
                source.close()
