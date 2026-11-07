"""DA-03B: verifiable source-space orientation and coarse obstruction.

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


def verified_occluders(index,project_id,snapshot):
    """Read only real bound source assets, never actor position gizmos."""
    candidates=[obj for obj in snapshot["objects"]
                if obj["semantic_role"] in ("prop","environment")
                and obj.get("asset") is not None]
    if not candidates:return []
    if len(candidates)>64:
        raise ValueError("Too many source geometry solids for bounded acoustics")
    shown=visual_state(index,project_id,{**snapshot,"objects":candidates})
    return [{
        "path":obj["path"],
        "center":_xyz(obj["world_translation"]),
        "radius":obj["size_m"]*(0.5 if obj["shape"]=="sphere" else
                                 math.sqrt(3)/2),
        "asset_sha256":obj["geometry_asset_sha256"],
        "approximate_bounding_volume":obj["shape"]=="cube",
    } for obj in shown["objects"]
      if (not obj["gizmo_only"] and
          obj["semantic_role"] in ("prop","environment") and
          obj["shape"] in ("cube","sphere"))]


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
        if type(r) not in (int,float) or not 0<r<=100000:
            raise ValueError("Unbounded native obstruction geometry")
        t=sum((c-u)*v for c,u,v in zip(center,a,delta))/length2
        # Only solid geometry actually BETWEEN listener and emitter.
        if not 0<t<1:continue
        closest=tuple(u+t*v for u,v in zip(a,delta))
        if sum((c-q)**2 for c,q in zip(center,closest))<r*r:
            gain*=0.65
    return max(0.1,gain)
