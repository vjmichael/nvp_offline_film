"""Native Step-2 GLB/ActorID/Take casting, license and calibration custody.

Public fixture inputs only. A seven-joint structural GLB remains a fixture,
not a professional performer or a proven retargeted Blender result.
"""
from pathlib import Path
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
from test_character_assets import synthetic_glb
from test_nvp_p1f_imported_actor_native import RealImportedActorTests, ACTOR


RIGHTS = {
    "basis": "creator_owned", "holder": "Original Creator Studio",
    "license_identifier": "original-actor-asset-ownership-2026",
    "allowed_uses": ["render", "derivative", "distribution"],
}
EVIDENCE = (b"Original creator-owned rigged GLB character bytes and mesh. "
            b"This authored test ownership statement is evidence custody only; "
            b"rights have not been independently verified or cleared for release.\n")
MAPPING = {"Body": "hips", "Body/Head": "head"}
CALIBRATION = {
    "meters_per_source_unit": 1.0, "root_height_m": 0.0,
    "yaw_degrees": 0.0, "rest_pose_reviewed": False,
}


class OriginalProductionCharacterTests(unittest.TestCase):
    def setUp(self):
        fixture = RealImportedActorTests(
            "test_composed_facial_actor_in_real_source_take_shot")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.test_composed_facial_actor_in_real_source_take_shot()
        self.fixture = fixture
        self.pid = fixture.pid
        self.index = fixture.index
        self.assets = P1FReviewedProductionCharacters(self.index)
        self.raw = synthetic_glb()

    def register(self, *, package_id="original_reviewed_lead",
                 source=None, actor_id=ACTOR, mapping=None, calibration=None,
                 rights=None, evidence=None, event="creator_approved_character"):
        return self.assets.publish(
            self.pid, package_id,
            self.raw if source is None else source,
            actor_id=actor_id, actor_asset_id="original_lead_asset",
            actor_asset_revision=1,
            joint_map=MAPPING if mapping is None else mapping,
            calibration=CALIBRATION if calibration is None else calibration,
            rights=RIGHTS if rights is None else rights,
            rights_evidence=EVIDENCE if evidence is None else evidence,
            creator_event=event,
            approve_import=lambda e,s:
                e == "creator_approved_character" and
                s["operation"] == "nvp.p1f.review_production_character_source.v1"
                and s["actor_id"] == ACTOR and
                s["joint_map"] == MAPPING)

    def cast(self, *, cast_id="original_reviewed_cast",
             scene_id="original_actor_scene", event="creator_approved_cast"):
        return self.assets.cast(
            self.pid, cast_id,
            package_id="original_reviewed_lead",
            scene_id=scene_id, scene_revision=1,
            actor_path="/World/Actor", creator_event=event,
            approve_cast=lambda e,s:
                e == "creator_approved_cast" and
                s["operation"] == "nvp.p1f.cast_reviewed_production_character.v1"
                and s["actor_id"] == ACTOR and s["glb_sha256"] == self.assets.open(
                    self.pid,"original_reviewed_lead")["data"]["glb_sha256"])

    def test_reviewed_glb_and_explicit_bone_map_survive_independent_take_reopen(self):
        published = self.register()
        package = self.assets.open(self.pid, "original_reviewed_lead")
        self.assertEqual(package["document_sha256"], published["document_sha256"])
        self.assertEqual(package["data"]["joint_map"], MAPPING)
        self.assertFalse(package["data"]["license_independently_verified"])
        self.assertFalse(package["data"]["contact_and_deformation_verified"])
        self.assertFalse(package["data"]["private_worker_authorized"])
        self.assertEqual(self.index.get_blob(
            self.pid, package["data"]["glb_sha256"]), self.raw)
        casted = self.cast()
        self.assertEqual(casted["revision"], 1)
        first = self.assets.for_frame(
            self.pid, "original_reviewed_cast","rigged_reel_plan",0,0)
        second = self.assets.for_frame(
            self.pid, "original_reviewed_cast","rigged_reel_plan",0,1)
        self.assertEqual(first["status"],"REVIEWED_CAST_SOURCE_NOT_RENDERED")
        self.assertEqual(first["actor_id"], ACTOR)
        self.assertEqual(first["joint_map"], MAPPING)
        self.assertEqual(len(first["facial_weights"]), 4)
        self.assertNotEqual(first["source_tick"], second["source_tick"])
        self.assertFalse(first["retargeted_body_motion_verified"])
        self.assertFalse(first["worker_authorized"])
        self.assertFalse(first["film_master_created"])
        reopened = P1FReviewedProductionCharacters(FilmIndex(self.fixture.studio))
        self.assertEqual(
            reopened.for_frame(self.pid,"original_reviewed_cast","rigged_reel_plan",0,0),
            first)

    def test_refuse_unapproved_external_foreign_or_ambiguous_skeleton(self):
        cases = [
            {"package_id": "declined_pkg","event": "refused"},
            {"package_id": "foreign_pkg","actor_id": "ACT_NotOriginal"},
            {"package_id": "duplicate_joints",
             "mapping": {"Body":"hips","Body/Head":"hips"}},
            {"package_id": "unknown_joint",
             "mapping": {"Body":"hips","Body/Head":"not_a_bone"}},
            {"package_id": "bad_license",
             "rights": {**RIGHTS,"allowed_uses":["render"]}},
            {"package_id": "missing_evidence", "evidence":b"none"},
            {"package_id": "external_images",
             "source": synthetic_glb(external_image=True)},
            {"package_id": "unreviewed_scale",
             "calibration": {**CALIBRATION,"meters_per_source_unit": 0}},
        ]
        for case in cases:
            with self.subTest(case=case["package_id"]):
                with self.assertRaises((ValueError,PermissionError)):
                    self.register(**case)
                with self.assertRaises(KeyError):
                    self.index.read_revision(self.pid,case["package_id"])

    def test_cast_refusal_cross_scene_and_one_use_id(self):
        self.register()
        with self.assertRaises(PermissionError):
            self.cast(event="no")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"original_reviewed_cast")
        self.cast()
        with self.assertRaises(RuntimeError):
            self.cast()
        OpenUSDSceneBridge(self.index).publish(
            self.pid,"different_reviewed_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,4]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{"path":"/World/Actor",
                             "asset_id":"original_lead_asset",
                             "asset_revision":1}])
        self.assets.cast(
            self.pid,"different_cast",package_id="original_reviewed_lead",
            scene_id="different_reviewed_scene",scene_revision=1,
            actor_path="/World/Actor",creator_event="okay",
            approve_cast=lambda *_:True)
        with self.assertRaisesRegex(RuntimeError,"not from this original actor cast"):
            self.assets.for_frame(
                self.pid,"different_cast","rigged_reel_plan",0,0)

    def test_original_glb_corruption_blocks_existing_cast_and_recovery(self):
        self.register()
        self.cast()
        record = self.assets.open(self.pid,"original_reviewed_lead")
        path=self.index._blob_path(self.pid,record["data"]["glb_sha256"])
        path.write_bytes(b"changed GLB source bytes")
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            P1FReviewedProductionCharacters(FilmIndex(self.fixture.studio)).open_cast(
                self.pid,"original_reviewed_cast")


if __name__=="__main__":
    unittest.main()
