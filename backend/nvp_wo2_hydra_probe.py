"""WO2 independent native Hydra screenshot evidence for a frozen OpenUSD Take.

The external executable is a fixed discovered local tool, not a model/JS
provided command. Source images resolve only inside the ephemeral SHA-verified
MaterialX probe. Never overwrites FilmIndex originals or Digital Takes.
A rendered image is evidence, not automatic shader/display parity acceptance.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import time

from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_wo2_materialx_resolver import resolved_materialx_probe

FORMAT="nvp.wo2.independent_hydra_frame_receipt.v1"
RENDERERS=frozenset(("Storm","Embree"))

def _original_texture_descriptors(index,pid,scene):
    result={}
    assets=OpenUSDAssetRegistry(index)
    for binding in scene["data"].get("asset_bindings",[]):
        record,_=assets.open(pid,binding["asset_id"],
                             binding["asset_revision"])
        if record["document_sha256"]!=binding["asset_document_sha256"]:
            raise RuntimeError("Hydra source mesh diverged from frozen scene")
        material=record["data"].get("preview_material") or {}
        for desc in ([material["texture"]] if "texture" in material else []):
            result[desc["sha256"]]=desc
        for desc in material.get("pbr_maps",{}).values():
            result[desc["sha256"]]=desc
    for rig in scene["data"].get("skeleton_rigs",[]):
        if rig.get("texture"):
            desc=rig["texture"]
            result[desc["sha256"]]=desc
        for desc in rig.get("pbr_maps",{}).values():
            result[desc["sha256"]]=desc
    return list(result.values())


def capture_hydra_evidence(index:FilmIndex,pid,scene_id,scene_revision,*,
                           camera_path,renderer="Embree",width=256,
                           timeout_seconds=90,require_gpu=False,
                           native_take=None):
    if not isinstance(index,FilmIndex):
        raise TypeError("Original FilmIndex required")
    _require_pid(pid)
    _id(scene_id,"frozen original scene")
    if (type(scene_revision) is not int or scene_revision<1 or
        renderer not in RENDERERS or
        type(width) is not int or not 64<=width<=1024 or
        type(timeout_seconds) is not int or
        not 5<=timeout_seconds<=180 or
        type(camera_path) is not str or
        not camera_path.startswith("/World/") or
        len(camera_path)>256):
        raise ValueError("Unsafe independent renderer acceptance request")
    if (renderer=="Storm" and not require_gpu) or (
            renderer=="Embree" and require_gpu):
        raise ValueError("Hydra renderer and GPU admission must agree")
    if native_take is not None:
        if (type(native_take) is not dict or
            set(native_take)!={"take_id","take_sha256","tick"} or
            type(native_take["tick"]) is not int or
            native_take["tick"]!=0):
            raise ValueError("Independent paired source comparison requires exact original tick zero")
        _id(native_take["take_id"],"frozen source comparison Take")
        _sha(native_take["take_sha256"])
    record,stage=OpenUSDSceneBridge(index).open(pid,scene_id,scene_revision)
    if record["data"]["prim_roles"].get(camera_path)!="camera":
        raise PermissionError("Hydra probe requires an original USD camera")
    descriptors=_original_texture_descriptors(index,pid,record)
    usdrecord=shutil.which("usdrecord")
    base={
        "format":FORMAT,"scene_document_sha256":record["document_sha256"],
        "camera_path":camera_path,"renderer":renderer,
        "original_modified":False,"ffmpeg_used":False,
        "hydra_shader_parity_accepted":False,
        "physical_display_calibrated":False,
        "physical_gpu_accepted":False,
        "real_independent_frame_rendered":False,
        "approved_texture_sha256":sorted(
            d["sha256"] for d in descriptors),
    }
    if not usdrecord:
        return {**base,"status":"HYDRA_BINARY_UNAVAILABLE"}
    from pxr import UsdGeom
    camera=UsdGeom.Camera(stage.GetPrimAtPath(camera_path))
    if not camera:
        raise RuntimeError("Original USD camera schema not authored")
    # Even an untextured scene goes through independent source re-verification;
    # textured scenes use the finite approved source resolver only.
    from contextlib import nullcontext
    source_ctx=(resolved_materialx_probe(index,pid,stage,descriptors)
                if descriptors else nullcontext((stage,{
                    "original_layer_mutated":False})))
    original_layer=stage.GetRootLayer().ExportToString()
    try:
        with source_ctx as (copy,evidence):
            with TemporaryDirectory(prefix="nvp-wo2-hydra-") as directory:
                root=Path(directory)
                scene_path=root/"approved_derived_scene.usda"
                image_path=root/"independent_hydra.png"
                if not copy.GetRootLayer().Export(str(scene_path)):
                    raise RuntimeError("Approved USD probe layer export failed")
                args=[usdrecord,"--camera",camera_path,
                      "--renderer",renderer,"--imageWidth",str(width),
                      "--colorCorrectionMode","disabled","--abortOnError"]
                if not require_gpu:args.append("--disableGpu")
                args.extend((str(scene_path),str(image_path)))
                began=time.monotonic()
                try:
                    run=subprocess.run(
                        args,cwd=root,capture_output=True,text=True,
                        timeout=timeout_seconds,check=False)
                except subprocess.TimeoutExpired:
                    return {**base,"status":"HYDRA_RENDER_TIMEOUT",
                            "requested_gpu":bool(require_gpu)}
                elapsed=round(time.monotonic()-began,4)
                if run.returncode!=0 or not image_path.is_file():
                    return {**base,"status":"HYDRA_RENDER_FAILED",
                            "requested_gpu":bool(require_gpu),
                            "render_wall_seconds":elapsed,
                            "exit_code":run.returncode,
                            "stderr_tail":(run.stderr or "")[-600:]}
                from PIL import Image
                with Image.open(image_path) as result:
                    if (result.width>width*4 or result.height>width*4 or
                        result.width<1 or result.height<1):
                        raise RuntimeError("Independent rendered frame size out of bounds")
                    result.load()
                    w,h=result.size
                    rgb=result.convert("RGB").tobytes()
                comparison=None
                if native_take is not None:
                    from backend.nvp_native_scene_linear_raster import (
                        NativeSceneLinearRaster)
                    import numpy as np
                    native,source_receipt=NativeSceneLinearRaster(index).render(
                        pid,native_take["take_id"],
                        native_take["take_sha256"],
                        tick=0,camera_path=camera_path)
                    if source_receipt["scene_document_sha256"]!=(
                            record["document_sha256"]):
                        raise PermissionError(
                            "Independent Hydra frame source differs from original frozen Take")
                    if (native.shape[0]!=h or native.shape[1]!=w or
                        native.shape[-1]<3):
                        comparison={
                            "status":"DIMENSIONS_DIFFER",
                            "native_height":int(native.shape[0]),
                            "native_width":int(native.shape[1]),
                            "hydra_height":h,"hydra_width":w,
                            "scene_linear_hydra_parity_proven":False,
                        }
                    else:
                        from backend.nvp_wo2_renderer_comparison import (
                            compare_rendered_rgb)
                        linear=np.clip(native[:,:,:3],0.,1.)
                        srgb=np.where(
                            linear<=.0031308,12.92*linear,
                            1.055*np.power(linear,1./2.4)-.055)
                        native_bytes=np.rint(np.clip(
                            srgb*255.,0.,255.)).astype(np.uint8).tobytes()
                        import json
                        comparison=compare_rendered_rgb(
                            native_rgb=native_bytes,
                            independent_rgb=rgb,width=w,height=h,
                            source_scene_sha256=record["document_sha256"],
                            native_receipt_sha256=sha256(
                                json.dumps(source_receipt,sort_keys=True,
                                    separators=(",",":")).encode()).hexdigest(),
                            independent_receipt_sha256=sha256(
                                (str(renderer)+str(width)+camera_path+
                                 sha256(rgb).hexdigest()).encode()).hexdigest())
                return {**base,
                    "comparison":comparison,
                    "status":"HYDRA_FRAME_RENDERED",
                    "real_independent_frame_rendered":True,
                    "requested_gpu":bool(require_gpu),
                    "render_wall_seconds":elapsed,
                    "rendered_width":w,"rendered_height":h,
                    "rendered_rgb_sha256":sha256(rgb).hexdigest(),
                    "rendered_rgb_mean":round(sum(rgb)/len(rgb),4),
                    "renderer_executable_sha256":sha256(
                        Path(usdrecord).read_bytes()).hexdigest(),
                    "derived_source_scope":True,
                    "original_modified":False,
                }
    finally:
        if stage.GetRootLayer().ExportToString()!=original_layer:
            raise RuntimeError("Independent renderer modified original scene layer")
