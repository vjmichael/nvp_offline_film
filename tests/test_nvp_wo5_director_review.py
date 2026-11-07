"""WO5-02: creator intent and observations are durable, not AI acceptance."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import ASSEMBLY_FORMAT, FRAME_TICKS
from backend.nvp_wo5_director_review import (
    INTENT_FORMAT, REVIEW_FORMAT, register_director_intent,
    record_director_review, validate_director_shots,
    validate_director_observations)


def planned_shots():
    return [
        {"shot_id":"Establish", "start_tick":0,
         "end_tick":60*FRAME_TICKS,
         "expected_action":"Actor walks into the harbor",
         "expected_camera":"Wide view with slow pan",
         "expected_sound":"Footsteps and water"},
        {"shot_id":"Dialogue", "start_tick":60*FRAME_TICKS,
         "end_tick":100*FRAME_TICKS,
         "expected_action":"Actor addresses companion",
         "expected_camera":"Stable two-shot with eyelines",
         "expected_sound":"Words are audible over surf"},
    ]


def human_observations():
    return [
        {"shot_id":"Establish", "observed_action":"Actor enters harbor",
         "observed_camera":"Slow wide camera pan",
         "observed_sound":"Footsteps, water", "judgment":"MATCHED",
         "review_note":"Appearance looked as directed"},
        {"shot_id":"Dialogue", "observed_action":"Actor speaks",
         "observed_camera":"Two-shot loses eyeline",
         "observed_sound":"Dialogue masked by surf",
         "judgment":"NEEDS_REVISION", "review_note":"Correct eyeline and dialog level"},
    ]


class IntentCustodyTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.studio=Studio(self.root/"studio.sqlite3")
        self.pid=self.studio.create_project("Original film","Film about a harbor")["id"]
        self.index=FilmIndex(self.studio)
        self.assembly=self.index.register_revision(
            self.pid,"OriginalFilmCut","edit",
            {"format":ASSEMBLY_FORMAT,
             "ordered_reel_job_ids":["future-reel-a","future-reel-b"],
             "start_tick":0,"end_tick":100*FRAME_TICKS},
            expected_revision=0,dependencies=[])

    def intent(self, **replace):
        inputs={"index":self.index,"project_id":self.pid,
                "assembly_id":"OriginalFilmCut","assembly_revision":1,
                "intent_id":"PreScreenDirectorIntent","shots":planned_shots(),
                "approve":lambda _:True}
        inputs.update(replace)
        return register_director_intent(**inputs)

    def test_intent_requires_explicit_host_consent_and_is_immutable(self):
        denied=self.intent(approve=lambda _:False)
        self.assertEqual(denied["status"],"DENIED")
        self.assertEqual(self.index.history(self.pid,"PreScreenDirectorIntent"),[])
        result=self.intent()
        self.assertEqual(result["status"],"DIRECTOR_INTENT_FROZEN_NOT_FILM_ACCEPTED")
        saved=self.index.read_revision(self.pid,"PreScreenDirectorIntent",1)
        self.assertEqual(saved["data"]["format"],INTENT_FORMAT)
        self.assertEqual(saved["data"]["source_assembly_sha256"],
                         self.assembly["document_sha256"])
        self.assertEqual(saved["dependencies"][0]["object_id"],"OriginalFilmCut")
        self.assertFalse(saved["data"]["film_created"])
        with self.assertRaises(FileExistsError):
            self.intent()

    def test_shot_timing_duplicates_and_untrusted_text_fail_before_consent(self):
        broken=planned_shots()
        broken[1]["start_tick"]-=FRAME_TICKS
        with self.assertRaisesRegex(PermissionError,"gap, overlap"):
            self.intent(shots=broken)
        broken=planned_shots()
        broken[1]["shot_id"]="Establish"
        with self.assertRaises(PermissionError):
            self.intent(shots=broken)
        broken=planned_shots()
        broken[0]["expected_sound"]=""
        with self.assertRaises(ValueError):
            self.intent(shots=broken)
        with self.assertRaises(PermissionError):
            validate_director_shots(planned_shots(),100*FRAME_TICKS+1)

    def test_human_report_must_follow_exact_planned_shots(self):
        shots=planned_shots()
        observations=human_observations()
        report=validate_director_observations(shots, observations,True,True)
        self.assertTrue(report["director_review_complete_by_self_report"])
        self.assertTrue(report["director_requests_revisions"])
        self.assertFalse(report["director_reports_all_shots_matched"])
        self.assertFalse(report["production_acceptance"])
        swapped=observations[::-1]
        with self.assertRaises(PermissionError):
            validate_director_observations(shots,swapped,True,True)
        with self.assertRaises(PermissionError):
            validate_director_observations(shots,observations,1,True)
        bad=human_observations()
        bad[0]["observed_sound"]=""
        with self.assertRaises(PermissionError):
            validate_director_observations(shots,bad,True,True)

    def test_review_is_source_bound_human_self_report_not_a_dcp_certificate(self):
        self.intent()
        feature_cpl="11111111-2222-4333-8444-555555555555"
        record_id="WO4FEATURE_"+feature_cpl.replace("-","")
        feature=self.index.register_revision(
            self.pid,record_id,"presentation",
            {"format":"test.reconstructed_feature_metadata.v1"},
            expected_revision=0,dependencies=[])
        audit={"assembly_id":"OriginalFilmCut",
               "assembly_revision":1,
               "assembly_sha256":self.assembly["document_sha256"],
               "duration_ticks":100*FRAME_TICKS,
               "filmindex_feature_receipt_sha256":feature["document_sha256"],
               "ordered_picture_custody_sha256":"a"*64,
               "cpl_uuid":feature_cpl}
        args=dict(index=self.index,journal=object(),project_id=self.pid,
                  feature_id="sample-feature",intent_id="PreScreenDirectorIntent",
                  review_id="CreatorViewing1",
                  observations=human_observations(),
                  watched_entire_film=True,heard_entire_sound=True,
                  approve=lambda _:True)
        # Only the *film proof* entrypoint is mocked here. This verifies
        # FilmIndex and host-authored review behavior, not production media.
        with patch("backend.nvp_wo5_director_review.inspect_original_feature_readiness",
                   return_value=audit):
            denied=record_director_review(**dict(args,approve=lambda _:False))
            self.assertEqual(denied["status"],"DENIED")
            result=record_director_review(**args)
        self.assertEqual(result["status"],
                         "DIRECTOR_OBSERVATIONS_RECORDED_NOT_INDEPENDENTLY_VERIFIED")
        self.assertTrue(result["director_review_complete_by_self_report"])
        self.assertTrue(result["director_requests_revisions"])
        self.assertFalse(result["production_acceptance"])
        saved=self.index.read_revision(self.pid,"CreatorViewing1",1)
        self.assertEqual(saved["data"]["format"],REVIEW_FORMAT)
        self.assertTrue(saved["data"]["creator_self_report_only"])
        self.assertFalse(saved["data"]["smpte_dcp_bv21_verified"])
        self.assertFalse(saved["data"]["production_acceptance"])
        self.assertEqual(len(saved["dependencies"]),2)
        self.assertEqual(self.index.read_revision(
            self.pid,"OriginalFilmCut",1)["document_sha256"],
            self.assembly["document_sha256"])
        with self.assertRaises(FileExistsError):
            record_director_review(**args)

    def test_review_rejects_nonexistent_feature_without_mocks(self):
        self.intent()
        with self.assertRaises(PermissionError):
            record_director_review(
                self.index, object(), self.pid,feature_id="bogus",
                intent_id="PreScreenDirectorIntent",review_id="NeverCreated",
                observations=human_observations(),
                watched_entire_film=True,heard_entire_sound=True,
                approve=lambda _:True)


if __name__ == "__main__":
    unittest.main()
