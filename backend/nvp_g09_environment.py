"""G09-A — director-approved non-destructive production environments.

All look and set-dressing revisions are derived edit decisions linked to an
immutable G06 Take SHA, never changes to a source USD or PCM original.
A producer can reuse an approved look across Takes as an immutable kit.
Nothing is rendered until a director explicitly approves and G08 binds the
approved look digest to an export job. No external textures, arbitrary file
paths, remotely supplied Python scripts or materials are admitted.

Native USD/MaterialX production rendering remains a separately reviewed worker;
this G09-A source model carries physically based parameters and provenance.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
from datetime import datetime,timezone

from backend.nvp_g07_edit import G07Editor,_json,_sha
from backend.nvp_g06_filming import HEX

FORMAT="nvp.g09.environment.v1"
BUILTIN_VERSION="nvp.g09.kits.2026-11-11.v1"
MAX_ITEMS=110
MAX_OBJECT_MATERIALS=100
MAX_KITS=80
PRESETS=("original","interior","city","mountains","coast","forest",
         "desert","farmland","space","open")
SHAPES=("box","sphere","cone","cylinder")
MATERIALS=("stone","plaster","glass","wood","metal","earth","foliage","fabric")
_COLOR=re.compile(r"#[a-fA-F0-9]{6}\Z")
_OBJECT=re.compile(r"O_[0-9a-f]{12}\Z")
_KIT_ID=re.compile(r"K_[0-9a-f]{24}\Z")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _check_color(value):
    if type(value) is not str or not _COLOR.fullmatch(value):
        raise ValueError("Choose a valid scene color")
    return value.lower()


def _number(value,low,high,what):
    if type(value) not in (int,float) or type(value) is bool or not math.isfinite(value):
        raise ValueError("Choose a valid "+what)
    if not low<=value<=high:
        raise ValueError("The "+what+" is outside a filmable range")
    return float(value)


def _vec(value,low=-150,high=150):
    if type(value) is not list or len(value)!=3:
        raise ValueError("Choose a scene position in 3D")
    return [_number(v,low,high,"scene position") for v in value]


def _material(value):
    if type(value) is not dict or set(value)!={
        "color","roughness","metallic","emission","kind"
    } or value["kind"] not in MATERIALS:
        raise ValueError("Choose a real material preset")
    return {"color":_check_color(value["color"]),
            "roughness":_number(value["roughness"],.03,1.,"roughness"),
            "metallic":_number(value["metallic"],0.,1.,"metalness"),
            "emission":_number(value["emission"],0.,20.,"light emission"),
            "kind":value["kind"]}


def _light(value):
    if type(value) is not dict or set(value)!={
        "azimuth","elevation","intensity","fill","temperature"
    }:
        raise ValueError("Choose complete scene lighting")
    return {"azimuth":_number(value["azimuth"],-180,180,"sun direction"),
            "elevation":_number(value["elevation"],-5,90,"sun height"),
            "intensity":_number(value["intensity"],0,8,"sun intensity"),
            "fill":_number(value["fill"],0,3,"ambient fill"),
            "temperature":_number(value["temperature"],2000,12000,"light temperature")}


def _fog(value):
    if type(value) is not dict or set(value)!={"density","color"}:
        raise ValueError("Choose a complete atmosphere")
    return {"density":_number(value["density"],0,.3,"fog density"),
            "color":_check_color(value["color"])}


def _item(value):
    if type(value) is not dict or set(value)!={
        "id","name","shape","position","rotation","scale","material","lod"
    } or type(value["id"]) is not str or not _OBJECT.fullmatch(value["id"]):
        raise ValueError("Set piece does not have a valid identity")
    if type(value["name"]) is not str or not 1<=len(value["name"])<=80 or any(
            ord(ch)<32 for ch in value["name"]):
        raise ValueError("Choose a short set-piece name")
    if value["shape"] not in SHAPES or type(value["lod"]) is not int or (
            value["lod"] not in (0,1,2)):
        raise ValueError("Set piece has an unsupported geometry or detail level")
    size=_vec(value["scale"],.03,70)
    return {"id":value["id"],"name":value["name"],"shape":value["shape"],
        "position":_vec(value["position"]),
        "rotation":_vec(value["rotation"],-360,360),
        "scale":size,"material":_material(value["material"]),
        "lod":value["lod"]}


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09_environment_versions(
      project_id TEXT NOT NULL,take_id TEXT NOT NULL,revision INTEGER NOT NULL,
      take_sha256 TEXT NOT NULL,document_json TEXT NOT NULL,
      document_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(project_id,take_id,revision))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09_environment_heads(
      project_id TEXT NOT NULL,take_id TEXT NOT NULL,
      draft_revision INTEGER NOT NULL,approved_revision INTEGER NOT NULL,
      take_sha256 TEXT NOT NULL,updated_at TEXT NOT NULL,
      PRIMARY KEY(project_id,take_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09_environment_kits(
      project_id TEXT NOT NULL,id TEXT NOT NULL,description TEXT NOT NULL,
      take_sha256 TEXT NOT NULL,document_json TEXT NOT NULL,
      document_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(project_id,id))""")


def _preset(name,base_color):
    spec={
      "original":("#718fa8","#5b725b",42,38,1.2,.5,6500,0),
      "interior":("#4e4857","#635b51",55,65,.9,.7,4200,0),
      "city":("#6d7b95","#3d4853",35,40,1.2,.65,5900,0.008),
      "mountains":("#9bb4c7","#696e71",55,25,1.5,.5,6700,.012),
      "coast":("#81b3d4","#c6b38d",20,28,1.5,.7,6700,.008),
      "forest":("#6c9d99","#324d33",80,48,1.1,.5,5600,.028),
      "desert":("#cc9d75","#bd9560",28,45,1.8,.45,5100,.005),
      "farmland":("#9cc2cb","#637951",75,45,1.35,.65,5900,.008),
      "space":("#131728","#202338",15,70,.25,.22,9000,0),
      "open":("#9db7c9","#74837b",48,42,1.35,.62,6400,.005)
    }
    sky,ground,az,el,power,fill,kelvin,fog=spec[name]
    return {"sky":sky,"ground":ground,
        "sun":{"azimuth":float(az),"elevation":float(el),
               "intensity":float(power),"fill":float(fill),
               "temperature":float(kelvin)},
        "atmosphere":{"density":fog,"color":sky}}


def _default(take_id,take_sha,source):
    setting=source.get("stage_setting",{})
    source_style=setting.get("style")
    preset=source_style if source_style in PRESETS else "original"
    base=_preset(preset,"#718fa8")
    return {"format":FORMAT,"kit_source":BUILTIN_VERSION,
       "take_id":take_id,"take_sha256":take_sha,"preset":preset,
       **base,"materials":{},"set_pieces":[],
       "notes":"","external_assets":False}


def _read_version(db,pid,take_id,revision):
    row=db.execute("""SELECT document_json,document_sha256,take_sha256
       FROM g09_environment_versions WHERE project_id=? AND take_id=?
       AND revision=?""",(pid,take_id,revision)).fetchone()
    if row is None:raise KeyError("Previous scene look was not found")
    if _sha(row["document_json"].encode("utf8"))!=row["document_sha256"]:
        raise RuntimeError("An approved scene look was altered")
    doc=json.loads(row["document_json"])
    if doc["take_sha256"]!=row["take_sha256"]:
        raise RuntimeError("Scene look has the wrong original source")
    return doc,row["document_sha256"]


def _take(db,pid,take_id):
    if type(take_id) is not str or not HEX.fullmatch(take_id):
        raise ValueError("Choose a recorded Take")
    row=db.execute("""SELECT take_sha256,performance_json FROM g06_frozen_takes
       WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
    if row is None:raise KeyError("The original Take was not found")
    doc=json.loads(row["performance_json"])
    return row["take_sha256"],doc


def _validate(doc,take_id,take_sha,original):
    if (type(doc) is not dict or set(doc)!={
        "format","kit_source","take_id","take_sha256","preset","sky",
        "ground","sun","atmosphere","materials","set_pieces","notes",
        "external_assets"
    } or doc["format"]!=FORMAT or doc["kit_source"]!=BUILTIN_VERSION or
        doc["take_id"]!=take_id or doc["take_sha256"]!=take_sha or
        doc["preset"] not in PRESETS or doc["external_assets"] is not False):
        raise ValueError("This production look cannot be applied to this original Take")
    _check_color(doc["sky"]);_check_color(doc["ground"])
    _light(doc["sun"]);_fog(doc["atmosphere"])
    if type(doc["notes"]) is not str or len(doc["notes"])>500:
        raise ValueError("Production look notes are too long")
    available={o["id"] for o in original["stage_objects"]}
    if (type(doc["materials"]) is not dict or
        len(doc["materials"])>MAX_OBJECT_MATERIALS or
        any(oid not in available for oid in doc["materials"])):
        raise ValueError("Material is not associated with the filmed scene")
    for obj in doc["materials"].values():_material(obj)
    items=doc["set_pieces"]
    if type(items) is not list or len(items)>MAX_ITEMS:
        raise ValueError("Set decoration is larger than the film's current budget")
    ids=set()
    for value in items:
        item=_item(value)
        if item["id"] in ids or item["id"] in available:
            raise ValueError("Scene contains duplicate set-piece identities")
        ids.add(item["id"])
    if len(_json(doc).encode("utf8"))>90000:
        raise ValueError("This environment style exceeds the scene budget")
    return doc


def _current(db,pid,take_id,take_sha,original):
    head=db.execute("""SELECT * FROM g09_environment_heads
        WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
    if head is None:
        return 0,0,_default(take_id,take_sha,original)
    if head["take_sha256"]!=take_sha:
        raise RuntimeError("A saved style is tied to a different frozen Take")
    draft,approved=head["draft_revision"],head["approved_revision"]
    doc,_=_read_version(db,pid,take_id,draft)
    _validate(doc,take_id,take_sha,original)
    return draft,approved,doc


def _save(db,pid,take_id,take_sha,doc,expected,approved):
    current=db.execute("""SELECT draft_revision FROM g09_environment_heads
        WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
    old=current["draft_revision"] if current else 0
    if old!=expected:
        raise RuntimeError("Another creative revision is newer; reopen the look")
    next_revision=old+1
    if next_revision>3000:raise RuntimeError("Scene look revision limit reached")
    raw=_json(doc);digest=_sha(raw.encode("utf8"))
    db.execute("""INSERT INTO g09_environment_versions
        (project_id,take_id,revision,take_sha256,document_json,
         document_sha256,created_at) VALUES (?,?,?,?,?,?,?)""",
        (pid,take_id,next_revision,take_sha,raw,digest,_now()))
    db.execute("""INSERT INTO g09_environment_heads
        (project_id,take_id,draft_revision,approved_revision,take_sha256,updated_at)
        VALUES (?,?,?,?,?,?) ON CONFLICT(project_id,take_id) DO UPDATE SET
        draft_revision=excluded.draft_revision,updated_at=excluded.updated_at""",
        (pid,take_id,next_revision,approved,take_sha,_now()))
    return next_revision


def _public(db,pid,take_id,take_sha,original):
    rev,approved,doc=_current(db,pid,take_id,take_sha,original)
    names={o["id"]:o["name"] for o in original["stage_objects"]
           if o["role"] not in ("camera","light")}
    kits=[{"id":row["id"],"description":row["description"]}
          for row in db.execute("""SELECT id,description FROM g09_environment_kits
            WHERE project_id=? ORDER BY created_at DESC LIMIT ?""",(pid,MAX_KITS))]
    return {"format":FORMAT,"take_id":take_id,"take_sha256":take_sha,
        "revision":rev,"approved_revision":approved,
        "ready_for_export":approved>0,
        "draft":doc,"filmed_objects":[{"id":k,"name":v}
                              for k,v in names.items()],
        "kits":kits,"presets":list(PRESETS),
        "source_unchanged":True}


class G09Environment:
    def __init__(self,studio,live=None,token=None):
        self.editor=G07Editor(studio,live,token)

    def _execute(self,pid,fn,mutate=False):
        def execute(db,movie):
            _schema(db)
            return fn(db,movie)
        return self.editor._execute(pid,execute,mutate=mutate)

    def view(self,pid,take_id):
        def read(db,movie):
            take_sha,source=_take(db,pid,take_id)
            return _public(db,pid,take_id,take_sha,source)
        return self._execute(pid,read)

    def edit(self,pid,take_id,expected_revision,operation,details):
        if (type(expected_revision) is not int or expected_revision<0 or
                type(operation) is not str or type(details) is not dict):
            raise ValueError("Choose an existing scene look to edit")
        def edit_tx(db,movie):
            take_sha,source=_take(db,pid,take_id)
            rev,approved,doc=_current(db,pid,take_id,take_sha,source)
            if rev!=expected_revision:
                raise RuntimeError("This scene look was updated elsewhere")
            doc=copy.deepcopy(doc)
            if operation=="preset":
                if set(details)!={"preset"} or details["preset"] not in PRESETS:
                    raise ValueError("Choose a production environment")
                name=details["preset"];previous=doc["set_pieces"]
                doc.update(_preset(name,"#718fa8"))
                doc["preset"]=name
                # Existing authored decoration remains in place; a preset
                # only changes the environment/weather/lighting, not props.
                doc["set_pieces"]=previous
            elif operation=="light":
                if set(details)!={"sun","atmosphere","sky","ground"}:
                    raise ValueError("Adjust the complete scene lighting")
                doc["sun"]=_light(details["sun"])
                doc["atmosphere"]=_fog(details["atmosphere"])
                doc["sky"]=_check_color(details["sky"])
                doc["ground"]=_check_color(details["ground"])
            elif operation=="material":
                if set(details)!={"object_id","material"}:
                    raise ValueError("Choose a filmed object and its surface")
                available={x["id"] for x in source["stage_objects"]
                           if x["role"] not in ("camera","light")}
                if details["object_id"] not in available:
                    raise ValueError("This object is not in the filmed scene")
                doc["materials"][details["object_id"]]=_material(details["material"])
            elif operation=="add_piece":
                if set(details)!={"name","shape","position","rotation",
                                   "scale","material","lod"}:
                    raise ValueError("Describe one physical set piece")
                if len(doc["set_pieces"])>=MAX_ITEMS:
                    raise ValueError("This set already contains enough decoration")
                item=_item({"id":"O_"+uuid.uuid4().hex[:12],**details})
                doc["set_pieces"].append(item)
            elif operation=="update_piece":
                if set(details)!={"item"}:
                    raise ValueError("Choose one set piece to move or reshape")
                item=_item(details["item"])
                index=next((i for i,x in enumerate(doc["set_pieces"])
                            if x["id"]==item["id"]),None)
                if index is None:raise KeyError("This set piece was removed")
                doc["set_pieces"][index]=item
            elif operation=="remove_piece":
                if set(details)!={"item_id"}:
                    raise ValueError("Choose the set piece to remove")
                before=len(doc["set_pieces"])
                doc["set_pieces"]=[x for x in doc["set_pieces"]
                                   if x["id"]!=details["item_id"]]
                if len(doc["set_pieces"])==before:
                    raise KeyError("This piece is not in the set")
            elif operation=="notes":
                if set(details)!={"notes"} or type(details["notes"]) is not str:
                    raise ValueError("Write a short director's look note")
                doc["notes"]=details["notes"]
            elif operation=="apply_kit":
                if set(details)!={"kit_id"} or type(details["kit_id"]) is not str or (
                        not _KIT_ID.fullmatch(details["kit_id"])):
                    raise ValueError("Choose a saved production set")
                row=db.execute("""SELECT document_json,document_sha256
                    FROM g09_environment_kits WHERE project_id=? AND id=?""",
                    (pid,details["kit_id"])).fetchone()
                if row is None:raise KeyError("That saved set is unavailable")
                if _sha(row["document_json"].encode("utf8"))!=row["document_sha256"]:
                    raise RuntimeError("Saved set was altered")
                template=json.loads(row["document_json"])
                doc.update({key:copy.deepcopy(template[key])
                    for key in ("preset","sky","ground","sun","atmosphere","notes")})
                doc["materials"]={}
                # A saved kit's decoration is cloned with fresh stable IDs:
                # no cross-Take object identity can be falsely reused.
                doc["set_pieces"]=[{**x,"id":"O_"+uuid.uuid4().hex[:12]}
                                   for x in template["set_pieces"]]
            else:
                raise ValueError("The requested environment change is not available")
            _validate(doc,take_id,take_sha,source)
            _save(db,pid,take_id,take_sha,doc,expected_revision,approved)
            return _public(db,pid,take_id,take_sha,source)
        return self._execute(pid,edit_tx,mutate=True)

    def approve(self,pid,take_id,expected_revision):
        def authorize(db,movie):
            take_sha,source=_take(db,pid,take_id)
            rev,approved,doc=_current(db,pid,take_id,take_sha,source)
            if type(expected_revision) is not int or rev!=expected_revision:
                raise RuntimeError("The director must review the current scene look")
            if rev<1:raise ValueError("Choose an environment look first")
            _validate(doc,take_id,take_sha,source)
            db.execute("""UPDATE g09_environment_heads
                SET approved_revision=?,updated_at=? WHERE
                project_id=? AND take_id=?""",(rev,_now(),pid,take_id))
            return _public(db,pid,take_id,take_sha,source)
        return self._execute(pid,authorize,mutate=True)

    def save_kit(self,pid,take_id,description,expected_revision):
        if type(description) is not str or not 1<=len(description.strip())<=80:
            raise ValueError("Name your reusable environment")
        def save(db,movie):
            take_sha,source=_take(db,pid,take_id)
            rev,approved,doc=_current(db,pid,take_id,take_sha,source)
            if rev!=expected_revision or approved!=rev:
                raise RuntimeError("Approve this set before saving a reusable kit")
            if db.execute("""SELECT count(*) AS n FROM g09_environment_kits
                WHERE project_id=?""",(pid,)).fetchone()["n"]>=MAX_KITS:
                raise RuntimeError("This film already has enough saved sets")
            kit_id="K_"+uuid.uuid4().hex[:24]
            kit={key:copy.deepcopy(doc[key])
                 for key in ("preset","sky","ground","sun","atmosphere",
                             "notes","set_pieces")}
            raw=_json(kit)
            db.execute("""INSERT INTO g09_environment_kits
               (project_id,id,description,take_sha256,document_json,
                document_sha256,created_at)
               VALUES (?,?,?,?,?,?,?)""",
               (pid,kit_id,description.strip(),take_sha,raw,
                _sha(raw.encode("utf8")),_now()))
            return _public(db,pid,take_id,take_sha,source)
        return self._execute(pid,save,mutate=True)

    @staticmethod
    def approved_source(db,pid,take_id,take_sha,original):
        """Source-of-truth export overlay, a verified immutable approved version."""
        _schema(db)
        head=db.execute("""SELECT approved_revision,take_sha256
             FROM g09_environment_heads WHERE project_id=? AND take_id=?""",
             (pid,take_id)).fetchone()
        if not head or not head["approved_revision"]:
            return None
        if head["take_sha256"]!=take_sha:
            raise RuntimeError("Approved environment belongs to a different Take")
        doc,digest=_read_version(db,pid,take_id,head["approved_revision"])
        _validate(doc,take_id,take_sha,original)
        return {"revision":head["approved_revision"],"sha256":digest,
                "look":doc}
