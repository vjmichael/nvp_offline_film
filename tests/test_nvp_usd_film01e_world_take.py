"""USD-FILM-01E: actual film-world-to-original-Take, ActorID and PCM tests.

Real first-party OpenUSD/FilmIndex/TemporalLedger/StoryBible source; no fake
USD or audio synthesis. The separate FILM03 fixture's voice waveform is
SYNTHETIC TEST DATA only, never a film voice acceptance sample.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import struct
import unittest

from pxr import UsdGeom

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_usd_film01d_shot_working_set import (
    FilmWorldShotPlanner,FilmShotWorkingSet,
)
from backend.nvp_usd_film01e_world_take import (
    OpenUSDWorldTakeCapture, FORMAT, AUDIO_TICKS_PER_SAMPLE,
)
from backend.nvp_data_av_source import RecordedSoundSources,SAMPLE_RATE
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from test_nvp_usd_film01_world import NativeFilmWorld01
from test_nvp_film03_dialogue_manager import construct_real_original_dialogue

T=TICKS_PER_SECOND
CREATIVE_ACTION="DIRECTOR_FREEZES_EXACT_ORIGINAL_FILM_WORLD"


def authority(event, scope):
    return (event==CREATIVE_ACTION and
            scope["operation"]=="nvp.freeze.usd_film01e_world_take.v1")


class OriginalWorldCinematicTakeTests(unittest.TestCase):
    def setUp(self):
        b=NativeFilmWorld01(
            "test_real_lazy_scene_payloads_and_original_authored_camera")
        b.setUp()
        self.addCleanup(b.tmp.cleanup)
        self.b=b
        self.world=b.publish()
        self.tick=TemporalLedger(b.index)
        b.index.register_revision(
            b.pid,"StageAction","performance",
            {"format":"test.01e.actual_source_motion",
             "verb":"turn to camera"},expected_revision=0)
        # Original PCM is explicit test-origin source. Its 48k samples are
        # published under FilmIndex, never made up by a virtual shot.
        pcm=struct.pack("<"+"h"*SAMPLE_RATE,
                        *[3000 if i%64<32 else -3000
                          for i in range(SAMPLE_RATE)])
        self.audio=RecordedSoundSources(b.index).publish(
            b.pid,"MicOriginal",[pcm],expected_revision=0)
        self.acting=self.tick.publish(
            b.pid,"StreetOriginalEvents",[
                {"event_id":"ActorTurns","event_kind":"action",
                 "subject_id":"StageActor","start_tick":0,
                 "end_tick":T,
                 "source_id":"StageAction","source_revision":1,
                 "payload":{"usd_prim_path":"/World/StageActor"}},
                {"event_id":"SourceRoomVoice","event_kind":"sound",
                 "subject_id":"StageActor","start_tick":0,
                 "end_tick":T,
                 "source_id":"MicOriginal","source_revision":1,
                 "payload":{"usd_prim_path":"/World/StageActor",
                            "source_first_sample":0}},
            ],duration_tick=2*T)
        scene_capture=OpenUSDTakeCapture(
            b.index,verify_creator_action=lambda event,scope:
                event=="APPROVE_ORIGINAL_TEST_SCENE" and
                scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.original=scene_capture.freeze(
            b.pid,"OriginalStreetTake",scene_id="Street",scene_revision=1,
            timeline_id="StreetOriginalEvents",timeline_revision=1,
            sample_ticks=[0,T],creator_event="APPROVE_ORIGINAL_TEST_SCENE")
        self.bible=StoryBible(b.studio)
        self.registry=ProductionBibleActors(b.studio)
        self.actor=self.bible.create_entity(
            b.pid,"character","ORIGINAL STREET ACTOR")
        self.shot=FilmWorldShotPlanner(b.index).publish(
            b.pid,"StreetWorldShot",world_id="TownWorld",world_revision=1,
            camera_set="Outside",camera_prim="/World/Camera",
            sample_ticks=[0,T],required_sets=["Outside"],
            max_loaded_sets=1)
        self.source_takes=[{
            "set":"Outside","take_id":"OriginalStreetTake",
            "take_sha256":self.original["document_sha256"],
        }]
        self.capture=OpenUSDWorldTakeCapture(
            b.index,verify_creator_action=authority)

    def link_actor(self):
        b=self.b
        current=self.registry.actor(b.pid,self.actor["id"])
        self.registry.link(
            b.pid,self.actor["id"],role="actor_prim",
            source_family="filmindex",target_id="OriginalStreetTake",
            target_revision=1,actor_prim_path="/World/StageActor",
            expected_actor_revision=current["bible_revision"],
            director_note="Actual original source geometry for the street character")

    def freeze(self,take="WorldStreetTake",**kw):
        inp={
            "world_id":"TownWorld","world_revision":1,
            "shot_id":"StreetWorldShot","shot_revision":1,
            "scene_takes":deepcopy(self.source_takes),
            "creator_event":CREATIVE_ACTION,
        }
        inp.update(kw)
        return self.capture.freeze(self.b.pid,take,**inp)

    def test_world_take_binds_actual_actor_and_original_pcm_without_new_voice(self):
        self.link_actor()
        frozen=self.freeze()
        self.assertEqual(frozen["revision"],1)
        doc=self.b.index.read_revision(
            self.b.pid,"WorldStreetTake",1)["data"]
        self.assertEqual(doc["format"],FORMAT)
        self.assertEqual(doc["world_document_sha256"],
                         self.world["document_sha256"])
        self.assertEqual(doc["camera_shot_document_sha256"],
                         self.shot["document_sha256"])
        self.assertEqual(len(doc["canonical_original_actors"]),1)
        member=doc["canonical_original_actors"][0]
        self.assertEqual(member["actor_id"],self.actor["id"])
        self.assertEqual(member["original_actor_prim"],"/World/StageActor")
        self.assertEqual(member["composed_actor_prim"],
                         "/World/Sets/Outside/StageActor")
        self.assertIsNone(member["voice_id"])
        self.assertTrue(member["voice_not_synthesized_from_identity"])
        self.assertEqual(len(doc["original_timeline_audio_sources"]),1)
        source=doc["original_timeline_audio_sources"][0]
        self.assertEqual(source["original_source_document_sha256"],
                         self.audio["document_sha256"])
        self.assertEqual(source["sample_rate_hz"],48000)
        self.assertEqual(source["ticks_per_original_pcm_sample"],147000)
        self.assertFalse(doc["dialogue_or_audio_generated"])
        self.assertFalse(doc["finished_picture_rendered"])
        report=self.capture.verify_take(self.b.pid,"WorldStreetTake")
        self.assertEqual(report["status"],
                         "VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE")
        self.assertEqual(report["canonical_actor_count"],1)
        self.assertEqual(report["original_audio_event_count"],1)
        state=self.capture.sample(self.b.pid,"WorldStreetTake",tick=T)
        self.assertEqual(state["original_camera_path"],
                         "/World/Sets/Outside/Camera")
        self.assertEqual(state["scenes"][0]["actors"][0]["actor_id"],
                         self.actor["id"])
        self.assertEqual(state["scenes"][0]["actors"][0][
            "world_translation_m"],[2.0,0.0,0.0])
        original=scene_capture_sha=self.b.index.read_revision(
            self.b.pid,"OriginalStreetTake",1)["document_sha256"]
        self.assertEqual(original,self.original["document_sha256"])
        with self.assertRaises(RuntimeError):
            self.freeze()

    def test_actor_casting_is_required_not_automatically_generated(self):
        with self.assertRaises((RuntimeError,PermissionError)):
            self.freeze(take="WorldTakeUncast")
        with self.assertRaises(KeyError):
            self.b.index.read_revision(self.b.pid,"WorldTakeUncast",1)
        self.link_actor()
        self.freeze(take="OriginalCastBound")
        self.assertEqual(
            self.capture.verify_take(self.b.pid,"OriginalCastBound")[
                "canonical_actor_count"],1)

    def test_reopen_after_project_restart_original_take_is_immutable(self):
        self.link_actor()
        original_sha=self.original["document_sha256"]
        frozen=self.freeze()
        newer=OpenUSDWorldComposer(self.b.index).publish(
            self.b.pid,"TownWorld",expected_revision=1,
            sets=self.b.sets,props=[],variants=[],instancers=[])
        self.assertEqual(newer["revision"],2)
        reader=OpenUSDWorldTakeCapture(
            FilmIndex(Studio(self.b.db)),
            verify_creator_action=lambda *_:False)
        report=reader.verify_take(self.b.pid,"WorldStreetTake")
        self.assertEqual(report["take_document_sha256"],
                         frozen["document_sha256"])
        self.assertEqual(reader.sample(
            self.b.pid,"WorldStreetTake",tick=0)["tick"],0)
        self.assertEqual(
            self.b.index.read_revision(
                self.b.pid,"OriginalStreetTake",1)["document_sha256"],original_sha)

    def test_wrong_camera_time_foreign_set_and_source_hash_fail_closed(self):
        self.link_actor()
        attempts=[
            {"scene_takes":[{
                "set":"Outside","take_id":"OriginalStreetTake",
                "take_sha256":"0"*64}]},
            {"scene_takes":[{
                "set":"Inside","take_id":"OriginalStreetTake",
                "take_sha256":self.original["document_sha256"]}]},
            {"scene_takes":[]},
            {"scene_takes":[{
                "set":"Outside","take_id":"OriginalStreetTake",
                "take_sha256":self.original["document_sha256"]},
                {"set":"Outside","take_id":"OriginalStreetTake",
                "take_sha256":self.original["document_sha256"]}]},
        ]
        for i,variation in enumerate(attempts):
            with self.subTest(case=i):
                with self.assertRaises((ValueError,RuntimeError,
                                        PermissionError,KeyError)):
                    self.freeze("RejectedWorldTake"+str(i),**variation)
                with self.assertRaises(KeyError):
                    self.b.index.read_revision(
                        self.b.pid,"RejectedWorldTake"+str(i),1)
        outsider=self.b.studio.create_project(
            "Separate film with no shared actor data","")["id"]
        with self.assertRaises((KeyError,PermissionError)):
            self.capture.freeze(
                outsider,"RejectedOtherFilm",world_id="TownWorld",
                world_revision=1,shot_id="StreetWorldShot",
                shot_revision=1,scene_takes=self.source_takes,
                creator_event=CREATIVE_ACTION)

    def test_rejected_fake_authority_preserves_old_world_and_take(self):
        self.link_actor()
        with self.assertRaises(PermissionError):
            self.freeze(take="NotCreativelyApproved",
                        creator_event="UNKNOWN_CREATIVE_ACTION")
        with self.assertRaises(KeyError):
            self.b.index.read_revision(self.b.pid,"NotCreativelyApproved",1)
        self.assertEqual(
            OpenUSDTakeCapture(
                self.b.index,verify_creator_action=lambda *_:False).
            verify_take(self.b.pid,"OriginalStreetTake")["status"],
            "VERIFIED_FROZEN_DATA_TAKE")

    def test_world_checkpoint_is_not_replaced_with_unverified_frame_time(self):
        self.link_actor()
        self.freeze()
        with self.assertRaises(ValueError):
            self.capture.sample(
                self.b.pid,"WorldStreetTake",tick=T//2)
        with self.assertRaises(ValueError):
            self.capture.sample(
                self.b.pid,"WorldStreetTake",tick=T+1)


class RecordedActorVoiceWorldTakeTests(unittest.TestCase):
    """Use existing FILM03's genuinely index-linked synthetic source fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix="nvp-usd-film01e-voice-")
        cls.state=construct_real_original_dialogue(
            Path(cls.tmp.name).resolve(),recorded_voice=True)
        s=cls.state
        # The source film has 3 original shot scene revisions; the
        # Rekindle source is a 3D FilmIndex scene with an original Take.
        cls.world=OpenUSDWorldComposer(s["index"]).publish(
            s["pid"],"RelayWorld",sets=[{
                "name":"Relay","scene_id":"Relay30Scene",
                "scene_revision":3,
            }],props=[],variants=[],instancers=[])
        cls.shot=FilmWorldShotPlanner(s["index"]).publish(
            s["pid"],"RelayDirectorShot",
            world_id="RelayWorld",world_revision=1,
            camera_set="Relay",camera_prim="/World/Camera",
            sample_ticks=[0,T,2*T],required_sets=["Relay"],
            max_loaded_sets=1)
        cls.source=[{
            "set":"Relay","take_id":"RelayRekindleTake",
            "take_sha256":s["original_take"]["document_sha256"],
        }]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def capture(self):
        return OpenUSDWorldTakeCapture(
            self.state["index"],verify_creator_action=authority)

    def test_original_actorid_and_approved_voiceid_reach_same_immutable_take(self):
        s=self.state
        writer=self.capture()
        result=writer.freeze(
            s["pid"],"RelayWorldTake",
            world_id="RelayWorld",world_revision=1,
            shot_id="RelayDirectorShot",shot_revision=1,
            scene_takes=self.source,
            dialogue_requests=[s["request"]],
            creator_event=CREATIVE_ACTION)
        self.assertEqual(result["revision"],1)
        doc=s["index"].read_revision(s["pid"],"RelayWorldTake",1)["data"]
        self.assertEqual(len(doc["canonical_original_actors"]),4)
        self.assertEqual(len(doc["original_selected_dialogue"]),1)
        speaker=doc["original_selected_dialogue"][0]
        self.assertEqual(speaker["actor_id"],s["people"]["DONUT"])
        self.assertEqual(speaker["voice_id"],"Voice_Donut_Original")
        self.assertEqual(speaker["original_recorded_voice"][
            "original_pcm_document_sha256"],
            s["audio"]["document_sha256"])
        self.assertEqual(speaker["composed_actor_prim"],
                         "/World/Sets/Relay/Engineer")
        self.assertTrue(speaker["voice_available_only_if_original_verified"])
        self.assertFalse(speaker["generated_voice_or_audio"])
        report=writer.verify_take(s["pid"],"RelayWorldTake")
        self.assertEqual(report["director_selected_dialogue_count"],1)
        self.assertGreater(report["original_audio_event_count"],0)
        self.assertEqual(
            writer.sample(s["pid"],"RelayWorldTake",tick=T)[
                "world_document_sha256"],self.world["document_sha256"])
        self.assertEqual(writer.verify_take(
            s["pid"],"RelayWorldTake")["status"],
            "VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE")

    def test_wrong_actorid_or_selected_line_does_not_create_world_take(self):
        s=self.state
        for i,request in enumerate((
            {**s["request"],"actor_id":s["people"]["BOX"]},
            {**s["request"],"exact_text":"Invented by a model"},
            {**s["request"],"source_take_sha256":"0"*64},
        )):
            with self.subTest(case=i):
                with self.assertRaises((
                    PermissionError,RuntimeError,ValueError,KeyError)):
                    self.capture().freeze(
                        s["pid"],"InvalidWorldVoice"+str(i),
                        world_id="RelayWorld",world_revision=1,
                        shot_id="RelayDirectorShot",shot_revision=1,
                        scene_takes=self.source,
                        dialogue_requests=[request],
                        creator_event=CREATIVE_ACTION)
                with self.assertRaises(KeyError):
                    s["index"].read_revision(
                        s["pid"],"InvalidWorldVoice"+str(i),1)


if __name__=="__main__":
    unittest.main()
