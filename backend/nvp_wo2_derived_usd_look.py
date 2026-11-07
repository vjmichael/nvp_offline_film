"""WO2 A–E derived OpenUSD lighting/material/UV stage for independent Hydra.

The original FilmIndex scene and USD layer stack are never touched. A
SHA-bound creator presentation is evaluated solely into a disposable
flattened layer. Native USD PreviewSurface, MaterialX OpenPBR and UV
Shader inputs remain standard typed UsdShade/UsdLux attributes.
"""
from __future__ import annotations
import math

from backend.nvp_wo2_presentation_look import validate_look

FORMAT="nvp.wo2.derived_usd_look_stage.v1"

def derived_look_stage(stage,scene_record,look):
    from pxr import Gf,Sdf,Usd,UsdGeom,UsdLux,UsdShade
    if (not isinstance(stage,Usd.Stage) or
        type(scene_record) is not dict or
        type(scene_record.get("data")) is not dict or
        not scene_record.get("document_sha256")):
        raise ValueError("A verified original scene stage is required")
    roles=scene_record["data"]["prim_roles"]
    clean=validate_look(look,roles)
    before=stage.GetRootLayer().ExportToString()
    derived=Usd.Stage.Open(stage.Flatten())
    if not derived:
        raise RuntimeError("Cannot derive independently inspectable USD look")
    material_paths=set()
    for path,values in clean["materials"].items():
        root=derived.GetPrimAtPath(path)
        if not root or not root.IsDefined():
            raise RuntimeError("Approved material source path vanished")
        materials={}
        for prim in Usd.PrimRange(root):
            if not prim.IsA(UsdGeom.Mesh):
                continue
            material,_=UsdShade.MaterialBindingAPI(
                prim).ComputeBoundMaterial()
            if material:
                if not str(material.GetPath()).startswith(path+"/"):
                    raise RuntimeError("Derived look would mutate another actor's material")
                materials[str(material.GetPath())]=material
        if not materials:
            raise RuntimeError("Original USD mesh has no bound source material")
        for material_path,material in materials.items():
            preview=UsdShade.Shader(
                derived.GetPrimAtPath(material_path+"/PreviewSurface"))
            openpbr=UsdShade.Shader(
                derived.GetPrimAtPath(material_path+"/OpenPBR"))
            if not preview or not openpbr:
                raise RuntimeError("Source material lacks bounded USD / OpenPBR nodes")
            if values["opacity"]!=1. and (
                    preview.GetInput("opacity") and
                    preview.GetInput("opacity").HasConnectedSource()):
                raise RuntimeError("Fractional opacity and binary cutout need a compositing graph")
            preview.CreateInput(
                "opacity",Sdf.ValueTypeNames.Float).Set(values["opacity"])
            preview.CreateInput(
                "ior",Sdf.ValueTypeNames.Float).Set(values["ior"])
            if values["opacity"]!=1. and (
                    openpbr.GetInput("geometry_opacity") and
                    openpbr.GetInput("geometry_opacity").HasConnectedSource()):
                raise RuntimeError("MaterialX cutout opacity cannot be overwritten")
            openpbr.CreateInput(
                "geometry_opacity",Sdf.ValueTypeNames.Float).Set(values["opacity"])
            openpbr.CreateInput(
                "transmission_weight",Sdf.ValueTypeNames.Float).Set(
                    values["transmission"])
            openpbr.CreateInput(
                "specular_ior",Sdf.ValueTypeNames.Float).Set(values["ior"])
            # Thickness is a geometric volume path length, not an OpenPBR
            # absorption-depth control. Retain bounded presentation metadata
            # rather than pretending those two distinct quantities are equal.
            material.GetPrim().CreateAttribute(
                "nvp:lookThicknessMeters",
                Sdf.ValueTypeNames.Float).Set(values["thickness_m"])
            material_paths.add(material_path)
    uv_count=0
    for path,channels in clean["textures"]["transforms"].items():
        root=derived.GetPrimAtPath(path)
        if not root or not root.IsDefined():
            raise RuntimeError("Original UV source actor disappeared")
        found=set()
        for prim in Usd.PrimRange(root):
            if not prim.IsA(UsdGeom.Mesh):continue
            material,_=UsdShade.MaterialBindingAPI(
                prim).ComputeBoundMaterial()
            if not material:continue
            base=str(material.GetPath())
            if not base.startswith(path+"/"):
                raise RuntimeError("UV look targets cross-actor material")
            for channel,transform in channels.items():
                suffix=("Texture" if channel=="base_color" else
                        "Map_"+channel.capitalize())
                image=UsdShade.Shader(derived.GetPrimAtPath(base+"/"+suffix))
                if not image:
                    # The base color uses the author's existing /Texture
                    # node (rig) or /Texture (asset); no arbitrary shader.
                    continue
                st=image.GetInput("st")
                connected=st.GetConnectedSource() if st else None
                if not connected:
                    raise RuntimeError("Original USD source UV was disconnected")
                uvnode=UsdShade.Shader.Define(
                    derived,base+"/WO2Transform_"+channel)
                uvnode.CreateIdAttr("UsdTransform2d")
                uvnode.CreateInput("in",Sdf.ValueTypeNames.Float2).ConnectToSource(
                    connected[0],connected[1])
                uvnode.CreateInput("scale",Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(*transform["repeat"]))
                uvnode.CreateInput("rotation",Sdf.ValueTypeNames.Float).Set(
                    transform["rotation_deg"])
                uvnode.CreateInput("translation",Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(*transform["offset"]))
                st.ConnectToSource(
                    uvnode.CreateOutput("result",Sdf.ValueTypeNames.Float2))
                # The same derived UV decision must reach the MaterialX
                # shader context; PreviewSurface-only edits are misleading.
                name=("MtlxImage" if channel=="base_color" else
                      "MtlxMap_"+channel.capitalize())
                mimage=UsdShade.Shader(
                    derived.GetPrimAtPath(base+"/"+name))
                if not mimage:
                    raise RuntimeError("Original MaterialX source image missing")
                m_st=mimage.GetInput("texcoord")
                m_source=m_st.GetConnectedSource() if m_st else None
                if not m_source:
                    raise RuntimeError("Original MaterialX UV graph disconnected")
                mtx=UsdShade.Shader.Define(
                    derived,base+"/WO2MtlxTransform_"+channel)
                # MaterialX has ND_place2d_vector2, not the fictional
                # ND_UsdTransform2d. Place2D divides by scale and
                # subtracts offset, so invert these to preserve the same
                # source UV mapping as USD's scale/rotation/translation.
                mtx.CreateIdAttr("ND_place2d_vector2")
                mtx.CreateInput("texcoord",Sdf.ValueTypeNames.Float2).ConnectToSource(
                    m_source[0],m_source[1])
                mtx.CreateInput("pivot",Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(0.,0.))
                mtx.CreateInput("scale",Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(*(1./x for x in transform["repeat"])))
                mtx.CreateInput("rotate",Sdf.ValueTypeNames.Float).Set(
                    transform["rotation_deg"])
                mtx.CreateInput("offset",Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(*(-x for x in transform["offset"])))
                m_st.ConnectToSource(
                    mtx.CreateOutput("out",Sdf.ValueTypeNames.Float2))
                found.add(channel)
                uv_count+=1
        if found!=set(channels):
            raise RuntimeError(
                "Original source UV image unavailable for requested channel")
    # The director's camera/aperture choices remain non-destructive source
    # presentation. USD fStop=0 explicitly disables depth of field.
    camera_count=0
    for path,role in roles.items():
        if role!="camera":continue
        camera=UsdGeom.Camera(derived.GetPrimAtPath(path))
        if not camera:
            raise RuntimeError("Authored USD camera missing from look stage")
        camera.GetFStopAttr().Set(
            clean["camera"]["f_stop"]
            if clean["camera"]["depth_of_field"] else 0.)
        camera.GetFocusDistanceAttr().Set(
            clean["camera"]["focus_distance_m"])
        camera.GetPrim().CreateAttribute(
            "nvp:lookExposureEV",Sdf.ValueTypeNames.Float).Set(
            clean["camera"]["exposure_ev"])
        camera.GetPrim().CreateAttribute(
            "nvp:lookViewCurve",Sdf.ValueTypeNames.String).Set(
            clean["camera"]["tone_curve"])
        camera_count+=1

    # Mip filter policy is used by a renderer when generating source-image
    # samples. USD PreviewSurface has no standard anisotropy input; keep
    # that value as declared presentation metadata rather than silently
    # claiming that each Hydra delegate must implement it.
    image_count=0
    for prim in derived.Traverse():
        image=UsdShade.Shader(prim)
        if not image:continue
        identifier=image.GetIdAttr().Get()
        if identifier not in ("UsdUVTexture","ND_image_color3","ND_image_float"):
            continue
        if not image.GetInput("file"):continue
        image.GetPrim().CreateAttribute(
            "nvp:lookTextureFilter",
            Sdf.ValueTypeNames.String).Set(clean["textures"]["filter"])
        image.GetPrim().CreateAttribute(
            "nvp:lookMaxAnisotropy",
            Sdf.ValueTypeNames.Int).Set(clean["textures"]["anisotropy"])
        if identifier.startswith("ND_image_"):
            image.CreateInput(
                "filtertype",Sdf.ValueTypeNames.String).Set(
                    "closest" if clean["textures"]["filter"]=="nearest"
                    else "linear")
        image_count+=1

    # An explicit *derived* lighting rig is distinct from original lights.
    # The source scene's light elements are not moved or rewritten.
    rig=UsdGeom.Xform.Define(derived,"/World/WO2PresentationRig")
    key=UsdLux.DistantLight.Define(
        derived,"/World/WO2PresentationRig/Key")
    key.CreateIntensityAttr().Set(
        clean["lighting"]["direct_intensity"]*500.)
    key.CreateAngleAttr().Set(
        max(.01,clean["lighting"]["shadow_softness"]*.5))
    key.CreateColorAttr().Set(
        Gf.Vec3f(*((
            1.,.72,.49) if clean["environment"]["preset"]=="golden_hour"
            else (.51,.66,1.) if clean["environment"]["preset"]=="moonlight"
            else (1.,1.,1.))))
    fill=UsdLux.DomeLight.Define(
        derived,"/World/WO2PresentationRig/Environment")
    fill.CreateIntensityAttr().Set(
        clean["lighting"]["ambient_intensity"]*
        clean["environment"]["intensity"]*200.)
    fill.CreateColorAttr().Set(
        Gf.Vec3f(*((
            .82,.88,1.) if clean["environment"]["preset"]=="moonlight"
            else (1.,.88,.73) if clean["environment"]["preset"]=="golden_hour"
            else (1.,1.,1.))))
    if stage.GetRootLayer().ExportToString()!=before:
        raise RuntimeError("Original immutable USD was modified by look derivation")
    return derived,{
        "format":FORMAT,
        "original_scene_document_sha256":scene_record["document_sha256"],
        "original_source_unchanged":True,
        "material_count":len(material_paths),
        "uv_transform_count":uv_count,
        "derived_camera_count":camera_count,
        "derived_texture_filter_count":image_count,
        "derived_lights":["UsdLux.DistantLight","UsdLux.DomeLight"],
        "environment_reflection_hdr_verified":False,
        "optical_dof_physically_calibrated":False,
        "hydra_scene_accepted":False,
    }
