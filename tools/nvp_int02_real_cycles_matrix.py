"""INT-02C actual native Cycles acceptance: real OpenUSD + Blender under NVP supervisor.

This is a REAL renderer fixture. It creates a native USD Cube (actor), Camera,
UsdLux SphereLight and authored materials; Blender must import all of them,
render a 1920x1080/64-sample Cycles PNG, and publish a sha-verified audit.
The fixture uses genuine NVP BlenderWorkerSupervisor; on Windows, its worker
is created suspended and admitted into a kernel Job Object before execution.
Linux Github-hosted runners typically lack delegated systemd cgroups, so
their process-group/PDEATHSIG fixture is NOT release-grade tree custody.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from backend.nvp_blender_worker import BlenderWorkerSupervisor, BlenderOperation, sha_file
from backend.nvp_final_2d_native import _png_header

FORMAT="nvp.int02.real_cycles_native_matrix.v1"


def prepare_real_usd(path:Path):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade
    stage=Usd.Stage.CreateNew(str(path))
    stage.SetTimeCodesPerSecond(24)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    UsdGeom.Xform.Define(stage,"/World")
    actor=UsdGeom.Cube.Define(stage,"/World/Actor")
    actor.GetSizeAttr().Set(2.0)
    actor.AddTranslateOp().Set(Gf.Vec3d(0,0,1.0))
    # Explicit USD PreviewSurface color is essential: an unlit imported
    # cube can produce valid-but-black PNG even when Cycles exits 0.
    looks=UsdGeom.Scope.Define(stage,"/World/Looks")
    material=UsdShade.Material.Define(stage,"/World/Looks/ActorMat")
    shader=UsdShade.Shader.Define(stage,"/World/Looks/ActorMat/PBR")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(.9,.12,.04))
    shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(.45)
    material.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(),"surface")
    UsdShade.MaterialBindingAPI.Apply(actor.GetPrim()).Bind(material)
    camera=UsdGeom.Camera.Define(stage,"/World/Camera")
    camera.GetFocalLengthAttr().Set(.5)
    camera.GetHorizontalApertureAttr().Set(.36)
    camera.GetVerticalApertureAttr().Set(.2025)
    # The previous forward-looking fixture had an incorrect camera
    # orientation after native USD import: real Cycles PNG contained only
    # a tiny ground triangle and no visible original actor. An overhead
    # USD camera points down its canonical -Z axis and unambiguously
    # frames the actor and stage without post-import camera cheats.
    camera.AddTranslateOp().Set(Gf.Vec3d(0,0,8.0))
    light=UsdLux.SphereLight.Define(stage,"/World/Light")
    light.GetIntensityAttr().Set(3500.0)
    light.GetRadiusAttr().Set(.5)
    light.AddTranslateOp().Set(Gf.Vec3d(-3,-4,6))
    # Fill ensures actor and geometry remain visible without manufacturing
    # a post-render picture. This is a genuine native lighting opinion.
    fill=UsdLux.DomeLight.Define(stage,"/World/Fill")
    fill.GetIntensityAttr().Set(2.5)
    ground=UsdGeom.Mesh.Define(stage,"/World/Ground")
    ground.CreatePointsAttr([
        Gf.Vec3f(-6,-6,-.04),Gf.Vec3f(6,-6,-.04),
        Gf.Vec3f(6,6,-.04),Gf.Vec3f(-6,6,-.04)])
    ground.CreateFaceVertexCountsAttr([4])
    ground.CreateFaceVertexIndicesAttr([0,1,2,3])
    ground_mat=UsdShade.Material.Define(stage,"/World/Looks/GroundMat")
    ground_shader=UsdShade.Shader.Define(stage,"/World/Looks/GroundMat/PBR")
    ground_shader.CreateIdAttr("UsdPreviewSurface")
    ground_shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(.24,.27,.32))
    ground_shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(.8)
    ground_mat.CreateSurfaceOutput().ConnectToSource(
        ground_shader.ConnectableAPI(),"surface")
    UsdShade.MaterialBindingAPI.Apply(ground.GetPrim()).Bind(ground_mat)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Real OpenUSD scene could not be saved")
    original=path.read_bytes()
    if len(original)<100:
        raise RuntimeError("Native USD fixture is empty")
    reopened=Usd.Stage.Open(str(path))
    if reopened is None or not reopened.GetPrimAtPath("/World/Camera"):
        raise RuntimeError("Native USD cannot independently reopen")
    return sha256(original).hexdigest()


def run_real_imported_actor_cycles(out,supervisor,scriptbytes):
    """P1-B/C: genuine source GLB -> skinned face+joint -> 1920x1080 Cycles.

    Actual original binary mesh, weighted bones, facial shape, SHA-pinned
    source and kernel-supervised native Blender; no mocked image or proxy
    mannequin. This is a *test* fixture, not a creator-authorized film master.
    """
    import struct
    from io import BytesIO
    from tempfile import TemporaryDirectory
    from PIL import Image
    from pxr import Sdf,Usd,UsdGeom
    from backend.nvp_studio import Studio
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_character_assets import CharacterAssets
    from backend.nvp_p1bc_actor_registry import ActorDirectory
    from backend.nvp_p1bc_scene_cast import NativeActorSceneCasting
    from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
    from backend.nvp_openusd_take import OpenUSDTakeCapture
    from backend.nvp_int02_cycles_renderer import static_composed_usd
    from tests.test_nvp_p1bc_glb_scene_native import original_rigged_glb

    studio=Studio(out/"p1bc-native-character.sqlite")
    pid=studio.create_project("Actual USD Skinned Actor Cycles Matrix","")["id"]
    index=FilmIndex(studio)
    ActorDirectory(index,verify_director_action=lambda event,scope:
        event=="test_creator_yes").register(
        pid,"ActorLead",display_name="Actual GLB Lead",creator_event="test_creator_yes")
    original=CharacterAssets(studio).register(
        pid,original_rigged_glb(),"creator_owned")
    cast=[{"actor_id":"ActorLead","character_asset_id":original["asset_id"],
           "position":[0,0,0],"motion_joint":"Bone001","travel":0.4,
           "face_target":"jaw_open","face_strength":0.5}]
    published=NativeActorSceneCasting(
        index,verify_director_action=lambda event,scope:
        event=="test_creator_yes").publish(
        pid,"SceneRealImportedGLB",cast=cast,
        creator_event="test_creator_yes")
    # This acceptance uses an explicit original recorded PCM *fixture*
    # linked to the exact ActorID's dialogue event, never generated speech.
    from backend.nvp_data_av_source import RecordedSoundSources
    from backend.nvp_p1bc_actor_registry import ActorDialogueDirector
    recorded=RecordedSoundSources(index).publish(
        pid,"OriginalVoiceFixture",[struct.pack("<h",900)*48000])
    TemporalLedger(index).publish(pid,"RealActorTimeline",[{
        "event_id":"OriginalLine","event_kind":"dialogue",
        "subject_id":"ActorLead","start_tick":0,
        "end_tick":TICKS_PER_SECOND,
        "source_id":"OriginalVoiceFixture","source_revision":1,
        "payload":{"usd_prim_path":"/World/Actor001","gain":1.0},
    }],duration_tick=2*TICKS_PER_SECOND)
    take=OpenUSDTakeCapture(
        index,verify_creator_action=lambda event,scope:
        event=="test_creator_yes").freeze(
        pid,"RealActorTake",scene_id="SceneRealImportedGLB",
        scene_revision=1,timeline_id="RealActorTimeline",
        timeline_revision=1,sample_ticks=[0,TICKS_PER_SECOND],
        creator_event="test_creator_yes")
    director=ActorDialogueDirector(
        index,verify_director_action=lambda event,scope:
        event=="test_creator_yes")
    dialogue=director.bind(
        pid,"OriginalActorDialogue",actor_id="ActorLead",
        take_id="RealActorTake",event_id="OriginalLine",
        creator_event="test_creator_yes")
    spoken=director.at(
        pid,"OriginalActorDialogue",1,TICKS_PER_SECOND//2)
    if (spoken["dialogue_active"] is not True or
        spoken["native_facial_deformation_evaluated"] is not True or
        spoken["native_skin_deformation_evaluated"] is not True or
        spoken["original_glb_face_targets"][0]["name"]!="jaw_open"):
        raise RuntimeError("True GLB face+body performance not coupled to original recorded PCM")
    original_usd,_,_=static_composed_usd(
        index,pid,"RealActorTake",take["document_sha256"],0,
        camera_path="/World/Camera")
    middle_usd,optics,original_materials=static_composed_usd(
        index,pid,"RealActorTake",take["document_sha256"],
        TICKS_PER_SECOND//2,camera_path="/World/Camera")
    if (sha256(original_usd).digest()==sha256(middle_usd).digest() or
        len(original_materials)!=1 or
        original_materials[0]["prim_path"]!=
            "/World/Actor001/Rig/CharacterMesh"):
        raise RuntimeError("Actual imported GLB bone+facial animation not visible in USD")
    def reopen(text):
        layer=Sdf.Layer.CreateAnonymous()
        if not layer.ImportFromString(text.decode("utf8")):
            raise RuntimeError("Native imported actor USD source was not parseable")
        usd=Usd.Stage.Open(layer)
        mesh=usd.GetPrimAtPath("/World/Actor001/Rig/CharacterMesh")
        if not mesh.IsA(UsdGeom.Mesh) or mesh.GetProperty("skel:skeleton"):
            raise RuntimeError("Cycles source requires static evaluated actual GLB mesh")
        return [[float(x) for x in p]
                for p in UsdGeom.Mesh(mesh).GetPointsAttr().Get()]
    orig,mid=reopen(original_usd),reopen(middle_usd)
    if (len(orig)!=3 or len(mid)!=3 or
        abs((mid[0][0]-orig[0][0])-.2)>1e-4 or
        abs((mid[0][2]-orig[0][2])-.05)>1e-4):
        raise RuntimeError("Real source facial/bone deformation changed after Cycles baking")
    # Genuine two-moment native Cycles acceptance: independently render both
    # the original rest pose and the changed joint/face source pose. One real
    # PNG never proved time-varying animation, even if the USD bytes differed.
    frames=[]
    for index,(tick,usd_source) in enumerate((
            (0,original_usd),(TICKS_PER_SECOND//2,middle_usd))):
        job_id="int02_real_original_glb_actor_"+str(index).zfill(3)
        jobdir=supervisor.root/job_id
        if jobdir.exists() or jobdir.is_symlink():
            raise RuntimeError("Imported GLB Cycles picture sample cannot be replayed")
        jobdir.mkdir()
        stage_sha=sha256(usd_source).hexdigest()
        for name,value in (("source.usda",usd_source),
                           ("render.py",scriptbytes)):
            with (jobdir/name).open("xb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
        plan={"format":"nvp.int02.cycles.frame_plan.v1",
              "usd_file":"source.usda","usd_sha256":stage_sha,
              "camera_path":"/World/Camera","source_tick":tick,
              "width":1920,"height":1080,"samples":64,"renderer":"CYCLES",
              **optics,"material_bindings":original_materials,
              "actor_paths":["/World/Actor001"],"light_paths":["/World/Key"]}
        planbytes=json.dumps(plan,sort_keys=True,separators=(",",":")).encode("ascii")
        (jobdir/"plan.json").write_bytes(planbytes)
        op=BlenderOperation(
            job_id=job_id,script="render.py",
            script_sha256=sha256(scriptbytes).hexdigest(),
            inputs={"source.usda":stage_sha,
                    "plan.json":sha256(planbytes).hexdigest()},
            outputs={"frame.png":"png","audit.json":"json_audit"},
            arguments={"--plan":"plan.json","--output":"frame.png",
                       "--audit":"audit.json"},
            timeout_seconds=600,memory_limit_mb=8192,
            require_linux_cgroup_v2=False)
        state=supervisor.run(op)
        if state["state"]!="SUCCEEDED":
            raise RuntimeError(
                "Original imported GLB native Cycles frame "+str(tick)+
                " failed: "+str(state.get("error")))
        checked=supervisor.verify_completed(job_id)
        picture=(jobdir/"frame.png").read_bytes()
        audit=json.loads((jobdir/"audit.json").read_text("utf8"))
        if (_png_header(picture)!=(1920,1080) or
            audit.get("original_actor_geometry_verified") is not True or
            audit.get("source_material_bindings_verified") is not True or
            audit.get("source_material_count")!=1 or
            checked["outputs"]["frame.png"]["sha256"]!=sha256(picture).hexdigest() or
            audit.get("source_usd_sha256")!=stage_sha):
            raise RuntimeError("Actual GLB face+bone source was not preserved in Cycles")
        with Image.open(BytesIO(picture)) as rendered:
            rgb=rendered.convert("RGB")
            visible=sum(1 for red,green,blue in rgb.getdata()
                        if red>green+15 and red>blue+15 and red>50)
        if visible<100:
            raise RuntimeError(
                "Native Cycles image lacks original source GLB colored actor "+
                f"at tick {tick} ({visible} source pixels)")
        frames.append({"tick":tick,"usd_sha256":stage_sha,
                       "png_sha256":sha256(picture).hexdigest(),
                       "red_actor_pixels":visible})
    if (len(frames)!=2 or
        frames[0]["png_sha256"]==frames[1]["png_sha256"] or
        frames[0]["usd_sha256"]==frames[1]["usd_sha256"]):
        raise RuntimeError("Actual Blender/Cycles output did not change with source actor pose")
    image=(supervisor.root/"int02_real_original_glb_actor_001"/"frame.png").read_bytes()
    visible=frames[-1]["red_actor_pixels"]
    scene_sha=frames[-1]["usd_sha256"]
    receipt={
        "format":"nvp.p1bc.genuine_imported_glb_cycles.v1",
        "status":"ACTUAL_IMPORT_SKIN_FACE_CYCLES_VERIFIED",
        "original_glb_sha256":original["sha256"],
        "scene_document_sha256":published["scene_document_sha256"],
        "frozen_take_document_sha256":take["document_sha256"],
        "sample_tick":TICKS_PER_SECOND//2,
        "actual_skinned_vertices":len(mid),
        "native_source_bone_travel_m":.2,
        "native_source_face_morph_travel_m":.05,
        "flattened_source_usd_sha256":scene_sha,
        "cycles_frame_sha256":sha256(image).hexdigest(),
        "actual_original_actor_color_pixels":visible,
        "genuine_animated_cycles_frame_pair":frames,
        "original_dialogue_document_sha256":dialogue["document_sha256"],
        "original_recorded_pcm_document_sha256":recorded["document_sha256"],
        "actor_voice_at_source_tick_verified":True,
        "windows_job_supervision":os.name=="nt",
        "linux_release_cgroup_custody_accepted":False,
        "original_source_modified":False,
        "synthetic_voice_generated":False,
        "physical_performance_accepted":False,
    }
    (out/"real_imported_actor_cycles.json").write_text(
        json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    return receipt


def run_matrix(out:Path,blender:Path):
    if out.exists() or out.is_symlink():
        raise RuntimeError("Real native matrix refuses to overwrite an output")
    out.mkdir(parents=True)
    executable=blender.resolve()
    if executable.is_symlink() or not executable.is_file():
        raise RuntimeError("Genuine Blender executable must exist")
    version=subprocess.run([str(executable),"-b","--version"],
                           capture_output=True,text=True,timeout=20,check=True)
    first=version.stdout.splitlines()[0].strip()
    if not first.startswith("Blender "):
        raise RuntimeError("Native renderer is not Blender")
    workspace=out/"workers"
    sup=BlenderWorkerSupervisor(
        workspace,blender_executable=executable,
        blender_sha256=sha_file(executable),blender_version=first)
    script=Path(__file__).with_name("nvp_int02_cycles_frame_worker.py").resolve()
    scriptbytes=script.read_bytes()
    source=out/"scene.usda"
    scene_sha=prepare_real_usd(source)
    from pxr import Usd
    from backend.nvp_int02_usd_materials import source_preview_materials
    reopened=Usd.Stage.Open(str(source))
    original_materials=source_preview_materials(reopened,0)
    if (len(original_materials)!=2 or
        not any(x["prim_path"]=="/World/Actor" for x in original_materials)):
        raise RuntimeError("Native actor/ground original material bindings not available")
    job_id="int02_real_native_cycles_001"
    jobdir=workspace/job_id
    jobdir.mkdir()
    for name,content in [
        ("source.usda",source.read_bytes()),
        ("render.py",scriptbytes),
    ]:
        with (jobdir/name).open("xb") as fd:
            fd.write(content)
            fd.flush();os.fsync(fd.fileno())
    plan={
        "format":"nvp.int02.cycles.frame_plan.v1",
        "usd_file":"source.usda",
        "usd_sha256":scene_sha,
        "camera_path":"/World/Camera",
        "source_tick":0,
        "width":1920,"height":1080,"samples":64,
        "renderer":"CYCLES",
        "camera_focal_length_mm":50.0,
        "camera_sensor_width_mm":36.0,
        "camera_sensor_height_mm":20.25,
        "material_bindings":original_materials,
        "actor_paths":["/World/Actor"],
        "light_paths":["/World/Light"],
    }
    planbytes=json.dumps(plan,sort_keys=True,separators=(",",":")).encode("ascii")
    (jobdir/"plan.json").write_bytes(planbytes)
    op=BlenderOperation(
        job_id=job_id,script="render.py",script_sha256=sha256(scriptbytes).hexdigest(),
        inputs={"source.usda":scene_sha,"plan.json":sha256(planbytes).hexdigest()},
        outputs={"frame.png":"png","audit.json":"json_audit"},
        arguments={"--plan":"plan.json","--output":"frame.png","--audit":"audit.json"},
        timeout_seconds=600,memory_limit_mb=8192,
        require_linux_cgroup_v2=False)
    completed=sup.run(op)
    if completed["state"]!="SUCCEEDED":
        raise RuntimeError("Real supervised Blender Cycles render FAILED: "+
                           str(completed.get("error")))
    checked=sup.verify_completed(job_id)
    image=(jobdir/"frame.png").read_bytes()
    audit=json.loads((jobdir/"audit.json").read_text("utf8"))
    # A renderer can return a perfectly valid SHA-pinned all-black image.
    # This fixture's actor is specifically red/orange; require that the
    # imported material is visibly represented in the actual pixels.
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(image)) as displayed:
        rgb=displayed.convert("RGB")
        red_visible=sum(1 for red,green,blue in rgb.getdata()
                        if red>green+20 and red>blue+20 and red>60)
    if red_visible<2500:
        raise RuntimeError(
            "Real Cycles image lacks visible original USD actor material "+
            f"(only {red_visible} red actor pixels); SHA alone is insufficient")
    if (audit.get("source_material_bindings_verified") is not True or
        audit.get("source_material_count")!=2 or
        audit.get("source_material_bindings_sha256")!=sha256(
            json.dumps(original_materials,sort_keys=True,
                       separators=(",",":")).encode("ascii")).hexdigest()):
        raise RuntimeError("Blender Cycles original material conversion is not source-verified")
    if (audit.get("source_camera_unit_conversion_verified") is not True or
        audit.get("camera_focal_length_mm")!=50.0 or
        audit.get("camera_sensor_width_mm")!=36.0 or
        audit.get("camera_sensor_height_mm")!=20.25):
        raise RuntimeError("Cycles did not use the source camera's meter-aware real lens")
    if (_png_header(image)!=(1920,1080) or
        audit.get("render_engine")!="CYCLES" or
        audit.get("source_usd_sha256")!=scene_sha or
        audit.get("cycles_samples")!=64 or
        audit.get("original_actor_geometry_verified") is not True or
        audit.get("authored_lights_verified") is not True or
        checked["outputs"]["frame.png"]["sha256"]!=sha256(image).hexdigest()):
        raise RuntimeError("Real Cycles USD import/frame/hash/camera/light contract failed")
    # Same Windows Job / Linux native supervised worker boundary now
    # exercises a genuinely imported source GLB with facial+joint motion.
    real_actor=run_real_imported_actor_cycles(out,sup,scriptbytes)
    result={
        "format":FORMAT,"status":"ACTUAL_CYCLES_SOURCE_FRAME_VERIFIED",
        "actual_imported_glb_actor":real_actor,
        "actual_blender_version":first,
        "actual_blender_binary_sha256":sha_file(executable),
        "source_usd_sha256":scene_sha,
        "cycles_png_sha256":sha256(image).hexdigest(),
        "worker_job_state":checked["state"],
        "native_worker_os":sys.platform,
        "windows_kernel_job_execution":os.name=="nt",
        "linux_release_tree_custody_accepted":False,
        "full_720_frame_native_film_accepted":False,
        "NSIS_upgrade_accepted":False,
        "physical_owner_accepted":False,
    }
    (out/"receipt.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--blender",required=True,type=Path)
    args=ap.parse_args()
    run_matrix(args.out,args.blender)
