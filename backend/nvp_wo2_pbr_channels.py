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
    result={}
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
        result[key]=publish_texture(index,pid,maps[key])
    return result

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
    if not maps:return
    from pxr import UsdShade
    for key,desc in maps.items():
        suffix=key.capitalize()
        path=material_path+"/Map_"+suffix
        uv_path=path+"_UV"
        shader=UsdShade.Shader(stage.GetPrimAtPath(path))
        uv=UsdShade.Shader(stage.GetPrimAtPath(uv_path))
        if (not shader or shader.GetIdAttr().Get()!="UsdUVTexture" or
            not uv or uv.GetIdAttr().Get()!="UsdPrimvarReader_float2" or
            uv.GetInput("varname").GetAttr().Get()!="st" or
            str(shader.GetInput("file").GetAttr().Get().path)!=
                desc["usd_asset_path"] or
            shader.GetInput("sourceColorSpace").GetAttr().Get()!=
                ("sRGB" if key=="emission" else "raw")):
            raise RuntimeError("Original PBR USD map source changed: "+key)
        for axis in ("wrapS","wrapT"):
            if shader.GetInput(axis).GetAttr().Get()!="repeat":
                raise RuntimeError("Original PBR map wrapping changed")
        if key=="opacity" and not abs(
            float(preview.GetInput("opacityThreshold").GetAttr().Get())-.5)<1e-6:
            raise RuntimeError("Original cutout opacity threshold changed")
        if key=="normal":
            scale=shader.GetInput("scale").GetAttr().Get()
            bias=shader.GetInput("bias").GetAttr().Get()
            if (list(scale)!=[2.,2.,2.,1.] or
                list(bias)!=[-1.,-1.,-1.,0.]):
                raise RuntimeError("Original tangent normal conversion changed")
        mtlx=UsdShade.Shader(stage.GetPrimAtPath(
            material_path+"/MtlxMap_"+suffix))
        expected_id=("ND_image_float" if key in ("roughness","metallic","opacity")
                     else "ND_image_color3")
        if (not mtlx or mtlx.GetIdAttr().Get()!=expected_id or
            str(mtlx.GetInput("file").GetAttr().Get().path)!=
                desc["usd_asset_path"] or
            mtlx.GetInput("file").GetAttr().GetColorSpace()!=
                ("srgb_texture" if key=="emission" else "raw")):
            raise RuntimeError("Original MaterialX channel source changed: "+key)
        for input_,expected in (
            (shader.GetInput("st"),uv_path),
            (mtlx.GetInput("texcoord"),material_path+"/MtlxMapUV_"+suffix),
        ):
            connected=input_.GetConnectedSource() if input_ else None
            if not connected or str(connected[0].GetPrim().GetPath())!=expected:
                raise RuntimeError("Original PBR UV input disconnected: "+key)
        target={
            "roughness":"roughness","metallic":"metallic",
            "emission":"emissiveColor","normal":"normal",
            "opacity":"opacity"}[key]
        connection=preview.GetInput(target).GetConnectedSource()
        if not connection or str(connection[0].GetPrim().GetPath())!=path:
            raise RuntimeError("PreviewSurface PBR input rewired: "+key)
        if key=="normal":
            normal=UsdShade.Shader(stage.GetPrimAtPath(
                material_path+"/MtlxNormalMap"))
            if not normal or normal.GetIdAttr().Get()!="ND_normalmap_vector3":
                raise RuntimeError("Original tangent-space normal conversion missing")
            out=openpbr.GetInput("geometry_normal").GetConnectedSource()
            if not out or str(out[0].GetPrim().GetPath())!=(
                material_path+"/MtlxNormalMap"):
                raise RuntimeError("Original OpenPBR normal input rewired")
        else:
            if key=="emission" and (
                float(openpbr.GetInput(
                    "emission_luminance").GetAttr().Get())!=1.):
                raise RuntimeError("Original OpenPBR emission disabled")
            input_name={"roughness":"specular_roughness",
                        "metallic":"base_metalness",
                        "emission":"emission_color",
                        "opacity":"geometry_opacity"}[key]
            connected=openpbr.GetInput(input_name).GetConnectedSource()
            if not connected or str(connected[0].GetPrim().GetPath())!=(
                material_path+"/MtlxMap_"+suffix):
                raise RuntimeError("Original OpenPBR PBR channel rewired")
