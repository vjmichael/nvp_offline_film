"""P1-B: convert actual immutable, already registered rigged GLB bytes to USD.

This is a constrained, deterministic, offline glTF mesh/skin reader. It never
runs model-provided scripts, downloads textures or invents a second mesh. More
complex material networks/animation are rejected rather than approximated.
The original GLB SHA, declared rights, source joint hierarchy and mesh
accessors remain independently recoverable from FilmIndex after restart.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct

from backend.nvp_character_assets import CharacterAssets, inspect_rigged_glb
from backend.nvp_film_index import FilmIndex, _id, _sha
from backend.nvp_openusd_skinning import normalize_skin, MAX_SKIN_VERTICES
from backend.nvp_openusd_skeleton import MAX_JOINTS
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.p1b.original_glb_usd_skin.v1"
COMPONENT={5121:("B",1),5123:("H",2),5125:("I",4),5126:("f",4)}
SHAPES={"SCALAR":1,"VEC3":3,"VEC4":4,"MAT4":16}
MAX_MATRIX_VALUE=1e6


def _unpack_glb(payload):
    inspect_rigged_glb(payload)  # original conservative structural validator
    length=struct.unpack_from("<I",payload,12)[0]
    doc=json.loads(payload[20:20+length].rstrip(b" \x00"))
    start=20+length
    binary_len,kind=struct.unpack_from("<II",payload,start)
    if kind!=0x004e4942:
        raise ValueError("Original GLB binary payload is missing")
    return doc,payload[start+8:start+8+binary_len]


def _accessor(doc,binary,number,*,type_name,types):
    accs=doc["accessors"]
    if type(number) is not int or not 0<=number<len(accs):
        raise ValueError("Source GLB accessor identity invalid")
    desc=accs[number]
    kind=desc.get("type")
    ctype=desc.get("componentType")
    if kind!=type_name or ctype not in types:
        raise ValueError("Unsupported original GLB skin/geometry encoding")
    fmt,size=COMPONENT[ctype]
    count=desc["count"]
    view=doc["bufferViews"][desc["bufferView"]]
    width=size*SHAPES[kind]
    stride=view.get("byteStride",width)
    offset=view.get("byteOffset",0)+desc.get("byteOffset",0)
    fmt="<"+fmt*SHAPES[kind]
    values=[]
    for i in range(count):
        row=list(struct.unpack_from(fmt,binary,offset+i*stride))
        if ctype==5126 and any(not math.isfinite(v) for v in row):
            raise ValueError("Nonfinite original GLB mesh or bind transform")
        if (desc.get("normalized") is True and ctype in (5121,5123)):
            norm=255.0 if ctype==5121 else 65535.0
            row=[float(v)/norm for v in row]
        values.append(row)
    return values


def _matrix(value):
    from pxr import Gf
    if type(value) is not list or len(value)!=16 or any(
        type(x) not in (int,float) or not math.isfinite(x)
        or abs(x)>MAX_MATRIX_VALUE for x in value):
        raise ValueError("Invalid finite source GLB transform matrix")
    mat=Gf.Matrix4d(*[float(x) for x in value])
    if not math.isfinite(mat.GetDeterminant()) or abs(mat.GetDeterminant())<1e-8:
        raise ValueError("Singular source GLB bone/skin transform")
    return mat


def _local_transform(node):
    from pxr import Gf
    if "matrix" in node:
        if any(k in node for k in ("rotation","translation","scale")):
            raise ValueError("GLB matrix cannot also have TRS values")
        return _matrix(node["matrix"])
    t=node.get("translation",[0,0,0])
    s=node.get("scale",[1,1,1])
    q=node.get("rotation",[0,0,0,1])
    if (any(type(v) is not list or len(v)!=n for v,n in
            ((t,3),(s,3),(q,4))) or
        any(type(v) not in (int,float) or not math.isfinite(v) or
            abs(v)>10000 for v in [*t,*s,*q]) or
        any(abs(v)<1e-8 for v in s)):
        raise ValueError("Invalid source GLB bone TRS")
    x,y,z,w=map(float,q)
    norm=math.sqrt(x*x+y*y+z*z+w*w)
    if not .999<=norm<=1.001:
        raise ValueError("Unnormalized source GLB joint rotation")
    x,y,z,w=(v/norm for v in (x,y,z,w))
    # glTF column-vector R transposed into OpenUSD Gf row-vector R.
    rows=[
      [1-2*(y*y+z*z),2*(x*y+z*w),2*(x*z-y*w),0],
      [2*(x*y-z*w),1-2*(x*x+z*z),2*(y*z+x*w),0],
      [2*(x*z+y*w),2*(y*z-x*w),1-2*(x*x+y*y),0],
      [0,0,0,1],
    ]
    for i in range(3):
        rows[i]=[v*float(s[i]) for v in rows[i]]
        rows[3][i]=float(t[i])
    return Gf.Matrix4d(*[v for row in rows for v in row])


def _values(mat):
    result=[float(mat[i][j]) for i in range(4) for j in range(4)]
    if any(not math.isfinite(x) or abs(x)>MAX_MATRIX_VALUE for x in result):
        raise ValueError("Source joint transform exceeds NVP bounds")
    return result


def extract_original_glb_skin(payload):
    """Return original geometry + joint poses, never a procedural mannequin."""
    info=inspect_rigged_glb(payload)
    doc,binary=_unpack_glb(payload)
    from pxr import Gf
    nodes=doc["nodes"]
    skins=doc["skins"][0]
    source_joint_ids=skins["joints"]
    if len(source_joint_ids)>MAX_JOINTS:
        raise ValueError("Native original-character preview joint cap exceeded")
    parents={}
    for node_i,node in enumerate(nodes):
        for child in node.get("children",[]):
            if type(child) is not int or not 0<=child<len(nodes) or child in parents:
                raise ValueError("Invalid or multiply-parented GLB joint hierarchy")
            parents[child]=node_i
    visiting=set()
    world_cache={}
    def world(n):
        if n in world_cache:return world_cache[n]
        if n in visiting:raise ValueError("Cyclic original GLB joint hierarchy")
        visiting.add(n)
        local=_local_transform(nodes[n])
        mat=local*world(parents[n]) if n in parents else local
        visiting.remove(n)
        world_cache[n]=mat
        return mat
    for n in source_joint_ids:world(n)
    joint_set=set(source_joint_ids)
    order=[]
    def append(n):
        p=parents.get(n)
        if p in joint_set and p not in order:append(p)
        if n not in order:order.append(n)
    for n in source_joint_ids:append(n)
    reorder={source_joint_ids.index(node):new for new,node in enumerate(order)}
    names={}
    for i,n in enumerate(order):
        p=parents.get(n)
        own="Bone"+str(i).zfill(3)
        names[n]=(names[p]+"/"+own) if p in names else own
    basis=Gf.Matrix4d(1,0,0,0, 0,0,1,0, 0,-1,0,0, 0,0,0,1)
    invbasis=basis.GetInverse()
    rest=[]
    binds=[]
    original_ibm=None
    if "inverseBindMatrices" in skins:
        original_ibm=_accessor(doc,binary,skins["inverseBindMatrices"],
                              type_name="MAT4",types={5126})
    for node in order:
        p=parents.get(node)
        local=(world(node)*world(p).GetInverse() if p in joint_set
               else world(node))
        rest.append(_values(invbasis*local*basis))
        old_i=source_joint_ids.index(node)
        actual_world=world(node)
        if original_ibm is not None:
            inverse=_matrix(original_ibm[old_i])
            if any(abs(v)>1e-3 for v in
                   _values(inverse*actual_world-Gf.Matrix4d(1))):
                raise ValueError("Unsupported GLB inverse bind does not match authoritative joint world")
            source_bind=inverse.GetInverse()
        else:
            # glTF specifies an identity inverse bind when omitted.
            if any(abs(v)>1e-5 for v in
                   _values(actual_world-Gf.Matrix4d(1))):
                raise ValueError("Nonidentity glTF bind requires explicit inverseBindMatrices")
            source_bind=Gf.Matrix4d(1)
        binds.append(_values(invbasis*source_bind*basis))
    bound=[n for n in nodes if n.get("skin")==0]
    if len(bound)!=1 or bound[0].get("mesh") not in range(len(doc["meshes"])):
        raise ValueError("This original source profile requires one unambiguous skinned mesh")
    if any(abs(v)>1e-5 for v in _values(world(nodes.index(bound[0]))-Gf.Matrix4d(1))):
        raise ValueError("Unsupported nonidentity skinned mesh node transform")
    prims=doc["meshes"][bound[0]["mesh"]].get("primitives",[])
    if type(prims) is not list or len(prims)!=1 or prims[0].get("mode",4)!=4:
        raise ValueError("Original skin must contain one indexed/nonindexed triangle primitive")
    prim=prims[0]
    attributes=prim["attributes"]
    pos=_accessor(doc,binary,attributes["POSITION"],
                  type_name="VEC3",types={5126})
    j=_accessor(doc,binary,attributes["JOINTS_0"],
                type_name="VEC4",types={5121,5123})
    weights=_accessor(doc,binary,attributes["WEIGHTS_0"],
                      type_name="VEC4",types={5121,5123,5126})
    if not 3<=len(pos)<=MAX_SKIN_VERTICES:
        raise ValueError("Original rigged GLB exceeds bounded source mesh capacity")
    if not (len(pos)==len(j)==len(weights)):
        raise ValueError("Original skinned mesh source accessor counts disagree")
    if "indices" in prim:
        ids=_accessor(doc,binary,prim["indices"],
                      type_name="SCALAR",types={5121,5123,5125})
        triangle_indices=[row[0] for row in ids]
    else:
        triangle_indices=list(range(len(pos)))
    if len(triangle_indices)%3 or not triangle_indices:
        raise ValueError("Original mesh has incomplete triangle face topology")
    faces=[triangle_indices[i:i+3] for i in range(0,len(triangle_indices),3)]
    if any(type(idx) is not int or not 0<=idx<len(pos) for idx in triangle_indices):
        raise ValueError("Original GLB face references a missing source vertex")
    materials=doc.get("materials",[])
    if type(prim.get("material")) is not int or not 0<=prim["material"]<len(materials):
        raise ValueError("Film source GLB needs an authored PBR material")
    material=materials[prim["material"]]
    pbr=material.get("pbrMetallicRoughness",{})
    if (material.get("alphaMode","OPAQUE")!="OPAQUE" or
        material.get("extensions") or pbr.get("baseColorTexture") or
        pbr.get("metallicRoughnessTexture") or material.get("normalTexture") or
        material.get("emissiveTexture") or material.get("occlusionTexture")):
        raise ValueError("Original source material graph needs specialist native conversion")
    metal=pbr.get("metallicFactor",1.0)
    if type(metal) not in (int,float) or not math.isfinite(metal) or abs(metal)>1e-6:
        raise ValueError("Metallic GLB material requires an authored metallic preview renderer")
    color=pbr.get("baseColorFactor",[1,1,1,1])
    rough=pbr.get("roughnessFactor",1.0)
    if (type(color) is not list or len(color)!=4 or
        any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in color)
        or color[3]!=1 or type(rough) not in (int,float) or not math.isfinite(rough)
        or not 0<=rough<=1):
        raise ValueError("Unsupported original GLB PBR material values")
    faces_out=[]
    for tri in faces:
        if len(set(tri))!=3:
            raise ValueError("Degenerate original GLB triangle indices")
        faces_out.append([int(i) for i in tri])
    source_points=[[float(v[0]),-float(v[2]),float(v[1])] for v in pos]
    mapped=[]
    norm_weights=[]
    for old_ids,w in zip(j,weights):
        nonzero=[(reorder[int(i)],float(x)) for i,x in zip(old_ids,w) if x>0]
        if not nonzero or len(nonzero)>4 or any(
            type(i) not in (int,float) or not float(i).is_integer() or
            not 0<=int(i)<len(source_joint_ids) for i in old_ids):
            raise ValueError("Original GLB joint influence invalid")
        if len({i for i,_ in nonzero})!=len(nonzero):
            raise ValueError("Repeated original joint influence")
        total=sum(x for _,x in nonzero)
        if not 0.98<=total<=1.02:
            raise ValueError("Original GLB vertex weights not normalized")
        mapped.append([i for i,_ in nonzero])
        norm_weights.append([v/total for _,v in nonzero])
    skin={"points":source_points,"faces":faces_out,
          "joint_indices":mapped,"joint_weights":norm_weights,
          "display_color":[float(v) for v in color[:3]],
          "roughness":float(rough),"source_glb_sha256":info["sha256"]}
    normalize_skin(skin,len(order))
    return {"source_joint_names":[nodes[n]["name"] for n in order],
            "joints":[names[n] for n in order],
            "rest_transforms":rest,"bind_transforms":binds,
            "skin":skin,"original_vertex_count":len(source_points),
            "original_triangle_count":len(faces_out)}


class ImportedCharacterSources:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Native FilmIndex project required")
        self.index=index

    def _registered(self,project_id,character_asset_id):
        _id(character_asset_id,"registered rigged character")
        store=CharacterAssets(self.index.studio)
        with self.index.studio._connection() as db:
            rec=store._asset(db,project_id,character_asset_id)
        sha=_sha(rec["sha"])
        root=store.root
        blob=root/(sha+".glb")
        if (blob.is_symlink() or not blob.is_file() or
            blob.resolve().parent!=root or
            hashlib.sha256(blob.read_bytes()).hexdigest()!=sha):
            raise RuntimeError("Registered original rigged GLB bytes not verified")
        return rec,blob.read_bytes()

    def import_registered(self,project_id,character_asset_id):
        rec,raw=self._registered(project_id,character_asset_id)
        decoded=extract_original_glb_skin(raw)
        sha=hashlib.sha256(raw).hexdigest()
        # Source GLB and normalized vertex data are content-addressed,
        # never served from an external file reference after publication.
        glb_sha=self.index.put_blob(project_id,raw,media_type="model/gltf-binary")
        data=json.dumps(decoded,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        skin_sha=self.index.put_blob(
            project_id,data,media_type="application/vnd.nvp.glb-to-usd-rig+json")
        doc={"format":FORMAT,"registered_character_id":character_asset_id,
             "original_glb_sha256":glb_sha,"normalized_rig_sha256":skin_sha,
             "source_license":rec["license"],"source_attribution":rec["attribution"],
             "source_name":rec["source"],"rights_independently_verified":False,
             "extracted_from_original_vertices":True,
             "procedural_character_substitute":False,
             "source_vertex_count":decoded["original_vertex_count"],
             "source_triangle_count":decoded["original_triangle_count"],
             "joint_count":len(decoded["joints"])}
        try:
            existing=self.index.read_revision(project_id,character_asset_id,1)
        except KeyError:
            return self.index.register_revision(
                project_id,character_asset_id,"asset",doc,expected_revision=0)
        if existing["kind"]!="asset" or existing["data"]!=doc:
            raise RuntimeError("Registered GLB asset conflicts with its frozen USD bridge source")
        return existing

    def rig(self,project_id,character_asset_id,revision,*,path,
            motion_joint=None,travel=0.0):
        """Build one native USD skeleton from exact imported source bytes."""
        _id(character_asset_id,"rigged GLB FilmIndex asset")
        record=self.index.read_revision(project_id,character_asset_id,revision)
        doc=record["data"]
        if (record["kind"]!="asset" or doc.get("format")!=FORMAT or
            doc.get("registered_character_id")!=character_asset_id):
            raise RuntimeError("Not an actual imported native character source")
        # Verify that a currently registered asset hasn't been swapped out.
        meta,raw=self._registered(project_id,character_asset_id)
        if hashlib.sha256(raw).hexdigest()!=doc["original_glb_sha256"]:
            raise RuntimeError("Original rigged character GLB changed")
        blob=self.index.get_blob(project_id,doc["original_glb_sha256"])
        if blob!=raw:
            raise RuntimeError("Published native GLB bytes differ from registered source")
        rigbytes=self.index.get_blob(project_id,doc["normalized_rig_sha256"])
        decoded=json.loads(rigbytes)
        if extract_original_glb_skin(blob)!=decoded:
            raise RuntimeError("Published USD rig is not derived from original GLB geometry")
        joints=decoded["joints"]
        if (type(travel) not in (int,float) or not math.isfinite(travel) or
            not -0.5<=travel<=0.5):
            raise ValueError("Creator joint translation amplitude out of bounds")
        if motion_joint is not None and motion_joint not in joints:
            raise ValueError("Requested acting joint is not part of original imported rig")
        end=[list(m) for m in decoded["rest_transforms"]]
        if motion_joint is not None:
            i=joints.index(motion_joint)
            end[i][12]+=float(travel)
        return {"path":path,"joints":joints,"skin":decoded["skin"],
                "rest_transforms":decoded["rest_transforms"],
                "bind_transforms":decoded["bind_transforms"],
                "samples":[
                    {"tick":0,"joint_transforms":decoded["rest_transforms"]},
                    {"tick":TICKS_PER_SECOND,"joint_transforms":end},
                ]}
