"""SLATE-07: bounded, typed, genuinely bound USD skeletal character meshes.

The source is a genuine UsdGeom.Mesh with UsdSkelBindingAPI joint indices,
weights and a skeleton relation. No arbitrary USD file, outside resolver,
arbitrary model script or untrusted image enters the frozen FilmIndex scene.

For now all skeletal bind/rest transforms in NVP's existing animation are
identities. This profile faithfully skins vertex points from those source
rig joints; more general bind-pose authoring and facial rigging follow later.
"""
from __future__ import annotations

import math
import re

MAX_SKIN_VERTICES=512
MAX_SKIN_FACES=1024
MAX_INFLUENCES=4
SKIN_MESH_SUFFIX="/Rig/CharacterMesh"
MAX_FACIAL_SHAPES=8
SHAPE_NAME=re.compile(r"[A-Za-z][A-Za-z0-9_]{0,30}\Z")


def _float(value):
    if type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1_000:
        raise ValueError("Skinned source geometry requires bounded finite coordinates")
    return float(value)


def normalize_skin(skin,joint_count):
    required={"points","faces","joint_indices","joint_weights","display_color"}
    optional={"blend_shapes","preview_material","mesh_uvs","face_uvs","texture","pbr_maps"}
    if type(skin) is not dict or not required<=set(skin) or not set(skin)<=required|optional:
        raise ValueError("Skin requires source topology, influence fields and typed optional appearance")
    points=skin["points"]
    faces=skin["faces"]
    ids=skin["joint_indices"]
    weights=skin["joint_weights"]
    if (type(points) is not list or not 4<=len(points)<=MAX_SKIN_VERTICES or
        type(faces) is not list or not 1<=len(faces)<=MAX_SKIN_FACES or
        type(ids) is not list or len(ids)!=len(points) or
        type(weights) is not list or len(weights)!=len(points)):
        raise ValueError("Skin mesh topology or per-vertex joint influences out of bounds")
    pts=[]
    joints=[]
    normalized_weights=[]
    for i,point in enumerate(points):
        if type(point) is not list or len(point)!=3:
            raise ValueError("Source mesh points must be 3D coordinates")
        pts.append([_float(x) for x in point])
        ji=ids[i]
        wi=weights[i]
        if (type(ji) is not list or type(wi) is not list or
            not 1<=len(ji)<=MAX_INFLUENCES or len(ji)!=len(wi)):
            raise ValueError("1..4 joint influences required per skin vertex")
        if any(type(x) is not int or not 0<=x<joint_count for x in ji):
            raise ValueError("Source skin refers to a non-existent skeleton joint")
        if len(set(ji))!=len(ji):
            raise ValueError("Duplicate joint influence at the same vertex")
        values=[_float(x) for x in wi]
        if any(x<0 or x>1 for x in values) or not math.isclose(
            sum(values),1.,rel_tol=0,abs_tol=1e-5):
            raise ValueError("Skin influences must be normalized nonnegative weights")
        joints.append(ji+[0]*(MAX_INFLUENCES-len(ji)))
        normalized_weights.append(values+[0.]*(MAX_INFLUENCES-len(wi)))
    polygons=[]
    total_triangles=0
    for face in faces:
        if (type(face) is not list or not 3<=len(face)<=8 or
            any(type(i) is not int or i<0 or i>=len(points) for i in face) or
            len(set(face))!=len(face)):
            raise ValueError("Unsupported source mesh face topology")
        total_triangles+=len(face)-2
        if total_triangles>MAX_SKIN_FACES*2:
            raise ValueError("Too many triangles in bounded source skin mesh")
        polygons.append(face[:])
    color=skin["display_color"]
    if type(color) is not list or len(color)!=3:
        raise ValueError("Source material preview requires RGB color")
    rgb=[_float(x) for x in color]
    if any(not 0<=x<=1 for x in rgb):
        raise ValueError("Material preview color out of RGB domain")
    shapes=skin.get("blend_shapes",[])
    if type(shapes) is not list or len(shapes)>MAX_FACIAL_SHAPES:
        raise ValueError("Too many original facial shape targets")
    bound_shapes=[]
    names=set()
    for original in shapes:
        if type(original) is not dict or set(original)!={"name","offsets"}:
            raise ValueError("A USD blend shape requires a name and mesh point offsets")
        name=original["name"]
        if type(name) is not str or not SHAPE_NAME.fullmatch(name) or name in names:
            raise ValueError("Duplicate/unsafe original facial shape identity")
        names.add(name)
        offsets=original["offsets"]
        if type(offsets) is not list or len(offsets)!=len(pts):
            raise ValueError("Native face blend shape does not match original mesh")
        verified=[]
        for vec in offsets:
            if type(vec) is not list or len(vec)!=3:
                raise ValueError("Face shape offset must contain exactly XYZ")
            values=[_float(x) for x in vec]
            if any(abs(x)>2.0 for x in values):
                raise ValueError("Unbounded original facial mesh displacement")
            verified.append(values)
        bound_shapes.append({"name":name,"offsets":verified})
    authored_uv=skin.get("mesh_uvs")
    if authored_uv is not None and (
        type(authored_uv) is not list or len(authored_uv)!=len(pts) or
        any(type(uv) is not list or len(uv)!=2 or
            any(type(x) not in (int,float) or not math.isfinite(x) or
                abs(x)>1024 for x in uv) for uv in authored_uv)):
        raise ValueError("Actor UV primvar must match original skinned vertices")
    face_uvs=skin.get("face_uvs")
    if authored_uv is not None and face_uvs is not None:
        raise ValueError("Original skinned st interpolation ambiguous")
    if face_uvs is not None and (
        type(face_uvs) is not list or len(face_uvs)!=len(polygons) or
        any(type(face) is not list or len(face)!=len(polygons[i]) or
            any(type(uv) is not list or len(uv)!=2 or
                any(type(v) not in (int,float) or
                    not math.isfinite(v) or abs(v)>1024
                    for v in uv) for uv in face)
            for i,face in enumerate(face_uvs))):
        raise ValueError("Skinned face-varying UVs must match original polygons")
    texture=skin.get("texture")
    if texture is not None:
        from backend.nvp_native_usd_texture import FORMAT as TEXTURE_FORMAT,PREFIX
        if ((authored_uv is None and face_uvs is None) or
            type(texture) is not dict or
            set(texture)!={"format","sha256","width","height",
                "color_space","wrap","usd_asset_path","source_modified"} or
            texture["format"]!=TEXTURE_FORMAT or
            type(texture["sha256"]) is not str or
            not re.fullmatch(r"[0-9a-f]{64}",texture["sha256"]) or
            texture["usd_asset_path"]!=PREFIX+texture["sha256"] or
            texture["color_space"]!="sRGB" or
            texture["wrap"]!="repeat" or
            texture["source_modified"] is not False or
            type(texture["width"]) is not int or
            type(texture["height"]) is not int or
            not 1<=texture["width"]<=2048 or
            not 1<=texture["height"]<=2048):
            raise ValueError("Skinned PNG texture must reference a verified source blob")
    pbr_maps=skin.get("pbr_maps")
    if pbr_maps is not None:
        from backend.nvp_wo2_pbr_channels import CHANNELS
        from backend.nvp_native_usd_texture import FORMAT as TF,PREFIX
        if (authored_uv is None and face_uvs is None or
            type(pbr_maps) is not dict or not pbr_maps or
            len(pbr_maps)>4 or any(key not in CHANNELS for key in pbr_maps)):
            raise ValueError("Skinned PBR maps require original authored UVs")
        for descriptor in pbr_maps.values():
            if (type(descriptor) is not dict or
                descriptor.get("format")!=TF or
                type(descriptor.get("sha256")) is not str or
                not re.fullmatch(r"[0-9a-f]{64}",descriptor["sha256"]) or
                descriptor.get("usd_asset_path")!=PREFIX+descriptor["sha256"] or
                descriptor.get("source_modified") is not False):
                raise ValueError("Skinned PBR source descriptor is invalid")
    material=skin.get("preview_material",{"roughness":0.8,"metallic":0.05})
    if (type(material) is not dict or
        set(material)!={"roughness","metallic"} or
        any(type(v) not in (int,float) or
            not math.isfinite(v) or not 0<=v<=1 for v in material.values())):
        raise ValueError("Original USD PreviewSurface needs bounded roughness/metallic")
    return {"points":pts,"faces":polygons,"joint_indices":joints,
            "joint_weights":normalized_weights,"display_color":rgb,
            "blend_shapes":bound_shapes,
            "mesh_uvs":([[float(x) for x in uv] for uv in authored_uv]
                        if authored_uv is not None else None),
            "face_uvs":([[[float(x) for x in uv] for uv in face]
                          for face in face_uvs]
                         if face_uvs is not None else None),
            "texture":texture,
            "pbr_maps":pbr_maps,
            "preview_material":{k:float(v) for k,v in material.items()}}


def author_skin_mesh(stage,actor_path,skeleton_path,skin,joint_count):
    from pxr import Gf,Sdf,UsdGeom,UsdSkel,UsdShade,Vt
    bound=normalize_skin(skin,joint_count)
    mesh=UsdGeom.Mesh.Define(stage,actor_path+SKIN_MESH_SUFFIX)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*x) for x in bound["points"]]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray(
        [len(face) for face in bound["faces"]]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray(
        [i for face in bound["faces"] for i in face]))
    mesh.GetDoubleSidedAttr().Set(True)
    if bound["mesh_uvs"] is not None:
        st=UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st",Sdf.ValueTypeNames.TexCoord2fArray,"vertex")
        st.Set(Vt.Vec2fArray([Gf.Vec2f(*uv) for uv in bound["mesh_uvs"]]))
    elif bound["face_uvs"] is not None:
        st=UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st",Sdf.ValueTypeNames.TexCoord2fArray,"faceVarying")
        st.Set(Vt.Vec2fArray([Gf.Vec2f(*uv)
                              for face in bound["face_uvs"] for uv in face]))
    mesh.GetDisplayColorPrimvar().Set(Vt.Vec3fArray(
        [Gf.Vec3f(*bound["display_color"])]))
    binding=UsdSkel.BindingAPI.Apply(mesh.GetPrim())
    if not binding:
        raise RuntimeError("Could not apply native UsdSkelBindingAPI to authored actor mesh")
    if not binding.CreateSkeletonRel().SetTargets([Sdf.Path(skeleton_path)]):
        raise RuntimeError("Could not bind actor mesh to source skeleton")
    if not binding.CreateGeomBindTransformAttr().Set(Gf.Matrix4d(1.0)):
        raise RuntimeError("Invalid original mesh bind pose")
    indexes=binding.CreateJointIndicesPrimvar(False,MAX_INFLUENCES)
    influence_weights=binding.CreateJointWeightsPrimvar(False,MAX_INFLUENCES)
    if (not indexes.Set(Vt.IntArray([i for row in bound["joint_indices"] for i in row])) or
        not influence_weights.Set(Vt.FloatArray(
            [w for row in bound["joint_weights"] for w in row]))):
        raise RuntimeError("Could not author native USD per-vertex joint influences")
    # The actual USD PreviewSurface is source geometry authority. The
    # Three.js viewport reads these exact typed shader inputs, not a
    # guessed RGB actor material or external texture.
    material_path=actor_path+"/Rig/Material"
    material=UsdShade.Material.Define(stage,material_path)
    shader=UsdShade.Shader.Define(stage,material_path+"/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*bound["display_color"]))
    if bound["texture"] is not None:
        tex=UsdShade.Shader.Define(stage,material_path+"/Texture")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file",Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath(bound["texture"]["usd_asset_path"]))
        tex.CreateInput("sourceColorSpace",Sdf.ValueTypeNames.Token).Set("sRGB")
        tex.CreateInput("wrapS",Sdf.ValueTypeNames.Token).Set("repeat")
        tex.CreateInput("wrapT",Sdf.ValueTypeNames.Token).Set("repeat")
        st=UsdShade.Shader.Define(stage,material_path+"/Primvar")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname",Sdf.ValueTypeNames.Token).Set("st")
        tex.CreateInput("st",Sdf.ValueTypeNames.Float2).ConnectToSource(
            st.CreateOutput("result",Sdf.ValueTypeNames.Float2))
        shader.GetInput("diffuseColor").ConnectToSource(
            tex.CreateOutput("rgb",Sdf.ValueTypeNames.Float3))
    shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(
        bound["preview_material"]["roughness"])
    shader.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(
        bound["preview_material"]["metallic"])
    shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(),"surface")
    if bound["texture"] is not None:
        from backend.nvp_wo2_openpbr import author_openpbr_texture
        author_openpbr_texture(stage,material_path,material,
            bound["texture"],bound["preview_material"]["roughness"],
            bound["preview_material"]["metallic"])
    else:
        from backend.nvp_wo2_openpbr import author_openpbr_scalar
        author_openpbr_scalar(stage,material_path,material,
            bound["display_color"],bound["preview_material"]["roughness"],
            bound["preview_material"]["metallic"])
    if bound.get("pbr_maps"):
        from backend.nvp_wo2_pbr_channels import author_pbr_maps
        author_pbr_maps(stage,material_path,shader,
            UsdShade.Shader(stage.GetPrimAtPath(material_path+"/OpenPBR")),
            bound["pbr_maps"])
    if not UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material):
        raise RuntimeError("Unable to bind original actor USD PreviewSurface")
    blend_paths=[]
    shape_names=[]
    for shape in bound["blend_shapes"]:
        name=shape["name"]
        blend=UsdSkel.BlendShape.Define(
            stage,actor_path+SKIN_MESH_SUFFIX+"/Blend_"+name)
        offsets=Vt.Vec3fArray([Gf.Vec3f(*p) for p in shape["offsets"]])
        if not blend.GetOffsetsAttr().Set(offsets):
            raise RuntimeError("Failed to author original USD facial shape offsets")
        blend_paths.append(blend.GetPrim().GetPath())
        shape_names.append(name)
    if shape_names:
        if (not binding.CreateBlendShapesAttr().Set(Vt.TokenArray(shape_names))
            or not binding.CreateBlendShapeTargetsRel().SetTargets(blend_paths)):
            raise RuntimeError("USD face shape binding is not authoritative")
    return {
        "mesh_path":actor_path+SKIN_MESH_SUFFIX,
        "source_vertex_count":len(bound["points"]),
        "source_face_count":len(bound["faces"]),
        "source_original_uvs_authored":(bound["mesh_uvs"] is not None or
                                      bound["face_uvs"] is not None),
        "source_original_png_texture_authored":bound["texture"] is not None,
        "skinning_method":"classicLinear",
        "geom_bind_transform":"identity",
        "max_influences":MAX_INFLUENCES,
        "human_actor_geometry_preview":True,
        "facial_shape_names":shape_names,
        "facial_shape_count":len(shape_names),
        "facial_deformation_rendered":len(shape_names)>0,
        "preview_material_path":material_path,
    }


def read_original_preview_surface(stage,mesh_prim,actor_path):
    """Read the actual frozen UsdShade shader, not assumed actor colors."""
    from pxr import UsdGeom,UsdShade
    expected=actor_path+"/Rig/Material"
    if not mesh_prim.HasAPI(UsdShade.MaterialBindingAPI):
        # Older immutable Takes legitimately predate authored
        # UsdPreviewSurface. They STILL have actual original UsdGeom
        # skinned meshes and displayColor. Never replace that actor
        # geometry with a gizmo just because only displayColor exists.
        raw=UsdGeom.Mesh(mesh_prim).GetDisplayColorPrimvar().Get()
        if raw is None or len(raw)!=1:
            raise RuntimeError("Legacy USD actor has no original color source")
        color=[float(v) for v in raw[0]]
        if any(not math.isfinite(v) or not 0<=v<=1 for v in color):
            raise RuntimeError("Legacy original actor color invalid")
        return {"format":"nvp.original_usd_displaycolor_preview.v1",
                "material_path":None,"base_color_rgb":color,
                "roughness":0.8,"metallic":0.05,
                "roughness_metallic_authored":False,
                "texture_images_loaded":False,
                "original_source_modified":False}
    binding=UsdShade.MaterialBindingAPI(mesh_prim)
    bound,relationship=binding.ComputeBoundMaterial()
    if (not bound or str(bound.GetPath())!=expected):
        raise RuntimeError("Skinned actor's source USD material binding changed")
    shader=UsdShade.Shader(
        stage.GetPrimAtPath(expected+"/PreviewSurface"))
    if not shader or shader.GetIdAttr().Get()!="UsdPreviewSurface":
        raise RuntimeError("Original actor material is not a supported USD PreviewSurface")
    values={}
    for name in ("diffuseColor","roughness","metallic"):
        inp=shader.GetInput(name)
        if not inp:
            raise RuntimeError("Authored actor shader input missing: "+name)
        # Preserve the authored input value even with a shader connection.
        values[name]=inp.GetAttr().Get()
    color=[float(x) for x in values["diffuseColor"]]
    roughness=float(values["roughness"])
    metallic=float(values["metallic"])
    if (any(not math.isfinite(v) or not 0<=v<=1 for v in color) or
        any(not math.isfinite(v) or not 0<=v<=1
            for v in (roughness,metallic))):
        raise RuntimeError("Original source actor material parameters untrusted")
    openpbr=stage.GetPrimAtPath(expected+"/OpenPBR")
    if openpbr:
        if shader.GetInput("diffuseColor").HasConnectedSource():
            # The source image identity is verified by the native pose reader
            # against the original indexed rig descriptor before display.
            image_node=UsdShade.Shader(stage.GetPrimAtPath(
                expected+"/MtlxImage"))
            source=image_node.GetInput("file").GetAttr().Get() if image_node else None
            if source is None:
                raise RuntimeError("Source rig MaterialX image missing")
            # Verify graph node/terminal identity here; complete blob digest
            # re-verification occurs using the exact manifest in live skins.
            from backend.nvp_wo2_openpbr import verify_openpbr_texture
            from backend.nvp_native_usd_texture import PREFIX,FORMAT
            path=str(source.path)
            if not path.startswith(PREFIX) or len(path)!=len(PREFIX)+64:
                raise RuntimeError("Untrusted rig MaterialX image source")
            descriptor={"format":FORMAT,"sha256":path[len(PREFIX):],
                "usd_asset_path":path,"color_space":"sRGB","wrap":"repeat",
                "source_modified":False}
            verify_openpbr_texture(
                stage,expected,bound,descriptor,roughness,metallic)
        else:
            from backend.nvp_wo2_openpbr import verify_openpbr_scalar
            verify_openpbr_scalar(stage,expected,bound,color,roughness,metallic)
    return {"format":"nvp.original_usd_preview_surface.v1",
            "material_path":expected,"base_color_rgb":color,
            "roughness":roughness,"metallic":metallic,
            "roughness_metallic_authored":True,
            "texture_images_loaded":False,"original_source_modified":False}


def evaluate_skin(stage,mesh_prim,actor_path,tick):
    """Read REAL USD skin binding and native joint pose; produce deformed vertices.

    Per-vertex classic linear blend skinning uses USD's bind-pose definition.
    Source geometry and animation are not altered; resulting points are
    a disposable exact-time derivative for the contained Blender renderer.
    """
    from pxr import Gf,Usd,UsdGeom,UsdSkel
    t=Usd.TimeCode(float(tick))
    if not mesh_prim.IsA(UsdGeom.Mesh):
        raise RuntimeError("Source character skin must be native UsdGeom.Mesh")
    path=str(mesh_prim.GetPath())
    if path!=actor_path+SKIN_MESH_SUFFIX:
        raise RuntimeError("Skin is not at the declared actor's bounded source path")
    mesh=UsdGeom.Mesh(mesh_prim)
    if not mesh_prim.HasAPI(UsdSkel.BindingAPI):
        raise RuntimeError("Character mesh is missing native USD skin binding")
    binding=UsdSkel.BindingAPI(mesh_prim)
    targets=binding.GetSkeletonRel().GetTargets()
    if targets!=[mesh_prim.GetPath().GetParentPath().AppendChild("Skeleton")]:
        raise RuntimeError("Character mesh no longer targets the original source skeleton")
    skel=UsdSkel.Skeleton(stage.GetPrimAtPath(targets[0]))
    if not skel:
        raise RuntimeError("Native bound USD skeleton is missing")
    cache=UsdSkel.Cache()
    query=cache.GetSkelQuery(skel)
    if not query:
        raise RuntimeError("Source skeletal animation could not be resolved")
    transforms=query.ComputeSkinningTransforms(t)
    if transforms is None or len(transforms)==0:
        raise RuntimeError("No native OpenUSD skinning transforms at source time")
    bind=binding.GetGeomBindTransformAttr().Get()
    if bind is None or bind!=Gf.Matrix4d(1.0):
        raise RuntimeError("This bounded NVP source renderer only supports identity mesh bind")
    # Evaluate the original USDSkel blend-shape offsets BEFORE skinning,
    # as required by the USD schema. This does not mutate the original
    # mesh or author a replacement performance Take.
    blend_names=list(binding.GetBlendShapesAttr().Get() or [])
    blend_targets=list(binding.GetBlendShapeTargetsRel().GetTargets())
    active_shapes=[]
    if blend_names or blend_targets:
        if len(blend_names)!=len(blend_targets):
            raise RuntimeError("Broken USD original facial shape binding")
        animation=UsdSkel.Animation(
            stage.GetPrimAtPath(actor_path+"/Rig/Skeleton/Animation"))
        if not animation:
            raise RuntimeError("Missing original USD facial performance animation")
        frame_names=list(animation.GetBlendShapesAttr().Get() or [])
        weights=animation.GetBlendShapeWeightsAttr().Get(t)
        if (weights is None or len(weights)!=len(frame_names) or
            set(blend_names)!=set(frame_names)):
            raise RuntimeError("Source facial performance no longer matches USD binding")
        for name,target in zip(blend_names,blend_targets):
            shape=UsdSkel.BlendShape(stage.GetPrimAtPath(target))
            if (not shape or str(target)!=
                    actor_path+SKIN_MESH_SUFFIX+"/Blend_"+str(name)
                    or shape.GetAuthoredInbetweens()):
                raise RuntimeError("Unsupported or changed original facial shape")
            offsets=shape.GetOffsetsAttr().Get()
            if offsets is None:
                raise RuntimeError("Source face blend offsets missing")
            weight=float(weights[frame_names.index(name)])
            if not math.isfinite(weight) or not 0<=weight<=1:
                raise RuntimeError("Original facial animation weight is unbounded")
            active_shapes.append((weight,offsets))
    raw=mesh.GetPointsAttr().Get(t)
    ids=binding.GetJointIndicesPrimvar().Get()
    weights=binding.GetJointWeightsPrimvar().Get()
    if raw is None or ids is None or weights is None:
        raise RuntimeError("Missing authored source actor geometry/weights")
    if len(raw)>MAX_SKIN_VERTICES or len(ids)!=4*len(raw) or len(weights)!=4*len(raw):
        raise RuntimeError("Frozen source joint influence arrays changed")
    if any(len(offsets)!=len(raw) for _,offsets in active_shapes):
        raise RuntimeError("Original USD blend shape topology changed")
    points=[]
    for n,p in enumerate(raw):
        face_point=Gf.Vec3d(*p)
        for weight,offsets in active_shapes:
            face_point+=Gf.Vec3d(*offsets[n])*weight
        out=Gf.Vec3d(0)
        total=0.
        for influence in range(MAX_INFLUENCES):
            joint=int(ids[n*MAX_INFLUENCES+influence])
            weight=float(weights[n*MAX_INFLUENCES+influence])
            if not 0<=joint<len(transforms) or not math.isfinite(weight) or weight<0:
                raise RuntimeError("Invalid frozen source skin weights")
            if weight:
                v=transforms[joint].Transform(face_point)
                out+=Gf.Vec3d(v)*weight
                total+=weight
        if not math.isclose(total,1.,abs_tol=1e-5):
            raise RuntimeError("Source skin vertex influence weights no longer normalized")
        coords=[_float(x) for x in out]
        points.append(coords)
    return {
        "source_mesh_path":path,
        "deformed_points":points,
        "skinning_evaluated":True,
        "usd_skin_binding_verified":True,
        "joint_count":len(transforms),
        "facial_deformation_evaluated":bool(active_shapes),
        "original_blend_shape_count":len(active_shapes),
        "source_preview_material":read_original_preview_surface(
            stage,mesh_prim,actor_path),
    }
