"""G05 — Director-approved visual staging as real, revisioned native OpenUSD.

G04 is the only authority for source/ActorID/approved creative facts.
G05 owns authorable low-poly USD geometry, cameras and lighting. A plan is a
DRAFT until the director accepts it. No render/capture/Take authority.
All USD source stays in the film's SQLite store: ordinary Studio SQLite, or
the same G03 DPAPI/AES-GCM sealed in-memory DB for protected films.
No files, asset resolver, external textures or arbitrary USD references.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import uuid
from datetime import datetime,timezone

from backend.nvp_g04_preproduction import G04Preproduction,SCENE_ID

FORMAT="nvp.g05.visual_scene.v1"
MAX_OBJECTS=96
MAX_USD_BYTES=3_000_000
OBJECT_ID=re.compile(r"O_[a-f0-9]{12}\Z")
HEX_SHA=re.compile(r"[0-9a-f]{64}\Z")
COLOR=re.compile(r"#[0-9a-fA-F]{6}\Z")
VALID_SHAPES=frozenset(("box","sphere","cone","cylinder","camera","sun","lamp"))
ROLES=frozenset(("environment","set","prop","actor","camera","light"))
WEATHER=frozenset(("clear","fog","rain","snow","cloudy"))
PRESETS={
    "box":("Box","prop","box",[1,1,1],"#b58d68"),
    "table":("Table","prop","box",[2,1,.75],"#986e4f"),
    "chair":("Chair","prop","box",[.65,.65,1],"#ad8a70"),
    "rock":("Rock","prop","sphere",[1.5,1.2,.8],"#777f8b"),
    "tree":("Tree","environment","cone",[2.8,2.8,5],"#458565"),
    "mountain":("Mountain","environment","cone",[8,8,9],"#81969c"),
    "water":("Water","environment","box",[8,5,.07],"#4686ab"),
    "lamp":("Lamp","light","lamp",[.4,.4,.4],"#ffe7b0"),
    "sun":("Sun","light","sun",[1,1,1],"#fff4cf"),
    "camera":("Camera","camera","camera",[.4,.35,.6],"#7cc6e3"),
    "sphere":("Sphere","prop","sphere",[1,1,1],"#b79bbb"),
}
SCENE_STYLE=("interior","mountains","coast","forest","open")
CAMERA_ID="O_"+hashlib.sha256(b"NVP-G05-CAMERA").hexdigest()[:12]


def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _when():
    return datetime.now(timezone.utc).isoformat()


def _oid(scene_id,key):
    return "O_"+_sha((scene_id+"\0"+key).encode("utf8"))[:12]


def _vec(value,limit=150):
    if (type(value) is not list or len(value)!=3 or any(
        type(v) not in (float,int) or not math.isfinite(v) or
        abs(v)>limit for v in value)):
        raise ValueError("Choose a position within your scene")
    return [float(v) for v in value]


def _scale(value):
    result=_vec(value,100)
    if any(not .04<=v<=100 for v in result):
        raise ValueError("Object size must be positive and reasonable")
    return result


def _name(value,limit=100):
    if type(value) is not str or not value.strip() or len(value)>limit or any(
            ord(ch)<32 for ch in value):
        raise ValueError("Choose a short object name")
    return value.strip()


def _object(scene_id,key,label,role,shape,position,scale,color,actor_id=None):
    return {"id":_oid(scene_id,key),"name":label,"role":role,
        "shape":shape,"position":position,"rotation":[0.0,0.0,0.0],
        "scale":scale,"color":color,"actor_id":actor_id,
        "preset":key.split(":")[0]}


def _daylight(when):
    t=when.casefold()
    return "night" if "night" in t else ("dusk" if any(
        token in t for token in ("dusk","sunset","evening")) else
        ("dawn" if any(token in t for token in ("dawn","sunrise","morning"))
         else "day"))


def _weather(label):
    weather=label.casefold()
    if any(x in weather for x in ("mist","fog","haze")):return "fog"
    if "snow" in weather or "blizzard" in weather:return "snow"
    if "rain" in weather or "storm" in weather:return "rain"
    if "cloud" in weather or "overcast" in weather:return "cloudy"
    return "clear"


def _scene_style(handoff):
    env=handoff["environment"]
    description=(" ".join([env["location"],handoff["scene_name"],
        handoff["director_intent"]["description"],
        handoff["director_intent"]["action"]])).casefold()
    if env["interior_exterior"].upper().startswith("INT") or any(
            name in description for name in ("kitchen","interior","bedroom","living room")):
        return "interior"
    if any(name in description for name in ("valley","mountain","cliff","ridge")):
        return "mountains"
    if any(name in description for name in ("beach","coast","shore","sea","ocean")):
        return "coast"
    if any(name in description for name in ("forest","woods","grove")):
        return "forest"
    return "open"


def _initial_plan(handoff):
    """Source-bound, conservative procedural proposal; no invented dialogue."""
    sid=handoff["scene_id"]
    env=handoff["environment"]
    style=_scene_style(handoff)
    objects=[]
    def put(key,label,role,shape,position,size,color,actor_id=None):
        objects.append(_object(sid,key,label,role,shape,position,size,color,actor_id))
    night=_daylight(env["time_of_day"])=="night"
    floor_color="#647f61" if style!="interior" else "#b5aa93"
    if style=="coast":floor_color="#d2bd8e"
    if style=="mountains":floor_color="#5b8465"
    put("ground","Ground","environment","box",[0,0,-.2],[30,30,.4],floor_color)
    if style=="interior":
        put("back_wall","Back wall","set","box",[0,8,3.0],[23,.35,6],"#aab3b6")
        put("left_wall","Side wall","set","box",[-11,0,3.0],[.35,17,6],"#b3bab5")
        if "kitchen" in (env["location"]+" "+handoff["scene_name"]).casefold():
            put("counter","Kitchen counter","set","box",[-5,5,.9],[5,1.1,1.8],"#a98b6b")
            put("table","Dining table","prop","box",[1,1,.4],[2.4,1.3,.8],"#947657")
            put("cupboard","Cupboard","set","box",[7,6,1.5],[2,1.1,3],"#b0a084")
    elif style=="mountains":
        for i,(x,y,height) in enumerate([
            (-10,8,8),(1,13,12),(12,7,9),(-6,17,11)],1):
            put("mountain:"+str(i),"Distant mountain "+str(i),
                "environment","cone",[x,y,height*.48],
                [7,7,height],"#778b85" if i%2 else "#93a5a2")
    elif style=="coast":
        put("sea","Water","environment","box",[0,10,-.08],
            [28,15,.12],"#4287a5")
        put("dune","Low dunes","environment","cone",[-9,1,1.3],
            [6,5,2.6],"#cfb787")
    elif style=="forest":
        for i,(x,y,h) in enumerate([(-8,4,5),(-3,9,7),(7,6,6),
                                     (10,-3,5),(-10,-5,7)],1):
            put("tree:"+str(i),"Tree "+str(i),"environment","cone",
                [x,y,h*.48],[2.8,2.8,h],"#4a7356")
    for i,actor in enumerate(handoff["cast"][:16]):
        aid=actor["actor_id"]
        if not aid:continue
        x=(i%5-2)*2.0
        y=-(i//5)*2.0
        put("actor:"+aid,actor["name"],"actor","cylinder",
            [x,y,.95],[.62,.62,1.9],"#b4a2c9",aid)
    for i,name in enumerate(handoff["approved_props"][:18]):
        if type(name) is not str or not name.strip():continue
        put("approved_prop:"+str(i),name[:100],"prop","box",
            [-5+(i%5)*2.2,-3-(i//5)*2.2,.55],
            [1,1,1.1],"#c3a780")
    put("camera","Main camera","camera","camera",[10,-15,8],
        [.65,.65,.65],"#68b8d3")
    put("sun","Key light","light","sun",[-7,-6,12],
        [1,1,1],"#ffd7a0" if night else "#fff3c5")
    return {"format":FORMAT,
            "source":{"scene_id":sid,"project_id":handoff["project_id"],
                "scene_sha256":handoff["scene_source_sha256"],
                "script_revision":handoff["script_revision"],
                "notes_revision":handoff["director_notes_revision"],
                "original_script_sha256":handoff["original_script_sha256"]},
            "scene_name":handoff["scene_name"],
            "visual_style":style,
            "setting":{"location":env["location"],
                       "time_of_day":env["time_of_day"],
                       "season":env["season"],"era":env["era"],
                       "weather":_weather(env["weather"]),
                       "weather_description":env["weather"],
                       "daylight":_daylight(env["time_of_day"])},
            "objects":objects,
            "cast_refs":[{"actor_id":actor["actor_id"],"name":actor["name"]}
                         for actor in handoff["cast"] if actor["actor_id"]],
            "dialogue_refs":[{"actor_id":line["actor_id"],
                              "source_line":line["source_line"]}
                             for line in handoff["dialogue"]],
            "approved_props":handoff["approved_props"],
            "unknowns":handoff["unresolved_questions"]+
                        (["Who is speaking?"] if handoff["unresolved_speaker_cues"] else []),
            "contains_external_asset_paths":False,
            "model_authorized":False,
            "worker_authorized":False,
            "take_created":False}


def _validate(plan,handoff):
    if type(plan) is not dict or plan.get("format")!=FORMAT:
        raise ValueError("This scene has an unrecognized authoring format")
    src=plan.get("source")
    if (type(src) is not dict or
        src.get("scene_id")!=handoff["scene_id"] or
        src.get("project_id")!=handoff["project_id"] or
        src.get("scene_sha256")!=handoff["scene_source_sha256"] or
        src.get("script_revision")!=handoff["script_revision"] or
        src.get("notes_revision")!=handoff["director_notes_revision"]):
        raise RuntimeError("Your scene notes or screenplay have changed; rebuild the stage")
    if (plan.get("contains_external_asset_paths") is not False or
        plan.get("worker_authorized") is not False or
        plan.get("take_created") is not False):
        raise ValueError("Scene authoring cannot run production workers")
    setting=plan.get("setting")
    if not isinstance(setting,dict) or setting.get("weather") not in WEATHER or (
            setting.get("daylight") not in ("day","night","dawn","dusk")):
        raise ValueError("Choose valid scene lighting and weather")
    objects=plan.get("objects")
    if type(objects) is not list or not 1<=len(objects)<=MAX_OBJECTS:
        raise ValueError("Scene size exceeds available creative workspace")
    ids=set();actors={c["actor_id"] for c in handoff["cast"]
                     if c["actor_id"]}
    camera=0
    for item in objects:
        if (type(item) is not dict or
            set(item)!={"id","name","role","shape","position","rotation",
                        "scale","color","actor_id","preset"} or
            type(item["id"]) is not str or not OBJECT_ID.fullmatch(item["id"]) or
            item["id"] in ids):
            raise ValueError("The scene contains a duplicate or unknown object")
        ids.add(item["id"])
        _name(item["name"]);_vec(item["position"]);_vec(item["rotation"],360)
        _scale(item["scale"])
        if (item["role"] not in ROLES or item["shape"] not in VALID_SHAPES
                or type(item["color"]) is not str or
                not COLOR.fullmatch(item["color"]) or
                type(item["preset"]) is not str or len(item["preset"])>100):
            raise ValueError("Unsupported scene object")
        if item["role"]=="actor":
            if (item["actor_id"] not in actors or
                    item["shape"]!="cylinder"):
                raise ValueError("Scene actor must have a verified film ActorID")
        elif item["actor_id"] is not None:
            raise ValueError("Only performers may carry film ActorIDs")
        if item["role"]=="camera":
            if item["shape"]!="camera":raise ValueError("Invalid scene camera")
            camera+=1
        if item["shape"] in ("sun","lamp") and item["role"]!="light":
            raise ValueError("Invalid light")
        if item["role"]=="light" and item["shape"] not in ("sun","lamp"):
            raise ValueError("Invalid lighting fixture")
    if camera<1 or camera>8:
        raise ValueError("Scene needs at least one camera")
    if len(_json(plan).encode("utf8"))>180_000:
        raise ValueError("Scene has too much authored data")


def _usd_color(s):
    return tuple(int(s[i:i+2],16)/255 for i in (1,3,5))


def _build_usd(plan):
    """Author actual USD geometry and verify a fresh independent stage reopen."""
    try:
        from pxr import Gf,Sdf,Usd,UsdGeom,UsdLux,UsdShade
    except ImportError as exc:
        raise RuntimeError("NVP's native scene authoring is unavailable") from exc
    layer=Sdf.Layer.CreateAnonymous("nvp-director-scene.usda")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    root=UsdGeom.Xform.Define(stage,"/World")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.Scope.Define(stage,"/World/Looks")
    UsdGeom.Xform.Define(stage,"/World/Objects")
    palette={}
    def material(color):
        if color in palette:return palette[color]
        path="/World/Looks/Color_"+color[1:].upper()
        mat=UsdShade.Material.Define(stage,path)
        shader=UsdShade.Shader.Define(stage,path+"/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        rgb=_usd_color(color)
        shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*rgb))
        shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(.8)
        shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),"surface")
        palette[color]=mat
        return mat
    for object_ in plan["objects"]:
        path="/World/Objects/"+object_["id"]
        prim=UsdGeom.Xform.Define(stage,path)
        api=UsdGeom.XformCommonAPI(prim)
        api.SetTranslate(Gf.Vec3d(*object_["position"]))
        api.SetRotate(Gf.Vec3f(*object_["rotation"]))
        api.SetScale(Gf.Vec3f(*object_["scale"]))
        holder=prim.GetPrim()
        holder.CreateAttribute("nvp:sceneObjectId",Sdf.ValueTypeNames.String).Set(object_["id"])
        holder.CreateAttribute("nvp:displayName",Sdf.ValueTypeNames.String).Set(object_["name"])
        holder.CreateAttribute("nvp:semanticRole",Sdf.ValueTypeNames.String).Set(object_["role"])
        if object_["actor_id"]:
            holder.CreateAttribute("nvp:ActorID",Sdf.ValueTypeNames.String).Set(object_["actor_id"])
        geometry_path=path+"/Geometry"
        shape=object_["shape"]
        if shape=="box":
            obj=UsdGeom.Cube.Define(stage,geometry_path)
            obj.CreateSizeAttr(1.)
        elif shape=="sphere":
            obj=UsdGeom.Sphere.Define(stage,geometry_path)
            obj.CreateRadiusAttr(.5)
        elif shape=="cone":
            obj=UsdGeom.Cone.Define(stage,geometry_path)
            obj.CreateRadiusAttr(.5);obj.CreateHeightAttr(1.)
            obj.CreateAxisAttr(UsdGeom.Tokens.z)
        elif shape=="cylinder":
            obj=UsdGeom.Cylinder.Define(stage,geometry_path)
            obj.CreateRadiusAttr(.5);obj.CreateHeightAttr(1.)
            obj.CreateAxisAttr(UsdGeom.Tokens.z)
            if object_["role"]=="actor":
                head=UsdGeom.Sphere.Define(stage,path+"/Head")
                # Child head uses the same parent scale; place in normalized
                # actor-local units rather than adding another world transform.
                UsdGeom.XformCommonAPI(head).SetTranslate(Gf.Vec3d(0,0,.45))
                head.CreateRadiusAttr(.42)
        elif shape=="camera":
            camera=UsdGeom.Camera.Define(stage,geometry_path)
            camera.CreateFocalLengthAttr(35.)
            camera.CreateHorizontalApertureAttr(36.)
            obj=None
        elif shape=="sun":
            light=UsdLux.DistantLight.Define(stage,geometry_path)
            light.CreateIntensityAttr(1.1 if plan["setting"]["daylight"]!="night" else .25)
            light.CreateColorAttr(Gf.Vec3f(*_usd_color(object_["color"])))
            obj=None
        elif shape=="lamp":
            light=UsdLux.SphereLight.Define(stage,geometry_path)
            light.CreateRadiusAttr(.15)
            light.CreateIntensityAttr(500.)
            light.CreateColorAttr(Gf.Vec3f(*_usd_color(object_["color"])))
            obj=None
        else:
            raise ValueError("Scene shape cannot be authored in native USD")
        if obj is not None:
            UsdShade.MaterialBindingAPI.Apply(obj.GetPrim()).Bind(
                material(object_["color"]))
    # Weather/daylight are NVP creative state, not baked meteorological facts.
    sky=stage.GetPrimAtPath("/World")
    sky.CreateAttribute("nvp:weather",Sdf.ValueTypeNames.String).Set(
        plan["setting"]["weather"])
    sky.CreateAttribute("nvp:daylight",Sdf.ValueTypeNames.String).Set(
        plan["setting"]["daylight"])
    raw=layer.ExportToString().encode("utf8")
    if not 0<len(raw)<=MAX_USD_BYTES:
        raise ValueError("OpenUSD scene is too large to save")
    return raw,_reopen_usd(raw,plan)


def _reopen_usd(raw,plan):
    """Use a NEW layer, not the authoring stage, for a real parse/shape audit."""
    from pxr import Sdf,Usd,UsdGeom
    layer=Sdf.Layer.CreateAnonymous("nvp-director-reopen.usda")
    if not layer.ImportFromString(raw.decode("utf8")):
        raise RuntimeError("Original OpenUSD scene did not reopen")
    if layer.subLayerPaths or layer.GetExternalReferences():
        raise RuntimeError("Scene unexpectedly refers to an external file")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if (stage is None or
        UsdGeom.GetStageUpAxis(stage)!=UsdGeom.Tokens.z or
        abs(UsdGeom.GetStageMetersPerUnit(stage)-1.)>1e-7):
        raise RuntimeError("Scene spatial metadata is not native")
    manifest=[]
    for item in plan["objects"]:
        prim=stage.GetPrimAtPath("/World/Objects/"+item["id"])
        if not prim or not prim.IsA(UsdGeom.Xform):
            raise RuntimeError("Native scene object missing on reopen")
        actor=prim.GetAttribute("nvp:ActorID")
        if item["actor_id"] and (
                not actor or actor.Get()!=item["actor_id"]):
            raise RuntimeError("Reopened performer is not the requested ActorID")
        geometry=stage.GetPrimAtPath(prim.GetPath().pathString+"/Geometry")
        shape=item["shape"]
        expected={
            "box":UsdGeom.Cube,"sphere":UsdGeom.Sphere,
            "cone":UsdGeom.Cone,"cylinder":UsdGeom.Cylinder,
            "camera":UsdGeom.Camera
        }
        if shape in expected and (not geometry or not geometry.IsA(expected[shape])):
            raise RuntimeError("Reopened USD geometry differs from the stage")
        transform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default())
        loc=transform.ExtractTranslation()
        if any(abs(float(loc[i])-item["position"][i])>1e-4 for i in range(3)):
            raise RuntimeError("Native USD scene position did not survive saving")
        manifest.append({"id":item["id"],"shape":shape,
                         "position":[float(loc[i]) for i in range(3)]})
    return manifest


class G05SceneAuthoring:
    """One film project, one scene, compare-and-swap revisions."""

    def __init__(self,studio,live=None,token=None):
        self.g04=G04Preproduction(studio,live,token)

    @staticmethod
    def _schema(db):
        db.execute("""CREATE TABLE IF NOT EXISTS g05_scene_heads(
            project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
            revision INTEGER NOT NULL, source_sha256 TEXT NOT NULL,
            status TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id,scene_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS g05_scene_versions(
            project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
            revision INTEGER NOT NULL,source_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,plan_json TEXT NOT NULL,
            usd_layer BLOB NOT NULL, usd_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(project_id,scene_id,revision))""")

    def _handoff(self,db,movie,scene_id):
        library=self.g04._view(db,movie)
        scene=next((x for x in library["scenes"] if x["id"]==scene_id),None)
        if scene is None:raise KeyError("This scene is no longer in the movie")
        facts=[x for x in library["bible"]["facts"] if x["scene_id"]==scene_id]
        approved={}
        for item in facts:
            approved.setdefault(item["category"],[]).append(item["value"])
        return {"format":"nvp.g04.g05_scene_handoff.v1",
            "scene_id":scene_id,"project_id":movie["id"],
            "scene_source_sha256":scene["source_sha256"],
            "script_revision":movie["revision"],
            "director_notes_revision":scene["notes_revision"],
            "original_script_sha256":scene["script_source_sha256"],
            "scene_name":scene["heading"],
            "source_line_range":scene["script_lines"],
            "environment":{
                "interior_exterior":scene["interior_exterior"],
                "location":scene["notes"]["location"] or scene["location"],
                "time_of_day":scene["notes"]["time_of_day"] or scene["time_of_day"],
                "era":scene["notes"]["era"],"season":scene["notes"]["season"],
                "weather":scene["notes"]["weather"]},
            "director_intent":{
                "description":scene["notes"]["description"],
                "action":scene["notes"]["action"]},
            "cast":[{"actor_id":p["actor_id"],"name":p["name"]}
                    for p in scene["cast"] if p["actor_id"]],
            "dialogue":[{"actor_id":v["actor_id"],
                         "source_line":v["line_number"]}
                        for v in scene["dialogue"]],
            "approved_props":approved.get("prop",[]),
            "unresolved_questions":scene["questions"],
            "unresolved_speaker_cues":[x["source_cue"] for x in scene["cast"]
                                         if x.get("needs_review")]}

    def _with(self,pid,scene_id,callback,mutate=False):
        if type(scene_id) is not str or not SCENE_ID.fullmatch(scene_id):
            raise ValueError("Select a movie scene")
        def fn(db,movie):
            self._schema(db)
            source=self._handoff(db,movie,scene_id)
            return callback(db,movie,source)
        return self.g04._execute(pid,fn,mutate=mutate)

    @staticmethod
    def _record(db,pid,sid):
        head=db.execute("""SELECT * FROM g05_scene_heads WHERE
            project_id=? AND scene_id=?""",(pid,sid)).fetchone()
        if head is None:return None,None
        version=db.execute("""SELECT * FROM g05_scene_versions WHERE
            project_id=? AND scene_id=? AND revision=?""",
            (pid,sid,head["revision"])).fetchone()
        if version is None:
            raise RuntimeError("Saved scene revision is missing")
        return dict(head),dict(version)

    @staticmethod
    def _public(db,source,head,record):
        if head is None:
            return {"created":False,"scene_id":source["scene_id"],
                "source_sha256":source["scene_source_sha256"],
                "source_revision":source["script_revision"],
                "notes_revision":source["director_notes_revision"],
                "scene_name":source["scene_name"],
                "status":"not_created","current":True,
                "draft":True,"revision":0,"objects":[],
                "available_presets":sorted(PRESETS),
                "past_versions":[],"filming_authorized":False}
        if (_sha(record["usd_layer"])!=record["usd_sha256"] or
            _sha(record["plan_json"].encode("utf8"))=="" ):
            raise RuntimeError("A saved scene has been altered")
        plan=json.loads(record["plan_json"])
        _validate(plan,source) if head["source_sha256"]==source["scene_source_sha256"] else None
        if head["source_sha256"]==source["scene_source_sha256"]:
            _reopen_usd(record["usd_layer"],plan)
        versions=db.execute("""SELECT revision,status,created_at
            FROM g05_scene_versions WHERE project_id=? AND scene_id=?
            ORDER BY revision DESC LIMIT 20""",
            (source["project_id"],source["scene_id"])).fetchall()
        current=(head["source_sha256"]==source["scene_source_sha256"])
        return {"created":True,"scene_id":source["scene_id"],
            "source_sha256":source["scene_source_sha256"],
            "source_revision":source["script_revision"],
            "notes_revision":source["director_notes_revision"],
            "scene_name":source["scene_name"],
            "status":head["status"] if current else "outdated",
            "current":current,"revision":head["revision"],
            "draft":head["status"]!="approved" or not current,
            "objects":plan["objects"],"setting":plan["setting"],
            "visual_style":plan["visual_style"],
            "stage_sha256":record["usd_sha256"],
            "stage_native_opensud_reopened":current,
            "available_presets":sorted(PRESETS),
            "past_versions":[dict(v) for v in versions],
            "unresolved_questions":plan["unknowns"],
            "filming_authorized":False}

    def view(self,pid,scene_id):
        def read(db,movie,source):
            head,rec=self._record(db,pid,scene_id)
            return self._public(db,source,head,rec)
        return self._with(pid,scene_id,read)

    @staticmethod
    def _persist(db,pid,source,plan,expected_revision,status):
        _validate(plan,source)
        raw,manifest=_build_usd(plan)
        text=_json(plan)
        digest=_sha(raw)
        prior=db.execute("""SELECT revision FROM g05_scene_heads
            WHERE project_id=? AND scene_id=?""",(pid,source["scene_id"])).fetchone()
        actual=0 if prior is None else prior["revision"]
        if actual!=expected_revision:
            raise RuntimeError("Scene changed; reopen before saving")
        new=actual+1
        db.execute("""INSERT INTO g05_scene_versions
            (project_id,scene_id,revision,source_sha256,status,plan_json,
             usd_layer,usd_sha256,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (pid,source["scene_id"],new,source["scene_source_sha256"],
             status,text,raw,digest,_when()))
        db.execute("""INSERT INTO g05_scene_heads
            (project_id,scene_id,revision,source_sha256,status,updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(project_id,scene_id) DO UPDATE SET
                revision=excluded.revision,
                source_sha256=excluded.source_sha256,
                status=excluded.status,updated_at=excluded.updated_at""",
            (pid,source["scene_id"],new,source["scene_source_sha256"],
             status,_when()))
        head,record=G05SceneAuthoring._record(db,pid,source["scene_id"])
        return G05SceneAuthoring._public(db,source,head,record)

    def generate(self,pid,scene_id,expected_revision=0):
        """Make/rebuild an UNAPPROVED OpenUSD scene from known creative facts."""
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Scene revision is invalid")
        def operation(db,movie,source):
            plan=_initial_plan(source)
            return self._persist(db,pid,source,plan,expected_revision,"draft")
        return self._with(pid,scene_id,operation,mutate=True)

    def edit(self,pid,scene_id,expected_revision,operation,details):
        """All visual edits commit actual new OpenUSD versions, never a fake UI."""
        if (type(expected_revision) is not int or expected_revision<1 or
            type(operation) is not str or type(details) is not dict):
            raise ValueError("Select an existing scene change")
        def change(db,movie,source):
            head,record=self._record(db,pid,scene_id)
            if not head or head["revision"]!=expected_revision:
                raise RuntimeError("Stage changed; reopen before editing")
            if head["source_sha256"]!=source["scene_source_sha256"]:
                raise RuntimeError("Screenplay or director notes changed; rebuild first")
            plan=json.loads(record["plan_json"])
            objects=plan["objects"]
            if operation=="add":
                if set(details)-{"preset","actor_id"}:
                    raise ValueError("Unsupported scene object request")
                preset=details.get("preset")
                if preset=="actor":
                    selected=next((a for a in source["cast"]
                        if a["actor_id"]==details.get("actor_id")),None)
                    if selected is None:
                        raise ValueError("Choose a performer from this movie")
                    label=selected["name"]
                    role="actor";shape="cylinder";scale=[.62,.62,1.9]
                    color="#b4a2c9";actor_id=selected["actor_id"]
                else:
                    if preset not in PRESETS:
                        raise ValueError("Choose an available scene object")
                    label,role,shape,scale,color=PRESETS[preset]
                    actor_id=None
                if len(objects)>=MAX_OBJECTS:
                    raise ValueError("This scene has reached its object limit")
                new_id="O_"+uuid.uuid4().hex[:12]
                objects.append({"id":new_id,"name":label,"role":role,
                    "shape":shape,"position":[0.,0.,1. if shape not in ("sun","camera") else 5.],
                    "rotation":[0.,0.,0.],"scale":list(scale),
                    "color":color,"actor_id":actor_id,"preset":preset})
            elif operation in ("move","rotate","resize","recolor","rename","remove"):
                if type(details.get("id")) is not str or not OBJECT_ID.fullmatch(
                        details["id"]):
                    raise ValueError("Choose an existing scene object")
                item=next((x for x in objects if x["id"]==details["id"]),None)
                if item is None:raise KeyError("That scene object no longer exists")
                if operation=="move":
                    if set(details)!={"id","position"}:raise ValueError("Invalid move")
                    item["position"]=_vec(details["position"])
                if operation=="rotate":
                    if set(details)!={"id","rotation"}:raise ValueError("Invalid turn")
                    item["rotation"]=_vec(details["rotation"],360)
                if operation=="resize":
                    if set(details)!={"id","scale"}:raise ValueError("Invalid object size")
                    item["scale"]=_scale(details["scale"])
                if operation=="recolor":
                    if (set(details)!={"id","color"} or
                        type(details["color"]) is not str or not
                            COLOR.fullmatch(details["color"])):
                        raise ValueError("Choose a valid object color")
                    item["color"]=details["color"]
                if operation=="rename":
                    if set(details)!={"id","name"}:raise ValueError("Invalid object label")
                    item["name"]=_name(details["name"])
                if operation=="remove":
                    if item["role"]=="camera" and sum(
                            o["role"]=="camera" for o in objects)==1:
                        raise ValueError("A scene needs one camera")
                    objects.remove(item)
            elif operation=="weather":
                if set(details)!={"weather"} or details["weather"] not in WEATHER:
                    raise ValueError("Choose fog, snow, rain, clouds or clear sky")
                plan["setting"]["weather"]=details["weather"]
            elif operation=="daylight":
                if set(details)!={"daylight"} or details["daylight"] not in (
                        "day","night","dawn","dusk"):
                    raise ValueError("Choose a time of day")
                plan["setting"]["daylight"]=details["daylight"]
            else:
                raise ValueError("That kind of scene change is not supported")
            return self._persist(db,pid,source,plan,expected_revision,"draft")
        return self._with(pid,scene_id,change,mutate=True)

    def restore(self,pid,scene_id,expected_revision,source_revision):
        if (type(expected_revision) is not int or expected_revision<1 or
            type(source_revision) is not int or source_revision<1):
            raise ValueError("Select a saved scene version")
        def change(db,movie,source):
            head,record=self._record(db,pid,scene_id)
            if not head or head["revision"]!=expected_revision:
                raise RuntimeError("Scene changed; reopen before restoring")
            earlier=db.execute("""SELECT * FROM g05_scene_versions
                WHERE project_id=? AND scene_id=? AND revision=?""",
                (pid,scene_id,source_revision)).fetchone()
            if earlier is None:raise KeyError("Earlier scene version is missing")
            if earlier["source_sha256"]!=source["scene_source_sha256"]:
                raise RuntimeError("Earlier scene used a different screenplay or direction")
            if _sha(earlier["usd_layer"])!=earlier["usd_sha256"]:
                raise RuntimeError("Earlier scene OpenUSD cannot be trusted")
            plan=json.loads(earlier["plan_json"])
            return self._persist(db,pid,source,plan,expected_revision,"draft")
        return self._with(pid,scene_id,change,mutate=True)

    def approve(self,pid,scene_id,expected_revision):
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("Choose an authored stage to approve")
        def change(db,movie,source):
            head,record=self._record(db,pid,scene_id)
            if not head or head["revision"]!=expected_revision:
                raise RuntimeError("Stage changed; review the latest version")
            if head["source_sha256"]!=source["scene_source_sha256"]:
                raise RuntimeError("Scene source changed; rebuild before approving")
            if head["status"]=="approved":
                raise RuntimeError("This stage is already approved")
            plan=json.loads(record["plan_json"])
            return self._persist(db,pid,source,plan,expected_revision,"approved")
        return self._with(pid,scene_id,change,mutate=True)

    def native_stage(self,pid,scene_id):
        """Internal G06 host reader; not a WebView USD file path."""
        def read(db,movie,source):
            head,record=self._record(db,pid,scene_id)
            if not head or head["status"]!="approved" or (
                    head["source_sha256"]!=source["scene_source_sha256"]):
                raise RuntimeError("Director has not approved the current scene")
            if _sha(record["usd_layer"])!=record["usd_sha256"]:
                raise RuntimeError("Original OpenUSD stage bytes changed")
            plan=json.loads(record["plan_json"])
            _validate(plan,source)
            _reopen_usd(record["usd_layer"],plan)
            return {"project_id":pid,"scene_id":scene_id,
                    "revision":head["revision"],
                    "source_sha256":head["source_sha256"],
                    "usd_bytes":bytes(record["usd_layer"]),
                    "usd_sha256":record["usd_sha256"],
                    "approved":True,"filming_authorized":False}
        return self._with(pid,scene_id,read)
