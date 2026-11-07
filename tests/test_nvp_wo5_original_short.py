"""WO5 source-custody eligibility contracts; no film fabricated by tests."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_wo5_original_short import (
    inspect_frame_variation, inspect_original_short_readiness)
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal


def receipts(count, varied=True):
    output = []
    for i in range(count):
        source = i if varied else i % 3
        output.append({
            "position": i,
            "source_sha256": hashlib.sha256(
                ("source-"+str(source)).encode()).hexdigest(),
            "j2k_sha256": hashlib.sha256(
                ("j2k-"+str(source)).encode()).hexdigest(),
            "segment_state": "VERIFIED",
        })
    return output


class OriginalShortReadinessTest(unittest.TestCase):
    def test_exact_30s_distinct_source_receipts_do_not_count_as_creative_acceptance(self):
        result = inspect_frame_variation(receipts(720), 720)
        self.assertEqual(result["frame_count"],720)
        self.assertEqual(result["film_time_seconds"],30)
        self.assertEqual(result["distinct_source_sha256_count"],720)
        self.assertFalse(result["visual_motion_or_originality_proven"])
        self.assertFalse(result["creative_intent_proven"])

    def test_repeated_three_frame_synthetic_stand_in_is_not_original_proof(self):
        with self.assertRaisesRegex(PermissionError,"stand-ins"):
            inspect_frame_variation(receipts(720,False),720)

    def test_missing_tampered_unverified_or_unordered_receipts_rejected(self):
        for field,value in [
            ("position",0),("source_sha256","INVALID"),
            ("j2k_sha256",None),("segment_state","PENDING")
        ]:
            items = receipts(48)
            items[1][field] = value
            with self.subTest(field=field):
                with self.assertRaises(PermissionError):
                    inspect_frame_variation(items,48)
        with self.assertRaises(PermissionError):
            inspect_frame_variation(receipts(48)[:-1],48)

    def test_proof_duration_bounded_and_boolean_not_integer(self):
        for count in (0,23,721):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    inspect_frame_variation(receipts(count),count)
        with self.assertRaises(ValueError):
            inspect_frame_variation(receipts(24),True)

    def test_untrusted_browser_and_nonexistent_production_jobs_never_admit(self):
        with self.assertRaises(PermissionError):
            inspect_original_short_readiness({},{},"project","job")
        with TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            index = FilmIndex(Studio(root/"studio.sqlite3"))
            journal = CinemaDeliveryJournal(root/"production")
            with self.assertRaises(KeyError):
                inspect_original_short_readiness(index,journal,
                                                  "0"*32,"made-up-job")


if __name__ == "__main__":
    unittest.main()
