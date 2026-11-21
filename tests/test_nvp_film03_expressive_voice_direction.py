"""FILM03-06: film dialogue requires actual acting directions; not a WAV."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_film03_expressive_voice_direction import (
    FilmActorVoiceDirection, cinematic_engine_readiness,
    validate_directions, text_words, REQUIRED_QUALITY,
)
from test_nvp_film03_actor_native_workers import prepared_source


def direction():
    return {
        "emotion":"uncertain","emotion_intensity":0.65,
        "delivery":"whisper","volume_db":-14.0,"speaking_rate":0.84,
        "breathiness":0.78,
        "emphasis":[{"word_index":3,"weight":0.85}],
        "pauses":[{"word_index":2,"duration_ms":430,"breath":True}],
        "pronunciations":[{"word_index":1,"spoken_as":"ree-LAY"}],
        "emotional_arc":[
            {"word_index":0,"emotion":"afraid","intensity":0.4},
            {"word_index":3,"emotion":"determined","intensity":0.9},
        ],
        "director_intent":"Donut barely whispers first, then gains conviction at the last word.",
    }


class CinemaPerformanceSource(unittest.TestCase):
    def test_director_voice_direction_keeps_same_actorid_script_take_and_immutable_retake_history(self):
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            pid=s["pid"];aid=s["people"]["DONUT"]
            calls=[]
            def confirm(event,scope):
                calls.append(scope)
                return event=="DIRECTOR" and scope["operation"]==(
                    "film03_publish_cinematic_actor_voice_directions")
            editor=FilmActorVoiceDirection(s["index"],verify_creator_action=confirm)
            item=direction()
            first=editor.publish(
                pid,s["request"],profile_revision=1,directions=item,
                expected_revision=0,director_note=
                "Director specifically approved whisper and pronunciation",
                creator_event="DIRECTOR")
            self.assertEqual(first["actor_id"],aid)
            self.assertEqual(first["voice_id"],"Voice_Donut_ActorIdentity")
            self.assertEqual(first["source_take_sha256"],
                             s["original_take"]["document_sha256"])
            self.assertFalse(first["provider_ran"])
            self.assertFalse(first["film_quality_approved"])
            self.assertEqual(calls[-1]["actor_id"],aid)
            stored=s["index"].read_revision(pid,first["direction_id"],1)
            self.assertEqual(stored["kind"],"performance")
            self.assertEqual(stored["data"]["directions"]["delivery"],"whisper")
            self.assertEqual(stored["data"]["directions"]["volume_db"],-14.0)
            self.assertEqual(stored["data"]["directions"]["pauses"][0][
                "duration_ms"],430)
            self.assertEqual(stored["data"]["directions"]["pronunciations"][0][
                "original_word"],text_words(
                    s["core"].prepare_generated_voice(
                        pid,s["request"],profile_revision=1)["exact_script_text"])[1])
            self.assertFalse(stored["data"]["voice_generation_executed"])
            revised=direction()
            revised["emotion"]="determined"
            revised["delivery"]="shout"
            revised["volume_db"]=2.0
            second=editor.publish(
                pid,s["request"],profile_revision=1,directions=revised,
                expected_revision=1,director_note=
                "Director changes delivery for intentional new emotional retake",
                creator_event="DIRECTOR")
            self.assertEqual(second["direction_id"],first["direction_id"])
            self.assertEqual(second["direction_revision"],2)
            original=s["index"].read_revision(pid,first["direction_id"],1)
            self.assertEqual(original["document_sha256"],stored["document_sha256"])
            self.assertEqual(original["data"]["directions"]["delivery"],"whisper")
            self.assertEqual(s["index"].read_revision(
                pid,"RelayRekindleTake",1)["document_sha256"],
                s["original_take"]["document_sha256"])
            with self.assertRaises(RuntimeError):
                editor.publish(
                    pid,s["request"],profile_revision=1,directions=revised,
                    expected_revision=1,director_note="Must never overwrite previous artistic review",
                    creator_event="DIRECTOR")

    def test_wrong_actor_or_script_cannot_inherit_another_characters_emotional_notes(self):
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            editor=FilmActorVoiceDirection(
                s["index"],verify_creator_action=lambda *_:True)
            for wrong in (
                dict(s["request"],actor_id=s["people"]["BOX"]),
                dict(s["request"],actor_id=s["people"]["SPHERE"]),
                dict(s["request"],exact_text="The box gets a different line."),
            ):
                with self.assertRaises((ValueError,KeyError,PermissionError)):
                    editor.publish(
                        s["pid"],wrong,profile_revision=1,
                        directions=direction(),expected_revision=0,
                        director_note="Never transfer Donut acting to another character",
                        creator_event="DIRECTOR")

    def test_invalid_word_level_pronunciation_emotion_pauses_and_loudness_refused(self):
        good=direction()
        text="The relay is still silent."
        self.assertEqual(validate_directions(text,good)["original_word_count"],5)
        changes=(
            ("emphasis",[{"word_index":7,"weight":1.0}]),
            ("pauses",[{"word_index":1,"duration_ms":9000,"breath":True}]),
            ("pronunciations",[{"word_index":6,"spoken_as":"wrong"}]),
            ("emotional_arc",[{"word_index":0,"emotion":"unknown","intensity":1.0}]),
            ("delivery","scream-unlimited"),
            ("volume_db",+35.0),
            ("breathiness",1.5),
        )
        for key,value in changes:
            broken=deepcopy(good);broken[key]=value
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):
                validate_directions(text,broken)

    def test_unapproved_or_unproven_provider_capabilities_cannot_open_film_voice_runtime(self):
        evidence=cinematic_engine_readiness({
            "provider":"UnreviewedFilmVoiceModel","claims_all_capabilities":True,
            "claimed_speaker_match":True,"model_says_wav_is_movie_quality":True,
        })
        self.assertFalse(evidence["cinematic_generation_enabled"])
        self.assertFalse(evidence["espeak_ng_film_voice_qualified"])
        self.assertEqual(set(evidence["required_real_audio_capabilities"]),
                         REQUIRED_QUALITY)
        self.assertTrue(evidence["provider_metadata_is_not_audio_evidence"])
        self.assertTrue(evidence["neural_engine_must_be_reviewed_and_measured"])

if __name__=="__main__":
    unittest.main()
