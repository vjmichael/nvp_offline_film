"""SHOT-01: director-authorized, shot-local USD opinions over one frozen Take.

A stronger OpenUSD layer is composed only for the requested shot interval.
The canonical world, original actor performance and Take are never edited.
This builds DATA only, not rendered frames or a final-master approval.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import (
    OpenUSDSceneBridge, _usd, _path, _vector, _evaluate,
    _layer_from_text, MAX_USD_EXACT_TICK, LAYER_TYPE)
from backend.nvp_openusd_take import FORMAT as TAKE_FORMAT
from backend.nvp_temporal_ledger import _int

FORMAT="nvp.usd.director_shot_override.v1"
MAX_OPINIONS=64
MAX_SHOT_LAYER_BYTES=256*1024
PURPOSES=frozenset(("framing","eyeline","lighting","occlusion","emotion",
                    "continuity","blocking","artistic","optics"))
CONTINUITY=frozenset(("preserve","intentional_cheat"))
PROPERTIES=frozenset(("translation_offset","visibility",
                     "camera_focal_length_mm","camera_f_stop",
                     "camera_focus_distance_m","camera_sensor_width_mm",
                     "camera_sensor_height_mm",
                     "light_intensity","eyeline_target"))


def _canonical(document):
    return json.dumps(document,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded_scalar(x,low,high):
    if (type(x) not in (int,float) or not math.isfinite(x) or
        not low<=x<=high):
        raise ValueError("Shot property outside accepted finite limits")
    return float(x)


def _normalize(changes,scene,stage):
    if type(changes) is not list or not 1<=len(changes)<=MAX_OPINIONS:
        raise ValueError("Need 1..64 bounded shot opinions")
    Gf,Sdf,Usd,UsdGeom=_usd()
    roles=scene["data"]["prim_roles"]
    native=bool(scene["data"].get("native_schema_version"))
    used=set()
    result=[]
    for entry in changes:
        if type(entry) is not dict or set(entry)!={"path","property","value"}:
            raise ValueError("Shot opinion needs exact path/property/value")
        path=_path(entry["path"],Sdf)
        prop=entry["property"]
        if path not in roles or type(prop) is not str or prop not in PROPERTIES:
            raise ValueError("Shot cannot invent source prims or property names")
        if (path,prop) in used:
            raise ValueError("Conflicting shot opinions for one property")
        used.add((path,prop))
        prim=stage.GetPrimAtPath(path)
        if not prim or not prim.IsDefined():
            raise RuntimeError("Shot target is not an existing source prim")
        val=entry["value"]
        role=roles[path]
        if prop=="translation_offset":
            order=prim.GetAttribute("xformOpOrder").Get()
            if (not UsdGeom.Xformable(prim) or order is None or
                [str(v) for v in order]!=["xformOp:translate"]):
                raise ValueError("Shot requires known canonical translate operation")
            val=_vector(val)
        elif prop=="visibility":
            if type(val) is not bool or not UsdGeom.Imageable(prim):
                raise ValueError("Shot visibility requires a boolean imageable prim")
        elif prop in ("camera_focal_length_mm","camera_f_stop",
                      "camera_focus_distance_m","camera_sensor_width_mm",
                      "camera_sensor_height_mm"):
            if role!="camera" or not native or not prim.IsA(UsdGeom.Camera):
                raise ValueError("Real native USD camera required for shot optics")
            lower,upper={
                "camera_focal_length_mm":(8.,300.),
                "camera_f_stop":(0.7,32.),
                "camera_focus_distance_m":(0.1,1000.),
                "camera_sensor_width_mm":(6.,70.),
                "camera_sensor_height_mm":(4.,50.),
            }[prop]
            val=_bounded_scalar(val,lower,upper)
        elif prop=="light_intensity":
            if role!="light" or not native:
                raise ValueError("Native USD light required")
            from pxr import UsdLux
            if not prim.IsA(UsdLux.SphereLight):
                raise ValueError("Expected native USD sphere light")
            val=_bounded_scalar(val,0.0,1_000_000.0)
        elif prop=="eyeline_target":
            if role!="actor":
                raise ValueError("Eyeline target is actor-only intention data")
            val=_vector(val)
        result.append({"path":path,"property":prop,"value":val})
    return sorted(result,key=lambda x:(x["path"],x["property"]))


def _author_layer(opinions):
    Gf,Sdf,Usd,UsdGeom=_usd()
    layer=Sdf.Layer.CreateAnonymous("nvp_director_shot.usda")
    stage=Usd.Stage.Open(layer)
    for item in opinions:
        prim=stage.OverridePrim(item["path"])
        prop,val=item["property"],item["value"]
        if prop=="translation_offset":
            order=prim.CreateAttribute(
                "xformOpOrder",Sdf.ValueTypeNames.TokenArray)
            move=prim.CreateAttribute(
                "xformOp:translate:shotOffset",Sdf.ValueTypeNames.Double3)
            if (not order.Set(
                    ["xformOp:translate","xformOp:translate:shotOffset"]) or
                not move.Set(Gf.Vec3d(*val))):
                raise RuntimeError("Native shot translation authoring failed")
        elif prop=="visibility":
            if not prim.CreateAttribute(
                "visibility",Sdf.ValueTypeNames.Token).Set(
                "inherited" if val else "invisible"):
                raise RuntimeError("Native shot visibility authoring failed")
        elif prop in ("camera_focal_length_mm","camera_f_stop",
                      "camera_focus_distance_m","camera_sensor_width_mm",
                      "camera_sensor_height_mm"):
            from backend.nvp_openusd_native_schemas import (
                MM_PER_CAMERA_UNIT,METERS_PER_UNIT)
            field,scale={
                "camera_focal_length_mm":("focalLength",1/MM_PER_CAMERA_UNIT),
                "camera_f_stop":("fStop",1.),
                "camera_focus_distance_m":("focusDistance",1/METERS_PER_UNIT),
                "camera_sensor_width_mm":("horizontalAperture",1/MM_PER_CAMERA_UNIT),
                "camera_sensor_height_mm":("verticalAperture",1/MM_PER_CAMERA_UNIT),
            }[prop]
            if not prim.CreateAttribute(field,Sdf.ValueTypeNames.Float).Set(val*scale):
                raise RuntimeError("Native shot optical parameter authoring failed")
        elif prop=="light_intensity":
            if not prim.CreateAttribute(
                "inputs:intensity",Sdf.ValueTypeNames.Float).Set(val):
                raise RuntimeError("Native shot light authoring failed")
        elif prop=="eyeline_target":
            # Director intention, NOT eye/neck mesh pose or computed gaze IK.
            if not prim.CreateAttribute(
                "nvp:shot:eyelineTarget",Sdf.ValueTypeNames.Double3,
                custom=True).Set(Gf.Vec3d(*val)):
                raise RuntimeError("Native shot eyeline metadata authoring failed")
    raw=layer.ExportToString().encode("utf-8")
    if len(raw)>MAX_SHOT_LAYER_BYTES:
        raise ValueError("Native shot USD layer exceeds bounded budget")
    return raw


class OpenUSDShotOverrides:
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("FilmIndex and trusted director approval policy required")
        self.index=index
        self.scene=OpenUSDSceneBridge(index)
        self._approve=verify_director_action

    def _take(self,project_id,take_id):
        _id(take_id,"frozen source Take")
        take=self.index.read_revision(project_id,take_id,1)
        data=take["data"]
        if (take["kind"]!="take" or data.get("format")!=TAKE_FORMAT or
            data.get("frozen") is not True):
            raise RuntimeError("Director shot needs a frozen Digital Take")
        scene,stage=self.scene.open(
            project_id,data["scene_id"],data["scene_revision"])
        if scene["document_sha256"]!=data["scene_document_sha256"]:
            raise RuntimeError("Frozen scene source SHA mismatch")
        return take,scene,stage

    def publish(self,project_id,shot_id,*,take_id,start_tick,end_tick,
                changes,purpose,continuity_policy,reason,creator_event,
                expected_revision=0):
        _require_pid(project_id)
        _id(shot_id,"director shot ID")
        _int(expected_revision,"expected shot revision")
        start=_int(start_tick,"shot start",maximum=MAX_USD_EXACT_TICK)
        end=_int(end_tick,"shot end",maximum=MAX_USD_EXACT_TICK)
        if end<=start:
            raise ValueError("Shot needs a half-open nonempty Film Time window")
        if (purpose not in PURPOSES or continuity_policy not in CONTINUITY or
            type(reason) is not str or not 1<=len(reason.strip())<=512):
            raise ValueError("Director must record shot purpose and continuity choice")
        take,scene,stage=self._take(project_id,take_id)
        if (shot_id in (take_id,scene["object_id"]) or
            end>take["data"]["duration_tick"]):
            raise ValueError("Shot identity/interval conflicts with its frozen Take")
        opinions=_normalize(changes,scene,stage)
        raw=_author_layer(opinions)
        sha=_sha(raw)
        scope={
            "operation":"nvp.usd.director_shot_override.v1",
            "project_id":project_id,"shot_id":shot_id,
            "expected_revision":expected_revision,
            "take_id":take_id,"take_document_sha256":take["document_sha256"],
            "scene_document_sha256":scene["document_sha256"],
            "start_tick":start,"end_tick":end,
            "purpose":purpose,"continuity_policy":continuity_policy,
            "reason":reason.strip(),
            "opinions_sha256":_sha(_canonical(opinions)),
            "usd_layer_sha256":sha,"final_render_approval":False,
        }
        if self._approve(creator_event,dict(scope)) is not True:
            raise PermissionError("Director did not authorize exact shot staging")
        if self.index.put_blob(project_id,raw,media_type=LAYER_TYPE)!=sha:
            raise RuntimeError("Shot USD blob SHA changed at publication")
        document={
            "format":FORMAT,
            "take_id":take_id,"take_revision":1,
            "take_document_sha256":take["document_sha256"],
            "scene_id":scene["object_id"],"scene_revision":scene["revision"],
            "scene_document_sha256":scene["document_sha256"],
            "start_tick":start,"end_tick":end,
            "purpose":purpose,"continuity_policy":continuity_policy,
            "reason":reason.strip(),"opinions":opinions,
            "opinions_sha256":scope["opinions_sha256"],
            "usd_layer_sha256":sha,
            "director_shot_change_approved":True,
            "original_scene_modified":False,
            "original_performance_modified":False,
            "presentation_render_approved":False,
            "frames_rendered":False,
        }
        def guard(db):
            for oid,rev,digest in (
                (take_id,1,take["document_sha256"]),
                (scene["object_id"],scene["revision"],scene["document_sha256"])):
                row=self.index._read_revision(db,project_id,oid,rev)
                if row is None or row["document_sha"]!=digest:
                    raise RuntimeError("Shot source changed before transaction")
            if db.execute("""SELECT 1 FROM film_blob_refs
                WHERE project_id=? AND sha256=?""",
                (project_id,sha)).fetchone() is None:
                raise RuntimeError("Director shot USD layer missing from FilmIndex")
        return self.index.register_revision(
            project_id,shot_id,"presentation",document,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id":take_id,"revision":1,"role":"source_take"},
                {"object_id":scene["object_id"],
                 "revision":scene["revision"],"role":"scene"}],
            precommit_guard=guard)

    def open_shot(self,project_id,shot_id,revision,*,tick):
        _int(tick,"shot film time",maximum=MAX_USD_EXACT_TICK)
        record=self.index.read_revision(project_id,shot_id,revision)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
            doc.get("director_shot_change_approved") is not True or
            doc.get("original_scene_modified") is not False or
            doc.get("original_performance_modified") is not False or
            doc.get("presentation_render_approved") is not False):
            raise RuntimeError("Not an authorized versioned shot USD layer")
        if not doc["start_tick"]<=tick<doc["end_tick"]:
            raise ValueError("Shot layer must not apply outside its cut interval")
        take,scene,stage=self._take(project_id,doc["take_id"])
        if (doc["take_revision"]!=1 or
            take["document_sha256"]!=doc["take_document_sha256"] or
            scene["object_id"]!=doc["scene_id"] or
            scene["revision"]!=doc["scene_revision"] or
            scene["document_sha256"]!=doc["scene_document_sha256"] or
            _sha(_canonical(doc["opinions"]))!=doc["opinions_sha256"] or
            _normalize(doc["opinions"],scene,stage)!=doc["opinions"]):
            raise RuntimeError("Shot no longer references its frozen source")
        raw=self.index.get_blob(project_id,doc["usd_layer_sha256"])
        if len(raw)>MAX_SHOT_LAYER_BYTES:
            raise RuntimeError("Director USD layer exceeds accepted size")
        _,Sdf,Usd,UsdGeom=_usd()
        layer=_layer_from_text(raw.decode("utf-8"),
                               "reopened_shot_opinions.usda",Sdf)
        # Mutate ONLY this ephemeral reconstructed source stage, not the
        # FilmIndex scene, persistent world or original Digital Take.
        stage.GetRootLayer().subLayerPaths.insert(0,layer.identifier)
        return record,scene,stage

    def evaluate(self,project_id,shot_id,revision,*,tick):
        shot,scene,stage=self.open_shot(
            project_id,shot_id,revision,tick=tick)
        data=shot["data"]
        _,canonical=self.scene.open(
            project_id,data["scene_id"],data["scene_revision"])
        Gf,Sdf,Usd,UsdGeom=_usd()
        changes=[]
        for path in sorted({item["path"] for item in data["opinions"]}):
            before=_evaluate(canonical,path,tick,Sdf,Usd,UsdGeom)
            after=_evaluate(stage,path,tick,Sdf,Usd,UsdGeom)
            prim=stage.GetPrimAtPath(path)
            item={
                "path":path,
                "role":scene["data"]["prim_roles"][path],
                "canonical_world_translation":before["world_translation"],
                "shot_world_translation":after["world_translation"],
                "shot_visibility":str(UsdGeom.Imageable(prim).ComputeVisibility(
                    Usd.TimeCode(float(tick)))),
                "opinions":[e for e in data["opinions"] if e["path"]==path],
            }
            if scene["data"].get("native_schema_version"):
                if scene["data"]["prim_roles"][path]=="camera":
                    from backend.nvp_openusd_native_schemas import MM_PER_CAMERA_UNIT
                    cam=UsdGeom.Camera(prim)
                    item["shot_focal_length_mm"]=float(
                        cam.GetFocalLengthAttr().Get(
                            Usd.TimeCode(float(tick))))*MM_PER_CAMERA_UNIT
                    item["shot_f_stop"]=float(
                        cam.GetFStopAttr().Get(Usd.TimeCode(float(tick))))
                    item["shot_focus_distance_m"]=float(
                        cam.GetFocusDistanceAttr().Get(
                            Usd.TimeCode(float(tick))))
                    item["shot_sensor_width_mm"]=float(
                        cam.GetHorizontalApertureAttr().Get(
                            Usd.TimeCode(float(tick))))*MM_PER_CAMERA_UNIT
                    item["shot_sensor_height_mm"]=float(
                        cam.GetVerticalApertureAttr().Get(
                            Usd.TimeCode(float(tick))))*MM_PER_CAMERA_UNIT
                elif scene["data"]["prim_roles"][path]=="light":
                    from pxr import UsdLux
                    item["shot_light_intensity"]=float(
                        UsdLux.LightAPI(prim).GetIntensityAttr().Get(
                            Usd.TimeCode(float(tick))))
            changes.append(item)
        return {
            "format":"nvp.usd.director_shot_evaluation.v1",
            "shot_id":shot_id,"shot_revision":revision,
            "shot_document_sha256":shot["document_sha256"],
            "source_take_document_sha256":data["take_document_sha256"],
            "scene_document_sha256":data["scene_document_sha256"],
            "time_tick":tick,
            "shot_interval":[data["start_tick"],data["end_tick"]],
            "continuity_policy":data["continuity_policy"],
            "reason":data["reason"],"changes":changes,
            "source_performance_modified":False,
            "director_shot_data_approved":True,
            "eyeline_ik_applied":False,"rendered_frames":False,
            "presentation_render_approved":False,
        }
