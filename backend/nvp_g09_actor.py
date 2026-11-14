"""G09-B: human-reviewed original-ActorID performance, non-destructive.

A film actor is always the authoritative G04 ActorID already present in a
G06 frozen Digital Take. This layer never changes or invents a performer,
word, speaker, PCM source, USD original or capture authority.

Director-approved body/face/gait/wardrobe and original-voice selections are
immutable derived revisions. Voice *performance* is the native microphone
source itself, not a model-generated stand-in. Envelope-driven jaw animation
is real source-synchronized animation, NOT speech recognition, phoneme/viseme
alignment, recorded facial motion, or ElevenLabs-class synthetic acting.
"""
from __future__ import annotations

import copy
from datetime import datetime,timezone
import json
import math
import uuid

from backend.nvp_g07_edit import G07Editor,_sha,_json,_sec
from backend.nvp_g06_filming import HEX,RATE
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.g09.actor_performance.v1"
MOTION=("neutral","natural","restrained","energetic","heavy")
EMOTION=("neutral","joy","sadness","anger","fear","surprise","focus")
HAIR=("bald","short","medium","long")
VOICE_STATES=("unreviewed","approved","rejected")
MAX_ACTORS=12
MAX_VOICES_PER_ACTOR=12
MAX_VER=3000
FROZEN_CONSTRAINT="source_take_unchanged"
MAX_TIME=3*3600*TICKS_PER_SECOND


def _now():
    return datetime.now(timezone.utc).isoformat()


def _number(value,lo,hi,name):
    if type(value) not in (int,float) or type(value) is bool or (
            not math.isfinite(value)) or not lo<=value<=hi:
        raise ValueError("Choose a realistic "+name)
    return float(value)


def _color(value):
    import re
    if type(value) is not str or not re.fullmatch(r"#[0-9a-fA-F]{6}",value):
        raise ValueError("Choose a character color")
    return value.lower()


def _profile(source):
    return {"actor_id":source["actor_id"],"object_id":source["id"],
        "name":source["name"],"movement":"natural",
        "emotion":"neutral","expression_strength":.55,
        "gait_strength":.7,"blink_rate":13.,
        "height_scale":1.0,"shoulder_width":1.,
        "skin_color":"#b38b71","hair_color":"#46332f",
        "hair":"short","wardrobe_color":source["color"],
        "eye_color":"#3d4748","voice_clips":[],
        "expression_cues":[],"director_note":""}


def _original_actors(doc):
    original=doc.get("stage_objects")
    if type(original) is not list:
        raise RuntimeError("Frozen Digital Take has no original scene geometry")
    seen=set()
    cast={}
    for obj in original:
        if obj["role"]!="actor":continue
        actor_id=obj["actor_id"]
        if (type(actor_id) is not str or not actor_id.startswith("ACT_") or
                not obj["id"].startswith("O_") or actor_id in cast):
            raise RuntimeError("Original scene has an invalid or duplicate ActorID")
        cast[actor_id]=obj
    if len(cast)>MAX_ACTORS:
        raise ValueError("This initial performer workspace supports up to twelve characters")
    return cast


def _clip_sources(doc):
    result={}
    for entry in doc.get("audio",[]):
        if not HEX.fullmatch(entry["clip_id"]):
            raise RuntimeError("Original voice identity is invalid")
        result[entry["clip_id"]]=entry
    return result


def _validate_voice(v,actor_id,clips):
    if (type(v) is not dict or set(v)!={"clip_id","review","delivery",
                                       "dialogue_note","actor_id"} or
        v["actor_id"]!=actor_id or type(v["clip_id"]) is not str or
        v["clip_id"] not in clips or clips[v["clip_id"]]["actor_id"]!=actor_id):
        raise ValueError("Select original sound recorded for this character")
    if type(v["review"]) is not str or v["review"] not in VOICE_STATES:
        raise ValueError("The actor's delivery needs director review")
    if (type(v["delivery"]) is not str or len(v["delivery"])>140 or
        type(v["dialogue_note"]) is not str or
        len(v["dialogue_note"])>600 or
        any(ord(c)<32 and c not in "\t\n" for c in v["dialogue_note"])):
        raise ValueError("Keep performance direction short")
    # Direction/notes do not claim that the recording contains those words.
    return v


def _validate_profile(profile,original,clips,duration):
    if (type(profile) is not dict or set(profile)!={
        "actor_id","object_id","name","movement","emotion",
        "expression_strength","gait_strength","blink_rate",
        "height_scale","shoulder_width","skin_color","hair_color",
        "hair","wardrobe_color","eye_color","voice_clips",
        "expression_cues","director_note"}):
        raise ValueError("Actor performance has an unknown field")
    if (profile["actor_id"]!=original["actor_id"] or
        profile["object_id"]!=original["id"] or
        profile["name"]!=original["name"]):
        raise RuntimeError("ActorID source identity was changed")
    if profile["movement"] not in MOTION or profile["emotion"] not in EMOTION or (
            profile["hair"] not in HAIR):
        raise ValueError("Choose a supported acting or appearance style")
    for field,lo,hi in (("expression_strength",0,1),("gait_strength",0,2),
                        ("blink_rate",0,40),("height_scale",.65,1.45),
                        ("shoulder_width",.55,1.55)):
        _number(profile[field],lo,hi,field.replace("_"," "))
    for field in ("skin_color","hair_color","wardrobe_color","eye_color"):
        _color(profile[field])
    if (type(profile["director_note"]) is not str or
            len(profile["director_note"])>1000):
        raise ValueError("Keep the character direction short")
    voice=profile["voice_clips"]
    if type(voice) is not list or len(voice)>MAX_VOICES_PER_ACTOR:
        raise ValueError("Too many original voice sources")
    ids=set()
    for item in voice:
        _validate_voice(item,profile["actor_id"],clips)
        if item["clip_id"] in ids:
            raise ValueError("The same original voice was selected twice")
        ids.add(item["clip_id"])
    cues=profile["expression_cues"]
    if type(cues) is not list or len(cues)>64:
        raise ValueError("Choose up to sixty-four facial expression changes")
    previous=-1;ids=set()
    for cue in cues:
        if (type(cue) is not dict or
            set(cue)!={"id","at_tick","emotion","strength"} or
            type(cue["id"]) is not str or not HEX.fullmatch(cue["id"]) or
            cue["id"] in ids or type(cue["at_tick"]) is not int or
            not 0<=cue["at_tick"]<duration or cue["at_tick"]<=previous or
            type(cue["emotion"]) is not str or
            cue["emotion"] not in EMOTION):
            raise ValueError("An expression cue is outside the original scene")
        _number(cue["strength"],0,1,"expression intensity")
        ids.add(cue["id"]);previous=cue["at_tick"]
    return profile


def _default(take_id,take_sha,doc):
    cast=_original_actors(doc)
    clips=_clip_sources(doc)
    profiles=[]
    for actor in cast.values():
        profile=_profile(actor)
        for clip in clips.values():
            if clip["actor_id"]==actor["actor_id"]:
                profile["voice_clips"].append({
                    "clip_id":clip["clip_id"],"actor_id":actor["actor_id"],
                    "review":"unreviewed","delivery":"","dialogue_note":""})
        profiles.append(profile)
    return {"format":FORMAT,"take_id":take_id,"take_sha256":take_sha,
        "actors":profiles,"frozen_originals_preserved":True}


def _validate(doc,take_id,take_sha,original):
    if (type(doc) is not dict or set(doc)!={
        "format","take_id","take_sha256","actors","frozen_originals_preserved"
    } or doc["format"]!=FORMAT or doc["take_id"]!=take_id or
        doc["take_sha256"]!=take_sha or
        doc["frozen_originals_preserved"] is not True or
        type(doc["actors"]) is not list):
        raise ValueError("The acting direction belongs to a different original Take")
    cast=_original_actors(original)
    if len(doc["actors"])!=len(cast):
        raise ValueError("Every original performer must keep their ActorID")
    clips=_clip_sources(original)
    seen=set()
    for profile in doc["actors"]:
        if type(profile) is not dict:
            raise ValueError("Actor profile is invalid")
        actor_id=profile.get("actor_id")
        if actor_id not in cast or actor_id in seen:
            raise ValueError("The acting plan contains an unknown character")
        _validate_profile(profile,cast[actor_id],clips,
                          original["duration_tick"])
        seen.add(actor_id)
    if len(_json(doc).encode("utf8"))>180000:
        raise ValueError("Actor direction has exceeded its size budget")
    return doc


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09_actor_versions(
        project_id TEXT NOT NULL,take_id TEXT NOT NULL,
        revision INTEGER NOT NULL,take_sha256 TEXT NOT NULL,
        document_json TEXT NOT NULL,document_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(project_id,take_id,revision))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09_actor_heads(
        project_id TEXT NOT NULL,take_id TEXT NOT NULL,
        draft_revision INTEGER NOT NULL,approved_revision INTEGER NOT NULL,
        take_sha256 TEXT NOT NULL,updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,take_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09_actor_templates(
        project_id TEXT NOT NULL,actor_id TEXT NOT NULL,
        revision INTEGER NOT NULL,profile_json TEXT NOT NULL,
        profile_sha256 TEXT NOT NULL,source_take_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(project_id,actor_id,revision))""")


def _take(db,pid,take_id):
    # G06's independent original-media validator checks USD, PCM hashes
    # and the Take manifest before any derived acting records are usable.
    from backend.nvp_g06_filming import G06Filming
    # Caller already has an editor and passes its validator separately.
    row=db.execute("""SELECT take_sha256,performance_json FROM g06_frozen_takes
        WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
    if row is None:raise KeyError("Original recorded Take not found")
    doc=json.loads(row["performance_json"])
    return row["take_sha256"],doc


def _version(db,pid,take_id,version):
    row=db.execute("""SELECT document_json,document_sha256,take_sha256
        FROM g09_actor_versions WHERE project_id=? AND take_id=?
          AND revision=?""",(pid,take_id,version)).fetchone()
    if not row:raise KeyError("Earlier actor performance version was not found")
    if _sha(row["document_json"].encode("utf8"))!=row["document_sha256"]:
        raise RuntimeError("Recorded actor direction history was changed")
    doc=json.loads(row["document_json"])
    if doc["take_sha256"]!=row["take_sha256"]:
        raise RuntimeError("Actor direction is no longer bound to its original")
    return doc,row["document_sha256"]


def _current(db,pid,take_id,take_sha,source):
    head=db.execute("""SELECT draft_revision,approved_revision,take_sha256
        FROM g09_actor_heads WHERE project_id=? AND take_id=?""",
        (pid,take_id)).fetchone()
    if head is None:
        return 0,0,_default(take_id,take_sha,source)
    if head["take_sha256"]!=take_sha:
        raise RuntimeError("Character direction refers to a different original Take")
    doc,_=_version(db,pid,take_id,head["draft_revision"])
    _validate(doc,take_id,take_sha,source)
    return head["draft_revision"],head["approved_revision"],doc


def _save(db,pid,take_id,take_sha,doc,expected,approved):
    row=db.execute("""SELECT draft_revision FROM g09_actor_heads
        WHERE project_id=? AND take_id=?""",(pid,take_id)).fetchone()
    current=row["draft_revision"] if row else 0
    if current!=expected:
        raise RuntimeError("The character directions changed in another window")
    new=current+1
    if new>MAX_VER:
        raise RuntimeError("Actor direction history limit reached")
    raw=_json(doc);sha=_sha(raw.encode("utf8"))
    db.execute("""INSERT INTO g09_actor_versions
        (project_id,take_id,revision,take_sha256,document_json,
         document_sha256,created_at)
        VALUES (?,?,?,?,?,?,?)""",
        (pid,take_id,new,take_sha,raw,sha,_now()))
    db.execute("""INSERT INTO g09_actor_heads
        (project_id,take_id,draft_revision,approved_revision,take_sha256,
         updated_at) VALUES (?,?,?,?,?,?)
        ON CONFLICT(project_id,take_id) DO UPDATE SET
        draft_revision=excluded.draft_revision,updated_at=excluded.updated_at""",
        (pid,take_id,new,approved,take_sha,_now()))
    return new


def _public(db,pid,take_id,take_sha,source):
    draft,approved,doc=_current(db,pid,take_id,take_sha,source)
    clips=[{"clip_id":entry["clip_id"],
            "actor_id":entry["actor_id"],
            "start_seconds":entry["start_tick"]/TICKS_PER_SECOND,
            "duration_seconds":entry["duration_tick"]/TICKS_PER_SECOND}
            for entry in source.get("audio",[]) if entry["actor_id"]]
    history=[{"revision":row["revision"],"created_at":row["created_at"]}
             for row in db.execute("""SELECT revision,created_at
                FROM g09_actor_versions WHERE project_id=? AND take_id=?
                ORDER BY revision DESC LIMIT 35""",(pid,take_id))]
    continuity={}
    for row in db.execute("""SELECT actor_id,MAX(revision) AS version
       FROM g09_actor_templates WHERE project_id=? GROUP BY actor_id""",(pid,)):
        continuity[row["actor_id"]]=row["version"]
    return {"format":FORMAT,"take_id":take_id,"take_sha256":take_sha,
        "continuity_profiles":continuity,
        "duration_seconds":source["duration_tick"]/TICKS_PER_SECOND,
        "revision":draft,"approved_revision":approved,
        "approved_for_film":approved>0,
        "draft":doc,"available_recorded_voices":clips,
        "history":history,"original_media_preserved":True,
        "dialogue_fabricated":False,
        "true_phoneme_alignment":False}


class G09Actors:
    def __init__(self,studio,live=None,token=None):
        self.editor=G07Editor(studio,live,token)

    def _execute(self,pid,fn,mutate=False):
        def work(db,movie):
            _schema(db)
            self.editor.filming._schema(db)
            return fn(db,movie)
        return self.editor._execute(pid,work,mutate=mutate)

    def view(self,pid,take_id):
        def read(db,movie):
            row,source,audio=self.editor._take(db,pid,take_id,{})
            return _public(db,pid,take_id,row["take_sha256"],source)
        return self._execute(pid,read)

    def change(self,pid,take_id,actor_id,expected_revision,operation,details):
        if (type(expected_revision) is not int or expected_revision<0 or
            type(actor_id) is not str or not actor_id.startswith("ACT_") or
            type(operation) is not str or type(details) is not dict):
            raise ValueError("Choose a known actor and current direction")
        def change_tx(db,movie):
            row,source,audio=self.editor._take(db,pid,take_id,{})
            take_sha=row["take_sha256"]
            rev,approved,doc=_current(db,pid,take_id,take_sha,source)
            if rev!=expected_revision:
                raise RuntimeError("Your performance directions were updated elsewhere")
            doc=copy.deepcopy(doc)
            profile=next((x for x in doc["actors"]
                          if x["actor_id"]==actor_id),None)
            if profile is None:raise KeyError("ActorID not part of this filmed Take")
            if operation=="appearance":
                if set(details)!={"skin_color","hair_color","hair",
                                   "wardrobe_color","eye_color",
                                   "height_scale","shoulder_width"}:
                    raise ValueError("Choose a complete character appearance")
                for key,val in details.items():profile[key]=val
            elif operation=="acting":
                if set(details)!={"movement","emotion","expression_strength",
                                   "gait_strength","blink_rate","director_note"}:
                    raise ValueError("Choose an acting and movement style")
                for key,val in details.items():profile[key]=val
            elif operation=="add_expression":
                if set(details)!={"at_seconds","emotion","strength"}:
                    raise ValueError("Choose the scene moment and expression")
                at_tick=_sec(details["at_seconds"])
                if at_tick>=source["duration_tick"]:
                    raise ValueError("Choose a moment inside this Take")
                cue={"id":uuid.uuid4().hex,"at_tick":at_tick,
                     "emotion":details["emotion"],
                     "strength":details["strength"]}
                profile["expression_cues"].append(cue)
                profile["expression_cues"].sort(key=lambda v:(
                    v["at_tick"],v["id"]))
            elif operation=="remove_expression":
                if set(details)!={"cue_id"}:
                    raise ValueError("Choose an expression cue to remove")
                before=len(profile["expression_cues"])
                profile["expression_cues"]=[
                    v for v in profile["expression_cues"]
                    if v["id"]!=details["cue_id"]]
                if before==len(profile["expression_cues"]):
                    raise KeyError("This facial cue was already removed")
            elif operation=="review_voice":
                if set(details)!={"clip_id","review","delivery","dialogue_note"}:
                    raise ValueError("Choose one original voice to review")
                entry=next((x for x in profile["voice_clips"]
                            if x["clip_id"]==details["clip_id"]),None)
                if entry is None:raise KeyError("This recording belongs to another actor")
                entry.update(details)
                _validate_voice(entry,actor_id,_clip_sources(source))
            else:raise ValueError("This acting change is not supported")
            _validate(doc,take_id,take_sha,source)
            _save(db,pid,take_id,take_sha,doc,expected_revision,approved)
            return _public(db,pid,take_id,take_sha,source)
        return self._execute(pid,change_tx,mutate=True)

    def approve(self,pid,take_id,expected_revision):
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("Review a saved character direction first")
        def commit(db,movie):
            row,source,audio=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],source)
            if rev!=expected_revision:
                raise RuntimeError("Actor performance changed while being reviewed")
            _validate(doc,take_id,row["take_sha256"],source)
            db.execute("""UPDATE g09_actor_heads SET approved_revision=?,
                updated_at=? WHERE project_id=? AND take_id=?""",
                (rev,_now(),pid,take_id))
            return _public(db,pid,take_id,row["take_sha256"],source)
        return self._execute(pid,commit,mutate=True)

    def restore(self,pid,take_id,source_revision,expected_revision):
        if (type(source_revision) is not int or source_revision<=0 or
                type(expected_revision) is not int or expected_revision<0):
            raise ValueError("Choose earlier actor directions")
        def restore_tx(db,movie):
            row,source,audio=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],source)
            if rev!=expected_revision:
                raise RuntimeError("Reopen the current actor directions")
            saved,sha=_version(db,pid,take_id,source_revision)
            _validate(saved,take_id,row["take_sha256"],source)
            _save(db,pid,take_id,row["take_sha256"],saved,expected_revision,approved)
            return _public(db,pid,take_id,row["take_sha256"],source)
        return self._execute(pid,restore_tx,mutate=True)

    def save_character(self,pid,take_id,actor_id,expected_revision):
        """Save approved appearance/acting baseline for the SAME ActorID.

        Recorded voice IDs, expression timings, source object IDs and
        source-scoped dialogue notes are never reused across Takes.
        """
        if type(actor_id) is not str or not actor_id.startswith("ACT_"):
            raise ValueError("Choose a real cast character")
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("Approve your character direction before saving")
        baseline=("movement","emotion","expression_strength",
                  "gait_strength","blink_rate","height_scale",
                  "shoulder_width","skin_color","hair_color",
                  "hair","wardrobe_color","eye_color")
        def save(db,movie):
            row,original,_=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],original)
            if rev!=expected_revision or approved!=rev:
                raise RuntimeError("Approve this current acting version first")
            actor=next((p for p in doc["actors"]
                        if p["actor_id"]==actor_id),None)
            if actor is None:raise KeyError("ActorID was not in this source Take")
            profile={"actor_id":actor_id,**{k:actor[k] for k in baseline}}
            raw=_json(profile)
            last=db.execute("""SELECT COALESCE(MAX(revision),0) AS revision
              FROM g09_actor_templates WHERE project_id=? AND actor_id=?""",
              (pid,actor_id)).fetchone()["revision"]
            if last>=500:raise RuntimeError("Too many character continuity versions")
            db.execute("""INSERT INTO g09_actor_templates
                (project_id,actor_id,revision,profile_json,profile_sha256,
                 source_take_sha256,created_at) VALUES (?,?,?,?,?,?,?)""",
                (pid,actor_id,last+1,raw,_sha(raw.encode("utf8")),
                 row["take_sha256"],_now()))
            return _public(db,pid,take_id,row["take_sha256"],original)
        return self._execute(pid,save,mutate=True)

    def use_character(self,pid,take_id,actor_id,expected_revision):
        """Copy approved creative identity, NEVER the source-bound voice/cues."""
        if type(actor_id) is not str or not actor_id.startswith("ACT_"):
            raise ValueError("Choose the current film character")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Review this character's current version")
        def use(db,movie):
            row,original,_=self.editor._take(db,pid,take_id,{})
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],original)
            if rev!=expected_revision:
                raise RuntimeError("Another performance revision was saved")
            template=db.execute("""SELECT profile_json,profile_sha256
               FROM g09_actor_templates WHERE project_id=? AND actor_id=?
               ORDER BY revision DESC LIMIT 1""",(pid,actor_id)).fetchone()
            if template is None:raise KeyError("No approved profile for this character")
            if _sha(template["profile_json"].encode("utf8"))!=template["profile_sha256"]:
                raise RuntimeError("The saved character continuity record changed")
            source=json.loads(template["profile_json"])
            if source.get("actor_id")!=actor_id:
                raise RuntimeError("This character continuity belongs to another ActorID")
            doc=copy.deepcopy(doc)
            actor=next((x for x in doc["actors"]
                        if x["actor_id"]==actor_id),None)
            if actor is None:raise KeyError("This character does not occur in the Take")
            for field,value in source.items():
                if field!="actor_id":actor[field]=value
            _validate(doc,take_id,row["take_sha256"],original)
            _save(db,pid,take_id,row["take_sha256"],doc,rev,approved)
            return _public(db,pid,take_id,row["take_sha256"],original)
        return self._execute(pid,use,mutate=True)

    def voice_preview(self,pid,take_id,clip_id):
        """Audition the verified source recording before approving a voice."""
        if type(clip_id) is not str or not HEX.fullmatch(clip_id):
            raise ValueError("Choose a recorded voice")
        def read(db,movie):
            row,source,audio=self.editor._take(db,pid,take_id,{})
            selected=next((x for x in audio if x["clip_id"]==clip_id),None)
            if selected is None or not selected["actor_id"]:
                raise KeyError("This is not an original actor voice in the Take")
            clip=db.execute("""SELECT pcm,pcm_sha256,sample_count,actor_id
                FROM g06_original_pcm WHERE project_id=? AND scene_id=? AND id=?""",
                (pid,row["scene_id"],clip_id)).fetchone()
            if (clip is None or clip["actor_id"]!=selected["actor_id"] or
                len(clip["pcm"])!=clip["sample_count"]*2 or
                _sha(clip["pcm"])!=selected["pcm_sha256"] or
                clip["pcm_sha256"]!=selected["pcm_sha256"]):
                raise RuntimeError("Original actor voice is missing or changed")
            import io,wave
            output=io.BytesIO()
            with wave.open(output,"wb") as wav:
                wav.setnchannels(1);wav.setsampwidth(2)
                wav.setframerate(RATE);wav.writeframes(bytes(clip["pcm"]))
            return output.getvalue()
        return self._execute(pid,read)

    def picture_preview(self,pid,take_id,time_seconds="0"):
        """Derived first-frame acting audition; original source is unmodified."""
        from backend.nvp_g07_edit import _sec,_default_grade
        tick=_sec(time_seconds)
        def read(db,movie):
            row,source,audio=self.editor._take(db,pid,take_id,{})
            if tick>=source["duration_tick"]:
                raise ValueError("Choose a moment in the original scene")
            rev,approved,doc=_current(db,pid,take_id,row["take_sha256"],source)
            from backend.nvp_g09_actor_rig import ActorFrameEvaluator
            from backend.nvp_g08_native_avi import SourceWorld
            from backend.nvp_g09_render import _one_shot
            from backend.nvp_g09_environment import _default as original_look
            from backend.nvp_g09_environment import G09Environment
            record={"performance_usd":bytes(row["performance_usd"]),
                "performance_sha256":row["performance_usd_sha256"],
                "take_sha256":row["take_sha256"],
                "stage_objects":source["stage_objects"],
                "stage_setting":source["stage_setting"],"events":source["events"],
                "duration_tick":source["duration_tick"],"audio":[]}
            for entry in audio:
                clip=db.execute("""SELECT pcm,pcm_sha256 FROM g06_original_pcm
                    WHERE project_id=? AND scene_id=? AND id=?""",
                    (pid,row["scene_id"],entry["clip_id"])).fetchone()
                if clip is None or _sha(clip["pcm"])!=entry["pcm_sha256"]:
                    raise RuntimeError("The original actor sound was changed")
                record["audio"].append({**entry,"pcm16le":bytes(clip["pcm"])})
            world=SourceWorld(record)
            current={"performance":doc,"revision":rev,
                     "sha256":_sha(_json(doc).encode("utf8"))}
            if doc["actors"]:
                world.actor_frame_evaluator=ActorFrameEvaluator(record,current)
            from backend.nvp_g09_environment import _json as _ejson,_sha as _esha
            look=G09Environment.approved_source(
                db,pid,take_id,row["take_sha256"],source)
            if look is None:
                fallback=original_look(take_id,row["take_sha256"],source)
                look={"revision":0,"look":fallback,
                      "sha256":_esha(_ejson(fallback).encode("utf8"))}
            view=self.editor.filming._camera(db,pid,take_id)["views"][0]
            shot={"take_id":take_id,"take_sha256":row["take_sha256"],
                  "camera":view,"grade":_default_grade()}
            picture=_one_shot(shot,world,tick,look)
            from io import BytesIO
            result=BytesIO()
            picture.save(result,format="JPEG",quality=79,subsampling=1)
            return result.getvalue()
        return self._execute(pid,read)

    @staticmethod
    def approved_source(db,pid,take_id,take_sha,original):
        """Only exact immutable director-approved ActorID/source revisions."""
        _schema(db)
        head=db.execute("""SELECT approved_revision,take_sha256
            FROM g09_actor_heads WHERE project_id=? AND take_id=?""",
            (pid,take_id)).fetchone()
        if not head or not head["approved_revision"]:
            return None
        if head["take_sha256"]!=take_sha:
            raise RuntimeError("Actor performance is from a different Take")
        doc,digest=_version(db,pid,take_id,head["approved_revision"])
        _validate(doc,take_id,take_sha,original)
        return {"revision":head["approved_revision"],"sha256":digest,
                "performance":doc}
