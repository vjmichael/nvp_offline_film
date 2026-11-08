"""FILM01-DONUT: source-authoritative OpenUSD torus MESH, not a fake sprite.

Any object may be a film actor. A donut actor is genuinely a torus:
its hole exposes scene background, its curved ring presents many
surface-normal orientations and its USD roughness/metallic parameters
test real image shading and artistic virtual fill. Native asset registry
stores its immutable triangle/face-varying UV source in OpenUSD.

Procedural design generator only: a creator or CI must explicitly
publish the resulting mesh as a frozen FilmIndex USD asset.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

FORMAT="nvp.film01.original_donut_torus_mesh.v1"
MIN_MAJOR_SEGMENTS=16
MAX_MAJOR_SEGMENTS=64
MIN_MINOR_SEGMENTS=8
MAX_MINOR_SEGMENTS=24
MAX_POINTS=2048
MAX_TRIANGLES=4096


def original_donut_mesh(*,major_radius=0.95,minor_radius=0.32,
                        major_segments=36,minor_segments=14):
    """Deterministic XY-ring torus around the Z axis with real central hole.

    Each pair of U,V angular coordinates yields a genuine USD triangle
    surface, not a painted circular texture, screen-space annulus or an
    assumed GI light bounce. Its normals will be approximated by actual
    triangle faces in the present first-party preview renderer.
    """
    if (type(major_segments) is not int or
            type(minor_segments) is not int or
            not MIN_MAJOR_SEGMENTS<=major_segments<=MAX_MAJOR_SEGMENTS or
            not MIN_MINOR_SEGMENTS<=minor_segments<=MAX_MINOR_SEGMENTS):
        raise ValueError("Donut mesh needs bounded integer angular topology")
    if (type(major_radius) not in (int,float) or
            type(minor_radius) not in (int,float) or
            not math.isfinite(major_radius) or
            not math.isfinite(minor_radius) or
            not 0.1<=minor_radius<major_radius<=3 or
            major_radius-minor_radius<0.2):
        raise ValueError("Donut must have a visible nonzero hole and finite radii")
    if (major_segments*minor_segments>MAX_POINTS or
            2*major_segments*minor_segments>MAX_TRIANGLES):
        raise ValueError("Original donut USD mesh exceeds source triangle budget")
    points=[]
    for i in range(major_segments):
        a=math.tau*i/major_segments
        ca,sa=math.cos(a),math.sin(a)
        for j in range(minor_segments):
            b=math.tau*j/minor_segments
            radial=major_radius+minor_radius*math.cos(b)
            points.append([
                round(radial*ca,9),
                round(radial*sa,9),
                round(minor_radius*math.sin(b),9)])
    triangles=[]
    face_uvs=[]
    for i in range(major_segments):
        for j in range(minor_segments):
            a=i*minor_segments+j
            b=((i+1)%major_segments)*minor_segments+j
            c=i*minor_segments+(j+1)%minor_segments
            d=((i+1)%major_segments)*minor_segments+(j+1)%minor_segments
            # Outward winding du x dv, checked in independent source test.
            triangles.extend([[a,b,c],[b,d,c]])
            u0=i/major_segments
            u1=(i+1)/major_segments
            v0=j/minor_segments
            v1=(j+1)/minor_segments
            face_uvs.extend([
                [[u0,v0],[u1,v0],[u0,v1]],
                [[u1,v0],[u1,v1],[u0,v1]]])
    if (len(points)!=major_segments*minor_segments or
            len(triangles)!=2*len(points) or
            len(face_uvs)!=len(triangles)):
        raise RuntimeError("True original torus geometry construction failed")
    # A useful source-only geometric invariant: every ring vertex is
    # outside the inner radius, and neither projection nor shading
    # needs to invent a filled center.
    inner=major_radius-minor_radius
    distances=[math.hypot(p[0],p[1]) for p in points]
    if min(distances)<inner-1e-7:
        raise RuntimeError("Original donut surface filled the center hole")
    obj={
        "format":FORMAT,
        "major_radius":float(major_radius),
        "minor_radius":float(minor_radius),
        "major_segments":major_segments,
        "minor_segments":minor_segments,
        "hole_radius":round(inner,9),
        "outer_radius":round(major_radius+minor_radius,9),
        "mesh_points":points,
        "mesh_triangles":triangles,
        "mesh_face_uvs":face_uvs,
        "real_source_mesh_not_screen_overlay":True,
        "rigging_and_deformation_not_yet_present":True,
        "physically_calibrated_shading_not_proven":True,
    }
    obj["mesh_sha256"]=sha256(json.dumps(
        {"points":points,"faces":triangles,"uvs":face_uvs},
        sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return obj
