"""P1-B/C: genuine TWO-frame imported GLB face+rig native Blender/Cycles audit.

A genuine glTF binary (not a cube replacement) is registered as immutable
GLB bytes, converted to canonical ActorID/OpenUSD, frozen with recorded PCM,
then rendered twice through the actual SHA-pinned, OS-contained NVP Blender
worker. Checks native source mesh/shape, pixel/colour output, image diversity,
original material provenance, unchanged Take and durable worker receipts.
This synthetic *minimal* GLB fixture proves mechanics, not actor artistry,
redistribution clearance, realistic face animation or feature-length scale.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys

from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor, sha_file
from backend.nvp_character_assets import CharacterAssets
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex
from backend.nvp_int02_cycles_renderer import static_composed_usd
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_p1bc_actor_registry import ActorDirectory, ActorDialogueDirector
from backend.nvp_p1bc_scene_cast import NativeActorSceneCasting
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_final_2d_native import _png_header
from tests.test_nvp_p1bc_glb_scene_native import original_rigged_glb

FORMAT="nvp.p1bc.genuine_glb_native_two_frame_cycles.v1"
T=TICKS_PER_SECOND


def _write_once(folder, name, content):
    path=folder/name
    with path.open("xb") as fd:
        fd.write(content)
        fd.flush()
        os.fsync(fd.fileno())
    return sha256(content).hexdigest()


def _source(index, pid):
    directory=ActorDirectory(index,verify_director_action=lambda event,scope:
        event=="author_approved" and scope["operation"]=="nvp.p1bc.register_actor.v1")
    directory.register(pid,"ActorLead",display_name="Real GLB mesh actor",
                       creator_event="author_approved")
    original=original_rigged_glb()
    registered=CharacterAssets(index.studio).register(pid,original,"creator_owned")
    actor=NativeActorSceneCasting(index,verify_director_action=lambda event,scope:
        event=="author_approved" and scope["operation"]==
        "nvp.p1bc.native_actor_scene_cast.v1")
    scene=actor.publish(pid,"GenuineNativeScene",cast=[{
        "actor_id":"ActorLead","character_asset_id":registered["asset_id"],
        "position":[0.0,0.0,0.0],
        "motion_joint":"Bone000/Bone001","travel":0.4,
        "face_target":"jaw_open","face_strength":0.5,
    }],creator_event="author_approved")
    original_audio=RecordedSoundSources(index).publish(
        pid,"SourceVoice",[(1000).to_bytes(2,"little",signed=True)*48000])
    TemporalLedger(index).publish(pid,"SourceTimeline",[{
        "event_id":"Speech","event_kind":"dialogue","subject_id":"ActorLead",
        "start_tick":0,"end_tick":T,"source_id":"SourceVoice",
        "source_revision":1,
        "payload":{"usd_prim_path":"/World/Actor001","gain":1.0}
    }],duration_tick=2*T)
    capture=OpenUSDTakeCapture(index,verify_creator_action=lambda event,scope:
        event=="author_approved" and
        scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
    take=capture.freeze(pid,"SourceTake",scene_id="GenuineNativeScene",
                        scene_revision=1,timeline_id="SourceTimeline",
                        timeline_revision=1,sample_ticks=[0,T//2,T],
                        creator_event="author_approved")
    dialogue=ActorDialogueDirector(index,verify_director_action=lambda event,scope:
        event=="author_approved" and
        scope["operation"]=="nvp.p1bc.bind_original_dialogue.v1")
    dialogue.bind(pid,"OriginalVoice",actor_id="ActorLead",
                  take_id="SourceTake",event_id="Speech",
                  creator_event="author_approved")
    state=dialogue.at(pid,"OriginalVoice",1,T//2)
    if (state["native_facial_deformation_evaluated"] is not True or
        state["native_skin_deformation_evaluated"] is not True or
        state["dialogue_active"] is not True or
        state["voice_synthesized"] is not False):
        raise RuntimeError("Original face, body and recorded voice do not agree at Film Time")
    return registered,scene,take,state


def run(out:Path,blender:Path):
    if out.exists() or out.is_symlink():
        raise RuntimeError("Native two-frame evidence destination already exists")
    out.mkdir(parents=True)
    exe=blender.resolve()
    if not exe.is_file() or exe.is_symlink():
        raise RuntimeError("Genuine installed Blender executable missing")
    version=subprocess.run([str(exe),"-b","--version"],
                           capture_output=True,text=True,check=True,timeout=30)
    first=version.stdout.splitlines()[0]
    if not first.startswith("Blender "):
        raise RuntimeError("Genuine Blender version not verified")
    studio=Studio(out/"source_filming.sqlite3")
    pid=studio.create_project("P1-B/C genuine original GLB Cycles acceptance","")["id"]
    index=FilmIndex(studio)
    registered,scene,take,voice=_source(index,pid)
    original_take_sha=take["document_sha256"]
    original_glb_sha=registered["sha256"]
    if not original_glb_sha==sha256(original_rigged_glb()).hexdigest():
        raise RuntimeError("Genuine source GLB input was substituted")
    workspace=out/"supervised_blender_workers"
    sup=BlenderWorkerSupervisor(workspace,blender_executable=exe,
          blender_sha256=sha_file(exe),blender_version=first)
    script=Path(__file__).with_name("nvp_int02_cycles_frame_worker.py").resolve()
    scriptbytes=script.read_bytes()
    frames=[]
    from pxr import Sdf,Usd,UsdGeom
    from PIL import Image,ImageChops
    source_meshes=[]
    pictures=[]
    for n,tick in enumerate((0,T//2)):
        usd,optics,materials=static_composed_usd(
            index,pid,"SourceTake",original_take_sha,tick,
            camera_path="/World/Camera")
        if (len(materials)!=1 or
            materials[0]["prim_path"]!="/World/Actor001/Rig/CharacterMesh"):
            raise RuntimeError("Original imported GLB source PBR material absent")
        if not (.84<materials[0]["linear_diffuse_rgb"][0]<.86):
            raise RuntimeError("Original GLB's actual red PBR source was replaced")
        layer=Sdf.Layer.CreateAnonymous("p1bc_natively_deformed.usda")
        if not layer.ImportFromString(usd.decode("utf8")):
            raise RuntimeError("NVP cannot independently reopen frozen deformed USD")
        reopened=Usd.Stage.Open(layer)
        mesh=reopened.GetPrimAtPath("/World/Actor001/Rig/CharacterMesh")
        if (not mesh.IsA(UsdGeom.Mesh) or mesh.GetProperty("skel:skeleton")):
            raise RuntimeError("Cycles input still has a double-binding or lacks native mesh")
        points=[list(v) for v in UsdGeom.Mesh(mesh).GetPointsAttr().Get()]
        if len(points)!=3:
            raise RuntimeError("Blender source is not the real original 3-vertex GLB mesh")
        source_meshes.append(points)
        jobid="P1BC_RealGLBActorFrame"+str(n)
        work=workspace/jobid
        work.mkdir()
        ssha=_write_once(work,"source.usda",usd)
        script_sha=_write_once(work,"render.py",scriptbytes)
        plan={
            "format":"nvp.int02.cycles.frame_plan.v1",
            "usd_file":"source.usda","usd_sha256":ssha,
            "camera_path":"/World/Camera","source_tick":tick,
            "width":1920,"height":1080,"samples":64,"renderer":"CYCLES",
            "actor_paths":["/World/Actor001"],"light_paths":["/World/Key"],
            "camera_focal_length_mm":optics["camera_focal_length_mm"],
            "camera_sensor_width_mm":optics["camera_sensor_width_mm"],
            "camera_sensor_height_mm":optics["camera_sensor_height_mm"],
            "material_bindings":materials,
        }
        planbytes=json.dumps(plan,sort_keys=True,separators=(",",":")).encode("ascii")
        plan_sha=_write_once(work,"plan.json",planbytes)
        op=BlenderOperation(
            job_id=jobid,script="render.py",script_sha256=script_sha,
            inputs={"source.usda":ssha,"plan.json":plan_sha},
            outputs={"frame.png":"png","audit.json":"json_audit"},
            arguments={"--plan":"plan.json","--output":"frame.png",
                       "--audit":"audit.json"},
            timeout_seconds=900,memory_limit_mb=8192,
            require_linux_cgroup_v2=False)
        result=sup.run(op)
        if result["state"]!="SUCCEEDED":
            raise RuntimeError("Genuine native skinned GLB Cycles worker failed: "+str(result))
        verified=sup.verify_completed(jobid)
        png=(work/"frame.png").read_bytes()
        audit=json.loads((work/"audit.json").read_text("utf8"))
        if (_png_header(png)!=(1920,1080) or
            verified["outputs"]["frame.png"]["sha256"]!=sha256(png).hexdigest() or
            audit.get("render_engine")!="CYCLES" or
            audit.get("source_usd_sha256")!=ssha or
            audit.get("source_material_bindings_verified") is not True or
            audit.get("source_material_count")!=1 or
            audit.get("original_actor_geometry_verified") is not True or
            audit.get("authored_lights_verified") is not True or
            audit.get("cycles_samples")!=64):
            raise RuntimeError("Original source/native Blender Cycles SHA/PBR/actor/light audit failed")
        with Image.open(BytesIO(png)) as img:
            rgb=img.convert("RGB")
            coloured=sum(1 for r,g,b in rgb.getdata()
                         if r>g+18 and r>b+18 and r>60)
            pictures.append(rgb.copy())
        if coloured<700:
            raise RuntimeError("Genuine GLB actor not visibly red in Cycles picture: "+
                               str(coloured)+" pixels")
        frames.append({
            "source_tick":tick,"usd_sha256":ssha,
            "cycles_png_sha256":sha256(png).hexdigest(),
            "source_material_sha256":sha256(json.dumps(
                materials,sort_keys=True,separators=(",",":")).encode("ascii")).hexdigest(),
            "red_source_actor_pixels":coloured,
            "worker_job_id":jobid,"worker_state":verified["state"],
            "native_blender_audit_sha256":sha_file(work/"audit.json"),
            "authored_actor_geometry_verified":True,
        })
    delta=source_meshes[1][0][0]-source_meshes[0][0][0]
    face=source_meshes[1][0][2]-source_meshes[0][0][2]
    if not .195<delta<.205 or not .045<face<.055:
        raise RuntimeError("NVP original GLB joint AND face morph have not animated correctly")
    image_delta=ImageChops.difference(pictures[0],pictures[1])
    changed=sum(1 for p in image_delta.convert("L").getdata() if p>22)
    if changed<700:
        raise RuntimeError("Genuine Cycles pictures do not visibly change with GLB face+joint motion")
    reopened=FilmIndex(Studio(studio.db_path))
    if reopened.read_revision(pid,"SourceTake",1)["document_sha256"]!=original_take_sha:
        raise RuntimeError("Two-frame Cycles verification rewrote original Digital Take")
    record={
        "format":FORMAT,"status":"GENUINE_ORIGINAL_GLB_TWO_FRAME_CYCLES_VERIFIED",
        "source_head":os.environ.get("GITHUB_SHA","LOCAL_UNPINNED"),
        "project_id":pid,"real_original_glb_sha256":original_glb_sha,
        "registered_character_id":registered["asset_id"],
        "original_scene_sha256":scene["scene_document_sha256"],
        "original_take_sha256":original_take_sha,
        "original_dialogue_pcm_sha256":voice["original_pcm_sha256"],
        "face_and_joint_native_source_deformation":[delta,face],
        "cycles_changed_visible_pixels":changed,"frames":frames,
        "actual_blender_version":first,"native_blender_binary_sha256":sha_file(exe),
        "native_worker_os":sys.platform,
        "windows_native_kernel_job_execution":os.name=="nt",
        "linux_delegated_cgroup_release_accepted":False,
        "realistic_actor_performance_accepted":False,
        "synthetic_voice_generated":False,"phoneme_lipsync_accepted":False,
        "feature_length_render_accepted":False,
        "physical_owner_accepted":False,"production_install_approved":False,
    }
    (out/"receipt.json").write_text(json.dumps(record,sort_keys=True,indent=2)+"\n")
    print(json.dumps(record,sort_keys=True,indent=2))
    return record


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--blender",type=Path,required=True)
    args=ap.parse_args()
    run(args.out,args.blender)
