"""FILM03-03: deterministic, ActorID-locked dialogue and original voice routing.

This module is the trusted boundary between an untrusted AI suggestion and
the authored screenplay/film. The AI NEVER gets to infer the speaker from
line text, visual prim labels, model output, prompt order or a voice name.

A request must carry the EXACT canonical StoryBible ActorID, script source
SHA, line ID, selected performance ID/revision, source Take SHA and film
tick. A successful route independently verifies all of them against:
  * current Studio screenplay + immutable FilmIndex script/selection/Take;
  * StoryBible ActorID and *complete* real OpenUSD actor casting;
  * current production-bible links for dialogue and selected performance;
  * authored temporal dialogue event with canonical ActorID subject;
  * original, SHA-verified recorded PCM16 source and sound event, if any.
Revisions are append-only. An old script/recording is never overwritten.
This is not a speech synthesizer, microphone capture engine or cinematic mix.
"""
from __future__ import annotations

from hashlib import sha256
import re

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE, MAX_READ_SAMPLES
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid
from backend.nvp_film03_object_dialogue import (
    read_scene_dialogue_selection, PERFORMANCE_FORMAT, SELECTION_FORMAT
)
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int

FORMAT = "nvp.film03.canonical_actorid_dialogue_route.v1"
SAMPLE_TICKS = TICKS_PER_SECOND // SAMPLE_RATE
ACTOR_ID_RE = re.compile(r"[a-f0-9]{32}\Z")
REQUIRED = frozenset({
    "actor_id", "script_line_id", "script_document_sha256",
    "selected_performance_id", "selection_id", "selection_revision",
    "source_take_id", "source_take_sha256", "film_time_tick", "exact_text",
})


def actor_subject(actor_id):
    """Safe reversible event-subject encoding (FilmIndex ID must start A-Z)."""
    if type(actor_id) is not str or not ACTOR_ID_RE.fullmatch(actor_id):
        raise ValueError("No canonical 32-hex StoryBible ActorID")
    return "Actor_" + actor_id


class ActorDialogueManager:
    def __init__(self, index):
        if not isinstance(index, FilmIndex):
            raise TypeError("Real NVP FilmIndex is required")
        self.index = index

    def route(self, project_id, requested):
        """Return precisely one source-approved delivery; NO generated voice."""
        _require_pid(project_id)
        if type(requested) is not dict or set(requested) != REQUIRED:
            raise ValueError("Actor dialogue request must specify exactly all source identities")
        aid = requested["actor_id"]
        event_subject = actor_subject(aid)
        for name in ("script_line_id", "selected_performance_id",
                     "selection_id", "source_take_id"):
            _id(requested[name], name)
        for name in ("script_document_sha256", "source_take_sha256"):
            _sha(requested[name])
        tick = _int(requested["film_time_tick"], "dialogue Film Time")
        rev = requested["selection_revision"]
        if type(rev) is not int or rev < 1:
            raise ValueError("Exact selected dialogue revision is required")
        text = requested["exact_text"]
        if type(text) is not str or not text.strip() or len(text) > 3000:
            raise ValueError("No bounded exact source line text was provided")

        # One authoritative creative selection, not a guess from latest text.
        context = read_scene_dialogue_selection(
            self.index, project_id, requested["selection_id"], rev,
            tick=tick, expected_take_id=requested["source_take_id"])
        if (context["source_take_sha256"] != requested["source_take_sha256"] or
                context["script_changed_since_selected_dialogue"]):
            raise PermissionError(
                "Script revision changed: director must publish a newly reviewed dialogue selection")
        selection = self.index.read_revision(project_id, requested["selection_id"], rev)
        source = selection["data"]
        if (source.get("format") != SELECTION_FORMAT or
                source["script_document_sha256"] != requested["script_document_sha256"]):
            raise PermissionError("Wrong frozen screenplay revision for this dialogue")

        active = context["active_object_actor_lines"]
        # A scene must not have two simultaneous different lines assigned
        # to one ActorID. This is not something AI should resolve by guessing.
        if len([x for x in active if x["actor_id"] == aid]) > 1:
            raise PermissionError("Ambiguous simultaneous actor dialogue at Film Time")
        matches = [x for x in active if
                   x["actor_id"] == aid and
                   x["performance_id"] == requested["selected_performance_id"] and
                   x["script_line_id"] == requested["script_line_id"] and
                   x["original_spoken_text"] == text]
        if len(matches) != 1:
            raise PermissionError("AI-assigned speaker or line does not match director selection")
        entry = matches[0]
        if (not entry["source_line_still_matches_selected_script"] and
                not entry["director_explicitly_retained_old_delivery"]):
            raise PermissionError("Old line no longer matches selected script and was not retained")

        # Source-verified original USD scene: actor prim is the geometry;
        # StoryBible ActorID is the speaking person. Require a FULL cast,
        # not only the requested actor, before accepting a final delivery.
        registry = ProductionBibleActors(self.index.studio)
        cast = registry.require_complete_cast(project_id, requested["source_take_id"])
        if cast["take_sha256"] != requested["source_take_sha256"]:
            raise PermissionError("Casting references a different immutable source Take")
        if cast["actor_id_by_prim"].get(entry["openusd_actor_prim_path"]) != aid:
            raise PermissionError("Wrong ActorID for the actual OpenUSD cast member")
        bible = registry.actor(project_id, aid)
        if bible["actor_id"] != aid:
            raise PermissionError("Production Bible actor identity mismatch")

        chosen = self.index.read_revision(
            project_id, requested["selected_performance_id"], 1)
        perf = chosen["data"]
        if (chosen["kind"] != "performance" or
                perf.get("format") != PERFORMANCE_FORMAT or
                chosen["document_sha256"] != entry["performance_document_sha256"] or
                perf["production_bible"]["actor_id"] != aid or
                perf["script_id"] != source["script_id"] or
                perf["script_line_id"] != requested["script_line_id"] or
                perf["script_line_text"] != text or
                perf["script_line_text_sha256"] != sha256(text.encode("utf8")).hexdigest() or
                perf["source_take_sha256"] != requested["source_take_sha256"] or
                perf["openusd_actor_prim_path"] != entry["openusd_actor_prim_path"]):
            raise PermissionError("Frozen performance points to another actor, line or Take")

        # If the director explicitly retained an older script performance,
        # its original source revision must STILL resolve exactly. A model
        # may never substitute "retained" as a blanket bypass of script SHA.
        original_script = self.index.read_revision(
            project_id, perf["script_id"], perf["script_revision"])
        if (original_script["kind"] != "dialogue" or
                original_script["document_sha256"] !=
                    perf["script_document_sha256"]):
            raise PermissionError("Historical script performance provenance changed")
        if perf["script_revision"] == source["script_revision"]:
            if perf["script_document_sha256"] != source["script_document_sha256"]:
                raise PermissionError("Performance came from another script source")
        elif (perf["script_revision"] > source["script_revision"] or
              not entry["director_explicitly_retained_old_delivery"] or
              requested["selected_performance_id"] not in
                source["retained_earlier_performances"]):
            raise PermissionError("Historical retake was not expressly retained by director")

        def require_link(role, target_id, source_revision, document_sha):
            hits = [link for link in bible["active_links"] if
                    link["role"] == role and link["source_family"] == "filmindex"
                    and link["target_id"] == target_id
                    and link["target_revision"] == source_revision
                    and link["source_sha256"] == document_sha]
            if not hits:
                raise PermissionError(
                    f"Production Bible ActorID lacks verified {role} source binding")
            return hits
        require_link("dialogue", source["script_id"], source["script_revision"],
                     source["script_document_sha256"])
        require_link("performance", requested["selected_performance_id"],
                     1, chosen["document_sha256"])

        timeline = TemporalLedger(self.index)
        events = timeline.events_at(
            project_id, source["overlay_timeline_id"],
            source["overlay_timeline_revision"], tick=tick, limit=400)
        authored = [event for event in events if
                    event["event_kind"] == "dialogue" and
                    event["source_id"] == requested["selected_performance_id"]]
        if len(authored) != 1:
            raise PermissionError("No unique authored dialogue event for selected performance")
        line_event = authored[0]
        payload = line_event["payload"]
        if (line_event["subject_id"] != event_subject or
                line_event["source_revision"] != 1 or
                line_event["source_document_sha256"] != chosen["document_sha256"] or
                payload.get("actor_id") != aid or
                payload.get("script_line_id") != requested["script_line_id"] or
                payload.get("script_line_sha256") !=
                   perf["script_line_text_sha256"] or
                payload.get("actor_prim_path") != entry["openusd_actor_prim_path"] or
                not perf["first_tick"] <= tick < perf["end_tick"]):
            raise PermissionError("Authored scene timeline does not bind this line to this ActorID")

        # Every character has one current approved VoiceID independent
        # of its mutable outfit, model, USD prim and individual PCM clips.
        # Reading a script is NOT permission to invent an audible voice.
        from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity
        voice_bible = ProductionBibleVoiceIdentity(
            self.index, verify_creator_action=lambda *_: False)
        cast_voice = voice_bible.current(project_id, aid)["current"]
        voice = None
        if perf["recorded_voice_source"] is not None:
            sound = perf["recorded_voice_source"]
            description = RecordedSoundSources(self.index).describe(
                project_id, sound["audio_id"], sound["audio_revision"])
            if description["document_sha256"] != sound["audio_sha256"]:
                raise PermissionError("Original voice source SHA changed")
            require_link("voice", sound["audio_id"],
                         sound["audio_revision"], sound["audio_sha256"])
            voice_event = [e for e in events if
                           e["event_id"] == "Voice_" +
                              requested["selected_performance_id"] and
                           e["event_kind"] == "sound"]
            if len(voice_event) != 1:
                raise PermissionError("Recorded voice has no unique authored sound event")
            e = voice_event[0]
            if (e["subject_id"] != event_subject or
                    e["source_id"] != sound["audio_id"] or
                    e["source_revision"] != sound["audio_revision"] or
                    e["source_document_sha256"] != sound["audio_sha256"] or
                    e["payload"].get("actor_id") != aid or
                    e["payload"].get("script_line_id") !=
                        requested["script_line_id"] or
                    e["payload"].get("performance_id") !=
                        requested["selected_performance_id"]):
                raise PermissionError("Original source PCM belongs to a different actor")
            # Correct character and dialogue text are insufficient:
            # recorded audio MUST be individually auditioned against
            # this ActorID's exact VoiceID reference and signed into the
            # production Bible. A file named "DonutVoice" is not proof.
            voice_proof = voice_bible.verify_delivery(
                project_id, aid, requested["selected_performance_id"],
                require_current_cast=True)
            if (cast_voice is None or
                    voice_proof["voice_id"] != cast_voice["voice_id"] or
                    voice_proof["cast_revision"] != cast_voice["cast_revision"] or
                    voice_proof["original_audio_sha256"] != sound["audio_sha256"]):
                raise PermissionError("Voice delivery does not match actor's current VoiceID")
            voice = {
                "voice_id": voice_proof["voice_id"],
                "voice_cast_revision": voice_proof["cast_revision"],
                "voice_approval_revision": voice_proof["approval_revision"],
                "voice_reference_audio_sha256": voice_proof["reference_audio_sha256"],
                "director_reviewed_exact_audio": True,
                "acoustically_same_speaker_automatically_proven": False,
                "source_id": sound["audio_id"],
                "source_revision": sound["audio_revision"],
                "original_pcm_document_sha256": sound["audio_sha256"],
                "sample_count": description["data"]["sample_count"],
                "sample_rate_hz": SAMPLE_RATE,
                "sound_event_id": e["event_id"],
                "recorded_voice_verified_not_synthesized": True,
            }
        return {
            "format": FORMAT,
            "project_id": project_id,
            "actor_id": aid, "actor_event_subject": event_subject,
            "production_bible_actor_revision": bible["bible_revision"],
            "canonical_voice_id": (cast_voice["voice_id"] if cast_voice else None),
            "voice_identity_cast_revision": (
                cast_voice["cast_revision"] if cast_voice else None),
            "voice_change_requires_new_director_approval": True,
            "openusd_actor_prim_path": entry["openusd_actor_prim_path"],
            "source_take_id": source["source_take_id"],
            "source_take_sha256": source["source_take_sha256"],
            "script_id": source["script_id"],
            "script_revision": source["script_revision"],
            "script_document_sha256": source["script_document_sha256"],
            "script_line_id": requested["script_line_id"],
            "exact_director_selected_text": text,
            "performance_id": requested["selected_performance_id"],
            "performance_document_sha256": chosen["document_sha256"],
            "selection_id": requested["selection_id"],
            "selection_revision": rev,
            "selection_document_sha256": selection["document_sha256"],
            "authored_dialogue_event_id": line_event["event_id"],
            "film_time_tick": tick,
            "first_tick": perf["first_tick"], "end_tick": perf["end_tick"],
            "historical_line_explicitly_retained": entry[
                "director_explicitly_retained_old_delivery"],
            "original_recorded_voice": voice,
            "playable_recorded_voice_available": voice is not None,
            "unrecorded_voice_does_not_become_synthesized": voice is None,
            "all_original_source_revisions_preserved": True,
            "untrusted_AI_cannot_assign_another_speaker": True,
            "rendered_new_picture": False, "generated_spoken_audio": False,
            "effect": "read_only_authoritative_dialogue_route",
        }

    def read_original_voice(self, project_id, request, *, sample_count):
        """Only source-recorded, exact ActorID-assigned mono PCM16LE; no TTS."""
        if type(sample_count) is not int or not 1 <= sample_count <= MAX_READ_SAMPLES:
            raise ValueError("Voice audition window must be bounded")
        delivery = self.route(project_id, request)
        voice = delivery["original_recorded_voice"]
        if voice is None:
            raise PermissionError("Actor performance has NO recorded voice source")
        elapsed = request["film_time_tick"] - delivery["first_tick"]
        if elapsed % SAMPLE_TICKS:
            raise ValueError("Film time is not aligned to original PCM sample grid")
        first_sample = elapsed // SAMPLE_TICKS
        if first_sample + sample_count > voice["sample_count"]:
            raise ValueError("Original recorded delivery runs out before audition window")
        original_pcm = RecordedSoundSources(self.index).read(
            project_id, voice["source_id"], voice["source_revision"],
            first_sample, sample_count)
        if len(original_pcm) != sample_count * 2:
            raise RuntimeError("Original source voice PCM was truncated")
        return {
            **delivery,
            "original_pcm16le": original_pcm,
            "original_pcm16le_sha256": sha256(original_pcm).hexdigest(),
            "source_sample_first": first_sample,
            "sample_count": sample_count,
            "sample_rate_hz": SAMPLE_RATE,
            "audio_voice_model_invoked": False,
            "new_audio_generated": False,
        }
