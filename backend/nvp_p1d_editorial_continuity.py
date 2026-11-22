"""P1-D: independent director continuity ledger over an immutable active cut.

A cue references only an already validated segment in a FilmIndex edit.
It does NOT copy source Take frames, mutate camera/shot layers, invent blends,
claim lip sync, or make a render/export permission. Editing the ledger always
creates a new version under the original source SHA, never a changed Take.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_temporal_ledger import _int

FORMAT="nvp.p1d.director_edit_continuity.v1"
MAX_CUES=500
STATES=frozenset(("accepted","needs_review"))
SOUND=frozenset(("original_scene","review_actor_dialogue"))
KEYS=frozenset(("segment_id","continuity","audio_policy","note"))


def _canon(doc):
    return json.dumps(doc,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _digest(doc):
    return hashlib.sha256(_canon(doc)).hexdigest()


class NativeEditorialContinuity:
    def __init__(self,assembly:SlateSequenceAssembly,*,verify_director_action):
        if not isinstance(assembly,SlateSequenceAssembly) or not callable(
                verify_director_action):
            raise TypeError("Native committed slate and director authority required")
        self.assembly=assembly
        self.index=assembly.index
        self.approve=verify_director_action

    def _source(self,project_id,edit_id,revision):
        original=self.assembly.open_edit(project_id,edit_id,revision)
        data=original["data"]
        if (original["kind"]!="edit" or data.get("render_approved") is not False
                or data.get("retimed") is not False or
                data.get("source_performance_modified") is not False):
            raise RuntimeError("Only original-time committed source edits qualify")
        return original

    def publish(self,project_id,continuity_id,*,edit_id,edit_revision,
                cues,creator_event,expected_revision=0):
        _require_pid(project_id)
        _id(continuity_id,"director editorial continuity identity")
        _id(edit_id,"canonical committed editorial source")
        _int(expected_revision,"expected director revision")
        original=self._source(project_id,edit_id,edit_revision)
        rows=original["data"]["segments"]
        if type(cues) is not list or len(cues)!=len(rows) or not 1<=len(cues)<=MAX_CUES:
            raise ValueError("Every committed source segment needs one director cue")
        by_id={}
        for cue in cues:
            if type(cue) is not dict or set(cue)!=KEYS:
                raise ValueError("Director cue needs exact segment/continuity/audio/note fields")
            sid=_id(cue["segment_id"],"authored source segment")
            if sid in by_id:
                raise ValueError("Duplicate source segment continuity cue")
            if (cue["continuity"] not in STATES or cue["audio_policy"] not in SOUND
                    or type(cue["note"]) is not str or len(cue["note"])>512
                    or any(ord(c)<32 and c not in "\t\n" for c in cue["note"])):
                raise ValueError("Unbounded or unsupported director editorial intent")
            by_id[sid]=dict(cue)
        if set(by_id)!={s["segment_id"] for s in rows}:
            raise ValueError("Director review must reference each exact selected segment")
        ordered=[by_id[seg["segment_id"]] for seg in rows]
        if expected_revision:
            old=self.open(project_id,continuity_id,expected_revision)
            if (old["data"]["edit_id"]!=edit_id or
                old["data"]["edit_revision"]!=edit_revision or
                old["data"]["edit_document_sha256"]!=original["document_sha256"]):
                raise RuntimeError("Changing the committed edit requires a distinct continuity identity")
        state="READY_FOR_SEPARATE_EXPORT_AUTHORIZATION" if all(
            c["continuity"]=="accepted" and c["audio_policy"]=="original_scene"
            for c in ordered) else "DIRECTOR_REVIEW_REQUIRED"
        document={"format":FORMAT,"edit_id":edit_id,"edit_revision":edit_revision,
                  "edit_document_sha256":original["document_sha256"],
                  "ordered_source_segments_sha256":original["data"]["ordered_segment_sha256"],
                  "cues":ordered,"cues_sha256":_digest(ordered),
                  "duration_tick":original["data"]["duration_tick"],
                  "review_status":state,"render_approved":False,
                  "source_take_modified":False,"automatic_crossfade":False}
        intent={"operation":"nvp.p1d.commit_director_continuity.v1",
                "project_id":project_id,"continuity_id":continuity_id,
                "expected_revision":expected_revision,
                "edit_document_sha256":original["document_sha256"],
                "cues_sha256":document["cues_sha256"],
                "review_status":state,"render_approved":False}
        if self.approve(creator_event,dict(intent)) is not True:
            raise PermissionError("Director refused exact editorial continuity decision")
        # Editor source revisions cannot be swapped while the native host
        # prompt was open. FilmIndex takes the same writer lease as this guard.
        def guard(db):
            rec=self.index._read_revision(db,project_id,edit_id,edit_revision)
            if rec is None or rec["document_sha"]!=original["document_sha256"]:
                raise RuntimeError("Committed edit changed before continuity publication")
        return self.index.register_revision(
            project_id,continuity_id,"presentation",document,
            expected_revision=expected_revision,
            dependencies=[{"object_id":edit_id,"revision":edit_revision,
                           "role":"presentation"}],
            precommit_guard=guard)

    def open(self,project_id,continuity_id,revision):
        record=self.index.read_revision(project_id,continuity_id,revision)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
            doc.get("render_approved") is not False or
            doc.get("source_take_modified") is not False or
            doc.get("automatic_crossfade") is not False):
            raise RuntimeError("Not a verified P1-D source-only editorial review")
        edited=self._source(project_id,doc["edit_id"],doc["edit_revision"])
        ordered=edited["data"]["segments"]
        if (doc["edit_document_sha256"]!=edited["document_sha256"] or
            doc["ordered_source_segments_sha256"]!=edited["data"]["ordered_segment_sha256"]
            or len(doc["cues"])!=len(ordered) or
            [v["segment_id"] for v in doc["cues"]]!=
                [v["segment_id"] for v in ordered] or
            _digest(doc["cues"])!=doc["cues_sha256"] or
            doc["duration_tick"]!=edited["data"]["duration_tick"]):
            raise RuntimeError("Original source edit/continuity ledger was changed")
        current="READY_FOR_SEPARATE_EXPORT_AUTHORIZATION" if all(
            c["continuity"]=="accepted" and c["audio_policy"]=="original_scene"
            for c in doc["cues"]) else "DIRECTOR_REVIEW_REQUIRED"
        if current!=doc["review_status"]:
            raise RuntimeError("Original director review status was altered")
        return record

    def at(self,project_id,continuity_id,revision,tick):
        rec=self.open(project_id,continuity_id,revision)
        doc=rec["data"]
        _int(tick,"editorial output Film Time",maximum=doc["duration_tick"]-1)
        edit=self._source(project_id,doc["edit_id"],doc["edit_revision"])
        for original,cue in zip(edit["data"]["segments"],doc["cues"]):
            if original["timeline_start_tick"]<=tick<original["timeline_end_tick"]:
                return {"format":FORMAT,"editorial_sha256":rec["document_sha256"],
                        "source_edit_sha256":edit["document_sha256"],
                        "director_cue":cue,"source_take_id":original["source_take_id"],
                        "source_take_sha256":original["source_take_document_sha256"],
                        "source_shot_id":original["source_shot_id"],
                        "source_shot_revision":original["source_shot_revision"],
                        "source_shot_sha256":original["source_shot_document_sha256"],
                        "source_tick":original["source_in_tick"]+
                            tick-original["timeline_start_tick"],
                        "output_tick":tick,
                        "render_approved":False,"retimed":False}
        raise RuntimeError("Continuity ledger has an uncovered source cut")
