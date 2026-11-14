"""Public genuine Blender-exported GLB → authoritative ActorID/Take native gate.

Reuses the original unchanged PROD-06C authentic skinned GLB export/reimport
and actual Blender deformation acceptance. Then independently registers those
same source bytes into FilmIndex and verifies original-source casting. This
is a public synthesized 7-tube fixture, not a licensed professional person,
production-private authorization or a final rendered film.
"""
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
from tools.nvp_prod06c_fixture import build_fixture
from test_nvp_p1f_imported_actor_native import RealImportedActorTests, ACTOR
from test_nvp_p1f_production_character_assets_native import RIGHTS,EVIDENCE,CALIBRATION,MAPPING


@unittest.skipUnless(os.name=="nt" and
                     os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")=="1" and
                     os.environ.get("NVP_TEST_BLENDER"),
                     "Only original real Windows Blender public skinned GLB fixture")
class RealBlenderSourceCharacterBridge(unittest.TestCase):
    def test_actual_blender_exported_skinned_character_to_original_take(self):
        blender=os.environ["NVP_TEST_BLENDER"]
        with tempfile.TemporaryDirectory(prefix="nvp-p1f-genuine-glb-cast-") as tmp:
            root=Path(tmp)
            native=build_fixture(root/"rigged_source",
                                 render_preview=False,blender=blender)
            self.assertEqual(native["status"],"passed_blender_audit_only",native)
            self.assertGreater(native["import"]["skinned_vertices"],100)
            self.assertGreater(native["native"]["checks"],10)
            original=(root/"rigged_source"/"importable_humanoid.glb").read_bytes()
            fixture=RealImportedActorTests(
                "test_composed_facial_actor_in_real_source_take_shot")
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.test_composed_facial_actor_in_real_source_take_shot()
            index=fixture.index
            cast=P1FReviewedProductionCharacters(index)
            record=cast.publish(
                fixture.pid,"blender_exported_lead",original,
                actor_id=ACTOR,actor_asset_id="original_lead_asset",
                actor_asset_revision=1,joint_map=MAPPING,
                calibration=CALIBRATION,rights=RIGHTS,rights_evidence=EVIDENCE,
                creator_event="one_source_review",
                approve_import=lambda event,scope:
                    event=="one_source_review" and
                    scope["operation"]=="nvp.p1f.review_production_character_source.v1" and
                    scope["glb_sha256"]==sha256(original).hexdigest())
            stored=cast.open(fixture.pid,"blender_exported_lead")
            self.assertEqual(record["document_sha256"],stored["document_sha256"])
            self.assertGreater(
                stored["data"]["decoded_geometry"]["decoded_skinned_vertices"],100)
            self.assertEqual(stored["data"]["glb_sha256"],sha256(original).hexdigest())
            cast.cast(
                fixture.pid,"reviewed_blender_export_cast",
                package_id="blender_exported_lead",scene_id="original_actor_scene",
                scene_revision=1,actor_path="/World/Actor",
                creator_event="one_cast_review",
                approve_cast=lambda event,scope:
                    event=="one_cast_review" and
                    scope["operation"]=="nvp.p1f.cast_reviewed_production_character.v1")
            frame=cast.for_frame(
                fixture.pid,"reviewed_blender_export_cast",
                "rigged_reel_plan",0,0)
            self.assertEqual(frame["glb_sha256"],sha256(original).hexdigest())
            self.assertEqual(frame["actor_id"],ACTOR)
            self.assertEqual(len(frame["facial_weights"]),4)
            self.assertFalse(frame["retargeted_body_motion_verified"])
            self.assertFalse(frame["worker_authorized"])
            self.assertFalse(frame["film_master_created"])
            second=P1FReviewedProductionCharacters(index).for_frame(
                fixture.pid,"reviewed_blender_export_cast",
                "rigged_reel_plan",0,0)
            self.assertEqual(second,frame)


if __name__=="__main__":
    unittest.main()
