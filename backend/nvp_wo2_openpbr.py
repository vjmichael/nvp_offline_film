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
        if not inp:
            raise RuntimeError("Original OpenPBR scalar input missing")
        if inp.HasConnectedSource():
            channel={"base_metalness":"Metallic",
                     "specular_roughness":"Roughness"}.get(name)
            connected=inp.GetConnectedSource()
            if (not channel or not connected or
                str(connected[0].GetPrim().GetPath())!=
                    material_path+"/MtlxMap_"+channel or
                connected[1]!="out"):
                raise RuntimeError("Untrusted MaterialX scalar channel connection")
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


def author_openpbr_texture(stage,material_path,material,
                           descriptor,roughness,metallic):
    """Author exact immutable source RGB texture in bounded MaterialX context.

    The symbolic nvp-blob:// file is resolved ONLY by NVP's approved
    FilmIndex reader. A generic Hydra renderer needs an explicit trusted,
    SHA-checked resolver before production shader generation can pass.
    """
    from pxr import Sdf,UsdShade
    if (type(descriptor) is not dict or
        descriptor.get("source_modified") is not False or
        descriptor.get("color_space")!="sRGB" or
        descriptor.get("wrap")!="repeat" or
        not str(descriptor.get("usd_asset_path","")).startswith(
            "nvp-blob://texture/")):
        raise ValueError("MaterialX PNG source must be NVP-indexed")
    shader=UsdShade.Shader.Define(stage,material_path+"/OpenPBR")
    shader.CreateIdAttr(NODE_ID)
    shader.CreateInput("base_metalness",Sdf.ValueTypeNames.Float).Set(
        float(metallic))
    shader.CreateInput("specular_roughness",Sdf.ValueTypeNames.Float).Set(
        float(roughness))
    image=UsdShade.Shader.Define(stage,material_path+"/MtlxImage")
    image.CreateIdAttr("ND_image_color3")
    source_file=image.CreateInput("file",Sdf.ValueTypeNames.Asset)
    source_file.Set(Sdf.AssetPath(descriptor["usd_asset_path"]))
    source_file.GetAttr().SetColorSpace("srgb_texture")
    image.CreateInput("uaddressmode",Sdf.ValueTypeNames.String).Set(
        "periodic")
    image.CreateInput("vaddressmode",Sdf.ValueTypeNames.String).Set(
        "periodic")
    image.CreateInput("filtertype",Sdf.ValueTypeNames.String).Set(
        "closest")
    uv=UsdShade.Shader.Define(stage,material_path+"/MtlxTexcoord")
    uv.CreateIdAttr("ND_texcoord_vector2")
    uv.CreateInput("index",Sdf.ValueTypeNames.Int).Set(0)
    image.CreateInput("texcoord",Sdf.ValueTypeNames.Float2).ConnectToSource(
        uv.CreateOutput("out",Sdf.ValueTypeNames.Float2))
    shader.CreateInput("base_color",Sdf.ValueTypeNames.Color3f).ConnectToSource(
        image.CreateOutput("out",Sdf.ValueTypeNames.Color3f))
    shader.CreateOutput("out",Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mtlx").ConnectToSource(
        shader.ConnectableAPI(),"out")


def verify_openpbr_texture(stage,material_path,material,
                           descriptor,roughness,metallic):
    """Reject every unexpected node, source URI, transform or UV rewiring."""
    from pxr import UsdShade
    shader=UsdShade.Shader(
        stage.GetPrimAtPath(material_path+"/OpenPBR"))
    image=UsdShade.Shader(
        stage.GetPrimAtPath(material_path+"/MtlxImage"))
    uv=UsdShade.Shader(
        stage.GetPrimAtPath(material_path+"/MtlxTexcoord"))
    if (not shader or shader.GetIdAttr().Get()!=NODE_ID or
        not image or image.GetIdAttr().Get()!="ND_image_color3" or
        not uv or uv.GetIdAttr().Get()!="ND_texcoord_vector2" or
        uv.GetInput("index").GetAttr().Get()!=0 or
        str(image.GetInput("file").GetAttr().Get().path)!=
            descriptor["usd_asset_path"] or
        image.GetInput("file").GetAttr().GetColorSpace()!="srgb_texture" or
        image.GetInput("uaddressmode").GetAttr().Get()!="periodic" or
        image.GetInput("vaddressmode").GetAttr().Get()!="periodic" or
        image.GetInput("filtertype").GetAttr().Get()!="closest"):
        raise RuntimeError("Frozen MaterialX original image graph changed")
    connections=[
        (material.GetSurfaceOutput("mtlx"),material_path+"/OpenPBR","out"),
        (shader.GetInput("base_color"),material_path+"/MtlxImage","out"),
        (image.GetInput("texcoord"),material_path+"/MtlxTexcoord","out"),
    ]
    for input_,expected_path,expected_output in connections:
        source=input_.GetConnectedSource() if input_ else None
        if (not source or
            str(source[0].GetPrim().GetPath())!=expected_path or
            source[1]!=expected_output):
            raise RuntimeError("Frozen MaterialX image graph rewired")
    for key,expected in (
        ("base_metalness",metallic),
        ("specular_roughness",roughness),
    ):
        value=shader.GetInput(key)
        if (not value or value.HasConnectedSource() or
            not math.isclose(float(value.GetAttr().Get()),
                float(expected),rel_tol=1e-5,abs_tol=1e-5)):
            raise RuntimeError("MaterialX source scalar changed")
    return {"format":FORMAT,
            "materialx_image_graph_authored":True,
            "immutable_texture_sha256":descriptor["sha256"],
            "external_resolver_admitted":False,
            "hydra_renderer_parity_proven":False}
