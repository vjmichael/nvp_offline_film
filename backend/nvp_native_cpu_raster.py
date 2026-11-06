"""DA-05: first independent native CPU rasterizer for original USD geometry.

No FFmpeg, Blender, video decoder, 2D source-frame index or external code
execution. Verified FilmIndex/OpenUSD primitive shapes and exact-time USD
world transforms are projected through the chosen real authored camera.
This restricted renderer handles cubes/spheres and blank authored gaps:
unsupported real character meshes/materials refuse production use instead
of forging them. Pillow encodes the disposable derived PNG on demand.

This is a first procedural geometry acceptance backend, NOT a general
Hydra renderer, calibrated color pipeline or completed cinema master.
"""
from __future__ import annotations

from io import BytesIO
import math

from PIL import Image,ImageDraw

from backend.nvp_data_av_visual import visual_state
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import _int

OUTPUT_WIDTH=640
OUTPUT_HEIGHT=360
FORMAT="nvp.native_source_cpu_raster.v1"
FACES=(
    ((0,1,2,3),.55),((4,5,6,7),.8),
    ((0,1,5,4),.75),((1,2,6,5),.65),
    ((2,3,7,6),.95),((3,0,4,7),.85),
)


def _apply(matrix,point):
    x,y,z=point
    w=x*matrix[0][3]+y*matrix[1][3]+z*matrix[2][3]+matrix[3][3]
    if abs(w)<1e-12:
        raise ValueError("Invalid homogeneous USD projective transform")
    return tuple((x*matrix[0][j]+y*matrix[1][j]+
                 z*matrix[2][j]+matrix[3][j])/w for j in range(3))


def _inverse(matrix):
    if (type(matrix) is not list or len(matrix)!=4 or
        any(type(row) is not list or len(row)!=4 for row in matrix)):
        raise ValueError("Unknown authored USD camera matrix")
    m=[[float(x) for x in row]+[float(i==j) for j in range(4)]
       for i,row in enumerate(matrix)]
    if any(not math.isfinite(x) for row in m for x in row):
        raise ValueError("Nonfinite source camera transform")
    for col in range(4):
        pivot=max(range(col,4),key=lambda row:abs(m[row][col]))
        if abs(m[pivot][col])<1e-10:
            raise ValueError("Singular source USD camera matrix")
        m[col],m[pivot]=m[pivot],m[col]
        scale=m[col][col]
        m[col]=[value/scale for value in m[col]]
        for row in range(4):
            if row!=col:
                q=m[row][col]
                m[row]=[a-q*c for a,c in zip(m[row],m[col])]
    return [row[4:] for row in m]


def _project(world,camera_inverse,focal_mm):
    x,y,z=_apply(camera_inverse,world)
    if z>=-0.05: # Native USD cameras observe along -Z
        return None
    factor=(focal_mm/36.0)*(OUTPUT_WIDTH/-z)
    return (OUTPUT_WIDTH/2+x*factor,
            OUTPUT_HEIGHT/2-y*factor,
            -z)


def _cube_vertices(size):
    half=size*.5
    return [(a*half,b*half,c*half) for a,b,c in (
        (-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
        (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]


class NativeSourceRaster:
    def __init__(self,index:FilmIndex,project_id,*,width=OUTPUT_WIDTH,
                 height=OUTPUT_HEIGHT):
        if not isinstance(index,FilmIndex):
            raise TypeError("A trusted FilmIndex must supply real USD geometry")
        if width!=OUTPUT_WIDTH or height!=OUTPUT_HEIGHT:
            raise ValueError("Only the verified bounded native raster contract is available")
        self.index=index
        self.project_id=project_id

    def render_png(self,*,scope,tick,camera_path,source_snapshot):
        _int(tick,"native picture source moment")
        if (type(source_snapshot) is not dict or
            source_snapshot.get("time_tick")!=tick or
            source_snapshot.get("scene_document_sha256")!=scope.get(
                "scene_document_sha256")):
            raise RuntimeError("Native image source moment is not SHA-bound")
        img=Image.new("RGB",(OUTPUT_WIDTH,OUTPUT_HEIGHT),(0,0,0))
        if camera_path is None:
            # Explicit Film Time has no active camera. Render true black,
            # without inventing a camera/picture or skipping that interval.
            out=BytesIO();img.save(out,format="PNG")
            return out.getvalue()
        objs=visual_state(self.index,self.project_id,source_snapshot)
        camera=next((x for x in objs["objects"] if
                     x["path"]==camera_path and
                     x["semantic_role"]=="camera"),None)
        if camera is None:
            raise RuntimeError("Only an original USD camera can observe source")
        inverse=_inverse(camera["world_matrix"])
        schema=next((x for x in
                     source_snapshot.get("native_scene_schemas",[])
                     if x.get("prim_path")==camera_path and
                     x.get("schema")=="UsdGeom.Camera"),None)
        if schema is None:
            raise RuntimeError("Real native UsdGeom.Camera optics are required")
        focal=schema["focal_length_mm"]
        if type(focal) not in (int,float) or not math.isfinite(focal) or not 1<=focal<=400:
            raise RuntimeError("Unsupported original camera focal length")
        primitives=[]
        for obj in objs["objects"]:
            if obj["path"]==camera_path or obj["semantic_role"]=="light":
                continue
            if obj["shape"]=="gizmo":
                # Actors and other geometry may not be silently rendered as
                # placeholder spheres in an explicitly approved 2D package.
                if obj["semantic_role"]=="actor":
                    raise RuntimeError("Source actor has no approved real geometry")
                continue
            matrix=obj["world_matrix"]
            size=obj["size_m"]
            if obj["shape"]=="cube":
                projected=[_project(_apply(matrix,p),inverse,focal)
                           for p in _cube_vertices(size)]
                for face,brightness in FACES:
                    pts=[projected[i] for i in face]
                    if any(p is None for p in pts):
                        continue
                    avg=sum(p[2] for p in pts)/len(pts)
                    shade=round(185*brightness)
                    primitives.append((avg,"polygon",[(p[0],p[1]) for p in pts],
                                       (shade,shade,shade)))
            elif obj["shape"]=="sphere":
                center=_project(_apply(matrix,(0,0,0)),inverse,focal)
                if center is None:continue
                edge=_project(_apply(matrix,(size*.5,0,0)),inverse,focal)
                if edge is None:continue
                radius=max(1.,math.hypot(edge[0]-center[0],edge[1]-center[1]))
                primitives.append((center[2],"ellipse",(
                    center[0]-radius,center[1]-radius,
                    center[0]+radius,center[1]+radius),(164,174,198)))
        draw=ImageDraw.Draw(img)
        # Painter's depth sorting. The primitive-only backend is deliberately
        # restricted and is not a substitute for per-fragment z-buffering.
        for _,shape,points,color in sorted(
                primitives,key=lambda item:item[0],reverse=True):
            if shape=="polygon":
                draw.polygon(points,fill=color)
            else:
                draw.ellipse(points,fill=color)
        output=BytesIO()
        img.save(output,format="PNG",optimize=False)
        return output.getvalue()
