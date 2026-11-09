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
from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity
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
            b.pid,"MicOriginal",[pcm[:48000],pcm[48000:]],
            expected_revision=0)
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

    def test_02m_h_actual_approved_building_in_original_actor_camera_shot(self):
        """Full native pxr/FilmIndex 02M→01D→01E source integration test."""
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        from backend.nvp_usd_film02m_modular_buildings import OriginalBuildingKit
        from backend.nvp_usd_film02m_e_district import OriginalFilmDistrict
        from backend.nvp_usd_film02m_h_actor_camera_binding import (
            OriginalDistrictShotBinding,FORMAT as SHOT_BINDING_FORMAT)
        self.link_actor()
        frozen=self.freeze()
        self.assertEqual(frozen["revision"],1)
        before_take=self.b.index.read_revision(
            self.b.pid,"OriginalStreetTake",1)["document_sha256"]
        before_world_take=self.b.index.read_revision(
            self.b.pid,"WorldStreetTake",1)["document_sha256"]
        before_shot=self.b.index.read_revision(
            self.b.pid,"StreetWorldShot",1)["document_sha256"]
        before_takes=self.b.index.list_objects(self.b.pid,kind="take")
        def sock(name,where,normal,span,kind):
            return {"name":name,"connector_type":kind,
                    "gender":"universal","at_m":where,"normal":normal,
                    "span_m":span,"tolerance_m":.01}
        pieces=[
            ("Floor","floor",[12,10,.4],[
                sock("Front",[0,-5,0],[0,-1,0],12,"wall_base"),
                sock("Rear",[0,5,0],[0,1,0],12,"wall_base"),
                sock("Left",[-6,0,0],[-1,0,0],10,"side_base"),
                sock("Right",[6,0,0],[1,0,0],10,"side_base")]),
            ("Front","facade",[12,.4,6],[
                sock("Back",[0,.2,-3],[0,1,0],12,"wall_base"),
                sock("Top",[0,0,3],[0,0,1],12,"roof_edge")]),
            ("Rear","rear",[12,.4,6],[
                sock("Front",[0,-.2,-3],[0,-1,0],12,"wall_base")]),
            ("Left","side",[.4,10,6],[
                sock("Inner",[.2,0,-3],[1,0,0],10,"side_base")]),
            ("Right","side",[.4,10,6],[
                sock("Inner",[-.2,0,-3],[-1,0,0],10,"side_base")]),
            ("Roof","roof",[12.8,10.8,.4],[
                sock("FrontBottom",[0,-5.2,-.2],[0,0,-1],12,"roof_edge")]),
        ]
        def cube(size):
            x,y,z=[n/2 for n in size]
            return ([[-x,-y,-z],[x,-y,-z],[x,y,-z],[-x,y,-z],
                     [-x,-y,z],[x,-y,z],[x,y,z],[-x,y,z]],
                    [[0,2,1],[0,3,2],[4,5,6],[4,6,7],
                     [0,1,5],[0,5,4],[3,7,6],[3,6,2],
                     [0,4,7],[0,7,3],[1,2,6],[1,6,5]])
        kit=OriginalBuildingKit(
            self.b.index,verify_director_action=lambda event,scope:
            event=="SOURCE_NATIVE_TEST" and scope["operation"] in (
                "nvp.film02m.publish_original_building_module.v1",
                "nvp.film02m.publish_original_architecture.v1"))
        assets=OpenUSDAssetRegistry(self.b.index)
        for suffix,role,dimensions,sockets in pieces:
            name="ShotModule"+suffix
            asset="ShotAsset"+suffix
            points,triangles=cube(dimensions)
            assets.publish(
                self.b.pid,asset,shape="mesh",size_m=max(dimensions),
                points=points,triangles=triangles,
                preview_material={"base_color_rgb":[.7,.4,.3],
                                  "roughness":.6,"metallic":.04})
            kit.publish_module(
                self.b.pid,name,asset_id=asset,asset_revision=1,
                role=role,style_family="OriginalShot",size_m=dimensions,
                sockets=sockets,director_event="SOURCE_NATIVE_TEST")
        def node(name,module,parent=None,attached=None,own=None,root=None):
            return {"node_id":name,
                    "options":[{"module_id":"ShotModule"+module,"revision":1}],
                    "parent_id":parent,"parent_socket":attached,
                    "own_socket":own,"yaw_deg":0,
                    "root_position_m":root}
        building=kit.publish_building(
            self.b.pid,"ShotOriginalBuilding",seed=4,
            blueprint=[
                node("Floor","Floor",root=[0,0,0]),
                node("Front","Front","Floor","Front","Back"),
                node("Rear","Rear","Floor","Rear","Front"),
                node("Left","Left","Floor","Left","Inner"),
                node("Right","Right","Floor","Right","Inner"),
                node("Roof","Roof","Front","Top","FrontBottom")],
            director_event="SOURCE_NATIVE_TEST")
        district=OriginalFilmDistrict(
            self.b.index,verify_director_action=lambda event,scope:
            event=="SOURCE_NATIVE_TEST" and scope["operation"]==
            "nvp.film02m_e.publish_original_layered_district.v1")
        params={
            "seed":11,"source_buildings":[
                {"building_id":"ShotOriginalBuilding","revision":1}],
            "grid_cols":1,"grid_rows":1,"lot_spacing_m":30.,
            "world_origin_m":[100.,0.,0.],
            "source_triangle_budget":100000,
            "source_instance_budget":1}
        original=district.publish(
            self.b.pid,"ShotApprovedDistrict",**params,
            expected_revision=0,director_event="SOURCE_NATIVE_TEST")
        approvals=[False]
        granted=[]
        def confirm(event,scope):
            granted.append((event,dict(scope)))
            return approvals[0] and event=="NATIVE_SHOT_APPROVAL"
        bindings=OriginalDistrictShotBinding(
            self.b.index,confirm=confirm)
        result=bindings.preview(
            self.b.pid,"ShotApprovedDistrict",1,"WorldStreetTake",T)
        self.assertTrue(result["native_approved_district_layer_composed"])
        self.assertTrue(result["native_original_camera_verified"])
        self.assertTrue(result["native_original_actor_pose_verified"])
        self.assertTrue(result["original_actor_takes_unchanged"])
        self.assertEqual(result["native_original_instance_count"],1)
        self.assertEqual(result["original_camera_path"],
                         "/World/Sets/Outside/Camera")
        self.assertEqual(result["original_actor_poses"][0]["actor_id"],
                         self.actor["id"])
        self.assertEqual(result["original_actor_poses"][0][
            "world_translation_m"],[2.0,0.0,0.0])
        with self.assertRaises(PermissionError):
            bindings.publish(self.b.pid,"ApprovedActorDistrictShot",
                district_id="ShotApprovedDistrict",district_revision=1,
                world_take_id="WorldStreetTake",film_tick=T,
                creator_event="NATIVE_SHOT_APPROVAL",
                expected_preview_sha256="f"*64)
        self.assertEqual(granted,[])
        with self.assertRaises(PermissionError):
            bindings.publish(self.b.pid,"ApprovedActorDistrictShot",
                district_id="ShotApprovedDistrict",district_revision=1,
                world_take_id="WorldStreetTake",film_tick=T,
                creator_event="NATIVE_SHOT_APPROVAL",
                expected_preview_sha256=result["binding_preview_sha256"])
        with self.assertRaises(KeyError):
            self.b.index.read_revision(self.b.pid,"ApprovedActorDistrictShot",1)
        approvals[0]=True
        published=bindings.publish(
            self.b.pid,"ApprovedActorDistrictShot",
            district_id="ShotApprovedDistrict",district_revision=1,
            world_take_id="WorldStreetTake",film_tick=T,
            creator_event="NATIVE_SHOT_APPROVAL",
            expected_preview_sha256=result["binding_preview_sha256"])
        self.assertEqual(published["revision"],1)
        reopened=bindings.reopen(self.b.pid,"ApprovedActorDistrictShot")
        self.assertEqual(reopened["format"],SHOT_BINDING_FORMAT)
        self.assertTrue(reopened["native_source_reopened"])
        self.assertEqual(reopened["source_preview"],result)
        # Installed bridge: exact first-party origin and genuine OS window
        # confirmation required, never a model-supplied creator_approved flag.
        from backend.nvp_wo5_desktop_bridge import TrustedDesktopWO5Bridge
        class InstalledWindow:
            url="http://127.0.0.1:43141/"
            allowed=False
            confirmations=0
            def get_current_url(self):
                return self.url
            def create_confirmation_dialog(self,title,message):
                self.confirmations+=1
                self.last_title=title
                self.last_message=message
                return self.allowed
        window=InstalledWindow()
        bridge=TrustedDesktopWO5Bridge(
            self.b.index,origin="http://127.0.0.1:43141",
            production_root=Path(self.b.tmp.name)/"02mh_installed_bridge")
        bridge._attach_window(window)
        try:
            request={
                "project_id":self.b.pid,"district_id":"ShotApprovedDistrict",
                "district_revision":1,"world_take_id":"WorldStreetTake",
                "film_tick":T}
            reviewed=bridge.film02mh_preview_shot(request)
            self.assertEqual(reviewed["binding_preview_sha256"],
                             result["binding_preview_sha256"])
            with self.assertRaises(PermissionError):
                bridge.film02mh_commit_shot_binding({
                    **request,"binding_id":"InstalledActorDistrictShot",
                    "source_preview_sha256":reviewed[
                        "binding_preview_sha256"]})
            self.assertEqual(window.confirmations,1)
            with self.assertRaises(PermissionError):
                bridge.film02mh_commit_shot_binding({
                    **request,"binding_id":"InstalledActorDistrictShot",
                    "source_preview_sha256":reviewed[
                        "binding_preview_sha256"],"creator_approved":True})
            self.assertEqual(window.confirmations,1)
            window.url="https://untrusted.example/"
            with self.assertRaises(PermissionError):
                bridge.film02mh_preview_shot(request)
            window.url="http://127.0.0.1:43141/"
            window.allowed=True
            published_via_bridge=bridge.film02mh_commit_shot_binding({
                **request,"binding_id":"InstalledActorDistrictShot",
                "source_preview_sha256":reviewed["binding_preview_sha256"]})
            self.assertEqual(published_via_bridge["revision"],1)
            self.assertEqual(window.confirmations,2)
            self.assertTrue(bridge.film02mh_reopen_shot_binding({
                "project_id":self.b.pid,
                "binding_id":"InstalledActorDistrictShot"})[
                    "native_source_reopened"])
        finally:
            bridge._close()
        self.assertEqual(self.b.index.list_objects(
            self.b.pid,kind="take"),before_takes)
        self.assertEqual(self.b.index.read_revision(
            self.b.pid,"OriginalStreetTake",1)["document_sha256"],before_take)
        self.assertEqual(self.b.index.read_revision(
            self.b.pid,"WorldStreetTake",1)["document_sha256"],before_world_take)
        self.assertEqual(self.b.index.read_revision(
            self.b.pid,"StreetWorldShot",1)["document_sha256"],before_shot)
        # A second immutable district revision may stage a different world,
        # but the previously approved shot binding retains source revision 1.
        district.publish(
            self.b.pid,"ShotApprovedDistrict",**{**params,"seed":12},
            expected_revision=1,director_event="SOURCE_NATIVE_TEST")
        self.assertEqual(bindings.reopen(
            self.b.pid,"ApprovedActorDistrictShot")[
            "binding_document_sha256"],published["document_sha256"])
        with self.assertRaises(RuntimeError):
            bindings.publish(
                self.b.pid,"ApprovedActorDistrictShot",
                district_id="ShotApprovedDistrict",district_revision=1,
                world_take_id="WorldStreetTake",film_tick=T,
                creator_event="NATIVE_SHOT_APPROVAL",
                expected_preview_sha256=result["binding_preview_sha256"])

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

    def test_corrupted_second_original_pcm_chunk_invalidates_world_take_replay(self):
        self.link_actor()
        frozen=self.freeze(take="SourcePCM2ChunkTake")
        manifest=self.b.index.read_revision(
            self.b.pid,"MicOriginal",1)["data"]
        self.assertEqual(len(manifest["chunks"]),2)
        second_sha=manifest["chunks"][1]["blob_sha256"]
        disk=self.b.index._blob_path(self.b.pid,second_sha)
        original=disk.read_bytes()
        self.assertGreater(len(original),0)
        disk.write_bytes(b"X"*len(original))
        with self.assertRaises((RuntimeError,PermissionError,ValueError)):
            self.capture.verify_take(self.b.pid,"SourcePCM2ChunkTake")
        self.assertEqual(
            self.b.index.read_revision(
                self.b.pid,"SourcePCM2ChunkTake",1)["document_sha256"],
            frozen["document_sha256"])

    def test_later_voiceid_recast_does_not_replace_historical_world_take_voice(self):
        self.link_actor()
        pid=self.b.pid
        actor_id=self.actor["id"]
        voice=ProductionBibleVoiceIdentity(
            self.b.index,verify_creator_action=lambda event,scope:
                event=="APPROVE_CREATIVE_RECAST" and
                scope["operation"]=="film03_cast_actor_voice_identity")
        voice.cast_voice(
            pid,actor_id,voice_id="Voice_Street_Original",
            reference_audio_id="MicOriginal",reference_audio_revision=1,
            expected_cast_revision=0,
            director_review_note="Original captured 48k mono audio for this cast",
            creator_event="APPROVE_CREATIVE_RECAST")
        frozen=self.freeze(take="HistoricalVoiceWorldTake")
        old=self.b.index.read_revision(
            pid,"HistoricalVoiceWorldTake",1)["data"]
        self.assertEqual(old["canonical_original_actors"][0]["voice_id"],
                         "Voice_Street_Original")
        original_pcm_sha=self.audio["document_sha256"]
        changed_pcm=RecordedSoundSources(self.b.index).publish(
            pid,"DifferentVoiceReference",
            [b"\x00\x01"*SAMPLE_RATE],expected_revision=0)
        self.assertNotEqual(changed_pcm["document_sha256"],original_pcm_sha)
        voice.cast_voice(
            pid,actor_id,voice_id="Voice_Street_Recast",
            reference_audio_id="DifferentVoiceReference",
            reference_audio_revision=1,
            expected_cast_revision=1,
            director_review_note="Second recording is for a later independent Take",
            voice_recast_reason="Director changed the character voice for a future retake",
            creator_event="APPROVE_CREATIVE_RECAST")
        self.assertEqual(voice.current(pid,actor_id)["current"]["voice_id"],
                         "Voice_Street_Recast")
        restored=OpenUSDWorldTakeCapture(
            FilmIndex(Studio(self.b.db)),
            verify_creator_action=lambda *_:False)
        same=restored.verify_take(pid,"HistoricalVoiceWorldTake")
        self.assertEqual(same["take_document_sha256"],
                         frozen["document_sha256"])
        stored=self.b.index.read_revision(
            pid,"HistoricalVoiceWorldTake",1)["data"]
        self.assertEqual(stored["canonical_original_actors"][0]["voice_id"],
                         "Voice_Street_Original")

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
