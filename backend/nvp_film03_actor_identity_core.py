"""FILM03-05: ActorID is the authoritative nucleus of ALL character identity.

The same canonical StoryBible ActorID owns the appearance, behavior, gait,
signature motions, VoiceType, VoiceID, voice synthesis settings, linked
3D/source assets and scene dialogue. This is a versioned production-bible
record, NOT a parallel character identity.

The AI may propose a rendition of this actor, but cannot substitute a voice
type, voice engine selector, actor, script line or gait by rewriting prompt
text. Future TTS/animation workers must receive a source-bound contract
from NVP and return independently verified output receipts. Nothing in this
module executes a model or claims acoustic speaker similarity.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_story_bible import StoryBible
from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity

PROFILE_FORMAT = "nvp.film03.actor_identity_profile.v1"
AI_CONTRACT_FORMAT = "nvp.film03.actorid_locked_voice_generation_contract.v1"
MAX_TEXT = 350
MAX_NOTES = 1500
HEX_ACTOR = re.compile(r"[a-f0-9]{32}\Z")
VOICE_FIELDS = frozenset({
    "voice_type_id", "register", "pitch", "timbre", "accent",
    "cadence", "articulation", "signature_quirks",
})
APPEARANCE_FIELDS = frozenset({
    "silhouette", "palette", "surface", "signature_marks", "visual_expression",
})
BEHAVIOR_FIELDS = frozenset({
    "personality_traits", "habits", "emotional_rules", "speech_style",
})
MOVEMENT_FIELDS = frozenset({
    "gait", "posture", "signature_gestures", "movement_peculiarities",
})
# A descriptive off-gait is not an executable locomotion instruction.
# NVP requires a reviewed, closed vocabulary so no LLM guesses motion.
GAIT_PRESETS = frozenset({"steady","lopsided_roll","uneven_step","unconfigured"})
GENERATION_FIELDS = frozenset({
    "engine_id", "model_id", "model_revision", "engine_voice_id",
    "seed", "rate", "pitch_shift", "stability", "language",
})
PROFILE_FIELDS = frozenset({
    "appearance", "behavior", "movement", "voice_type",
    "voice_generation", "director_notes",
})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def bounded(value, field, *, max_length=MAX_TEXT, required=True):
    if type(value) is not str or len(value)>max_length or "\x00" in value:
        raise ValueError("Invalid actor profile " + field)
    if required and not value.strip():
        raise ValueError("Missing required actor profile " + field)
    return value.strip()


def section(value, fields, label):
    if type(value) is not dict or set(value)!=fields:
        raise ValueError("Actor " + label + " must have its exact typed fields")
    result={}
    for field in sorted(fields):
        result[field]=bounded(value[field], label+"."+field,
                              required=field not in {"signature_marks","visual_expression",
                                                    "habits","emotional_rules","speech_style",
                                                    "signature_gestures","movement_peculiarities",
                                                    "accent","signature_quirks"})
    return result


def checked_profile(profile):
    """Reject arbitrary prompts/provider URLs and unbounded hidden persona data."""
    if type(profile) is not dict or set(profile)!=PROFILE_FIELDS:
        raise ValueError("Actor identity profile must have exactly six typed sections")
    appearance=section(profile["appearance"],APPEARANCE_FIELDS,"appearance")
    behavior=section(profile["behavior"],BEHAVIOR_FIELDS,"behavior")
    motion=profile["movement"]
    if type(motion) is not dict:
        raise ValueError("Expected exact ActorID motion source")
    if set(motion) == MOVEMENT_FIELDS:
        # Old (FILM03-05) profiles are readable without pretending their
        # prose text already specifies safe executable animation.
        preset="unconfigured"
    elif set(motion) == MOVEMENT_FIELDS | {"gait_preset"}:
        preset=motion["gait_preset"]
        if type(preset) is not str or preset not in GAIT_PRESETS:
            raise ValueError("Unsupported actor gait preset")
    else:
        raise ValueError("Motion contains extra or missing identity fields")
    movement=section({k:motion[k] for k in MOVEMENT_FIELDS},
                     MOVEMENT_FIELDS,"movement")
    movement["gait_preset"]=preset
    voice_type=section(profile["voice_type"],VOICE_FIELDS,"voice_type")
    _id(voice_type["voice_type_id"],"ActorID's stable VoiceType identifier")
    if not voice_type["voice_type_id"].startswith("VoiceType_"):
        raise ValueError("VoiceType must be explicit and versioned, not a guessed sound name")
    settings=profile["voice_generation"]
    if type(settings) is not dict or set(settings)!=GENERATION_FIELDS:
        raise ValueError("Voice generation profile must have exact typed engine settings")
    gen={}
    for name in ("engine_id","model_id","model_revision","engine_voice_id"):
        gen[name]=_id(settings[name],"authored "+name)
    gen["language"]=bounded(settings["language"],"generation.language",max_length=48)
    seed=settings["seed"]
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Actor voice seed must be stable unsigned 32-bit integer")
    gen["seed"]=seed
    for name,minimum,maximum in (
        ("rate",0.5,2.0),("pitch_shift",-12.0,12.0),
        ("stability",0.0,1.0),
    ):
        value=settings[name]
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError("Invalid numeric actor voice generation setting")
        if not minimum<=value<=maximum:
            raise ValueError("Voice setting outside reviewed production bounds")
        gen[name]=float(value)
    notes=bounded(profile["director_notes"],"director notes",
                  max_length=MAX_NOTES,required=False)
    return {
        "appearance":appearance,"behavior":behavior,"movement":movement,
        "voice_type":voice_type,"voice_generation":gen,
        "director_notes":notes,
    }


class ActorIdentityCore:
    """Canonically scoped, immutable-by-revision profile inside NVP's StoryBible."""

    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index,FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Actor identity needs actual FilmIndex and native director authority")
        self.index=index
        self.studio=index.studio
        self.bible=StoryBible(self.studio)
        self.voices=ProductionBibleVoiceIdentity(
            index, verify_creator_action=lambda *_:False)
        self._approve=verify_creator_action
        with self.studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS nvp_bible_actor_identity_profiles (
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              actor_id TEXT NOT NULL REFERENCES bible_entities(id),
              profile_revision INTEGER NOT NULL CHECK(profile_revision>0),
              document_sha256 TEXT NOT NULL,
              profile_json TEXT NOT NULL,
              voice_id TEXT,
              voice_cast_revision INTEGER,
              voice_reference_sha256 TEXT,
              source_bible_revision INTEGER NOT NULL,
              director_note TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(project_id,actor_id,profile_revision)
            );
            CREATE INDEX IF NOT EXISTS nvp_bible_actor_profile_latest
              ON nvp_bible_actor_identity_profiles(project_id,actor_id,profile_revision);
            """)

    def _actor(self,pid,actor_id):
        _require_pid(pid)
        if type(actor_id) is not str or not HEX_ACTOR.fullmatch(actor_id):
            raise ValueError("Expected canonical 32-hex StoryBible ActorID")
        actor=self.bible.get_entity(pid,actor_id)
        if actor["kind"]!="character" or actor["id"]!=actor_id:
            raise PermissionError("Only canonical cast characters own actor identity profiles")
        return actor

    def current(self,pid,actor_id):
        actor=self._actor(pid,actor_id)
        with self.studio._connection() as db:
            history=[dict(row) for row in db.execute(
                """SELECT * FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=?
                   ORDER BY profile_revision""",(pid,actor_id))]
        for row in history:
            row["profile"]=json.loads(row.pop("profile_json"))
        current=history[-1] if history else None
        if current is not None and digest(current["profile"])!=current["document_sha256"]:
            raise RuntimeError("Durable actor profile SHA does not match original profile")
        cast=self.voices.current(pid,actor_id)["current"]
        return {
            "format":PROFILE_FORMAT,"project_id":pid,
            "actor_id":actor_id,"actor_name":actor["name"],
            "current":current,"profile_history":history,
            "current_voice_id":cast["voice_id"] if cast else None,
            "current_voice_cast_revision":cast["cast_revision"] if cast else None,
            "current_voice_reference_sha256":
                cast["reference_audio_sha256"] if cast else None,
            "profile_voice_cast_stale": bool(current and (
                current["voice_id"] != (cast["voice_id"] if cast else None) or
                current["voice_cast_revision"] !=
                    (cast["cast_revision"] if cast else None) or
                current["voice_reference_sha256"] !=
                    (cast["reference_audio_sha256"] if cast else None))),
            "identity_is_story_bible_character_id":True,
            "no_generated_voice_or_motion_claim":True,
        }

    def publish(self,pid,actor_id,profile,*,expected_profile_revision,
                expected_bible_revision,director_note,creator_event):
        actor=self._actor(pid,actor_id)
        if (type(expected_profile_revision) is not int or
                expected_profile_revision<0 or
                type(expected_bible_revision) is not int or
                actor["revision"]!=expected_bible_revision):
            raise RuntimeError("ActorID or profile revision changed; refresh before publishing")
        normalized=checked_profile(profile)
        note=bounded(director_note,"director approval note",
                     max_length=MAX_NOTES)
        profile_sha=digest(normalized)
        voice=self.voices.current(pid,actor_id)["current"]
        voice_id=voice["voice_id"] if voice else None
        cast_revision=voice["cast_revision"] if voice else None
        voice_sha=voice["reference_audio_sha256"] if voice else None
        exact={
            "operation":"film03_publish_actor_identity_profile",
            "project_id":pid,"actor_id":actor_id,
            "expected_profile_revision":expected_profile_revision,
            "expected_bible_revision":expected_bible_revision,
            "profile_sha256":profile_sha,
            "voice_id":voice_id,
            "voice_cast_revision":cast_revision,
            "voice_reference_sha256":voice_sha,
            "director_note":note,
        }
        if not self._approve(creator_event,exact):
            raise PermissionError("No trusted director consent for exact ActorID identity profile")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            refreshed=db.execute(
                "SELECT kind,revision FROM bible_entities WHERE project_id=? AND id=?",
                (pid,actor_id)).fetchone()
            if (not refreshed or refreshed["kind"]!="character" or
                    refreshed["revision"]!=expected_bible_revision):
                raise RuntimeError("Production Bible ActorID changed during identity approval")
            previous=db.execute(
                """SELECT profile_revision,profile_json,voice_id
                   FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=? ORDER BY profile_revision DESC LIMIT 1""",
                (pid,actor_id)).fetchone()
            head=previous["profile_revision"] if previous else 0
            if head!=expected_profile_revision:
                raise RuntimeError("ActorID profile revision conflict; earlier profile is intact")
            last_cast=db.execute(
                """SELECT voice_id,cast_revision,reference_audio_sha256
                   FROM nvp_bible_voice_casts WHERE project_id=? AND actor_id=?
                   ORDER BY cast_revision DESC LIMIT 1""",
                (pid,actor_id)).fetchone()
            if ((last_cast["voice_id"] if last_cast else None)!=voice_id or
                    (last_cast["cast_revision"] if last_cast else None)!=cast_revision or
                    (last_cast["reference_audio_sha256"] if last_cast else None)!=voice_sha):
                raise RuntimeError("Approved ActorID VoiceID changed during profile publication")
            if previous and previous["voice_id"]!=voice_id:
                old_voice=json.loads(previous["profile_json"])["voice_generation"]
                new_voice=normalized["voice_generation"]
                if all(old_voice[k]==new_voice[k] for k in (
                        "engine_id","model_id","model_revision",
                        "engine_voice_id")):
                    raise PermissionError(
                        "New ActorID VoiceID must use a different generator voice selector; old timbre cannot be silently relabeled")
            # A generic voice *type* may be shared (e.g. low and resonant),
            # but the actual engine-specific VOICE SELECTOR must never be
            # reused as two different characters' approved identity.
            selector=normalized["voice_generation"]
            others=db.execute(
                """SELECT p.actor_id,p.profile_json
                   FROM nvp_bible_actor_identity_profiles p
                  WHERE p.project_id=? AND p.actor_id<>?
                    AND p.profile_revision=(
                      SELECT MAX(q.profile_revision)
                        FROM nvp_bible_actor_identity_profiles q
                       WHERE q.project_id=p.project_id
                         AND q.actor_id=p.actor_id)""",
                (pid,actor_id)).fetchall()
            for other in others:
                prior=json.loads(other["profile_json"])["voice_generation"]
                if all(prior[k]==selector[k] for k in (
                        "engine_id","model_id","model_revision",
                        "engine_voice_id")):
                    raise PermissionError(
                        "Generated voice engine selector already belongs to another ActorID")
            db.execute(
                """INSERT INTO nvp_bible_actor_identity_profiles
                  (project_id,actor_id,profile_revision,document_sha256,
                   profile_json,voice_id,voice_cast_revision,
                   voice_reference_sha256,source_bible_revision,director_note)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (pid,actor_id,head+1,profile_sha,canonical(normalized).decode("utf8"),
                 voice_id,cast_revision,voice_sha,expected_bible_revision,note))
        return self.current(pid,actor_id)

    def prepare_generated_voice(self,pid,source_route,*,profile_revision):
        """Immutable source-derived TTS INPUT only; no execution permission.

        The provider, model revision, provider voice selector, VoiceType,
        seed, rate and pronunciation traits come ONLY from the director-
        approved ActorID profile. AI may not supply replacements in this
        request. Actual TTS worker results require later independent,
        host-supervised source/provenance verification and human audition.
        """
        if type(source_route) is not dict or "actor_id" not in source_route:
            raise ValueError("One fully specified source dialogue route is required")
        actor_id=source_route["actor_id"]
        self._actor(pid,actor_id)
        current=self.current(pid,actor_id)
        selected=current["current"]
        if selected is None or selected["profile_revision"]!=profile_revision:
            raise PermissionError("ActorID profile changed or is not approved")
        cast=self.voices.current(pid,actor_id)["current"]
        if (cast is None or selected["voice_id"]!=cast["voice_id"] or
                selected["voice_cast_revision"]!=cast["cast_revision"] or
                selected["voice_reference_sha256"]!=cast["reference_audio_sha256"]):
            raise PermissionError("ActorID VoiceID or VoiceType has stale casting provenance")
        from backend.nvp_film03_dialogue_manager import ActorDialogueManager
        route=ActorDialogueManager(self.index).route(pid,source_route)
        if route["actor_id"]!=actor_id or route["canonical_voice_id"]!=cast["voice_id"]:
            raise PermissionError("AI requested another actor's voice identity")
        if route["original_recorded_voice"] is not None:
            raise PermissionError("This delivery already has recorded source audio; do not synthesize over it")
        profile=selected["profile"]
        packet={
            "format":AI_CONTRACT_FORMAT,"project_id":pid,
            "actor_id":actor_id,
            "actor_identity_profile_revision":profile_revision,
            "actor_identity_profile_sha256":selected["document_sha256"],
            "voice_id":cast["voice_id"],
            "voice_cast_revision":cast["cast_revision"],
            "voice_reference_sha256":cast["reference_audio_sha256"],
            "voice_type":profile["voice_type"],
            "generation_settings":profile["voice_generation"],
            "behavior_speech_style":profile["behavior"]["speech_style"],
            "movement_signature":profile["movement"],
            "script_line_id":route["script_line_id"],
            "exact_script_text":route["exact_director_selected_text"],
            "script_document_sha256":route["script_document_sha256"],
            "source_take_id":route["source_take_id"],
            "source_take_sha256":route["source_take_sha256"],
            "source_selection_id":route["selection_id"],
            "source_selection_revision":route["selection_revision"],
            "source_selection_document_sha256":route["selection_document_sha256"],
            "source_performance_id":route["performance_id"],
            "film_time_tick":route["film_time_tick"],
            "audio_generation_executed":False,
            "tts_worker_authorized":False,
            "untrusted_model_may_not_change_actor_or_voice_type":True,
            "audio_output_must_be_revalidated_before_take_approval":True,
        }
        return {**packet,"contract_sha256":digest(packet)}
