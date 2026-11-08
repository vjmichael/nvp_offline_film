"""FILM01: frozen ORIGINAL OpenUSD Take -> approved native Blender/Cycles worker.

Production architecture: source authority in FilmIndex; host stages a
first-party trusted Blender-side adapter + SHA-pinned immutable geometry,
exact 72 original actor poses and timing; the established Blender worker
manages native process, resource admission, cancellation and durable
worker journal. Scene/.blend/images are derived, never source truth.

CI fixture consent is a PRIVATE trusted-host callback, not a production
user authorization, and cannot be invoked by an untrusted model/browser.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image,ImageChops,ImageDraw

from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_film_index import FilmIndex
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_render_source_stage import _write_exclusive
from tools.nvp_film01_donut_light_probe import (
    build_frozen_donut_source,DONUT_PATH,BOX_PATH,SPHERE_PATH)

FORMAT="nvp.film01.blender.cycles.source_from_frozen_usd.v1"
RECEIPT="nvp.film01.blender.cycles.verified_72_frames.v1"
SOURCE_NAME="source.json"
SCRIPT_NAME="trusted_cycles_donut.py"
BATCH_FRAMES=72
RATE=24
STILLS=("neutral","silver","gold","fixed_summer_3pm")
KEY_FRAMES=(0,12,24,36,48,60)


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      allow_nan=False).encode("utf8")


def original_take_manifest(source):
    """Reopen the actual frozen OpenUSD Take/asset; never invent poses."""
    idx=source["index"]
    pid=source["project_id"]
    take=idx.read_revision(pid,"DonutLightingTake",1)
    scene=idx.read_revision(pid,"DonutLightingScene",1)
    asset=idx.read_revision(pid,"DonutMesh",1)
    geometry=source["geometry"]
    mesh={
        "points":asset["data"]["points"],
        "faces":asset["data"]["triangles"],
        "uvs":asset["data"]["face_uvs"],
    }
    original_sha=sha256(_json({
        "points":geometry["mesh_points"],
        "faces":geometry["mesh_triangles"],
        "uvs":geometry["mesh_face_uvs"]})).hexdigest()
    if (take["document_sha256"]!=source["take_sha256"] or
            scene["document_sha256"]!=source["scene_sha256"] or
            original_sha!=geometry["mesh_sha256"] or
            sha256(_json(mesh)).hexdigest()!=original_sha):
        raise PermissionError("Original torus/Take SHA does not match frozen FilmIndex")
    ids={row["path"]:row for row in scene["data"]["asset_bindings"]}
    for path,asset_id in ((DONUT_PATH,"DonutMesh"),(BOX_PATH,"BoxActorMesh"),
                          (SPHERE_PATH,"SphereActorMesh")):
        if (scene["data"]["prim_roles"].get(path)!="actor" or
                ids[path]["asset_id"]!=asset_id):
            raise PermissionError("Three actor role/source binding not trusted")
    tick_step=TICKS_PER_SECOND//RATE
    frames=[]
    native=FrozenSceneAV(idx,pid,"DonutLightingTake",
                         expected_take_sha256=source["take_sha256"],
                         listener_path="/World/Camera")
    try:
        for frame in range(BATCH_FRAMES):
            tick=frame*tick_step
            snapshot=native.snapshot(tick)
            positions={}
            by_path={obj["path"]:obj for obj in snapshot["objects"]}
            for name,path in (("donut",DONUT_PATH),("box",BOX_PATH),
                              ("sphere",SPHERE_PATH)):
                if by_path[path]["semantic_role"]!="actor":
                    raise RuntimeError("Trusted actor role unexpectedly changed")
                positions[name]=[
                    float(x) for x in by_path[path]["world_translation"]]
            frames.append({
                "frame_zero":frame,
                "film_tick":str(tick),
                "actors":positions,
                "frozen_scene_snapshot_sha256":snapshot["snapshot_sha256"],
            })
    finally:
        native.close()
    if (len(frames)!=BATCH_FRAMES or
            any(x["frame_zero"]!=i for i,x in enumerate(frames)) or
            not source["sphere_clearance_from_hole_m"]>.2):
        raise RuntimeError("Native original 3-second actor performance incomplete")
    # An actor may be ANY object: preserve the original semantics,
    # not an invented face/voice/character rig.
    return {
        "format":FORMAT,
        "performance_variant":source.get("performance_variant","baseline"),
        "source_take_sha256":source["take_sha256"],
        "scene_sha256":source["scene_sha256"],
        "torus_mesh_sha256":original_sha,
        "donut_vertices":geometry["mesh_points"],
        "donut_triangles":geometry["mesh_triangles"],
        "original_actor_roles":{
            "donut":"actor","box":"actor","sphere":"actor"},
        "source_object_paths":{
            "donut":DONUT_PATH,"box":BOX_PATH,"sphere":SPHERE_PATH},
        "frame_rate":RATE,
        "source_duration_seconds":3,
        "frames":frames,
        "renderer_requirement":"BLENDER_CYCLES_ONLY",
        "original_take_source_unchanged":True,
        "creator_approval_test_only":True,
    }


def stage_original_cycles_worker(source,supervisor,*,memory_mb=3072):
    if not isinstance(supervisor,BlenderWorkerSupervisor):
        raise TypeError("Existing native supervised Blender worker required")
    body=original_take_manifest(source)
    packet={"format":FORMAT,"source":body,
            "source_sha256":sha256(_json(body)).hexdigest()}
    job_id="film01cycles_"+body["source_take_sha256"][:18]
    job=supervisor.root/job_id
    job.mkdir(mode=0o700,exist_ok=False)
    script=Path(__file__).with_name("nvp_film01_blender_cycles_worker.py")
    if not script.is_file() or script.is_symlink():
        raise PermissionError("Trusted first-party Blender script is missing")
    _write_exclusive(job,SOURCE_NAME,_json(packet))
    _write_exclusive(job,SCRIPT_NAME,script.read_bytes())
    outputs={
        "scene.blend":"blend",
        "audit.json":"json_audit",
        **{f"{kind}_024.png":"png" for kind in STILLS},
    }
    operation=BlenderOperation(
        job_id=job_id,script=SCRIPT_NAME,
        script_sha256=sha_file(job/SCRIPT_NAME),
        inputs={SOURCE_NAME:sha_file(job/SOURCE_NAME)},
        outputs=outputs,
        arguments={
            "--manifest":SOURCE_NAME,
            "--output":"scene.blend",
            "--audit":"audit.json",
            "--out":"frames",
        },
        timeout_seconds=600,
        memory_limit_mb=memory_mb,
        gpu_memory_mb=0,require_linux_cgroup_v2=False,
    )
    supervisor._validate(operation)
    if original_take_manifest(source)!=body:
        raise RuntimeError("Original frozen Take changed during Blender staging")
    return operation,packet,job


def _actual_source_images(job,packet):
    data=json.loads((job/"audit.json").read_text("utf8"))
    take=packet["source"]
    if (data.get("passed") is not True or data.get("engine")!="CYCLES" or
            data.get("cycles_device")!="CPU" or
            data.get("original_scene_take_sha256")!=take["source_take_sha256"] or
            data.get("original_scene_document_sha256")!=take["scene_sha256"] or
            data.get("original_torus_mesh_sha256")!=take["torus_mesh_sha256"] or
            data.get("source_manifest_sha256")!=packet["source_sha256"] or
            data.get("blender_geometry_polygon_count")!=1008 or
            data.get("rendered_frames")!=BATCH_FRAMES or
            data.get("exact_frame_rate")!=RATE):
        raise RuntimeError("Blender Cycles audit does not match exact original source")
    rows=data["all_native_source_frames"]
    if len(rows)!=BATCH_FRAMES:
        raise RuntimeError("Blender failed to render full 72-frame original shot")
    movie=[]
    for i,row in enumerate(rows):
        path=job/"frames"/f"frame_{i:03d}.png"
        if (row["frame_zero"]!=i or
                row["source_film_tick"]!=take["frames"][i]["film_tick"] or
                row["original_scene_take_sha256"]!=take["source_take_sha256"] or
                not path.is_file() or path.is_symlink() or
                sha_file(path)!=row["image_sha256"] or
                path.stat().st_size!=row["image_bytes"]):
            raise PermissionError("Cycles original frame number/SHA/source altered")
        with Image.open(path) as img:
            img.load()
            if img.format!="PNG" or img.size!=(640,360):
                raise RuntimeError("Genuine Blender Cycles frame resolution invalid")
            movie.append(img.convert("RGB").copy())
    stills={}
    for kind in STILLS:
        filename=f"{kind}_024.png"
        path=job/filename
        if sha_file(path)!=data["artistic_light_still_sha256"][kind]:
            raise RuntimeError("Cycles lighting comparison source image changed")
        with Image.open(path) as image:
            image.load()
            if image.format!="PNG" or image.size!=(640,360):
                raise RuntimeError("Cycles light variant not a genuine Blender PNG")
            stills[kind]=image.convert("RGB").copy()
    if len(set(data["artistic_light_still_sha256"].values()))!=4:
        raise RuntimeError("Actual Blender lighting treatments produced no difference")
    if any(
        ImageChops.difference(stills["neutral"],stills[kind]).getbbox() is None
        for kind in STILLS if kind!="neutral"):
        raise RuntimeError("No visible source-dependent Cycles light difference")
    if data.get("cycles_traced_cast_shadows_enabled") is not True or (
            data.get("cycles_indirect_reflection_bounces_enabled") is not True):
        raise RuntimeError("Renderer lacks actual ray-traced Cycles lighting configuration")
    return movie,stills,data


def _review_outputs(dest,movie,stills,data,packet):
    dest.mkdir(mode=0o700,parents=True,exist_ok=False)
    # Actual Blender PNG bytes copied byte-for-byte; color/image hashes
    # are identical to source audited native worker files.
    job_frames=[]
    for i in range(BATCH_FRAMES):
        # Saving a GIF is *review encoding*, not scene rendering.
        job_frames.append(movie[i])
    gif=dest/"donut_box_sphere_REAL_BLENDER_CYCLES_3sec.gif"
    # Add a tiny diagnostic frame counter to GIF COPIES only, so
    # Pillow cannot merge visually identical adjacent frames and silently
    # shorten the 72-frame timing. Original Cycles PNGs stay untouched.
    gif_frames=[]
    for frame,image in enumerate(job_frames):
        marked=image.copy()
        ImageDraw.Draw(marked).text(
            (8,8),f"Original USD / Cycles frame {frame:02d}",
            fill=(250,250,250))
        gif_frames.append(marked.quantize(colors=256))
    # GIF delays are integer centiseconds: a uniform 42 ms rounds to
    # 40 ms in Pillow, shortening 72 frames from 3.00s to 2.88s.
    # Distribute 40/50 ms delays on the exact 24-fps time grid.
    gif_delays=[10*((((i+1)*100+RATE//2)//RATE)-
                    ((i*100+RATE//2)//RATE))
                for i in range(BATCH_FRAMES)]
    if sum(gif_delays)!=3000 or sorted(set(gif_delays))!=[40,50]:
        raise RuntimeError("GIF review timebase does not preserve 3-second film")
    gif_frames[0].save(
        gif,save_all=True,append_images=gif_frames[1:],
        duration=gif_delays,loop=0,optimize=False,disposal=2)
    with Image.open(gif) as verify:
        if verify.format!="GIF" or verify.n_frames!=BATCH_FRAMES:
            raise RuntimeError("Native Cycles review animation lost real frames")
        if sum((verify.seek(i) or verify.info["duration"])
               for i in range(BATCH_FRAMES))!=3000:
            raise RuntimeError("Native Cycles GIF did not preserve exact 3-second playback")
    contact=Image.new("RGB",(3*640+4*12,2*390+3*12),(24,24,29))
    pen=ImageDraw.Draw(contact)
    for i,n in enumerate(KEY_FRAMES):
        x=12+(i%3)*652;y=12+(i//3)*390
        contact.paste(movie[n],(x,y))
        pen.text((x,y+366),f"Blender Cycles  {n/RATE:.2f}s",fill=(240,242,246))
    contact.save(dest/"donut_box_sphere_REAL_CYCLES_six_frames.png",format="PNG")
    lights=Image.new("RGB",(2*640+3*12,2*390+3*12),(24,24,29))
    pen=ImageDraw.Draw(lights)
    for i,kind in enumerate(STILLS):
        x=12+(i%2)*652;y=12+(i//2)*390
        lights.paste(stills[kind],(x,y))
        pen.text((x,y+366),"CYCLES  "+kind.replace("_"," ").upper(),
                 fill=(240,242,246))
    lights.save(dest/"donut_REAL_CYCLES_four_lights.png",format="PNG")
    return {
        "movie_gif_sha256":sha_file(gif),
        "six_original_frame_contact_sha256":sha_file(
            dest/"donut_box_sphere_REAL_CYCLES_six_frames.png"),
        "four_real_light_variants_sha256":sha_file(
            dest/"donut_REAL_CYCLES_four_lights.png"),
        "authoritative_original_take_sha256":packet["source"]["source_take_sha256"],
        "all_72_real_Blender_Cycles_PNGs_rendered_and_reopened":True,
        "actual_ray_traced_Cycles_GI_and_reflection_bounces_enabled":True,
        "inter_object_reflections_visually_accepted":False,
        "cast_shadows_visually_accepted":False,
        "user_director_review_pending":True,
        "not_DCI_or_cinema_color_approved":True,
    }


def fixture(workspace,blender,*,ci_test_consent=False):
    root=Path(workspace).resolve()
    if root.exists() or root.is_symlink() or not ci_test_consent:
        raise PermissionError("Fresh disposable native test workspace and explicit test consent required")
    exe=Path(shutil.which(blender) or blender).resolve()
    if not exe.is_file():
        raise FileNotFoundError("Genuine installed Blender/Cycles binary required")
    version=subprocess.run(
        [str(exe),"-b","--version"],check=True,timeout=25,
        capture_output=True,text=True).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("Unexpected real Blender executable identity")
    root.mkdir(mode=0o700,parents=True)
    source=build_frozen_donut_source(
        root/"original_frozen_take",performance="director_retake_01")
    ledger=TaskLedger(root/"activity")
    worker=BlenderWorkerSupervisor(
        root/"native_blender_worker",blender_executable=exe,
        blender_sha256=sha_file(exe),blender_version=version,
        activity_ledger=ledger)
    op,packet,job=stage_original_cycles_worker(source,worker)
    approval_name="CI_ONLY_FROZEN_DONUT_CYCLES_"+op.job_id[-12:]
    test_approval_id=approval_name if ci_test_consent else ""
    def approval_check(approval_id,digest,document):
        operation=document.get("operation",{})
        # Production UI must use its own independent creator-presence
        # verifier. This fixture cannot mint a real approval.
        return (approval_id==approval_name and
                operation.get("inputs",{}).get(SOURCE_NAME)==
                    sha_file(job/SOURCE_NAME) and
                operation.get("script_sha256")==op.script_sha256 and
                operation.get("outputs")==op.outputs and
                original_take_manifest(source)==packet["source"])
    dispatcher=ApprovedBlenderDispatcher(
        worker,ledger,approval_check=approval_check)
    queued=dispatcher.enqueue(
        op,approval_id=test_approval_id,lane="standard")
    if not queued:
        raise RuntimeError("Trusted resource-admitted Blender job not queued")
    outcome=dispatcher.run_next()
    if not outcome or outcome.get("state")!="SUCCEEDED":
        raise RuntimeError(
            "Real externally supervised Blender/Cycles did not pass: "+
            str(outcome))
    recovered=worker.verify_completed(op.job_id)
    if recovered["state"]!="SUCCEEDED":
        raise RuntimeError("Existing native worker journal refused real Blender results")
    movie,lights,audit=_actual_source_images(job,packet)
    result=_review_outputs(root/"director_review",movie,lights,audit,packet)
    result.update({
        "format":RECEIPT,
        "real_supervised_blender_ran":True,
        "real_blender_version":version,
        "blender_executable_sha256":sha_file(exe),
        "first_party_script_sha256":op.script_sha256,
        "staged_original_source_file_sha256":sha_file(job/SOURCE_NAME),
        "worker_durable_result":recovered["state"],
        "approved_resource_ledger_task":outcome.get("task_id") or
            worker._activity_id(op.job_id),
        "actual_blend_sha256":sha_file(job/"scene.blend"),
        "original_frame_24_sha256":audit["all_native_source_frames"][24][
            "image_sha256"],
        "frame_count":BATCH_FRAMES,"fps":RATE,
        "source_original_take_modified":False,
        "real_creator_UI_approval_obtained":False,
    })
    dest=root/"director_review"
    # Copy only after native worker and ALL source pixels passed.
    shutil.copy2(job/"scene.blend",dest/"source_derived_Blender_Cycles_scene.blend")
    for name in STILLS:
        shutil.copy2(job/f"{name}_024.png",dest/f"{name}_024.png")
    (dest/"original_source_and_cycles_audit.json").write_text(
        json.dumps(audit,sort_keys=True,indent=2)+"\n",encoding="utf8")
    (dest/"verified_director_review_receipt.json").write_text(
        json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--blender",default="blender")
    parser.add_argument("--consent",required=True)
    args=parser.parse_args()
    if args.consent!="I_APPROVE_DISPOSABLE_ORIGINAL_BLENDER_CYCLES_TEST":
        parser.error("Requires explicit disposable CI Blender/film source approval")
    result=fixture(
        args.out.resolve(),args.blender,ci_test_consent=True)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
