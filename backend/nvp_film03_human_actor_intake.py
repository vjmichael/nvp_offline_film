"""FILM03-09B: real voice-actor / director guide intake and scoped consent.

A REAL, already-captured first-party 48 kHz PCM source may be enrolled as a
candidate for one exact StoryBible ActorID and screenplay line. The human
performer is a contributor distinct from ActorID and VoiceID. Voice/film
usage, conversion, cloning, training, and distribution are SEPARATE consent
scopes. A trusted native performer-attestation action and an independently
approved director action are required; neither implies legal sufficiency.

No recording device, model, ASR, forced aligner, film approval or cloning
worker is launched here. Audio measurements cannot prove speech/content.
"""
from __future__ import annotations

from hashlib import sha256
from math import sqrt, log10

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_film03_actor_identity_core import ActorIdentityCore, bounded, digest
from backend.nvp_film03_dialogue_manager import ActorDialogueManager
from backend.nvp_film03_voice_conversion_intent import verified_guide_signal
from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid

FORMAT = "nvp.film03.original_human_voice_actor_session.v1"
RIGHTS = frozenset({
    "recorded_line_use", "voice_conversion", "voice_cloning",
    "model_training", "distribution",
})
ROLE = frozenset({"voice_actor", "director_guide"})
MIN_SIGNAL_MAGNITUDE = 512
MAX_CLIPPED_FRACTION = 0.02


def checked_rights(rights):
    """Consent to use a line never implies training or cloning rights."""
    if type(rights) is not dict or set(rights) != RIGHTS:
        raise ValueError("Each human-performance rights scope must be explicit")
    out = {}
    for name in sorted(RIGHTS):
        row = rights[name]
        if type(row) is not dict or set(row) != {"consented", "evidence_sha256"}:
            raise ValueError("Human recording rights require scoped evidence")
        approved = row["consented"]
        evidence = row["evidence_sha256"]
        if type(approved) is not bool or (
            approved and evidence is None
        ) or (not approved and evidence is not None):
            raise ValueError("Consent and evidence cannot contradict each other")
        if approved:
            _sha(evidence)
        out[name] = {"consented": approved, "evidence_sha256": evidence}
    if not out["recorded_line_use"]["consented"]:
        raise PermissionError("No human permission to use this recorded dialogue line")
    return out


def original_signal_measurement(index, pid, audio_id, audio_revision):
    """Reopen original 48 k PCM, reject silence/clipping; NOT speech recognition.

    Peak/RMS and noisy-sample count are about actual samples, not emotion or
    intelligible language. Memory stays under 1 MiB per source chunk.
    """
    description = verified_guide_signal(index, pid, audio_id, audio_revision)
    raw = RecordedSoundSources(index).describe(pid, audio_id, audio_revision)["data"]
    total = 0
    sum_sq = 0
    peak = 0
    nonquiet = 0
    clipped = 0
    for part in raw["chunks"]:
        block = index.get_blob(pid, part["blob_sha256"])
        if len(block) != part["byte_count"] or len(block) % 2:
            raise RuntimeError("Recorded performer PCM bytes changed")
        for pos in range(0, len(block), 2):
            sample = int.from_bytes(block[pos:pos + 2], "little", signed=True)
            mag = abs(sample)
            peak = max(peak, mag)
            sum_sq += sample * sample
            nonquiet += mag >= MIN_SIGNAL_MAGNITUDE
            clipped += mag >= 32700
            total += 1
    if total != raw["sample_count"]:
        raise RuntimeError("Original performer recording has incomplete samples")
    if peak < MIN_SIGNAL_MAGNITUDE or nonquiet * 1000 < total * 5:
        raise ValueError("No sufficient recorded acoustic signal for a voice audition")
    if clipped / total > MAX_CLIPPED_FRACTION:
        raise ValueError("Original recording is excessively clipped; request a clean retake")
    return {
        **description,
        "peak_dbfs": round(20 * log10(max(peak / 32768, 1e-12)), 3),
        "rms_dbfs": round(20 * log10(max(sqrt(sum_sq / total) / 32768, 1e-12)), 3),
        "nonquiet_sample_fraction": round(nonquiet / total, 6),
        "clipped_sample_fraction": round(clipped / total, 6),
        "speech_transcript_verified": False,
        "actor_voice_similarity_verified": False,
        "emotional_performance_verified": False,
        "human_listening_pending": True,
    }


class VoiceActorPerformanceIntake:
    """Immutable source-session intake, separate performer + director consent."""

    def __init__(self, index: FilmIndex, *, verify_performer_consent,
                 verify_creator_action):
        if (not isinstance(index, FilmIndex) or
                not callable(verify_performer_consent) or
                not callable(verify_creator_action)):
            raise TypeError("Native FilmIndex and two separate trusted approvals required")
        self.index = index
        self._performer = verify_performer_consent
        self._director = verify_creator_action
        self.actors = ActorIdentityCore(index, verify_creator_action=lambda *_: False)
        self.voices = ProductionBibleVoiceIdentity(
            index, verify_creator_action=lambda *_: False)
        with self.index.studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS nvp_film03_human_voice_audio_custody (
              project_id TEXT NOT NULL,
              audio_id TEXT NOT NULL,
              audio_revision INTEGER NOT NULL CHECK(audio_revision>0),
              pcm_sha256 TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              performer_id TEXT NOT NULL,
              session_id TEXT NOT NULL,
              PRIMARY KEY(project_id,audio_id,audio_revision),
              UNIQUE(project_id,pcm_sha256),
              UNIQUE(project_id,session_id)
            );
            """)

    def plan(self, pid, route_request, *, profile_revision, audio_id,
             audio_revision, performer_id, performer_role, credit_line, rights):
        _require_pid(pid)
        _id(audio_id, "original human microphone source")
        _id(performer_id, "human performer contribution ID")
        if performer_role not in ROLE:
            raise ValueError("Only human actor or director guide can originate this PCM")
        credit = bounded(credit_line, "performer chosen credit", max_length=160)
        consent = checked_rights(rights)
        route = ActorDialogueManager(self.index).route(pid, route_request)
        current = self.actors.current(pid, route["actor_id"])
        selected = current["current"]
        voice = self.voices.current(pid, route["actor_id"])["current"]
        if (selected is None or selected["profile_revision"] != profile_revision
                or current["profile_voice_cast_stale"]
                or voice is None or voice["voice_id"] != route["canonical_voice_id"]):
            raise PermissionError("ActorID profile or approved VoiceID changed")
        measured = original_signal_measurement(
            self.index, pid, audio_id, audio_revision)
        script = self.index.read_revision(pid, route["script_id"], route["script_revision"])
        if script["document_sha256"] != route["script_document_sha256"]:
            raise PermissionError("Original script provenance changed")
        payload = {
            "format": FORMAT, "project_id": pid,
            "actor_id": route["actor_id"], "voice_id": voice["voice_id"],
            "voice_cast_revision": voice["cast_revision"],
            "voice_reference_sha256": voice["reference_audio_sha256"],
            "actor_profile_revision": profile_revision,
            "actor_profile_sha256": selected["document_sha256"],
            "script_line_id": route["script_line_id"],
            "script_text_sha256": sha256(
                route["exact_director_selected_text"].encode("utf8")).hexdigest(),
            "script_id": route["script_id"],
            "script_revision": route["script_revision"],
            "script_document_sha256": route["script_document_sha256"],
            "script_screenplay_revision": script["data"]["screenplay_revision"],
            "script_screenplay_sha256": script["data"]["screenplay_sha256"],
            "source_selection_id": route["selection_id"],
            "source_selection_revision": route["selection_revision"],
            "source_selection_sha256": route["selection_document_sha256"],
            "selected_source_performance_id": route["performance_id"],
            "selected_source_performance_sha256": route["performance_document_sha256"],
            "source_take_id": route["source_take_id"],
            "source_take_sha256": route["source_take_sha256"],
            "source_film_time_tick": route["film_time_tick"],
            "recorded_original_signal": measured,
            "contributor_id": performer_id, "contributor_role": performer_role,
            "performer_requested_credit": credit, "consent_scopes": consent,
            "rights_separately_attested_by_performer": False,
            "legal_reuse_clearance_completed": False,
            "recorded_line_underlying_voice_proven": False,
            "director_voice_timbre_reviewed": False,
            "director_delivery_accepted": False,
            "voice_conversion_worker_authorized": False,
            "voice_cloning_worker_authorized": False,
            "model_training_authorized": False,
            "source_data_never_replaced": True,
        }
        return {**payload, "plan_sha256": digest(payload)}

    def publish(self, pid, route_request, *, session_id, profile_revision,
                audio_id, audio_revision, performer_id, performer_role,
                credit_line, rights, performer_consent_event, director_event,
                director_note):
        _id(session_id, "original voice actor session ID")
        note = bounded(director_note, "performance session review", max_length=1400)
        arguments = dict(
            profile_revision=profile_revision, audio_id=audio_id,
            audio_revision=audio_revision, performer_id=performer_id,
            performer_role=performer_role, credit_line=credit_line, rights=rights)
        plan = self.plan(pid, route_request, **arguments)
        if session_id in {
            audio_id, plan["source_take_id"], plan["source_selection_id"],
            plan["selected_source_performance_id"], plan["script_id"]
        }:
            raise ValueError("Voice session must not alias an original source")
        consent_scope = {
            "operation": "film03_attest_original_human_voice_performance",
            "project_id": pid, "contributor_id": performer_id,
            "actor_id": plan["actor_id"], "voice_id": plan["voice_id"],
            "session_id": session_id,
            "original_audio_id": audio_id, "original_audio_revision": audio_revision,
            "original_pcm_sha256": plan["recorded_original_signal"]["pcm16le_sha256"],
            "script_line_id": plan["script_line_id"],
            "script_text_sha256": plan["script_text_sha256"],
            "consent_scopes": plan["consent_scopes"],
            "performer_requested_credit": plan["performer_requested_credit"],
        }
        if not self._performer(performer_consent_event, consent_scope):
            raise PermissionError("No trusted human performer attestation for exact audio and rights")
        approved_scope = {
            "operation": "film03_admit_human_actor_voice_performance",
            "project_id": pid, "actor_id": plan["actor_id"],
            "voice_id": plan["voice_id"], "contributor_id": performer_id,
            "session_id": session_id, "plan_sha256": plan["plan_sha256"],
            "source_take_sha256": plan["source_take_sha256"],
            "original_pcm_sha256": plan["recorded_original_signal"]["pcm16le_sha256"],
            "director_note": note,
        }
        if not self._director(director_event, approved_scope):
            raise PermissionError("No independent director approval for the exact human source")
        if self.plan(pid, route_request, **arguments) != plan:
            raise PermissionError("Actor, original audio, or screenplay changed during consent")
        doc = {**plan, "session_id": session_id, "director_note": note,
               "rights_separately_attested_by_performer": True,
               "director_authorized_source_intake": True,
               "no_voice_cloning_or_model_training_permission_inferred": True}
        def guard(db):
            person = db.execute("""
                SELECT document_sha256,voice_id,voice_cast_revision,voice_reference_sha256
                FROM nvp_bible_actor_identity_profiles
                WHERE project_id=? AND actor_id=?
                ORDER BY profile_revision DESC LIMIT 1
            """, (pid,plan["actor_id"])).fetchone()
            cast = db.execute("""
                SELECT voice_id,cast_revision,reference_audio_sha256
                FROM nvp_bible_voice_casts
                WHERE project_id=? AND actor_id=?
                ORDER BY cast_revision DESC LIMIT 1
            """,(pid,plan["actor_id"])).fetchone()
            project = db.execute(
                "SELECT revision,screenplay FROM projects WHERE id=?", (pid,)).fetchone()
            if (person is None or cast is None or project is None or
                person["document_sha256"] != plan["actor_profile_sha256"] or
                person["voice_id"] != plan["voice_id"] or
                person["voice_cast_revision"] != plan["voice_cast_revision"] or
                person["voice_reference_sha256"] != plan["voice_reference_sha256"] or
                cast["voice_id"] != plan["voice_id"] or
                cast["cast_revision"] != plan["voice_cast_revision"] or
                cast["reference_audio_sha256"] != plan["voice_reference_sha256"] or
                project["revision"] != plan["script_screenplay_revision"] or
                sha256(project["screenplay"].encode("utf8")).hexdigest() !=
                        plan["script_screenplay_sha256"]):
                raise PermissionError("Casting or script changed before voice actor session commit")
            current = db.execute("""
                SELECT head_revision FROM film_objects
                WHERE project_id=? AND object_id=?
            """,(pid,plan["source_selection_id"])).fetchone()
            if not current or current["head_revision"] != plan["source_selection_revision"]:
                raise PermissionError("Director changed active screenplay selection")
            db.execute("""
                INSERT INTO nvp_film03_human_voice_audio_custody
                (project_id,audio_id,audio_revision,pcm_sha256,actor_id,performer_id,session_id)
                VALUES (?,?,?,?,?,?,?)
            """, (
                pid, audio_id, audio_revision,
                plan["recorded_original_signal"]["pcm16le_sha256"],
                plan["actor_id"], performer_id, session_id,
            ))
        saved = self.index.register_revision(
            pid, session_id, "performance", doc,
            expected_revision=0,
            dependencies=[
                {"object_id": audio_id, "revision": audio_revision, "role": "audio"},
                {"object_id": plan["selected_source_performance_id"],
                 "revision": 1, "role": "performance"},
                {"object_id": plan["source_selection_id"],
                 "revision": plan["source_selection_revision"],
                 "role": "presentation"},
                {"object_id": plan["source_take_id"], "revision": 1, "role": "source_take"},
            ],
            precommit_guard=guard,
        )
        return {
            "format": FORMAT, "session_id": session_id,
            "session_revision": saved["revision"],
            "session_document_sha256": saved["document_sha256"],
            "actor_id": plan["actor_id"], "voice_id": plan["voice_id"],
            "contributor_id": performer_id,
            "recorded_original_pcm_sha256":
                plan["recorded_original_signal"]["pcm16le_sha256"],
            "separate_performer_and_director_attestations": True,
            "recording_source_preserved": True,
            "human_listening_and_transcript_verification_pending": True,
            "generated_voice_or_model_executed": False,
            "film_take_approved": False,
        }

    def reopen(self, pid, session_id, *, revision=1):
        """Restart/recovery readback verifies the same performer + original PCM."""
        record = self.index.read_revision(pid, session_id, revision)
        doc = record["data"]
        if record["kind"] != "performance" or doc.get("format") != FORMAT:
            raise PermissionError("Not a canonical original human voice session")
        source = doc["recorded_original_signal"]
        sound = original_signal_measurement(
            self.index, pid, source["source_id"], source["revision"])
        if sound != source:
            raise RuntimeError("Human actor's original recorded PCM was modified")
        with self.index.studio._connection() as db:
            owner = db.execute("""
                SELECT actor_id,performer_id,pcm_sha256
                FROM nvp_film03_human_voice_audio_custody
                WHERE project_id=? AND audio_id=? AND audio_revision=?
            """, (pid, source["source_id"], source["revision"])).fetchone()
        if (owner is None or owner["actor_id"] != doc["actor_id"] or
                owner["performer_id"] != doc["contributor_id"] or
                owner["pcm_sha256"] != sound["pcm16le_sha256"]):
            raise RuntimeError("Durable performer/audio custody differs from source revision")
        return {
            "format": FORMAT, "session_id": session_id, "revision": revision,
            "document_sha256": record["document_sha256"],
            "actor_id": doc["actor_id"], "voice_id": doc["voice_id"],
            "contributor_id": doc["contributor_id"],
            "consent_scopes": doc["consent_scopes"],
            "original_audio_sha256": sound["pcm16le_sha256"],
            "reopened_and_source_verified": True,
            "filmmaking_performance_not_yet_approved": True,
        }
