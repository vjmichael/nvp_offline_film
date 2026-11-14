"""G09-C native spatial sound: immutable derived acoustic decisions per G06 Take.

One Director-approved acoustic revision is pinned to an original Take SHA.
The film's editable G07 sound mix is authoritative; this module only refines
how each authentic PCM source sounds in the actual 3D film environment.

A sound event synthesized from film weather is always DERIVED and separately
enabled by the director. It is never represented as a microphone capture.
No unreviewed file, impulse response, plugin, executable or URL is accepted.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import uuid
from datetime import datetime,timezone
from backend.nvp_g07_edit import G07Editor,_json,_sha
from backend.nvp_g06_filming import HEX

FORMAT="nvp.g09c.acoustics.v1"
PROFILES=("original","interior","hall","outdoor","forest","city","cavern","space")
MAX_VERSION=2000
MAX_SOUNDS=32
MAX_SOURCE_DISTANCE=200
ROOMS={
 "original":(.06,.14,15.,0.),
 "interior":(.30,.23,9.,.22),
 "hall":(.54,.48,27.,.32),
 "outdoor":(.04,.12,80.,.05),
 "forest":(.10,.23,40.,.22),
 "city":(.15,.33,34.,.24),
 "cavern":(.68,.65,52.,.45),
 "space":(0.,0.,100.,0.)
}

def _now():return datetime.now(timezone.utc).isoformat()

def _num(v,lo,hi,label):
    if type(v) not in (float,int) or type(v) is bool or not math.isfinite(v) or not lo<=v<=hi:
        raise ValueError("Choose a valid "+label)
    return float(v)

def _base(take_id,take_sha,source):
    scene=source.get("stage_setting",{})
    style=str(scene.get("style","")).lower()
    profile=style if style in PROFILES else "original"
    p=ROOMS[profile]
    return {"format":FORMAT,"take_id":take_id,"take_sha256":take_sha,
        "profile":profile,"reverb":p[0],"reflections":p[1],
        "room_size":p[2],"obstruction":p[3],
        "distance_rolloff":1.,"air_absorption":.4,"stereo_width":1.,
        "weather_sounds":False,"weather_level":.13,
        "notes":"","preserve_original_pcm":True}

def _validate(doc,take_id,take_sha,source):
    if (type(doc) is not dict or set(doc)!={"format","take_id","take_sha256",
         "profile","reverb","reflections","room_size","obstruction",
         "distance_rolloff","air_absorption","stereo_width","weather_sounds",
         "weather_level","notes","preserve_original_pcm"} or
         doc["format"]!=FORMAT or doc["take_id"]!=take_id or
         doc["take_sha256"]!=take_sha or
         type(doc["profile"]) is not str or doc["profile"] not in PROFILES or
         doc["preserve_original_pcm"] is not True or
         type(doc["weather_sounds"]) is not bool or
         type(doc["notes"]) is not str or len(doc["notes"])>500):
        raise ValueError("The room sound belongs to another original recording")
    for key,a,b in (
        ("reverb",0.,.85),("reflections",0.,.85),
        ("room_size",3.,100.),("obstruction",0.,1.),
        ("distance_rolloff",0.,2.5),("air_absorption",0.,1.),
        ("stereo_width",0.,1.5),("weather_level",0.,.4)):
        _num(doc[key],a,b,key.replace("_"," "))
    if len(_json(doc).encode("utf8"))>4000:
        raise ValueError("The acoustic look is too large")
    return doc

def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09c_acoustic_versions(
      project_id TEXT NOT NULL,take_id TEXT NOT NULL,revision INTEGER NOT NULL,
      take_sha256 TEXT NOT NULL,document_json TEXT NOT NULL,
      document_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(project_id,take_id,revision))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09c_acoustic_heads(
      project_id TEXT NOT NULL,take_id TEXT NOT NULL,
      draft_revision INTEGER NOT NULL,approved_revision INTEGER NOT NULL,
      take_sha256 TEXT NOT NULL,updated_at TEXT NOT NULL,
      PRIMARY KEY(project_id,take_id))""")

def _get(db,pid,take_id,revision):
    row=db.execute("""SELECT document_json,document_sha256,take_sha256
      FROM g09c_acoustic_versions WHERE project_id=? AND take_id=?
      AND revision=?""",(pid,take_id,revision)).fetchone()
    if not row or _sha(row["document_json"].encode("utf8"))!=row["document_sha256"]:
        raise RuntimeError("Previous room sound history was not preserved")
    result=json.loads(row["document_json"])
    if result["take_sha256"]!=row["take_sha256"]:
        raise RuntimeError("Room sound no longer matches its original Take")
    return result,row["document_sha256"]

def _current(db,pid,take_id,take_sha,source):
    row=db.execute("""SELECT draft_revision,approved_revision,take_sha256
      FROM g09c_acoustic_heads WHERE project_id=? AND take_id=?""",
      (pid,take_id)).fetchone()
    if row is None:return 0,0,_base(take_id,take_sha,source)
    if row["take_sha256"]!=take_sha:
        raise RuntimeError("A different film source has replaced this sound")
    doc,_=_get(db,pid,take_id,row["draft_revision"])
    return row["draft_revision"],row["approved_revision"],_validate(
        doc,take_id,take_sha,source)

def _public(db,pid,take_id,take_sha,source):
    rev,approved,doc=_current(db,pid,take_id,take_sha,source)
    history=[{"revision":r["revision"],"created_at":r["created_at"]}
        for r in db.execute("""SELECT revision,created_at
            FROM g09c_acoustic_versions WHERE project_id=? AND take_id=?
            ORDER BY revision DESC LIMIT 25""",(pid,take_id))]
    return {"format":FORMAT,"take_id":take_id,
        "revision":rev,"approved_revision":approved,
        "draft":doc,"history":history,"profiles":list(PROFILES),
        "recorded_sound_preserved":True,
        "weather_sound_is_derived":doc["weather_sounds"],
        "native_spatial_engine":"source_based_stereo"}

class G09CAcoustics:
    def __init__(self,studio,live=None,token=None):
        self.editor=G07Editor(studio,live,token)
    def _execute(self,pid,fn,mutate=False):
        def work(db,movie):
            _schema(db)
            return fn(db,movie)
        return self.editor._execute(pid,work,mutate=mutate)
    def view(self,pid,take_id):
        def read(db,movie):
            row,doc,audio=self.editor._take(db,pid,take_id,{})
            return _public(db,pid,take_id,row["take_sha256"],doc)
        return self._execute(pid,read)
    def change(self,pid,take_id,expected,operation,details):
        if type(expected) is not int or expected<0 or type(details) is not dict:
            raise ValueError("Choose the current sound version")
        def update(db,movie):
            row,src,audio=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],src)
            if rev!=expected:raise RuntimeError("The room sound changed; reopen it")
            doc=copy.deepcopy(doc)
            if operation=="preset":
                if (set(details)!={"profile"} or
                    type(details["profile"]) is not str or
                    details["profile"] not in PROFILES):
                    raise ValueError("Choose one familiar sound environment")
                profile=details["profile"];p=ROOMS[profile]
                doc.update({"profile":profile,"reverb":p[0],
                    "reflections":p[1],"room_size":p[2],
                    "obstruction":p[3]})
            elif operation=="mix":
                keys={"reverb","reflections","room_size","obstruction",
                      "distance_rolloff","air_absorption","stereo_width",
                      "weather_sounds","weather_level","notes"}
                if set(details)!=keys:
                    raise ValueError("Review a complete sound environment")
                doc.update(details)
            else:raise ValueError("That room sound adjustment is not available")
            _validate(doc,take_id,row["take_sha256"],src)
            nextrev=rev+1
            if nextrev>MAX_VERSION:raise RuntimeError("Sound versions reached their limit")
            raw=_json(doc);digest=_sha(raw.encode("utf8"))
            db.execute("""INSERT INTO g09c_acoustic_versions(
                project_id,take_id,revision,take_sha256,document_json,
                document_sha256,created_at) VALUES(?,?,?,?,?,?,?)""",
                (pid,take_id,nextrev,row["take_sha256"],raw,digest,_now()))
            db.execute("""INSERT INTO g09c_acoustic_heads(
                project_id,take_id,draft_revision,approved_revision,
                take_sha256,updated_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(project_id,take_id) DO UPDATE SET
                draft_revision=excluded.draft_revision,
                updated_at=excluded.updated_at""",
                (pid,take_id,nextrev,approved,row["take_sha256"],_now()))
            return _public(db,pid,take_id,row["take_sha256"],src)
        return self._execute(pid,update,mutate=True)
    def approve(self,pid,take_id,expected):
        if type(expected) is not int or expected<1:
            raise ValueError("Adjust and review the room sound first")
        def accept(db,movie):
            row,src,audio=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],src)
            if rev!=expected:raise RuntimeError("The sound changed since you reviewed it")
            _validate(doc,take_id,row["take_sha256"],src)
            db.execute("""UPDATE g09c_acoustic_heads
                SET approved_revision=?,updated_at=? WHERE
                project_id=? AND take_id=?""",(rev,_now(),pid,take_id))
            return _public(db,pid,take_id,row["take_sha256"],src)
        return self._execute(pid,accept,mutate=True)
    def restore(self,pid,take_id,source_revision,expected):
        if type(expected) is not int or expected<0 or (
                type(source_revision) is not int or source_revision<1):
            raise ValueError("Choose an earlier sound version")
        def rollback(db,movie):
            row,src,audio=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],src)
            if rev!=expected:raise RuntimeError("Room sound changed since you reviewed it")
            chosen,_=_get(db,pid,take_id,source_revision)
            _validate(chosen,take_id,row["take_sha256"],src)
            nextrev=rev+1
            if nextrev>MAX_VERSION:raise RuntimeError("Too many sound revisions")
            raw=_json(chosen)
            db.execute("""INSERT INTO g09c_acoustic_versions(
                project_id,take_id,revision,take_sha256,document_json,
                document_sha256,created_at) VALUES(?,?,?,?,?,?,?)""",
                (pid,take_id,nextrev,row["take_sha256"],raw,_sha(raw.encode("utf8")),_now()))
            db.execute("""UPDATE g09c_acoustic_heads SET
                draft_revision=?,updated_at=? WHERE project_id=? AND take_id=?""",
                (nextrev,_now(),pid,take_id))
            return _public(db,pid,take_id,row["take_sha256"],src)
        return self._execute(pid,rollback,mutate=True)
    @staticmethod
    def approved_source(db,pid,take_id,take_sha,source):
        _schema(db)
        row=db.execute("""SELECT approved_revision,take_sha256
            FROM g09c_acoustic_heads WHERE project_id=? AND take_id=?""",
            (pid,take_id)).fetchone()
        if not row or not row["approved_revision"]:return None
        if row["take_sha256"]!=take_sha:
            raise RuntimeError("Approved sound is bound to a different recording")
        doc,sha=_get(db,pid,take_id,row["approved_revision"])
        _validate(doc,take_id,take_sha,source)
        return {"revision":row["approved_revision"],"sha256":sha,"acoustics":doc}
