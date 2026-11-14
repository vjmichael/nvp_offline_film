"""SHOT-01 real native OpenUSD director-specific cinematic staging acceptance."""
import tempfile
import unittest
from pathlib import Path

from pxr import Usd, UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_openusd_presentation import OpenUSDPresentationPlanner

T=TICKS_PER_SECOND


class DirectorOpenUSDShotNativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/"film.sqlite")
        self.project=self.studio.create_project(
            "One scene, many artistic angles","Continuity film")["id"]
        self.index=FilmIndex(self.studio)
        self.scenes=OpenUSDSceneBridge(self.index)
        self.temporal=TemporalLedger(self.index)
        self.take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
            event=="freeze_yes" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.shots=OpenUSDShotOverrides(
            self.index,verify_director_action=lambda event,scope:
            event=="director_accepts" and
            scope["operation"]=="nvp.usd.director_shot_override.v1" and
            scope["final_render_approval"] is False)
        self.prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Chair","role":"prop","position":[3,0,1]},
            {"path":"/World/Camera","role":"camera","position":[0,2,-8]},
            {"path":"/World/Light","role":"light","position":[2,4,0]},
        ]
        self.curves=[
            {"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[10,0,0]}]}
        ]
        self.scenes.publish(
            self.project,"scene",prims=self.prims,curves=self.curves)
        self.index.register_revision(
            self.project,"actor_source","performance",
            {"format":"nvp.shot.test.actor.v1","actor":"walk"})
        self.temporal.publish(self.project,"timeline",[{
            "event_id":"walk","event_kind":"action",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"actor_source","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor","action":"walk"},
        }],duration_tick=3*T)
        self.take.freeze(
            self.project,"frozen_take",scene_id="scene",scene_revision=1,
            timeline_id="timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="freeze_yes")

    def publish(self,shot,*,start=0,end=T,changes=None,
                continuity="intentional_cheat",reason=None,
                creator="director_accepts",expected=0):
        return self.shots.publish(
            self.project,shot,take_id="frozen_take",
            start_tick=start,end_tick=end,
            changes=changes if changes is not None else [
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[2,0,0]},
                {"path":"/World/Chair","property":"translation_offset",
                 "value":[-1,0,0]},
                {"path":"/World/Chair","property":"visibility","value":False},
            ],purpose="framing",continuity_policy=continuity,
            reason=reason or "Director moved performers and prop for clean angle",
            creator_event=creator,expected_revision=expected)

    def test_one_canonical_performance_two_shot_stagings(self):
        a=self.publish("angle_a")
        b=self.publish("angle_b",start=T,end=2*T,changes=[
            {"path":"/World/Actor","property":"translation_offset",
             "value":[-1,0,0]},
            {"path":"/World/Chair","property":"visibility","value":True},
        ],continuity="preserve",reason="Reverse angle keeps actor readable")
        first=self.shots.evaluate(
            self.project,"angle_a",1,tick=T//2)
        second=self.shots.evaluate(
            self.project,"angle_b",1,tick=T+T//2)
        actor_a=next(v for v in first["changes"] if v["path"]=="/World/Actor")
        actor_b=next(v for v in second["changes"] if v["path"]=="/World/Actor")
        self.assertAlmostEqual(actor_a["canonical_world_translation"][0],2.5)
        self.assertAlmostEqual(actor_a["shot_world_translation"][0],4.5)
        self.assertAlmostEqual(actor_b["canonical_world_translation"][0],7.5)
        self.assertAlmostEqual(actor_b["shot_world_translation"][0],6.5)
        chair=next(v for v in first["changes"] if v["path"]=="/World/Chair")
        self.assertEqual(chair["shot_visibility"],"invisible")
        self.assertAlmostEqual(chair["shot_world_translation"][0],2.0)
        self.assertEqual(first["source_take_document_sha256"],
                         second["source_take_document_sha256"])
        self.assertNotEqual(a["document_sha256"],b["document_sha256"])
        self.assertFalse(first["source_performance_modified"])
        self.assertFalse(first["rendered_frames"])
        self.assertEqual(self.take.verify_take(
            self.project,"frozen_take")["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertAlmostEqual(self.scenes.evaluate(
            self.project,"scene",1,path="/World/Actor",
            tick=T//2)["world_translation"][0],2.5)

    def test_presentation_plans_use_shot_only_without_rewriting_take(self):
        self.publish("closeup")
        self.index.register_revision(
            self.project,"realistic","style",
            {"format":"nvp.style.test.v1","profile":"realistic"})
        planner=OpenUSDPresentationPlanner(self.index)
        common=dict(project_id=self.project,take_id="frozen_take",
                    style_id="realistic",style_revision=1,
                    start_tick=0,end_tick=T,fps_den=1)
        baseline=planner.prepare(**common,fps_num=24)
        angle24=planner.prepare(
            **common,fps_num=24,shot_id="closeup",shot_revision=1)
        angle60=planner.prepare(
            **common,fps_num=60,shot_id="closeup",shot_revision=1)
        def actor_x(plan):
            return next(p["world_translation"][0] for p in
                        plan["presentation_samples"][0]["world_state"]
                        if p["prim_path"]=="/World/Actor")
        self.assertAlmostEqual(actor_x(baseline),0.0)
        self.assertAlmostEqual(actor_x(angle24),2.0)
        self.assertAlmostEqual(actor_x(angle60),2.0)
        self.assertEqual(angle24["frozen_take_document_sha256"],
                         angle60["frozen_take_document_sha256"])
        self.assertEqual(angle24["frozen_take_document_sha256"],
                         baseline["frozen_take_document_sha256"])
        self.assertTrue(angle24["intentional_continuity_cheat"])
        self.assertFalse(angle24["render_approved"])
        self.assertFalse(angle24["frames_rendered"])
        with self.assertRaises((ValueError,RuntimeError)):
            planner.prepare(
                self.project,"frozen_take",style_id="realistic",
                style_revision=1,start_tick=T,end_tick=2*T,
                fps_num=24,fps_den=1,
                shot_id="closeup",shot_revision=1)

    def test_old_shot_revision_survives_new_directors_choice_and_restart(self):
        self.publish("blocking_a")
        self.publish("blocking_a",changes=[
            {"path":"/World/Actor","property":"translation_offset",
             "value":[4,0,0]}],reason="Close framing with offset mark",
            expected=1)
        old=self.shots.evaluate(
            self.project,"blocking_a",1,tick=T//2)
        new=self.shots.evaluate(
            self.project,"blocking_a",2,tick=T//2)
        self.assertAlmostEqual(old["changes"][0]["shot_world_translation"][0],
                               4.5)
        self.assertAlmostEqual(new["changes"][0]["shot_world_translation"][0],
                               6.5)
        reopened=OpenUSDShotOverrides(
            FilmIndex(Studio(self.studio.db_path)),
            verify_director_action=lambda *_:False)
        self.assertEqual(
            reopened.evaluate(self.project,"blocking_a",1,
                              tick=T//2)["shot_document_sha256"],
            old["shot_document_sha256"])
        self.assertEqual(self.take.verify_take(
            self.project,"frozen_take")["status"],"VERIFIED_FROZEN_DATA_TAKE")

    def test_cut_scoping_and_missing_authority(self):
        self.publish("cut_a")
        for wrong_tick in (T,2*T):
            with self.assertRaises(ValueError):
                self.shots.evaluate(self.project,"cut_a",1,tick=wrong_tick)
        with self.assertRaises(PermissionError):
            self.publish("unapproved",creator="model_proposed")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.project,"unapproved",1)
        bad=[
            {"path":"/World/Stranger","property":"translation_offset",
             "value":[1,0,0]}]
        with self.assertRaises(ValueError):
            self.publish("bad_path",changes=bad)
        with self.assertRaises(ValueError):
            self.publish("duplicate",changes=[
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[1,0,0]},
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[2,0,0]},
            ])
        with self.assertRaises(ValueError):
            self.publish("nan",changes=[
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[float("nan"),0,0]}])

    def test_eyeline_is_metadata_not_unverified_ik(self):
        self.publish("eyeline",changes=[
            {"path":"/World/Actor","property":"eyeline_target",
             "value":[4,2,7]}],continuity="intentional_cheat",
             reason="Aim eyeline toward off-camera actor")
        result=self.shots.evaluate(
            self.project,"eyeline",1,tick=T//2)
        self.assertFalse(result["eyeline_ik_applied"])
        self.assertEqual(result["changes"][0]["opinions"][0]["value"],[4.,2.,7.])
        _,_,stage=self.shots.open_shot(
            self.project,"eyeline",1,tick=T//2)
        self.assertTrue(stage.GetPrimAtPath("/World/Actor").GetAttribute(
            "nvp:shot:eyelineTarget").IsValid())

    def test_shot_only_camera_and_light_properties_on_native_usd(self):
        self.scenes.publish(
            self.project,"native_scene",prims=self.prims,
            curves=self.curves,native_schemas=True)
        self.take.freeze(
            self.project,"native_take",scene_id="native_scene",scene_revision=1,
            timeline_id="timeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="freeze_yes")
        self.shots.publish(
            self.project,"lens_light",take_id="native_take",
            start_tick=0,end_tick=T,purpose="lighting",
            continuity_policy="intentional_cheat",
            reason="Soft portrait lens and gentler key light for this angle",
            changes=[
                {"path":"/World/Camera","property":"camera_focal_length_mm",
                 "value":85.0},
                {"path":"/World/Light","property":"light_intensity",
                 "value":200.0},
            ],creator_event="director_accepts")
        snapshot=self.shots.evaluate(
            self.project,"lens_light",1,tick=T//2)
        values={x["path"]:x for x in snapshot["changes"]}
        self.assertAlmostEqual(values["/World/Camera"]["shot_focal_length_mm"],
                               85.0,places=4)
        self.assertAlmostEqual(values["/World/Light"]["shot_light_intensity"],
                               200.0,places=4)
        _,native=self.scenes.open(self.project,"native_scene",1)
        canonical=UsdGeom.Camera(native.GetPrimAtPath("/World/Camera"))
        self.assertNotAlmostEqual(float(canonical.GetFocalLengthAttr().Get(
            Usd.TimeCode(float(T//2))))*100.0,85.0,places=3)

    def test_no_cross_project_shot_source(self):
        alien=self.studio.create_project("Other film","")["id"]
        with self.assertRaises(KeyError):
            self.shots.publish(
                alien,"bad_foreign_take",take_id="frozen_take",
                start_tick=0,end_tick=T,
                purpose="framing",continuity_policy="preserve",
                reason="Not authorized project",creator_event="director_accepts",
                changes=[{"path":"/World/Actor",
                          "property":"translation_offset","value":[1,0,0]}])


if __name__=="__main__":
    unittest.main()
