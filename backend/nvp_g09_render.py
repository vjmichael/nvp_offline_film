"""G09-A approved source-driven material/lighting environment renderer.

An improved bounded native CPU look-pass with actual shaded geometry,
director-authored physical material parameters, scene lights, set pieces,
LOD/culling and atmospheric depth. It is NOT marketed as a path-traced
Cycles/MaterialX final master. For production-quality photorealism G09
must admit a protected genuine Blender/Hydra/OCIO worker separately.

No generated picture is stored as a new original and no full-frame
raster index replaces authoritative OpenUSD time or source PCM.
"""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
import math

from PIL import Image,ImageDraw
from backend.nvp_g08_native_avi import (
    WIDTH,HEIGHT,MESH,_active,_basis,_project,_dot,_normalized,_cross,
    _grade,DEFAULT_BACKGROUND)
from backend.nvp_g09_environment import _json,_sha
from backend.nvp_g09_production_usd import _kelvin_rgb

PI=math.pi
MAX_DISTANCE=240.
MAX_POLYGONS=32000


def _rgb(s):
    return tuple(int(s[i:i+2],16)/255. for i in (1,3,5))


def _srgb_to_linear(v):
    return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4


def _linear_to_srgb(v):
    v=max(0.,v)
    return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055


def _clamp(v):
    return max(0.,min(1.,v))


def _vec(p):
    return tuple(float(x) for x in p)


def _sub(a,b):
    return tuple(a[i]-b[i] for i in range(3))


def _mul(a,n):
    return tuple(v*n for v in a)


def _add(a,b):
    return tuple(a[i]+b[i] for i in range(3))


def _brdf(surface,normal,view,light,light_color,power,fill):
    """One-bounce metallic-roughness microfacet (GGX/Schlick/Smith).

    Uses per-face normals, not full texture-level PBR or global illumination.
    MaterialX/UsdPreviewSurface values in the derived USD layer are the
    portable authoring truth; this is their deterministic software preview.
    """
    n=_normalized(normal);v=_normalized(view);l=_normalized(light)
    if not n or not v or not l:return (0.,0.,0.)
    nvl=max(0.,_dot(n,l));nv=max(.0001,_dot(n,v))
    if nvl<.0001:nvl=.0001
    halfway=_normalized(_add(l,v))
    if not halfway:return (0.,0.,0.)
    nh=max(0.,_dot(n,halfway));vh=max(0.,_dot(v,halfway))
    metal=surface["metallic"];rough=surface["roughness"]
    base=tuple(_srgb_to_linear(x) for x in _rgb(surface["color"]))
    a=max(.03,rough)**2
    a2=a*a
    denom=max(.0001,nh*nh*(a2-1.)+1.)
    distribution=a2/(PI*denom*denom)
    k=(rough+1.)**2/8.
    smith=(nv/(nv*(1-k)+k))*(nvl/(nvl*(1-k)+k))
    f0=tuple(.04*(1-metal)+base[i]*metal for i in range(3))
    fresnel=tuple(f0[i]+(1-f0[i])*(1-vh)**5 for i in range(3))
    spec=tuple(distribution*smith*fresnel[i]/max(.001,4*nv*nvl)
               for i in range(3))
    diffuse=tuple((1-fresnel[i])*(1-metal)*base[i]/PI for i in range(3))
    return tuple(
        (diffuse[i]+spec[i])*power*nvl*light_color[i]+
        base[i]*fill*.15+
        base[i]*surface["emission"]*.1
        for i in range(3))


def _tone_map(l):
    return _clamp(_linear_to_srgb(l/(1+l)))


def _default_material(color):
    return {"color":color,"roughness":.75,"metallic":0.,"emission":0.,"kind":"stone"}


def _rotate_local(v,rot):
    # Director-controlled XYZ degrees; geometry transform is derived, not
    # written over any object in a frozen Take.
    x,y,z=v;rx,ry,rz=(math.radians(a) for a in rot)
    y,z=y*math.cos(rx)-z*math.sin(rx),y*math.sin(rx)+z*math.cos(rx)
    x,z=x*math.cos(ry)+z*math.sin(ry),-x*math.sin(ry)+z*math.cos(ry)
    x,y=x*math.cos(rz)-y*math.sin(rz),x*math.sin(rz)+y*math.cos(rz)
    return (x,y,z)


def _set_world(item):
    points,faces=MESH[item["shape"]]
    p=item["position"];s=item["scale"];rot=item["rotation"]
    pts=[tuple(p[i]+_rotate_local(tuple(v[j]*s[j] for j in range(3)),rot)[i]
               for i in range(3)) for v in points]
    return pts,faces


def _key_light(look):
    sun=look["sun"]
    az=math.radians(sun["azimuth"])
    elevation=math.radians(sun["elevation"])
    light=(math.cos(elevation)*math.cos(az),
           math.cos(elevation)*math.sin(az),
           math.sin(elevation))
    return light,_kelvin_rgb(sun["temperature"])


def _fog_color(rgb,distance,atmosphere):
    density=atmosphere["density"]
    blend=1-math.exp(-density*distance)
    fog=_rgb(atmosphere["color"])
    return tuple(round(rgb[i]*(1-blend)*255+fog[i]*blend*255) for i in range(3))


def _background(look):
    sky=_rgb(look["sky"]);ground=_rgb(look["ground"])
    background=Image.new("RGB",(WIDTH,HEIGHT),look["sky"])
    draw=ImageDraw.Draw(background)
    # Light-scattering gradient is a derived proxy and never called an
    # independent HDR environment texture or physical atmosphere simulation.
    bands=30
    for i in range(bands):
        k=i/(bands-1)
        value=tuple(round(255*_clamp(sky[c]*(.68+.35*k)))
                    for c in range(3))
        y0=round(i*HEIGHT/bands)
        y1=round((i+1)*HEIGHT/bands)
        draw.rectangle((0,y0,WIDTH,y1),fill=value)
    draw.rectangle((0,round(HEIGHT*.79),WIDTH,HEIGHT),fill=tuple(
        round(x*255*.8) for x in ground))
    return background


def _actor_proxy_faces(out,world,original,actor,evaluator,tick,basis,light,
                       light_color,power,fill,fog):
    """Actual articulated human proxy, not the G05 cylinder stand-in.

    Joint positions/pose are shared with the native derived USD skeleton.
    Hair/wardrobe have stable ActorID-specific material decisions. Facial
    movement is waveform-driven mouth motion, not phoneme recognition.
    """
    from pxr import Usd,UsdGeom,Gf
    root=world.stage.GetPrimAtPath("/World/Objects/"+original["id"])
    if not root:
        raise RuntimeError("The original ActorID geometry is absent")
    transform=UsdGeom.Xformable(root).ComputeLocalToWorldTransform(
        Usd.TimeCode(float(tick)))
    positions,pose=evaluator.sample(actor["actor_id"],tick)
    z=actor["height_scale"];shoulder=actor["shoulder_width"]
    standard={
      "Torso":("cylinder",(.27*shoulder,.26*shoulder,.77*z),"wardrobe_color",0),
      "Head":("sphere",(.29*z,.29*z,.29*z),"skin_color",0),
      "LeftArm":("cylinder",(.10*shoulder,.10*shoulder,.50*z),"wardrobe_color",6),
      "RightArm":("cylinder",(.10*shoulder,.10*shoulder,.50*z),"wardrobe_color",8),
      "LeftLeg":("cylinder",(.12*shoulder,.12*shoulder,.58*z),"wardrobe_color",10),
      "RightLeg":("cylinder",(.12*shoulder,.12*shoulder,.58*z),"wardrobe_color",12),
      "LeftHand":("sphere",(.11,.11,.11),"skin_color",0),
      "RightHand":("sphere",(.11,.11,.11),"skin_color",0),
      "Jaw":("sphere",(.16,.14,.085*(1+pose["jaw"]*1.5)),"skin_color",5),
      "LeftEye":("sphere",(.06,.06,.06*(1-pose["blink"]*.9)),"eye_color",0),
      "RightEye":("sphere",(.06,.06,.06*(1-pose["blink"]*.9)),"eye_color",0)}
    if actor["hair"]!="bald":
        height={"short":.19,"medium":.25,"long":.38}[actor["hair"]]
        standard["Hair"]=("sphere",(.31,.31,height),"hair_color",0)
    focal=world._camera_focal
    for name,(shape,scale,color_key,joint_index) in standard.items():
        center=positions.get(name)
        if center is None:continue
        angle=pose["rotations"][joint_index][0]
        vertices,polygons=MESH[shape]
        world_points=[]
        for vertex in vertices:
            p=tuple(vertex[i]*scale[i] for i in range(3))
            p=_rotate_local(p,(math.degrees(angle),0.,0.))
            p=tuple(p[i]+center[i] for i in range(3))
            world_points.append(transform.Transform(Gf.Vec3d(*p)))
        material=_default_material(actor[color_key])
        # Human skin and original clothing have separate reflectance
        # even before a protected Blender/Cycles renderer is admitted.
        material["kind"]="fabric" if color_key=="wardrobe_color" else "plaster"
        material["roughness"]=.85 if color_key=="wardrobe_color" else .55
        distance=math.dist(tuple(transform.Transform(Gf.Vec3d(*center))),
                           tuple(basis[0]))
        _append_faces(out,world_points,polygons,material,basis,
                      focal,light,light_color,power,fill,fog,distance,0)


def _one_shot(seg,world,tick,approved):
    look=approved["look"]
    if (approved["sha256"]!=_sha(_json(look).encode("utf8")) or
        look["take_sha256"]!=seg["take_sha256"]):
        raise RuntimeError("The selected production style no longer matches its Take")
    basis=_basis(seg["camera"]);camera=basis[0]
    image=_background(look)
    draw=ImageDraw.Draw(image)
    light,light_color=_key_light(look)
    sun_power=look["sun"]["intensity"]
    fill=look["sun"]["fill"]
    faces=[]
    from pxr import Usd,UsdGeom,Gf
    clock=Usd.TimeCode(float(tick))
    performance=getattr(world,"actor_frame_evaluator",None)
    source_by_id={x["id"]:x for x in world.record["stage_objects"]}
    world._camera_focal=seg["camera"]["focal_mm"]
    for item,prim in world.objects:
        if performance and item["actor_id"] in performance.cast:
            _actor_proxy_faces(
                faces,world,item,performance.cast[item["actor_id"]],
                performance,tick,basis,light,light_color,
                sun_power,fill,look["atmosphere"])
            continue
        if item["shape"] not in MESH:continue
        mat=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(clock)
        center=mat.ExtractTranslation()
        dist=math.dist(tuple(center),tuple(camera))
        if dist>MAX_DISTANCE:continue
        vertices,polygons=MESH[item["shape"]]
        points=[mat.Transform(Gf.Vec3d(*vertex)) for vertex in vertices]
        material=look["materials"].get(item["id"],
                                      _default_material(item["color"]))
        _append_faces(faces,points,polygons,material,basis,
                      seg["camera"]["focal_mm"],light,light_color,
                      sun_power,fill,look["atmosphere"],
                      dist,0)
    for item in look["set_pieces"]:
        dist=math.dist(item["position"],camera)
        if dist>MAX_DISTANCE:continue
        points,polygons=_set_world(item)
        _append_faces(faces,points,polygons,item["material"],basis,
                      seg["camera"]["focal_mm"],light,light_color,
                      sun_power,fill,look["atmosphere"],
                      dist,item["lod"])
    if len(faces)>MAX_POLYGONS:
        raise ValueError("The environment exceeds current picture complexity")
    faces.sort(key=lambda x:x[0],reverse=True)
    for depth,polygon,color in faces:
        draw.polygon(polygon,fill=color)
    return _grade(image,seg["grade"])


def _append_faces(out,points,polygons,surface,basis,focal,light,
                  light_color,power,fill,fog,distance,lod):
    if lod>=1 and distance>100:return
    if lod>=2 and distance>55:return
    projected=[_project(p,basis,focal,WIDTH,HEIGHT) for p in points]
    if not any(p is not None and -.25*WIDTH<p[0]<1.25*WIDTH and
               -.25*HEIGHT<p[1]<1.25*HEIGHT for p in projected):
        return
    count=len(polygons)
    stride=(3 if distance>80 and count>50 else 1)
    stride=(max(stride,2) if lod>=1 and count>40 else stride)
    for k in range(0,count,stride):
        face=polygons[k]
        xy=[projected[i] for i in face]
        if any(p is None for p in xy):continue
        xs=[p[0] for p in xy];ys=[p[1] for p in xy]
        if max(xs)<-1 or min(xs)>WIDTH+1 or max(ys)<-1 or min(ys)>HEIGHT+1:
            continue
        if (max(xs)-min(xs)<.45 and max(ys)-min(ys)<.45):continue
        v=[tuple(points[i]) for i in face]
        normal=_cross(_sub(v[1],v[0]),_sub(v[2],v[0]))
        center=tuple(sum(x[i] for x in v)/len(v) for i in range(3))
        view=_sub(basis[0],center)
        lit=_brdf(surface,normal,view,light,light_color,power,fill)
        rgb=tuple(_tone_map(x) for x in lit)
        color=_fog_color(rgb,distance,fog)
        out.append((sum(p[2] for p in xy)/len(xy),
                   [(p[0],p[1]) for p in xy],color))


def render_production_picture(assembly,worlds,tick):
    """Render approved G09 looks while keeping source time authoritative.

    If a Take has no approved G09 style, reuse the exact G08 picture path
    for that shot. Mixed styled/unstyled dissolves use correct two-source
    linear weights. The first output is still a 640×360 working AVI.
    """
    from backend.nvp_g08_native_avi import render_picture
    entries=_active(assembly["segments"],tick)
    if not entries:raise RuntimeError("No picture exists at the selected Film Time")
    image=None
    approved_map=assembly.get("production_looks",{})
    actor_map=assembly.get("actor_performances",{})
    for seg,weight in entries:
        src_tick=seg["source_in_tick"]+tick-seg["start_tick"]
        if not seg["source_in_tick"]<=src_tick<seg["source_out_tick"]:
            raise RuntimeError("An edit tried to leave the original Take")
        world=worlds[seg["take_id"]]
        approved=approved_map.get(seg["take_id"])
        if approved is None and seg["take_id"] in actor_map:
            # Actors can be directed independently of set dressing. A
            # neutral built-in look is a render default, NOT an invented
            # director-approved environment revision.
            from backend.nvp_g09_environment import _default
            from backend.nvp_g09_environment import _json,_sha
            fallback=_default(seg["take_id"],seg["take_sha256"],
                              world.record)
            approved={"revision":0,
                      "sha256":_sha(_json(fallback).encode("utf8")),
                      "look":fallback}
        if approved is None:
            # Build a one-shot self-contained subset instead of asking the
            # original G08 renderer to re-evaluate a whole dissolve.
            single={"segments":[{**seg,"start_tick":0,"end_tick":
                        seg["source_out_tick"]-seg["source_in_tick"],
                        "transition":{"kind":"cut","duration_tick":0}}],
                    "original_takes":assembly["original_takes"]}
            raw=render_picture(single,worlds,
                               tick=src_tick-seg["source_in_tick"])
            with Image.open(BytesIO(raw)) as decoded:
                part=decoded.convert("RGB")
        else:
            part=_one_shot(seg,world,src_tick,approved)
        if image is None:image=part
        else:image=Image.blend(image,part,max(0.,min(1.,weight)))
    output=BytesIO()
    image.save(output,format="JPEG",quality=84,
               subsampling=1,optimize=False)
    return output.getvalue()
