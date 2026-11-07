"""DA-03B/C: source-space orientation and source-verified geometric occlusion.

This first original-scene acoustic model respects the listener's USD
rotation and SHA-verified, on-demand primitive geometry. Sphere/cube
bounding volumes offer only coarse broadband obstruction; full wave
propagation, frequency-selective absorption, HRTF, reflection and room
simulation remain explicitly unimplemented.
"""
from __future__ import annotations

import math

from backend.nvp_data_av_visual import visual_state

FORMAT="nvp.native_spatial.acoustics_v1"


def _xyz(v):
    if (not isinstance(v,(list,tuple)) or len(v)!=3 or
            any(type(x) not in (int,float) or not math.isfinite(x) for x in v)):
        raise ValueError("Invalid original USD position")
    return tuple(float(x) for x in v)


def _right(matrix):
    if (not isinstance(matrix,list) or len(matrix)!=4 or
            any(not isinstance(row,list) or len(row)!=4 for row in matrix)):
        raise ValueError("Invalid authored USD listener basis")
    direction=_xyz(matrix[0][:3])
    size=math.sqrt(sum(x*x for x in direction))
    if size<1e-9:raise ValueError("Degenerate native listener orientation")
    return tuple(x/size for x in direction)


def right_axis(listener_matrix):
    """Reusable source-local right direction from the original USD matrix."""
    return _right(listener_matrix)


def spatial_gains(emitter,listener,listener_matrix,gain,obstruction=1.0):
    """Equal-power stereo panning in the listener's *local* right axis."""
    emitter=_xyz(emitter)
    listener=_xyz(listener)
    if (type(gain) not in (int,float) or not math.isfinite(gain) or
            not 0<=gain<=2 or
            type(obstruction) not in (int,float) or
            not math.isfinite(obstruction) or not 0<=obstruction<=1):
        raise ValueError("Untrusted native acoustic gain")
    vec=tuple(e-l for e,l in zip(emitter,listener))
    distance=math.sqrt(sum(x*x for x in vec))
    if (isinstance(listener_matrix,(tuple,list)) and
            len(listener_matrix)==3):
        direction=_xyz(listener_matrix)
        length=math.sqrt(sum(v*v for v in direction))
        if length<1e-9:raise ValueError("Degenerate USD local-right axis")
        right=tuple(v/length for v in direction)
    else:
        right=_right(listener_matrix)
    # Local orientation, not global world X. No Doppler or HRTF claim.
    balance=max(-1.,min(1.,sum(v*r for v,r in zip(vec,right))/
                               max(distance,1.0)))
    atten=1.0/(1.0+max(0.0,distance-1.0))
    level=atten*float(gain)*float(obstruction)
    return (level*math.sqrt((1.0-balance)*0.5),
            level*math.sqrt((1.0+balance)*0.5))


# Native local-to-world coordinates obey USD Gf.Matrix4d's ROW convention.
# Exactly the same authored transform is used by the picture/world reader.
_CUBE_CORNERS=tuple((x,y,z) for z in (-1.,1.)
    for y in (-1.,1.) for x in (-1.,1.))
_CUBE_TRIANGLES=(
    (0,1,3),(0,3,2), (4,6,7),(4,7,5),
    (0,4,5),(0,5,1), (2,3,7),(2,7,6),
    (0,2,6),(0,6,4), (1,5,7),(1,7,3),
)
MAX_OCCLUDER_TRIANGLES=4096


def _world(matrix,point):
    if (type(matrix) is not list or len(matrix)!=4 or
            any(type(row) is not list or len(row)!=4 for row in matrix)):
        raise RuntimeError("Missing original USD obstruction transform")
    x,y,z=_xyz(point)
    w=x*matrix[0][3]+y*matrix[1][3]+z*matrix[2][3]+matrix[3][3]
    if not math.isfinite(w) or abs(w)<1e-9:
        raise RuntimeError("Untrusted USD obstruction homogeneous transform")
    result=tuple(
        (x*matrix[0][i]+y*matrix[1][i]+z*matrix[2][i]+matrix[3][i])/w
        for i in range(3))
    return _xyz(result)


def _triangle_hit(a,d,points):
    # Two-sided segment/triangle Moller-Trumbore. Unit segment parameter
    # t excludes the emitter/listener endpoints to avoid self-occlusion.
    v0,v1,v2=points
    e1=tuple(y-x for x,y in zip(v0,v1))
    e2=tuple(y-x for x,y in zip(v0,v2))
    cross=lambda p,q:(p[1]*q[2]-p[2]*q[1],
                      p[2]*q[0]-p[0]*q[2],
                      p[0]*q[1]-p[1]*q[0])
    dot=lambda p,q:sum(x*y for x,y in zip(p,q))
    h=cross(d,e2)
    det=dot(e1,h)
    if abs(det)<1e-10:return False
    s=tuple(x-y for x,y in zip(a,v0))
    u=dot(s,h)/det
    if u<0 or u>1:return False
    q=cross(s,e1)
    v=dot(d,q)/det
    if v<0 or u+v>1:return False
    t=dot(e2,q)/det
    return 1e-7<t<1.-1e-7


def _sphere_hits_segment(a,b,center,radius):
    d=tuple(y-x for x,y in zip(a,b))
    d2=sum(x*x for x in d)
    if d2<1e-9:return False
    t=max(0.,min(1.,sum((c-x)*v for c,x,v in
                       zip(center,a,d))/d2))
    nearest=tuple(x+t*v for x,v in zip(a,d))
    return sum((p-q)**2 for p,q in zip(center,nearest))<radius*radius


def verified_occluders(index,project_id,snapshot):
    """Use exact original USD mesh/cube faces; approximate spheres only.

    This is ray-based broadband geometry blocking, NOT HRTF, spectral
    absorption, diffraction or a room impulse-response simulator.
    """
    candidates=[obj for obj in snapshot["objects"]
                if obj["semantic_role"] in ("prop","environment")
                and obj.get("asset") is not None]
    if not candidates:return []
    if len(candidates)>64:
        raise ValueError("Too many source solids for bounded native acoustics")
    shown=visual_state(index,project_id,{**snapshot,"objects":candidates})
    results=[]
    total_triangles=0
    for obj in shown["objects"]:
        if obj["gizmo_only"] or obj["semantic_role"] not in (
                "prop","environment"):
            continue
        shape=obj["shape"]
        if shape not in ("cube","sphere","mesh"):
            raise RuntimeError("Unsupported frozen sound occluder topology")
        center=_xyz(obj["world_translation"])
        base={
            "path":obj["path"],"center":center,
            "asset_sha256":obj["geometry_asset_sha256"],
            "source_geometry_exact":shape in ("cube","mesh"),
        }
        if shape=="sphere":
            # Bounding the transformed original sphere is conservative for
            # authored nonuniform scaling; it is not a spectral material.
            matrix=obj["world_matrix"]
            extent=obj["size_m"]*.5
            radius=max(math.dist(center,_world(matrix,p))
                for p in ((extent,0.,0.),(0.,extent,0.),(0.,0.,extent)))
            base["radius"]=radius
        else:
            if shape=="cube":
                half=obj["size_m"]*.5
                pts=[(x*half,y*half,z*half) for x,y,z in _CUBE_CORNERS]
                triangles=_CUBE_TRIANGLES
            else:
                pts=obj["mesh_points"]
                triangles=obj["mesh_triangles"]
            total_triangles+=len(triangles)
            if total_triangles>MAX_OCCLUDER_TRIANGLES:
                raise RuntimeError("Real-time native occluder triangle budget exceeded")
            transformed=[_world(obj["world_matrix"],p) for p in pts]
            base["radius"]=max(math.dist(center,p) for p in transformed)
            base["triangles"]=tuple(tuple(transformed[i] for i in face)
                                    for face in triangles)
        if not math.isfinite(base["radius"]) or base["radius"]<=0:
            raise RuntimeError("Invalid source geometry obstruction bounds")
        results.append(base)
    return results

def obstruction_gain(emitter,listener,obstacles,*,source_path,listener_path):
    """Conservative, bounded approximate solid obstruction gain.

    This is a broadband visual-geometry proxy, not physics-based sound
    occlusion. An exact geometry ray tracer or Steam Audio/HRTF backend
    must replace it before claiming professional spatial acoustics.
    """
    a=_xyz(emitter)
    b=_xyz(listener)
    delta=tuple(v-u for u,v in zip(a,b))
    length2=sum(x*x for x in delta)
    if length2<1e-9:return 1.0
    gain=1.0
    for ob in obstacles:
        if ob["path"] in (source_path,listener_path):
            continue
        center=_xyz(ob["center"])
        r=ob["radius"]
        if type(r) not in (int,float) or not math.isfinite(r) or not 0<r<=100000:
            raise ValueError("Unbounded native obstruction geometry")
        if not _sphere_hits_segment(a,b,center,r):
            continue
        triangles=ob.get("triangles")
        if triangles is not None:
            if (not isinstance(triangles,(list,tuple)) or
                len(triangles)>MAX_OCCLUDER_TRIANGLES):
                raise RuntimeError("Untrusted native obstruction triangle count")
            blocked=any(_triangle_hit(a,delta,face) for face in triangles)
        else:
            # Native authored sphere and compatibility-only coarse inputs.
            blocked=True
        if blocked:
            gain*=0.65  # Bounded conservative level, not measured material.
    return max(0.1,gain)
