"""P1-B/C: actual creator-selected GLB → authoritative multi-actor USD scene.

New scene identity is a fresh source revision, not an edit to a previously
approved Digital Take. Every actor, GLB SHA and 3D rig source is independently
resolved by FilmIndex and native USD after restart. External filenames, model
scripts, arbitrary scene layers and silent skin substitutions are forbidden.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_p1bc_actor_registry import ActorDirectory
from backend.nvp_p1bc_glb_character import (
    FORMAT as GLB_FORMAT, ImportedCharacterSources,
    extract_original_glb_skin)
from backend.nvp_openusd_skinning import normalize_skin
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

MAX_CAST=8
FORMAT="nvp.p1bc.native_actor_scene_cast.v1"


def _sha(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


def resolve_imported_character_sources(index,project_id,cast,rigs,entries,
                                       *,verify_manifest=False,
                                       composed_stage=None):
    """Verify SOURCE GLB vertices, USD bone matrices and FilmIndex asset edges."""
    if type(entries) is not list or len(entries)>MAX_CAST:
        raise ValueError("Imported actor source list exceeds rigged scene capacity")
    by_id={c["actor_id"]:c for c in cast}
    by_path={r["path"]:r for r in rigs}
    seen=set()
    normalized=[]
    for source in entries:
        required=({"actor_id","path","character_asset_id",
                   "character_asset_revision",
                   "character_asset_document_sha256","original_glb_sha256"}
                  if verify_manifest else
                  {"actor_id","path","character_asset_id","character_asset_revision"})
        if type(source) is not dict or set(source)!=required:
            raise ValueError("Imported character must have exact ActorID + pinned asset source")
        actor=_id(source["actor_id"],"original imported ActorID")
        path=source["path"]
        asset=_id(source["character_asset_id"],"imported character FilmIndex source")
        revision=source["character_asset_revision"]
        if (type(revision) is not int or revision!=1 or actor in seen
            or actor not in by_id or by_id[actor]["path"]!=path
            or path not in by_path):
            raise ValueError("Imported source lacks unique native skinned ActorID")
        seen.add(actor)
        rec=index.read_revision(project_id,asset,revision)
        doc=rec["data"]
        if (rec["kind"]!="asset" or doc.get("format")!=GLB_FORMAT or
            doc.get("registered_character_id")!=asset):
            raise RuntimeError("Imported character cannot be sourced from this project")
        data=json.loads(index.get_blob(project_id,doc["normalized_rig_sha256"]))
        rig=by_path[path]
        if (rig.get("joints")!=data["joints"] or
            rig.get("original_glb_sha256",
                    rig.get("skin",{}).get("source_glb_sha256"))!=
                doc["original_glb_sha256"]):
            raise RuntimeError("Native actor rig is not an exact imported GLB joint set")
        if not verify_manifest:
            if (rig.get("rest_transforms")!=data["rest_transforms"] or
                rig.get("bind_transforms")!=data["bind_transforms"] or
                normalize_skin(rig["skin"],len(rig["joints"]))!=
                normalize_skin(data["skin"],len(data["joints"]))):
                raise RuntimeError("Imported GLB mesh or bind/rest source was substituted")
        elif composed_stage is not None:
            from pxr import UsdGeom, UsdSkel
            prim=composed_stage.GetPrimAtPath(path+"/Rig/CharacterMesh")
            if (not prim.IsA(UsdGeom.Mesh) or
                not prim.HasAPI(UsdSkel.BindingAPI) or
                prim.GetAttribute("nvp:sourceGLBSHA256").Get()!=
                    doc["original_glb_sha256"] or
                len(UsdGeom.Mesh(prim).GetPointsAttr().Get())!=
                    doc["source_vertex_count"]):
                raise RuntimeError("Frozen imported source mesh identity changed")
        item={"actor_id":actor,"path":path,"character_asset_id":asset,
              "character_asset_revision":revision,
              "character_asset_document_sha256":rec["document_sha256"],
              "original_glb_sha256":doc["original_glb_sha256"]}
        if verify_manifest and item!=source:
            raise RuntimeError("Pinned original GLB source manifest changed on reopen")
        normalized.append(item)
    return sorted(normalized,key=lambda x:x["path"])


class NativeActorSceneCasting:
    """Trusted native filmmaker authored source scene with REAL GLB skin."""
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("Trusted FilmIndex and native human approval required")
        self.index=index
        self.authorize=verify_director_action
        self.importer=ImportedCharacterSources(index)

    def publish(self,project_id,scene_id,*,cast,creator_event,
                camera_height=8.0):
        _require_pid(project_id)
        _id(scene_id,"new actor source USD scene")
        if type(cast) is not list or not 1<=len(cast)<=MAX_CAST:
            raise ValueError("At least one and no more than eight skinned actors")
        if (type(camera_height) not in (int,float) or
            not math.isfinite(camera_height) or not 2<=camera_height<=30):
            raise ValueError("Source USD camera height must be finite and bounded")
        checked=[]
        seen_actors=set()
        identities=ActorDirectory(self.index,verify_director_action=lambda *_:False)
        for number,item in enumerate(cast,1):
            old_fields={"actor_id","character_asset_id","position",
                        "motion_joint","travel"}
            face_fields=old_fields|{"face_target","face_strength"}
            if type(item) is not dict or set(item) not in (old_fields,face_fields):
                raise ValueError("Scene cast requires exact ActorID/source/pose choices")
            actor=_id(item["actor_id"],"source scene ActorID")
            asset=_id(item["character_asset_id"],"source skinned GLB asset")
            position=item["position"]
            if (actor in seen_actors or type(position) is not list or
                len(position)!=3 or any(type(v) not in (int,float) or
                not math.isfinite(v) or abs(v)>100 for v in position)):
                raise ValueError("Duplicate actor or invalid original 3D staging position")
            seen_actors.add(actor)
            original=identities.open(project_id,actor,1)
            registry,raw=self.importer._registered(project_id,asset)
            decoded=extract_original_glb_skin(raw)
            motion=item["motion_joint"]
            travel=item["travel"]
            if motion is not None and motion not in decoded["joints"]:
                raise ValueError("Acting motion must select an actual original rig joint")
            if type(travel) not in (int,float) or not math.isfinite(travel) or abs(travel)>0.5:
                raise ValueError("Authored acting joint motion exceeds 0.5 metre")
            face_target=item.get("face_target")
            face_strength=item.get("face_strength",0.0)
            names={x["name"] for x in decoded["skin"].get("facial_targets",[])}
            if ((face_target is not None and face_target not in names) or
                (type(face_strength) not in (int,float) or
                 not math.isfinite(face_strength) or
                 not 0<=face_strength<=1) or
                (face_target is None and face_strength!=0)):
                raise ValueError("Facial expression must be an actual original GLB morph")
            path="/World/Actor"+str(number).zfill(3)
            checked.append({
                "actor_id":actor,"character_asset_id":asset,
                "actor_document_sha256":original["document_sha256"],
                "original_glb_sha256":registry["sha"],
                "path":path,"position":[float(v) for v in position],
                "motion_joint":motion,"travel":float(travel),
                "face_target":face_target,"face_strength":float(face_strength),
            })
        scope={"operation":FORMAT,"project_id":project_id,
               "scene_id":scene_id,"creator_cast_sha256":_sha(checked),
               "camera_height":float(camera_height),
               "source_glb_shas":[x["original_glb_sha256"] for x in checked]}
        if self.authorize(creator_event,dict(scope)) is not True:
            raise PermissionError("Creator rejected exact original cast and 3D scene source")
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        prims=[
            {"path":"/World/Camera","role":"camera",
             "position":[0,0,float(camera_height)]},
            {"path":"/World/Key","role":"light","position":[2,3,6]},
        ]
        rigs=[]
        actor_bindings=[]
        imported=[]
        parameters=[{
            "path":"/World/Key","property":"light.intensity",
            "samples":[{"tick":0,"value":300.0},
                       {"tick":TICKS_PER_SECOND,"value":300.0}]
        }]
        for source in checked:
            # Source read, hash, and extracted geometry are reverified
            # AFTER approval, before any new scene is made authoritative.
            asset=self.importer.import_registered(
                project_id,source["character_asset_id"])
            actor=identities.open(project_id,source["actor_id"],1)
            if (actor["document_sha256"]!=source["actor_document_sha256"] or
                asset["data"]["original_glb_sha256"]!=source["original_glb_sha256"]):
                raise RuntimeError("Actor or original GLB changed during human approval")
            rig=self.importer.rig(
                project_id,source["character_asset_id"],1,path=source["path"],
                motion_joint=source["motion_joint"],travel=source["travel"])
            rigs.append(rig)
            prims.append({"path":source["path"],"role":"actor",
                          "position":source["position"]})
            actor_bindings.append({"actor_id":source["actor_id"],
                                   "actor_revision":1,"path":source["path"]})
            imported.append({"actor_id":source["actor_id"],
                             "path":source["path"],
                             "character_asset_id":source["character_asset_id"],
                             "character_asset_revision":1})
            if source["face_target"] is not None:
                parameters.append({
                    "path":source["path"],
                    "property":"face."+source["face_target"],
                    "samples":[{"tick":0,"value":0.0},
                               {"tick":TICKS_PER_SECOND,
                                "value":source["face_strength"]}],
                })
        scene=OpenUSDSceneBridge(self.index).publish(
            project_id,scene_id,prims=prims,curves=[],native_schemas=True,
            skeletal_rigs=rigs,actor_bindings=actor_bindings,
            imported_character_sources=imported,
            # Explicit creator-selected facial and original authored light
            # controls; never inferred from a GLB filename or recorded voice.
            performance_channels=parameters)
        return {"format":FORMAT,"scene_id":scene_id,
                "scene_revision":scene["revision"],
                "scene_document_sha256":scene["document_sha256"],
                "cast":checked,"imported_glb_skins":len(rigs),
                "source_film_time_animated":any(
                    x["travel"]!=0 or x["face_strength"]!=0 for x in checked),
                "original_glb_facial_shapes_animated":sum(
                    x["face_target"] is not None for x in checked),
                "original_sources_modified":False,"picture_rendered":False,
                "director_authorized":True}
