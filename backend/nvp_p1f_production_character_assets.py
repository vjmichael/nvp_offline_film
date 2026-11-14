"""P1-F Step 2: reviewed offline character source and original film casting.

Bridge the existing bounded GLB 2.0 skinned mesh inspector to the authoritative
FilmIndex/OpenUSD ActorID and immutable Take. Every joint correspondence and
rest-pose calibration is creator-declared and source-bound, never inferred by
a model or an arbitrary Blender script. This does NOT claim a retargeted
performance, licensed distribution, private worker execution, or film master.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_character_assets import inspect_rigged_glb
from backend.nvp_p1f_glb_mesh_audit import audit_glb_skinned_mesh
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_p1f_cycles_source_admission import admit_original_frame
from backend.nvp_p1f_reviewed_pbr_materials import _rights

FORMAT = "nvp.p1f.reviewed_production_character_glb.v1"
CAST_FORMAT = "nvp.p1f.original_scene_actor_character_cast.v1"
MAX_RIGHTS_BYTES = 16384


def _source_rig(index, pid, actor_asset_id, revision, actor_id):
    from pxr import Usd, UsdSkel
    record, layer = OpenUSDAssetRegistry(index).open(pid, actor_asset_id, revision)
    data = record["data"]
    if data.get("actor_id") != actor_id:
        raise ValueError("Original imported USD rig belongs to a different ActorID")
    stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
    skeleton = UsdSkel.Skeleton(stage.GetPrimAtPath("/Asset/Skeleton"))
    if not skeleton:
        raise RuntimeError("Original rigged USD skeleton unavailable")
    joints = [str(x) for x in skeleton.GetJointsAttr().Get()]
    if not joints or len(set(joints)) != len(joints):
        raise RuntimeError("Original skeleton joint identity changed")
    return record, joints, stage


def _calibration(value):
    if type(value) is not dict or set(value) != {
        "meters_per_source_unit", "root_height_m",
        "yaw_degrees", "rest_pose_reviewed"}:
        raise ValueError("Explicit scale, rest pose and grounding review required")
    a, b, c = (value["meters_per_source_unit"],
               value["root_height_m"], value["yaw_degrees"])
    if (any(type(x) not in (float, int) or not math.isfinite(x)
            for x in (a, b, c)) or
            not 0.001 <= a <= 100 or
            not -20 <= b <= 20 or not -180 <= c <= 180 or
            type(value["rest_pose_reviewed"]) is not bool):
        raise ValueError("Character scale, grounding and orientation out of reviewed bounds")
    return {**value, "meters_per_source_unit": float(a),
            "root_height_m": float(b), "yaw_degrees": float(c)}


def _joint_map(mapping, original_joints, glb_joints):
    if (type(mapping) is not dict or
            not 2 <= len(mapping) <= min(128, len(original_joints)) or
            not set(mapping).issubset(set(original_joints)) or
            len(set(mapping.values())) != len(mapping) or
            not set(mapping.values()).issubset(set(glb_joints)) or
            any(type(x) is not str for x in [*mapping.keys(), *mapping.values()])):
        raise ValueError("Original USD to imported GLB joint mapping must be explicit, unique and bounded")
    return {key: mapping[key] for key in sorted(mapping)}


class P1FReviewedProductionCharacters:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Original film index required")
        self.index = index
        self.assets = OpenUSDAssetRegistry(index)
        self.scenes = OpenUSDSceneBridge(index)

    def publish(self, pid, package_id, glb_bytes, *,
                actor_id, actor_asset_id, actor_asset_revision,
                joint_map, calibration, rights, rights_evidence,
                approve_import, creator_event):
        _require_pid(pid)
        _id(package_id, "reviewed production character package")
        _id(actor_id, "authoritative ActorID")
        _id(actor_asset_id, "original USD actor asset")
        if (not actor_id.startswith("ACT_") or
                type(actor_asset_revision) is not int or
                actor_asset_revision != 1 or
                not callable(approve_import)):
            raise ValueError("One exact original ActorID, USD revision and creator callback required")
        rig, original_joints, _ = _source_rig(
            self.index, pid, actor_asset_id, actor_asset_revision, actor_id)
        original = inspect_rigged_glb(glb_bytes)
        decoded = audit_glb_skinned_mesh(glb_bytes, original)
        mapped = _joint_map(joint_map, original_joints, original["joint_names"])
        placement = _calibration(calibration)
        evidence = _rights(rights, rights_evidence)
        evidence_sha = sha256(rights_evidence).hexdigest()
        source_sha = original["sha256"]
        if len(rights_evidence) > MAX_RIGHTS_BYTES:
            raise ValueError("Character license document too large")
        scope = {
            "operation": "nvp.p1f.review_production_character_source.v1",
            "project_id": pid, "package_id": package_id,
            "actor_id": actor_id,
            "original_actor_id": actor_asset_id,
            "original_actor_revision": actor_asset_revision,
            "original_actor_document_sha256": rig["document_sha256"],
            "glb_sha256": source_sha,
            "decoded_geometry": decoded,
            "joint_map": mapped,
            "calibration": placement,
            "rights": evidence,
            "rights_evidence_sha256": evidence_sha,
        }
        if approve_import(creator_event, dict(scope)) is not True:
            raise PermissionError("Creator refused exact rig, GLB bytes or license evidence")
        if self.index.put_blob(pid, glb_bytes, "model/gltf-binary") != source_sha:
            raise RuntimeError("Reviewed GLB source hash changed at FilmIndex publication")
        if self.index.put_blob(pid, rights_evidence, "text/plain; charset=utf-8") != evidence_sha:
            raise RuntimeError("Reviewed character rights-evidence bytes changed")
        doc = {
            "format": FORMAT,
            "actor_id": actor_id,
            "original_actor_id": actor_asset_id,
            "original_actor_revision": actor_asset_revision,
            "original_actor_document_sha256": rig["document_sha256"],
            "glb_sha256": source_sha, "glb_inspection": original,
            "decoded_geometry": decoded,
            "joint_map": mapped, "calibration": placement,
            "rights": evidence, "rights_evidence_sha256": evidence_sha,
            "creator_source_reviewed": True,
            "license_independently_verified": False,
            "bone_axis_retargeting_verified": False,
            "contact_and_deformation_verified": False,
            "real_performer_capture_verified": False,
            "private_worker_authorized": False,
            "finished_film": False,
        }
        def guard(db):
            for digest in (source_sha, evidence_sha):
                if db.execute(
                    "SELECT 1 FROM film_blob_refs WHERE project_id=? AND sha256=?",
                    (pid, digest)).fetchone() is None:
                    raise RuntimeError("Original character source lost before approved commit")
        return self.index.register_revision(
            pid, package_id, "asset", doc,
            expected_revision=0,
            dependencies=[{"object_id": actor_asset_id,
                           "revision": actor_asset_revision, "role": "asset"}],
            precommit_guard=guard)

    def open(self, pid, package_id, revision=1):
        _require_pid(pid)
        _id(package_id, "reviewed character package")
        if revision != 1 or type(revision) is not int:
            raise ValueError("Immutable character package accepts only original revision")
        record = self.index.read_revision(pid, package_id, revision)
        d = record["data"]
        if (record["kind"] != "asset" or d.get("format") != FORMAT or
                d.get("creator_source_reviewed") is not True or
                any(d.get(key) is not False for key in (
                    "license_independently_verified",
                    "bone_axis_retargeting_verified",
                    "contact_and_deformation_verified",
                    "real_performer_capture_verified",
                    "private_worker_authorized", "finished_film")) or
                record["dependencies"] != [{
                    "object_id": d["original_actor_id"],
                    "revision": d["original_actor_revision"], "role": "asset"}]):
            raise RuntimeError("Unreviewed, incomplete or altered original character package")
        rig, joints, _ = _source_rig(
            self.index, pid, d["original_actor_id"],
            d["original_actor_revision"], d["actor_id"])
        if rig["document_sha256"] != d["original_actor_document_sha256"]:
            raise RuntimeError("Original USD ActorID/rig source was changed")
        original = self.index.get_blob(pid, d["glb_sha256"])
        if inspect_rigged_glb(original) != d["glb_inspection"]:
            raise RuntimeError("Reviewed skinned GLB geometry/skeleton differs on cold reopen")
        if audit_glb_skinned_mesh(original, d["glb_inspection"]) != d["decoded_geometry"]:
            raise RuntimeError("Original decoded skinning/mesh differs on cold reopen")
        if _joint_map(d["joint_map"], joints, d["glb_inspection"]["joint_names"]) != d["joint_map"]:
            raise RuntimeError("Reviewed joint mapping changed")
        if _calibration(d["calibration"]) != d["calibration"]:
            raise RuntimeError("Reviewed original rest-pose calibration changed")
        license_bytes = self.index.get_blob(pid, d["rights_evidence_sha256"])
        if (sha256(license_bytes).hexdigest() != d["rights_evidence_sha256"] or
                _rights(d["rights"], license_bytes) != d["rights"]):
            raise RuntimeError("Character license evidence changed on cold reopen")
        return record

    def cast(self, pid, cast_id, *, package_id, scene_id,
             scene_revision, actor_path, approve_cast, creator_event):
        _require_pid(pid)
        _id(cast_id, "original actor cast")
        _id(package_id, "approved character package")
        _id(scene_id, "original film scene")
        if (not callable(approve_cast) or
                type(scene_revision) is not int or scene_revision != 1 or
                type(actor_path) is not str or not actor_path.startswith("/World/")):
            raise ValueError("Exact native scene/actor and independent cast review required")
        package = self.open(pid, package_id)
        scene, stage = self.scenes.open(pid, scene_id, scene_revision)
        if (scene["data"]["prim_roles"].get(actor_path) != "actor" or
                not stage.GetPrimAtPath(actor_path)):
            raise ValueError("Authoritative film scene has no reviewed original actor at path")
        bindings = [entry for entry in scene["data"].get("asset_bindings", [])
                    if entry["path"] == actor_path]
        source = package["data"]
        if (len(bindings) != 1 or
                bindings[0]["asset_id"] != source["original_actor_id"] or
                bindings[0]["asset_revision"] != source["original_actor_revision"] or
                bindings[0]["asset_document_sha256"] != source["original_actor_document_sha256"]):
            raise RuntimeError("GLB source is not explicitly mapped to this original ActorID")
        scope = {
            "operation": "nvp.p1f.cast_reviewed_production_character.v1",
            "project_id": pid, "cast_id": cast_id,
            "package_id": package_id, "package_document_sha256": package["document_sha256"],
            "scene_id": scene_id, "scene_revision": scene_revision,
            "scene_document_sha256": scene["document_sha256"],
            "actor_path": actor_path, "actor_id": source["actor_id"],
            "glb_sha256": source["glb_sha256"],
            "rest_pose_reviewed": source["calibration"]["rest_pose_reviewed"],
        }
        if approve_cast(creator_event, dict(scope)) is not True:
            raise PermissionError("Creator refused the exact source character casting")
        doc = {**scope, "format": CAST_FORMAT,
               "source_take_mutated": False,
               "retargeted_body_motion_verified": False,
               "private_worker_authorized": False, "film_master_created": False}
        deps = [
            {"object_id": package_id, "revision": 1, "role": "asset"},
            {"object_id": scene_id, "revision": scene_revision, "role": "scene"}]
        return self.index.register_revision(
            pid, cast_id, "presentation", doc,
            expected_revision=0, dependencies=deps)

    def open_cast(self, pid, cast_id):
        record = self.index.read_revision(pid, cast_id, 1)
        doc = record["data"]
        if (record["kind"] != "presentation" or doc.get("format") != CAST_FORMAT or
                doc.get("source_take_mutated") is not False or
                doc.get("retargeted_body_motion_verified") is not False or
                doc.get("private_worker_authorized") is not False or
                doc.get("film_master_created") is not False):
            raise RuntimeError("Unreviewed source character cast")
        expected_deps = sorted([
            {"object_id": doc["package_id"], "revision": 1, "role": "asset"},
            {"object_id": doc["scene_id"], "revision": doc["scene_revision"], "role": "scene"}],
            key=lambda d: (d["object_id"], d["revision"], d["role"]))
        if record["dependencies"] != expected_deps:
            raise RuntimeError("Immutable original character cast dependencies changed")
        package = self.open(pid, doc["package_id"])
        scene, stage = self.scenes.open(pid, doc["scene_id"], doc["scene_revision"])
        sources = [entry for entry in scene["data"]["asset_bindings"]
                   if entry["path"] == doc["actor_path"]]
        if (doc["package_document_sha256"] != package["document_sha256"] or
                doc["scene_document_sha256"] != scene["document_sha256"] or
                doc["actor_id"] != package["data"]["actor_id"] or
                doc["glb_sha256"] != package["data"]["glb_sha256"] or
                len(sources) != 1 or
                sources[0]["asset_id"] != package["data"]["original_actor_id"] or
                sources[0]["asset_document_sha256"] !=
                    package["data"]["original_actor_document_sha256"]):
            raise RuntimeError("Frozen scene/ActorID/GLB casting has changed")
        if scene["data"]["prim_roles"].get(doc["actor_path"]) != "actor":
            raise RuntimeError("Original scene actor role no longer matches cast")
        return record

    def for_frame(self, pid, cast_id, plan_id, reel_index, frame_offset):
        cast = self.open_cast(pid, cast_id)
        original = admit_original_frame(self.index, pid, plan_id, reel_index, frame_offset)
        take = self.index.read_revision(pid, original["take_id"], 1)
        d = cast["data"]
        if (original["take_document_sha256"] != take["document_sha256"] or
                take["data"]["scene_id"] != d["scene_id"] or
                take["data"]["scene_revision"] != d["scene_revision"] or
                take["data"]["scene_document_sha256"] != d["scene_document_sha256"]):
            raise RuntimeError("Requested performance frame is not from this original actor cast")
        package = self.open(pid, d["package_id"])
        _, _, stage = _source_rig(
            self.index, pid, package["data"]["original_actor_id"],
            package["data"]["original_actor_revision"], d["actor_id"])
        from pxr import Usd, UsdSkel
        anim = UsdSkel.Animation(stage.GetPrimAtPath("/Asset/Animation"))
        expression = anim.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(float(original["source_tick"])))
        if expression is None or len(expression) != 4 or any(
                not math.isfinite(float(x)) or not 0 <= x <= 1
                for x in expression):
            raise RuntimeError("Actor facial expression did not originate from Film Time")
        return {
            "format": CAST_FORMAT, "status": "REVIEWED_CAST_SOURCE_NOT_RENDERED",
            "cast_id": cast_id, "cast_document_sha256": cast["document_sha256"],
            "actor_id": d["actor_id"], "actor_path": d["actor_path"],
            "glb_sha256": d["glb_sha256"],
            "original_actor_sha256": package["data"]["original_actor_document_sha256"],
            "source_take_sha256": take["document_sha256"],
            "source_tick": original["source_tick"], "output_tick": original["output_tick"],
            "facial_weights": [float(v) for v in expression],
            "joint_map": package["data"]["joint_map"],
            "calibration": package["data"]["calibration"],
            "source_rights_evidence_sha256": package["data"]["rights_evidence_sha256"],
            "retargeted_body_motion_verified": False,
            "worker_authorized": False, "film_master_created": False,
        }
