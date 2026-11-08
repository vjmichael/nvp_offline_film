"""WO2 immutable, typed MaterialX/PBR texture-channel contracts.

The canonical original PNG blobs remain FilmIndex-owned and SHA-addressed.
These channels are not custom shader code, external paths or arbitrary graphs.
"""
from __future__ import annotations
import math
from backend.nvp_native_usd_texture import publish_texture,verified_texture

CHANNELS=("roughness","metallic","emission","normal","opacity")
FORMAT="nvp.wo2.original_pbr_maps.v1"

def publish_pbr_maps(index,pid,maps,*,has_uv):
    if maps is None:return None
    if (not has_uv or type(maps) is not dict or not maps or
        len(maps)>len(CHANNELS) or
        any(k not in CHANNELS for k in maps)):
        raise ValueError("Original PBR images require bounded authored USD UVs")
    # Validate *every* channel before publishing *any* FilmIndex blob.
    # An invalid final opacity/normal PNG must not partially admit previous
    # channels or create an incomplete original material revision.
    from backend.nvp_native_usd_texture import decode_png
    for key in CHANNELS:
        if key not in maps:continue
        _,_,rgba=decode_png(maps[key])
        if key in ("roughness","metallic","opacity"):
            rgb=memoryview(rgba)
            for i in range(0,len(rgb),4):
                r,g,b=rgb[i],rgb[i+1],rgb[i+2]
                if not (r==g==b and
                        (key!="opacity" or r in (0,255))):
                    raise ValueError(
                        "Scalar PBR maps must be grayscale; opacity is binary")
    return {key:publish_texture(index,pid,maps[key])
            for key in CHANNELS if key in maps}

def verify_pbr_maps(index,pid,maps):
    if maps is None:return None
    if (type(maps) is not dict or not maps or len(maps)>len(CHANNELS) or
        any(k not in CHANNELS for k in maps)):
        raise RuntimeError("Unsupported original PBR image channel")
    for key in CHANNELS:
        if key in maps:
            _,(_,_,rgba)=verified_texture(index,pid,maps[key])
            if key in ("roughness","metallic","opacity"):
                for i in range(0,len(rgba),4):
                    r,g,b=rgba[i:i+3]
                    if not (r==g==b and (
                        key!="opacity" or r in (0,255))):
                        raise RuntimeError("Original scalar PBR pixel contract changed")
    return maps

def author_pbr_maps(stage,material_path,preview,openpbr,maps):
    """Produce actual typed UsdUVTexture and bounded MaterialX shader nodes."""
    if not maps:return
    from pxr import Gf,Sdf,UsdShade
    for key,desc in maps.items():
        suffix=key.capitalize()
        path=material_path+"/Map_"+suffix
        shader=UsdShade.Shader.Define(stage,path)
        shader.CreateIdAttr("UsdUVTexture")
        shader.CreateInput("file",Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath(desc["usd_asset_path"]))
        shader.CreateInput("sourceColorSpace",Sdf.ValueTypeNames.Token).Set(
            "sRGB" if key=="emission" else "raw")
        for axis in ("wrapS","wrapT"):
            shader.CreateInput(axis,Sdf.ValueTypeNames.Token).Set("repeat")
        uv=UsdShade.Shader.Define(stage,path+"_UV")
        uv.CreateIdAttr("UsdPrimvarReader_float2")
        uv.CreateInput("varname",Sdf.ValueTypeNames.Token).Set("st")
        shader.CreateInput("st",Sdf.ValueTypeNames.Float2).ConnectToSource(
            uv.CreateOutput("result",Sdf.ValueTypeNames.Float2))
        if key=="normal":
            shader.CreateInput("scale",Sdf.ValueTypeNames.Float4).Set(
                Gf.Vec4f(2,2,2,1))
            shader.CreateInput("bias",Sdf.ValueTypeNames.Float4).Set(
                Gf.Vec4f(-1,-1,-1,0))
        output=("r" if key in ("roughness","metallic","opacity") else "rgb")
        typ=(Sdf.ValueTypeNames.Float if output=="r" else
             Sdf.ValueTypeNames.Float3)
        preview_type=(
            Sdf.ValueTypeNames.Normal3f if key=="normal" else
            Sdf.ValueTypeNames.Color3f if key=="emission" else typ)
        preview_input={
            "roughness":"roughness",
            "metallic":"metallic",
            "emission":"emissiveColor",
            "normal":"normal",
            "opacity":"opacity",
        }[key]
        preview.CreateInput(preview_input,preview_type).ConnectToSource(
            shader.CreateOutput(output,typ))
        if key=="opacity":
            preview.CreateInput(
                "opacityThreshold",Sdf.ValueTypeNames.Float).Set(.5)
        mtlx=UsdShade.Shader.Define(stage,material_path+"/MtlxMap_"+suffix)
        mtlx.CreateIdAttr(
            "ND_image_float" if key in ("roughness","metallic","opacity")
            else "ND_image_color3")
        attr=mtlx.CreateInput("file",Sdf.ValueTypeNames.Asset)
        attr.Set(Sdf.AssetPath(desc["usd_asset_path"]))
        attr.GetAttr().SetColorSpace(
            "srgb_texture" if key=="emission" else "raw")
        for axis in ("uaddressmode","vaddressmode"):
            mtlx.CreateInput(axis,Sdf.ValueTypeNames.String).Set("periodic")
        mtlx.CreateInput("filtertype",Sdf.ValueTypeNames.String).Set("closest")
        texcoord=UsdShade.Shader.Define(
            stage,material_path+"/MtlxMapUV_"+suffix)
        texcoord.CreateIdAttr("ND_texcoord_vector2")
        texcoord.CreateInput("index",Sdf.ValueTypeNames.Int).Set(0)
        mtlx.CreateInput("texcoord",Sdf.ValueTypeNames.Float2).ConnectToSource(
            texcoord.CreateOutput("out",Sdf.ValueTypeNames.Float2))
        out_type=(Sdf.ValueTypeNames.Float if key in ("roughness","metallic","opacity")
                  else Sdf.ValueTypeNames.Color3f)
        out=mtlx.CreateOutput("out",out_type)
        if key=="normal":
            normal=UsdShade.Shader.Define(
                stage,material_path+"/MtlxNormalMap")
            normal.CreateIdAttr("ND_normalmap_vector3")
            normal.CreateInput("in",Sdf.ValueTypeNames.Color3f).ConnectToSource(
                out)
            normal.CreateOutput("out",Sdf.ValueTypeNames.Vector3f)
            openpbr.CreateInput("geometry_normal",
                Sdf.ValueTypeNames.Vector3f).ConnectToSource(
                normal.GetOutput("out"))
        else:
            target={
                "roughness":"specular_roughness",
                "metallic":"base_metalness",
                "emission":"emission_color",
                "opacity":"geometry_opacity",
            }[key]
            openpbr.CreateInput(target,out_type).ConnectToSource(out)
            if key=="emission":
                openpbr.CreateInput(
                    "emission_luminance",Sdf.ValueTypeNames.Float).Set(1.)

def verify_pbr_map_graph(stage,material_path,preview,openpbr,maps):
    """Verify exact USD + MaterialX sockets, color policy, UV and normal graph.

    Do not accept a matched node path with an arbitrary socket, a substituted
    texcoord node or changed output data type as an immutable PBR source.
    """
    if not maps:return
    from pxr import Sdf,UsdShade
    from backend.nvp_wo3_materialx_integrity import (
        verify_shader_id,verify_literal_input,verify_output_connection)
    for key,desc in maps.items():
        suffix=key.capitalize()
        path=material_path+"/Map_"+suffix
        uv_path=path+"_UV"
        mtlx_path=material_path+"/MtlxMap_"+suffix
        mtlx_uv_path=material_path+"/MtlxMapUV_"+suffix
        shader=verify_shader_id(stage,path,"UsdUVTexture")
        uv=verify_shader_id(stage,uv_path,"UsdPrimvarReader_float2")
        mtlx=verify_shader_id(
            stage,mtlx_path,
            "ND_image_float" if key in ("roughness","metallic","opacity")
            else "ND_image_color3")
        mtlx_uv=verify_shader_id(stage,mtlx_uv_path,"ND_texcoord_vector2")
        preview_file=shader.GetInput("file")
        materialx_file=mtlx.GetInput("file")
        if (not preview_file or
                preview_file.GetTypeName()!=Sdf.ValueTypeNames.Asset or
                preview_file.HasConnectedSource() or
                not materialx_file or
                materialx_file.GetTypeName()!=Sdf.ValueTypeNames.Asset or
                materialx_file.HasConnectedSource() or
                str(preview_file.GetAttr().Get().path)!=desc["usd_asset_path"] or
                str(materialx_file.GetAttr().Get().path)!=desc["usd_asset_path"] or
                materialx_file.GetAttr().GetColorSpace()!=(
                    "srgb_texture" if key=="emission" else "raw")):
            raise RuntimeError("Original PBR source file or color policy changed: "+key)
        verify_literal_input(shader,"sourceColorSpace",
            "sRGB" if key=="emission" else "raw",
            type_name=Sdf.ValueTypeNames.Token)
        for axis in ("wrapS","wrapT"):
            verify_literal_input(shader,axis,"repeat",
                type_name=Sdf.ValueTypeNames.Token)
        for axis in ("uaddressmode","vaddressmode"):
            verify_literal_input(mtlx,axis,"periodic",
                type_name=Sdf.ValueTypeNames.String)
        verify_literal_input(mtlx,"filtertype","closest",
            type_name=Sdf.ValueTypeNames.String)
        verify_literal_input(uv,"varname","st",
            type_name=Sdf.ValueTypeNames.Token)
        verify_literal_input(mtlx_uv,"index",0,
            type_name=Sdf.ValueTypeNames.Int)
        verify_output_connection(
            shader.GetInput("st"),uv_path,"result",
            output_type=Sdf.ValueTypeNames.Float2,
            input_type=Sdf.ValueTypeNames.Float2)
        verify_output_connection(
            mtlx.GetInput("texcoord"),mtlx_uv_path,"out",
            output_type=Sdf.ValueTypeNames.Float2,
            input_type=Sdf.ValueTypeNames.Float2)
        if key=="opacity":
            verify_literal_input(preview,"opacityThreshold",.5,
                type_name=Sdf.ValueTypeNames.Float)
        if key=="normal":
            if (list(shader.GetInput("scale").GetAttr().Get())!=
                    [2.,2.,2.,1.] or
                list(shader.GetInput("bias").GetAttr().Get())!=
                    [-1.,-1.,-1.,0.]):
                raise RuntimeError("Original tangent normal conversion changed")
        preview_socket="r" if key in ("roughness","metallic","opacity") else "rgb"
        preview_output_type=(
            Sdf.ValueTypeNames.Float if preview_socket=="r"
            else Sdf.ValueTypeNames.Float3)
        preview_target={
            "roughness":"roughness","metallic":"metallic",
            "emission":"emissiveColor","normal":"normal",
            "opacity":"opacity"}[key]
        verify_output_connection(
            preview.GetInput(preview_target),path,preview_socket,
            output_type=preview_output_type)
        map_output_type=(
            Sdf.ValueTypeNames.Float
            if key in ("roughness","metallic","opacity")
            else Sdf.ValueTypeNames.Color3f)
        if key=="normal":
            normal_path=material_path+"/MtlxNormalMap"
            normal=verify_shader_id(stage,normal_path,"ND_normalmap_vector3")
            verify_output_connection(
                normal.GetInput("in"),mtlx_path,"out",
                output_type=Sdf.ValueTypeNames.Color3f,
                input_type=Sdf.ValueTypeNames.Color3f)
            verify_output_connection(
                openpbr.GetInput("geometry_normal"),normal_path,"out",
                output_type=Sdf.ValueTypeNames.Vector3f,
                input_type=Sdf.ValueTypeNames.Vector3f)
        else:
            if key=="emission":
                verify_literal_input(openpbr,"emission_luminance",1.,
                    type_name=Sdf.ValueTypeNames.Float)
            openpbr_target={
                "roughness":"specular_roughness",
                "metallic":"base_metalness",
                "emission":"emission_color",
                "opacity":"geometry_opacity"}[key]
            verify_output_connection(
                openpbr.GetInput(openpbr_target),mtlx_path,"out",
                output_type=map_output_type)
