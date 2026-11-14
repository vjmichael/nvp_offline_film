"""FILM03-03 actual source-bound actor dialogue router acceptance.

These are explicitly disposable tests, using REAL Studio, StoryBible,
immutable FILM02 original OpenUSD Digital Take and FilmIndex revisions.
The test 48k PCM fixture is synthetic TEST-ONLY source audio, NOT an
actual actor speech recording; it is used solely for identity/byte parity.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_film_index import FilmIndex
from backend.nvp_film03_dialogue_manager import ActorDialogueManager, actor_subject, FORMAT
from backend.nvp_film03_object_dialogue import ObjectActorDialogue
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_story_bible import StoryBible
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, TemporalLedger
from backend.nvp_wo6_scene_context import assemble_film_crew_context
from tools.nvp_film01_original_30s import write_original_30s_source


SOURCE_SCRIPT = """INT. RELAY NINE - NIGHT

DONUT
The relay is still silent.

BOX
This seems like a problem.

SPHERE
Watch this.
"""
REVISED_SCRIPT = SOURCE_SCRIPT.replace(
    "The relay is still silent.", "The relay is coming back online.")
ACTION = "EXPLICIT_DISPOSABLE_CREATOR_APPROVAL_IN_NATIVE_TEST"


def creator(event, scope):
    return bool(event == ACTION and
                scope["operation"] in {
                    "film03_publish_script_dialogue",
                    "film03_record_object_actor_dialogue",
                    "film03_publish_scene_dialogue_selection"
                })


def construct_real_original_dialogue(root, *, recorded_voice=True):
    src = root/"frozen-original-film"
    original = write_original_30s_source(src, approve_test_only=True)
    pid = original["project_id"]
    studio = Studio(src/"short.sqlite3")
    index = FilmIndex(studio)
    writer = ObjectActorDialogue(index,verify_creator_action=creator)
    registry = ProductionBibleActors(studio)
    bible = StoryBible(studio)
    script = studio.save_screenplay(pid, SOURCE_SCRIPT, expected_revision=0)
    scene_id=script["scenes"][0]["id"]
    people={}
    for name in ("DONUT","BOX","SPHERE","SERVICE CRAFT"):
        actor=bible.create_entity(pid,"character",name)
        if name != "SERVICE CRAFT":
            actor=bible.link_scene(pid,actor["id"],scene_id,actor["revision"],
                                   note="Test-only real source screenplay actor cast")
        people[name]=actor["actor_id"]
    take=index.read_revision(pid,"RelayRekindleTake",1)
    take_sha=take["document_sha256"]
    for name,prim in (
            ("DONUT","/World/Engineer"),
            ("BOX","/World/CrossingBox"),
            ("SPHERE","/World/PassingSphere"),
            ("SERVICE CRAFT","/World/ServiceCraft")):
        aid=people[name]
        actor=registry.actor(pid,aid)
        registry.link(
            pid,aid,role="actor_prim",source_family="filmindex",
            target_id="RelayRekindleTake",target_revision=1,
            actor_prim_path=prim,
            expected_actor_revision=actor["bible_revision"],
            director_note="Physical source-authored OpenUSD actor path")
    complete=registry.require_complete_cast(pid,"RelayRekindleTake")
    assert complete["complete"] and len(complete["actor_id_by_prim"]) == 4
    script_revision=writer.publish_script_snapshot(
        pid,"RelayAuthoredObjectScript",
        expected_screenplay_revision=1,expected_manifest_revision=0,
        creator_event=ACTION)
    script_sha=script_revision["document_sha256"]
    script_data=index.read_revision(pid,"RelayAuthoredObjectScript",1)
    lines={l["speaker"]:l for l in script_data["data"]["scenes"][0]["lines"]}
    donut_id=people["DONUT"]
    actor=registry.actor(pid,donut_id)
    registry.link(
        pid,donut_id,role="dialogue",source_family="filmindex",
        target_id="RelayAuthoredObjectScript",target_revision=1,
        expected_actor_revision=actor["bible_revision"])
    audio=None
    pcm=None
    if recorded_voice:
        pcm=struct.pack("<"+"h"*SAMPLE_RATE,
                        *(int(3000*((i%200)/200-0.5)) for i in range(SAMPLE_RATE)))
        # 48kHz mono TEST fixture, NOT a real recorded actor voice.
        audio=RecordedSoundSources(index).publish(
            pid,"DonutSourceVoiceFixture",[pcm],expected_revision=0)
        actor=registry.actor(pid,donut_id)
        registry.link(
            pid,donut_id,role="voice",source_family="filmindex",
            target_id="DonutSourceVoiceFixture",target_revision=1,
            expected_actor_revision=actor["bible_revision"])
    performance=writer.record_performance(
        pid,"DonutAuthoredOriginalLine",
        script_id="RelayAuthoredObjectScript",script_revision=1,
        script_line_id=lines["DONUT"]["line_id"],
        bible_entity_id=donut_id,
        actor_prim_path="/World/Engineer",
        source_take_id="RelayRekindleTake",
        source_take_sha256=take_sha,
        first_tick=0,end_tick=TICKS_PER_SECOND,
        delivery_intent="Clearly enunciate original line as torus",
        voice_source_id=("DonutSourceVoiceFixture" if recorded_voice else None),
        voice_source_revision=(1 if recorded_voice else None),
        creator_event=ACTION)
    actor=registry.actor(pid,donut_id)
    registry.link(
        pid,donut_id,role="performance",source_family="filmindex",
        target_id="DonutAuthoredOriginalLine",target_revision=1,
        expected_actor_revision=actor["bible_revision"])
    selected=writer.publish_scene_dialogue(
        pid,selection_id="OriginalDonutDialogueSelection",
        overlay_timeline_id="OriginalDonutDialogueEvents",
        source_take_id="RelayRekindleTake",source_take_sha256=take_sha,
        script_id="RelayAuthoredObjectScript",script_revision=1,
        performance_ids=["DonutAuthoredOriginalLine"],
        creator_event=ACTION)
    request={
        "actor_id":donut_id,
        "script_line_id":lines["DONUT"]["line_id"],
        "script_document_sha256":script_sha,
        "selected_performance_id":"DonutAuthoredOriginalLine",
        "selection_id":"OriginalDonutDialogueSelection",
        "selection_revision":1,
        "source_take_id":"RelayRekindleTake",
        "source_take_sha256":take_sha,
        "film_time_tick":0,
        "exact_text":lines["DONUT"]["text"],
    }
    return {
        "root":src,"pid":pid,"studio":studio,"index":index,
        "bible":bible,"registry":registry,"people":people,
        "script":script,"original_take":take,"script_sha":script_sha,
        "original_pcm":pcm,"audio":audio,"selected":selected,
        "request":request,
    }


class ActualOriginalActorSourceRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix="nvp-film03-authored-routing-")
        cls.state=construct_real_original_dialogue(
            Path(cls.tmp.name).resolve(),recorded_voice=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_selected_donut_actor_voice_and_timeline_exactly_agree(self):
        s=self.state
        routed=ActorDialogueManager(s["index"]).route(s["pid"],s["request"])
        self.assertEqual(routed["format"],FORMAT)
        self.assertEqual(routed["actor_id"],s["people"]["DONUT"])
        self.assertEqual(routed["actor_event_subject"],
                         actor_subject(s["people"]["DONUT"]))
        self.assertEqual(routed["openusd_actor_prim_path"],"/World/Engineer")
        self.assertEqual(routed["exact_director_selected_text"],
                         "The relay is still silent.")
        self.assertEqual(routed["performance_id"],"DonutAuthoredOriginalLine")
        self.assertEqual(routed["script_document_sha256"],s["script_sha"])
        self.assertEqual(routed["source_take_sha256"],
                         s["original_take"]["document_sha256"])
        self.assertTrue(routed["playable_recorded_voice_available"])
        self.assertTrue(routed["original_recorded_voice"][
            "recorded_voice_verified_not_synthesized"])
        self.assertFalse(routed["generated_spoken_audio"])
        self.assertTrue(routed["untrusted_AI_cannot_assign_another_speaker"])
        stored=TemporalLedger(s["index"]).events_at(
            s["pid"],"OriginalDonutDialogueEvents",1,tick=0,
            event_kind="dialogue")
        self.assertEqual(len(stored),1)
        self.assertEqual(stored[0]["subject_id"],
                         actor_subject(s["people"]["DONUT"]))
        self.assertEqual(stored[0]["payload"]["actor_id"],s["people"]["DONUT"])

    def test_source_recorded_pcm_is_byte_exact_and_never_generated(self):
        s=self.state
        mgr=ActorDialogueManager(s["index"])
        frame=mgr.read_original_voice(s["pid"],s["request"],sample_count=2000)
        self.assertEqual(frame["original_pcm16le"],s["original_pcm"][:4000])
        self.assertEqual(frame["source_sample_first"],0)
        self.assertEqual(frame["sample_rate_hz"],48000)
        self.assertFalse(frame["audio_voice_model_invoked"])
        changed=deepcopy(s["request"])
        changed["film_time_tick"]=TICKS_PER_SECOND//2
        later=mgr.read_original_voice(s["pid"],changed,sample_count=2000)
        self.assertEqual(later["source_sample_first"],24000)
        self.assertEqual(later["original_pcm16le"],
                         s["original_pcm"][48000:52000])
        self.assertEqual(
            later["original_pcm16le_sha256"],
            sha256(s["original_pcm"][48000:52000]).hexdigest())

    def test_ai_wrong_character_and_wrong_line_are_rejected_not_redistributed(self):
        s=self.state
        mgr=ActorDialogueManager(s["index"])
        variations=[
            ("actor_id",s["people"]["SPHERE"]),
            ("actor_id",s["people"]["BOX"]),
            ("actor_id","0"*32),
            ("script_line_id","Dlg_MadeUp"),
            ("script_document_sha256","0"*64),
            ("selected_performance_id","SphereOldVoice"),
            ("source_take_id","RelayDiscoveryTake"),
            ("source_take_sha256","0"*64),
            ("selection_id","OtherSelection"),
            ("selection_revision",2),
            ("exact_text","Sphere: The relay is still silent."),
            ("exact_text","The relay is coming back online."),
            ("film_time_tick",TICKS_PER_SECOND+1),
        ]
        for key,value in variations:
            with self.subTest(key=key,value=value):
                wrong=dict(s["request"],**{key:value})
                with self.assertRaises((
                        PermissionError,KeyError,ValueError,RuntimeError)):
                    mgr.route(s["pid"],wrong)
        with self.assertRaises(ValueError):
            mgr.route(s["pid"],dict(s["request"],speaker_name="DONUT"))
        with self.assertRaises(ValueError):
            actor_subject("TheDonut")

    def test_native_AI_scene_crew_requires_verified_actorid_delivery(self):
        s=self.state
        context=assemble_film_crew_context(
            s["index"],s["pid"],"RelayRekindleTake",1,0,
            dialogue_selection_id="OriginalDonutDialogueSelection",
            dialogue_selection_revision=1,
            dialogue_route_request=s["request"])
        deliver=context["authoritative_actorid_dialogue_route"]
        self.assertEqual(deliver["actor_id"],s["people"]["DONUT"])
        self.assertEqual(deliver["script_line_id"],s["request"]["script_line_id"])
        self.assertFalse(context[
            "dialogue_source_inspection_is_not_permission_to_speak"])
        observed=assemble_film_crew_context(
            s["index"],s["pid"],"RelayRekindleTake",1,0,
            dialogue_selection_id="OriginalDonutDialogueSelection",
            dialogue_selection_revision=1)
        self.assertTrue(observed[
            "dialogue_source_inspection_is_not_permission_to_speak"])
        self.assertIsNone(observed["authoritative_actorid_dialogue_route"])
        wrong=dict(s["request"],actor_id=s["people"]["SPHERE"])
        with self.assertRaises(PermissionError):
            assemble_film_crew_context(
                s["index"],s["pid"],"RelayRekindleTake",1,0,
                dialogue_selection_id="OriginalDonutDialogueSelection",
                dialogue_selection_revision=1,
                dialogue_route_request=wrong)
        with self.assertRaises(PermissionError):
            assemble_film_crew_context(
                s["index"],s["pid"],"RelayRekindleTake",1,1,
                dialogue_selection_id="OriginalDonutDialogueSelection",
                dialogue_selection_revision=1,
                dialogue_route_request=s["request"])

    def test_reopen_SQLite_keeps_original_identity_and_audio(self):
        s=self.state
        reopened=FilmIndex(Studio(s["root"]/"short.sqlite3"))
        mgr=ActorDialogueManager(reopened)
        result=mgr.route(s["pid"],s["request"])
        self.assertEqual(result["actor_id"],s["people"]["DONUT"])
        voice=mgr.read_original_voice(s["pid"],s["request"],sample_count=2000)
        self.assertEqual(voice["original_pcm16le"],s["original_pcm"][:4000])


class ActorDialogueFailuresMustRemainNonDestructive(unittest.TestCase):
    def test_no_fake_audio_from_metadata_only_actor_performance(self):
        with TemporaryDirectory() as d:
            s=construct_real_original_dialogue(Path(d).resolve(),
                                                recorded_voice=False)
            manager=ActorDialogueManager(s["index"])
            delivery=manager.route(s["pid"],s["request"])
            self.assertFalse(delivery["playable_recorded_voice_available"])
            self.assertTrue(delivery["unrecorded_voice_does_not_become_synthesized"])
            with self.assertRaises(PermissionError):
                manager.read_original_voice(s["pid"],s["request"],
                                            sample_count=2000)

    def test_dropping_voice_bible_link_blocks_voice_routing_but_retains_old_data(self):
        with TemporaryDirectory() as d:
            s=construct_real_original_dialogue(Path(d).resolve(),
                                                recorded_voice=True)
            reg=s["registry"]; aid=s["people"]["DONUT"]
            previous=reg.actor(s["pid"],aid)
            voice_link=next(x for x in previous["active_links"]
                            if x["role"]=="voice")
            retired=reg.retire(s["pid"],aid,voice_link["link_id"],
                               expected_actor_revision=previous["bible_revision"],
                               expected_link_revision=voice_link["link_revision"],
                               reason="Source voice removed from current production cast")
            self.assertTrue(any(x["link_id"]==voice_link["link_id"]
                                and x["status"]=="retired"
                                for x in retired["history"]))
            with self.assertRaises(PermissionError):
                ActorDialogueManager(s["index"]).route(s["pid"],s["request"])
            self.assertEqual(s["index"].read_revision(
                s["pid"],"DonutSourceVoiceFixture",1)["document_sha256"],
                s["audio"]["document_sha256"])

    def test_script_update_never_assigns_the_old_line_to_new_words(self):
        with TemporaryDirectory() as d:
            s=construct_real_original_dialogue(Path(d).resolve())
            s["studio"].save_screenplay(
                s["pid"],REVISED_SCRIPT,expected_revision=1)
            with self.assertRaises(PermissionError):
                ActorDialogueManager(s["index"]).route(s["pid"],s["request"])
            self.assertEqual(s["index"].read_revision(
                s["pid"],"DonutAuthoredOriginalLine",1)["data"][
                    "script_line_text"],"The relay is still silent.")

    def test_director_can_retain_earlier_actor_voice_after_script_rewrite_without_misassigning(self):
        with TemporaryDirectory() as d:
            s=construct_real_original_dialogue(Path(d).resolve(),recorded_voice=True)
            pid=s["pid"]; aid=s["people"]["DONUT"]
            index=s["index"]; registry=s["registry"]
            studio=s["studio"]
            studio.save_screenplay(pid, REVISED_SCRIPT, expected_revision=1)
            # No actor or recording changes automatically after a script edit.
            manager=ActorDialogueManager(index)
            with self.assertRaises(PermissionError):
                manager.route(pid,s["request"])
            writer=ObjectActorDialogue(index,verify_creator_action=creator)
            new=writer.publish_script_snapshot(
                pid,"RelayAuthoredObjectScript",
                expected_screenplay_revision=2,
                expected_manifest_revision=1,
                creator_event=ACTION)
            # Director explicitly links the NEW source revision under the
            # same canonical ActorID, preserving old link history.
            current=registry.actor(pid,aid)
            oldlink=next(x for x in current["active_links"]
                         if x["role"]=="dialogue")
            updated=registry.link(
                pid,aid,role="dialogue",source_family="filmindex",
                target_id="RelayAuthoredObjectScript",target_revision=2,
                expected_actor_revision=current["bible_revision"],
                link_id=oldlink["link_id"],
                expected_link_revision=oldlink["link_revision"],
                director_note="Revised script source; keep old voice for this Take")
            self.assertTrue(any(
                x["link_id"]==oldlink["link_id"] and
                x["target_revision"]==1
                for x in updated["history"]))
            with self.assertRaises(PermissionError):
                writer.publish_scene_dialogue(
                    pid,selection_id="OriginalDonutDialogueSelection",
                    overlay_timeline_id="OriginalDonutDialogueEvents",
                    source_take_id="RelayRekindleTake",
                    source_take_sha256=s["original_take"]["document_sha256"],
                    script_id="RelayAuthoredObjectScript",script_revision=2,
                    performance_ids=["DonutAuthoredOriginalLine"],
                    expected_selection_revision=1,expected_timeline_revision=1,
                    creator_event=ACTION)
            accepted=writer.publish_scene_dialogue(
                pid,selection_id="OriginalDonutDialogueSelection",
                overlay_timeline_id="OriginalDonutDialogueEvents",
                source_take_id="RelayRekindleTake",
                source_take_sha256=s["original_take"]["document_sha256"],
                script_id="RelayAuthoredObjectScript",script_revision=2,
                performance_ids=["DonutAuthoredOriginalLine"],
                expected_selection_revision=1,expected_timeline_revision=1,
                preserve_prior_script_performances=True,
                preservation_reason="Director specifically retains original Donut delivery",
                creator_event=ACTION)
            self.assertEqual(accepted["revision"],2)
            revised_request=dict(
                s["request"],selection_revision=2,
                script_document_sha256=new["document_sha256"])
            delivered=manager.route(pid,revised_request)
            self.assertTrue(delivered["historical_line_explicitly_retained"])
            self.assertEqual(delivered["actor_id"],aid)
            self.assertEqual(delivered["exact_director_selected_text"],
                             "The relay is still silent.")
            self.assertEqual(manager.read_original_voice(
                pid,revised_request,sample_count=2000)["original_pcm16le"],
                s["original_pcm"][:4000])
            # Both source revisions remain independently inspectable.
            self.assertEqual(index.read_revision(pid,
                "OriginalDonutDialogueSelection",1)["document_sha256"],
                s["selected"]["document_sha256"])
            self.assertEqual(index.read_revision(pid,
                "DonutAuthoredOriginalLine",1)["data"]["script_revision"],1)

    def test_cast_is_complete_or_line_cannot_enter_real_scene(self):
        with TemporaryDirectory() as d:
            s=construct_real_original_dialogue(Path(d).resolve())
            reg=s["registry"]; aid=s["people"]["BOX"]
            actor=reg.actor(s["pid"],aid)
            binding=next(x for x in actor["active_links"] if x["role"]=="actor_prim")
            reg.retire(s["pid"],aid,binding["link_id"],
                       expected_actor_revision=actor["bible_revision"],
                       expected_link_revision=binding["link_revision"],
                       reason="Temporarily uncast box; do not give its dialogue away")
            self.assertFalse(reg.casting_coverage(
                s["pid"],"RelayRekindleTake")["complete"])
            with self.assertRaises(RuntimeError):
                ActorDialogueManager(s["index"]).route(s["pid"],s["request"])


if __name__=="__main__":
    unittest.main()
