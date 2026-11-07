"""WO2 dual-context USD PreviewSurface + tightly bounded OpenPBR scalar node.

OpenPBR is authored as UsdShade (info:id from MaterialX 1.39
ND_open_pbr_surface_surfaceshader), never by importing arbitrary XML or
executing renderer-provided code. Real shader generation/physical image
parity remains a separate renderer-dependent acceptance gate.
"""
from __future__ import annotations
import math

NODE_ID="ND_open_pbr_surface_surfaceshader"
FORMAT="nvp.wo2.usd_openpbr_scalar_fallback.v1"


def author_openpbr_scalar(stage,material_path,material,color,roughness,metallic):
    from pxr import Gf,Sdf,UsdShade
    path=material_path+"/OpenPBR"
    shader=UsdShade.Shader.Define(stage,path)
    shader.CreateIdAttr(NODE_ID)
    shader.CreateInput("base_color",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*color))
    shader.CreateInput("base_metalness",Sdf.ValueTypeNames.Float).Set(
        float(metallic))
    shader.CreateInput("specular_roughness",Sdf.ValueTypeNames.Float).Set(
        float(roughness))
    shader.CreateOutput("out",Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mtlx").ConnectToSource(
        shader.ConnectableAPI(),"out")


def verify_openpbr_scalar(stage,material_path,material,color,roughness,metallic):
    from pxr import UsdShade
    shader=UsdShade.Shader(
        stage.GetPrimAtPath(material_path+"/OpenPBR"))
    if not shader or shader.GetIdAttr().Get()!=NODE_ID:
        raise RuntimeError("Bounded MaterialX OpenPBR USD shader missing")
    surface=material.GetSurfaceOutput("mtlx")
    if not surface or not surface.HasConnectedSource():
        raise RuntimeError("MaterialX surface output disconnected")
    source=surface.GetConnectedSource()
    if (not source or
        str(source[0].GetPrim().GetPath())!=material_path+"/OpenPBR"
        or source[1]!="out"):
        raise RuntimeError("MaterialX surface source rewired")
    expectations={
        "base_color":list(color),
        "base_metalness":[metallic],
        "specular_roughness":[roughness],
    }
    for name,expected in expectations.items():
        inp=shader.GetInput(name)
        if not inp or inp.HasConnectedSource():
            raise RuntimeError("Unexpected arbitrary MaterialX input connection")
        value=inp.GetAttr().Get()
        actual=(list(value) if name=="base_color" else [value])
        if (len(actual)!=len(expected) or
            any(not math.isclose(float(x),float(y),
                    rel_tol=1e-5,abs_tol=1e-5)
                for x,y in zip(actual,expected))):
            raise RuntimeError("Bounded original OpenPBR parameter changed")
    return {"format":FORMAT,"material_path":material_path,
            "materialx_source_verified":True,
            "hydra_renderer_parity_proven":False}
