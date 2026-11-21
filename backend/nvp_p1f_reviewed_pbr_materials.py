"""P1-F production-asset milestone: reviewed, immutable UV/PBR texture source.

Only human-selected, original PNG bytes are accepted; no filename, URL, model-
provided path or USD asset-resolver reference is carried into trusted render
workers. This stores rights EVIDENCE, not a legal assertion that third-party
rights have been cleared. Future Blender/MaterialX translation requires a
separate source-bound renderer and cannot use this asset as a worker permit.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import math
import re

from PIL import Image, UnidentifiedImageError

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_assets import OpenUSDAssetRegistry

FORMAT="nvp.asset.p1f.reviewed_uv_pbr_texture_set.v1"
CHANNELS=frozenset(("baseColor","roughness","metallic","normal"))
ALLOWED_RIGHTS=frozenset(("creator_owned","licensed_for_production"))
MAX_IMAGE_BYTES=8*1024*1024
MAX_IMAGE_DIMENSION=4096
MAX_PIXELS=4096*4096
MAX_TOTAL_BYTES=24*1024*1024
MAX_LICENSE_BYTES=16384
RIGHTS_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ /():+-]{2,159}$")


def _image_review(slot,raw):
    if slot not in CHANNELS or type(raw) is not bytes or not 80<=len(raw)<=MAX_IMAGE_BYTES:
        raise ValueError("Reviewed PBR slot needs finite original PNG image bytes")
    try:
        with Image.open(BytesIO(raw)) as image:
            if (image.format!="PNG" or getattr(image,"n_frames",1)!=1 or
                    image.width<16 or image.height<16 or
                    image.width>MAX_IMAGE_DIMENSION or
                    image.height>MAX_IMAGE_DIMENSION or
                    image.width*image.height>MAX_PIXELS):
                raise ValueError("PBR texture PNG size, type or frame count out of bounds")
            if (slot in ("baseColor","normal") and image.mode not in ("RGB","RGBA")) or (
                    slot in ("roughness","metallic") and image.mode not in ("L","RGB")):
                raise ValueError("Texture color channels are incompatible with declared PBR role")
            image.load()  # Fully decode untrusted binary before asset admission.
            dimensions=[image.width,image.height]
            color_mode=image.mode
    except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as exc:
        raise ValueError("Original texture is not an independently decodable PNG") from exc
    return {"sha256":sha256(raw).hexdigest(),"width":dimensions[0],
            "height":dimensions[1],"mode":color_mode,"media_type":"image/png",
            "size_bytes":len(raw)}


def _rights(rights,evidence):
    if (type(rights) is not dict or
            set(rights)!={"basis","holder","license_identifier","allowed_uses"} or
            rights["basis"] not in ALLOWED_RIGHTS or
            type(rights["holder"]) is not str or
            type(rights["license_identifier"]) is not str or
            not RIGHTS_RE.fullmatch(rights["holder"]) or
            not RIGHTS_RE.fullmatch(rights["license_identifier"]) or
            type(rights["allowed_uses"]) is not list or
            sorted(rights["allowed_uses"])!=["derivative","distribution","render"]):
        raise ValueError("Original texture rights require reviewed holder, license and explicit uses")
    if (type(evidence) is not bytes or
            not 32<=len(evidence)<=MAX_LICENSE_BYTES or b"\x00" in evidence):
        raise ValueError("An actual bounded license/ownership evidence document is required")
    evidence.decode("utf8","strict")
    return {"basis":rights["basis"],"holder":rights["holder"],
            "license_identifier":rights["license_identifier"],
            "allowed_uses":list(rights["allowed_uses"])}


def _binding_review(layer,material_path):
    from pxr import Usd,UsdGeom,UsdShade,Sdf
    if (type(material_path) is not str or
            not material_path.startswith("/Asset/Looks/") or
            not Sdf.Path.IsValidPathString(material_path)):
        raise ValueError("Texture material must be inside original reviewed /Asset/Looks")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if not stage:
        raise RuntimeError("Frozen environment cannot be inspected for original UV/PBR")
    material=stage.GetPrimAtPath(material_path)
    if not material or not material.IsA(UsdShade.Material):
        raise ValueError("Original material is not present in reviewed environment")
    matching=[]
    for prim in stage.TraverseAll():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        binding=UsdShade.MaterialBindingAPI(prim).GetDirectBindingRel()
        if [str(p) for p in (binding.GetTargets() or [])]!=[material_path]:
            continue
        mesh=UsdGeom.Mesh(prim)
        uv=UsdGeom.PrimvarsAPI(prim).GetPrimvar("st")
        if not uv or not uv.HasAuthoredValue():
            raise ValueError("Texture-bearing mesh has no original authored UV st primvar")
        values=uv.Get()
        if values is None or not len(values):
            raise ValueError("Original mesh has no finite UV coordinates")
        interpolation=str(uv.GetInterpolation())
        point_count=len(mesh.GetPointsAttr().Get())
        corners=sum(mesh.GetFaceVertexCountsAttr().Get())
        expected={"vertex":point_count,"faceVarying":corners}.get(interpolation)
        if expected is None or len(values)!=expected or uv.GetIndices():
            raise ValueError("Only direct authored vertex/faceVarying UV values supported")
        if any(not math.isfinite(float(v)) or abs(float(v))>1024
               for coord in values for v in coord):
            raise ValueError("Original source UV contains nonfinite/unbounded values")
        matching.append({"mesh_path":str(prim.GetPath()),
                         "uv_interpolation":interpolation,
                         "uv_count":len(values)})
    if not matching:
        raise ValueError("Selected original PBR material is not bound to UV-mapped geometry")
    return matching


class P1FReviewedPBRMaterials:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Only original FilmIndex can authorize reviewed material sources")
        self.index=index
        self.assets=OpenUSDAssetRegistry(index)

    def publish(self,pid,material_set_id,*,environment_id,environment_revision,
                material_path,textures,rights,rights_evidence,
                approve_import,creator_event):
        _require_pid(pid)
        _id(material_set_id,"reviewed immutable texture-set identity")
        _id(environment_id,"original environment asset ID")
        if (type(environment_revision) is not int or environment_revision<1 or
                not callable(approve_import)):
            raise ValueError("Original environment revision and independent creator review required")
        env,layer=self.assets.open(pid,environment_id,environment_revision)
        from backend.nvp_p1f_imported_environment import FORMAT as ENV_FORMAT
        if env["data"].get("format")!=ENV_FORMAT:
            raise ValueError("PBR textures must bind to an immutable imported environment")
        bindings=_binding_review(layer,material_path)
        if (type(textures) is not dict or
                "baseColor" not in textures or not 1<=len(textures)<=4 or
                set(textures)-CHANNELS):
            raise ValueError("PBR surface requires a baseColor map and finite reviewed channels")
        reviewed={slot:_image_review(slot,raw) for slot,raw in textures.items()}
        dimensions={(v["width"],v["height"]) for v in reviewed.values()}
        if len(dimensions)!=1 or sum(len(b) for b in textures.values())>MAX_TOTAL_BYTES:
            raise ValueError("Reviewed PBR maps must share bounded original UV dimensions")
        reviewed_rights=_rights(rights,rights_evidence)
        evidence_sha=sha256(rights_evidence).hexdigest()
        scope={
            "operation":"nvp.p1f.import_reviewed_pbr_texture_set.v1",
            "project_id":pid,"material_set_id":material_set_id,
            "environment_id":environment_id,
            "environment_revision":environment_revision,
            "environment_document_sha256":env["document_sha256"],
            "material_path":material_path,"bindings":bindings,
            "textures":reviewed,"rights":reviewed_rights,
            "rights_evidence_sha256":evidence_sha,
        }
        if approve_import(creator_event,dict(scope)) is not True:
            raise PermissionError("Creator did not approve the exact UV maps and rights evidence")
        for slot,raw in textures.items():
            if self.index.put_blob(pid,raw,media_type="image/png")!=reviewed[slot]["sha256"]:
                raise RuntimeError("Frozen original PBR image SHA disagrees at FilmIndex storage")
        if self.index.put_blob(pid,rights_evidence,media_type="text/plain; charset=utf-8")!=evidence_sha:
            raise RuntimeError("Frozen material rights evidence SHA disagrees")
        doc={
            "format":FORMAT,
            "environment_id":environment_id,
            "environment_revision":environment_revision,
            "environment_document_sha256":env["document_sha256"],
            "material_path":material_path,"bindings":bindings,
            "textures":reviewed,"rights":reviewed_rights,
            "rights_evidence_sha256":evidence_sha,
            "rights_document_verified":False,
            "creator_source_reviewed":True,
            "private_worker_authorized":False,
            "whole_film_delivered":False,
        }
        dependencies=[{"object_id":environment_id,
                       "revision":environment_revision,"role":"asset"}]
        def guard(db):
            for digest in [evidence_sha,*[v["sha256"] for v in reviewed.values()]]:
                if not db.execute("""SELECT 1 FROM film_blob_refs
                       WHERE project_id=? AND sha256=?""",(pid,digest)).fetchone():
                    raise RuntimeError("Reviewed material publication lost original image/evidence")
        return self.index.register_revision(
            pid,material_set_id,"asset",doc,
            expected_revision=0,dependencies=dependencies,precommit_guard=guard)

    def open(self,pid,material_set_id,revision=1):
        _require_pid(pid);_id(material_set_id,"reviewed material set")
        record=self.index.read_revision(pid,material_set_id,revision)
        doc=record["data"]
        if (record["kind"]!="asset" or doc.get("format")!=FORMAT or
                revision!=1 or
                doc.get("creator_source_reviewed") is not True or
                doc.get("rights_document_verified") is not False or
                doc.get("private_worker_authorized") is not False or
                doc.get("whole_film_delivered") is not False or
                record["dependencies"]!=[{
                    "object_id":doc["environment_id"],
                    "revision":doc["environment_revision"],"role":"asset"}]):
            raise RuntimeError("Unreviewed or altered PBR material asset identity")
        env,layer=self.assets.open(pid,doc["environment_id"],doc["environment_revision"])
        if env["document_sha256"]!=doc["environment_document_sha256"]:
            raise RuntimeError("Original environment source SHA changed")
        if _binding_review(layer,doc["material_path"])!=doc["bindings"]:
            raise RuntimeError("Original UV mesh/material binding changed")
        names=doc.get("textures")
        if (type(names) is not dict or "baseColor" not in names or
                not 1<=len(names)<=4 or set(names)-CHANNELS):
            raise RuntimeError("Original texture manifest changed")
        for slot,meta in names.items():
            raw=self.index.get_blob(pid,meta["sha256"])
            if _image_review(slot,raw)!=meta:
                raise RuntimeError("Original reviewed image pixels/dimensions changed")
        rights_doc=self.index.get_blob(pid,doc["rights_evidence_sha256"])
        if sha256(rights_doc).hexdigest()!=doc["rights_evidence_sha256"]:
            raise RuntimeError("Frozen rights evidence was corrupted")
        if _rights(doc["rights"],rights_doc)!=doc["rights"]:
            raise RuntimeError("Material permissions no longer match reviewed evidence")
        return record

    def original_texture_bytes(self,pid,material_set_id,slot):
        # Fetch only through the canonical indexed source; never return a path.
        record=self.open(pid,material_set_id)
        if slot not in record["data"]["textures"]:
            raise KeyError("Unapproved PBR texture channel")
        return self.index.get_blob(pid,record["data"]["textures"][slot]["sha256"])
