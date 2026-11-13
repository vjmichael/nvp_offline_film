"""P1-B/C: genuine USD-skinned ActorID, exact original audio dialogue, frozen Takes."""
from pathlib import Path
import struct
import tempfile
import unittest

from pxr import UsdSkel

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_p1bc_actor_registry import (
    ActorDirectory, ActorDialogueDirector,
)
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_openusd_skinning import evaluate_skin
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND

T=TICKS_PER_SECOND


class P1BCActorDialogueNative(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.studio=Studio(Path(temp.name)/"actor.sqlite3")
        self.pid=self.studio.create_project("P1B-C actor original performance", "")["id"]
        self.index=FilmIndex(self.studio)
        self.actors=ActorDirectory(
            self.index,verify_director_action=lambda event,scope:
            event=="human_approved" and scope["operation"]=="nvp.p1bc.register_actor.v1")
        self.dialogue=ActorDialogueDirector(
            self.index,verify_director_action=lambda event,scope:
            event=="human_approved" and
            scope["operation"]=="nvp.p1bc.bind_original_dialogue.v1")
        self.scenes=OpenUSDSceneBridge(self.index)
        self.timelines=TemporalLedger(self.index)
        self.actors.register(self.pid,"ActorLead",display_name="Original Lead",
                             creator_event="human_approved")
        self.prims=[
            {"path":"/World/Lead","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,1,6]},
            {"path":"/World/Light","role":"light","position":[2,3,2]},
        ]
        self.rigs=[{"path":"/World/Lead",
                    "joints":["Root","Root/Hand"],
                    "samples":[
                        {"tick":0,"translations":[[0,0,0],[0,0,0]]},
                        {"tick":T,"translations":[[0,0,0],[2,0,0]]},
                    ],
                    "skin":{
                        "points":[[0,0,0],[0,1,0],[0,1,1],[0,0,1]],
                        "faces":[[0,1,2],[0,2,3]],
                        "joint_indices":[[1],[1],[1],[1]],
                        "joint_weights":[[1.0],[1.0],[1.0],[1.0]],
                        "display_color":[0.8,0.4,0.2],
                    }}]
        self.cast=[{"actor_id":"ActorLead","actor_revision":1,
                    "path":"/World/Lead"}]
        self.scene=self.scenes.publish(
            self.pid,"SceneLead",prims=self.prims,curves=[],
            native_schemas=True,skeletal_rigs=self.rigs,actor_bindings=self.cast)
        self.audio=RecordedSoundSources(self.index).publish(
            self.pid,"MicLead",[struct.pack("<h",2111)*48000])
        self.timeline=self.timelines.publish(
            self.pid,"TimelineLead",[{
                "event_id":"LineOne","event_kind":"dialogue",
                "subject_id":"ActorLead","start_tick":0,"end_tick":T,
                "source_id":"MicLead","source_revision":1,
                "payload":{"usd_prim_path":"/World/Lead","gain":1.0},
            }],duration_tick=2*T)
        self.takes=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
            event=="human_approved" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.take=self.takes.freeze(
            self.pid,"TakeLead",scene_id="SceneLead",scene_revision=1,
            timeline_id="TimelineLead",timeline_revision=1,
            sample_ticks=[0,T],creator_event="human_approved")

    def test_actor_identity_is_immutable_scene_and_real_skinned_3d_performance(self):
        scene,usd=self.scenes.open(self.pid,"SceneLead",1)
        self.assertEqual(scene["data"]["actor_bindings"][0]["actor_id"],"ActorLead")
        self.assertEqual(
            usd.GetPrimAtPath("/World/Lead").GetAttribute("nvp:actorId").Get(),
            "ActorLead")
        self.assertTrue(usd.GetPrimAtPath(
            "/World/Lead/Rig/Skeleton").IsA(UsdSkel.Skeleton))
        deformed=evaluate_skin(
            usd,usd.GetPrimAtPath("/World/Lead/Rig/CharacterMesh"),
            "/World/Lead",T//2)
        self.assertTrue(deformed["usd_skin_binding_verified"])
        self.assertTrue(deformed["skinning_evaluated"])
        self.assertGreater(deformed["deformed_points"][0][0],0)
        state=OpenUSDTimeState(self.index).evaluate(
            self.pid,"SceneLead",1,"TimelineLead",1,tick=T//2)
        actor=next(obj for obj in state["objects"]
                   if obj["path"]=="/World/Lead")
        self.assertEqual(actor["actor_id"],"ActorLead")
        self.assertEqual(state["skeletal_pose"][0]["actor_id"],"ActorLead")
        self.assertEqual(self.takes.verify_take(
            self.pid,"TakeLead")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        take=self.index.read_revision(self.pid,"TakeLead",1)
        self.assertEqual(take["data"]["actor_bindings"],
                         scene["data"]["actor_bindings"])

    def test_original_dialogue_actor_source_and_film_time_survive_restart(self):
        output=self.dialogue.bind(
            self.pid,"LeadLineOne",actor_id="ActorLead",
            take_id="TakeLead",event_id="LineOne",creator_event="human_approved")
        self.assertEqual(output["kind"],"dialogue")
        self.assertEqual(
            {(d["object_id"],d["role"]) for d in output["dependencies"]},
            {("ActorLead","actor"),("SceneLead","scene"),
             ("TakeLead","source_take"),("TimelineLead","temporal"),
             ("MicLead","audio")})
        active=self.dialogue.at(self.pid,"LeadLineOne",1,T//2)
        self.assertTrue(active["dialogue_active"])
        self.assertFalse(active["voice_synthesized"])
        self.assertFalse(active["lip_sync_generated"])
        self.assertEqual(active["usd_prim_path"],"/World/Lead")
        self.assertEqual(active["source_event_id"],"LineOne")
        self.assertFalse(self.dialogue.at(
            self.pid,"LeadLineOne",1,T)["dialogue_active"])
        restarted=FilmIndex(Studio(self.studio.db_path))
        reopened=ActorDialogueDirector(
            restarted,verify_director_action=lambda *_:False)
        self.assertEqual(
            reopened.at(self.pid,"LeadLineOne",1,T//2),active)
        self.assertEqual(OpenUSDTakeCapture(
            restarted,verify_creator_action=lambda *_:False).verify_take(
            self.pid,"TakeLead")["status"],"VERIFIED_FROZEN_DATA_TAKE")

    def test_unknown_cross_project_or_duplicate_actor_prim_is_denied(self):
        other=self.studio.create_project("Other film","")["id"]
        with self.assertRaises(KeyError):
            self.scenes.publish(
                other,"OtherWorld",prims=self.prims,curves=[],
                native_schemas=True,skeletal_rigs=self.rigs,
                actor_bindings=self.cast)
        with self.assertRaises(ValueError):
            self.scenes.publish(
                self.pid,"DuplicateActor",prims=self.prims,curves=[],
                native_schemas=True,skeletal_rigs=self.rigs,
                actor_bindings=self.cast+self.cast)
        with self.assertRaises(KeyError):
            self.dialogue.bind(
                self.pid,"UnknownSpeaker",actor_id="ActorOther",
                take_id="TakeLead",event_id="LineOne",
                creator_event="human_approved")

    def test_unrigged_or_unweighted_actor_never_receives_actor_identity(self):
        with self.assertRaises(ValueError):
            self.scenes.publish(
                self.pid,"NoRigActor",prims=self.prims,curves=[],
                actor_bindings=self.cast)
        unweighted=[{k:v for k,v in self.rigs[0].items() if k!="skin"}]
        with self.assertRaises(ValueError):
            self.scenes.publish(
                self.pid,"NoSkinActor",prims=self.prims,curves=[],
                native_schemas=True,skeletal_rigs=unweighted,
                actor_bindings=self.cast)

    def test_wrong_subject_and_refused_binding_leave_no_dialogue(self):
        # Speaker cannot be guessed by GLB filenames or UI text.
        self.actors.register(
            self.pid,"ActorOther",display_name="Second actor",
            creator_event="human_approved")
        with self.assertRaisesRegex(RuntimeError,"no unique rigged scene"):
            self.dialogue.bind(
                self.pid,"FalseLine",actor_id="ActorOther",
                take_id="TakeLead",event_id="LineOne",
                creator_event="human_approved")
        with self.assertRaises(PermissionError):
            self.dialogue.bind(
                self.pid,"DeniedLine",actor_id="ActorLead",
                take_id="TakeLead",event_id="LineOne",
                creator_event="refused")
        for identity in ("FalseLine","DeniedLine"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_actor_binding_old_take_survives_new_scene_head(self):
        self.scenes.publish(
            self.pid,"SceneLead",prims=self.prims,curves=[],
            native_schemas=True,skeletal_rigs=self.rigs,
            actor_bindings=self.cast,expected_revision=1)
        self.assertEqual(self.takes.verify_take(
            self.pid,"TakeLead")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(
            self.scenes.open(self.pid,"SceneLead",1)[0]["document_sha256"],
            self.scene["document_sha256"])


if __name__=="__main__":
    unittest.main()
