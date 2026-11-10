"""PLAN-02-D1 source window admission regressions; not renderer acceptance.

Fixtures supply genuine OpenUSD frozen Takes and independently published
camera rails. No mocked frame output, OS approval or process custody is
counted as proven by these tests.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from test_nvp_plan02c_native_camera_ai import CanonicalDirectorRailTests
from backend.nvp_plan02d_source_selection import ExactSourceWindowSelector
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


class ExactSourceSelectionTests(unittest.TestCase):
    def setUp(self):
        CanonicalDirectorRailTests.setUp(self)
        self.selector = ExactSourceWindowSelector(self.index)
        self.request = {
            "take_id": self.spec["take_id"],
            "take_document_sha256": self.spec["take_document_sha256"],
            "camera_timeline_id": self.spec["camera_timeline_id"],
            "camera_timeline_revision": self.spec["camera_timeline_revision"],
            "camera_timeline_sha256": self.spec["camera_timeline_sha256"],
            "first_tick": 0,
            "last_tick_exclusive": T,
            "camera_mode": "original",
            "rail_id": None,
            "rail_revision": None,
            "rail_document_sha256": None,
        }

    def test_exact_source_ticks_and_derived_only_preview(self):
        original = self.index.read_revision(
            self.pid, self.spec["take_id"], 1)["document_sha256"]
        original_pcm = self.sound.read(self.pid, "mic_signal", 1, 0, 100)
        before = self.index.list_objects(self.pid, kind="presentation")
        preview = self.selector.preview(self.pid, self.request)
        self.assertFalse(preview["renderer_worker_authorized"])
        self.assertFalse(preview["native_os_approval_granted"])
        self.assertTrue(preview["derived_sample_cadence_is_not_source_time"])
        self.assertFalse(preview["ffmpeg_required"])
        self.assertEqual(preview["first_tick"], 0)
        sample = self.selector.sample_at(
            self.pid, self.request, preview["selection_sha256"], 1234567)
        self.assertEqual(sample["source_tick"], 1234567)
        self.assertEqual(sample["source_snapshot"]["time_tick"], 1234567)
        self.assertIsNone(sample["approved_director_camera_pose"])
        self.assertFalse(sample["renderer_worker_authorized"])
        self.assertEqual(
            self.index.read_revision(
                self.pid, self.spec["take_id"], 1)["document_sha256"], original)
        self.assertEqual(
            self.sound.read(self.pid, "mic_signal", 1, 0, 100), original_pcm)
        self.assertEqual(self.index.list_objects(self.pid, kind="presentation"), before)

    def test_reject_unreviewed_rail_stale_source_and_changed_preview(self):
        trial = self.selector.preview(self.pid, self.request)
        stale = deepcopy(self.request)
        stale["take_document_sha256"] = "0" * 64
        with self.assertRaises(PermissionError):
            self.selector.preview(self.pid, stale)
        stale = deepcopy(self.request)
        stale["rail_id"] = self.rail
        with self.assertRaises(PermissionError):
            self.selector.preview(self.pid, stale)
        stale = deepcopy(self.request)
        stale["last_tick_exclusive"] = T + 1
        with self.assertRaises(PermissionError):
            self.selector.sample_at(
                self.pid, stale, trial["selection_sha256"], 1234567)
        with self.assertRaises(PermissionError):
            self.selector.sample_at(
                self.pid, self.request, trial["selection_sha256"], T)
        stale = deepcopy(self.request)
        stale["first_tick"] = True
        with self.assertRaises(ValueError):
            self.selector.preview(self.pid, stale)
        stale = deepcopy(self.request)
        stale["last_tick_exclusive"] = T * 6
        with self.assertRaises(ValueError):
            self.selector.preview(self.pid, stale)
        stale = deepcopy(self.request)
        stale["untrusted_approval"] = True
        with self.assertRaises(PermissionError):
            self.selector.preview(self.pid, stale)

    def test_only_independently_verified_human_published_rail_is_selectable(self):
        before = self.selector.preview(self.pid, self.request)
        trial = self.service.preview(
            self.pid, self.rail, self.spec, expected_revision=0)
        self.native_allow = False
        with self.assertRaises(PermissionError):
            self.service.publish(
                self.pid, self.rail, self.spec, 0, trial["proposal_sha256"])
        not_approved = {
            **self.request, "camera_mode": "approved_rail",
            "rail_id": self.rail, "rail_revision": 1,
            "rail_document_sha256": "0" * 64,
        }
        with self.assertRaises(KeyError):
            self.selector.preview(self.pid, not_approved)
        self.native_allow = True
        saved = self.service.publish(
            self.pid, self.rail, self.spec, 0, trial["proposal_sha256"])
        approved = {
            **not_approved,
            "rail_document_sha256": saved["rail_document_sha256"],
        }
        preview = self.selector.preview(self.pid, approved)
        self.assertNotEqual(
            preview["selection_sha256"], before["selection_sha256"])
        self.assertEqual(
            preview["approved_rail"]["rail_layer_sha256"], saved["layer_sha256"])
        sample = self.selector.sample_at(
            self.pid, approved, preview["selection_sha256"], 1234567)
        self.assertEqual(
            sample["approved_director_camera_pose"]["film_tick"], 1234567)
        self.assertFalse(sample["renderer_worker_authorized"])
        forged = deepcopy(approved)
        forged["rail_document_sha256"] = "0" * 64
        with self.assertRaises(PermissionError):
            self.selector.preview(self.pid, forged)
        forged = deepcopy(approved)
        forged["camera_timeline_sha256"] = "0" * 64
        with self.assertRaises(PermissionError):
            self.selector.preview(self.pid, forged)


if __name__ == "__main__":
    unittest.main()
