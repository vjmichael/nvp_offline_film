"""G09-D human-reviewed, source-locked finishing for the FIRST native film.

Finishing applies only to a derived presentation. The authoritative G06
OpenUSD/ActorID/PCM and G07 edit remain unchanged. A completion MAY be called
an SDR working film when its measured profile passes. No 8-bit JPEG source
or 16-bit PCM output is silently relabeled as ACES/OCIO, Rec.2020, ProRes,
24-bit capture, SMPTE DCP, theatrical master or studio-certified loudness.
"""
from __future__ import annotations

import copy
from datetime import datetime,timezone
import json
import math

from backend.nvp_g07_edit import G07Editor,_project,_json,_sha

FORMAT="nvp.g09d.finishing.v1"
PROFILE="native_sdr_avi_640p24_pcm16"
MAX_REVISIONS=2500
SOURCE_KEYS=("edit_revision","edit_sha256","production_looks_sha256",
             "actor_performances_sha256","acoustic_looks_sha256",
             "original_takes_sha256")
LEVELS=("working","broadcast_review","dialogue_review")
DEFAULT_AUDIO={"target_lufs":-18.0,"peak_ceiling_dbfs":-1.5,
               "fade_in_seconds":0.0,"fade_out_seconds":0.0}
DEFAULT_COLOR={"exposure":0.0,"contrast":1.0,"saturation":1.0,
               "lift":0.0,"warmth":0.0}

def _now():return datetime.now(timezone.utc).isoformat()

def _number(value,low,high,label):
    if (type(value) not in (int,float) or type(value) is bool or
        not math.isfinite(value) or not low<=value<=high):
        raise ValueError("Choose a valid "+label)
    return float(value)

def _default(binding):
    return {"format":FORMAT,"profile":PROFILE,"source":binding,
        "color":dict(DEFAULT_COLOR),"audio":dict(DEFAULT_AUDIO),
        "finishing_intent":"working",
        "notes":"","source_media_unchanged":True,
        "display_referred_input":"srgb_8bit",
        "output_transfer":"srgb_8bit",
        "output_audio":"pcm16_48000_stereo",
        "ocio_aces_certified":False,"cinema_dcp_certified":False}

def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09d_finish_versions(
        project_id TEXT NOT NULL,revision INTEGER NOT NULL,
        source_sha256 TEXT NOT NULL,document_json TEXT NOT NULL,
        document_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
        PRIMARY KEY(project_id,revision))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09d_finish_heads(
        project_id TEXT PRIMARY KEY,
        draft_revision INTEGER NOT NULL,
        approved_revision INTEGER NOT NULL,
        updated_at TEXT NOT NULL)""")

def _binding(db,pid,editor):
    """Recompute the full source identity WITHOUT entering native_assembly.

    Calling G07.native_assembly within a SQLite mutation would open a second
    project DB connection (unsafe for encrypted project sessions). Binding
    here uses the same independently verified Take/revision approval records.
    """
    from backend.nvp_g09_environment import G09Environment
    from backend.nvp_g09_actor import G09Actors
    from backend.nvp_g09c_acoustics import G09CAcoustics
    version,document=_project(db,pid)
    duration,segments=editor._validate(db,pid,document)
    if version<1 or duration<=0 or not segments:
        raise ValueError("Add and save film shots before finishing")
    seen={}
    looks={};actors={};acoustics={}
    for seg in segments:
        tid=seg["take_id"]
        if tid in seen:continue
        row,original,audio=editor._take(db,pid,tid,{})
        sha=row["take_sha256"]
        seen[tid]=sha
        for dest,reader in (
            (looks,G09Environment.approved_source),
            (actors,G09Actors.approved_source),
            (acoustics,G09CAcoustics.approved_source)):
            record=reader(db,pid,tid,sha,original)
            if record is not None:dest[tid]=record
    def digest(data):
        return _sha(_json({
            tid:{"revision":data[tid]["revision"],
                 "sha256":data[tid]["sha256"]}
            for tid in sorted(data)}).encode("utf8"))
    return {"edit_revision":version,
        "edit_sha256":_sha(_json(document).encode("utf8")),
        "production_looks_sha256":digest(looks),
        "actor_performances_sha256":digest(actors),
        "acoustic_looks_sha256":digest(acoustics),
        "original_takes_sha256":_sha(_json(
            [[tid,seen[tid]] for tid in sorted(seen)]).encode("utf8"))}

def _source_digest(binding):
    if type(binding) is not dict or set(binding)!=set(SOURCE_KEYS):
        raise ValueError("Finished film source contract changed")
    return _sha(_json(binding).encode("utf8"))

def _validate(doc,binding=None):
    if (type(doc) is not dict or set(doc)!={
        "format","profile","source","color","audio","finishing_intent",
        "notes","source_media_unchanged","display_referred_input",
        "output_transfer","output_audio","ocio_aces_certified",
        "cinema_dcp_certified"} or doc["format"]!=FORMAT or
        doc["profile"]!=PROFILE or doc["source_media_unchanged"] is not True or
        doc["display_referred_input"]!="srgb_8bit" or
        doc["output_transfer"]!="srgb_8bit" or
        doc["output_audio"]!="pcm16_48000_stereo" or
        doc["ocio_aces_certified"] is not False or
        doc["cinema_dcp_certified"] is not False or
        doc["finishing_intent"] not in LEVELS or
        type(doc["notes"]) is not str or len(doc["notes"])>900):
        raise ValueError("Finishing must preserve the actual native film profile")
    _source_digest(doc["source"])
    if binding is not None and doc["source"]!=binding:
        raise RuntimeError("Your film source changed since this finishing review")
    color=doc["color"]
    if type(color) is not dict or set(color)!=set(DEFAULT_COLOR):
        raise ValueError("A color adjustment is incomplete")
    for key,lo,hi in (("exposure",-2,2),("contrast",.65,1.55),
                      ("saturation",.4,1.6),("lift",-.12,.12),
                      ("warmth",-.2,.2)):
        _number(color[key],lo,hi,key)
    audio=doc["audio"]
    if type(audio) is not dict or set(audio)!=set(DEFAULT_AUDIO):
        raise ValueError("A sound mastering adjustment is incomplete")
    for key,lo,hi in (("target_lufs",-26,-12),
        ("peak_ceiling_dbfs",-6,-1),("fade_in_seconds",0,3),
        ("fade_out_seconds",0,3)):
        _number(audio[key],lo,hi,key)
    if len(_json(doc).encode("utf8"))>8000:
        raise ValueError("Finishing direction exceeds its source budget")
    return doc

def _version(db,pid,revision):
    row=db.execute("""SELECT document_json,document_sha256,source_sha256
       FROM g09d_finish_versions WHERE project_id=? AND revision=?""",
       (pid,revision)).fetchone()
    if row is None:raise KeyError("The earlier finishing version is not available")
    if _sha(row["document_json"].encode("utf8"))!=row["document_sha256"]:
        raise RuntimeError("A finishing revision no longer matches its audit record")
    data=json.loads(row["document_json"])
    if _source_digest(data["source"])!=row["source_sha256"]:
        raise RuntimeError("Finishing source identity was changed")
    return data,row["document_sha256"]

def _head(db,pid):
    row=db.execute("""SELECT draft_revision,approved_revision
        FROM g09d_finish_heads WHERE project_id=?""",(pid,)).fetchone()
    return (row["draft_revision"],row["approved_revision"]) if row else (0,0)

def _current(db,pid,binding):
    revision,approved=_head(db,pid)
    if revision==0:
        return 0,0,_default(binding),False
    doc,_=_version(db,pid,revision)
    stale=doc["source"]!=binding
    # Never automatically show a stale finishing plan as ready to approve.
    return revision,approved,doc,stale

def _public(db,pid,binding):
    rev,approved,doc,stale=_current(db,pid,binding)
    return {"format":FORMAT,"revision":rev,"approved_revision":approved,
        "approved_for_current_film":bool(
            approved and not stale and approved==rev),
        "current_film_source":binding,"source_changed":stale,
        "draft":doc,"levels":list(LEVELS),
        "working_delivery_only":True,
        "aces_ocio_or_dcp_claimed":False,
        "history":[{"revision":row["revision"],"created_at":row["created_at"]}
            for row in db.execute("""SELECT revision,created_at
                FROM g09d_finish_versions WHERE project_id=?
                ORDER BY revision DESC LIMIT 30""",(pid,))]}

def _save(db,pid,doc,revision,approved):
    if revision>=MAX_REVISIONS:
        raise RuntimeError("Finishing history reached its size limit")
    raw=_json(doc);sha=_sha(raw.encode("utf8"));now=_now()
    db.execute("""INSERT INTO g09d_finish_versions(
         project_id,revision,source_sha256,document_json,
         document_sha256,created_at)
         VALUES(?,?,?,?,?,?)""",(pid,revision+1,_source_digest(
            doc["source"]),raw,sha,now))
    db.execute("""INSERT INTO g09d_finish_heads(
         project_id,draft_revision,approved_revision,updated_at)
         VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET
         draft_revision=excluded.draft_revision,updated_at=excluded.updated_at""",
         (pid,revision+1,approved,now))
    return revision+1

class G09DFinishing:
    def __init__(self,studio,live=None,token=None):
        self.editor=G07Editor(studio,live,token)

    def _execute(self,pid,fn,mutate=False):
        def task(db,movie):
            _schema(db)
            binding=_binding(db,pid,self.editor)
            return fn(db,binding)
        return self.editor._execute(pid,task,mutate=mutate)

    def view(self,pid):
        return self._execute(pid,lambda db,src:_public(db,pid,src))

    def change(self,pid,expected,field,details):
        if (type(expected) is not int or not 0<=expected<=MAX_REVISIONS or
            type(field) is not str or type(details) is not dict):
            raise ValueError("Review your current finishing decisions")
        def modify(db,binding):
            rev,approved,doc,stale=_current(db,pid,binding)
            if rev!=expected:raise RuntimeError(
                "The finishing directions changed in another film window")
            # A source change creates a new draft bound to the NEW film,
            # retaining the old decision as an immutable historical revision.
            doc=_default(binding) if stale else copy.deepcopy(doc)
            if field=="color":
                if set(details)!=set(DEFAULT_COLOR):
                    raise ValueError("Choose complete picture finishing settings")
                doc["color"]=dict(details)
            elif field=="audio":
                if set(details)!=set(DEFAULT_AUDIO):
                    raise ValueError("Choose complete sound finishing settings")
                doc["audio"]=dict(details)
            elif field=="intent":
                if set(details)!={"intent","notes"}:
                    raise ValueError("Choose the review intent and your note")
                doc["finishing_intent"]=details["intent"]
                doc["notes"]=details["notes"]
            else:raise ValueError("This film finishing action is unavailable")
            _validate(doc,binding)
            _save(db,pid,doc,rev,approved)
            return _public(db,pid,binding)
        return self._execute(pid,modify,mutate=True)

    def approve(self,pid,expected):
        if type(expected) is not int or expected<=0:
            raise ValueError("Save a finishing decision before approval")
        def accept(db,binding):
            rev,approved,doc,stale=_current(db,pid,binding)
            if rev!=expected or stale:
                raise RuntimeError("The film changed; review the current finishing decisions")
            _validate(doc,binding)
            db.execute("""UPDATE g09d_finish_heads SET
                approved_revision=?,updated_at=? WHERE project_id=?""",
                (rev,_now(),pid))
            return _public(db,pid,binding)
        return self._execute(pid,accept,mutate=True)

    def restore(self,pid,expected,old):
        if type(old) is not int or old<=0 or (
                type(expected) is not int or expected<0):
            raise ValueError("Choose an earlier finishing version")
        def restore_tx(db,binding):
            rev,approved,doc,stale=_current(db,pid,binding)
            if rev!=expected:raise RuntimeError("Finishing changed in another window")
            old_doc,_=_version(db,pid,old)
            # Restoration never rebinds previous creative decisions onto a
            # different original Take or a different approved sound mix.
            _validate(old_doc,binding)
            _save(db,pid,old_doc,rev,approved)
            return _public(db,pid,binding)
        return self._execute(pid,restore_tx,mutate=True)

    @staticmethod
    def approved_source(db,pid,binding):
        _schema(db)
        rev,approved=_head(db,pid)
        if not approved:return None
        doc,digest=_version(db,pid,approved)
        if doc["source"]!=binding:return None
        _validate(doc,binding)
        return {"revision":approved,"sha256":digest,"finishing":doc}
