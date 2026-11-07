"""WO5-01 corrected 30-minute multi-reel source-custody admission tests.

These are technical *contract* tests; no synthetic data can satisfy director
approval or independent cinema certification.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import FeatureJournal, FRAME_TICKS
from backend.nvp_wo5_original_feature import (
    FORMAT, MAX_FRAMES, _FrameDigestReview,
    inspect_ordered_feature_reels, inspect_original_feature_readiness)


def parts(frame_counts):
    result = []
    cursor = 0
    for count in frame_counts:
        result.append({
            "frames": count, "start_tick": cursor * FRAME_TICKS,
            "end_tick": (cursor + count) * FRAME_TICKS,
        })
        cursor += count
    return result


def digest(n):
    return sha256(str(n).encode("ascii")).hexdigest()


class WO5ThirtyMinuteFeature(unittest.TestCase):
    def test_six_five_minute_reels_exactly_thirty_minutes(self):
        evidence = inspect_ordered_feature_reels(parts([7200] * 6))
        self.assertEqual(evidence["frame_count"], 43200)
        self.assertEqual(evidence["seconds"], 1800)
        self.assertEqual(evidence["reel_count"], 6)
        self.assertEqual(evidence["duration_ticks"], 43200 * FRAME_TICKS)

    def test_uneven_valid_reels_and_no_gap(self):
        evidence = inspect_ordered_feature_reels(parts([311, 7199, 107]))
        self.assertEqual(evidence["frame_count"], 7617)
        for bad in (parts([7200]*6+[3]),):  # over thirty minutes
            with self.assertRaises(ValueError):
                inspect_ordered_feature_reels(bad)
        with self.assertRaises(PermissionError):
            inspect_ordered_feature_reels(parts([7200,7201]))
        for tweak in ("start_tick", "end_tick"):
            broken = parts([500,600])
            broken[1][tweak] += FRAME_TICKS
            with self.subTest(tweak=tweak):
                with self.assertRaises(PermissionError):
                    inspect_ordered_feature_reels(broken)
        with self.assertRaises(PermissionError):
            inspect_ordered_feature_reels([{"frames":True, "start_tick":0,
                                           "end_tick":FRAME_TICKS}]*2)
        with self.assertRaises(PermissionError):
            inspect_ordered_feature_reels(parts([12]))

    def test_exact_43200_distinct_frame_receipts_are_still_not_creative_acceptance(self):
        seen = _FrameDigestReview(MAX_FRAMES)
        for i in range(MAX_FRAMES):
            original = f"{i:064x}"
            encoded = f"{i+MAX_FRAMES:064x}"
            seen.add(i, original, encoded, "VERIFIED", original)
        report = seen.finish()
        self.assertEqual(report["distinct_original_picture_sha256"], MAX_FRAMES)
        self.assertEqual(report["distinct_native_j2k_sha256"], MAX_FRAMES)
        self.assertFalse(report["visual_motion_quality_or_originality_verified"])
        self.assertRegex(report["ordered_picture_custody_sha256"], r"^[0-9a-f]{64}$")

    def test_three_repeated_synthetic_frames_fail_thirty_minute_proof(self):
        seen = _FrameDigestReview(MAX_FRAMES)
        for i in range(MAX_FRAMES):
            source = digest(i % 3)
            encoded = digest(i % 3 + 10)
            seen.add(i, source, encoded, "VERIFIED", source)
        with self.assertRaisesRegex(PermissionError,"repeated synthetic"):
            seen.finish()

    def test_unapproved_frame_missing_frame_and_reordering_fail(self):
        seen = _FrameDigestReview(24)
        with self.assertRaises(PermissionError):
            seen.add(1,digest(1),digest(2),"VERIFIED",digest(1))
        with self.assertRaises(PermissionError):
            seen.add(0,digest(1),digest(2),"VERIFIED",digest(3))
        with self.assertRaises(PermissionError):
            seen.add(0,"malformed",digest(2),"VERIFIED",digest(1))
        with self.assertRaises(PermissionError):
            seen.add(0,digest(1),digest(2),"PENDING",digest(1))
        with self.assertRaises(PermissionError):
            seen.finish()
        with self.assertRaises(ValueError):
            _FrameDigestReview(MAX_FRAMES+1)

    def test_untrusted_or_unindexed_feature_cannot_count_as_real_film(self):
        with self.assertRaises(PermissionError):
            inspect_original_feature_readiness({}, {}, "0"*32, "wrong")
        with TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            index = FilmIndex(Studio(root/"original_studio.sqlite3"))
            journal = FeatureJournal(root/"native_production")
            with self.assertRaises(KeyError):
                inspect_original_feature_readiness(
                    index, journal, "0"*32,
                    "17cb5f21-e9a9-40f5-93a6-a6507c7c2b61")


if __name__ == "__main__":
    unittest.main()
