"""USD-FILM-02M-H: approved district in original 01D/01E film shot.

This is a source-authentic read-only native OpenUSD composition and, only
with an independent native director approval, an immutable FilmIndex binding.
It does not change the source film world, original frozen actor Takes, shot
camera, dialogue or PCM. It does not produce final film pixels.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_usd_film01d_shot_working_set import (
    FilmWorldShotPlanner, _camera_native)
from backend.nvp_usd_film01e_world_take import (
    OpenUSDWorldTakeCapture, FORMAT as TAKE_FORMAT)
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film02m_e_district import OriginalFilmDistrict

FORMAT = "nvp.usd_film02m_h.approved_district_original_actor_camera_binding.v1"
PREVIEW = "nvp.usd_film02m_h.native_source_district_shot_preview.v1"


def _bytes(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _digest(value):
    return sha256(_bytes(value)).hexdigest()


def _source_preview(index,pid,district_id,district_revision,
                    world_take_id,film_tick):
    if not isinstance(index,FilmIndex):
        raise TypeError("Original FilmIndex is required")
    _require_pid(pid)
    _id(district_id,"approved source film district")
    _id(world_take_id,"original frozen world Take")
    if type(district_revision) is not int or district_revision<1:
        raise ValueError("Exact approved district revision required")
    if type(film_tick) is not int or film_tick<0:
        raise ValueError("Exact 01E film checkpoint tick required")

    capture=OpenUSDWorldTakeCapture(
        index,verify_creator_action=lambda *_:False)
    verification=capture.verify_take(pid,world_take_id)
    if (verification["status"]!="VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE"
        or verification["original_actor_source_unchanged"] is not True):
        raise PermissionError("Frozen 01E actor performance source invalid")
    take=index.read_revision(pid,world_take_id,1)
    doc=take["data"]
    if (doc.get("format")!=TAKE_FORMAT or
        film_tick not in doc["checkpoint_ticks"]):
        raise ValueError("Not an authored original film checkpoint")

    shot=FilmWorldShotPlanner(index).inspect(
        pid,doc["camera_shot_id"],doc["camera_shot_revision"],
        expected_world_sha=doc["world_document_sha256"])
    shot_doc=shot["data"]
    original_sample=capture.sample(pid,world_take_id,tick=film_tick)
    if (original_sample["world_document_sha256"]!=
        doc["world_document_sha256"]):
        raise RuntimeError("Original actor/camera checkpoint world mismatch")

    district=OriginalFilmDistrict(
        index,verify_director_action=lambda *_:False)
    with district.open(pid,district_id,district_revision) as approved:
        plan=approved["plan"]
        root_sha=approved["receipt"]["district_root_sha256"]
        if (root_sha!=approved["record"]["data"]["native_source_receipt"][
                "district_root_sha256"]):
            raise RuntimeError("Previously approved original world USD changed")

        # 01D's exact shot is the ONLY camera selector; 01E's frozen
        # checkpoint is the ONLY actor/performance selector.
        with OpenUSDWorldComposer(index).open(
            pid,doc["world_id"],doc["world_revision"]) as original_world:
            original_world.load(shot_doc["director_required_sets"])
            from pxr import Usd, UsdGeom, Gf, Sdf
            stage=original_world.stage
            original_root=stage.GetRootLayer().ExportToString()
            # Apply only the shot's authored look variants in this session,
            # exactly as the 01E checkpoint sampler does.
            with Usd.EditContext(stage,stage.GetSessionLayer()):
                for variant,look in shot_doc["director_looks"].items():
                    original_world.switch_variant(variant,look)
            path,position=_camera_native(
                original_world,shot_doc["camera_set"],
                shot_doc["camera_prim_path"],[film_tick])
            if (path!=original_sample["original_camera_path"] or
                any(abs(a-b)>1e-6 for a,b in zip(
                    position[0],original_sample["original_camera_position_m"]))):
                raise RuntimeError("01D camera changed before district shot composition")

            actor_poses=[]
            for scene in original_sample["scenes"]:
                for actor in scene["actors"]:
                    actor_prim=stage.GetPrimAtPath(actor["composed_world_prim"])
                    xform=UsdGeom.Xformable(actor_prim)
                    if not actor_prim.IsDefined() or not xform:
                        raise RuntimeError("Original actor vanished from loaded USD set")
                    matrix=xform.ComputeLocalToWorldTransform(
                        Usd.TimeCode(float(film_tick)))
                    observed=list(map(float,matrix.ExtractTranslation()))
                    if (any(not math.isfinite(x) for x in observed) or
                        any(abs(a-b)>1e-6 for a,b in zip(
                            observed,actor["world_translation_m"]))):
                        raise RuntimeError("Original 01E actor pose differs from filmed source")
                    actor_poses.append({
                        "actor_id":actor["actor_id"],
                        "source_take_id":scene["source_take_id"],
                        "composed_world_prim":actor["composed_world_prim"],
                        "world_translation_m":observed,
                    })
            # Append one session-only stronger layer. Original film world
            # root, original actor Takes, and source district layer stay
            # byte-identical. The approved 3D layer refs remain live during
            # this bounded USD context, including real prototype meshes.
            session=stage.GetSessionLayer()
            child="/World/OriginalFilmDistricts/"+district_id
            with Usd.EditContext(stage,session):
                UsdGeom.Xform.Define(stage,"/World/OriginalFilmDistricts")
                prim=UsdGeom.Xform.Define(stage,child)
                if not prim.GetPrim().GetReferences().AddReference(
                        str(approved["root_path"]),Sdf.Path("/World")):
                    raise RuntimeError("Approved district USD reference failed")
                if not UsdGeom.XformCommonAPI(prim).SetTranslate(
                        Gf.Vec3d(*plan["world_origin_m"])):
                    raise RuntimeError("Original district world origin cannot compose")
            point=UsdGeom.PointInstancer.Get(
                stage,child+"/GeneratedBuildings")
            if (not point or not stage.GetPrimAtPath(
                    child+"/GeneratedBuildings").IsDefined()):
                raise RuntimeError("Native approved PointInstancer missing from shot")
            ids=list(point.GetIdsAttr().Get() or [])
            invisible=list(point.GetInvisibleIdsAttr().Get() or [])
            if (ids!=[x["instance_id"] for x in plan["generated_instances"]]
                or invisible!=plan["director_invisible_instance_ids"]):
                raise RuntimeError("Native shot altered approved district identities")
            for manual in plan["director_manual_overrides"]:
                if not stage.GetPrimAtPath(
                        child+"/DirectorOverrides/"+manual["name"]).IsDefined():
                    raise RuntimeError("Native shot lost a manual original source reference")
            post_path,post_pos=_camera_native(
                original_world,shot_doc["camera_set"],
                shot_doc["camera_prim_path"],[film_tick])
            if post_path!=path or post_pos!=position:
                raise RuntimeError("Approved district unexpectedly changed original camera")
            for actor in actor_poses:
                prim=stage.GetPrimAtPath(actor["composed_world_prim"])
                observed=list(map(float,
                    UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                        Usd.TimeCode(float(film_tick))).ExtractTranslation()))
                if any(abs(a-b)>1e-6 for a,b in zip(
                        observed,actor["world_translation_m"])):
                    raise RuntimeError("Approved district modified original actor pose")
            if stage.GetRootLayer().ExportToString()!=original_root:
                raise RuntimeError("Original film world root layer was modified")
            # Source identities and actor performance are verified before
            # returning this derived, non-authoritative working-set receipt.
            return {
                "format":PREVIEW,
                "project_id":pid,
                "district_id":district_id,
                "district_revision":district_revision,
                "district_document_sha256":approved["record"]["document_sha256"],
                "district_original_usd_root_sha256":root_sha,
                "district_source_plan_sha256":_digest(plan),
                "district_world_origin_m":plan["world_origin_m"],
                "native_composed_district_prim":child,
                "native_original_instance_count":len(ids),
                "native_original_hidden_ids":invisible,
                "native_original_manual_count":len(
                    plan["director_manual_overrides"]),
                "world_take_id":world_take_id,
                "world_take_sha256":take["document_sha256"],
                "world_id":doc["world_id"],
                "world_revision":doc["world_revision"],
                "world_document_sha256":doc["world_document_sha256"],
                "shot_id":doc["camera_shot_id"],
                "shot_revision":doc["camera_shot_revision"],
                "shot_document_sha256":shot["document_sha256"],
                "film_tick":film_tick,
                "original_camera_path":path,
                "original_camera_position_m":position[0],
                "original_actor_poses":actor_poses,
                "original_scene_take_sha256":[t["take_sha256"] for t in
                                               doc["original_scene_takes"]],
                "original_checkpoint_digest_sha256":
                    doc["checkpoint_digest_sha256"],
                "native_original_camera_verified":True,
                "native_original_actor_pose_verified":True,
                "native_approved_district_layer_composed":True,
                "original_film_world_root_unchanged":True,
                "original_actor_takes_unchanged":True,
                "original_camera_source_unchanged":True,
                "rendered_frames":0,
                "original_pcm_modified":False,
                "final_movie_accepted":False,
            }


class OriginalDistrictShotBinding:
    def __init__(self,index,*,confirm):
        if not isinstance(index,FilmIndex) or not callable(confirm):
            raise TypeError("Native original FilmIndex + director action required")
        self.index=index
        self.confirm=confirm

    def preview(self,pid,district_id,district_revision,world_take_id,film_tick):
        result=_source_preview(self.index,pid,district_id,district_revision,
                               world_take_id,film_tick)
        return {**result,"binding_preview_sha256":_digest(result)}

    def publish(self,pid,binding_id,*,district_id,district_revision,
                world_take_id,film_tick,creator_event,
                expected_preview_sha256):
        _id(binding_id,"immutable film district shot binding")
        snapshot=self.preview(
            pid,district_id,district_revision,world_take_id,film_tick)
        key=snapshot["binding_preview_sha256"]
        if expected_preview_sha256!=key:
            raise PermissionError("Native shot binding preview source SHA stale")
        scope={
            "operation":"nvp.film02m_h.approve_original_district_shot_binding.v1",
            "project_id":pid,"binding_id":binding_id,
            "district_id":district_id,
            "district_revision":district_revision,
            "district_document_sha256":snapshot["district_document_sha256"],
            "district_usd_root_sha256":snapshot[
                "district_original_usd_root_sha256"],
            "world_take_id":world_take_id,
            "world_take_sha256":snapshot["world_take_sha256"],
            "original_camera_shot_sha256":snapshot["shot_document_sha256"],
            "source_preview_sha256":key,"film_tick":film_tick,
            "actor_count":len(snapshot["original_actor_poses"])}
        if self.confirm(creator_event,scope) is not True:
            raise PermissionError("Director must independently approve shot binding")
        # Re-read and recompose exact source AFTER confirmation, to catch
        # a changed file or source view while a native dialog was open.
        after=self.preview(
            pid,district_id,district_revision,world_take_id,film_tick)
        if after["binding_preview_sha256"]!=key:
            raise RuntimeError("Source shot changed during native director approval")
        doc={**after,
             "format":FORMAT,
             "immutable_original_world_take_binding":True,
             "original_01e_take_not_rewritten":True}
        dependencies=[
            {"object_id":district_id,"revision":district_revision,
             "role":"presentation"},
            {"object_id":world_take_id,"revision":1,"role":"source_take"},
            {"object_id":snapshot["shot_id"],"revision":snapshot["shot_revision"],
             "role":"camera"},
            {"object_id":snapshot["world_id"],"revision":snapshot["world_revision"],
             "role":"world"}]
        source_take_doc=self.index.read_revision(pid,world_take_id,1)["data"]
        for source in source_take_doc["original_scene_takes"]:
            dependencies.append({
                "object_id":source["take_id"],"revision":1,
                "role":"source_take"})
        deps=list({(x["object_id"],x["revision"],x["role"]):x
                   for x in dependencies}.values())
        digest={(x["object_id"],x["revision"]):
            self.index.read_revision(pid,x["object_id"],x["revision"])[
                "document_sha256"] for x in deps}
        def guard(db):
            for (oid,rev),sha in digest.items():
                observed=db.execute("""SELECT document_sha
                    FROM film_object_revisions WHERE project_id=?
                    AND object_id=? AND revision=?""",(pid,oid,rev)).fetchone()
                if observed is None or observed["document_sha"]!=sha:
                    raise RuntimeError("Original shot source changed at binding commit")
        return self.index.register_revision(
            pid,binding_id,"presentation",doc,expected_revision=0,
            dependencies=deps,precommit_guard=guard)

    def reopen(self,pid,binding_id):
        _id(binding_id,"exact immutable district shot binding")
        record=self.index.read_revision(pid,binding_id,1)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
            doc.get("immutable_original_world_take_binding") is not True):
            raise PermissionError("Not an approved original district shot binding")
        current=self.preview(pid,doc["district_id"],doc["district_revision"],
                             doc["world_take_id"],doc["film_tick"])
        if doc!={**current,"format":FORMAT,
                "immutable_original_world_take_binding":True,
                "original_01e_take_not_rewritten":True}:
            raise RuntimeError("Approved original world/actor/camera binding changed")
        return {
            "format":FORMAT,
            "binding_id":binding_id,
            "binding_document_sha256":record["document_sha256"],
            "source_preview":current,
            "native_source_reopened":True,
            "source_actor_takes_unchanged":True,
            "new_film_frames_rendered":0}
