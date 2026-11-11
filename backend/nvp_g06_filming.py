"""G06 — actual director-led performance source and immutable Digital Takes.

G05's approved OpenUSD stage is the only scene source. Animated actor/prop
transforms and typed ambient events are authored at exact Film Time on a fresh
OpenUSD copy; source USD is never modified. Recorded native PCM bytes are
immutable project-scoped originals. Camera plans are independent of frozen
performances, so G07 can reframe without modifying a Take.

Both ordinary and encrypted projects use the SAME existing G04/G05 SQLite
host writer (encrypted storage stays in the DPAPI/AES-GCM sealed movie DB).
No model, WebView or API may invent microphone bytes, grant Take authority,
write arbitrary USD, choose filesystem paths or execute a rendering worker.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation

from backend.nvp_g05_scene_authoring import G05SceneAuthoring,_reopen_usd
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.g06.film.performance.v1"
TAKE_FORMAT="nvp.g06.immutable_openusd_take.v1"
MAX_SECONDS=1800
MAX_EVENTS=512
MAX_TAKES_PER_SCENE=128
MAX_NATIVE_PCM_SECONDS=120
RATE=48000
SAMPLE_TICKS=TICKS_PER_SECOND//RATE
ACTOR_ACTIONS=frozenset(("walk","run","jog","crawl","gesture","look","expression","dialogue"))
PROP_ACTIONS=frozenset(("prop_move","prop_turn","prop_action"))
AMBIENT_ACTIONS=frozenset(("wind","fog","rain","snow","light","ambient_action"))
ALL_ACTIONS=ACTOR_ACTIONS|PROP_ACTIONS|AMBIENT_ACTIONS
MOVING=frozenset(("walk","run","jog","crawl","prop_move"))
HEX=re.compile(r"[a-f0-9]{32}\Z")
OID=re.compile(r"O_[a-f0-9]{12}\Z")
MAX_FILM_USD=6_000_000


def _json(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,
                      separators=(",",":"),allow_nan=False)


def _sha(v):
    return hashlib.sha256(v).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _seconds(value):
    if type(value) not in (str,int,float) or isinstance(value,bool):
        raise ValueError("Choose a time within the scene")
    try: d=Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Choose a valid scene time") from exc
    if not d.is_finite() or not Decimal(0)<=d<=Decimal(MAX_SECONDS):
        raise ValueError("Time is outside this scene")
    ticks=d*Decimal(TICKS_PER_SECOND)
    if ticks!=ticks.to_integral_value():
        raise ValueError("Scene time must be exact to the film clock")
    return int(ticks)


def _time(ticks):
    return str(Decimal(ticks)/Decimal(TICKS_PER_SECOND))


def _vec(v):
    if (type(v) is not list or len(v)!=3 or
            any(type(x) not in (float,int) or not math.isfinite(x)
                or abs(x)>150 for x in v)):
        raise ValueError("Choose a position inside the stage")
    return [float(x) for x in v]


def _short(text,maximum=500):
    if type(text) is not str or len(text)>maximum:
        raise ValueError("Creative note is too long")
    return text.strip()


def _stage(db,source,pid,scene_id):
    head,record=G05SceneAuthoring._record(db,pid,scene_id)
    if (head is None or head["status"]!="approved" or
            head["source_sha256"]!=source["scene_source_sha256"]):
        raise RuntimeError("Approve the current visual scene before filming")
    raw=bytes(record["usd_layer"])
    if _sha(raw)!=record["usd_sha256"]:
        raise RuntimeError("Approved scene original was changed")
    plan=json.loads(record["plan_json"])
    _reopen_usd(raw,plan)
    return head,record,plan,raw


def _event_validate(event,objects,duration):
    if (type(event) is not dict or
        set(event)!={"id","kind","object_id","actor_id","start_tick",
                     "end_tick","target_position","intensity","note","status"} or
        not isinstance(event["id"],str) or not HEX.fullmatch(event["id"]) or
        event["kind"] not in ALL_ACTIONS or
        type(event["start_tick"]) is not int or
        type(event["end_tick"]) is not int or
        not 0<=event["start_tick"]<event["end_tick"]<=duration or
        event["status"]!="director_authored"):
        raise ValueError("Invalid event or scene time")
    if type(event["note"]) is not str or len(event["note"])>1000:
        raise ValueError("Performance note is invalid")
    kind=event["kind"]
    if kind in ACTOR_ACTIONS:
        obj=objects.get(event["object_id"])
        if obj is None or obj["role"]!="actor" or not obj["actor_id"] or (
                obj["actor_id"]!=event["actor_id"]):
            raise ValueError("Performance is not bound to the correct character")
    elif kind in PROP_ACTIONS:
        obj=objects.get(event["object_id"])
        if obj is None or obj["role"] not in ("prop","set","environment") or (
                event["actor_id"] is not None):
            raise ValueError("Choose an actual stage object")
    else:
        if event["actor_id"] is not None or event["object_id"] is not None:
            raise ValueError("Ambient events belong to the film environment")
    if kind in MOVING:
        _vec(event["target_position"])
    elif event["target_position"] is not None:
        raise ValueError("Only a movement action has a destination")
    intensity=event["intensity"]
    if intensity is not None and (
            type(intensity) not in (float,int) or
            not math.isfinite(intensity) or not 0<=intensity<=10):
        raise ValueError("Environmental strength must be reasonable")
    if kind in AMBIENT_ACTIONS and intensity is None:
        raise ValueError("Choose the environmental event strength")
    if kind not in AMBIENT_ACTIONS and intensity is not None:
        raise ValueError("Actor performance cannot contain an ambient intensity")


def _author_performance(original,stage_plan,working):
    """Author exact native OpenUSD time samples on an independent film layer."""
    from pxr import Sdf,Usd,UsdGeom,Gf,UsdLux
    copy=Sdf.Layer.CreateAnonymous("nvp-g06-original-performance.usda")
    if not copy.ImportFromString(original.decode("utf8")):
        raise RuntimeError("Could not open the approved film world")
    if copy.subLayerPaths or copy.GetExternalReferences():
        raise RuntimeError("Film world contains unresolved external assets")
    stage=Usd.Stage.Open(copy,Usd.Stage.LoadNone)
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    stage.SetStartTimeCode(0)
    duration=working["duration_tick"]
    stage.SetEndTimeCode(float(duration))
    root=stage.GetPrimAtPath("/World")
    if not root:
        raise RuntimeError("Film world has no authoritative root")
    objects={x["id"]:x for x in stage_plan["objects"]}
    events=sorted(working["events"],key=lambda v:(v["start_tick"],v["id"]))
    movement_ends={}
    for event in events:
        _event_validate(event,objects,duration)
        kind=event["kind"]
        t0=Usd.TimeCode(float(event["start_tick"]))
        t1=Usd.TimeCode(float(event["end_tick"]))
        if kind in MOVING:
            oid=event["object_id"]
            prim=stage.GetPrimAtPath("/World/Objects/"+oid)
            if not prim:
                raise RuntimeError("Film performer or prop is missing")
            if movement_ends.get(oid,-1)>event["start_tick"]:
                raise ValueError("Overlapping movement needs director review")
            movement_ends[oid]=event["end_tick"]
            initial=objects[oid]["position"]
            # Previous movement's ending position becomes the next beginning.
            prev=[e for e in events if e["kind"] in MOVING and
                  e["object_id"]==oid and
                  e["end_tick"]<=event["start_tick"]]
            if prev:
                initial=max(prev,key=lambda e:e["end_tick"])["target_position"]
            trans=UsdGeom.XformCommonAPI(UsdGeom.Xform(prim))
            if not trans.SetTranslate(Gf.Vec3d(*initial),t0):
                raise RuntimeError("Could not author a movement start")
            if not trans.SetTranslate(Gf.Vec3d(*event["target_position"]),t1):
                raise RuntimeError("Could not author a movement end")
        elif kind=="light":
            world=root.CreateAttribute(
                "nvp:environment:light",Sdf.ValueTypeNames.Double)
            world.Set(float(event["intensity"]),t0)
            world.Set(1.0,t1)
            # The existing authored key light remains a separate editable
            # source; this time-varying parameter is Film Time data.
        elif kind in AMBIENT_ACTIONS:
            field=root.CreateAttribute(
                "nvp:environment:"+kind,Sdf.ValueTypeNames.Double)
            field.Set(float(event["intensity"]),t0)
            field.Set(0.0,t1)
        elif kind in ACTOR_ACTIONS|PROP_ACTIONS:
            target=stage.GetPrimAtPath("/World/Objects/"+event["object_id"])
            if not target:raise RuntimeError("Performance target is absent")
            # Author held semantic state for expression/dialogue/action;
            # rigging, voice production and lip sync are later G09 work.
            attr=target.CreateAttribute("nvp:performance:"+kind,
                                        Sdf.ValueTypeNames.String)
            attr.Set(event["note"] or kind,t0)
            attr.Set("",t1)
    origin=root.CreateAttribute(
        "nvp:frozenSourceSceneSha256",Sdf.ValueTypeNames.String)
    origin.Set(_sha(original))
    layer=copy.ExportToString().encode("utf8")
    if len(layer)>MAX_FILM_USD:
        raise ValueError("The recorded film performance exceeds scene limits")
    reopened=Sdf.Layer.CreateAnonymous("nvp-g06-independent-reopen.usda")
    if not reopened.ImportFromString(layer.decode("utf8")):
        raise RuntimeError("Recorded film performance did not reopen")
    recreated=Usd.Stage.Open(reopened,Usd.Stage.LoadNone)
    if (not recreated or recreated.GetPrimAtPath("/World").GetAttribute(
            "nvp:frozenSourceSceneSha256").Get()!=_sha(original)):
        raise RuntimeError("Recorded film lost its original scene binding")
    for event in events:
        if event["kind"] in MOVING:
            prim=recreated.GetPrimAtPath("/World/Objects/"+event["object_id"])
            xyz=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                Usd.TimeCode(float(event["end_tick"]))).ExtractTranslation()
            if any(abs(float(xyz[i])-event["target_position"][i])>1e-3
                   for i in range(3)):
                raise RuntimeError("Recorded 3D movement did not survive reopening")
    return layer


class G06Filming:
    def __init__(self,studio,live=None,token=None):
        self.g05=G05SceneAuthoring(studio,live,token)

    @staticmethod
    def _schema(db):
        db.execute("""CREATE TABLE IF NOT EXISTS g06_working(
            project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
            revision INTEGER NOT NULL,scene_stage_revision INTEGER NOT NULL,
            stage_sha256 TEXT NOT NULL,duration_tick TEXT NOT NULL,
            events_json TEXT NOT NULL,updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id,scene_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS g06_work_history(
            project_id TEXT NOT NULL,scene_id TEXT NOT NULL,
            revision INTEGER NOT NULL,snapshot_json TEXT NOT NULL,
            saved_at TEXT NOT NULL,
            PRIMARY KEY(project_id,scene_id,revision))""")
        db.execute("""CREATE TABLE IF NOT EXISTS g06_original_pcm(
            id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
            scene_id TEXT NOT NULL,actor_id TEXT,source_kind TEXT NOT NULL,
            pcm BLOB NOT NULL,pcm_sha256 TEXT NOT NULL,
            sample_rate INTEGER NOT NULL,channels INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,recorded_at TEXT NOT NULL,
            CHECK(source_kind='native_microphone_pcm16le'))""")
        db.execute("""CREATE TABLE IF NOT EXISTS g06_frozen_takes(
            take_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
            scene_id TEXT NOT NULL,source_stage_revision INTEGER NOT NULL,
            source_sha256 TEXT NOT NULL,original_usd_sha256 TEXT NOT NULL,
            original_usd BLOB NOT NULL,performance_usd_sha256 TEXT NOT NULL,
            performance_usd BLOB NOT NULL,performance_json TEXT NOT NULL,
            audio_json TEXT NOT NULL,take_sha256 TEXT NOT NULL,
            frozen_at TEXT NOT NULL)""")
        db.execute("""CREATE INDEX IF NOT EXISTS g06_takes_by_scene
            ON g06_frozen_takes(project_id,scene_id,frozen_at)""")
        db.execute("""CREATE TABLE IF NOT EXISTS g06_camera_views(
            project_id TEXT NOT NULL,take_id TEXT NOT NULL,
            revision INTEGER NOT NULL,views_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id,take_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS g06_camera_view_history(
            project_id TEXT NOT NULL,take_id TEXT NOT NULL,
            revision INTEGER NOT NULL,views_json TEXT NOT NULL,
            saved_at TEXT NOT NULL,
            PRIMARY KEY(project_id,take_id,revision))""")
        db.execute("""CREATE TABLE IF NOT EXISTS g06_refused_attempts(
            id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
            scene_id TEXT NOT NULL,revision INTEGER NOT NULL,
            reason TEXT NOT NULL,created_at TEXT NOT NULL)""")

    def _with(self,pid,scene_id,callback,mutate=False):
        def operation(db,movie,source):
            self._schema(db)
            return callback(db,movie,source)
        return self.g05._with(pid,scene_id,operation,mutate=mutate)

    @staticmethod
    def _working(db,pid,scene_id,stage):
        row=db.execute("""SELECT * FROM g06_working WHERE
            project_id=? AND scene_id=?""",(pid,scene_id)).fetchone()
        if row is None:
            return {"revision":0,"scene_stage_revision":stage["revision"],
                "stage_sha256":stage["usd_sha256"],"duration_tick":
                    30*TICKS_PER_SECOND,"events":[]}
        result=dict(row)
        result["duration_tick"]=int(result["duration_tick"])
        result["events"]=json.loads(result["events_json"])
        return result

    @staticmethod
    def _save(db,pid,scene_id,work,expected):
        prior=db.execute("""SELECT revision FROM g06_working
            WHERE project_id=? AND scene_id=?""",(pid,scene_id)).fetchone()
        found=prior["revision"] if prior else 0
        if expected!=found:
            raise RuntimeError("Film performance was updated elsewhere")
        new=found+1
        db.execute("""INSERT INTO g06_work_history
            (project_id,scene_id,revision,snapshot_json,saved_at)
            VALUES (?,?,?,?,?)""",(pid,scene_id,new,_json(work),_now()))
        db.execute("""INSERT INTO g06_working
            (project_id,scene_id,revision,scene_stage_revision,
             stage_sha256,duration_tick,events_json,updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id,scene_id) DO UPDATE SET
              revision=excluded.revision,
              scene_stage_revision=excluded.scene_stage_revision,
              stage_sha256=excluded.stage_sha256,
              duration_tick=excluded.duration_tick,
              events_json=excluded.events_json,
              updated_at=excluded.updated_at""",
            (pid,scene_id,new,work["scene_stage_revision"],
             work["stage_sha256"],str(work["duration_tick"]),
             _json(work["events"]),_now()))
        return new

    @staticmethod
    def _manifest(db,pid,scene_id,source,head,stage_plan):
        work=G06Filming._working(db,pid,scene_id,head)
        current=(work["scene_stage_revision"]==head["revision"] and
                 work["stage_sha256"]==head["usd_sha256"])
        clips=[{"id":r["id"],"actor_id":r["actor_id"],
                "sample_count":r["sample_count"],"seconds":round(
                    r["sample_count"]/RATE,3),"recorded_at":r["recorded_at"]}
                for r in db.execute("""SELECT id,actor_id,sample_count,
                    recorded_at FROM g06_original_pcm WHERE
                    project_id=? AND scene_id=?
                    ORDER BY recorded_at DESC LIMIT 30""",(pid,scene_id))]
        takes=[{"id":r["take_id"],"digest":r["take_sha256"],
                "created_at":r["frozen_at"]}
                for r in db.execute("""SELECT take_id,take_sha256,frozen_at
                    FROM g06_frozen_takes WHERE project_id=? AND scene_id=?
                    ORDER BY frozen_at DESC LIMIT 60""",(pid,scene_id))]
        history=[{"revision":r["revision"],"saved_at":r["saved_at"]}
                 for r in db.execute("""SELECT revision,saved_at
                    FROM g06_work_history WHERE project_id=? AND scene_id=?
                    ORDER BY revision DESC LIMIT 30""",(pid,scene_id))]
        return {"format":FORMAT,"project_id":pid,"scene_id":scene_id,
                "scene_name":source["scene_name"],
                "stage_revision":head["revision"],
                "stage_sha256":head["usd_sha256"],
                "stage_objects":[{"id":o["id"],"name":o["name"],
                    "role":o["role"],"actor_id":o["actor_id"],
                    "position":o["position"],"scale":o["scale"],
                    "shape":o["shape"],"color":o["color"]}
                    for o in stage_plan["objects"]],
                "work_revision":work["revision"],
                "work_current":current,
                "duration_seconds":float(_time(work["duration_tick"])),
                "events":[{**e,"start_seconds":float(_time(e["start_tick"])),
                           "end_seconds":float(_time(e["end_tick"]))}
                          for e in work["events"]],
                "audio_clips":clips,"takes":takes,
                "history":history,
                "camera_suggestions":["Wide","Medium","Close-up"],
                "recording_is_a_director_action":True,
                "frozen_take_present":bool(takes)}

    def view(self,pid,scene_id):
        def reader(db,movie,source):
            head,record,plan,raw=_stage(db,source,pid,scene_id)
            return self._manifest(db,pid,scene_id,source,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]},plan)
        return self._with(pid,scene_id,reader)

    def set_duration(self,pid,scene_id,seconds,expected_revision):
        duration=_seconds(seconds)
        if duration<5*TICKS_PER_SECOND:
            raise ValueError("A filmed scene needs at least five seconds")
        def change(db,movie,source):
            head,record,plan,raw=_stage(db,source,pid,scene_id)
            working=self._working(db,pid,scene_id,record|{"revision":head["revision"]})
            self._current(working,head,record)
            if any(e["end_tick"]>duration for e in working["events"]):
                raise ValueError("The scene still has performances beyond that duration")
            working["duration_tick"]=duration
            self._save(db,pid,scene_id,working,expected_revision)
            return self._manifest(db,pid,scene_id,source,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]},plan)
        return self._with(pid,scene_id,change,mutate=True)

    @staticmethod
    def _current(working,head,record):
        if (working["scene_stage_revision"]!=head["revision"] or
                working["stage_sha256"]!=record["usd_sha256"]):
            raise RuntimeError("The approved stage changed; start a new performance draft")

    def add_event(self,pid,scene_id,*,expected_revision,kind,object_id,
                  start_seconds,end_seconds,target_position=None,
                  intensity=None,note=""):
        if kind not in ALL_ACTIONS:
            raise ValueError("Choose a supported performance or scene event")
        start,end=_seconds(start_seconds),_seconds(end_seconds)
        note=_short(note,1000)
        def change(db,movie,source):
            head,record,plan,raw=_stage(db,source,pid,scene_id)
            working=self._working(db,pid,scene_id,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]})
            self._current(working,head,record)
            if len(working["events"])>=MAX_EVENTS:
                raise ValueError("This scene has reached its event limit")
            objects={o["id"]:o for o in plan["objects"]}
            obj=objects.get(object_id)
            actor_id=obj["actor_id"] if obj and kind in ACTOR_ACTIONS else None
            event={"id":uuid.uuid4().hex,"kind":kind,
                   "object_id":object_id if kind not in AMBIENT_ACTIONS else None,
                   "actor_id":actor_id,"start_tick":start,"end_tick":end,
                   "target_position":_vec(target_position) if kind in MOVING else None,
                   "intensity":intensity if kind in AMBIENT_ACTIONS else None,
                   "note":note,"status":"director_authored"}
            _event_validate(event,objects,working["duration_tick"])
            working["events"].append(event)
            self._save(db,pid,scene_id,working,expected_revision)
            return self._manifest(db,pid,scene_id,source,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]},plan)
        return self._with(pid,scene_id,change,mutate=True)

    def remove_event(self,pid,scene_id,event_id,expected_revision):
        if type(event_id) is not str or not HEX.fullmatch(event_id):
            raise ValueError("Choose a performance event")
        def change(db,movie,source):
            head,record,plan,raw=_stage(db,source,pid,scene_id)
            working=self._working(db,pid,scene_id,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]})
            self._current(working,head,record)
            old=len(working["events"])
            working["events"]=[e for e in working["events"] if e["id"]!=event_id]
            if len(working["events"])==old:
                raise KeyError("Performance event not found")
            self._save(db,pid,scene_id,working,expected_revision)
            return self._manifest(db,pid,scene_id,source,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]},plan)
        return self._with(pid,scene_id,change,mutate=True)

    def restart_scene(self,pid,scene_id,expected_revision,reason="retake"):
        reason=_short(reason,160)
        def change(db,movie,source):
            head,record,plan,raw=_stage(db,source,pid,scene_id)
            working=self._working(db,pid,scene_id,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]})
            if working["revision"]!=expected_revision:
                raise RuntimeError("Film changed; review the current work first")
            db.execute("""INSERT INTO g06_refused_attempts
                (id,project_id,scene_id,revision,reason,created_at)
                VALUES (?,?,?,?,?,?)""",
                (uuid.uuid4().hex,pid,scene_id,expected_revision,reason,_now()))
            working["events"]=[]
            working["scene_stage_revision"]=head["revision"]
            working["stage_sha256"]=record["usd_sha256"]
            self._save(db,pid,scene_id,working,expected_revision)
            return self._manifest(db,pid,scene_id,source,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]},plan)
        return self._with(pid,scene_id,change,mutate=True)

    def record_native_audio(self,pid,scene_id,actor_id,pcm):
        """Trusted host only; accepts bytes from G06NativeRecorder, not HTTP."""
        if type(pcm) is not bytes or not 2<=len(pcm)<=RATE*2*MAX_NATIVE_PCM_SECONDS or len(pcm)%2:
            raise ValueError("Native microphone recording has invalid PCM bytes")
        if actor_id is not None and (
                type(actor_id) is not str or not actor_id.startswith("ACT_")):
            raise ValueError("Original sound emitter is not a film performer")
        def save(db,movie,source):
            head,record,plan,_raw=_stage(db,source,pid,scene_id)
            actors={o["actor_id"] for o in plan["objects"] if o["role"]=="actor"}
            if actor_id is not None and actor_id not in actors:
                raise ValueError("Recorded speaker is not in this scene")
            cid=uuid.uuid4().hex
            db.execute("""INSERT INTO g06_original_pcm
                (id,project_id,scene_id,actor_id,source_kind,pcm,pcm_sha256,
                 sample_rate,channels,sample_count,recorded_at)
                VALUES (?,?,?,?,'native_microphone_pcm16le',?,?,?,?,?)""",
                (cid,pid,scene_id,actor_id,pcm,_sha(pcm),RATE,1,len(pcm)//2,_now()))
            return {"clip_id":cid,"sample_count":len(pcm)//2,
                    "duration_seconds":len(pcm)//2/RATE,
                    "recorded_from_native_microphone":True}
        return self._with(pid,scene_id,save,mutate=True)

    def freeze_take(self,pid,scene_id,expected_revision,clip_ids=()):
        if (type(clip_ids) not in (list,tuple) or len(clip_ids)>32 or
                len(set(clip_ids))!=len(clip_ids) or
                any(type(x) is not str or not HEX.fullmatch(x) for x in clip_ids)):
            raise ValueError("Select valid original audio clips")
        def freeze(db,movie,source):
            head,record,plan,original=_stage(db,source,pid,scene_id)
            working=self._working(db,pid,scene_id,
                {"revision":head["revision"],"usd_sha256":record["usd_sha256"]})
            self._current(working,head,record)
            if working["revision"]!=expected_revision:
                raise RuntimeError("Performance changed; review it before freezing")
            if db.execute("""SELECT COUNT(*) FROM g06_frozen_takes
                WHERE project_id=? AND scene_id=?""",(pid,scene_id)).fetchone()[0] >= MAX_TAKES_PER_SCENE:
                raise ValueError("This scene has reached its Take limit")
            objects={x["id"]:x for x in plan["objects"]}
            for event in working["events"]:
                _event_validate(event,objects,working["duration_tick"])
            animated=_author_performance(original,plan,working)
            audio=[]
            for clip_id in clip_ids:
                clip=db.execute("""SELECT id,actor_id,pcm,pcm_sha256,
                    sample_rate,channels,sample_count FROM g06_original_pcm
                    WHERE project_id=? AND scene_id=? AND id=?""",
                    (pid,scene_id,clip_id)).fetchone()
                if clip is None:raise KeyError("Original recording not in this scene")
                if (_sha(clip["pcm"])!=clip["pcm_sha256"] or
                    clip["sample_rate"]!=RATE or clip["channels"]!=1 or
                    len(clip["pcm"])!=clip["sample_count"]*2):
                    raise RuntimeError("Original source audio failed its integrity check")
                if clip["sample_count"]*SAMPLE_TICKS>working["duration_tick"]:
                    raise ValueError("Original sound is longer than this scene")
                audio.append({"clip_id":clip_id,"actor_id":clip["actor_id"],
                    "pcm_sha256":clip["pcm_sha256"],
                    "sample_rate":RATE,"channels":1,
                    "sample_count":clip["sample_count"],"start_tick":0,
                    "duration_tick":clip["sample_count"]*SAMPLE_TICKS})
            take_id=uuid.uuid4().hex
            document={"format":TAKE_FORMAT,"project_id":pid,
                "scene_id":scene_id,"source_stage_revision":head["revision"],
                "scene_source_sha256":head["source_sha256"],
                "original_usd_sha256":_sha(original),
                "performance_usd_sha256":_sha(animated),
                "duration_tick":working["duration_tick"],
                "tick_rate":TICKS_PER_SECOND,
                "events":working["events"],"audio":audio,
                "camera_tracks_frozen":False,"immutable":True,
                "source_is_original_openusd":True,
                "picture_frames_rendered":False}
            digest=_sha(_json(document).encode("utf8"))
            db.execute("""INSERT INTO g06_frozen_takes(
                take_id,project_id,scene_id,source_stage_revision,
                source_sha256,original_usd_sha256,original_usd,
                performance_usd_sha256,performance_usd,performance_json,
                audio_json,take_sha256,frozen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (take_id,pid,scene_id,head["revision"],head["source_sha256"],
                 _sha(original),original,_sha(animated),animated,
                 _json(document),_json(audio),digest,_now()))
            # The source was approved at the time of capture. A future edit
            # cannot change the frozen original, performance, or PCM.
            return {"take_id":take_id,"digest":digest,"scene_id":scene_id,
                    "duration_seconds":float(_time(working["duration_tick"])),
                    "audio_clip_count":len(audio),"frozen":True,
                    "camera_changes_preserve_take":True}
        return self._with(pid,scene_id,freeze,mutate=True)

    def _take(self,db,pid,take_id,with_audio=False):
        if type(take_id) is not str or not HEX.fullmatch(take_id):
            raise ValueError("Select a recorded Take")
        row=db.execute("""SELECT * FROM g06_frozen_takes
            WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
        if row is None:raise KeyError("Take not found in this movie")
        data=json.loads(row["performance_json"])
        if (data.get("format")!=TAKE_FORMAT or
            _sha(row["original_usd"])!=row["original_usd_sha256"] or
            _sha(row["performance_usd"])!=row["performance_usd_sha256"] or
            _sha(_json(data).encode("utf8"))!=row["take_sha256"] or
            data["original_usd_sha256"]!=row["original_usd_sha256"] or
            data["performance_usd_sha256"]!=row["performance_usd_sha256"] or
            data["scene_id"]!=row["scene_id"]):
            raise RuntimeError("The original Take has changed unexpectedly")
        from pxr import Sdf,Usd
        for label,raw in (("original",row["original_usd"]),
                          ("performance",row["performance_usd"])):
            layer=Sdf.Layer.CreateAnonymous("g06-verify-"+label+".usda")
            if not layer.ImportFromString(raw.decode("utf8")) or (
                    layer.subLayerPaths or layer.GetExternalReferences()) or (
                    not Usd.Stage.Open(layer,Usd.Stage.LoadNone)):
                raise RuntimeError("Frozen original scene could not be reopened")
        audio=json.loads(row["audio_json"])
        if audio!=data["audio"]:
            raise RuntimeError("Original audio binding was changed")
        for entry in audio:
            clip=db.execute("""SELECT actor_id,pcm,pcm_sha256,
                sample_count FROM g06_original_pcm
                WHERE project_id=? AND scene_id=? AND id=?""",
                (pid,row["scene_id"],entry["clip_id"])).fetchone()
            if (clip is None or clip["actor_id"]!=entry["actor_id"] or
                _sha(clip["pcm"])!=clip["pcm_sha256"] or
                clip["pcm_sha256"]!=entry["pcm_sha256"] or
                clip["sample_count"]!=entry["sample_count"]):
                raise RuntimeError("Take's original recorded sound is missing")
        return row,data,audio

    def read_take(self,pid,scene_id,take_id):
        def read(db,movie,source):
            row,doc,audio=self._take(db,pid,take_id)
            if row["scene_id"]!=scene_id:
                raise KeyError("Take belongs to another film scene")
            views=self._camera(db,pid,take_id)
            return {"take_id":take_id,"digest":row["take_sha256"],
                    "scene_id":scene_id,"frozen":True,
                    "duration_seconds":float(_time(doc["duration_tick"])),
                    "events":[{**e,
                        "start_seconds":float(_time(e["start_tick"])),
                        "end_seconds":float(_time(e["end_tick"]))}
                        for e in doc["events"]],
                    "audio_clip_count":len(audio),"camera":views,
                    "camera_changes_preserve_take":True}
        return self._with(pid,scene_id,read)

    @staticmethod
    def _camera(db,pid,take_id):
        row=db.execute("""SELECT revision,views_json FROM g06_camera_views
            WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
        if row:
            return {"revision":row["revision"],"views":json.loads(row["views_json"])}
        return {"revision":0,"views":[
            {"name":"Wide","focal_mm":24.,"position":[13.,-23.,12.],
             "look_at":[0.,0.,1.5]},
            {"name":"Medium","focal_mm":50.,"position":[8.,-12.,5.],
             "look_at":[0.,0.,1.4]},
            {"name":"Close-up","focal_mm":85.,"position":[3.6,-5.,2.4],
             "look_at":[0.,0.,1.7]}]}

    def change_camera(self,pid,scene_id,take_id,expected_revision,
                      view_index,focal_mm,position,look_at):
        if (type(view_index) is not int or not 0<=view_index<3 or
            type(focal_mm) not in (float,int) or not math.isfinite(focal_mm) or
            not 12<=focal_mm<=180 or
            type(expected_revision) is not int or expected_revision<0):
            raise ValueError("Choose a camera view and focal length")
        position=_vec(position);look_at=_vec(look_at)
        def revise(db,movie,source):
            row,doc,audio=self._take(db,pid,take_id)
            if row["scene_id"]!=scene_id:raise KeyError("Take belongs to another scene")
            camera=self._camera(db,pid,take_id)
            if camera["revision"]!=expected_revision:
                raise RuntimeError("Framing has changed; review the current camera")
            views=camera["views"]
            views[view_index]={"name":views[view_index]["name"],
                "focal_mm":float(focal_mm),"position":position,"look_at":look_at}
            revision=expected_revision+1
            db.execute("""INSERT INTO g06_camera_view_history
                (project_id,take_id,revision,views_json,saved_at)
                VALUES (?,?,?,?,?)""",
                (pid,take_id,revision,_json(views),_now()))
            db.execute("""INSERT INTO g06_camera_views
                (project_id,take_id,revision,views_json,updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(project_id,take_id) DO UPDATE SET
                 revision=excluded.revision,views_json=excluded.views_json,
                 updated_at=excluded.updated_at""",
                (pid,take_id,revision,_json(views),_now()))
            return {"take_id":take_id,"take_digest":row["take_sha256"],
                    "camera":self._camera(db,pid,take_id),
                    "original_take_unchanged":True}
        return self._with(pid,scene_id,revise,mutate=True)
