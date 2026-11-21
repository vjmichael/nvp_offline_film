"""G09-A: independently reopenable production OpenUSD + PBR / MaterialX looks.

Derived from immutable G06 OpenUSD and an approved G09 material/environment
overlay. The original source bytes are never rewritten, and the derived layer
is never inserted as a replacement Digital Take. Both UsdPreviewSurface and
MaterialX standard_surface outputs are authored: Hydra/MaterialX and Cycles
adapters can choose their approved backend and report unsupported shading
separately. No arbitrary texture resolver, Python expression or external USD.
"""
from __future__ import annotations

from hashlib import sha256
import math

from backend.nvp_g09_environment import _validate,_material,FORMAT
from backend.nvp_g08_native_avi import _world_stage

MAX_PRODUCTION_USD=8*1024*1024


def _color(value):
    return tuple(int(value[k:k+2],16)/255 for k in (1,3,5))


def author_derived_world(original_bytes,take_id,take_sha,look,source_doc):
    """Return (new_usda_bytes, receipt) with exact-source integrity proofs.

    This operation never saves the bytes to the original G05/G06 SQLite cell.
    A protected production worker needs G03's reviewed host approval/custody.
    """
    if type(original_bytes) is not bytes or len(original_bytes)>MAX_PRODUCTION_USD:
        raise ValueError("Original film world is outside production scene limits")
    _validate(look,take_id,take_sha,source_doc)
    from pxr import Gf,Sdf,Usd,UsdGeom,UsdLux,UsdShade
    layer=Sdf.Layer.CreateAnonymous("nvp-g09-derived-production.usda")
    if not layer.ImportFromString(original_bytes.decode("utf8","strict")):
        raise RuntimeError("Cannot reopen original Digital Take OpenUSD")
    if layer.subLayerPaths or layer.GetExternalReferences():
        raise RuntimeError("External source layers are not allowed")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if not stage or not stage.GetPrimAtPath("/World"):
        raise RuntimeError("Original Take has no authoritative world")
    root=stage.GetPrimAtPath("/World")
    root.CreateAttribute("nvp:g09:originalUsdSha256",
                         Sdf.ValueTypeNames.String).Set(sha256(original_bytes).hexdigest())
    root.CreateAttribute("nvp:g09:takeSha256",Sdf.ValueTypeNames.String).Set(take_sha)
    root.CreateAttribute("nvp:g09:kitSource",Sdf.ValueTypeNames.String).Set(
        look["kit_source"])
    root.CreateAttribute("nvp:g09:approvedMaterialMode",
                         Sdf.ValueTypeNames.String).Set("PBR_MaterialX_UsdPreviewSurface")
    root.CreateAttribute("nvp:g09:skyColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*_color(look["sky"])))
    root.CreateAttribute("nvp:g09:fogDensity",Sdf.ValueTypeNames.Double).Set(
        look["atmosphere"]["density"])
    root.CreateAttribute("nvp:g09:fogColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*_color(look["atmosphere"]["color"])))
    scope=UsdGeom.Scope.Define(stage,"/World/G09Production")
    mat_root=UsdGeom.Scope.Define(stage,"/World/G09Production/Materials")
    pieces=UsdGeom.Xform.Define(stage,"/World/G09Production/SetPieces")
    sun=UsdLux.DistantLight.Define(stage,"/World/G09Production/Key")
    sun.CreateIntensityAttr(float(look["sun"]["intensity"]))
    sun.CreateAngleAttr(1.1)
    sky=UsdLux.DomeLight.Define(stage,"/World/G09Production/Fill")
    sky.CreateIntensityAttr(float(look["sun"]["fill"]))
    sky.CreateColorAttr(Gf.Vec3f(*_color(look["sky"])))
    az=math.radians(look["sun"]["azimuth"])
    el=math.radians(look["sun"]["elevation"])
    source_color=_kelvin_rgb(look["sun"]["temperature"])
    sun.CreateColorAttr(Gf.Vec3f(*source_color))
    UsdGeom.XformCommonAPI(sun).SetRotate(
        Gf.Vec3f(0,90-look["sun"]["elevation"],look["sun"]["azimuth"]))
    bound=[]
    def material(index,parameters):
        mat=UsdShade.Material.Define(
            stage,"/World/G09Production/Materials/M"+str(index))
        shade=UsdShade.Shader.Define(stage,mat.GetPath().pathString+"/Preview")
        shade.CreateIdAttr("UsdPreviewSurface")
        shade.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*_color(parameters["color"])))
        shade.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(
            parameters["roughness"])
        shade.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(
            parameters["metallic"])
        shade.CreateInput("emissiveColor",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*(x*parameters["emission"] for x in _color(parameters["color"]))))
        shade.CreateOutput("surface",Sdf.ValueTypeNames.Token)
        mat.CreateSurfaceOutput().ConnectToSource(
            shade.ConnectableAPI(),"surface")
        # Separate MaterialX shader network: no external MaterialX document
        # or untrusted texture path is ever loaded.
        mtlx=UsdShade.Shader.Define(stage,mat.GetPath().pathString+"/MaterialX")
        mtlx.CreateIdAttr("ND_standard_surface_surfaceshader")
        mtlx.CreateInput("base_color",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*_color(parameters["color"])))
        mtlx.CreateInput("specular_roughness",Sdf.ValueTypeNames.Float).Set(
            parameters["roughness"])
        mtlx.CreateInput("metalness",Sdf.ValueTypeNames.Float).Set(
            parameters["metallic"])
        mtlx.CreateInput("emission",Sdf.ValueTypeNames.Float).Set(
            parameters["emission"])
        mtlx.CreateOutput("out",Sdf.ValueTypeNames.Token)
        mat.CreateSurfaceOutput("mtlx").ConnectToSource(
            mtlx.ConnectableAPI(),"out")
        return mat
    index=0
    for item in source_doc["stage_objects"]:
        selected=look["materials"].get(item["id"])
        if selected is None:continue
        base=stage.GetPrimAtPath("/World/Objects/"+item["id"])
        if not base:raise RuntimeError("Material target was removed from the Take")
        candidate=base.GetChild("Geometry")
        if not candidate:
            raise RuntimeError("Filmed geometry cannot receive a material")
        index+=1
        UsdShade.MaterialBindingAPI.Apply(candidate).Bind(material(index,selected))
        bound.append(item["id"])
    for item in look["set_pieces"]:
        path="/World/G09Production/SetPieces/"+item["id"]
        obj=UsdGeom.Xform.Define(stage,path)
        x=UsdGeom.XformCommonAPI(obj)
        x.SetTranslate(Gf.Vec3d(*item["position"]))
        x.SetRotate(Gf.Vec3f(*item["rotation"]))
        x.SetScale(Gf.Vec3f(*item["scale"]))
        shape=item["shape"]
        if shape=="box":
            geom=UsdGeom.Cube.Define(stage,path+"/Geometry")
            geom.CreateSizeAttr(1.)
        elif shape=="sphere":
            geom=UsdGeom.Sphere.Define(stage,path+"/Geometry")
            geom.CreateRadiusAttr(.5)
        elif shape=="cone":
            geom=UsdGeom.Cone.Define(stage,path+"/Geometry")
            geom.CreateRadiusAttr(.5)
            geom.CreateHeightAttr(1.)
        elif shape=="cylinder":
            geom=UsdGeom.Cylinder.Define(stage,path+"/Geometry")
            geom.CreateRadiusAttr(.5)
            geom.CreateHeightAttr(1.)
        else:raise ValueError("Unsupported derived set shape")
        obj.GetPrim().CreateAttribute("nvp:g09:setPieceId",
            Sdf.ValueTypeNames.String).Set(item["id"])
        index+=1
        UsdShade.MaterialBindingAPI.Apply(geom.GetPrim()).Bind(
            material(index,item["material"]))
    produced=layer.ExportToString().encode("utf8")
    if len(produced)>MAX_PRODUCTION_USD:
        raise ValueError("Derived film production scene exceeds size budget")
    new=_world_stage(produced)
    orig=new.GetPrimAtPath("/World").GetAttribute(
        "nvp:g09:originalUsdSha256").Get()
    if orig!=sha256(original_bytes).hexdigest():
        raise RuntimeError("Rendered USD lost its frozen source provenance")
    for item in look["set_pieces"]:
        if not new.GetPrimAtPath(
                "/World/G09Production/SetPieces/"+item["id"]+"/Geometry"):
            raise RuntimeError("Production set piece did not survive USD reopen")
    return produced,{"format":"nvp.g09.derived_pbr_usd.v1",
        "original_usd_sha256":orig,
        "take_sha256":take_sha,
        "derived_usd_sha256":sha256(produced).hexdigest(),
        "material_targets":bound,
        "set_pieces":len(look["set_pieces"]),
        "external_asset_paths":False,"source_modified":False}


def _kelvin_rgb(kelvin):
    t=max(1000,min(40000,kelvin))/100
    if t<=66:r=255
    else:r=329.698727446*((t-60)**(-.1332047592))
    if t<=66:g=99.4708025861*math.log(t)-161.1195681661
    else:g=288.1221695283*((t-60)**(-.0755148492))
    if t>=66:b=255
    elif t<=19:b=0
    else:b=138.5177312231*math.log(t-10)-305.0447927307
    return tuple(max(0.,min(1.,v/255.)) for v in (r,g,b))
