"""Single FilmIndex shot with source GLB/full body + UV/PBR + ActorID PCM."""
import unittest

from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
from backend.nvp_p1f_production_scene_performance import (
    review_original_character_scene_frame,
)
from test_nvp_p1f_full_body_retarget_native import full_body_glb, ROLE_MAP
from test_nvp_p1f_production_character_assets_native import (
    CALIBRATION, EVIDENCE as ACTOR_EVIDENCE, MAPPING, RIGHTS as ACTOR_RIGHTS,
)
from test_nvp_p1f_shot_material_binding_native import (
    OriginalShotReviewedMaterialTests, original_combined_shot,
)
from test_nvp_p1f_imported_actor_native import ACTOR


class OriginalCharacterSourceSceneTests(unittest.TestCase):
    def setUp(self):
        owner = OriginalShotReviewedMaterialTests(
            "test_real_actor_timeline_original_take_and_uv_material_binding")
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        original_combined_shot(owner)
        owner.publish()
        self.owner = owner
        self.index = owner.fixture.index
        self.pid = owner.fixture.pid
        self.char = P1FReviewedProductionCharacters(self.index)
        self.char.publish(
            self.pid, "reviewed_body_with_set", full_body_glb(),
            actor_id=ACTOR, actor_asset_id="original_lead_asset",
            actor_asset_revision=1, joint_map=MAPPING,
            full_body_role_map=ROLE_MAP,
            calibration=CALIBRATION,
            rights=ACTOR_RIGHTS, rights_evidence=ACTOR_EVIDENCE,
            creator_event="source_bundle_review",
            approve_import=lambda e,s: (
                e=="source_bundle_review" and
                s["full_body_rest_axes"]["glb_inverse_bind_rest_verified"]
                and s["original_actor_document_sha256"]==self.index.read_revision(
                    self.pid,"original_lead_asset",1)["document_sha256"]))
        self.char.cast(
            self.pid, "source_bundle_cast",
            package_id="reviewed_body_with_set",
            scene_id="scene_with_reviewed_materials", scene_revision=1,
            actor_path="/World/Actor",creator_event="one_scene_cast",
            approve_cast=lambda e,s: e=="one_scene_cast" and
                s["scene_id"]=="scene_with_reviewed_materials")

    def source(self, *, plan="combined_set_reel_plan", frame=0):
        return review_original_character_scene_frame(
            self.index, self.pid,
            plan_id=plan, reel_index=0, frame_offset=frame,
            cast_id="source_bundle_cast",
            reviewed_look_id="original_scene_look")

    def test_original_actor_full_body_environment_voice_one_take_and_clock(self):
        first = self.source()
        self.assertEqual(first["status"],"REVIEWED_ORIGINAL_SOURCES_NOT_RENDERED")
        self.assertEqual(first["actor_id"],ACTOR)
        self.assertEqual(first["original_material_look_id"],"original_scene_look")
        self.assertEqual(set(first["original_texture_sha256"]),
                         {"baseColor","roughness","metallic","normal"})
        self.assertEqual(first["source_voice_event_id"],"lead_speech")
        self.assertEqual(first["glb_decoded_skinned_vertices"],3)
        self.assertTrue(first["glb_full_body_rest_axes"]["glb_inverse_bind_rest_verified"])
        self.assertEqual(first,self.source())
        second=self.source(frame=1)
        self.assertNotEqual(second["original_source_tick"],first["original_source_tick"])
        self.assertNotEqual(second["source_review_sha256"],first["source_review_sha256"])
        for k in ("detailed_asset_rights_independently_cleared",
                  "full_body_original_usd_animation_verified",
                  "actor_lipsync_deformation_verified",
                  "original_mesh_terrain_contact_verified",
                  "cycles_rendered","worker_authorized"):
            self.assertFalse(first[k])

    def test_cross_scene_take_and_corrupted_original_pbr_denied(self):
        with self.assertRaises(RuntimeError):
            self.source(plan="rigged_reel_plan")
        look = self.index.read_revision(self.pid,"reviewed_film_materials",1)
        digest=look["data"]["textures"]["baseColor"]["sha256"]
        path=self.index._blob_path(self.pid,digest)
        path.write_bytes(b"modified original PBR image")
        with self.assertRaises(RuntimeError):
            self.source()


if __name__ == "__main__":
    unittest.main()
