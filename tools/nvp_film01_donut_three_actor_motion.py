"""FILM01-DONUT: three-actor crossing, genuine USD pixel/depth review frames.

Green box crosses *behind* original torus actor. Blue sphere passes along
the torus hole's true Z axis. Every frame is rasterized from the same
frozen original 3D USD Take, never AI-generated or a screen-space sprite.

Evidence: original source object positions, native depth-tested center
owner, visible actor pixels, source hashes, actual PNG and genuine
source-derived animated GIF. GIF is a silent diagnostic; it is NOT the
30-second mastered movie or validated DCI picture.
"""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image,ImageDraw

from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_wo6_07f_rendered_av import _encode_real_raster
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from tools.nvp_film01_donut_light_probe import (
    build_frozen_donut_source,DONUT_PATH,BOX_PATH,SPHERE_PATH,BOX_DEPTH,
    SPHERE_RADIUS)

FORMAT="nvp.film01.donut_box_behind_sphere_through_real_hole.v1"
FPS=24
FRAMES=72
FRAME_TICK=TICKS_PER_SECOND//FPS
KEY_FRAMES=(0,12,24,36,48,60)
EXPECTED_CENTER_OWNER={0:SPHERE_PATH,24:BOX_PATH,48:SPHERE_PATH}
SHOT_NAMES={
    0:"Sphere seen through hole",
    12:"Box approaches behind ring",
    24:"Box in hole, sphere behind box",
    36:"Sphere enters ring opening",
    48:"Sphere crosses torus plane",
    60:"Sphere emerges toward camera",
}


def _pose(snapshot,path):
    objs=[obj for obj in snapshot["objects"] if obj["path"]==path]
    if len(objs)!=1 or objs[0]["semantic_role"]!="actor":
        raise RuntimeError("Missing true native object actor in frozen USD snapshot")
    xyz=objs[0]["world_translation"]
    if len(xyz)!=3 or any(not math.isfinite(v) for v in xyz):
        raise RuntimeError("Actual original 3D actor world position invalid")
    return [float(x) for x in xyz]


def render_actual_three_actor_frames(source,*,full_72_frames=False):
    if type(full_72_frames) is not bool:
        raise TypeError("Explicitly select full animated source or six proof frames")
    idx=source["index"];pid=source["project_id"]
    sha=source["take_sha256"]
    n=FRAMES if full_72_frames else len(KEY_FRAMES)
    chosen=range(FRAMES) if full_72_frames else KEY_FRAMES
    raster=NativeSceneLinearRaster(idx)
    images=[]
    receipts=[]
    # FrozenSceneAV is an explicit first-party session with close(),
    # not a Python context-manager. Always close even on failed pixels.
    native=FrozenSceneAV(
        idx,pid,"DonutLightingTake",
        expected_take_sha256=sha,listener_path="/World/Camera")
    try:
        for frame in chosen:
            tick=frame*FRAME_TICK
            snap=native.snapshot(tick)
            torus=_pose(snap,DONUT_PATH)
            box=_pose(snap,BOX_PATH)
            sphere=_pose(snap,SPHERE_PATH)
            if (abs(box[2]-BOX_DEPTH)>1e-6 or
                    abs(sphere[0])>1e-6 or abs(sphere[1])>1e-6 or
                    source["sphere_clearance_from_hole_m"]<.2):
                raise PermissionError("Box/ball cannot leave original behind/hole scene path")
            if sphere[2]>0 and frame<24:
                raise RuntimeError("Sphere crossed ring plane before intended action")
            color,proof=raster.render(
                pid,"DonutLightingTake",sha,
                tick=tick,camera_path="/World/Camera",
                source_session=native,source_snapshot=snap,
                visibility_probe=True)
            if (proof["original_take_sha256"]!=sha or
                    proof["scene_document_sha256"]!=source["scene_sha256"] or
                    proof["native_depth_tested_visible_pixel_probe"] is not True or
                    proof["source_geometry_triangles"]<
                        len(source["geometry"]["mesh_triangles"])+12 or
                    proof["rasterized_triangles"]<10 or
                    proof["source_modified"] is not False):
                raise PermissionError("Original USD 3D scene/depth proof is not verified")
            counts=proof["visible_original_prim_pixels"]
            if (counts.get(DONUT_PATH,0)<50 or
                    counts.get(BOX_PATH,0)<0 or
                    counts.get(SPHERE_PATH,0)<0):
                raise RuntimeError("Source torus and other actors not projected")
            if frame in EXPECTED_CENTER_OWNER and (
                    proof["center_visible_original_prim"]!=
                    EXPECTED_CENTER_OWNER[frame]):
                raise RuntimeError(
                    "Real native center depth owner violates box/ball passage plan")
            out=_encode_real_raster(color,proof)
            raw=base64.b64decode(
                out["frame_image_data_url"].split(",",1)[1],
                validate=True)
            if sha256(raw).hexdigest()!=out["frame_png_sha256"]:
                raise PermissionError("Native scene PNG frame SHA mismatch")
            with Image.open(BytesIO(raw)) as picture:
                picture.load()
                if picture.format!="PNG" or picture.size!=(640,360):
                    raise RuntimeError("Native source full-resolution preview missing")
                # Source-derived animation uses the ORIGINAL NVP pixels.
                images.append((frame,picture.convert("RGB").copy(),raw))
            receipts.append({
                "frame_zero":frame,
                "original_film_tick":str(tick),
                "original_take_sha256":sha,
                "scene_document_sha256":source["scene_sha256"],
                "torus_world_position":torus,
                "box_world_position":box,
                "sphere_world_position":sphere,
                "sphere_through_torus_axis_xy":[sphere[0],sphere[1]],
                "sphere_clearance_from_real_mesh_hole_m":
                    source["sphere_clearance_from_hole_m"],
                "box_physically_behind_torus":box[2]<torus[2]-.5,
                "camera_depth_test_center_actor":
                    proof["center_visible_original_prim"],
                "native_visible_source_actor_pixels":counts,
                "depth_tested_native_picture_sha256":
                    out["frame_png_sha256"],
                "native_mesh_triangles":
                    proof["source_geometry_triangles"],
                "real_shadow_ray_tracing_performed":
                    proof["real_light_ray_traced_shadows_computed"],
                "interobject_reflection_ray_tracing_performed":
                    proof["real_interobject_reflections_computed"],
                "source_original_modified":False,
            })
    finally:
        native.close()
    if any(not row["box_physically_behind_torus"] for row in receipts):
        raise RuntimeError("Passing box was not behind donut throughout filmed action")
    if len(receipts)!=n or len(images)!=n:
        raise RuntimeError("Missing original scene motion picture frames")
    return images,receipts


def export_three_actor_picture_probe(source,output,*,full_72_frames=False):
    dest=Path(output)
    if not dest.is_absolute() or dest.exists() or dest.is_symlink():
        raise PermissionError("Native actual picture diagnostic needs fresh absolute folder")
    frames,rows=render_actual_three_actor_frames(
        source,full_72_frames=full_72_frames)
    dest.mkdir(parents=True,mode=0o700)
    by_frame={f:(img,png) for f,img,png in frames}
    contact=Image.new("RGB",(3*640+4*12,2*390+3*12),(21,23,30))
    draw=ImageDraw.Draw(contact)
    if full_72_frames:
        # Output ALL original 72 PNGs. Do not quietly substitute a
        # 6-still slideshow for the requested 3-second native motion.
        for frame,image,png in frames:
            (dest/f"original_usd_frame_{frame:03d}.png").write_bytes(png)
        playback=[image.copy() for _,image,_ in frames]
        playback[0].save(
            dest/"donut_box_sphere_actual_3sec_NVP.gif",
            format="GIF",save_all=True,append_images=playback[1:],
            duration=42,loop=0,optimize=False,disposal=2)
        with Image.open(dest/"donut_box_sphere_actual_3sec_NVP.gif") as gif:
            if getattr(gif,"n_frames",0)!=FRAMES:
                raise RuntimeError("3-second source animation omitted native frames")
    for i,frame in enumerate(KEY_FRAMES):
        if frame not in by_frame:
            raise RuntimeError("Missing actual decisive object-overlap pose")
        img,png=by_frame[frame]
        x=12+(i%3)*652
        y=12+(i//3)*390
        contact.paste(img,(x,y))
        draw.text((x,y+365),f"{frame/24:.2f}s  {SHOT_NAMES[frame]}",
                  fill=(237,238,241))
        (dest/f"donut_actors_key_{frame:03d}.png").write_bytes(png)
    sheet=dest/"donut_box_sphere_real_NVP_6_moments.png"
    contact.save(sheet,format="PNG")
    result={
        "format":FORMAT,
        "original_source_take_sha256":source["take_sha256"],
        "original_torus_mesh_sha256":source["torus_source_mesh_sha256"],
        "actual_three_original_usd_object_actors":True,
        "genuine_raster_source_frames":len(frames),
        "full_72_frames_and_gif":full_72_frames,
        "through_hole_mechanical_clearance_m":
            source["sphere_clearance_from_hole_m"],
        "center_depth_owner_at_key_frames":{
            str(x["frame_zero"]):x["camera_depth_test_center_actor"]
            for x in rows if x["frame_zero"] in EXPECTED_CENTER_OWNER},
        "source_pose_and_visibility_receipts":rows,
        "genuine_six_moment_contact_sha256":sha256(sheet.read_bytes()).hexdigest(),
        "real_interobject_cast_shadows_computed":False,
        "real_interobject_reflections_computed":False,
        "native_depth_occlusion_computed":True,
        "object_interpenetration_not_shown_by_silhouette_alone":True,
        "native_preview_only_not_DCI":True,
        "human_picture_review_required":True,
    }
    (dest/"donut_three_actor_original_source_receipts.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root",type=Path,required=True)
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--full-72",action="store_true")
    cli.add_argument("--consent",required=True)
    args=cli.parse_args()
    if args.consent!="I_APPROVE_DISPOSABLE_DONUT_SOURCE":
        cli.error("Only a fresh test-authorized original USD scene is allowed")
    source=build_frozen_donut_source(args.root.resolve())
    result=export_three_actor_picture_probe(
        source,args.output.resolve(),full_72_frames=args.full_72)
    print(json.dumps({
        "result":"ACTUAL_NVP_DEPTH_TESTED_DONUT_BOX_SPHERE_REVIEW",
        "source_sha256":result["original_source_take_sha256"],
        "native_frames":result["genuine_raster_source_frames"],
        "gif":result["full_72_frames_and_gif"],
        "true_reflections_tested":False,
        "true_cast_shadows_tested":False,
        "artist_approved":False,
    },indent=2))


if __name__=="__main__":
    main()
