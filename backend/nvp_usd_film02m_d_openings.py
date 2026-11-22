"""USD-FILM-02M-D: geometry-first façade apertures and true room interiors.

A window/door is an actual void in USD mesh topology, not an alpha map
or an absent camera-facing polygon. The same deterministic source mesh
is visible from front, rear and inside. Procedural bays/story choices
yield immutable source-asset revisions; old film world Takes remain frozen.

All source authoring uses first-party OpenUSDAssetRegistry. The director
must separately authorize the exact original module SHA through 02M-A.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_openusd_assets import (
    OpenUSDAssetRegistry,MAX_MESH_VERTICES,MAX_MESH_TRIANGLES)

FORMAT="nvp.usd_film02m.openings_and_room_source.v1"
MAX_OPENINGS=24
MAX_STORIES=4
MAX_BAYS=6
MIN_WEB=.12


def _number(x,label):
    if type(x) not in (int,float) or not math.isfinite(x):
        raise ValueError("Finite original geometry "+label+" required")
    return float(x)


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode("ascii")).hexdigest()


def _box_shell_mesh(blocks):
    """Real triangle faces, never 2D cardboard. Dedup same point locations."""
    points=[]
    triangles=[]
    lookup={}
    def vertex(p):
        pos=tuple(round(float(x),6) for x in p)
        if pos not in lookup:
            lookup[pos]=len(points)
            points.append(list(pos))
        return lookup[pos]
    def quad(a,b,c,d):
        ids=[vertex(v) for v in (a,b,c,d)]
        triangles.extend(([ids[0],ids[1],ids[2]],
                          [ids[0],ids[2],ids[3]]))
    for x0,x1,y0,y1,z0,z1 in blocks:
        if x1<=x0 or y1<=y0 or z1<=z0:
            raise ValueError("Original room shell needs 3D thickness")
        quad((x0,y0,z0),(x0,y1,z0),(x1,y1,z0),(x1,y0,z0))
        quad((x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1))
        quad((x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1))
        quad((x1,y1,z0),(x0,y1,z0),(x0,y1,z1),(x1,y1,z1))
        quad((x0,y1,z0),(x0,y0,z0),(x0,y0,z1),(x0,y1,z1))
        quad((x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1))
    return points,triangles


def _validate_openings(width,height,openings):
    if type(openings) is not list or not 1<=len(openings)<=MAX_OPENINGS:
        raise ValueError("Bounded actual architectural openings required")
    result=[]
    left=-width/2
    bottom=-height/2
    for opening in openings:
        if type(opening) is not dict or set(opening)!={
                "kind","x_center_m","bottom_m","width_m","height_m"}:
            raise ValueError("Original doorway/window geometry has typed dimensions")
        kind=opening["kind"]
        if kind not in ("door","window","storefront"):
            raise ValueError("Only true building entrance, window or storefront openings")
        x=_number(opening["x_center_m"],"aperture x")
        z=_number(opening["bottom_m"],"aperture bottom")
        w=_number(opening["width_m"],"aperture width")
        h=_number(opening["height_m"],"aperture height")
        if w<.5 or h<.5:
            raise ValueError("Aperture must be usable scaled geometry")
        x0,x1=x-w/2,x+w/2
        z0,z1=z,z+h
        if (x0<left+MIN_WEB or x1>width/2-MIN_WEB or
            z1>height/2-MIN_WEB or
            z0<bottom-1e-6):
            raise ValueError("Opening breaks the surrounding structural wall web")
        if kind=="door":
            if abs(z0-bottom)>1e-6 or not 1.8<=h<=3.5:
                raise ValueError("Door must open onto the actual floor edge")
        elif z0<bottom+MIN_WEB:
            raise ValueError("Windows need a real sill, not a fake doorway")
        for previous in result:
            p=previous["bounds_xz_m"]
            dx=min(x1,p[1])-max(x0,p[0])
            dz=min(z1,p[3])-max(z0,p[2])
            if dx>-MIN_WEB and dz>-MIN_WEB:
                raise ValueError("Opening borders need nonzero compatible piers")
        result.append({
            "kind":kind,
            "x_center_m":round(x,6),"bottom_m":round(z,6),
            "width_m":round(w,6),"height_m":round(h,6),
            "bounds_xz_m":[round(x0,6),round(x1,6),
                           round(z0,6),round(z1,6)]})
    return result


def apertured_wall_mesh(width_m,thickness_m,height_m,openings):
    width=_number(width_m,"wall width")
    depth=_number(thickness_m,"wall depth")
    height=_number(height_m,"wall height")
    if not (.6<=width<=40 and .08<=depth<=1.5 and
            2.1<=height<=20):
        raise ValueError("Original modular wall measured metres out of bounds")
    accepted=_validate_openings(width,height,openings)
    xmin,xmax=-width/2,width/2
    zmin,zmax=-height/2,height/2
    xs=sorted({xmin,xmax}|{x for hole in accepted
                           for x in hole["bounds_xz_m"][:2]})
    zs=sorted({zmin,zmax}|{x for hole in accepted
                           for x in hole["bounds_xz_m"][2:]})
    # Cell surfaces and jambs are composed as ONE connected indexed
    # triangle topology; neighbor interior faces are omitted.
    solid={}
    for i in range(len(xs)-1):
        for j in range(len(zs)-1):
            xmid=(xs[i]+xs[i+1])/2
            zmid=(zs[j]+zs[j+1])/2
            solid[i,j]=not any(
                h["bounds_xz_m"][0]<xmid<h["bounds_xz_m"][1] and
                h["bounds_xz_m"][2]<zmid<h["bounds_xz_m"][3]
                for h in accepted)
    vertices=[]
    triangles=[]
    cache={}
    y0,y1=-depth/2,depth/2
    def idx(x,y,z):
        key=(round(x,6),round(y,6),round(z,6))
        if key not in cache:
            cache[key]=len(vertices);vertices.append(list(key))
        return cache[key]
    def face(corners):
        ids=[idx(*p) for p in corners]
        if len(set(ids))!=4:
            raise RuntimeError("Degenerate aperture wall face")
        triangles.extend((
            [ids[0],ids[1],ids[2]],
            [ids[0],ids[2],ids[3]]))
    for (i,j),is_solid in solid.items():
        if not is_solid:continue
        x0,x1=xs[i],xs[i+1]
        z0,z1=zs[j],zs[j+1]
        face([(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)])
        face([(x1,y1,z0),(x0,y1,z0),(x0,y1,z1),(x1,y1,z1)])
        if not solid.get((i-1,j),False):
            face([(x0,y1,z0),(x0,y0,z0),(x0,y0,z1),(x0,y1,z1)])
        if not solid.get((i+1,j),False):
            face([(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)])
        if not solid.get((i,j-1),False):
            face([(x0,y0,z0),(x0,y1,z0),(x1,y1,z0),(x1,y0,z0)])
        if not solid.get((i,j+1),False):
            face([(x0,y1,z1),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1)])
    if (not 8<=len(vertices)<=MAX_MESH_VERTICES or
        not 12<=len(triangles)<=MAX_MESH_TRIANGLES):
        raise ValueError("Original real wall aperture topology exceeds bounded mesh budget")
    return {
        "format":FORMAT,"kind":"wall_with_real_apertures",
        "points":vertices,"triangles":triangles,
        "size_m":[width,depth,height],
        "openings":accepted,
        "real_jambs_and_wall_thickness":True,
        "no_opacity_only_openings":True,
        "floor_aligned_doors":True,
        "original_source_hash":_hash({
            "vertices":vertices,"triangles":triangles,
            "openings":accepted})}


def _tri_crossing_xz(p,q,r,x,z):
    # Rays along Y cross only front/back surfaces. Barycentric test
    # in the X/Z plane is independent of material/alpha or art metadata.
    a=(p[0],p[2]);b=(q[0],q[2]);c=(r[0],r[2])
    area=(b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1])
    if abs(area)<1e-9:return False
    s=((b[0]-x)*(c[1]-z)-(c[0]-x)*(b[1]-z))/area
    t=((c[0]-x)*(a[1]-z)-(a[0]-x)*(c[1]-z))/area
    u=1-s-t
    return s>=-1e-9 and t>=-1e-9 and u>=-1e-9


def original_through_opening(points,triangles,x,z,thickness):
    """Independent ray-through-geometry proof; aperture metadata alone fails."""
    if len(points)<8 or len(triangles)<12:
        raise ValueError("Actual original source triangle wall required")
    for a,b,c in triangles:
        p,q,r=points[a],points[b],points[c]
        if (max(p[1],q[1],r[1])-min(p[1],q[1],r[1])<1e-7 and
            abs(p[1])<=thickness/2+1e-6 and
            _tri_crossing_xz(p,q,r,x,z)):
            return False
    return True


def prove_facade_geometry(mesh):
    points=mesh["points"]
    triangles=mesh["triangles"]
    width,depth,height=mesh["size_m"]
    for opening in mesh["openings"]:
        x=opening["x_center_m"]
        z=opening["bottom_m"]+opening["height_m"]*.5
        if not original_through_opening(points,triangles,x,z,depth):
            raise RuntimeError("Authored window has pixels painted over solid wall")
        for dx,dz in ((-.23,-.23),(.23,-.23),(-.23,.23),(.23,.23)):
            test_x=x+dx*opening["width_m"]
            test_z=z+dz*opening["height_m"]
            if not original_through_opening(
                    points,triangles,test_x,test_z,depth):
                raise RuntimeError("Authored aperture is not genuinely open throughout")
    if original_through_opening(
            points,triangles,-width/2+MIN_WEB/2,0,depth):
        raise RuntimeError("Fake facade has no solid perimeter structure")
    return {
        "all_source_openings_ray_verified":True,
        "original_aperture_count":len(mesh["openings"]),
        "native_jambs_and_wall_thickness":True,
        "source_geometry_hash":mesh["original_source_hash"]}


def facade_layout(*,width_m,height_m,stories,bays,
                  treatment,seed):
    """Explicit reproducible source facade layout, not a rendered image."""
    if (type(stories) is not int or not 1<=stories<=MAX_STORIES or
        type(bays) is not int or not 2<=bays<=MAX_BAYS or
        type(seed) is not int or not 0<=seed<2**63 or
        treatment not in ("residential","shopfront","industrial")):
        raise ValueError("Bounded repeatable architectural bays/stories required")
    width=_number(width_m,"facade width")
    height=_number(height_m,"facade height")
    bay=width/bays
    story=height/stories
    if bay<2.2 or story<2.5:
        raise ValueError("Actual door/window dimensions need sufficient source span")
    # The bottom storey gets one real door; windows are placed in other
    # bays with enough piers between apertures. Subsequent storeys have
    # independent real framed voids, not texture variation.
    door_index=int(_hash({
        "seed":seed,"treatment":treatment,"bays":bays})[:12],16)%bays
    openings=[]
    bottom=-height/2
    for s in range(stories):
        for b in range(bays):
            center=-width/2+bay*(b+.5)
            if s==0 and b==door_index:
                opening={"kind":"door","x_center_m":center,
                    "bottom_m":bottom,
                    "width_m":min(1.5,bay*.55),
                    "height_m":min(2.25,story-.24)}
            else:
                is_shop=s==0 and treatment=="shopfront"
                kind="storefront" if is_shop else "window"
                variation=int(_hash({
                    "seed":seed,"bay":b,"story":s,
                    "treatment":treatment})[:10],16)%4
                window_width=bay*(.52+variation*.04)
                opening={
                    "kind":kind,"x_center_m":center,
                    "bottom_m":bottom+s*story+(0.35 if is_shop else
                                            max(.66,story*.28)),
                    "width_m":window_width,
                    "height_m":min(
                        story*(.70 if is_shop else .48),
                        story-(0.55 if is_shop else 1.1))}
            openings.append(opening)
    # The apertures MUST pass the actual physical clearance constraints.
    checked=_validate_openings(width,height,openings)
    return {
        "format":FORMAT,"kind":"deterministic_film_facade_layout",
        "width_m":width,"height_m":height,
        "stories":stories,"bays":bays,"treatment":treatment,"seed":seed,
        "openings":[{k:v for k,v in x.items() if k!="bounds_xz_m"}
                    for x in checked],
        "source_procedural_layout_sha256":_hash(checked),
        "renderer_pixels_not_generated":True}


def room_shell_mesh(width_m,depth_m,height_m,wall_thickness_m):
    """Interior floor, ceiling, sides and rear; OPEN front sightline.

    Boundaries are strictly inside exterior shell. They are genuine
    original 3D source mesh surfaces, including room-side walls.
    """
    w=_number(width_m,"room width")
    d=_number(depth_m,"room depth")
    h=_number(height_m,"room height")
    t=_number(wall_thickness_m,"room shell thickness")
    if (not 2<=w<=40 or not 2<=d<=40 or not 2.1<=h<=20 or
        not .04<=t<=.25 or t*4>=min(w,d,h)):
        raise ValueError("Real interior requires measurable 3D clearances")
    x=w/2
    y=d/2
    z=h/2
    blocks=[
        (-x,x,-y,y,-z,-z+t), # floor
        (-x,x,-y,y,z-t,z), # ceiling
        (-x,-x+t,-y,y,-z+t,z-t),
        (x-t,x,-y,y,-z+t,z-t),
        (-x+t,x-t,y-t,y,-z+t,z-t), # actual rear wall
    ]
    points,faces=_box_shell_mesh(blocks)
    if len(points)>MAX_MESH_VERTICES or len(faces)>MAX_MESH_TRIANGLES:
        raise ValueError("Original interior shell has too many surfaces")
    # A line from exterior through the missing front wall sees an
    # independently authored rear interior wall, not a void/black card.
    return {
        "format":FORMAT,"kind":"genuine_room_interior_shell",
        "points":points,"triangles":faces,
        "size_m":[w,d,h],
        "front_portal_open":True,"rear_wall_is_real_geometry":True,
        "real_floor_ceiling_two_sides":True,
        "interior_source_hash":_hash({
            "points":points,"triangles":faces})}


def publish_facade_asset(index,project_id,asset_id,*,layout,thickness_m,
                         color_rgb):
    """Creates a source asset only; attaching it still needs director 02M grant."""
    if type(layout) is not dict or layout.get("format")!=FORMAT or (
            layout.get("kind")!="deterministic_film_facade_layout"):
        raise ValueError("Only deterministic original facade design")
    expected=facade_layout(
        width_m=layout["width_m"],height_m=layout["height_m"],
        stories=layout["stories"],bays=layout["bays"],
        treatment=layout["treatment"],seed=layout["seed"])
    if layout!=expected:
        raise PermissionError("Unreviewed building aperture layout altered")
    mesh=apertured_wall_mesh(
        layout["width_m"],thickness_m,
        layout["height_m"],layout["openings"])
    proof=prove_facade_geometry(mesh)
    published=OpenUSDAssetRegistry(index).publish(
        project_id,asset_id,shape="mesh",
        size_m=max(mesh["size_m"]),
        points=mesh["points"],triangles=mesh["triangles"],
        preview_material={
            "base_color_rgb":color_rgb,"roughness":.65,
            "metallic":0.02})
    # A first-party source proof is never a renderer pixel acceptance.
    return {"asset":published,"layout":layout,"source":mesh,
            "source_proof":proof,
            "native_cycles_picture_verified":False}


def publish_room_asset(index,project_id,asset_id,*,width_m,depth_m,
                       height_m,wall_thickness_m,color_rgb):
    mesh=room_shell_mesh(
        width_m,depth_m,height_m,wall_thickness_m)
    published=OpenUSDAssetRegistry(index).publish(
        project_id,asset_id,shape="mesh",
        size_m=max(mesh["size_m"]),
        points=mesh["points"],triangles=mesh["triangles"],
        preview_material={
            "base_color_rgb":color_rgb,"roughness":.83,
            "metallic":0.})
    return {"asset":published,"source":mesh,
            "actual_room_geometry":True,
            "front_portal_open":True,
            "native_interior_render_reviewed":False}


DETAIL_FORMAT="nvp.usd_film02m.reproducible_original_geometry_detail.v1"


def verify_detail(index,pid,detail_id,revision,*,asset_id=None,
                  asset_revision=None,required_kind=None):
    from backend.nvp_film_index import _id
    _id(detail_id,"published original aperture/room source detail")
    row=index.read_revision(pid,detail_id,revision)
    doc=row["data"]
    if row["kind"]!="presentation" or doc.get("format")!=DETAIL_FORMAT:
        raise PermissionError("Only original saved procedural source geometry")
    if (asset_id is not None and doc.get("asset_id")!=asset_id or
        asset_revision is not None and doc.get("asset_revision")!=asset_revision or
        required_kind is not None and doc.get("geometry_kind")!=required_kind):
        raise PermissionError("Procedural detail belongs to another source")
    src,index_layer=OpenUSDAssetRegistry(index).open(
        pid,doc["asset_id"],doc["asset_revision"])
    if (row["dependencies"]!=[{
            "object_id":doc["asset_id"],"revision":doc["asset_revision"],
            "role":"asset"}] or
        src["document_sha256"]!=doc["asset_sha256"] or
        src["data"]["layer_sha256"]!=doc["source_layer_sha256"]):
        raise RuntimeError("Original procedural asset reference changed")
    if doc["geometry_kind"]=="wall_with_real_apertures":
        layout=doc["layout"]
        regenerated=facade_layout(
            width_m=layout["width_m"],height_m=layout["height_m"],
            stories=layout["stories"],bays=layout["bays"],
            treatment=layout["treatment"],seed=layout["seed"])
        if layout!=regenerated:
            raise RuntimeError("Source facade procedural layout was revised")
        mesh=apertured_wall_mesh(
            layout["width_m"],doc["thickness_m"],
            layout["height_m"],layout["openings"])
        prove_facade_geometry(mesh)
    elif doc["geometry_kind"]=="genuine_room_interior_shell":
        p=doc["room_parameters_m"]
        mesh=room_shell_mesh(
            p["width"],p["depth"],p["height"],p["wall_thickness"])
    else:
        raise PermissionError("Unknown original geometry source kind")
    if (mesh["points"]!=src["data"]["points"] or
        mesh["triangles"]!=src["data"]["triangles"] or
        _hash({"points":mesh["points"],
               "triangles":mesh["triangles"]})!=doc["mesh_sha256"] or
        doc["source_generated_without_blender"] is not True or
        doc["native_cycles_pixels_verified"] is not False):
        raise RuntimeError("Real USD geometry no longer reproduces from original design")
    return row


def _publish_detail(index,pid,detail_id,asset,mesh,*,layout=None,
                    thickness_m=None,room_parameters_m=None):
    from backend.nvp_film_index import _id,_require_pid
    _require_pid(pid)
    _id(detail_id,"original geometry design detail")
    row=asset["asset"]
    doc={
        "format":DETAIL_FORMAT,
        "asset_id":row["object_id"],
        "asset_revision":row["revision"],
        "asset_sha256":row["document_sha256"],
        "source_layer_sha256":index.read_revision(
            pid,row["object_id"],row["revision"])["data"]["layer_sha256"],
        "geometry_kind":mesh["kind"],
        "mesh_sha256":_hash({
            "points":mesh["points"],"triangles":mesh["triangles"]}),
        "source_generated_without_blender":True,
        "native_cycles_pixels_verified":False,
        "original_actor_performance_unchanged":True}
    if layout is not None:
        doc.update({"layout":layout,"thickness_m":float(thickness_m),
                    "through_wall_rays_independently_verified":
                        asset["source_proof"]["all_source_openings_ray_verified"]})
    if room_parameters_m is not None:
        doc["room_parameters_m"]=room_parameters_m
        doc["front_portal_open"]=True
        doc["real_interior_rear_wall"]=True
    published=index.register_revision(
        pid,detail_id,"presentation",doc,
        expected_revision=0,
        dependencies=[{"object_id":row["object_id"],
                       "revision":row["revision"],"role":"asset"}])
    verified=verify_detail(
        index,pid,detail_id,published["revision"],
        asset_id=row["object_id"],asset_revision=row["revision"],
        required_kind=mesh["kind"])
    return {"detail":published,"source_asset":row,
            "detail_reopened_from_original_geometry":True,
            "source_design_sha256":verified["document_sha256"]}


def publish_facade_with_detail(index,pid,asset_id,detail_id,*,
                               layout,thickness_m,color_rgb):
    asset=publish_facade_asset(
        index,pid,asset_id,layout=layout,
        thickness_m=thickness_m,color_rgb=color_rgb)
    return _publish_detail(
        index,pid,detail_id,asset,asset["source"],
        layout=layout,thickness_m=thickness_m)


def publish_room_with_detail(index,pid,asset_id,detail_id,*,
                             width_m,depth_m,height_m,
                             wall_thickness_m,color_rgb):
    asset=publish_room_asset(
        index,pid,asset_id,width_m=width_m,depth_m=depth_m,
        height_m=height_m,wall_thickness_m=wall_thickness_m,
        color_rgb=color_rgb)
    parameters={
        "width":float(width_m),"depth":float(depth_m),
        "height":float(height_m),
        "wall_thickness":float(wall_thickness_m)}
    return _publish_detail(
        index,pid,detail_id,asset,asset["source"],
        room_parameters_m=parameters)
