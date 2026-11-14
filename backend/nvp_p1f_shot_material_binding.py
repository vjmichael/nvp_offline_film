"""P1-F immutable reviewed PBR environment binding to ORIGINAL film shot source.

This file binds one source-verified UV material set to one frozen authored
OpenUSD scene environment, not to a filename, Blender workspace, arbitrary
path, or inferred actor identity. Reopen validates both source revisions and
each frame's original Take/scene SHA. The binding does not admit a worker,
alter a Take, grant private source access, or create picture/audio/master bytes.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex,_require_pid,_id
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_p1f_reviewed_pbr_materials import (
    P1FReviewedPBRMaterials,FORMAT as MATERIAL_FORMAT)
from backend.nvp_p1f_cycles_source_admission import admit_original_frame

FORMAT="nvp.p1f.original_shot_reviewed_material_binding.v1"


class P1FOriginalShotMaterialBinding:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Only original FilmIndex can bind scene materials")
        self.index=index
        self.scenes=OpenUSDSceneBridge(index)
        self.materials=P1FReviewedPBRMaterials(index)

    def _check(self,pid,scene_id,scene_revision,environment_path,
               material_set_id,material_set_revision):
        _require_pid(pid)
        _id(scene_id,"original scene");_id(material_set_id,"reviewed material asset")
        if (type(scene_revision) is not int or scene_revision<1 or
                type(material_set_revision) is not int or material_set_revision<1 or
                type(environment_path) is not str):
            raise ValueError("Exact scene/material revisions and environment path required")
        scene,stage=self.scenes.open(pid,scene_id,scene_revision)
        if scene["data"]["prim_roles"].get(environment_path)!="environment":
            raise ValueError("Material must attach to an original environment role")
        assets=[x for x in scene["data"].get("asset_bindings",[])
                if x["path"]==environment_path]
        if len(assets)!=1:
            raise ValueError("Scene must reference one approved original environment asset")
        asset=assets[0]
        mat=self.materials.open(pid,material_set_id,material_set_revision)
        doc=mat["data"]
        if (doc.get("format")!=MATERIAL_FORMAT or
                asset["asset_id"]!=doc["environment_id"] or
                asset["asset_revision"]!=doc["environment_revision"] or
                asset["asset_document_sha256"]!=doc["environment_document_sha256"]):
            raise RuntimeError("Reviewed PBR maps do not belong to scene's original environment")
        from pxr import UsdGeom,UsdShade
        import math
        original_material=doc["material_path"]
        composed_material=environment_path+original_material.removeprefix("/Asset")
        prim=stage.GetPrimAtPath(composed_material)
        if not prim or not prim.IsA(UsdShade.Material):
            raise RuntimeError("Frozen composed material missing from original film scene")
        bound=[]
        for item in doc["bindings"]:
            path=environment_path+item["mesh_path"].removeprefix("/Asset")
            mesh_prim=stage.GetPrimAtPath(path)
            if not mesh_prim or not mesh_prim.IsA(UsdGeom.Mesh):
                raise RuntimeError("Frozen UV-mapped source geometry absent in scene")
            targets=[str(p) for p in
                     UsdShade.MaterialBindingAPI(mesh_prim).GetDirectBindingRel().GetTargets()]
            if targets!=[composed_material]:
                raise RuntimeError("Original scene has changed PBR material binding")
            uv=UsdGeom.PrimvarsAPI(mesh_prim).GetPrimvar("st")
            data=uv.Get() if uv else None
            if (not uv or not data or
                    len(data)!=item["uv_count"] or
                    str(uv.GetInterpolation())!=item["uv_interpolation"] or
                    any(not math.isfinite(float(x)) for value in data for x in value)):
                raise RuntimeError("Original scene UV data changed after asset import")
            bound.append(path)
        if not bound:
            raise RuntimeError("No immutable scene UV mesh available")
        return scene,mat,composed_material,sorted(bound)

    def publish(self,pid,look_id,*,scene_id,scene_revision,
                environment_path,material_set_id,material_set_revision=1,
                approve_bind,creator_event):
        _require_pid(pid);_id(look_id,"original shot look")
        if not callable(approve_bind):
            raise TypeError("Separate human review of scene look required")
        scene,material,composed,meshes=self._check(
            pid,scene_id,scene_revision,environment_path,
            material_set_id,material_set_revision)
        scope={
            "operation":"nvp.p1f.bind_reviewed_material_to_original_scene.v1",
            "project_id":pid,"look_id":look_id,
            "scene_id":scene_id,"scene_revision":scene_revision,
            "scene_document_sha256":scene["document_sha256"],
            "environment_path":environment_path,
            "material_set_id":material_set_id,
            "material_set_revision":material_set_revision,
            "material_set_document_sha256":material["document_sha256"],
            "original_material_path":composed,
            "original_uv_mesh_paths":meshes,
            "texture_sources":material["data"]["textures"],
        }
        if approve_bind(creator_event,dict(scope)) is not True:
            raise PermissionError("Creator did not approve exact original shot/material scope")
        doc={
            "format":FORMAT,"scene_id":scene_id,
            "scene_revision":scene_revision,
            "scene_document_sha256":scene["document_sha256"],
            "environment_path":environment_path,
            "material_set_id":material_set_id,
            "material_set_revision":material_set_revision,
            "material_set_document_sha256":material["document_sha256"],
            "composed_material_path":composed,
            "bound_mesh_paths":meshes,
            "texture_sources":material["data"]["textures"],
            "original_take_mutated":False,
            "worker_authorized":False,
            "film_master_created":False,
        }
        deps=[
            {"object_id":scene_id,"revision":scene_revision,"role":"scene"},
            {"object_id":material_set_id,"revision":material_set_revision,"role":"asset"},
        ]
        return self.index.register_revision(
            pid,look_id,"presentation",doc,expected_revision=0,
            dependencies=deps)

    def open(self,pid,look_id,revision=1):
        _require_pid(pid);_id(look_id,"original shot look")
        if type(revision) is not int or revision!=1:
            raise ValueError("Reviewed original scene/material binding is immutable")
        record=self.index.read_revision(pid,look_id,1)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
                doc.get("original_take_mutated") is not False or
                doc.get("worker_authorized") is not False or
                doc.get("film_master_created") is not False):
            raise RuntimeError("Untrusted original shot/material binding identity")
        dependencies=sorted([
            {"object_id":doc["scene_id"],"revision":doc["scene_revision"],"role":"scene"},
            {"object_id":doc["material_set_id"],"revision":doc["material_set_revision"],"role":"asset"},
        ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if record["dependencies"]!=dependencies:
            raise RuntimeError("Source scene/material dependency identity changed")
        scene,material,composed,meshes=self._check(
            pid,doc["scene_id"],doc["scene_revision"],
            doc["environment_path"],doc["material_set_id"],
            doc["material_set_revision"])
        if (doc["scene_document_sha256"]!=scene["document_sha256"] or
                doc["material_set_document_sha256"]!=material["document_sha256"] or
                doc["composed_material_path"]!=composed or
                doc["bound_mesh_paths"]!=meshes or
                doc["texture_sources"]!=material["data"]["textures"]):
            raise RuntimeError("Original scene PBR binding differs on independently reopened source")
        return record

    def for_frame(self,pid,look_id,plan_id,reel_index,frame_offset):
        look=self.open(pid,look_id)
        adm=admit_original_frame(
            self.index,pid,plan_id,reel_index,frame_offset)
        take=self.index.read_revision(pid,adm["take_id"],1)
        if (take["document_sha256"]!=adm["take_document_sha256"] or
                take["data"]["scene_id"]!=look["data"]["scene_id"] or
                take["data"]["scene_revision"]!=look["data"]["scene_revision"] or
                take["data"]["scene_document_sha256"]!=
                    look["data"]["scene_document_sha256"]):
            raise RuntimeError("Requested film frame does not originate from reviewed look scene")
        return {"format":FORMAT,"status":"LOOK_SOURCE_VERIFIED_NOT_RENDERED",
                "look_id":look_id,"look_document_sha256":look["document_sha256"],
                "material_set_id":look["data"]["material_set_id"],
                "material_set_document_sha256":
                    look["data"]["material_set_document_sha256"],
                "scene_document_sha256":look["data"]["scene_document_sha256"],
                "take_document_sha256":adm["take_document_sha256"],
                "source_tick":adm["source_tick"],
                "output_tick":adm["output_tick"],
                "composed_material_path":look["data"]["composed_material_path"],
                "bound_mesh_paths":look["data"]["bound_mesh_paths"],
                "texture_sources":look["data"]["texture_sources"],
                "worker_authorized":False,"picture_rendered":False,
                "film_master_created":False}
