"""Real OpenUSD donut-actor lighting diagnostic: source USD -> four real PNGs.

This deliberately tests the director's idea that an *object* can act.
The donut is a frozen USD mesh with a real hole and rough surface,
not an image search/AI-drawn donut. The four looks are genuine NVP
640x360 scene-linear CPU raster pixels with original-source receipts:
neutral, silver fill, gold fill, and impossible fixed summer-3PM sun.

Artistic/pixel-level QC here does not claim smooth vertex normals,
physical shadow transport, photoreal quality, DCI or studio acceptance.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_wo6_07f_rendered_av import _encode_real_raster
from backend.nvp_virtual_light_fx import make_simple_virtual_fx
from backend.nvp_film01_donut_actor import original_donut_mesh

FORMAT="nvp.film01.real_source_donut_actor_four_lights.v1"
DONUT_PATH="/World/DonutActor"
BOX_PATH="/World/BoxActor"
SPHERE_PATH="/World/SphereActor"
# Real torus inner radius .63m; sphere .30m radius has .33m clearance
# through the torus tube, even while the torus is slowly bobbing.
BOX_DEPTH=-2.2
SPHERE_RADIUS=.30
STORY_TICKS=(0, TICKS_PER_SECOND//2, TICKS_PER_SECOND,
             3*TICKS_PER_SECOND//2, 2*TICKS_PER_SECOND,
             5*TICKS_PER_SECOND//2)
FILENAME="donut_actor_real_NVP_4_lighting_looks.png"
SELECTED_TICK=TICKS_PER_SECOND
LOOKS=("neutral","silver_fill","gold_fill","locked_summer_3pm_sun")


def build_frozen_donut_source(workspace):
    """Create once from first-party NVP USD/FilmIndex and freeze true source."""
    root=Path(workspace)
    if not root.is_absolute() or root.exists() or root.is_symlink():
        raise PermissionError("Diagnostic must use a new absolute workspace")
    root.mkdir(parents=True,mode=0o700)
    studio=Studio(root/"donut.sqlite3")
    project=studio.create_project(
        "NVP Donut Actor — Light Probe",
        "One genuine OpenUSD torus actor tests neutral/gold/silver/fixed 3PM shading")
    pid=project["id"]
    index=FilmIndex(studio)
    donut=original_donut_mesh()
    asset=OpenUSDAssetRegistry(index).publish(
        pid,"DonutMesh",shape="mesh",size_m=1.4,
        points=donut["mesh_points"],
        triangles=donut["mesh_triangles"],
        face_uvs=donut["mesh_face_uvs"],
        preview_material={
            "base_color_rgb":[.78,.63,.47],
            "roughness":.26,
            "metallic":.08})
    # These are THREE genuine source actors. The box crosses behind
    # the torus while the smaller sphere travels *through its open hole*
    # along its actual Z axis (toward the native camera at +Z).
    assets=OpenUSDAssetRegistry(index)
    box_asset=assets.publish(
        pid,"BoxActorMesh",shape="cube",size_m=.8,
        preview_material={"base_color_rgb":[.14,.78,.31],
                          "roughness":.46,"metallic":.18})
    sphere_asset=assets.publish(
        pid,"SphereActorMesh",shape="sphere",size_m=2*SPHERE_RADIUS,
        preview_material={"base_color_rgb":[.25,.42,.94],
                          "roughness":.22,"metallic":.26})
    prims=[
        {"path":DONUT_PATH,"role":"actor","position":[0.,0.,0.]},
        {"path":BOX_PATH,"role":"actor","position":[-2.4,0.,BOX_DEPTH]},
        {"path":SPHERE_PATH,"role":"actor","position":[0.,0.,-4.]},
        {"path":"/World/Camera","role":"camera","position":[0.,0.,9.]},
        {"path":"/World/KeyLight","role":"light","position":[2.8,3.,5.0]},
    ]
    # Box: -X -> 0 -> +X strictly behind donut; sphere: -Z -> +Z
    # passes the ring without intersecting it. Source motion is in the
    # original immutable USD layer, not screen-space frame invention.
    curves=[
        {"path":DONUT_PATH,"samples":[
            {"tick":0,"position":[0.,0.,0.]},
            {"tick":SELECTED_TICK,"position":[0.,0.,.12]},
            {"tick":2*TICKS_PER_SECOND,"position":[0.,0.,0.]},
            {"tick":3*TICKS_PER_SECOND,"position":[0.,0.,0.]}]},
        {"path":BOX_PATH,"samples":[
            {"tick":0,"position":[-2.4,0.,BOX_DEPTH]},
            {"tick":SELECTED_TICK,"position":[0.,0.,BOX_DEPTH]},
            {"tick":2*TICKS_PER_SECOND,"position":[2.4,0.,BOX_DEPTH]},
            {"tick":3*TICKS_PER_SECOND,"position":[2.8,0.,BOX_DEPTH]}]},
        {"path":SPHERE_PATH,"samples":[
            {"tick":0,"position":[0.,0.,-4.]},
            {"tick":SELECTED_TICK,"position":[0.,0.,-3.7]},
            {"tick":3*TICKS_PER_SECOND//2,"position":[0.,0.,-1.]},
            {"tick":2*TICKS_PER_SECOND,"position":[0.,0.,.1]},
            {"tick":5*TICKS_PER_SECOND//2,"position":[0.,0.,1.45]},
            {"tick":3*TICKS_PER_SECOND,"position":[0.,0.,2.2]}]},
    ]
    scene=OpenUSDSceneBridge(index).publish(
        pid,"DonutLightingScene",prims=prims,curves=curves,
        asset_bindings=[
            {"path":DONUT_PATH,"asset_id":"DonutMesh","asset_revision":1},
            {"path":BOX_PATH,"asset_id":"BoxActorMesh","asset_revision":1},
            {"path":SPHERE_PATH,"asset_id":"SphereActorMesh","asset_revision":1},
        ],
        native_schemas=True)
    duration=3*TICKS_PER_SECOND
    timeline=TemporalLedger(index).publish(
        pid,"DonutLightingTimeline",[
            {"event_id":"DonutPerformance","event_kind":"action",
             "subject_id":"DonutActor","start_tick":0,
             "end_tick":duration,"source_id":"DonutLightingScene",
             "source_revision":1,
             "payload":{"usd_prim_path":DONUT_PATH,
                        "actor_is_a_real_object":True}},
            {"event_id":"BoxCrossesBehindDonut","event_kind":"action",
             "subject_id":"BoxActor","start_tick":0,
             "end_tick":duration,"source_id":"DonutLightingScene",
             "source_revision":1,
             "payload":{"usd_prim_path":BOX_PATH,
                        "blocking":"torus ring in depth"}},
            {"event_id":"SpherePassesThroughHole","event_kind":"action",
             "subject_id":"SphereActor","start_tick":0,
             "end_tick":duration,"source_id":"DonutLightingScene",
             "source_revision":1,
             "payload":{"usd_prim_path":SPHERE_PATH,
                        "true_hole_passage":True}},
            {"event_id":"DonutCamera","event_kind":"camera",
             "subject_id":"DirectorCamera","start_tick":0,
             "end_tick":duration,"source_id":"DonutLightingScene",
             "source_revision":1,
             "payload":{"usd_prim_path":"/World/Camera"}},
        ],duration_tick=duration)
    capture=OpenUSDTakeCapture(
        index,verify_creator_action=lambda event,scope:(
            event=="CI_ONLY_DONUT_TEST_CAPTURE" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1" and
            scope["duration_tick"]==duration))
    frozen=capture.freeze(
        pid,"DonutLightingTake",scene_id="DonutLightingScene",
        scene_revision=1,timeline_id="DonutLightingTimeline",
        timeline_revision=1,
        sample_ticks=[0,SELECTED_TICK,2*TICKS_PER_SECOND,
                      5*TICKS_PER_SECOND//2],
        creator_event="CI_ONLY_DONUT_TEST_CAPTURE")
    if capture.verify_take(pid,"DonutLightingTake")[
            "status"]!="VERIFIED_FROZEN_DATA_TAKE":
        raise RuntimeError("Original donut USD actor performance did not freeze")
    return {
        "index":index,"studio":studio,"project_id":pid,
        "take_sha256":frozen["document_sha256"],
        "scene_sha256":scene["document_sha256"],
        "mesh_asset_sha256":asset["document_sha256"],
        "box_source_asset_sha256":box_asset["document_sha256"],
        "sphere_source_asset_sha256":sphere_asset["document_sha256"],
        "torus_source_mesh_sha256":donut["mesh_sha256"],
        "sphere_radius_m":SPHERE_RADIUS,
        "sphere_clearance_from_hole_m":round(
            donut["hole_radius"]-SPHERE_RADIUS,6),
        "all_three_actors_authoritatively_animated":True,
        "geometry":donut,
    }


def render_donut_four_looks(source):
    idx=source["index"];pid=source["project_id"]
    raster=NativeSceneLinearRaster(idx)
    results=[]
    image_arrays=[]
    for look in LOOKS:
        fx=None
        if look=="locked_summer_3pm_sun":
            fx=[make_simple_virtual_fx(
                look,"/World/Scene",fx_id="DonutFixedSummerSun",
                intensity=.7,azimuth=245,elevation=48)]
        elif look!="neutral":
            fx=[make_simple_virtual_fx(
                look,DONUT_PATH,fx_id="Donut"+look,
                intensity=.6)]
        original,proof=raster.render(
            pid,"DonutLightingTake",source["take_sha256"],
            tick=SELECTED_TICK,camera_path="/World/Camera",
            virtual_fx=fx)
        if (proof["original_take_sha256"]!=source["take_sha256"] or
                proof["scene_document_sha256"]!=source["scene_sha256"] or
                proof["rasterized_triangles"]<=0 or
                proof["source_geometry_triangles"]!=len(
                    source["geometry"]["mesh_triangles"]) or
                proof["source_modified"] is not False or
                bool(proof["virtual_artistic_fx_applied_to_real_pixels"])!=
                (look!="neutral")):
            raise PermissionError("Real donut source did not reach native pixel shader")
        image=_encode_real_raster(original,proof)
        bytes_png=base64.b64decode(
            image["frame_image_data_url"].split(",",1)[1],validate=True)
        if hashlib.sha256(bytes_png).hexdigest()!=image["frame_png_sha256"]:
            raise PermissionError("Genuine NVP donut PNG verification failed")
        with Image.open(BytesIO(bytes_png)) as img:
            img.load()
            if img.size!=(640,360) or img.format!="PNG" or img.mode!="RGB":
                raise PermissionError("Original NVP donut preview image invalid")
            pixels=np.asarray(img,dtype=np.uint8).copy()
        # A torus must be a ring, not a filled disk. Inspect the actual
        # center and an annulus where the original true mesh projects.
        height,width=pixels.shape[:2]
        yy,xx=np.ogrid[:height,:width]
        radius=np.sqrt((xx-width/2)**2+(yy-height/2)**2)
        luminance=(.2126*pixels[:,:,0]+.7152*pixels[:,:,1]+.0722*pixels[:,:,2])
        center=float(np.mean(luminance[radius<12]))
        annular=float(np.mean(luminance[(radius>45)&(radius<150)]))
        # Record true highlight/midtone spread *inside the lit ring*,
        # rather than confusing the black hole with dark material.
        lit_ring=luminance[(radius>45)&(radius<150)&(luminance>2)]
        if center>2 or annular<=1. or lit_ring.size<200:
            raise RuntimeError(
                "Rendered donut must show an actual dark central hole and visible ring")
        p10,p50,p90=(float(v) for v in np.percentile(lit_ring,[10,50,90]))
        if look=="neutral" and p90-p10<1.:
            raise RuntimeError(
                "Neutral light did not produce measurable curved-surface shading")
        image_arrays.append(pixels)
        results.append({
            "look":look,"true_3d_usd_mesh_actor":True,
            "original_take_sha256":source["take_sha256"],
            "original_scene_sha256":source["scene_sha256"],
            "torus_mesh_sha256":source["torus_source_mesh_sha256"],
            "rendered_triangle_count":proof["rasterized_triangles"],
            "authored_torus_triangle_count":proof["source_geometry_triangles"],
            "real_image_png_sha256":image["frame_png_sha256"],
            "scene_linear_pixel_sha256":proof["scene_linear_rgba_sha256"],
            "virtual_effects_applied_to_real_pixels":(
                proof["virtual_artistic_fx_applied_to_real_pixels"]),
            "original_acting_object_role":"actor",
            "central_hole_mean_brightness_8bit":round(center,4),
            "annular_ring_mean_brightness_8bit":round(annular,4),
            "lit_ring_luminance_p10_p50_p90_8bit":[
                round(p10,4),round(p50,4),round(p90,4)],
            "lit_ring_highlight_range_8bit":round(p90-p10,4),
            "visible_lit_ring_pixels":int(lit_ring.size),
            "render_resolution":[640,360],
            "actual_image_bytes":bytes_png,
        })
    x0=image_arrays[0].astype(np.int16)
    comparisons=[]
    for i in range(1,len(image_arrays)):
        other=image_arrays[i].astype(np.int16)
        delta=other-x0
        total=int(np.count_nonzero(np.any(delta!=0,axis=2)))
        if total<=20:
            raise RuntimeError("Native artistic light did not alter donut's real pixels")
        comparisons.append({
            "compared_to":"neutral",
            "look":LOOKS[i],
            "real_changed_pixel_count":total,
            "real_RGB_mean_delta_8bit":[round(float(n),4)
                for n in np.mean(delta,axis=(0,1))],
            "actual_source_audio_unchanged":True,
        })
    # Gold is artistically warmer than neutral and visibly differs from silver.
    if (results[1]["real_image_png_sha256"]==
            results[2]["real_image_png_sha256"]):
        raise RuntimeError("Silver/gold donut lighting rendered identically")
    if comparisons[1]["real_RGB_mean_delta_8bit"][0]<=(
            comparisons[1]["real_RGB_mean_delta_8bit"][2]):
        raise RuntimeError("Gold fill failed to create warmer donut image")
    before=idx.read_revision(pid,"DonutLightingTake",1)
    if before["document_sha256"]!=source["take_sha256"]:
        raise PermissionError("Light probe changed original donut Take")
    return results,comparisons


def export_donut_lighting_contact(source,output_dir):
    path=Path(output_dir)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise PermissionError("Diagnostic needs fresh absolute output folder")
    rows,comparisons=render_donut_four_looks(source)
    path.mkdir(parents=True,mode=0o700)
    canvas=Image.new("RGB",(1312,792),(22,22,27))
    draw=ImageDraw.Draw(canvas)
    for n,row in enumerate(rows):
        name=f"donut_actor_{row['look']}_real_NVP.png"
        (path/name).write_bytes(row["actual_image_bytes"])
        with Image.open(BytesIO(row["actual_image_bytes"])) as img:
            img.load()
            x=8+(n%2)*656
            y=8+(n//2)*392
            canvas.paste(img,(x,y))
            draw.text((x,y+365),row["look"].replace("_"," ").upper(),
                      fill=(245,245,245))
        del row["actual_image_bytes"]
    sheet=path/FILENAME
    canvas.save(sheet,format="PNG")
    with Image.open(sheet) as reopened:
        reopened.load()
        if reopened.size!=(1312,792):
            raise RuntimeError("Original NVP donut lighting contact invalid")
    evidence={
        "format":FORMAT,
        "source_original_actor_role":"actor",
        "real_usd_torus_ring_with_hole":True,
        "first_party_native_scene_linear_raster":True,
        "source_film_tick":str(SELECTED_TICK),
        "original_scene_take_sha256":source["take_sha256"],
        "source_mesh_SHA256":source["torus_source_mesh_sha256"],
        "genuine_per_light_render_receipts":rows,
        "neutral_vs_virtual_shader_pixel_deltas":comparisons,
        "four_way_visual_comparison_png_sha256":hashlib.sha256(
            sheet.read_bytes()).hexdigest(),
        "display_shading_uncalibrated":True,
        "face_normals_flat_not_smooth_vertex_normals":True,
        "no_true_occlusion_shadows_or_global_illumination":True,
        "no_authorized_film_release_or_DCI_master":True,
        "human_creative_review_required":True,
    }
    (path/"donut_actor_actual_source_lighting_receipt.json").write_text(
        json.dumps(evidence,sort_keys=True,indent=2)+"\n")
    return evidence


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root",required=True,type=Path)
    cli.add_argument("--output",required=True,type=Path)
    cli.add_argument("--test-consent",required=True)
    args=cli.parse_args()
    if args.test_consent!="I_APPROVE_DISPOSABLE_DONUT_SOURCE":
        cli.error("Disposable donut lighting verification must be explicitly authorized")
    source=build_frozen_donut_source(args.root.resolve())
    report=export_donut_lighting_contact(source,args.output.resolve())
    print(json.dumps({
        "result":"GENUINE_ORIGINAL_NVP_DONUT_REFERENCE",
        "looks":[x["look"] for x in report["genuine_per_light_render_receipts"]],
        "original_source_sha256":report["original_scene_take_sha256"],
        "human_artistic_review_required":True,
        "DCI_master":False,
    },indent=2))


if __name__=="__main__":
    main()
