"""INT-02C immutable USD PreviewSurface material bridge for native Cycles.

Blender's USD importer may drop the original authored material binding on
typed USD geometry. The NVP trusted host reads the actual composed OpenUSD
material bindings at exact source Film Time. Only bounded, constant-color
UsdPreviewSurface values are supported; connected textures, material graphs,
MaterialX and unsupported render contexts FAIL CLOSED pending specialist
conversion. This never invents a new look or recolors a final raster.
"""
from __future__ import annotations

import math

FORMAT="nvp.int02.native_preview_material_bindings.v1"
MAX_BINDINGS=128


def source_preview_materials(stage,tick):
    from pxr import Usd,UsdGeom,UsdShade
    if not stage:
        raise RuntimeError("Original composed native USD source required")
    if type(tick) is not int or tick<0:
        raise ValueError("Exact source Film Time required")
    result=[]
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Gprim):
            continue
        path=str(prim.GetPath())
        if not path.startswith("/World/") or len(path)>240:
            raise RuntimeError("Unscoped USD geometry material")
        bound,relation=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if not bound:
            raise RuntimeError("Native Cycles cannot invent an unbound source material for "+path)
        shader,name,shader_type=bound.ComputeSurfaceSource()
        if not shader or str(shader.GetIdAttr().Get())!="UsdPreviewSurface":
            raise RuntimeError("Unsupported native USD material network; no color fallback")
        values={}
        for field in ("diffuseColor","roughness"):
            inp=shader.GetInput(field)
            if not inp or inp.HasConnectedSource():
                raise RuntimeError("Connected or missing USD shader input unsupported: "+field)
            sampled=inp.Get(Usd.TimeCode(float(tick)))
            if sampled is None:
                raise RuntimeError("Original material lacks exact-time authored look: "+field)
            if field=="diffuseColor":
                if len(sampled)!=3:
                    raise RuntimeError("USD material color is not RGB")
                color=[float(x) for x in sampled]
                if any(not math.isfinite(x) or not 0.0<=x<=1.0 for x in color):
                    raise RuntimeError("Non-finite or unsupported original linear USD color")
                values["linear_diffuse_rgb"]=color
            else:
                roughness=float(sampled)
                if not math.isfinite(roughness) or not 0<=roughness<=1:
                    raise RuntimeError("Non-finite or unsupported source USD roughness")
                values["roughness"]=roughness
        result.append({
            "prim_path":path,
            "material_path":str(bound.GetPath()),
            "shader_path":str(shader.GetPath()),
            **values,
        })
        if len(result)>MAX_BINDINGS:
            raise RuntimeError("Too many original USD material bindings for one frame")
    return sorted(result,key=lambda item:item["prim_path"])
