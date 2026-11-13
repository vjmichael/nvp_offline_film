"""P1-D/E/F/P2 original film-source integration, no simulated native Blender pass.

The P1-F renderer callback here is an explicit deterministic test double.
Tests establish source SHA custody, WAV/picture structure, native authorization,
atomic delivery and longform source paging. The real contained Blender/Cycles
acceptance is a SEPARATE matrix, never inferred from this fixture.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
import struct
import wave

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
from backend.nvp_p1e_actor_spatial_bus import NativeActorSpatialBus
from backend.nvp_p1f_sustained_delivery import NativeSustainedPictureSound
from backend.nvp_p2_longform_source_plan import NativeLongformFilmPlan
from backend.nvp_p1bc_actor_registry import ActorDialogueDirector
from tests.test_nvp_slate06_geometry_native import Slate06NativeTests
from tests.test_nvp_p1bc_glb_scene_native import OriginalImportedGLBAndActing
from tests.test_nvp_slate05_preview_native import _png

T=TICKS_PER_SECOND


class OriginalP1DEditorAndP1FOutput(unittest.TestCase):
    def setUp(self):
        self.original=Slate06NativeTests(methodName="runTest")
        self.original.setUp()
        self.addCleanup(self.original.doCleanups)
        self.index=self.original.index
        self.pid=self.original.pid
        self.continuity=NativeEditorialContinuity(
            self.original.editor,verify_director_action=lambda action,scope:
            action=="director_yes" and
            scope["operation"]=="nvp.p1d.commit_director_continuity.v1")
        # The previous source cut deliberately uses a director shot that
        # translates the actor. P1-F MUST reject its uncomposed spatial audio.
        # Positive delivery instead uses the unchanged original-source branch.
        self.original.editor.commit(
            self.pid,"cut_no_shot",graph_id="slate",graph_revision=1,
            segments=[{"segment_id":"original_part","branch_id":"original",
                       "source_in_tick":T,"source_out_tick":2*T}],
            editor_event="commit_cut")
        self.cue={"segment_id":"original_part","continuity":"accepted",
                  "audio_policy":"original_scene","note":"Actor movement is original"}
        self.c=self.continuity.publish(
            self.pid,"DirectorCutProof",edit_id="cut_no_shot",edit_revision=1,
            cues=[self.cue],creator_event="director_yes")
        self.exporter=NativeSustainedPictureSound(
            self.original.editor,self.continuity,
            native_creator_approval=lambda scope:
                scope["operation"]=="nvp.p1f.authorize_original_finite_chunk.v1",
            render_png=self._render)
        self.calls=[]

    def _render(self,*,scope,tick,camera_path,source_snapshot):
        self.calls.append((tick,camera_path,scope["source_take_sha256"]))
        self.assertEqual(camera_path,"/World/Camera")
        self.assertEqual(source_snapshot["scene_document_sha256"],
                         self.index.read_revision(self.pid,"world",1)["document_sha256"])
        self.assertFalse(scope["render_approved"])
        return _png(64,64)

    def test_director_review_and_source_tick_survive_restart(self):
        before=self.index.read_revision(self.pid,"take",1)["document_sha256"]
        detail=self.continuity.at(self.pid,"DirectorCutProof",1,0)
        self.assertEqual(detail["source_tick"],T)
        self.assertIsNone(detail["source_shot_id"])
        self.assertFalse(detail["render_approved"])
        fresh=NativeEditorialContinuity(
            SlateSequenceAssembly(DigitalSlateBranches(
                FilmIndex(Studio(self.original.studio.db_path)),
                verify_editor_action=lambda *_:False),
                verify_editor_action=lambda *_:False),
            verify_director_action=lambda *_:False)
        self.assertEqual(fresh.at(self.pid,"DirectorCutProof",1,0),detail)
        self.assertEqual(self.index.read_revision(self.pid,"take",1)[
            "document_sha256"],before)

    def test_refusal_stale_cues_and_review_require_separate_export_permission(self):
        before=self.index.read_revision(self.pid,"cut_no_shot",1)["document_sha256"]
        with self.assertRaises(ValueError):
            self.continuity.publish(self.pid,"BadCut",edit_id="cut_no_shot",
                edit_revision=1,cues=[{**self.cue,"segment_id":"unknown"}],
                creator_event="director_yes")
        refused=NativeEditorialContinuity(
            self.original.editor,verify_director_action=lambda *_:False)
        with self.assertRaises(PermissionError):
            refused.publish(self.pid,"Refused",edit_id="cut_no_shot",
                edit_revision=1,cues=[self.cue],creator_event="no")
        review=self.continuity.publish(
            self.pid,"Unreviewed",edit_id="cut_no_shot",edit_revision=1,
            cues=[{**self.cue,"continuity":"needs_review"}],
            creator_event="director_yes")
        self.assertEqual(review["revision"],1)
        with self.assertRaises(PermissionError):
            self.exporter.preflight(
                self.pid,"Unreviewed",1,first_frame=0,frame_count=2,
                listener_path="/World/Camera",camera_path="/World/Camera")
        self.assertEqual(self.index.read_revision(self.pid,"cut_no_shot",1)[
            "document_sha256"],before)

    def test_atomic_pictures_original_sound_and_independent_verification(self):
        with TemporaryDirectory() as tmp:
            target=self.exporter.export_chunk(
                self.pid,"DirectorCutProof",1,"P2FilmChunk000000",tmp,
                first_frame=0,frame_count=2,listener_path="/World/Camera",
                camera_path="/World/Camera")
            self.assertEqual(target["status"],"INDEPENDENT_SOURCE_CHUNK_VERIFIED")
            self.assertFalse(target["full_film_master_approved"])
            self.assertEqual(len(self.calls),2)
            self.assertEqual(self.calls[0][0],T)
            self.assertEqual(self.calls[1][0],T+T//24)
            folder=Path(target["file_path"])
            with wave.open(str(folder/"soundtrack.wav"),"rb") as wav:
                self.assertEqual(wav.getnframes(),4000)
                self.assertEqual(wav.getframerate(),48000)
            reopen=NativeSustainedPictureSound(
                self.original.editor,self.continuity,
                native_creator_approval=lambda *_:False,
                render_png=lambda **_: (_ for _ in ()).throw(
                    AssertionError("A verified chunk must never rerender")))
            self.assertEqual(reopen.verify_chunk(self.pid,folder)["manifest_sha256"],
                             target["manifest_sha256"])
            (folder/"pictures"/"000001.png").write_bytes(b"tampered")
            with self.assertRaises(RuntimeError):
                reopen.verify_chunk(self.pid,folder)
            self.assertEqual(self.exporter.abandoned_stages(tmp),[])

    def test_moving_shot_with_uncomposed_spatial_audio_rejected_preapproval(self):
        self.continuity.publish(
            self.pid,"ShotNeedsAudio",edit_id="cut",edit_revision=1,
            cues=[{"segment_id":"angle_part","continuity":"accepted",
                   "audio_policy":"original_scene","note":"Director has moved actor"}],
            creator_event="director_yes")
        with self.assertRaisesRegex(RuntimeError,"composed acoustic mixer"):
            self.exporter.preflight(
                self.pid,"ShotNeedsAudio",1,first_frame=0,frame_count=2,
                listener_path="/World/Camera",camera_path="/World/Camera")
        self.assertEqual(self.calls,[])

    def test_native_refusal_and_boundaries_never_publish_partial(self):
        refused=NativeSustainedPictureSound(
            self.original.editor,self.continuity,
            native_creator_approval=lambda *_:False,
            render_png=lambda **_:self.fail("Unapproved Blender render"))
        with TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):
                refused.export_chunk(self.pid,"DirectorCutProof",1,
                    "RejectedChunk",tmp,first_frame=0,frame_count=2,
                    listener_path="/World/Camera",camera_path="/World/Camera")
            self.assertEqual(list(Path(tmp).iterdir()),[])
            with self.assertRaises(ValueError):
                self.exporter.preflight(
                    self.pid,"DirectorCutProof",1,first_frame=23,frame_count=2,
                    listener_path="/World/Camera",camera_path="/World/Camera")
            with self.assertRaises(ValueError):
                self.exporter.preflight(
                    self.pid,"DirectorCutProof",1,first_frame=0,frame_count=2,
                    listener_path="/World/Actor",camera_path="/World/Actor")
            self.assertEqual(self.calls,[])

    def test_p2_plan_rehearsal_pages_and_independent_completion(self):
        scheduler=NativeLongformFilmPlan(
            self.original.editor,self.continuity,
            verify_creator_action=lambda event,scope:
            event=="director_yes" and
            scope["operation"]=="nvp.p2.authorize_original_longform_source_plan.v1")
        result=scheduler.publish(
            self.pid,"P2OriginalPlan",continuity_id="DirectorCutProof",
            continuity_revision=1,listener_path="/World/Camera",
            camera_path="/World/Camera",creator_event="director_yes")
        self.assertEqual(result["revision"],1)
        record=scheduler.open(self.pid,"P2OriginalPlan",1)
        self.assertEqual(record["data"]["total_frames"],24)
        self.assertEqual(record["data"]["total_chunks"],1)
        self.assertFalse(record["data"]["is_thirty_minute_longform"])
        with TemporaryDirectory() as tmp:
            self.assertEqual(
                scheduler.reconcile_all(
                    self.pid,"P2OriginalPlan",1,output_parent=tmp)["status"],
                "INCOMPLETE_ORIGINAL_SOURCE_DERIVATIVES")
            self.exporter.export_chunk(
                self.pid,"DirectorCutProof",1,"P2FilmChunk000000",tmp,
                first_frame=0,frame_count=24,listener_path="/World/Camera",
                camera_path="/World/Camera")
            verified=scheduler.reconcile_all(
                self.pid,"P2OriginalPlan",1,output_parent=tmp)
            self.assertEqual(verified["verified_frames"],24)
            self.assertEqual(verified["status"],
                "ALL_TECHNICAL_PICTURE_PCM_DERIVATIVES_VERIFIED_NOT_MASTER")
            self.assertFalse(verified["master_approved"])


class OriginalActorOwnedStereo(unittest.TestCase):
    def setUp(self):
        self.fixture=OriginalImportedGLBAndActing(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.pid=self.fixture.project
        self.index=self.fixture.index
        self.fixture._make_take()
        self.binding=ActorDialogueDirector(
            self.index,verify_director_action=lambda event,scope:
            event=="director_yes" and
            scope["operation"]=="nvp.p1bc.bind_original_dialogue.v1")
        self.binding.bind(self.pid,"OriginalActorVoice",
            actor_id="ActorLead",take_id="SourceHumanTake",
            event_id="OriginalLine",creator_event="director_yes")
        self.bus=NativeActorSpatialBus(
            self.index,verify_director_action=lambda event,scope:
            event=="director_yes" and
            scope["operation"]=="nvp.p1e.commit_actor_dry_spatial_mix.v1")
        self.bus.publish(self.pid,"LeadVoiceBus",take_id="SourceHumanTake",
                         listener_path="/World/Camera",
                         routes=[{"dialogue_id":"OriginalActorVoice",
                                  "revision":1,"gain":1.0}],
                         creator_event="director_yes")

    def test_real_actor_pcm_window_is_attributed_and_spatial(self):
        out=self.bus.window(self.pid,"LeadVoiceBus",1,
                            first_sample=0,count=4096)
        self.assertEqual(out["sample_rate"],48000)
        self.assertEqual(out["channels"],2)
        self.assertEqual(len(out["original_pcm_bytes"]),4096*4)
        self.assertEqual(out["active_original_actors"][0]["actor_id"],"ActorLead")
        self.assertNotEqual(out["original_pcm_bytes"],bytes(4096*4))
        self.assertFalse(out["voice_generated"])
        self.assertFalse(out["hrtf_processed"])
        self.assertFalse(out["sound_master_approved"])
        later=self.bus.window(self.pid,"LeadVoiceBus",1,
                              first_sample=48000,count=2000)
        self.assertEqual(later["original_pcm_bytes"],bytes(2000*4))

    def test_original_dialogue_after_500_indexed_cues_without_partial_source(self):
        from backend.nvp_data_av_scene import TICKS_PER_SAMPLE
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        events=[]
        for i in range(520):
            start=i*160*TICKS_PER_SAMPLE
            events.append({
                "event_id":"Line"+str(i).zfill(4),
                "event_kind":"dialogue","subject_id":"ActorLead",
                "start_tick":start,
                "end_tick":start+160*TICKS_PER_SAMPLE,
                "source_id":"OriginalSpeech","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor001","gain":1.0},
            })
        TemporalLedger(self.index).publish(
            self.pid,"LongOriginalDialogue",events,duration_tick=2*T)
        OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda e,s:
            e=="yes" and s["operation"]=="nvp.freeze.usd_temporal_take.v1"
        ).freeze(self.pid,"LongOriginalTake",
                 scene_id="SourceHumanScene",scene_revision=1,
                 timeline_id="LongOriginalDialogue",timeline_revision=1,
                 sample_ticks=[0,T//2,T],creator_event="yes")
        approval=ActorDialogueDirector(
            self.index,verify_director_action=lambda e,s:
            e=="yes" and s["operation"]=="nvp.p1bc.bind_original_dialogue.v1")
        approval.bind(self.pid,"LateOriginalVoice",
                      actor_id="ActorLead",take_id="LongOriginalTake",
                      event_id="Line0519",creator_event="yes")
        tick=519*160*TICKS_PER_SAMPLE+2*TICKS_PER_SAMPLE
        state=approval.at(self.pid,"LateOriginalVoice",1,tick)
        self.assertTrue(state["dialogue_active"])
        self.assertEqual(state["source_event_id"],"Line0519")
        self.assertTrue(state["native_skin_deformation_evaluated"])
        self.assertFalse(state["voice_synthesized"])

    def test_audio_refusal_duplicates_and_foreign_actor_fail_closed(self):
        before=self.index.read_revision(
            self.pid,"SourceHumanTake",1)["document_sha256"]
        with self.assertRaises(ValueError):
            self.bus.publish(
                self.pid,"DuplicateVoiceBus",take_id="SourceHumanTake",
                listener_path="/World/Camera",
                routes=[{"dialogue_id":"OriginalActorVoice","revision":1,"gain":1.0}]*2,
                creator_event="director_yes")
        with self.assertRaises(ValueError):
            self.bus.publish(
                self.pid,"UnboundedGain",take_id="SourceHumanTake",
                listener_path="/World/Camera",
                routes=[{"dialogue_id":"OriginalActorVoice","revision":1,
                         "gain":float("nan")}],creator_event="director_yes")
        denial=NativeActorSpatialBus(
            self.index,verify_director_action=lambda *_:False)
        with self.assertRaises(PermissionError):
            denial.publish(self.pid,"NoActorMix",take_id="SourceHumanTake",
                listener_path="/World/Camera",
                routes=[{"dialogue_id":"OriginalActorVoice","revision":1,"gain":1.0}],
                creator_event="no")
        self.assertEqual(self.index.read_revision(
            self.pid,"SourceHumanTake",1)["document_sha256"],before)


class FeatureLengthNativeSourceSchedule(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory(prefix="nvp-p2-30m-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.studio=Studio(self.root/"film.sqlite")
        self.pid=self.studio.create_project("Thirty minute immutable source","")["id"]
        self.index=FilmIndex(self.studio)
        scene=OpenUSDSceneBridge(self.index)
        scene.publish(self.pid,"FullWorld",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,0,8]},
        ],curves=[])
        self.index.register_revision(self.pid,"OriginalPerformance","performance",
            {"format":"nvp.p2.source_longform_fixture.v1","authentic_source":True})
        ledger=TemporalLedger(self.index)
        duration=30*60*T
        ledger.publish(self.pid,"FullTimeline",[{
            "event_id":"OriginalWork","event_kind":"action","subject_id":"Actor",
            "start_tick":0,"end_tick":duration,
            "source_id":"OriginalPerformance","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor","action":"hold"}
        }],duration_tick=duration)
        take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda e,s:
            e=="yes" and s["operation"]=="nvp.freeze.usd_temporal_take.v1")
        take.freeze(self.pid,"FullTake",scene_id="FullWorld",scene_revision=1,
                    timeline_id="FullTimeline",timeline_revision=1,
                    sample_ticks=[0,T,duration-1],creator_event="yes")
        slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        slate.publish_graph(self.pid,"FullGraph",scene_id="FullWorld",
            scene_label="30",nodes=[{
                "branch_id":"Original","kind":"performance",
                "parent_id":None,"fork_tick":None,"group_id":"All",
                "primary":True,"take_id":"FullTake",
                "source_start_tick":0,"source_end_tick":duration,
                "shot_id":None,"shot_revision":None,
                "slate":{"scene":"30","setup":"A","shot":"A",
                         "camera":"A","take_number":1,"wild":False,
                         "script_revision":"v1","notes":"Original duration"}
            }])
        self.assembly=SlateSequenceAssembly(
            slate,verify_editor_action=lambda e,s:
            e=="yes" and s["operation"]=="nvp.slate.commit_assembled_edit.v1")
        self.assembly.commit(self.pid,"FullCut",graph_id="FullGraph",
            graph_revision=1,segments=[{
                "segment_id":"WholeFilm","branch_id":"Original",
                "source_in_tick":0,"source_out_tick":duration
            }],editor_event="yes")
        self.continuity=NativeEditorialContinuity(
            self.assembly,verify_director_action=lambda e,s:
            e=="yes" and s["operation"]=="nvp.p1d.commit_director_continuity.v1")
        self.continuity.publish(self.pid,"FullContinuity",
            edit_id="FullCut",edit_revision=1,cues=[{
                "segment_id":"WholeFilm","continuity":"accepted",
                "audio_policy":"original_scene","note":"Continuous source"}
            ],creator_event="yes")
        self.sched=NativeLongformFilmPlan(
            self.assembly,self.continuity,verify_creator_action=lambda e,s:
            e=="yes" and s["operation"]==
            "nvp.p2.authorize_original_longform_source_plan.v1")

    def test_30minute_exact_native_source_plan_pages_without_fake_render(self):
        receipt=self.sched.publish(self.pid,"ThirtyMinutePlan",
            continuity_id="FullContinuity",continuity_revision=1,
            listener_path="/World/Camera",camera_path="/World/Camera",
            creator_event="yes")
        self.assertEqual(receipt["revision"],1)
        record=self.sched.open(self.pid,"ThirtyMinutePlan",1)
        self.assertTrue(record["data"]["is_thirty_minute_longform"])
        self.assertEqual(record["data"]["total_frames"],43200)
        self.assertEqual(record["data"]["total_chunks"],1800)
        page=self.sched.page(self.pid,"ThirtyMinutePlan",1,
                             first_index=1799,limit=2)
        self.assertIsNone(page["next_index"])
        self.assertEqual(page["chunks"][0]["first_frame"],43176)
        self.assertEqual(page["chunks"][0]["frame_count"],24)
        self.assertFalse(page["full_film_picture_sound_delivered"])
        with TemporaryDirectory() as tmp:
            absent=self.sched.reconcile_all(self.pid,"ThirtyMinutePlan",1,
                                            output_parent=tmp)
            self.assertEqual(absent["status"],"INCOMPLETE_ORIGINAL_SOURCE_DERIVATIVES")
            self.assertEqual(absent["verified_frames"],0)
            self.assertFalse(absent["master_approved"])
        fresh_index=FilmIndex(Studio(self.studio.db_path))
        fresh_assembly=SlateSequenceAssembly(
            DigitalSlateBranches(fresh_index,
                verify_editor_action=lambda *_:False),
            verify_editor_action=lambda *_:False)
        fresh_continuity=NativeEditorialContinuity(
            fresh_assembly,verify_director_action=lambda *_:False)
        fresh=NativeLongformFilmPlan(
            fresh_assembly,fresh_continuity,
            verify_creator_action=lambda *_:False)
        self.assertEqual(fresh.open(self.pid,"ThirtyMinutePlan",1)[
            "document_sha256"],receipt["document_sha256"])


if __name__=="__main__":
    unittest.main()
