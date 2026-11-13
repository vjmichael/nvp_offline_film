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

MAX_SKIN_VERTICES=8192
MAX_SKIN_FACES=16384
MAX_INFLUENCES=4
SKIN_MESH_SUFFIX="/Rig/CharacterMesh"


def _float(value):
    if type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1_000:
        raise ValueError("Skinned source geometry requires bounded finite coordinates")
    return float(value)


def normalize_skin(skin,joint_count):
    expected={"points","faces","joint_indices","joint_weights","display_color"}
    if (type(skin) is not dict or not expected.issubset(skin) or
        not set(skin)<=expected|{"roughness","source_glb_sha256"}):
        raise ValueError("Skin requires exact typed point/topology/joint influence fields")
    points=skin["points"]
    faces=skin["faces"]
    ids=skin["joint_indices"]
    weights=skin["joint_weights"]
    if (type(points) is not list or not 3<=len(points)<=MAX_SKIN_VERTICES or
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
    out={"points":pts,"faces":polygons,"joint_indices":joints,
         "joint_weights":normalized_weights,"display_color":rgb}
    if "source_glb_sha256" in skin:
        from backend.nvp_film_index import _sha
        _sha(skin["source_glb_sha256"])
        rough=skin.get("roughness")
        if type(rough) not in (int,float) or not math.isfinite(rough) or not 0<=rough<=1:
            raise ValueError("Imported GLB PBR roughness must be original authored source")
        out.update(source_glb_sha256=skin["source_glb_sha256"],
                   roughness=float(rough))
    elif "roughness" in skin:
        raise ValueError("Authored skin roughness requires imported original PBR source")
    return out


def author_skin_mesh(stage,actor_path,skeleton_path,skin,joint_count):
    from pxr import Gf,Sdf,UsdGeom,UsdSkel,Vt
    bound=normalize_skin(skin,joint_count)
    mesh=UsdGeom.Mesh.Define(stage,actor_path+SKIN_MESH_SUFFIX)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*x) for x in bound["points"]]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray(
        [len(face) for face in bound["faces"]]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray(
        [i for face in bound["faces"] for i in face]))
    mesh.GetDoubleSidedAttr().Set(True)
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
    if "source_glb_sha256" in bound:
        # Native Cycles reads this true source PBR via UsdShade; it must NOT
        # silently substitute a white material for a skinned actor.
        from pxr import UsdShade
        material=UsdShade.Material.Define(
            stage,actor_path+"/Rig/OriginalGLBMaterial")
        shader=UsdShade.Shader.Define(
            stage,actor_path+"/Rig/OriginalGLBMaterial/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*bound["display_color"]))
        shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(
            bound["roughness"])
        shader.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(0.0)
        if not material.CreateSurfaceOutput().ConnectToSource(
                shader.ConnectableAPI(),"surface"):
            raise RuntimeError("Imported original PBR material USD binding failed")
        if not UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material):
            raise RuntimeError("Imported skinned mesh lacks original USD material binding")
        mesh.GetPrim().CreateAttribute(
            "nvp:sourceGLBSHA256",Sdf.ValueTypeNames.String).Set(
                bound["source_glb_sha256"])
    return {
        "mesh_path":actor_path+SKIN_MESH_SUFFIX,
        "source_vertex_count":len(bound["points"]),
        "source_face_count":len(bound["faces"]),
        "skinning_method":"classicLinear",
        "geom_bind_transform":"identity",
        "max_influences":MAX_INFLUENCES,
        "human_actor_geometry_preview":True,
        "facial_deformation_rendered":False,
    }


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
    raw=mesh.GetPointsAttr().Get(t)
    ids=binding.GetJointIndicesPrimvar().Get()
    weights=binding.GetJointWeightsPrimvar().Get()
    if raw is None or ids is None or weights is None:
        raise RuntimeError("Missing authored source actor geometry/weights")
    if len(raw)>MAX_SKIN_VERTICES or len(ids)!=4*len(raw) or len(weights)!=4*len(raw):
        raise RuntimeError("Frozen source joint influence arrays changed")
    points=[]
    for n,p in enumerate(raw):
        out=Gf.Vec3d(0)
        total=0.
        for influence in range(MAX_INFLUENCES):
            joint=int(ids[n*MAX_INFLUENCES+influence])
            weight=float(weights[n*MAX_INFLUENCES+influence])
            if not 0<=joint<len(transforms) or not math.isfinite(weight) or weight<0:
                raise RuntimeError("Invalid frozen source skin weights")
            if weight:
                v=transforms[joint].Transform(Gf.Vec3d(*p))
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
        "facial_deformation_evaluated":False,
    }
