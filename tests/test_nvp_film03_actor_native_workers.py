"""FILM03-06 source-bound actor identity and real Blender motion acceptance.

Genuine OpenUSD/StoryBible donut, box and sphere cast. Voice ID
source validation remains mandatory, but film speech generation is
DISABLED until expressive/neural performance quality is proven.
The Blender .blend/PNG are real Cycles outputs when configured.
No original Take or audio is overwritten; no candidate automatically approved.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import json
import subprocess
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_film03_actor_animation_host import ReviewedActorAnimationHost,PRESETS
from backend.nvp_film03_actor_identity_core import ActorIdentityCore,digest
from test_nvp_film03_actor_identity_core import (
    identity_profile,real_unrecorded_actor_with_voice,ACTION,
)

def approval(event,scope):
    return (event==ACTION and
            scope["operation"] in (
                "film03_publish_actor_identity_profile",
                        "film03_run_source_locked_actor_animation"))

def prepared_source(root):
    s=real_unrecorded_actor_with_voice(root)
    profile=identity_profile()
    profile["movement"]["gait_preset"]="lopsided_roll"
    # An unqualified model selector is never permission to synthesize
    # a film performance; source VoiceID and profile can still be audited.
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
                             "DonutEngineVoice2026")
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
            self.assertEqual(correct["generation_settings"]["model_id"],
                             "TestModelNotInstalled")
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
    def test_unqualified_film_speech_worker_is_unavailable_in_trusted_host(self):
        import os
        from unittest.mock import patch
        from backend.nvp_wo6_desktop_bridge import TrustedDesktopWO6Bridge

        class HumanWindow:
            def get_current_url(self):
                return "http://127.0.0.1:43231/"
            def create_confirmation_dialog(self,*_):
                raise AssertionError("No cinematic voice engine should launch or ask consent")
        with TemporaryDirectory() as d:
            s=prepared_source(Path(d).resolve())
            with patch.dict(os.environ,{
                "NVP_HOME":str(Path(d).resolve()/"desktop")}):
                host=TrustedDesktopWO6Bridge(
                    s["index"],origin="http://127.0.0.1:43231",
                    host_factory=lambda *_:None)
                self.addCleanup(host._close)
                host._attach_window(HumanWindow())
                with self.assertRaisesRegex(PermissionError,
                                             "no expressive, film-qualified"):
                    host.film03_run_actor_voice_candidate({
                        "project_id":s["pid"],"source_route":s["request"],
                        "profile_revision":1,"job_id":"NoUnqualifiedVoice"})
                self.assertFalse(
                    (Path(d)/"desktop"/".creator-native-actions"/"actor-tts").exists())
                self.assertIsNone(s["index"].read_revision(
                    s["pid"],"DonutAuthoredOriginalLine",1)["data"][
                    "recorded_voice_source"])

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
            # Reopen actual saved .blend in a completely fresh Blender
            # process; the Python host and worker JSON alone are insufficient.
            saved=supervisor.root/"DonutRealGait001"
            reopen=saved/"independent_reopen.json"
            script=Path(__file__).resolve().parents[1]/"tools"/"nvp_film03_actor_animation_reopen.py"
            command=[str(bin),"-b",str(saved/"scene.blend"),
                     "--python-exit-code","70","--python",str(script),
                     "--",str(saved/"source.json"),str(reopen)]
            completed=subprocess.run(
                command,capture_output=True,text=True,timeout=180,check=False)
            self.assertEqual(completed.returncode,0,
                             (completed.stdout+completed.stderr)[-3000:])
            independent=json.loads(reopen.read_text("utf8"))
            self.assertTrue(independent["passed"])
            self.assertEqual(independent["actor_id"],s["people"]["DONUT"])
            self.assertEqual(independent["original_source_frames_checked"],4)
            self.assertTrue(independent["all_other_source_actors_unchanged"])
            if os.environ.get("NVP_FILM03_ARTIFACT_DIR"):
                dest=Path(os.environ["NVP_FILM03_ARTIFACT_DIR"])/"real-animation"
                dest.mkdir(parents=True,exist_ok=True)
                for rel in ("scene.blend","preview.png","source.json",
                            "audit.json","independent_reopen.json",
                            "worker_stdout.log","worker_stderr.log"):
                    shutil.copy2(saved/rel,dest/rel)
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
