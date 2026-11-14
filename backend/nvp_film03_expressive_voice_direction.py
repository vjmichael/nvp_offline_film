"""FILM03: director-authored cinematic dialogue delivery, NOT a TTS generator.

A film voice is acting: emotion, arc, emphasis, pronunciation, breath,
pauses, volume, whisper/shout and characteristic ActorID voice continuity.
These are explicit, versioned source directions; strings masquerading as a
VoiceID or WAV existence cannot prove quality. The default film runtime
remains BLOCKED until a reviewed neural/expressive provider demonstrates
these controls on actual audio and receives separate director approval.

No eSpeak NG or low-expressivity engine is authorized by this module.
"""
from __future__ import annotations

from hashlib import sha256
import math
import re

from backend.nvp_film03_actor_identity_core import (
    ActorIdentityCore, canonical, digest, bounded,
)
from backend.nvp_film_index import FilmIndex, _id, _require_pid

FORMAT="nvp.film03.actor_expressive_dialogue_direction.v1"
EMOTIONS=frozenset({
    "neutral","happy","sad","angry","afraid","tender","uncertain",
    "excited","grieving","sarcastic","determined","reassuring",
})
DELIVERIES=frozenset({
    "natural","soft","whisper","shout","crying","laughing",
})
DIRECTION_KEYS=frozenset({
    "emotion","emotion_intensity","delivery","volume_db",
    "speaking_rate","breathiness","emphasis","pauses",
    "pronunciations","emotional_arc","director_intent",
})
REQUIRED_QUALITY=frozenset({
    "natural_contextual_inflection","emotion_and_emotional_arc",
    "word_and_phrase_emphasis","director_approved_pronunciation",
    "timed_pauses_and_breaths","soft_and_whisper_delivery",
    "shout_and_loudness_dynamics","consistent_actor_voice_identity",
    "revision_and_retake_reproducibility",
})
TOKEN=re.compile(r"[^\W_]+(?:['’-][^\W_]+)*",re.UNICODE)


def text_words(source_text):
    return TOKEN.findall(source_text)


def _finite(value,label,minimum,maximum):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise ValueError("Invalid bounded "+label)
    return float(value)


def _word_index(value,count,label):
    if type(value) is not int or not 0<=value<count:
        raise ValueError(label+" must address a real word in the exact screenplay")
    return value


def _event_rows(rows,fields,count,label,max_items):
    if type(rows) is not list or len(rows)>max_items:
        raise ValueError(label+" needs bounded word-indexed directions")
    normalized=[]
    seen=set()
    for entry in rows:
        if type(entry) is not dict or set(entry)!=fields:
            raise ValueError(label+" requires exact typed event fields")
        ix=_word_index(entry["word_index"],count,label)
        if ix in seen:
            raise ValueError("Ambiguous repeated "+label+" at same screenplay word")
        seen.add(ix)
        normalized.append(entry)
    return sorted(normalized,key=lambda x:x["word_index"])


def validate_directions(source_text,directions):
    if type(source_text) is not str or not 1<=len(source_text)<=1800:
        raise ValueError("Actual bounded original screenplay line required")
    words=text_words(source_text)
    if not 1<=len(words)<=240:
        raise ValueError("Original screenplay must contain bounded spoken words")
    if type(directions) is not dict or set(directions)!=DIRECTION_KEYS:
        raise ValueError("Director must supply the complete cinematic delivery schema")
    emotion=directions["emotion"]
    delivery=directions["delivery"]
    if emotion not in EMOTIONS or delivery not in DELIVERIES:
        raise ValueError("Unknown emotional/delivery film-performance instruction")
    normalized={
        "emotion":emotion,
        "emotion_intensity":_finite(directions["emotion_intensity"],
                                    "emotion intensity",0.0,1.0),
        "delivery":delivery,
        "volume_db":_finite(directions["volume_db"],"vocal dynamics dB",-24,6),
        "speaking_rate":_finite(directions["speaking_rate"],
                                "relative speaking rate",0.5,1.8),
        "breathiness":_finite(directions["breathiness"],"breathiness",0,1),
        "director_intent":bounded(directions["director_intent"],
                                  "cinematic director intent",max_length=2000),
    }
    emphasis=_event_rows(directions["emphasis"],
                         {"word_index","weight"},len(words),"emphasis",32)
    normalized["emphasis"]=[
        {"word_index":row["word_index"],
         "weight":_finite(row["weight"],"word stress weight",0.0,1.0)}
        for row in emphasis]
    pauses=_event_rows(directions["pauses"],
                       {"word_index","duration_ms","breath"},len(words),"pause",32)
    normalized["pauses"]=[
        {"word_index":row["word_index"],
         "duration_ms":(
             row["duration_ms"] if type(row["duration_ms"]) is int and
             0<=row["duration_ms"]<=3000 else
             _invalid_pause()),
         "breath":row["breath"] if type(row["breath"]) is bool else _invalid_breath()}
        for row in pauses]
    pronunciations=_event_rows(directions["pronunciations"],
                               {"word_index","spoken_as"},len(words),
                               "pronunciation",32)
    normalized["pronunciations"]=[
        {"word_index":row["word_index"],
         "original_word":words[row["word_index"]],
         "spoken_as":bounded(row["spoken_as"],"approved pronunciation",
                             max_length=120)}
        for row in pronunciations]
    arc=_event_rows(directions["emotional_arc"],
                    {"word_index","emotion","intensity"},len(words),
                    "emotional arc",24)
    normalized["emotional_arc"]=[]
    for row in arc:
        if row["emotion"] not in EMOTIONS:
            raise ValueError("Unknown word-level emotional arc")
        normalized["emotional_arc"].append({
            "word_index":row["word_index"],"emotion":row["emotion"],
            "intensity":_finite(row["intensity"],"word emotion intensity",0,1),
        })
    # Also bind directions to the exact authentic script words; a model
    # cannot silently alter the line when adding emotional metadata.
    normalized["original_word_count"]=len(words)
    normalized["original_word_sequence_sha256"]=digest(words)
    return normalized


def _invalid_pause():
    raise ValueError("Pause duration must be 0..3000 integer milliseconds")


def _invalid_breath():
    raise ValueError("Breath cue must be boolean")


class FilmActorVoiceDirection:
    def __init__(self,index:FilmIndex,*,verify_creator_action):
        if not isinstance(index,FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Native FilmIndex + creator-only source approval required")
        self.index=index
        self._auth=verify_creator_action
        self.actors=ActorIdentityCore(index,verify_creator_action=lambda *_:False)

    @staticmethod
    def identity(pid,plan):
        # Stable per script-performance and ActorID across revised dialogues;
        # FilmIndex revisions preserve all older director intent.
        key=(pid+"|"+plan["actor_id"]+"|"+plan["source_performance_id"])
        return "ActorVoiceDirection_"+sha256(key.encode("utf8")).hexdigest()[:40]

    def publish(self,pid,source_route,*,profile_revision,directions,
                expected_revision,director_note,creator_event):
        _require_pid(pid)
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Source film voice direction revision must be explicit")
        plan=self.actors.prepare_generated_voice(
            pid,source_route,profile_revision=profile_revision)
        normalized=validate_directions(plan["exact_script_text"],directions)
        note=bounded(director_note,"director approval comparison note",
                     max_length=1800)
        id=self.identity(pid,plan)
        source={
            "format":FORMAT,"actor_id":plan["actor_id"],
            "voice_id":plan["voice_id"],
            "voice_type_id":plan["voice_type"]["voice_type_id"],
            "profile_revision":profile_revision,
            "profile_sha256":plan["actor_identity_profile_sha256"],
            "voice_cast_revision":plan["voice_cast_revision"],
            "voice_reference_sha256":plan["voice_reference_sha256"],
            "source_take_id":plan["source_take_id"],
            "source_take_sha256":plan["source_take_sha256"],
            "script_line_id":plan["script_line_id"],
            "script_document_sha256":plan["script_document_sha256"],
            "source_selection_id":plan["source_selection_id"],
            "source_selection_revision":plan["source_selection_revision"],
            "source_selection_sha256":plan["source_selection_document_sha256"],
            "performance_id":plan["source_performance_id"],
            "selected_words_sha256":normalized["original_word_sequence_sha256"],
            "source_generation_contract_sha256":plan["contract_sha256"],
            "directions":normalized,
            "directions_sha256":digest(normalized),
            "director_note":note,
            "voice_generation_executed":False,
            "film_speech_worker_qualified":False,
            "director_audio_approval":False,
            "original_dialogue_take_modified":False,
        }
        scope={
            "operation":"film03_publish_cinematic_actor_voice_directions",
            "project_id":pid,"actor_id":plan["actor_id"],
            "voice_id":plan["voice_id"],
            "source_take_sha256":plan["source_take_sha256"],
            "profile_sha256":plan["actor_identity_profile_sha256"],
            "script_line_id":plan["script_line_id"],
            "direction_sha256":source["directions_sha256"],
            "expected_direction_revision":expected_revision,
            "director_note":note,
        }
        if not self._auth(creator_event,scope):
            raise PermissionError("No genuine director consent for exact cinematic delivery")
        if self.actors.prepare_generated_voice(
                pid,source_route,profile_revision=profile_revision)!=plan:
            raise PermissionError("VoiceID, character or screenplay changed before publication")
        def guard(db):
            current=db.execute(
                """SELECT document_sha256 FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=? ORDER BY profile_revision DESC LIMIT 1""",
                (pid,plan["actor_id"])).fetchone()
            if not current or current[0]!=plan["actor_identity_profile_sha256"]:
                raise PermissionError("Character identity changed before cinematic direction commit")
        saved=self.index.register_revision(pid,id,"performance",source,
            expected_revision=expected_revision,precommit_guard=guard)
        return {
            "format":FORMAT,"project_id":pid,"actor_id":plan["actor_id"],
            "direction_id":id,"direction_revision":saved["revision"],
            "direction_document_sha256":saved["document_sha256"],
            "voice_id":plan["voice_id"],"source_take_sha256":plan["source_take_sha256"],
            "provider_ran":False,"film_quality_approved":False,
            "previous_direction_revisions_preserved":True,
        }


def cinematic_engine_readiness(engine_manifest):
    """Evidence insufficiency always blocks film generation.

    A claimed tag/control from an API or model card is not a measurement
    of whether the actual recording contains whispering, natural acting
    or matching VoiceID across different lines. Native execution remains
    closed until independent benchmark and director review are implemented.
    """
    return {
        "format":"nvp.film03.cinematic_engine_readiness.v1",
        "cinematic_generation_enabled":False,
        "required_real_audio_capabilities":sorted(REQUIRED_QUALITY),
        "provider_metadata_is_not_audio_evidence":True,
        "must_verify_real_emotional_pronunciation_and_voice_continuity":True,
        "unapproved_engine_cannot_generate_filmmaking_dialogue":True,
        "espeak_ng_film_voice_qualified":False,
        "neural_engine_must_be_reviewed_and_measured":True,
        "reason":"No reviewed expressive film voice producer has passing actor and human-listening evidence",
    }
