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
                           native_take=None,look_ref=None,
                           material_context_probe="dual"):
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
        len(camera_path)>256 or
        material_context_probe not in ("dual","mtlx_only")):
        raise ValueError("Unsafe independent renderer acceptance request")
    if (renderer=="Storm" and not require_gpu) or (
            renderer=="Embree" and require_gpu):
        raise ValueError("Hydra renderer and GPU admission must agree")
    if material_context_probe=="mtlx_only" and (renderer!="Storm" or native_take is not None or look_ref is not None):
        raise ValueError("MaterialX-only audit requires isolated Storm source without look/Take")
    if native_take is not None:
        if (type(native_take) is not dict or
            set(native_take)!={"take_id","take_sha256","tick"} or
            type(native_take["tick"]) is not int or
            native_take["tick"]!=0):
            raise ValueError("Independent paired source comparison requires exact original tick zero")
        _id(native_take["take_id"],"frozen source comparison Take")
        _sha(native_take["take_sha256"])
    record,stage=OpenUSDSceneBridge(index).open(pid,scene_id,scene_revision)
    look_evidence=None
    if look_ref is not None:
        if (native_take is not None or type(look_ref) is not dict or
            set(look_ref)!={"look_id","revision","document_sha256"}):
            raise ValueError(
                "Derived look Hydra must not be compared with an ungraded CPU source")
        _id(look_ref["look_id"],"source-bound look")
        _sha(look_ref["document_sha256"])
        from backend.nvp_wo2_presentation_look import OriginalSceneLook
        look=OriginalSceneLook(index).open(
            pid,look_ref["look_id"],look_ref["revision"],
            scene_sha256=record["document_sha256"])
        if look["look_document_sha256"]!=look_ref["document_sha256"]:
            raise PermissionError("Derived Hydra look changed since creator approval")
        from backend.nvp_wo2_derived_usd_look import derived_look_stage
        stage,look_evidence=derived_look_stage(stage,record,look["look"])
    if record["data"]["prim_roles"].get(camera_path)!="camera":
        raise PermissionError("Hydra probe requires an original USD camera")
    descriptors=_original_texture_descriptors(index,pid,record)
    usdrecord=shutil.which("usdrecord")
    base={
        "format":FORMAT,"scene_document_sha256":record["document_sha256"],
        "camera_path":camera_path,"renderer":renderer,
        "material_context_probe":material_context_probe,
        "original_modified":False,"ffmpeg_used":False,
        "hydra_shader_parity_accepted":False,
        "physical_display_calibrated":False,
        "physical_gpu_accepted":False,
        "real_independent_frame_rendered":False,
        "source_bound_presentation_sha256":(
            look_ref["document_sha256"] if look_ref is not None else None),
        "derived_look_scope":look_evidence,
        "approved_texture_sha256":sorted(
            d["sha256"] for d in descriptors),
    }
    if not usdrecord:
        return {**base,"status":"HYDRA_BINARY_UNAVAILABLE"}
    # The discovered native tool is not creator/model-supplied code. Bind
    # exact executable essence for this probe: its bytes must not change
    # while an independent image is produced.
    native_tool=Path(usdrecord).resolve(strict=True)
    if not native_tool.is_file():
        raise PermissionError("Independent renderer must be a real native tool")
    native_tool_sha=sha256(native_tool.read_bytes()).hexdigest()
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
    if material_context_probe=="mtlx_only" and not descriptors:
        raise RuntimeError("MaterialX-only audit requires actual indexed textures")
    original_layer=stage.GetRootLayer().ExportToString()
    try:
        with source_ctx as (copy,evidence):
            if material_context_probe=="mtlx_only":
                if evidence.get("derived_probe_only") is not True:
                    raise RuntimeError("MaterialX-only isolation forbidden on source stage")
                from backend.nvp_wo3_materialx_integrity import (
                    isolate_materialx_only_on_derived_stage)
                isolate_materialx_only_on_derived_stage(copy)
            with TemporaryDirectory(prefix="nvp-wo2-hydra-") as directory:
                root=Path(directory)
                scene_path=root/"approved_derived_scene.usda"
                image_path=root/"independent_hydra.png"
                if not copy.GetRootLayer().Export(str(scene_path)):
                    raise RuntimeError("Approved USD probe layer export failed")
                args=[str(native_tool),"--camera",camera_path,
                      "--renderer",renderer,"--imageWidth",str(width),
                      "--colorCorrectionMode","disabled","--abortOnError"]
                if not require_gpu:args.append("--disableGpu")
                args.extend((str(scene_path),str(image_path)))
                began=time.monotonic()
                try:
                    run=subprocess.run(
                        # Renderer diagnostics are untrusted and may be
                        # arbitrarily large. Do not hold stdout/stderr in
                        # memory or surface private source paths to callers.
                        args,cwd=root,stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=timeout_seconds,check=False)
                except subprocess.TimeoutExpired:
                    return {**base,"status":"HYDRA_RENDER_TIMEOUT",
                            "requested_gpu":bool(require_gpu)}
                elapsed=round(time.monotonic()-began,4)
                if sha256(native_tool.read_bytes()).hexdigest()!=native_tool_sha:
                    raise RuntimeError("Independent renderer binary changed during run")
                # No symlink, arbitrary renderer output path or unbounded
                # decompression input becomes evidence for a source render.
                if (run.returncode!=0 or not image_path.is_file() or
                    image_path.is_symlink() or
                    not 0<image_path.stat().st_size<=64*1024*1024):
                    return {**base,"status":"HYDRA_RENDER_FAILED",
                            "requested_gpu":bool(require_gpu),
                            "render_wall_seconds":elapsed,
                            "exit_code":run.returncode,
                            "untrusted_or_missing_output":True}
                from PIL import Image,ImageStat
                with Image.open(image_path) as result:
                    if (result.width>width*4 or result.height>width*4 or
                        result.width<1 or result.height<1):
                        raise RuntimeError("Independent rendered frame size out of bounds")
                    result.load()
                    w,h=result.size
                    rendered=result.convert("RGB")
                    rgb=rendered.tobytes()
                    # Actual center-surface image pixels, not shader metadata
                    # or expected source RGB. No color-space calibration is
                    # inferred from these unprofiled RGB8 output samples.
                    bounds=(3*w//8,3*h//8,max(3*w//8+1,5*w//8),
                            max(3*h//8+1,5*h//8))
                    patch=rendered.crop(bounds)
                    center_rgb=[round(v,3) for v in ImageStat.Stat(patch).mean]
                    center_pixels=patch.width*patch.height
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
                    "rendered_center_patch_mean_rgb8":center_rgb,
                    "rendered_center_patch_pixels":center_pixels,
                    "renderer_executable_sha256":native_tool_sha,
                    "derived_source_scope":True,
                    "original_modified":False,
                }
    finally:
        if stage.GetRootLayer().ExportToString()!=original_layer:
            raise RuntimeError("Independent renderer modified original scene layer")
