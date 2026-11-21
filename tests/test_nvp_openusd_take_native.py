"""USD-01 native acceptance: real OpenUSD composition, event binding, frozen Take."""
import tempfile
import unittest
from pathlib import Path

from pxr import Usd, UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_temporal_projection import TemporalProjection
from backend.nvp_openusd_scene import OpenUSDSceneBridge, MAX_USD_EXACT_TICK
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_presentation import OpenUSDPresentationPlanner

T = TICKS_PER_SECOND


class OpenUSDNativeIntegration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio=Studio(Path(self.temp.name)/"studio.sqlite")
        self.pid=self.studio.create_project(
            "One performance, two presentations","OpenUSD integration")["id"]
        self.film=FilmIndex(self.studio)
        self.temporal=TemporalLedger(self.film)
        self.scenes=OpenUSDSceneBridge(self.film)
        self.take=OpenUSDTakeCapture(
            self.film,verify_creator_action=lambda event,scope:
            event=="creator_authorized" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,3,-8]},
            {"path":"/World/Prop","role":"prop","position":[5,0,0]},
        ]
        self.motion=[
            {"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[10,0,0]}]},
            {"path":"/World/Camera","samples":[
                {"tick":0,"position":[0,3,-8]},
                {"tick":2*T,"position":[2,3,-8]}]},
        ]
        self.scenes.publish(self.pid,"scene_usd",prims=self.prims,
                            curves=self.motion)
        self.film.register_revision(
            self.pid,"actor_performance","performance",
            {"format":"test.actor.performance.v1",
             "actor":"Actor","motion":"walk"},expected_revision=0)
        self.temporal.publish(self.pid,"action_timeline",[
            {"event_id":"walk_across","event_kind":"action",
             "subject_id":"Actor","start_tick":0,"end_tick":2*T,
             "source_id":"actor_performance","source_revision":1,
             "payload":{"verb":"walk","usd_prim_path":"/World/Actor"}},
        ],duration_tick=3*T)

    def test_two_layers_recompose_and_evaluate_halfway_without_render(self):
        rec,usd=self.scenes.open(self.pid,"scene_usd",1)
        self.assertEqual(rec["kind"],"scene")
        self.assertEqual(rec["data"]["layer_order"],["motion","layout"])
        self.assertTrue(usd.GetPrimAtPath("/World/Actor").IsDefined())
        self.assertGreaterEqual(len(usd.GetUsedLayers()),3)
        self.assertEqual(usd.GetTimeCodesPerSecond(),float(T))
        half=self.scenes.evaluate(
            self.pid,"scene_usd",1,path="/World/Actor",tick=T)
        self.assertAlmostEqual(half["world_translation"][0],5.0,places=5)
        self.assertFalse(half["frames_rendered"])
        camera=self.scenes.evaluate(
            self.pid,"scene_usd",1,path="/World/Camera",tick=T)
        self.assertAlmostEqual(camera["world_translation"][0],1.0,places=5)
        other=OpenUSDSceneBridge(FilmIndex(Studio(self.studio.db_path)))
        self.assertEqual(
            other.evaluate(self.pid,"scene_usd",1,path="/World/Actor",
                           tick=T)["world_translation"],half["world_translation"])

    def test_freeze_real_immutable_take_and_two_presentations(self):
        frozen=self.take.freeze(
            self.pid,"frozen_take_a",scene_id="scene_usd",scene_revision=1,
            timeline_id="action_timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="creator_authorized")
        self.assertEqual(frozen["revision"],1)
        take_doc=self.film.read_revision(self.pid,"frozen_take_a",1)
        self.assertEqual(take_doc["kind"],"take")
        self.assertEqual(
            {x["role"] for x in take_doc["dependencies"]},
            {"scene","temporal"})
        evidence=self.take.verify_take(self.pid,"frozen_take_a")
        self.assertEqual(evidence["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertFalse(evidence["rendered_frames"])
        p=TemporalProjection(self.temporal)
        a=p.prepare(self.pid,"action_timeline",1,
            start_tick=T,end_tick=2*T,fps_num=24,fps_den=1)
        b=p.prepare(self.pid,"action_timeline",1,
            start_tick=T,end_tick=2*T,fps_num=60,fps_den=1)
        self.assertEqual(len(a["presentation_samples"]),24)
        self.assertEqual(len(b["presentation_samples"]),60)
        self.assertEqual(a["timeline_document_sha256"],
                         b["timeline_document_sha256"])
        # One frozen Take ID can be the basis of two presentation plans.
        self.assertEqual(self.take.verify_take(
            self.pid,"frozen_take_a")["take_document_sha256"],
            evidence["take_document_sha256"])
        with self.assertRaises(RuntimeError):
            self.take.freeze(self.pid,"frozen_take_a",
                scene_id="scene_usd",scene_revision=1,
                timeline_id="action_timeline",timeline_revision=1,
                sample_ticks=[0,T],creator_event="creator_authorized")

    def test_new_scene_revision_does_not_rewrite_previous_take(self):
        self.take.freeze(self.pid,"take_old",
            scene_id="scene_usd",scene_revision=1,
            timeline_id="action_timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="creator_authorized")
        revised=[{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":2*T,"position":[20,0,0]}]}]
        self.scenes.publish(self.pid,"scene_usd",
            prims=self.prims,curves=revised,expected_revision=1)
        old=self.scenes.evaluate(self.pid,"scene_usd",1,
            path="/World/Actor",tick=T)["world_translation"][0]
        new=self.scenes.evaluate(self.pid,"scene_usd",2,
            path="/World/Actor",tick=T)["world_translation"][0]
        self.assertAlmostEqual(old,5)
        self.assertAlmostEqual(new,10)
        self.assertEqual(self.take.verify_take(
            self.pid,"take_old")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(self.film.direct_dependents(self.pid,"scene_usd",1),
                         [{"object_id":"take_old","revision":1}])

    def test_two_style_presentation_plans_share_one_frozen_performance(self):
        self.take.freeze(
            self.pid,"take_for_styles",scene_id="scene_usd",scene_revision=1,
            timeline_id="action_timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="creator_authorized")
        self.film.register_revision(self.pid,"photo_style","style",
            {"format":"nvp.style.test","profile":"photoreal"},
            expected_revision=0)
        self.film.register_revision(self.pid,"toon_style","style",
            {"format":"nvp.style.test","profile":"stylized"},
            expected_revision=0)
        planner=OpenUSDPresentationPlanner(self.film)
        a=planner.prepare(
            self.pid,"take_for_styles",style_id="photo_style",style_revision=1,
            start_tick=T,end_tick=2*T,fps_num=24,fps_den=1)
        b=planner.prepare(
            self.pid,"take_for_styles",style_id="toon_style",style_revision=1,
            start_tick=T,end_tick=2*T,fps_num=60,fps_den=1)
        self.assertEqual(len(a["presentation_samples"]),24)
        self.assertEqual(len(b["presentation_samples"]),60)
        self.assertNotEqual(a["style_document_sha256"],b["style_document_sha256"])
        self.assertEqual(a["frozen_take_document_sha256"],
                         b["frozen_take_document_sha256"])
        self.assertFalse(a["frames_rendered"])
        self.assertFalse(a["source_full_audit_this_operation"])
        self.assertTrue(a["revision_metadata_bound"])
        self.assertEqual(a["output"],"DATA_ONLY_NOT_RENDERED")
        # Compare authored time = one second, not an arbitrary frame identity.
        actor_a=next(p for p in a["presentation_samples"][0]["world_state"]
                     if p["prim_path"]=="/World/Actor")
        actor_b=next(p for p in b["presentation_samples"][0]["world_state"]
                     if p["prim_path"]=="/World/Actor")
        self.assertEqual(actor_a["world_translation"],actor_b["world_translation"])

    def test_no_permission_no_freeze_and_missing_prim_rejection(self):
        with self.assertRaises(PermissionError):
            self.take.freeze(self.pid,"take_denied",
                scene_id="scene_usd",scene_revision=1,
                timeline_id="action_timeline",timeline_revision=1,
                sample_ticks=[0,T],creator_event="not_approved")
        with self.assertRaises(KeyError):
            self.film.read_revision(self.pid,"take_denied",1)
        self.temporal.publish(self.pid,"bad_timeline",[
            {"event_id":"bad","event_kind":"action",
             "subject_id":"Actor","start_tick":0,"end_tick":2*T,
             "source_id":"actor_performance","source_revision":1,
             "payload":{"usd_prim_path":"/World/Missing"}}
        ],duration_tick=3*T)
        with self.assertRaises(RuntimeError):
            self.take.freeze(self.pid,"take_bad_prim",
                scene_id="scene_usd",scene_revision=1,
                timeline_id="bad_timeline",timeline_revision=1,
                sample_ticks=[0],creator_event="creator_authorized")

    def test_invalid_time_source_scope_and_unsafe_prim_paths(self):
        with self.assertRaises(ValueError):
            self.scenes.publish(self.pid,"escape_scene",
                prims=[{"path":"/Outside/Actor","role":"actor",
                        "position":[0,0,0]}],curves=[])
        with self.assertRaises(ValueError):
            self.scenes.publish(self.pid,"bad_curve",
                prims=self.prims,curves=[{
                    "path":"/World/Actor",
                    "samples":[{"tick":T,"position":[1,0,0]},
                               {"tick":0,"position":[2,0,0]}]}])
        with self.assertRaises(ValueError):
            self.scenes.evaluate(self.pid,"scene_usd",1,
                path="/World/Actor",tick=MAX_USD_EXACT_TICK+1)
        other=self.studio.create_project("Other film","")["id"]
        with self.assertRaises(KeyError):
            self.scenes.evaluate(other,"scene_usd",1,
                path="/World/Actor",tick=T)


if __name__=="__main__":
    unittest.main()
