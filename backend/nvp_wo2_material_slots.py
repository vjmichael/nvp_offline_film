"""WO2 bounded real USD face-material subsets on immutable triangle meshes.

No arbitrary MaterialX source, prim paths or external asset resolvers.
The original USD stage owns actual UsdGeom.Subset and UsdShade materials.
"""
from __future__ import annotations
import math

MAX_SUBSETS=8
FORMAT="nvp.original.usd_material_subsets.v1"


def normalize_material_slots(slots,face_count):
    if slots is None:return None
    if (type(slots) is not list or not 1<=len(slots)<=MAX_SUBSETS or
        type(face_count) is not int or face_count<1):
        raise ValueError("Bounded native USD face material slots required")
    occupied=set()
    result=[]
    for i,slot in enumerate(slots):
        if (type(slot) is not dict or set(slot)!={
            "faces","base_color_rgb","roughness","metallic"}):
            raise ValueError("Unsupported original face material fields")
        faces=slot["faces"]
        rgb=slot["base_color_rgb"]
        if (type(faces) is not list or not faces or
            any(type(n) is not int or n<0 or n>=face_count
                for n in faces) or len(set(faces))!=len(faces) or
            occupied.intersection(faces)):
            raise ValueError("Original USD material subset faces overlap or escape")
        occupied.update(faces)
        if (type(rgb) is not list or len(rgb)!=3 or
            any(type(x) not in (int,float) or not math.isfinite(x) or
                not 0<=x<=1 for x in rgb)):
            raise ValueError("Original material subset RGB is invalid")
        for name in ("roughness","metallic"):
            x=slot[name]
            if type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1:
                raise ValueError("Original material subset scalar invalid")
        result.append({
            "format":FORMAT,
            "material_path":"/Asset/Materials/Slot"+str(i),
            "subset_path":"/Asset/Geometry/MaterialSlot"+str(i),
            "faces":sorted(faces),
            "base_color_rgb":[float(x) for x in rgb],
            "roughness":float(slot["roughness"]),
            "metallic":float(slot["metallic"]),
            "source_modified":False,
        })
    return result


def author_material_slots(stage,geometry,slots):
    from pxr import Gf,Sdf,UsdGeom,UsdShade,Vt
    for spec in slots or []:
        subset=UsdShade.MaterialBindingAPI(
            geometry.GetPrim()).CreateMaterialBindSubset(
                "MaterialSlot"+str(slots.index(spec)),
                Vt.IntArray(spec["faces"]),UsdGeom.Tokens.face)
        if str(subset.GetPrim().GetPath())!=spec["subset_path"]:
            raise RuntimeError("Source face subset has an unexpected path")
        material=UsdShade.Material.Define(stage,spec["material_path"])
        shader=UsdShade.Shader.Define(stage,
            spec["material_path"]+"/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*spec["base_color_rgb"]))
        for key in ("roughness","metallic"):
            shader.CreateInput(key,Sdf.ValueTypeNames.Float).Set(spec[key])
        shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(),"surface")
        from backend.nvp_wo2_openpbr import author_openpbr_scalar
        author_openpbr_scalar(stage,spec["material_path"],material,
            spec["base_color_rgb"],spec["roughness"],spec["metallic"])
        if not UsdShade.MaterialBindingAPI.Apply(
                subset.GetPrim()).Bind(material):
            raise RuntimeError("Source USD face subset material binding failed")


def verify_material_slots(stage,geometry,slots,face_count):
    from pxr import UsdGeom,UsdShade
    if not slots:return
    expected=normalize_material_slots([
        {key:s[key] for key in ("faces","base_color_rgb",
                                "roughness","metallic")}
        for s in slots],face_count)
    if expected!=slots:
        raise RuntimeError("Original material subset manifest differs")
    found=UsdShade.MaterialBindingAPI(
        geometry).GetMaterialBindSubsets()
    if len(found)!=len(slots) or {
            str(item.GetPrim().GetPath()) for item in found}!={
            spec["subset_path"] for spec in slots}:
        raise RuntimeError("Unexpected original USD material subset inserted")
    for spec in slots:
        prim=stage.GetPrimAtPath(spec["subset_path"])
        if not prim or not prim.IsA(UsdGeom.Subset):
            raise RuntimeError("Original USD face material subset missing")
        subset=UsdGeom.Subset(prim)
        if (subset.GetElementTypeAttr().Get()!=UsdGeom.Tokens.face or
            subset.GetFamilyNameAttr().Get()!="materialBind" or
            list(subset.GetIndicesAttr().Get())!=spec["faces"]):
            raise RuntimeError("Original USD material face indices modified")
        bound,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if not bound or str(bound.GetPath())!=spec["material_path"]:
            raise RuntimeError("Frozen material subset USD binding changed")
        from backend.nvp_wo2_openpbr import verify_openpbr_scalar
        verify_openpbr_scalar(stage,spec["material_path"],bound,
            spec["base_color_rgb"],spec["roughness"],spec["metallic"])
        shader=UsdShade.Shader(stage.GetPrimAtPath(
            spec["material_path"]+"/PreviewSurface"))
        if not shader or shader.GetIdAttr().Get()!="UsdPreviewSurface":
            raise RuntimeError("Original subset is not UsdPreviewSurface")
        for key in ("diffuseColor","roughness","metallic"):
            actual=shader.GetInput(key).GetAttr().Get()
            expected_value=(spec["base_color_rgb"] if
                key=="diffuseColor" else [spec[key]])
            got=(list(actual) if key=="diffuseColor" else [actual])
            if len(got)!=len(expected_value) or any(
                not math.isclose(float(x),float(y),abs_tol=1e-5,rel_tol=1e-5)
                for x,y in zip(got,expected_value)):
                raise RuntimeError("Original USD face material shader changed")
