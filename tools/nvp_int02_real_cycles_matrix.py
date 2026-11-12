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
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux
    stage=Usd.Stage.CreateNew(str(path))
    stage.SetTimeCodesPerSecond(24)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    UsdGeom.Xform.Define(stage,"/World")
    actor=UsdGeom.Cube.Define(stage,"/World/Actor")
    actor.GetSizeAttr().Set(2.0)
    actor.AddTranslateOp().Set(Gf.Vec3d(0,0,1.0))
    camera=UsdGeom.Camera.Define(stage,"/World/Camera")
    camera.GetFocalLengthAttr().Set(.5)
    camera.GetHorizontalApertureAttr().Set(.36)
    camera.AddTranslateOp().Set(Gf.Vec3d(0,-7.0,2.0))
    camera.AddRotateXYZOp().Set(Gf.Vec3f(90,0,0))
    light=UsdLux.SphereLight.Define(stage,"/World/Light")
    light.GetIntensityAttr().Set(3500.0)
    light.GetRadiusAttr().Set(.5)
    light.AddTranslateOp().Set(Gf.Vec3d(-3,-4,6))
    ground=UsdGeom.Mesh.Define(stage,"/World/Ground")
    ground.CreatePointsAttr([
        Gf.Vec3f(-6,-6,-.04),Gf.Vec3f(6,-6,-.04),
        Gf.Vec3f(6,6,-.04),Gf.Vec3f(-6,6,-.04)])
    ground.CreateFaceVertexCountsAttr([4])
    ground.CreateFaceVertexIndicesAttr([0,1,2,3])
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
    if (_png_header(image)!=(1920,1080) or
        audit.get("render_engine")!="CYCLES" or
        audit.get("source_usd_sha256")!=scene_sha or
        audit.get("cycles_samples")!=64 or
        audit.get("original_actor_geometry_verified") is not True or
        audit.get("authored_lights_verified") is not True or
        checked["outputs"]["frame.png"]["sha256"]!=sha256(image).hexdigest()):
        raise RuntimeError("Real Cycles USD import/frame/hash/camera/light contract failed")
    result={
        "format":FORMAT,"status":"ACTUAL_CYCLES_SOURCE_FRAME_VERIFIED",
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
