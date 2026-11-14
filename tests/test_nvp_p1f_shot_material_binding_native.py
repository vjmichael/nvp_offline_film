"""P1-F native exact original OpenUSD scene/Take to reviewed UV/PBR material tests.

Uses a genuine skinned ActorID, original dialogue PCM, camera/timing,
native authored USD environment with UV topology and immutable PNG/rights
evidence. Does NOT claim production photorealism, render or film mastery.
"""
from pathlib import Path
import unittest

from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_p1de_edit_audio import P1DEConform
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
from backend.nvp_p1f_reviewed_pbr_materials import P1FReviewedPBRMaterials
from backend.nvp_p1f_shot_material_binding import P1FOriginalShotMaterialBinding
from test_nvp_p1f_imported_actor_native import RealImportedActorTests,ACTOR,T
from test_nvp_p1f_reviewed_pbr_materials_native import (
    original_uv_location,png,RIGHTS,EVIDENCE)


def original_combined_shot(test):
    """Publish independent original Take with BOTH skinned actor and UV set."""
    fixture=test.fixture
    fixture.test_composed_facial_actor_in_real_source_take_shot()
    pid=fixture.pid
    index=fixture.index
    assets=OpenUSDAssetRegistry(index)
    raw_env=original_uv_location()
    assets.import_environment(
        pid,"reviewed_film_environment",raw_env,
        location_id="LOCATION_ReviewedFilmSet",
        creator_event="reviewed_location",
        approve_import=lambda e,s:
            e=="reviewed_location" and
            s["operation"]=="nvp.p1f.import_authored_3d_environment.v1")
    maps={
        "baseColor":png("RGB",(123,65,42)),
        "roughness":png("L",179),
        "metallic":png("L",13),
        "normal":png("RGB",(128,128,255)),
    }
    P1FReviewedPBRMaterials(index).publish(
        pid,"reviewed_film_materials",
        environment_id="reviewed_film_environment",
        environment_revision=1,
        material_path="/Asset/Looks/Brick",
        textures=maps,rights=RIGHTS,rights_evidence=EVIDENCE,
        approve_import=lambda e,s:
            e=="reviewed_exact_png" and
            s["operation"]=="nvp.p1f.import_reviewed_pbr_texture_set.v1",
        creator_event="reviewed_exact_png")
    scene=OpenUSDSceneBridge(index).publish(
        pid,"scene_with_reviewed_materials",
        prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Set","role":"environment","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,0,4]},
        ],curves=[],native_schemas=True,
        asset_bindings=[
            {"path":"/World/Actor","asset_id":"original_lead_asset",
             "asset_revision":1},
            {"path":"/World/Set","asset_id":"reviewed_film_environment",
             "asset_revision":1},
        ])
    capture=OpenUSDTakeCapture(
        index,verify_creator_action=lambda *_:True)
    take=capture.freeze(
        pid,"original_combined_set_take",
        scene_id="scene_with_reviewed_materials",
        scene_revision=1,
        timeline_id="original_actor_timeline",
        timeline_revision=1,sample_ticks=[0,T],
        creator_event="reviewed_capture")
    edl=P1DEConform(index,approve_edit=lambda *_:True)
    original_pcm=index.read_revision(pid,"actor_dialogue_source",1)
    edited=edl.publish(
        pid,"combined_set_edit",[{
            "take_id":"original_combined_set_take",
            "take_sha256":take["document_sha256"],
            "in_tick":0,"out_tick":T,
            "listener_path":"/World/Camera",
            "audio":[{"event_id":"lead_speech","actor_id":ACTOR,
                     "source_id":"actor_dialogue_source","source_revision":1,
                     "source_sha256":original_pcm["document_sha256"],
                     "enabled":True,"gain":1.0}]
        }],expected_revision=0,creator_event="reviewed_edit")
    P1FReelPlan(index).publish(
        pid,"combined_set_reel_plan",
        edit_id="combined_set_edit",edit_revision=1,
        expected_edit_document_sha256=edited["document_sha256"])
    return scene,{"environment":"reviewed_film_environment",
                  "material_set":"reviewed_film_materials",
                  "scene":"scene_with_reviewed_materials",
                  "plan":"combined_set_reel_plan"}


class OriginalShotReviewedMaterialTests(unittest.TestCase):
    def setUp(self):
        fixture=RealImportedActorTests(
            "test_composed_facial_actor_in_real_source_take_shot")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture

    def publish(self,scene="scene_with_reviewed_materials",
                look="original_scene_look",event="reviewed_look"):
        return P1FOriginalShotMaterialBinding(self.fixture.index).publish(
            self.fixture.pid,look,
            scene_id=scene,scene_revision=1,
            environment_path="/World/Set",
            material_set_id="reviewed_film_materials",
            material_set_revision=1,
            approve_bind=lambda e,s:
                e=="reviewed_look" and
                s["operation"]=="nvp.p1f.bind_reviewed_material_to_original_scene.v1"
                and s["original_material_path"]=="/World/Set/Looks/Brick"
                and s["original_uv_mesh_paths"]==[
                    "/World/Set/Geometry/Wall"],
            creator_event=event)

    def test_real_actor_timeline_original_take_and_uv_material_binding(self):
        scene,_=original_combined_shot(self)
        published=self.publish()
        self.assertEqual(published["revision"],1)
        native=P1FOriginalShotMaterialBinding(self.fixture.index)
        look=native.open(self.fixture.pid,"original_scene_look")
        self.assertEqual(look["data"]["scene_document_sha256"],
                         scene["document_sha256"])
        receipt=native.for_frame(
            self.fixture.pid,"original_scene_look",
            "combined_set_reel_plan",0,0)
        self.assertEqual(receipt["status"],"LOOK_SOURCE_VERIFIED_NOT_RENDERED")
        self.assertEqual(receipt["composed_material_path"],
                         "/World/Set/Looks/Brick")
        self.assertEqual(receipt["bound_mesh_paths"],
                         ["/World/Set/Geometry/Wall"])
        self.assertEqual(len(receipt["texture_sources"]),4)
        self.assertFalse(receipt["worker_authorized"])
        self.assertFalse(receipt["picture_rendered"])
        self.assertFalse(receipt["film_master_created"])
        restarted=P1FOriginalShotMaterialBinding(self.fixture.index)
        self.assertEqual(restarted.for_frame(
            self.fixture.pid,"original_scene_look",
            "combined_set_reel_plan",0,0),receipt)

    def test_cross_scene_nonmatching_take_and_tampered_original_png_refused(self):
        original_combined_shot(self)
        self.publish()
        bindings=P1FOriginalShotMaterialBinding(self.fixture.index)
        with self.assertRaisesRegex(RuntimeError,"does not originate"):
            bindings.for_frame(
                self.fixture.pid,"original_scene_look",
                "rigged_reel_plan",0,0)
        with self.assertRaises(RuntimeError):
            self.publish(look="replayed_look")
        material=P1FReviewedPBRMaterials(self.fixture.index).open(
            self.fixture.pid,"reviewed_film_materials")
        sha=material["data"]["textures"]["baseColor"]["sha256"]
        source=self.fixture.index._blob_path(self.fixture.pid,sha)
        source.write_bytes(b"original texture was changed")
        with self.assertRaises(RuntimeError):
            bindings.open(self.fixture.pid,"original_scene_look")

    def test_creator_refusal_does_not_publish_look(self):
        original_combined_shot(self)
        with self.assertRaises(PermissionError):
            self.publish(event="declined")
        with self.assertRaises(KeyError):
            self.fixture.index.read_revision(
                self.fixture.pid,"original_scene_look")


if __name__=="__main__":
    unittest.main()
