"""FILM03-06 actual native voice synthesis AND reviewed Blender actor gait.

Genuine source: the original three-shot FilmIndex/OpenUSD scene and
production-bible cast (donut, box, sphere, service craft). The reference
VoiceID source is a clearly labelled TEST-ONLY PCM anchor, not actual
actor speech. Generated WAV is REAL local offline eSpeak-NG synthesis.
The animated .blend/PNG are REAL Blender Cycles outputs when configured.

No real source Take is overwritten. No candidate is director approved.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_film03_actor_animation_host import ReviewedActorAnimationHost,PRESETS
from backend.nvp_film03_actor_voice_worker import ReviewedActorVoiceWorker,wav_info,ENGINE
from backend.nvp_film03_actor_identity_core import ActorIdentityCore,digest
from test_nvp_film03_actor_identity_core import (
    identity_profile,real_unrecorded_actor_with_voice,ACTION,
)

def approval(event,scope):
    return (event==ACTION and
            scope["operation"] in (
                "film03_publish_actor_identity_profile",
                "film03_generate_actor_voice_candidate",
                "film03_run_source_locked_actor_animation"))

def prepared_source(root):
    s=real_unrecorded_actor_with_voice(root)
    profile=identity_profile()
    profile["movement"]["gait_preset"]="lopsided_roll"
    # This is a real offline speech engine, NOT a neural cloned actor voice.
    profile["voice_generation"]={
        "engine_id":"NvpEspeakNG",
        "model_id":"EspeakNG",
        "model_revision":"EspeakNG_1_51",
        "engine_voice_id":"en-us",
        "seed":0,"rate":1,"pitch_shift":0,
        "stability":1,"language":"en",
    }
    core=ActorIdentityCore(s["index"],verify_creator_action=approval)
    aid=s["people"]["DONUT"]
    s["profile"]=core.publish(
        s["pid"],aid,profile,expected_profile_revision=0,
        expected_bible_revision=s["registry"].actor(s["pid"],aid)["bible_revision"],
        director_note="TEST ONLY: approve exact actor gait and offline TTS plan",
        creator_event=ACTION)
    s["core"]=core
    return s

class ActorSourceWorkerContracts(unittest.TestCase):
    def test_original_4_cast_blender_packet_and_source_gait_are_pinned(self):
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            host=ReviewedActorAnimationHost(s["index"],
                # Running native Blender is a separate OS-gated acceptance.
                self._dummy_supervisor(Path(d)),verify_creator_action=approval)
            packet=host.plan(s["pid"],s["people"]["DONUT"],
                take_id="RelayRekindleTake",profile_revision=1,
                frame_count=4)
            src=packet["source"]
            self.assertEqual(src["actor_id"],s["people"]["DONUT"])
            self.assertEqual(src["actor_prim_path"],"/World/Engineer")
            self.assertEqual(src["cast_actor_id_by_prim"]["/World/CrossingBox"],
                             s["people"]["BOX"])
            self.assertEqual(src["cast_actor_id_by_prim"]["/World/PassingSphere"],
                             s["people"]["SPHERE"])
            self.assertEqual(src["gait_preset"],"lopsided_roll")
            self.assertEqual(src["profile_sha256"],
                             s["profile"]["current"]["document_sha256"])
            self.assertEqual(src["source_take_sha256"],
                             s["original_take"]["document_sha256"])
            self.assertEqual(src["profile"]["voice_generation"]["engine_voice_id"],
                             "en-us")
            self.assertEqual(len(src["frames"]),4)
            self.assertEqual(len(src["assets"]),5)
            self.assertEqual(packet["source_sha256"],digest(src))
            with self.assertRaises(PermissionError):
                host.plan(s["pid"],s["people"]["BOX"],
                    take_id="RelayRekindleTake",profile_revision=1)
            with self.assertRaises(PermissionError):
                host.plan(s["pid"],s["people"]["DONUT"],
                    take_id="RelayDiscoveryTake",profile_revision=2)
            with self.assertRaises(ValueError):
                host.plan(s["pid"],s["people"]["DONUT"],
                    take_id="RelayRekindleTake",profile_revision=1,frame_count=48)
            # Exact frozen source unchanged by packet building.
            self.assertEqual(s["index"].read_revision(
                s["pid"],"RelayRekindleTake",1)["document_sha256"],
                s["original_take"]["document_sha256"])

    def _dummy_supervisor(self,root):
        # A non-worker contract test must not use a fake Blender executable.
        # Instead initialize an actual supervisor only when provided a native
        # reviewed binary; for CI source-only work use a real OS executable
        # with a real SHA, which is never run by these plan tests.
        binary=Path(os.environ.get("NVP_FILM03_BLENDER_BIN",""))
        if not binary.is_file():
            executable=shutil.which("python3") or shutil.which("python")
            if not executable:
                self.skipTest("Source-only host needs installed executable for supervisor constructor")
            binary=Path(executable)
        return BlenderWorkerSupervisor(root/"unused-supervisor",
            blender_executable=binary,blender_sha256=sha_file(binary),
            blender_version="Blender 5.2.3")

    def test_wrong_model_voice_override_and_cross_actor_profile_fail_before_execution(self):
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            core=s["core"];pid=s["pid"];aid=s["people"]["DONUT"]
            correct=core.prepare_generated_voice(pid,s["request"],profile_revision=1)
            self.assertEqual(correct["voice_id"],"Voice_Donut_ActorIdentity")
            self.assertEqual(correct["generation_settings"]["engine_id"],ENGINE)
            self.assertFalse(correct["audio_generation_executed"])
            self.assertFalse(correct["tts_worker_authorized"])
            for change in (
                dict(s["request"],actor_id=s["people"]["SPHERE"]),
                dict(s["request"],exact_text="The sphere is speaking now."),
                dict(s["request"],engine_voice_id="en-gb"),
            ):
                with self.assertRaises((ValueError,PermissionError,KeyError)):
                    core.prepare_generated_voice(pid,change,profile_revision=1)
            self.assertIsNone(s["index"].read_revision(
                pid,"DonutAuthoredOriginalLine",1)["data"]["recorded_voice_source"])

    def test_unconfigured_movement_cannot_generate_unreviewed_gait(self):
        with TemporaryDirectory() as d:
            s=real_unrecorded_actor_with_voice(Path(d).resolve())
            p=identity_profile()
            core=ActorIdentityCore(s["index"],verify_creator_action=approval)
            current=core.publish(
                s["pid"],s["people"]["DONUT"],p,expected_profile_revision=0,
                expected_bible_revision=s["registry"].actor(
                    s["pid"],s["people"]["DONUT"])["bible_revision"],
                director_note="Director authored descriptive gait only",
                creator_event=ACTION)
            self.assertEqual(current["current"]["profile"]["movement"]["gait_preset"],
                             "unconfigured")
            supervisor=self._dummy_supervisor(Path(d))
            with self.assertRaises(PermissionError):
                ReviewedActorAnimationHost(s["index"],supervisor,
                    verify_creator_action=approval).plan(
                    s["pid"],s["people"]["DONUT"],
                    profile_revision=1,take_id="RelayRekindleTake")

class NativeRealActorWorkerExecution(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("NVP_FILM03_ESPEAK_BIN"),
                         "Actual eSpeak NG native executable required for spoken WAV acceptance")
    def test_real_contained_espeak_produces_unapproved_but_verified_actor_wav(self):
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            exe=Path(os.environ["NVP_FILM03_ESPEAK_BIN"]).resolve(strict=True)
            worker=ReviewedActorVoiceWorker(s["index"],Path(d)/"voice",
                executable=exe,executable_sha256=sha_file(exe),
                engine_revision="EspeakNG_1_51",
                verify_creator_action=approval)
            with self.assertRaises(PermissionError):
                worker.run(s["pid"],s["request"],profile_revision=1,
                           job_id="DonutNotApproved",creator_event="FAKE_AI_CONSENT")
            result=worker.run(s["pid"],s["request"],profile_revision=1,
                              job_id="DonutOriginalSpeech01",creator_event=ACTION)
            self.assertEqual(result["actor_id"],s["people"]["DONUT"])
            self.assertEqual(result["voice_id"],"Voice_Donut_ActorIdentity")
            self.assertTrue(result["voice_output_generated_in_contained_real_process"])
            self.assertTrue(result["worker_exited_and_closed"])
            self.assertFalse(result["voice_approved_for_film"])
            self.assertFalse(result["acoustic_identity_independently_verified"])
            self.assertGreater(result["wav_info"]["sample_count"],1000)
            candidate=s["index"].read_revision(
                s["pid"],result["candidate_id"],1)
            self.assertFalse(candidate["data"]["director_audition_approved"])
            self.assertFalse(candidate["data"]["film_dialogue_take_published"])
            self.assertTrue(candidate["data"]["voice_is_offline_rule_based_tts"])
            self.assertEqual(candidate["data"]["source_pcm_wav_blob_sha256"],
                             result["wav_info"]["wav_sha256"])
            self.assertEqual(worker.verify(
                s["pid"],"DonutOriginalSpeech01")["actor_id"],
                s["people"]["DONUT"])
            with self.assertRaises(RuntimeError):
                worker.run(s["pid"],s["request"],profile_revision=1,
                    job_id="DonutOriginalSpeech01",creator_event=ACTION)
            other=dict(s["request"],actor_id=s["people"]["SPHERE"])
            with self.assertRaises((PermissionError,KeyError,ValueError)):
                worker.run(s["pid"],other,profile_revision=1,
                           job_id="SphereStealsDonutVoice",
                           creator_event=ACTION)
            with open(worker.root/"DonutOriginalSpeech01"/"voice.wav","ab") as f:
                f.write(b"altered")
            with self.assertRaises((PermissionError,RuntimeError)):
                worker.verify(s["pid"],"DonutOriginalSpeech01")

    @unittest.skipUnless(os.environ.get("NVP_FILM03_BLENDER_BIN"),
                         "Real Blender 5.2.3 binary required for actual Cycles gait acceptance")
    def test_real_os_supervised_blender_produces_verified_keyframed_actor_candidate(self):
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            bin=Path(os.environ["NVP_FILM03_BLENDER_BIN"]).resolve(strict=True)
            supervisor=BlenderWorkerSupervisor(
                Path(d)/"contained-blender",
                blender_executable=bin,blender_sha256=sha_file(bin),
                blender_version="Blender 5.2.3")
            host=ReviewedActorAnimationHost(s["index"],supervisor,
                                             verify_creator_action=approval)
            with self.assertRaises(PermissionError):
                host.run(s["pid"],s["people"]["DONUT"],
                         take_id="RelayRekindleTake",
                         profile_revision=1,job_id="DonutUnapprovedMotion",
                         frame_count=4,creator_event="FAKE_AI_CONSENT")
            result=host.run(s["pid"],s["people"]["DONUT"],
                 take_id="RelayRekindleTake",profile_revision=1,
                 job_id="DonutRealGait001",frame_count=4,creator_event=ACTION)
            self.assertTrue(result["actual_native_Blender_completed"])
            self.assertEqual(result["actor_id"],s["people"]["DONUT"])
            self.assertEqual(result["gait_preset"],"lopsided_roll")
            self.assertFalse(result["creator_film_approval"])
            self.assertEqual(result["frame_count"],4)
            receipt=result["native_blender_receipt"]
            self.assertTrue(receipt["all_other_actors_source_transforms_unchanged"])
            self.assertEqual(receipt["source_take_sha256"],
                             s["original_take"]["document_sha256"])
            self.assertNotEqual(receipt["generated_keyframes"][0]["gait_lift_m"],
                                receipt["generated_keyframes"][1]["gait_lift_m"])
            verified=host.verify(s["pid"],"DonutRealGait001")
            self.assertEqual(verified["status"],"VERIFIED_UNAPPROVED")
            self.assertFalse(verified["production_approved"])
            candidate=s["index"].read_revision(
                s["pid"],result["candidate_id"],1)["data"]
            self.assertFalse(candidate["candidate_director_approved"])
            self.assertEqual(candidate["preview_png_blob_sha256"],
                             result["preview_png_sha256"])
            self.assertEqual(s["index"].read_revision(
                s["pid"],"RelayRekindleTake",1)["document_sha256"],
                s["original_take"]["document_sha256"])
            with self.assertRaises(RuntimeError):
                host.run(s["pid"],s["people"]["DONUT"],
                    take_id="RelayRekindleTake",profile_revision=1,
                    job_id="DonutRealGait001",frame_count=4,creator_event=ACTION)

if __name__=="__main__":
    unittest.main()
