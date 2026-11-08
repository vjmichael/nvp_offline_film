"""FILM03-05: ActorID nucleus for visual traits, gait, VoiceType and AI voice.

Runs with actual Studio/StoryBible/FilmIndex/real original OpenUSD source,
exact 4-actor casting and source-authorized unrecorded dialogue selection.
Voice reference is disposable TEST-ONLY PCM, not a real human/AI voice.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film03_actor_identity_core import (
    ActorIdentityCore,PROFILE_FORMAT,AI_CONTRACT_FORMAT,digest,
)
from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_wo6_scene_context import assemble_film_crew_context
from test_nvp_film03_dialogue_manager import (
    construct_real_original_dialogue,ACTION,
)

def permit(event, scope):
    return event==ACTION and scope["operation"] in {
        "film03_cast_actor_voice_identity",
        "film03_publish_actor_identity_profile",
    }

def identity_profile(*,selector="DonutEngineVoice2026"):
    return {
        "appearance":{
            "silhouette":"Animated copper metallic torus; hole stays visible",
            "palette":"Copper, cream glints and cool blue rim",
            "surface":"Brushed copper with deliberate specular imperfections",
            "signature_marks":"A notch at the upper-left edge",
            "visual_expression":"Tilts slowly before answering",
        },
        "behavior":{
            "personality_traits":"Cautious, loyal and sardonic engineer",
            "habits":"Double-checks relay before trusting the sphere",
            "emotional_rules":"Express concern through shorter pauses",
            "speech_style":"Measured cadence, dry understated delivery",
        },
        "movement":{
            "gait":"Lopsided roll every third step, never perfectly symmetric",
            "posture":"Slight tilted axis at rest",
            "signature_gestures":"Small clockwise wobble when surprised",
            "movement_peculiarities":"Off-gait limp and slower leftward recovery",
        },
        "voice_type":{
            "voice_type_id":"VoiceType_DonutWarmLow",
            "register":"Low-mid register",
            "pitch":"Low warm fundamental, no sudden register jumps",
            "timbre":"Rounded, slightly grainy resonant quality",
            "accent":"Neutral studio English",
            "cadence":"Even speech with intentionally delayed response",
            "articulation":"Precise consonants, softened endings",
            "signature_quirks":"Small breath before key engineering terms",
        },
        "voice_generation":{
            "engine_id":"NvpReviewedLocalTTS",
            "model_id":"TestModelNotInstalled",
            "model_revision":"TestRevision001",
            "engine_voice_id":selector,
            "seed":1742,
            "rate":0.95,
            "pitch_shift":-0.5,
            "stability":0.93,
            "language":"en",
        },
        "director_notes":"Character-wide continuity source for every future take",
    }


def real_unrecorded_actor_with_voice(root):
    source=construct_real_original_dialogue(root,recorded_voice=False)
    pid=source["pid"];aid=source["people"]["DONUT"]
    # Test-only source bytes, no actual spoken/synthesized dialogue.
    anchor=RecordedSoundSources(source["index"]).publish(
        pid,"DonutGenuineSourceVoiceAnchorTest",
        [b"\x00\x00"*256],expected_revision=0)
    identity=ProductionBibleVoiceIdentity(
        source["index"],verify_creator_action=permit)
    cast=identity.cast_voice(
        pid,aid,voice_id="Voice_Donut_ActorIdentity",
        reference_audio_id="DonutGenuineSourceVoiceAnchorTest",
        reference_audio_revision=1,expected_cast_revision=0,
        director_review_note="TEST ONLY: approve source identity, no speech synthesized",
        creator_event=ACTION)
    source.update(anchor=anchor,voice_identity=cast)
    return source


class ActorIdentityCompleteProfileSource(unittest.TestCase):
    def test_core_actorid_sources_voice_type_gait_traits_without_creating_audio(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            service=ActorIdentityCore(s["index"],verify_creator_action=permit)
            actor=s["registry"].actor(pid,aid)
            first=service.publish(
                pid,aid,identity_profile(),
                expected_profile_revision=0,
                expected_bible_revision=actor["bible_revision"],
                director_note="Director approves actual donut identity and odd gait",
                creator_event=ACTION)
            self.assertEqual(first["format"],PROFILE_FORMAT)
            self.assertEqual(first["actor_id"],aid)
            self.assertEqual(first["current"]["voice_id"],"Voice_Donut_ActorIdentity")
            self.assertIn("Off-gait",first["current"]["profile"]["movement"][
                "movement_peculiarities"])
            self.assertEqual(first["current"]["profile"]["voice_type"][
                "voice_type_id"],"VoiceType_DonutWarmLow")
            view=s["registry"].actor(pid,aid)
            self.assertEqual(view["current_identity_profile"]["document_sha256"],
                             first["current"]["document_sha256"])
            self.assertEqual(len(view["immutable_identity_profile_history"]),1)
            prepared=service.prepare_generated_voice(
                pid,s["request"],profile_revision=1)
            self.assertEqual(prepared["format"],AI_CONTRACT_FORMAT)
            self.assertEqual(prepared["actor_id"],aid)
            self.assertEqual(prepared["voice_id"],"Voice_Donut_ActorIdentity")
            self.assertEqual(prepared["voice_type"]["voice_type_id"],
                             "VoiceType_DonutWarmLow")
            self.assertEqual(prepared["generation_settings"]["engine_voice_id"],
                             "DonutEngineVoice2026")
            self.assertEqual(prepared["exact_script_text"],
                             "The relay is still silent.")
            self.assertEqual(prepared["source_take_sha256"],
                             s["original_take"]["document_sha256"])
            self.assertFalse(prepared["audio_generation_executed"])
            self.assertFalse(prepared["tts_worker_authorized"])
            self.assertTrue(prepared[
                "untrusted_model_may_not_change_actor_or_voice_type"])
            raw=dict(prepared)
            sha=raw.pop("contract_sha256")
            self.assertEqual(digest(raw),sha)
            self.assertIsNone(
                s["index"].read_revision(pid,"DonutAuthoredOriginalLine",1)[
                    "data"]["recorded_voice_source"])
            # No new audio or other originally rendered film content invented.
            self.assertEqual(s["index"].read_revision(
                pid,"RelayRekindleTake",1)["document_sha256"],
                s["original_take"]["document_sha256"])

    def test_actual_source_scene_crew_retrieves_authoritative_actor_essence(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            core=ActorIdentityCore(s["index"],verify_creator_action=permit)
            actor=s["registry"].actor(pid,aid)
            prof=core.publish(
                pid,aid,identity_profile(),
                expected_profile_revision=0,
                expected_bible_revision=actor["bible_revision"],
                director_note="Director connects actor physicality and voice to scene",
                creator_event=ACTION)
            context=assemble_film_crew_context(
                s["index"],pid,"RelayRekindleTake",1,0,
                actor_identity_id=aid,actor_profile_revision=1)
            essence=context["selected_actorid_character_essence"]
            self.assertEqual(essence["actor_id"],aid)
            self.assertEqual(essence["profile_document_sha256"],
                             prof["current"]["document_sha256"])
            self.assertEqual(essence["actor_prim_paths"],["/World/Engineer"])
            self.assertIn("Off-gait",essence["character_profile"]["movement"][
                "movement_peculiarities"])
            self.assertEqual(essence["character_profile"]["voice_type"][
                "timbre"],"Rounded, slightly grainy resonant quality")
            self.assertEqual(essence["voice_id"],"Voice_Donut_ActorIdentity")
            self.assertFalse(essence["rendered_or_generated_performance_authorized"])
            self.assertTrue(context[
                "actor_identity_context_is_not_generation_authorization"])
            inspected=assemble_film_crew_context(
                s["index"],pid,"RelayRekindleTake",1,0)
            self.assertIsNone(inspected["selected_actorid_character_essence"])
            with self.assertRaises(PermissionError):
                assemble_film_crew_context(
                    s["index"],pid,"RelayRekindleTake",1,0,
                    actor_identity_id=s["people"]["BOX"],
                    actor_profile_revision=1)
            with self.assertRaises(PermissionError):
                assemble_film_crew_context(
                    s["index"],pid,"RelayRekindleTake",1,0,
                    actor_identity_id=aid,actor_profile_revision=2)

    def test_revisions_preserve_original_persona_and_reject_stale_ai_profile(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            core=ActorIdentityCore(s["index"],verify_creator_action=permit)
            rev=s["registry"].actor(pid,aid)["bible_revision"]
            original=core.publish(
                pid,aid,identity_profile(),expected_profile_revision=0,
                expected_bible_revision=rev,
                director_note="Original movement and character voice approved",
                creator_event=ACTION)
            revised=identity_profile()
            revised["movement"]["gait"]="Now limps every second turn"
            revised["behavior"]["habits"]="Pauses twice when seeing the sphere"
            second=core.publish(
                pid,aid,revised,expected_profile_revision=1,
                expected_bible_revision=rev,
                director_note="Specific story scene changes donut's odd gait",
                creator_event=ACTION)
            self.assertEqual(second["current"]["profile_revision"],2)
            self.assertEqual(len(second["profile_history"]),2)
            self.assertEqual(second["profile_history"][0]["document_sha256"],
                             original["current"]["document_sha256"])
            self.assertIn("every third step",
                second["profile_history"][0]["profile"]["movement"]["gait"])
            with self.assertRaises(PermissionError):
                core.prepare_generated_voice(pid,s["request"],profile_revision=1)
            with self.assertRaises(RuntimeError):
                core.publish(
                    pid,aid,revised,expected_profile_revision=1,
                    expected_bible_revision=rev,
                    director_note="Attempt to overwrite immutable earlier profile",
                    creator_event=ACTION)
            reopened=ActorIdentityCore(
                FilmIndex(Studio(s["root"]/"short.sqlite3")),
                verify_creator_action=lambda *_:False)
            current=reopened.current(pid,aid)
            self.assertEqual(current["current"]["profile_revision"],2)
            self.assertEqual(current["profile_history"][0]["document_sha256"],
                             original["current"]["document_sha256"])
            self.assertEqual(reopened.prepare_generated_voice(
                pid,s["request"],profile_revision=2)["actor_id"],aid)

    def test_voice_recast_invalidates_old_voice_type_until_director_republishes(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            core=ActorIdentityCore(s["index"],verify_creator_action=permit)
            actor=s["registry"].actor(pid,aid)
            original=core.publish(
                pid,aid,identity_profile(),expected_profile_revision=0,
                expected_bible_revision=actor["bible_revision"],
                director_note="Original actor style and VoiceID approved",
                creator_event=ACTION)
            self.assertFalse(original["profile_voice_cast_stale"])
            new_pcm=RecordedSoundSources(s["index"]).publish(
                pid,"DonutChangedVoiceAnchorTestOnly",
                [b"\x10\x00"*256],expected_revision=0)
            voice=ProductionBibleVoiceIdentity(
                s["index"],verify_creator_action=permit)
            voice.cast_voice(
                pid,aid,voice_id="Voice_Donut_Recast_V2",
                reference_audio_id="DonutChangedVoiceAnchorTestOnly",
                reference_audio_revision=1,expected_cast_revision=1,
                director_review_note="TEST: hearing a different reference profile",
                voice_recast_reason="Director intentionally recasts the character for story",
                creator_event=ACTION)
            stale=core.current(pid,aid)
            self.assertTrue(stale["profile_voice_cast_stale"])
            self.assertEqual(stale["current"]["voice_id"],
                             "Voice_Donut_ActorIdentity")
            with self.assertRaises(PermissionError):
                core.prepare_generated_voice(pid,s["request"],profile_revision=1)
            with self.assertRaises(PermissionError):
                core.publish(
                    pid,aid,identity_profile(),expected_profile_revision=1,
                    expected_bible_revision=actor["bible_revision"],
                    director_note="Unacceptable recast keeps the same actual model voice",
                    creator_event=ACTION)
            changed=identity_profile()
            changed["voice_generation"]["engine_voice_id"]="DonutDistinctRecastVoice2026"
            changed["voice_type"]["timbre"]="More airy, less resonant"
            revised=core.publish(
                pid,aid,changed,expected_profile_revision=1,
                expected_bible_revision=actor["bible_revision"],
                director_note="Director approves VoiceType and generator after recasting",
                creator_event=ACTION)
            self.assertEqual(revised["current"]["voice_id"],
                             "Voice_Donut_Recast_V2")
            self.assertFalse(revised["profile_voice_cast_stale"])
            next_plan=core.prepare_generated_voice(
                pid,s["request"],profile_revision=2)
            self.assertEqual(next_plan["voice_id"],"Voice_Donut_Recast_V2")
            self.assertEqual(next_plan["voice_type"]["timbre"],
                             "More airy, less resonant")
            self.assertEqual(revised["profile_history"][0]["voice_id"],
                             "Voice_Donut_ActorIdentity")
            self.assertEqual(s["index"].read_revision(
                pid,"DonutGenuineSourceVoiceAnchorTest",1)["document_sha256"],
                s["anchor"]["document_sha256"])

    def test_wrong_speaker_and_wrong_voice_selector_are_rejected(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            core=ActorIdentityCore(s["index"],verify_creator_action=permit)
            actor=s["registry"].actor(pid,aid)
            core.publish(
                pid,aid,identity_profile(),expected_profile_revision=0,
                expected_bible_revision=actor["bible_revision"],
                director_note="Source-authorized donut actor identity",
                creator_event=ACTION)
            for swapped in (
                dict(s["request"],actor_id=s["people"]["BOX"]),
                dict(s["request"],actor_id=s["people"]["SPHERE"]),
                dict(s["request"],exact_text="Box owns this line."),
                dict(s["request"],voice_override="DonutEngineVoice2026"),
            ):
                with self.assertRaises((PermissionError,ValueError,KeyError)):
                    core.prepare_generated_voice(pid,swapped,profile_revision=1)
            box=s["people"]["BOX"]
            box_rev=s["registry"].actor(pid,box)["bible_revision"]
            with self.assertRaises(PermissionError):
                core.publish(
                    pid,box,identity_profile(),
                    expected_profile_revision=0,
                    expected_bible_revision=box_rev,
                    director_note="Cannot share same engine voice across two actors",
                    creator_event=ACTION)
            # Character voice *type* can be descriptively similar, but the
            # actual provider voice identity must not be the same.
            box_profile=identity_profile(selector="BoxEngineVoiceDistinct")
            box_profile["behavior"]["personality_traits"]="Pragmatic box"
            separate=core.publish(
                pid,box,box_profile,
                expected_profile_revision=0,
                expected_bible_revision=box_rev,
                director_note="Distinct model voice selector is bound to box",
                creator_event=ACTION)
            self.assertEqual(separate["actor_id"],box)
            self.assertEqual(separate["current"]["voice_id"],None)
            with self.assertRaises(PermissionError):
                core.prepare_generated_voice(
                    pid,dict(s["request"],actor_id=box),profile_revision=1)

    def test_no_AI_or_browser_can_auto_publish_or_mutate_actor_profile(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            actor=s["registry"].actor(pid,aid)
            deny=ActorIdentityCore(s["index"],
                verify_creator_action=lambda *_:False)
            with self.assertRaises(PermissionError):
                deny.publish(
                    pid,aid,identity_profile(),expected_profile_revision=0,
                    expected_bible_revision=actor["bible_revision"],
                    director_note="Untrusted model has no authority",
                    creator_event="MODEL_OUTPUT")
            bad=identity_profile()
            bad["voice_generation"]["engine_voice_id"]="https://remote-voice"
            with self.assertRaises(ValueError):
                deny.publish(
                    pid,aid,bad,expected_profile_revision=0,
                    expected_bible_revision=actor["bible_revision"],
                    director_note="Should not submit arbitrary remote voice URL",
                    creator_event=ACTION)
            bad=identity_profile()
            bad["movement"]["gait"]="<"*1000
            with self.assertRaises(ValueError):
                deny.publish(
                    pid,aid,bad,expected_profile_revision=0,
                    expected_bible_revision=actor["bible_revision"],
                    director_note="Unbounded AI character movement text",
                    creator_event=ACTION)
            self.assertIsNone(deny.current(pid,aid)["current"])

class NativeActorIdentityDirectorApproval(unittest.TestCase):
    def test_native_host_denies_AI_identity_updates_and_exposes_only_a_read_only_tts_plan(self):
        import os
        from unittest.mock import patch
        from backend.nvp_wo6_desktop_bridge import TrustedDesktopWO6Bridge

        class HumanWindow:
            def __init__(self):
                self.answers=[]
                self.prompts=[]
            def get_current_url(self):
                return "http://127.0.0.1:43231/"
            def create_confirmation_dialog(self,title,message):
                self.prompts.append((title,message))
                return self.answers.pop(0) if self.answers else False

        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            original=ActorIdentityCore(
                s["index"],verify_creator_action=permit)
            current=original.publish(
                pid,aid,identity_profile(),
                expected_profile_revision=0,
                expected_bible_revision=s["registry"].actor(pid,aid)["bible_revision"],
                director_note="Original identity approved for exact source",
                creator_event=ACTION)
            old_sha=current["current"]["document_sha256"]
            changed=identity_profile()
            changed["voice_type"]["cadence"]="Quicker with short breaths"
            with patch.dict(os.environ,{
                    "NVP_HOME":str(Path(d).resolve()/"native_app_home")}):
                host=TrustedDesktopWO6Bridge(
                    s["index"],origin="http://127.0.0.1:43231",
                    host_factory=lambda *_:None)
                self.addCleanup(host._close)
                window=HumanWindow()
                host._attach_window(window)
                request={
                    "project_id":pid,"actor_id":aid,"profile":changed,
                    "expected_profile_revision":1,
                    "expected_bible_revision":
                        s["registry"].actor(pid,aid)["bible_revision"],
                    "director_note":"Director authorizes a new speaking cadence",
                }
                with self.assertRaises(PermissionError):
                    host.film03_publish_actor_identity_profile(request)
                self.assertEqual(original.current(pid,aid)["current"][
                    "document_sha256"],old_sha)
                self.assertTrue(any(aid in message
                                    for _,message in window.prompts))
                window.answers=[True]
                result=host.film03_publish_actor_identity_profile(request)
                self.assertEqual(result["current"]["profile_revision"],2)
                self.assertTrue(result["host_native_director_confirmation"])
                self.assertFalse(result["tts_or_animation_worker_invoked"])
                plan=host.film03_preview_actor_ai_voice_contract({
                    "project_id":pid,"actor_id":aid,
                    "source_route":s["request"],"profile_revision":2})
                self.assertEqual(plan["actor_id"],aid)
                self.assertEqual(plan["voice_type"]["cadence"],
                                 "Quicker with short breaths")
                self.assertFalse(plan["audio_generation_executed"])
                self.assertFalse(plan["tts_worker_authorized"])
                self.assertEqual(original.current(pid,aid)["profile_history"][0][
                    "document_sha256"],old_sha)
                with self.assertRaises(PermissionError):
                    host.film03_preview_actor_ai_voice_contract({
                        "project_id":pid,"actor_id":s["people"]["BOX"],
                        "source_route":s["request"],"profile_revision":2})

if __name__=="__main__":
    unittest.main()
