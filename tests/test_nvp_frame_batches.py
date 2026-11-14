"""FILM-01A production-length frame-batch regression contracts."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.nvp_frame_batches import materialize_batch, plan_batches, verify_batch


def fixture(total):
    blobs = {i: b"fixture-frame-" + str(i).encode() for i in range(1, 5)}
    rows = (
        {"edit_frame": n, "source_frame": (n - 1) % 4 + 1,
         "source_sha256": hashlib.sha256(blobs[(n - 1) % 4 + 1]).hexdigest(),
         "shot_id": "A" if n <= total // 2 else "B"}
        for n in range(1, total + 1)
    )
    return rows, blobs


class FrameBatchContracts(unittest.TestCase):
    def test_720_frames_restart_reuse(self):
        rows, blobs = fixture(720)
        plans = plan_batches(rows, source_revision_sha256="a" * 64, batch_frames=48)
        self.assertEqual(len(plans), 15)
        with tempfile.TemporaryDirectory() as root:
            for plan in plans:
                result = materialize_batch(
                    root, plan, get_source_bytes=lambda r: blobs[r["source_frame"]])
                self.assertEqual(result["status"], "VERIFIED_CREATED")
            for plan in plans:
                self.assertTrue(verify_batch(root, plan))
                result = materialize_batch(
                    root, plan, get_source_bytes=lambda r: None)
                self.assertEqual(result["status"], "VERIFIED_REUSED")
        self.assertEqual(plans[-1]["end_frame_exclusive"], 721)

    def test_1440_frame_planning_preserves_source(self):
        rows, _ = fixture(1440)
        plans = plan_batches(rows, source_revision_sha256="b" * 64, batch_frames=96)
        self.assertEqual(len(plans), 15)
        self.assertEqual(sum(len(p["frames"]) for p in plans), 1440)
        self.assertEqual(plans[0]["frames"][0]["source_frame"], 1)
        self.assertEqual(plans[-1]["frames"][-1]["source_frame"], 4)

    def test_interrupted_batch_is_not_overwritten(self):
        rows, blobs = fixture(3)
        plan = plan_batches(rows, source_revision_sha256="a" * 64)[0]
        def crash(row):
            if row["edit_frame"] == 2:
                raise RuntimeError("simulated power loss")
            return blobs[row["source_frame"]]
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, "power loss"):
                materialize_batch(root, plan, get_source_bytes=crash)
            self.assertFalse(verify_batch(root, plan))
            with self.assertRaisesRegex(RuntimeError, "reconciliation"):
                materialize_batch(
                    root, plan, get_source_bytes=lambda r: blobs[r["source_frame"]])

    def test_source_tampering_is_detected(self):
        rows, blobs = fixture(3)
        plan = plan_batches(rows, source_revision_sha256="a" * 64)[0]
        with tempfile.TemporaryDirectory() as root:
            materialize_batch(root, plan, get_source_bytes=lambda r: blobs[r["source_frame"]])
            frame = Path(root) / plan["plan_sha256"] / "frame_000000002.png"
            frame.write_bytes(b"tampered")
            self.assertFalse(verify_batch(root, plan))
            with self.assertRaisesRegex(RuntimeError, "reconciliation"):
                materialize_batch(
                    root, plan, get_source_bytes=lambda r: blobs[r["source_frame"]])

    def test_noncontiguous_or_invalid_plan_fails(self):
        rows, _ = fixture(3)
        rows = list(rows)
        rows[1]["edit_frame"] = 99
        with self.assertRaisesRegex(ValueError, "non-contiguous"):
            plan_batches(rows, source_revision_sha256="a" * 64)
        with self.assertRaises(ValueError):
            plan_batches([], source_revision_sha256="0" * 63)


if __name__ == "__main__":
    unittest.main()
